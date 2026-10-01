"""Pre-IFF modulator autocenter (avoid PWFS pupil saturation).

Mirrors Drop1 GUI Auto Align: find pupils → tip/tilt null on modulation
center for a few seconds. Also offers a flux-balance step that equalizes
A/B/C/D disk intensities when Zernike tip/tilt is a poor proxy.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from prima.metrology.engine import MetrologyEngine


@dataclass
class AutocenterResult:
    center_before: np.ndarray
    center_after: np.ndarray
    n_steps: int
    tip_tilt_last: tuple[float, float]
    fluxes_before: np.ndarray | None = None
    fluxes_after: np.ndarray | None = None
    peak_before: float = float('nan')
    peak_after: float = float('nan')
    notes: str = ''


def pupil_disk_fluxes(frame, centers_yx, radius: float) -> np.ndarray:
    """Mean ADU in each pupil disk (A,B,C,D)."""
    img = np.asarray(frame, dtype=float)
    yy, xx = np.ogrid[: img.shape[0], : img.shape[1]]
    out = []
    r2 = float(radius) ** 2
    for cy, cx in np.asarray(centers_yx, dtype=float).reshape(-1, 2):
        m = (yy - cy) ** 2 + (xx - cx) ** 2 <= r2
        out.append(float(np.mean(img[m])) if np.any(m) else 0.0)
    return np.asarray(out, dtype=float)


def _frame_peak(frame) -> float:
    a = np.asarray(frame, dtype=float)
    finite = a[np.isfinite(a)]
    return float(np.max(finite)) if finite.size else float('nan')


def run_autocenter(
        engine: MetrologyEngine,
        *,
        duration_s: float = 8.0,
        period_s: float = 0.35,
        gain: float | None = None,
        flux_balance: bool = True,
        flux_gain_mrad: float = 0.15,
        max_center_mrad: float = 8.0,
        camera=None,
) -> AutocenterResult:
    """Run GUI-like Auto Align on an already-wired ``MetrologyEngine``.

    Parameters
    ----------
    engine
        Must have live camera + modulator; pupils should already be set.
    duration_s, period_s
        Match Drop1 GUI (~8 s @ 350 ms).
    flux_balance
        After Zernike tip/tilt loop, nudge center from A–D flux imbalance
        (helps when one pupil is saturating).
    """
    if gain is not None:
        engine.set_auto_align_gain(gain)
    engine.enable_auto_align(True)

    def _grab():
        if camera is not None and hasattr(camera, 'acquire_frames'):
            return np.asarray(camera.acquire_frames(1), dtype=float)
        if hasattr(engine, '_camera_raw') and hasattr(engine._camera_raw, 'getFrame'):
            return np.asarray(engine._camera_raw.getFrame(), dtype=float)
        return None

    centers = engine.pupil_centers()
    radius = engine.pupil_radius()
    frame0 = _grab()
    fluxes0 = (pupil_disk_fluxes(frame0, centers, radius)
               if frame0 is not None else None)
    peak0 = _frame_peak(frame0) if frame0 is not None else float('nan')
    c0 = np.asarray(engine._mod.getCenterInMilliRad(), dtype=float).ravel()[:2]

    t_end = time.time() + float(duration_s)
    n = 0
    tip = tilt = 0.0
    while time.time() < t_end:
        engine.take_measurement(
            frames_to_average=1, apply_automatic_mask=True,
            remove_zernikes=[2, 3])
        new, (tip, tilt) = engine.auto_align_step()
        # Clamp center so Auto Align cannot walk away to large offsets
        new = np.asarray(new, dtype=float).ravel()[:2]
        new = np.clip(new, -float(max_center_mrad), float(max_center_mrad))
        engine.set_modulation_center_mrad(new)
        n += 1
        time.sleep(max(0.0, float(period_s)))

    notes = 'zernike tip/tilt null %d steps' % n

    if flux_balance:
        frame1 = _grab()
        if frame1 is not None:
            flux = pupil_disk_fluxes(frame1, centers, radius)
            # A=BL B=BR C=TL D=TR
            mean = float(np.mean(flux)) + 1e-9
            # right−left and bottom−top normalized imbalance
            err_x = ((flux[1] + flux[3]) - (flux[0] + flux[2])) / mean
            err_y = ((flux[0] + flux[1]) - (flux[2] + flux[3])) / mean
            cur = np.asarray(
                engine._mod.getCenterInMilliRad(), dtype=float).ravel()[:2]
            # Sign: move center opposite to excess light (lab-tuned starting point)
            cur = cur - float(flux_gain_mrad) * np.array([err_x, err_y])
            cur = np.clip(cur, -float(max_center_mrad), float(max_center_mrad))
            engine.set_modulation_center_mrad(cur)
            time.sleep(0.4)
            notes += '; flux_balance err=(%.3f,%.3f)' % (err_x, err_y)

    engine.enable_auto_align(False)
    c1 = np.asarray(engine._mod.getCenterInMilliRad(), dtype=float).ravel()[:2]
    frame2 = _grab()
    fluxes1 = (pupil_disk_fluxes(frame2, centers, radius)
               if frame2 is not None else None)
    peak1 = _frame_peak(frame2) if frame2 is not None else float('nan')
    return AutocenterResult(
        center_before=c0, center_after=c1, n_steps=n,
        tip_tilt_last=(float(tip), float(tilt)),
        fluxes_before=fluxes0, fluxes_after=fluxes1,
        peak_before=peak0, peak_after=peak1, notes=notes)


def ensure_engine_for_autocenter(wfs, modulator) -> MetrologyEngine:
    """Return a MetrologyEngine bound to LivePyramid camera + modulator."""
    if getattr(wfs, '_eng', None) is not None:
        eng = wfs._eng
        # ensure modulator is the live one
        if modulator is not None:
            wfs._modulator = modulator
            eng._modulator_raw = modulator
            from prima.metrology.engine import ModulatorClientAdapter
            eng._mod = ModulatorClientAdapter(modulator)
        return eng
    from prima.metrology.engine import MetrologyEngine
    cam = wfs._camera._cam if hasattr(wfs, '_camera') else None
    eng = MetrologyEngine(camera=cam, modulator=modulator)
    if getattr(wfs, '_centers', None) is not None:
        eng.set_pyramid_geometry(wfs._centers)
        eng.set_pupil_radius(wfs._radius)
    wfs._eng = eng
    return eng
