"""Pyramid WFS processing: pupil finding, valid pixels, slopes.

Conventions
-----------
Pupils are numbered by position on the detector (row, col)::

        2 | 3          (row index increases upwards when shown with
        --+--           origin='lower')
        0 | 1

    Sx = (I0 - I1 + I2 - I3) / <I>        # left - right
    Sy = (I0 + I1 - I2 - I3) / <I>        # bottom - top

``<I>`` is the mean flux per valid pixel summed on the 4 pupils (global
normalisation, robust to scintillation-free lab use).  The sign of the
slopes is irrelevant for closed loop: the interaction matrix absorbs it.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

import numpy as np
from scipy import ndimage


@dataclass
class PupilGeometry:
    centers: np.ndarray          # (4, 2) [row, col] in detector pixels
    radius: float                # common radius (detector pixels)
    frame_shape: tuple = (0, 0)
    notes: str = ''

    def to_dict(self):
        d = asdict(self)
        d['centers'] = np.asarray(self.centers).tolist()
        d['frame_shape'] = list(self.frame_shape)
        return d

    @classmethod
    def from_dict(cls, d):
        return cls(np.asarray(d['centers'], float), float(d['radius']),
                   tuple(d.get('frame_shape', (0, 0))), d.get('notes', ''))


def find_pupils(frame: np.ndarray, threshold: float | None = None,  # fraction
                smooth: float = 2.0) -> PupilGeometry:
    """Find the 4 pyramid pupils on a frame.

    Threshold the (smoothed, background subtracted) image, keep the 4
    largest connected blobs, centre = intensity-weighted centroid,
    radius = sqrt(area / pi).  Works best with a large modulation radius
    (uniformly illuminated pupils)."""
    img = np.asarray(frame, float)
    # wash out the MEMS print-through grid, scale with frame size
    sm = max(smooth, img.shape[0] / 256.0)
    img = ndimage.gaussian_filter(img, sm)
    img = img - np.percentile(img, 10)
    hi = np.percentile(img, 99.5)
    fracs = [threshold] if threshold is not None else [0.3, 0.2, 0.12, 0.07]
    last = ''
    for fr in fracs:
        thr = fr * hi
        mask = ndimage.binary_opening(img > thr, iterations=2)
        mask = ndimage.binary_fill_holes(mask)
        lab, n = ndimage.label(mask)
        if n < 4:
            last = 'found only %d bright regions (need 4)' % n
            continue
        areas = ndimage.sum(mask, lab, index=np.arange(1, n + 1))
        keep = np.argsort(areas)[::-1][:4] + 1
        cents, radii = [], []
        for k in keep:
            m = lab == k
            cents.append(ndimage.center_of_mass(np.where(m, 1.0, 0.0)))
            radii.append(np.sqrt(m.sum() / np.pi))
        cents = np.asarray(cents)
        radii = np.asarray(radii)
        if radii.min() < 0.8 * radii.max():
            last = 'pupil sizes inconsistent: %s' % np.round(radii, 1)
            continue
        break
    else:
        raise RuntimeError(last + ': check light, exposure, modulation')
    # order: bottom-left, bottom-right, top-left, top-right
    order = np.lexsort((cents[:, 1], cents[:, 0]))
    cents = cents[order]
    low, high = cents[:2], cents[2:]
    low = low[np.argsort(low[:, 1])]
    high = high[np.argsort(high[:, 1])]
    cents = np.vstack([low, high])
    return PupilGeometry(cents, float(np.median(radii)), tuple(img.shape),
                         'thr=%.2f*p99.5 radii=%s' % (fr, np.round(radii, 1)))


class PyramidProcessor:
    """Turns a camera frame into slopes on a fixed set of valid pixels.

    ``npix_across``: resampling of each pupil on a square grid with this
    many pixels across the diameter (the DM has ~11 actuators across the
    pupil, ~3 pixels per actuator is plenty).
    """

    def __init__(self, geom: PupilGeometry, npix_across: int = 32,
                 radius_scale: float = 0.95, norm: str = 'global'):
        self.geom = geom
        self.n = int(npix_across)
        self.norm = norm
        n = self.n
        r = geom.radius * radius_scale
        u = (np.arange(n) - (n - 1) / 2.0) / (n / 2.0)       # [-1, 1]
        U, V = np.meshgrid(u, u)                              # V rows
        self.valid2d = (U ** 2 + V ** 2) <= 1.0
        self.n_valid = int(self.valid2d.sum())
        self._step = (2.0 * r) / n
        self._k = max(1, int(round(self._step)))
        pad = int(np.ceil(r + 2 * self._k + 2))
        self._crops, self._coords = [], []
        h, w = geom.frame_shape if geom.frame_shape[0] else (10 ** 6, 10 ** 6)
        for (cy, cx) in geom.centers:
            y0 = int(max(0, np.floor(cy - pad)))
            x0 = int(max(0, np.floor(cx - pad)))
            y1 = int(min(h, np.ceil(cy + pad) + 1))
            x1 = int(min(w, np.ceil(cx + pad) + 1))
            self._crops.append((y0, y1, x0, x1))
            rows = cy + V[self.valid2d] * r - y0
            cols = cx + U[self.valid2d] * r - x0
            self._coords.append(np.vstack([rows, cols]))
        self.ref = np.zeros(2 * self.n_valid)
        # background ring: pixels well outside the 4 pupils
        self._bg_idx = None

    # ---- helpers -----------------------------------------------------
    def _background(self, frame: np.ndarray) -> float:
        if self._bg_idx is None or self._bg_idx[0].size == 0:
            h, w = frame.shape
            yy, xx = np.mgrid[0:h:4, 0:w:4]
            far = np.ones(yy.shape, bool)
            for (cy, cx) in self.geom.centers:
                far &= np.hypot(yy - cy, xx - cx) > 1.3 * self.geom.radius
            self._bg_idx = (yy[far], xx[far])
        if self._bg_idx[0].size == 0:
            return 0.0
        return float(np.median(frame[self._bg_idx]))

    def pupil_intensities(self, frame: np.ndarray) -> np.ndarray:
        """(4, n_valid) intensities on the resampled pupil grids
        (box-averaged over ~one resampled pixel, then bilinear)."""
        f = np.asarray(frame, np.float32)
        bg = self._background(f)
        out = []
        for (y0, y1, x0, x1), c in zip(self._crops, self._coords):
            sub = f[y0:y1, x0:x1] - bg
            if self._k > 1:
                sub = ndimage.uniform_filter(sub, size=self._k)
            out.append(ndimage.map_coordinates(sub, c, order=1,
                                               mode='nearest'))
        return np.stack(out)

    # ---- main API ----------------------------------------------------
    def compute(self, frame: np.ndarray) -> dict:
        I = self.pupil_intensities(frame)
        tot = I.sum(axis=0)
        if self.norm == 'local':
            den = np.where(tot > 1e-6, tot, np.inf)
        else:
            den = max(float(tot.mean()), 1e-6)
        sx = (I[0] - I[1] + I[2] - I[3]) / den
        sy = (I[0] + I[1] - I[2] - I[3]) / den
        s = np.concatenate([sx, sy])
        return {'slopes_raw': s, 'slopes': s - self.ref,
                'flux': float(tot.sum()), 'I': I}

    def set_reference(self, slopes_raw: np.ndarray | None) -> None:
        self.ref = (np.zeros(2 * self.n_valid) if slopes_raw is None
                    else np.asarray(slopes_raw, float).copy())

    def to_maps(self, vec: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """slope vector -> (Sx map, Sy map) with NaN outside the pupil."""
        mx = np.full(self.valid2d.shape, np.nan)
        my = np.full(self.valid2d.shape, np.nan)
        mx[self.valid2d] = vec[:self.n_valid]
        my[self.valid2d] = vec[self.n_valid:]
        return mx, my

    def intensity_map(self, I: np.ndarray) -> np.ndarray:
        m = np.full(self.valid2d.shape, np.nan)
        m[self.valid2d] = I.sum(axis=0)
        return m
