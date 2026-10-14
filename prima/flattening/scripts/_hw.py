"""Open live HW stack for flattening scripts (DAO DM + Aravis + E-518)."""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from prima.drop1_defaults import (
    DEFAULT_E518_HOST, DEFAULT_E518_PORT, DEFAULT_EXPOSURE_MS,
    DEFAULT_MANTA_IP, DEFAULT_MOD_FREQ_HZ, DEFAULT_MOD_RADIUS_MRAD,
    exposure_ms_one_mod_period)
from prima.flattening.devices.aravis_camera import AravisCamera
from prima.flattening.devices.bmc_dm import BmcMultiDm
from prima.flattening.devices.live_pyramid import LivePyramid
from prima.hardware.pi_e518_modulator import PiE518Modulator


@dataclass
class LiveStack:
    dm: BmcMultiDm
    camera: AravisCamera
    modulator: PiE518Modulator
    wfs: LivePyramid
    autocenter_result: object | None = None

    def close(self, park_dm: bool = True, leave_modulating: bool = True):
        if park_dm:
            try:
                self.dm.park()
            except Exception as exc:
                print('DM park warning:', exc)
        try:
            self.dm.close()
        except Exception:
            pass
        if not leave_modulating:
            try:
                self.modulator.close()
            except Exception:
                pass
        else:
            # Release GCS TCP without parking wavegen to 0 — keep 4 mrad if up.
            try:
                if getattr(self.modulator, '_gcs', None) is not None:
                    self.modulator._gcs.close()
                    self.modulator._setup_done = False
            except Exception:
                pass
        try:
            self.camera.close()
        except Exception:
            pass


def open_live_stack(
        prefer: str = 'dao',
        park_dm: bool = True,
        radius_mrad: float = DEFAULT_MOD_RADIUS_MRAD,
        freq_hz: float = DEFAULT_MOD_FREQ_HZ,
        exposure_ms: float | None = None,
        lock_exp_to_mod: bool = True,
        geometry_dir=None,
        autocenter: bool = True,
        autocenter_duration_s: float = 8.0,
        restore_mod_center: bool = True,
) -> LiveStack:
    """Connect DM (DAO/USB), Aravis Mono12, E-518 @ work defaults, LivePyramid.

    By default runs **autocenter** before returning (required before IFF so
    PWFS pupils are not flux-saturated). Pass ``autocenter=False`` only for
    diagnostics. When ``geometry_dir`` has ``mod_center_mrad.npy``, that
    center is restored instead of re-running autocenter (IFF/flatten match).

    Exposure defaults to **one modulator period** ``t_exp = 1000/f_mod`` ms
    (``lock_exp_to_mod=True``). Pass ``exposure_ms=...`` to override.
    """
    dm = BmcMultiDm(prefer=prefer, dry_run=False)
    if park_dm:
        dm.park()
    mod = PiE518Modulator(
        host=DEFAULT_E518_HOST, port=DEFAULT_E518_PORT, connect=True)
    mod.setFrequencyInHz(float(freq_hz))
    mod.setRadiusInMilliRad(float(radius_mrad))
    # Start near mid; autocenter will null tip/tilt
    try:
        mod.setCenterInMilliRad((0.0, 0.0))
    except Exception:
        pass
    time.sleep(0.8)
    if exposure_ms is None:
        if lock_exp_to_mod:
            exposure_ms = exposure_ms_one_mod_period(freq_hz)
        else:
            exposure_ms = float(DEFAULT_EXPOSURE_MS)
    else:
        exposure_ms = float(exposure_ms)
    print('camera t_exp=%.2f ms  (1/f_mod=%.2f ms, lock=%s)' % (
        exposure_ms, exposure_ms_one_mod_period(freq_hz), lock_exp_to_mod))
    cam = AravisCamera(ip_address=DEFAULT_MANTA_IP, exposure_ms=exposure_ms)
    time.sleep(0.3)
    wfs = LivePyramid(cam, modulator=mod, nframes=2, detect_threshold=400.0)

    ac_result = None
    gdir = Path(geometry_dir) if geometry_dir is not None else None
    restored = False
    if gdir is not None and wfs.load_geometry(gdir):
        mode = wfs.mode
        cpath = gdir / 'mod_center_mrad.npy'
        if restore_mod_center and cpath.exists():
            c = np.load(cpath).astype(float).ravel()[:2]
            mod.setCenterInMilliRad((float(c[0]), float(c[1])))
            time.sleep(0.5)
            restored = True
            print('restored mod center (mrad) = %.3f, %.3f' % (c[0], c[1]))
            autocenter = False  # keep IFF working point
    else:
        mode = wfs.ensure_pupils(detect=True)

    if autocenter:
        from prima.flattening.autocenter import (
            ensure_engine_for_autocenter, run_autocenter)
        from prima.flattening.scripts._vis import save_frame_with_pupils
        from prima.flattening.scripts._common import media_path
        eng = ensure_engine_for_autocenter(wfs, mod)
        # Refresh pupils at current mod before align
        try:
            frame = np.asarray(cam.acquire_frames(2), dtype=float)
            from prima.flattening.pupils import find_pupils_prima
            geo = find_pupils_prima(frame, engine=eng)
            eng.set_pyramid_geometry(geo.centers)
            eng.set_pupil_radius(geo.radius)
            wfs._centers = geo.as_yx()
            wfs._radius = float(geo.radius)
            save_frame_with_pupils(
                frame, geo.centers, geo.radius,
                'flatten-vis-autocenter-before.png',
                title='Pre-autocenter pupils (may be unbalanced/saturated)')
        except Exception as exc:
            print('autocenter pre-pupil vis skip:', exc)
        print('running autocenter for %.1fs (pre-IFF)…' % autocenter_duration_s)
        ac_result = run_autocenter(
            eng, duration_s=autocenter_duration_s, camera=cam,
            flux_balance=True)
        print('autocenter done: C=%.3f,%.3f → %.3f,%.3f  peak %.0f→%.0f  %s' % (
            ac_result.center_before[0], ac_result.center_before[1],
            ac_result.center_after[0], ac_result.center_after[1],
            ac_result.peak_before, ac_result.peak_after, ac_result.notes))
        if ac_result.fluxes_before is not None and ac_result.fluxes_after is not None:
            print('  fluxes before', np.round(ac_result.fluxes_before, 1),
                  'after', np.round(ac_result.fluxes_after, 1))
        # Re-find pupils after tip/tilt move
        mode = wfs.ensure_pupils(detect=True)
        try:
            frame2 = np.asarray(cam.acquire_frames(2), dtype=float)
            save_frame_with_pupils(
                frame2, wfs._centers, wfs._radius,
                'flatten-vis-autocenter-after.png',
                title='Post-autocenter C=%.2f,%.2f peak=%.0f' % (
                    ac_result.center_after[0], ac_result.center_after[1],
                    ac_result.peak_after))
        except Exception as exc:
            print('autocenter post-pupil vis skip:', exc)

    print('live stack: dm=%s wfs=%s R=%.1f f=%.1f exp=%.1fms autocenter=%s restored=%s' % (
        dm, mode, radius_mrad, freq_hz, exposure_ms, autocenter or False, restored))
    return LiveStack(
        dm=dm, camera=cam, modulator=mod, wfs=wfs, autocenter_result=ac_result)
