"""Bench / simulator from a notebook, without the GUI.

    from prima.aolab import lab
    e = lab.sim_engine()                  # numerical twin, calibrated
    e.set_turbulence(True, rms=0.01, wind=0.3, seed=1)
    e.lp.gain = 0.4; e.close_loop()
    an = lab.record(e, 2048, 'g0.4')      # -> PrimaAnalyzer
    lab.close(e)

Only one program at a time can drive the real bench: close the GUI before
``lab.hw_engine()`` and call ``lab.close(e)`` at the end.
"""
from __future__ import annotations

import time

from prima.aolab.analysis import PrimaAnalyzer
from prima.aolab.engine import AOEngine


def _quiet(msg):
    pass


def calibrate(e: AOEngine, n_modes: int = 50, amplitude: float = 0.005,
              basis: str = 'kl', n_avg: int = 1, settle: int = 1,
              zero_reference: bool = True) -> AOEngine:
    """Find pupils, reference, push-pull IM and reconstructor (blocking)."""
    e.detect_pupils()
    e.set_reference(zero=zero_reference)
    e.cp.basis, e.cp.n_modes, e.cp.amplitude = basis, n_modes, amplitude
    e.cp.n_avg, e.cp.settle = n_avg, settle
    e.lp.n_modes = n_modes
    e.start_calibration()
    while e.calibrating:
        time.sleep(0.1)
    if e.rec is None:
        raise RuntimeError('calibration failed')
    return e


def sim_engine(fps: float = 200.0, calibrated: bool = True,
               n_modes: int = 50, flux: float | None = None, log=_quiet,
               **calib_kw) -> AOEngine:
    """Started engine on the numerical twin of the bench.  ``fps`` is the
    simulated camera rate: everything (wind, delay) is in frames, so a
    faster simulation is just a shorter wait.  ``flux``: photons per 10 ms
    frame (default 6e6, almost noiseless; ~2e4 gives the ~30 nm noise
    floor of the bench at 41 Hz).  It can be changed at any time with
    ``e.sim_model.flux``."""
    from prima.aolab.devices.hw import FACTORY_FLAT, load_flat
    from prima.aolab.devices.sim import make_sim_bench
    flat = load_flat(FACTORY_FLAT)
    cam, dm, mod, model = make_sim_bench(flat=flat, fps=fps)
    e = AOEngine(cam, dm, mod, flat, log=log)
    e.sim_model = model
    if flux is not None:
        model.flux = float(flux)
    e.start()
    if calibrated:
        calibrate(e, n_modes=n_modes, **calib_kw)
    return e


def hw_engine(exposure_ms: float = 20.0, binning: int = 2,
              fmod_hz: float = 50.0, radius_mrad: float = 10.0,
              cam_gain_db: float | None = 6.0, log=print) -> AOEngine:
    """Started engine on the real bench, course configuration (41 Hz).
    Not calibrated: use ``calibrate`` (or load a calibration)."""
    from prima.aolab.devices.hw import make_hw_bench
    cam, dm, mod, flat = make_hw_bench(exposure_ms=exposure_ms,
                                       binning=binning,
                                       radius_mrad=radius_mrad,
                                       freq_hz=fmod_hz)
    if cam_gain_db is not None:
        cam.set_gain(cam_gain_db)
    e = AOEngine(cam, dm, mod, flat, log=log)
    e.mode = 'hw'
    e.start()
    return e


def record(e: AOEngine, n_frames: int, label: str = '',
           n_cam_frames: int = 0, timeout_s: float | None = None
           ) -> PrimaAnalyzer:
    """Record ``n_frames`` loop frames (blocking) and open the result."""
    done = []
    e.start_recording(n_frames, label=label, n_cam_frames=n_cam_frames,
                      done_cb=done.append)
    t0 = time.time()
    if timeout_s is None:
        timeout_s = 30 + 3 * n_frames / max(e.loop_rate_hz(), 5)
    while not done:
        if time.time() - t0 > timeout_s:
            e.stop_recording()
            raise TimeoutError('recording did not finish')
        time.sleep(0.05)
    if done[0] is None:
        raise RuntimeError('recording failed: %s'
                           % e.last_recording.error)
    return PrimaAnalyzer.get(str(done[0]))


def settle(e: AOEngine, n_frames: int = 50):
    """Wait ``n_frames`` loop iterations (e.g. after closing the loop)."""
    for _ in range(int(n_frames)):
        e.wait_measure()


def close(e: AOEngine):
    """Stop the loop, park the DM at the flat and release the devices
    (real DM: HV off).  The modulator keeps modulating, as with the GUI."""
    try:
        e.stop(park=True)
    finally:
        for d in (e.dm, e.mod, e.cam):
            try:
                d.close()
            except Exception:
                pass
