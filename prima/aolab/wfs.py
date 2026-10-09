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
        try:
            cents, radii, fr = _find_per_quadrant(img)
        except RuntimeError as exc:
            raise RuntimeError(last + '; per-quadrant: %s: check light, '
                               'exposure, modulation' % exc)
    # order: bottom-left, bottom-right, top-left, top-right
    order = np.lexsort((cents[:, 1], cents[:, 0]))
    cents = cents[order]
    low, high = cents[:2], cents[2:]
    low = low[np.argsort(low[:, 1])]
    high = high[np.argsort(high[:, 1])]
    cents = np.vstack([low, high])
    return PupilGeometry(cents, float(np.median(radii)), tuple(img.shape),
                         'thr=%.2f*p99.5 radii=%s' % (fr, np.round(radii, 1)))


def _find_per_quadrant(img: np.ndarray):
    """Fallback for strongly unbalanced pupils: one blob per detector
    quadrant, each thresholded at half of its own maximum."""
    h, w = img.shape
    cents, radii = [], []
    for (y0, x0) in ((0, 0), (0, w // 2), (h // 2, 0), (h // 2, w // 2)):
        q = img[y0:y0 + h // 2, x0:x0 + w // 2]
        bg = np.percentile(q, 20)
        top = np.percentile(q, 99.9)
        if top - bg <= 0:
            raise RuntimeError('empty quadrant')
        m = ndimage.binary_fill_holes(
            ndimage.binary_opening(q > bg + 0.3 * (top - bg), iterations=2))
        lab, n = ndimage.label(m)
        if n == 0:
            raise RuntimeError('no blob in quadrant')
        areas = ndimage.sum(m, lab, index=np.arange(1, n + 1))
        k = int(np.argmax(areas)) + 1
        cy, cx = ndimage.center_of_mass(lab == k)
        cents.append((cy + y0, cx + x0))
        radii.append(np.sqrt(areas[k - 1] / np.pi))
    radii = np.asarray(radii)
    if radii.min() < 0.8 * radii.max():
        raise RuntimeError('sizes %s' % np.round(radii, 1))
    return np.asarray(cents), radii, -1


class PyramidProcessor:
    """Turns a camera frame into slopes on a fixed set of valid pixels.

    ``npix_across``: resampling of each pupil on a square grid with this
    many pixels across the diameter (the DM has ~11 actuators across the
    pupil, ~3 pixels per actuator is plenty).
    """

    def __init__(self, geom: PupilGeometry, npix_across: int = 32,
                 radius_scale: float = 0.95, norm: str = 'global',
                 dark_mode: str = 'follower', dark_frames: int = 20,
                 dark_margin: float = 1.2):
        self.geom = geom
        # --- dark ("dark follower") -------------------------------------
        # The source cannot be switched off during the loop, so the dark
        # level is measured on every frame from the pixels OUTSIDE the
        # four pupils (beyond dark_margin * radius, to skip the halo) and
        # smoothed with an exponential running mean over ~dark_frames.
        #   'follower' : running mean (default)
        #   'frame'    : value of the current frame only
        #   'fixed'    : self.dark_fixed (e.g. a frozen value)
        #   'off'      : no subtraction
        self.dark_mode = dark_mode
        self.dark_frames = int(dark_frames)
        self.dark_margin = float(dark_margin)
        self.dark = None          # followed value (ADU)
        self.dark_inst = None     # value measured on the last frame
        self.dark_fixed = 0.0
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
        self._bg_shape = None

    # ---- helpers -----------------------------------------------------
    def _dark_pixels(self, shape):
        """Indices of background pixels (outside all pupils), subsampled
        to <= ~40k pixels."""
        h, w = shape
        step = max(1, int(np.sqrt(h * w / 40000.0)))
        yy, xx = np.mgrid[0:h:step, 0:w:step]
        far = np.ones(yy.shape, bool)
        for (cy, cx) in self.geom.centers:
            far &= np.hypot(yy - cy, xx - cx) > self.dark_margin * self.geom.radius
        return yy[far], xx[far]

    def _background(self, frame: np.ndarray) -> float:
        if self.dark_mode == 'off':
            self.dark_inst = None
            return 0.0
        if self._bg_idx is None or self._bg_shape != frame.shape:
            self._bg_idx = self._dark_pixels(frame.shape)
            self._bg_shape = frame.shape
        if self._bg_idx[0].size < 50:
            return float(self.dark or 0.0)
        v = frame[self._bg_idx]
        # trimmed mean: drop the brightest 5 % (stray light, hot pixels)
        hi = np.percentile(v, 95)
        inst = float(v[v <= hi].mean())
        self.dark_inst = inst
        if self.dark_mode == 'fixed':
            return float(self.dark_fixed)
        if self.dark_mode == 'frame' or self.dark is None:
            self.dark = inst
        else:
            a = 1.0 / max(1, self.dark_frames)
            self.dark = (1 - a) * self.dark + a * inst
        return float(self.dark)

    def background_mask(self, shape) -> np.ndarray:
        """Boolean image of the pixels used for the dark (for display)."""
        m = np.zeros(shape, bool)
        yy, xx = self._dark_pixels(shape)
        m[yy, xx] = True
        return m

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
                'dark': self.dark, 'dark_inst': self.dark_inst,
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
