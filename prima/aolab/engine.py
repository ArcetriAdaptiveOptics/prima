"""AO lab engine: one real-time thread that does WFS -> reconstructor ->
integrator -> DM, plus calibration and disturbance injection.

DM command = flat + sum of channels (like the DAO "DM channels"):

    'loop'   integrator output (closed loop correction)
    'turb'   frozen-flow turbulence generated with the DM
    'static' static aberration (Zernike sliders)
    'calib'  push/pull pokes during the interaction matrix
    'user'   manual pokes / modes from the GUI

The total is clipped to [0, 1] and to +-``max_delta`` around the flat.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np

from prima.aolab import dm_geometry as G
from prima.aolab.calibration import (InteractionMatrix, Reconstructor,
                                     build_im, make_reconstructor)
from prima.aolab.disturbance import FrozenFlowTurbulence, StaticAberration
from prima.aolab.telemetry import Telemetry
from prima.aolab.wfs import PupilGeometry, PyramidProcessor, find_pupils

DATA_DIR = Path.home() / 'git' / 'prima_data'
CHANNELS = ('loop', 'turb', 'static', 'calib', 'user')


@dataclass
class LoopParams:
    gain: float = 0.3
    leak: float = 0.99
    n_modes: int = 60            # modes used by the reconstructor
    n_cut: int = 0               # extra SVD cut
    max_delta: float = 0.25      # +- around flat, DM units
    diverge_factor: float = 4.0  # watchdog: open if slope rms > f * start
    diverge_frames: int = 30


@dataclass
class CalibParams:
    basis: str = 'kl'            # kl | zernike | zonal | hadamard
    n_modes: int = 90
    amplitude: float = 0.01      # DM units (rms over pupil actuators)
    n_avg: int = 2               # frames averaged per push / pull
    settle: int = 2              # frames skipped after each DM change
    pupil_margin: float = 0.0    # actuator selection margin (pitches)
    pupil_diam_mm: float = 4.5


class AOEngine:
    def __init__(self, camera, dm, modulator, flat: np.ndarray,
                 nm_per_unit: float | None = None, log=print):
        self.cam, self.dm, self.mod = camera, dm, modulator
        self.log = log
        self.flat = np.clip(np.asarray(flat, float).ravel(), 0, 1)
        # wavefront nm per DM unit about the flat (2 x surface,
        # MEMS deflection ~ stroke u^2 -> d/du = 2 stroke u)
        self.nm_per_unit = (nm_per_unit if nm_per_unit is not None
                            else 2 * 2 * 5500.0 * float(self.flat.mean()))
        self.lp = LoopParams()
        self.cp = CalibParams()
        self.ch = {k: np.zeros(G.N_ACT) for k in CHANNELS}
        self._dm_dirty = True
        self._lock = threading.RLock()
        self._meas = threading.Condition()
        self._meas_id = 0
        self._last = {}
        self.last_frame = None
        self.frame_id = 0
        self.proc: PyramidProcessor | None = None
        self.geom: PupilGeometry | None = None
        self.imat: InteractionMatrix | None = None
        self.rec: Reconstructor | None = None
        self.loop_closed = False
        self._c = None                 # modal integrator state
        self.active = G.pupil_actuators(self.cp.pupil_diam_mm,
                                        self.cp.pupil_margin)
        self.static = StaticAberration(self.active, self.cp.pupil_diam_mm)
        self.turb: FrozenFlowTurbulence | None = None
        self.turb_on = False
        self.tel = Telemetry(3000, 0)
        self.sat_frac = 0.0
        self.status = 'idle'
        self.calib_progress = 0.0
        self._calib_stop = threading.Event()
        self._calib_thread = None
        self._watch = 0
        self._rms_at_close = None
        self._running = False
        self._thread = None
        self._t_loop: list[float] = []
        self._proj = None              # pinv(M2C) for disturbance modes

    # ============================================================ life
    def start(self):
        self.cam.start()
        self._apply_dm(force=True)
        self._running = True
        self._thread = threading.Thread(target=self._rtc, daemon=True,
                                        name='rtc')
        self._thread.start()
        self.status = 'running'

    def stop(self, park: bool = True):
        self.stop_calibration()
        self.open_loop()
        self._running = False
        if self._thread is not None:
            self._thread.join(3.0)
        if park:
            self.park_dm()
        try:
            self.cam.stop()
        except Exception:
            pass
        self.status = 'stopped'

    def park_dm(self, ramp_s: float = 0.5, steps: int = 10):
        """Ramp every channel to zero -> DM at flat."""
        with self._lock:
            start = {k: v.copy() for k, v in self.ch.items()}
        for i in range(1, steps + 1):
            with self._lock:
                for k in CHANNELS:
                    self.ch[k] = start[k] * (1 - i / steps)
            self._apply_dm(force=True)
            time.sleep(ramp_s / steps)
        self.turb_on = False

    # ============================================================== DM
    def total_command(self) -> np.ndarray:
        with self._lock:
            delta = sum(self.ch[k] for k in CHANNELS)
        delta = np.clip(delta, -self.lp.max_delta, self.lp.max_delta)
        cmd = self.flat + delta
        sat = (np.abs(delta) >= self.lp.max_delta - 1e-9) | (cmd <= 0) | \
            (cmd >= 1)
        self.sat_frac = float(sat[self.active].mean())
        return np.clip(cmd, 0.0, 1.0)

    def _apply_dm(self, force=False):
        if self._dm_dirty or force:
            self.dm.send(self.total_command())
            self._dm_dirty = False

    def set_channel(self, name: str, vec: np.ndarray | None):
        with self._lock:
            self.ch[name] = (np.zeros(G.N_ACT) if vec is None
                             else np.asarray(vec, float).ravel().copy())
            self._dm_dirty = True
        if not self._running:
            self._apply_dm()

    def set_flat(self, flat: np.ndarray):
        with self._lock:
            self.flat = np.clip(np.asarray(flat, float).ravel(), 0, 1)
            self._dm_dirty = True

    def flat_from_current(self) -> np.ndarray:
        """New flat = current total command (use after closing the loop
        on the reference you want as 'flat')."""
        return self.total_command()

    # ============================================================= WFS
    def detect_pupils(self, n_frames: int = 5) -> PupilGeometry:
        frames = [self.wait_frame()[1] for _ in range(n_frames)]
        g = find_pupils(np.mean(frames, axis=0))
        self.set_geometry(g)
        return g

    def set_geometry(self, g: PupilGeometry, npix_across: int = 32,
                     keep_calib: bool = False):
        """New pupil geometry.  ``keep_calib``: the same detector pixels
        are seen (e.g. after a ROI change, centres just shifted), so the
        reference, IM and reconstructor stay valid."""
        with self._lock:
            old = self.proc
            self.geom = g
            self.proc = PyramidProcessor(g, npix_across)
            if keep_calib and old is not None:
                self.proc.set_reference(old.ref)
                self.proc.dark_mode = old.dark_mode
                self.proc.dark_frames = old.dark_frames
                self.proc.dark = old.dark
            else:
                self.imat = None
                self.rec = None
                self._c = None
        self.log('pupils: r=%.1f px, %d valid px/pupil, %s'
                 % (g.radius, self.proc.n_valid, g.notes))

    # ---------------------------------------------------------- ROI
    def roi_to_pupils(self, margin_px: int = 5):
        """Crop the camera to the box tangent to the outer pupil edges
        (+ margin): fewer pixels to read and transfer -> faster frames.
        Geometry is shifted, calibration kept."""
        if self.geom is None:
            raise RuntimeError('find the pupils first')
        g = self.geom
        x0, y0, w, h = self.cam.get_roi()
        r = g.radius
        rmin = int(np.floor(g.centers[:, 0].min() - r - margin_px))
        rmax = int(np.ceil(g.centers[:, 0].max() + r + margin_px))
        cmin = int(np.floor(g.centers[:, 1].min() - r - margin_px))
        cmax = int(np.ceil(g.centers[:, 1].max() + r + margin_px))
        rmin, cmin = max(rmin, 0), max(cmin, 0)
        self._apply_roi(x0 + cmin, y0 + rmin, cmax - cmin, rmax - rmin)

    def roi_full(self):
        self._apply_roi(0, 0, 10 ** 5, 10 ** 5)

    def _apply_roi(self, x, y, w, h):
        ox, oy, _, _ = self.cam.get_roi()
        self.cam.set_roi(x, y, w, h)
        nx, ny, nw, nh = self.cam.get_roi()
        if self.geom is not None:
            c = self.geom.centers - np.array([ny - oy, nx - ox], float)
            g = PupilGeometry(c, self.geom.radius, (nh, nw),
                              self.geom.notes)
            self.set_geometry(g, self.proc.n if self.proc else 32,
                              keep_calib=True)
        self.log('camera ROI x=%d y=%d %dx%d' % (nx, ny, nw, nh))

    def set_reference(self, n_frames: int = 10, zero: bool = False):
        """Reference slopes = mean slopes now (or zero = 'absolute')."""
        if self.proc is None:
            raise RuntimeError('no pupils')
        if zero:
            self.proc.set_reference(None)
            return
        acc = [self.wait_measure()['slopes_raw'] for _ in range(n_frames)]
        self.proc.set_reference(np.mean(acc, axis=0))

    def wait_frame(self, timeout_s=3.0):
        """Next new frame (works whether or not the RTC is running)."""
        if not self._running:
            fid, f = self.cam.get_frame(True, timeout_s)
            self.last_frame = f
            return fid, f
        with self._meas:
            target = self._meas_id + 1
            if not self._meas.wait_for(lambda: self._meas_id >= target,
                                       timeout_s):
                raise TimeoutError('no frame')
            return self.frame_id, self.last_frame

    def wait_measure(self, skip: int = 0, timeout_s=3.0) -> dict:
        """Wait ``skip`` + 1 new processed frames, return last result."""
        with self._meas:
            target = self._meas_id + 1 + int(skip)
            if not self._meas.wait_for(lambda: self._meas_id >= target,
                                       timeout_s * (1 + skip)):
                raise TimeoutError('no measurement')
            return dict(self._last)

    # ============================================================= RTC
    def _rtc(self):
        while self._running:
            try:
                fid, frame = self.cam.get_frame(True, 1.0)
            except TimeoutError:
                continue
            except Exception as exc:
                self.log('camera error: %s' % exc)
                time.sleep(0.2)
                continue
            t0 = time.time()
            res = {}
            with self._lock:
                proc, rec = self.proc, self.rec
            if proc is not None and proc.geom.frame_shape[0] and \
                    tuple(frame.shape) != tuple(proc.geom.frame_shape):
                proc = None           # frame from before a ROI change
            if proc is not None:
                try:
                    res = proc.compute(frame)
                except Exception as exc:
                    self.log('slopes error: %s' % exc)
                    res = {}
            modes = None
            if res:
                s = res['slopes']
                if rec is not None:
                    modes = rec.rec @ s
                    if self.loop_closed:
                        self._integrate(modes)
            if self.turb_on and self.turb is not None:
                with self._lock:
                    self.ch['turb'] = self.turb.step()
                    self._dm_dirty = True
            self._apply_dm()
            self._telemetry(fid, res, modes)
            with self._meas:
                self.last_frame = frame
                self.frame_id = fid
                self._last = res
                self._meas_id += 1
                self._meas.notify_all()
            self._t_loop.append(time.time() - t0)
            if len(self._t_loop) > 100:
                self._t_loop = self._t_loop[-100:]

    def _integrate(self, modes):
        lp = self.lp
        if self._c is None or self._c.size != modes.size:
            self._c = np.zeros(modes.size)
        self._c = lp.leak * self._c - lp.gain * modes
        with self._lock:
            self.ch['loop'] = self.rec.m2c @ self._c
            self._dm_dirty = True

    def _telemetry(self, fid, res, modes):
        scal = {'t': time.time(), 'frame': fid,
                'loop_closed': float(self.loop_closed),
                'sat_frac': self.sat_frac}
        dist_modes = None
        if res:
            s = res['slopes']
            scal['slope_rms'] = float(np.sqrt(np.mean(s ** 2)))
            scal['flux'] = res['flux']
            scal['dark'] = res.get('dark') if res.get('dark') is not None \
                else np.nan
        if modes is not None:
            # modes are orthonormal with unit RMS on the active actuators
            # -> WF rms on the DM = sqrt(sum m_k^2)
            scal['mode_rms'] = float(np.sqrt(np.sum(modes ** 2)))
            if self._proj is not None:
                with self._lock:
                    d = self.ch['turb'] + self.ch['static']
                dist_modes = self._proj @ d
        with self._lock:
            scal['loop_cmd_rms'] = float(self.ch['loop'][self.active].std())
            scal['dist_rms'] = float((self.ch['turb']
                                      + self.ch['static'])[self.active].std())
            # what is left of the DM-made disturbance after the loop's
            # correction: (turb + static + loop) on the DM itself.  Independent
            # of the WFS noise; includes the (constant) bench-aberration
            # correction held by the loop.
            scal['dm_res_rms'] = float((self.ch['turb'] + self.ch['static']
                                        + self.ch['loop'])[self.active].std())
        self.tel.push(scal, modes, dist_modes)
        # watchdog
        if self.loop_closed and res:
            r = scal['slope_rms']
            ref = self._rms_at_close or r
            if r > self.lp.diverge_factor * max(ref, 1e-4) \
                    or self.sat_frac > 0.3:
                self._watch += 1
            else:
                self._watch = 0
            if self._watch > self.lp.diverge_frames:
                self.log('WATCHDOG: loop diverging (slope rms %.3g, '
                         'saturation %.0f%%) -> open loop + reset'
                         % (r, 100 * self.sat_frac))
                self.open_loop(reset=True)

    def loop_rate_hz(self) -> float:
        t = self.tel.series('t', 50)
        t = t[np.isfinite(t)]
        if t.size < 2:
            return 0.0
        return (t.size - 1) / max(t[-1] - t[0], 1e-6)

    def compute_time_ms(self) -> float:
        return 1e3 * float(np.mean(self._t_loop)) if self._t_loop else 0.0

    # ============================================================ loop
    def close_loop(self):
        if self.rec is None:
            raise RuntimeError('no reconstructor: calibrate first')
        if self.calibrating:
            raise RuntimeError('calibration running')
        r = self.tel.series('slope_rms', 20)
        r = r[np.isfinite(r)]
        self._rms_at_close = float(np.median(r)) if r.size else None
        self._watch = 0
        self.loop_closed = True
        self.log('loop CLOSED  gain=%.2f leak=%.3f modes=%d'
                 % (self.lp.gain, self.lp.leak, self.rec.n_modes))

    def open_loop(self, reset: bool = False):
        was = self.loop_closed
        self.loop_closed = False
        if reset:
            self.reset_loop()
        if was:
            self.log('loop OPEN' + (' (reset)' if reset else ''))

    def reset_loop(self):
        with self._lock:
            self._c = None
            self.ch['loop'] = np.zeros(G.N_ACT)
            self._dm_dirty = True

    # =================================================== calibration
    @property
    def calibrating(self) -> bool:
        return self._calib_thread is not None and self._calib_thread.is_alive()

    def basis(self) -> np.ndarray:
        cp = self.cp
        self.active = G.pupil_actuators(cp.pupil_diam_mm, cp.pupil_margin)
        return G.make_basis(cp.basis, self.active, cp.n_modes,
                            cp.pupil_diam_mm)

    def start_calibration(self, done_cb=None):
        if self.proc is None:
            raise RuntimeError('detect pupils first')
        if self.calibrating:
            raise RuntimeError('already calibrating')
        self.open_loop(reset=True)
        if self.turb_on:
            self.log('turbulence switched OFF for calibration')
            self.set_turbulence(False)
        self._calib_stop.clear()
        self._calib_thread = threading.Thread(
            target=self._calibrate, args=(done_cb,), daemon=True,
            name='calib')
        self._calib_thread.start()

    def stop_calibration(self):
        self._calib_stop.set()
        if self._calib_thread is not None:
            self._calib_thread.join(5.0)

    def _calibrate(self, done_cb):
        cp = self.cp
        try:
            B = self.basis()
            nm = B.shape[1]
            amp = cp.amplitude
            if cp.basis in ('zonal',):
                amp = cp.amplitude * 3      # single actuator: more signal
            self.log('IM: %s basis, %d modes, amp %.4f (~%.0f nm wf rms), '
                     'n_avg %d' % (cp.basis, nm, amp, amp * self.nm_per_unit,
                                   cp.n_avg))
            self.status = 'calibrating'
            t0 = time.time()
            ns = 2 * self.proc.n_valid
            plus = np.zeros((ns, nm))
            minus = np.zeros((ns, nm))
            for k in range(nm):
                for sgn, store in ((+1, plus), (-1, minus)):
                    if self._calib_stop.is_set():
                        raise InterruptedError
                    self.set_channel('calib', sgn * amp * B[:, k])
                    self.wait_measure(skip=cp.settle)
                    acc = [self.wait_measure()['slopes']
                           for _ in range(cp.n_avg)]
                    store[:, k] = np.mean(acc, axis=0)
                self.calib_progress = (k + 1) / nm
            self.set_channel('calib', None)
            im = build_im(plus, minus, amp)
            self.imat = InteractionMatrix(
                im, B, amp, cp.basis, cp.n_avg,
                {'time': time.strftime('%Y-%m-%d %H:%M:%S'),
                 'duration_s': time.time() - t0,
                 'geometry': self.geom.to_dict(),
                 'modulator': self.mod.state(),
                 'exposure_ms': self.cam.get_exposure_ms(),
                 'calib_params': asdict(cp)})
            self.log('IM done in %.0f s' % (time.time() - t0))
            self.update_reconstructor()
            ok = True
        except InterruptedError:
            self.log('IM aborted')
            ok = False
        except Exception as exc:
            self.log('IM failed: %r' % exc)
            ok = False
        finally:
            self.set_channel('calib', None)
            self.status = 'running'
        if done_cb:
            done_cb(ok)

    def update_reconstructor(self, n_modes: int | None = None,
                             n_cut: int | None = None):
        if self.imat is None:
            raise RuntimeError('no interaction matrix')
        if n_modes is not None:
            self.lp.n_modes = int(n_modes)
        if n_cut is not None:
            self.lp.n_cut = int(n_cut)
        rec = make_reconstructor(self.imat, self.lp.n_modes, self.lp.n_cut)
        was = self.loop_closed
        self.open_loop(reset=False)
        with self._lock:
            self.rec = rec
            self._c = None
            self._proj = np.linalg.pinv(rec.m2c)
            self.ch['loop'] = np.zeros(G.N_ACT)
            self._dm_dirty = True
        self.tel.reset(rec.n_modes)
        self.log('reconstructor: %d modes, %d SVD kept, cond %.1f'
                 % (rec.n_modes, rec.n_kept,
                    rec.singular_values[0] / rec.singular_values[-1]))
        if was:
            self.close_loop()

    # ==================================================== disturbance
    def set_turbulence(self, on: bool, rms: float | None = None,
                       wind: float | None = None, seed: int | None = None):
        if on and (self.turb is None or seed is not None):
            self.turb = FrozenFlowTurbulence(
                self.active, rms or 0.01, wind or 0.3,
                seed=0 if seed is None else seed)
        if self.turb is not None:
            if rms is not None:
                self.turb.rms = float(rms)
            if wind is not None:
                self.turb.wind = float(wind)
        self.turb_on = bool(on)
        if not on:
            self.set_channel('turb', None)

    def set_static(self, coeffs: dict):
        for j, a in coeffs.items():
            self.static.set(j, a)
        self.set_channel('static', self.static.command())

    # =================================================== persistence
    def save(self, tag: str = '') -> Path:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        d = DATA_DIR / (time.strftime('%Y%m%d_%H%M%S')
                        + ('_' + tag if tag else ''))
        d.mkdir()
        meta = {'flat_mean': float(self.flat.mean()),
                'loop': asdict(self.lp), 'calib': asdict(self.cp),
                'modulator': self.mod.state(),
                'exposure_ms': self.cam.get_exposure_ms()}
        arrays = {'flat': self.flat}
        if self.geom is not None:
            meta['geometry'] = self.geom.to_dict()
        if self.proc is not None:
            arrays['ref_slopes'] = self.proc.ref
        if self.imat is not None:
            arrays['im'] = self.imat.im
            arrays['m2c'] = self.imat.m2c
            meta['im'] = {'amplitude': self.imat.amplitude,
                          'basis': self.imat.basis, **self.imat.meta}
        np.savez_compressed(d / 'calib.npz', **arrays)
        (d / 'meta.json').write_text(json.dumps(meta, indent=1, default=str))
        self.log('saved %s' % d)
        return d

    def load(self, d: Path | str):
        d = Path(d)
        meta = json.loads((d / 'meta.json').read_text())
        arr = np.load(d / 'calib.npz')
        if 'geometry' in meta:
            self.set_geometry(PupilGeometry.from_dict(meta['geometry']))
            if 'ref_slopes' in arr:
                self.proc.set_reference(arr['ref_slopes'])
        if 'im' in arr:
            im = meta['im']
            self.imat = InteractionMatrix(arr['im'], arr['m2c'],
                                          im['amplitude'], im['basis'],
                                          meta=im)
            self.update_reconstructor()
        self.log('loaded %s' % d)
