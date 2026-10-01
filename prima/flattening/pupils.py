"""PWFS pupil position measurement — Prima and opticalib paths in parallel.

Prima order (lab / MetrologyEngine): A=BL, B=BR, C=TL, D=TR as ``(y, x)``.

Opticalib / ArcetriLAB ``ncoords`` order: BL, BR, TR, TL as ``[x, y]``,
with a square-geometry fit (see ``opticalib.devices._pyramid_pupils``).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class PupilGeometry:
    """Four-pupil geometry in Prima center convention."""

    centers: np.ndarray          # (4, 2) A,B,C,D as (y, x)
    radius: float                # shared radius [px]
    method: str                  # 'prima' | 'opticalib'
    avg_diameter: float = 0.0
    threshold: float | None = None
    ncoords_opticalib: np.ndarray | None = None  # (4, 2) [x,y] BL,BR,TR,TL
    pupil_data: object | None = None             # opticalib PyramidPupilData
    notes: str = ''
    extras: dict = field(default_factory=dict)

    def as_yx(self) -> np.ndarray:
        return np.asarray(self.centers, dtype=float).reshape(4, 2)


def opticalib_ncoords_to_prima_centers(ncoords) -> np.ndarray:
    """Convert ArcetriLAB ncoords [x,y] BL,BR,TR,TL → Prima (y,x) A,B,C,D."""
    c = np.asarray(ncoords, dtype=float).reshape(4, 2)
    # ncoords: 0=BL, 1=BR, 2=TR, 3=TL
    bl, br, tr, tl = c
    # Prima: A=BL, B=BR, C=TL, D=TR  as (y, x)
    return np.array([
        [bl[1], bl[0]],
        [br[1], br[0]],
        [tl[1], tl[0]],
        [tr[1], tr[0]],
    ], dtype=float)


def prima_centers_to_opticalib_ncoords(centers_yx) -> np.ndarray:
    """Inverse of :func:`opticalib_ncoords_to_prima_centers`."""
    a, b, c, d = np.asarray(centers_yx, dtype=float).reshape(4, 2)
    # A=BL, B=BR, C=TL, D=TR → BL,BR,TR,TL as [x,y]
    return np.array([
        [a[1], a[0]],
        [b[1], b[0]],
        [d[1], d[0]],
        [c[1], c[0]],
    ], dtype=float)


def find_pupils_prima(frame, engine=None) -> PupilGeometry:
    """Existing Prima free-centroid path (no rectangular snap)."""
    from prima.metrology.engine import MetrologyEngine
    eng = engine or MetrologyEngine(camera=None, modulator=None)
    centers, r = eng.find_pupils_from_frame(np.asarray(frame, dtype=float))
    centers = np.asarray(centers, dtype=float).reshape(4, 2)
    return PupilGeometry(
        centers=centers,
        radius=float(r),
        method='prima',
        avg_diameter=2.0 * float(r),
        notes='MetrologyEngine.find_pupils_from_frame (free A–D)',
    )


def _refine_radius_around_centers(frame, centers_yx, thr_frac: float = 0.25):
    """Estimate shared radius from illuminated disk around each center."""
    img = np.asarray(frame, dtype=float)
    rs = []
    for cy, cx in np.asarray(centers_yx, dtype=float).reshape(-1, 2):
        if not (np.isfinite(cy) and np.isfinite(cx)):
            continue
        # local peak near center
        y0, x0 = int(round(cy)), int(round(cx))
        h, w = img.shape
        y0 = int(np.clip(y0, 0, h - 1))
        x0 = int(np.clip(x0, 0, w - 1))
        half = min(400, h // 2, w // 2)
        ysl = slice(max(0, y0 - half), min(h, y0 + half + 1))
        xsl = slice(max(0, x0 - half), min(w, x0 + half + 1))
        patch = img[ysl, xsl]
        peak = float(np.nanmax(patch)) if patch.size else 0.0
        if peak <= 0:
            continue
        yy, xx = np.ogrid[ysl.start:ysl.stop, xsl.start:xsl.stop]
        mask = patch >= (thr_frac * peak)
        if not np.any(mask):
            continue
        # equivalent radius of illuminated pixels about center
        area = float(np.count_nonzero(mask))
        rs.append(np.sqrt(area / np.pi))
    if not rs:
        return None
    return float(np.median(rs))


def find_pupils_opticalib(
        frame,
        threshold: float = 400.0,
        require_indpup: bool = False,
        refine_radius: bool = True,
) -> PupilGeometry:
    """Opticalib PWFS pupil detect (``PyramidPupilData.from_img``).

    Uses ArcetriLAB quadrant centroids + square fit. Returns Prima-ordered
    centers for overlay compatibility. ``pupil_data`` is kept for opticalib
    slopes / indpup when intersection succeeds.

    On lab Mono12 frames, ``avg_d`` from quadrant fill can under-estimate
    radius; optional ``refine_radius`` remeasures disk size around ncoords.
    """
    from opticalib.devices._pyramid_pupils import PyramidPupilData

    img = np.asarray(frame, dtype=float)
    thr = float(threshold)
    # Try requested threshold first, then opticalib-style adaptive fallbacks
    # already inside from_img; if that fails, retry with lower seeds.
    last_exc = None
    pdata = None
    for thr_try in (thr, 200.0, 100.0, 50.0):
        try:
            pdata = PyramidPupilData.from_img(img, threshold=thr_try, verbose=False)
            thr = thr_try
            break
        except Exception as exc:
            last_exc = exc
            pdata = None
    if pdata is None:
        raise RuntimeError('opticalib from_img failed: %s' % last_exc)

    centers = opticalib_ncoords_to_prima_centers(pdata.ncoords)
    radius_raw = float(pdata.avg_d) / 2.0
    radius = radius_raw
    note = 'opticalib PyramidPupilData.from_img (ncoords; thr=%.0f)' % thr
    if refine_radius:
        r2 = _refine_radius_around_centers(img, centers)
        if r2 is not None and r2 > 1.0:
            radius = r2
            note += '; radius_refined=%.1f (raw_avg_d/2=%.1f)' % (radius, radius_raw)
        else:
            note += '; radius_raw=%.1f' % radius_raw
    n_sub = None
    indpup_ok = False
    try:
        n_sub = int(pdata.n_subap)
        indpup_ok = n_sub >= 8
        note += '; n_subap=%d' % n_sub
    except Exception as exc:
        note += '; indpup unavailable (%s)' % exc
        if require_indpup:
            raise
    return PupilGeometry(
        centers=centers,
        radius=float(radius),
        method='opticalib',
        avg_diameter=2.0 * float(radius),
        threshold=thr,
        ncoords_opticalib=np.asarray(pdata.ncoords, dtype=float),
        pupil_data=pdata,
        notes=note,
        extras={
            'n_subap': n_sub,
            'indpup_ok': indpup_ok,
            'radius_raw': radius_raw,
            'sizes': np.asarray(pdata.sizes, dtype=float).tolist(),
        },
    )


def find_pupils_both(
        frame,
        opticalib_threshold: float = 400.0,
        engine=None,
) -> dict[str, PupilGeometry]:
    """Run Prima and opticalib detectors; return both (failures omitted)."""
    out: dict[str, PupilGeometry] = {}
    try:
        out['prima'] = find_pupils_prima(frame, engine=engine)
    except Exception as exc:
        out['prima_error'] = PupilGeometry(
            centers=np.full((4, 2), np.nan), radius=0.0, method='prima',
            notes='FAILED: %s' % exc)
    try:
        out['opticalib'] = find_pupils_opticalib(
            frame, threshold=opticalib_threshold)
    except Exception as exc:
        out['opticalib_error'] = PupilGeometry(
            centers=np.full((4, 2), np.nan), radius=0.0, method='opticalib',
            notes='FAILED: %s' % exc)
    return out


def compare_geometries(a: PupilGeometry, b: PupilGeometry) -> dict:
    """Centroid / radius deltas between two geometries (Prima order)."""
    ca, cb = a.as_yx(), b.as_yx()
    d = ca - cb
    return {
        'center_delta_yx': d,
        'center_rms_px': float(np.sqrt(np.mean(d ** 2))),
        'radius_a': a.radius,
        'radius_b': b.radius,
        'radius_delta': float(a.radius - b.radius),
    }
