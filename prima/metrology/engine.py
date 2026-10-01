"""In-process PWFS metrology engine (Prisma arbitrator surface, local)."""
from __future__ import annotations

import numpy as np

from prima.metrology.types.camera_frame import CameraFrame
from prima.metrology.types.measure import Measure
from prima.metrology.types.mask import CircularMask
from prima.metrology.types.pyramid_pupils_geometry import PyramidPupilsGeometry
from prima.metrology.types.pyramid_tilt_response import PyramidTiltResponse
from prima.metrology.modal_decomposer import ModalDecomposer
from prima.metrology.arbitrator.measurement_manager import MeasurementManager
from prima.demo.backends import DemoCamera, DemoModulator
from prima.drop1_defaults import (
    DEFAULT_EXPOSURE_MS as _DROP1_EXPOSURE_MS,
    DEFAULT_MOD_RADIUS_MRAD as _DROP1_MOD_RADIUS_MRAD,
    DEFAULT_MOD_FREQ_HZ as _DROP1_MOD_FREQ_HZ,
)


# Demo pupil centers [row, col] matching DemoCamera 4-spot layout (512²)
DEFAULT_DEMO_PUPIL_CENTERS = np.array(
    [[368, 144], [368, 368], [144, 144], [144, 368]], dtype=float)

# Prisma pygo_gui.ui rbtnGain0..6 labels (mrad)
MODULATION_GAIN_PRESETS_MRAD = [0.0, 1.0, 2.0, 4.0, 10.0, 20.0, 40.0]

# Demo pupil radius in pixels (matches DemoCamera ~0.14 * 512)
DEFAULT_DEMO_PUPIL_RADIUS = 72

# Modulation used only while finding pupils (restored afterward).
# User lab tip: 10–20 mrad makes the four spots more even for detection.
PUPIL_FIND_MOD_MRAD_CANDIDATES = (10.0, 20.0)
PUPIL_FIND_SETTLE_S = 0.6

# Dark from pixels outside the four pupils. Lab: "overshoot di 120% del
# diametro" → exclusion disk diameter = 1.2 × pupil diameter → exclusion
# radius = 1.2 × pupil_radius (20% margin beyond the pupil edge).
DARK_OUTSIDE_DIAMETER_OVERSHOOT = 1.2


class CameraClientAdapter:
    """Adapt DemoCamera / LiveCameraWrapper / pysilico to MeasurementManager."""

    def __init__(self, camera):
        self._camera = camera

    def _to_prima_frame(self, raw):
        if isinstance(raw, CameraFrame):
            return raw
        if hasattr(raw, 'toNumpyArray'):
            return CameraFrame(np.asarray(raw.toNumpyArray(), dtype=np.float64))
        return CameraFrame(np.asarray(raw, dtype=np.float64))

    def getFutureFrames(self, n, numberOfFramesToAverageForEachImage=1):
        n = int(n)
        n_avg = max(1, int(numberOfFramesToAverageForEachImage))
        # Prefer native getFutureFrames (live pysilico / LiveCameraWrapper)
        if hasattr(self._camera, 'getFutureFrames'):
            try:
                result = self._camera.getFutureFrames(
                    n, numberOfFramesToAverageForEachImage=n_avg)
                if isinstance(result, (list, tuple)):
                    if not result:
                        raise RuntimeError('empty frame list')
                    if len(result) == 1:
                        return self._to_prima_frame(result[0])
                    stacked = [self._to_prima_frame(f).toNumpyArray()
                               for f in result]
                    return CameraFrame(np.mean(stacked, axis=0))
                return self._to_prima_frame(result)
            except Exception:
                pass
        # Prefer raw 12-bit getFrame / getRawFrame over display-scaled path
        frames = []
        for _ in range(max(n, 1) * n_avg):
            if hasattr(self._camera, 'getFrame'):
                raw = self._camera.getFrame()
            elif hasattr(self._camera, 'getRawFrame'):
                raw = self._camera.getRawFrame()
            else:
                raw = self._camera.getFrameForDisplay()
            if hasattr(raw, 'toNumpyArray'):
                raw = raw.toNumpyArray()
            frames.append(np.asarray(raw, dtype=np.float64))
        avg = np.mean(frames, axis=0) if len(frames) > 1 else frames[0]
        return CameraFrame(avg)

    def getLastFrame(self):
        return self.getFutureFrames(1, 1)

    def getFrameForDisplay(self):
        return self.getLastFrame()

    def getBinning(self):
        if hasattr(self._camera, 'getBinning'):
            return int(self._camera.getBinning())
        return 1

    def exposureTime(self):
        return float(self._camera.exposureTime())

    def setExposureTime(self, ms):
        self._camera.setExposureTime(ms)

    def shape(self):
        return tuple(self._camera.shape())

    def getSnapshot(self, prefix=''):
        return {}

    def setBinning(self, b):
        if hasattr(self._camera, 'setBinning'):
            self._camera.setBinning(b)


class ModulatorClientAdapter:
    def __init__(self, modulator):
        self._m = modulator

    def getRadiusInMilliRad(self):
        return float(self._m.getRadiusInMilliRad())

    def getFrequencyInHz(self):
        return float(self._m.getFrequencyInHz())

    def getCenterInMilliRad(self):
        return np.asarray(self._m.getCenterInMilliRad(), dtype=float)

    def setRadiusInMilliRad(self, r):
        self._m.setRadiusInMilliRad(r)

    def setFrequencyInHz(self, f):
        self._m.setFrequencyInHz(f)

    def setCenterInMilliRad(self, c):
        self._m.setCenterInMilliRad(c)

    def getSnapshot(self, prefix=''):
        from prima.metrology.arbitrator.snapshot_entry import (
            SnapshotEntry, SnapshotPrefix)
        base = SnapshotPrefix.MODULATOR if not prefix else prefix
        return {
            '%s.%s' % (base, SnapshotEntry.MODULATOR_AMPLITUDE):
                self.getRadiusInMilliRad(),
            '%s.%s' % (base, SnapshotEntry.MODULATOR_FREQUENCY):
                self.getFrequencyInHz(),
            '%s.%s' % (base, SnapshotEntry.MODULATOR_CENTER):
                self.getCenterInMilliRad(),
        }


class MetrologyEngine:
    """Prisma-like local arbitrator used by Drop 1 GUI."""

    # Lab work-mode defaults (prima.drop1_defaults / conf/drop1-lab.conf).
    DEFAULT_EXPOSURE_MS = float(_DROP1_EXPOSURE_MS)
    DEFAULT_MOD_RADIUS_MRAD = float(_DROP1_MOD_RADIUS_MRAD)
    DEFAULT_FIBER_UM = 600.0
    PUPIL_SCALE_M_PER_PX = 8.25e-6

    def __init__(self, camera=None, modulator=None, pupil_centers=None,
                 pupil_radius=None):
        self._camera_raw = camera or DemoCamera(512, 512)
        self._modulator_raw = modulator or DemoModulator()
        self._cam = CameraClientAdapter(self._camera_raw)
        self._mod = ModulatorClientAdapter(self._modulator_raw)
        self._mgr = MeasurementManager(self._cam, self._mod)
        self._mgr.setPupilScaleInMeterPerPx(self.PUPIL_SCALE_M_PER_PX)
        centers = (pupil_centers if pupil_centers is not None
                   else DEFAULT_DEMO_PUPIL_CENTERS.copy())
        self._pupil_radius = float(
            pupil_radius if pupil_radius is not None
            else DEFAULT_DEMO_PUPIL_RADIUS)
        self.set_pyramid_geometry(centers)
        self._set_theoretical_tilt_response()
        self._last_measure = None
        self._auto_align = False
        self._align_gain = 0.3
        self._measure_history = []
        self._last_pupil_thresholds = []
        self._last_provisional_dark = 0.0
        self._last_outside_dark = 0.0
        self._last_outside_dark_n = 0
        self._last_pupil_find_mod_mrad = None
        self._last_pupil_find_note = ''
        # Lab work-mode defaults (unlocked exp + independent f_mod).
        # Do NOT call set_exposure_ms here — that forces f=1/t_exp.
        try:
            self._cam.setExposureTime(float(self.DEFAULT_EXPOSURE_MS))
        except Exception:
            pass
        try:
            self._mod.setFrequencyInHz(float(_DROP1_MOD_FREQ_HZ))
        except Exception:
            pass
        self.set_modulation_radius_mrad(self.DEFAULT_MOD_RADIUS_MRAD)

    def rebind(self, camera=None, modulator=None):
        """Swap live/demo backends without rebuilding geometry."""
        if camera is not None:
            self._camera_raw = camera
            self._cam = CameraClientAdapter(camera)
        if modulator is not None:
            self._modulator_raw = modulator
            self._mod = ModulatorClientAdapter(modulator)
        self._mgr = MeasurementManager(self._cam, self._mod)
        self._mgr.setPupilScaleInMeterPerPx(self.PUPIL_SCALE_M_PER_PX)
        self.set_pyramid_geometry(self._pupil_centers)
        self._set_theoretical_tilt_response()
        return self

    @property
    def camera(self):
        return self._camera_raw

    @property
    def modulator(self):
        return self._modulator_raw

    def set_pyramid_geometry(self, pupil_centers):
        geom = PyramidPupilsGeometry(
            np.asarray(pupil_centers, dtype=float), {})
        self._mgr.setPyramidGeometry(geom)
        self._pupil_centers = np.asarray(pupil_centers, dtype=float)

    def pupil_centers(self):
        return self._pupil_centers.copy()

    def pupil_radius(self):
        return float(self._pupil_radius)

    def set_pupil_radius(self, radius_px):
        self._pupil_radius = float(radius_px)

    @staticmethod
    def _pupil_geometry_score(centers: np.ndarray) -> float:
        """Lower is better: rectangle residual normalized by separation."""
        c = np.asarray(centers, dtype=float).reshape(4, 2)
        y_bot = 0.5 * (c[0, 0] + c[1, 0])
        y_top = 0.5 * (c[2, 0] + c[3, 0])
        x_left = 0.5 * (c[0, 1] + c[2, 1])
        x_right = 0.5 * (c[1, 1] + c[3, 1])
        sep = max(abs(y_bot - y_top), abs(x_right - x_left), 1.0)
        target = np.array([
            [y_bot, x_left], [y_bot, x_right],
            [y_top, x_left], [y_top, x_right],
        ], dtype=float)
        return float(np.mean(np.linalg.norm(c - target, axis=1)) / sep)

    def find_pupils(self, frame=None, mod_mrad=None, restore_mod=True,
                    settle_s=None):
        """Find pupils, optionally bumping modulation to 10/20 mrad first.

        Lab practice: higher modulation (10 or 20 mrad) equalizes the four
        PWFS spots for detection. Previous radius is restored afterward
        (default), so measure/align can stay at e.g. 4 mrad.
        """
        import time as _time
        settle = float(PUPIL_FIND_SETTLE_S if settle_s is None else settle_s)
        prev_r = None
        try:
            prev_r = float(self._mod.getRadiusInMilliRad())
        except Exception:
            prev_r = None

        candidates = []
        if mod_mrad is not None:
            candidates = [float(mod_mrad)]
        else:
            candidates = list(PUPIL_FIND_MOD_MRAD_CANDIDATES)

        best = None
        used_mod = None
        try:
            for r_try in candidates:
                if prev_r is not None and abs(r_try - prev_r) > 1e-6:
                    try:
                        self.set_modulation_radius_mrad(r_try)
                        _time.sleep(settle)
                    except Exception as exc:
                        # Demo / refused radius — keep trying without bump
                        self._last_pupil_find_mod_mrad = None
                        self._last_pupil_find_note = (
                            'mod bump to %.1f mrad failed: %s' % (r_try, exc))
                        continue
                centers, radius = self.find_pupils_from_frame(frame=frame)
                score = self._pupil_geometry_score(centers)
                if best is None or score < best[0]:
                    best = (score, centers, radius, r_try)
                # Good enough at 10 mrad — skip 20
                if score < 0.025 and r_try <= 10.5:
                    break
                # If caller forced a single mod, don't loop
                if mod_mrad is not None:
                    break
                # Otherwise try next candidate (20) if 10 was uneven
                frame = None  # re-grab after next mod change
            if best is None:
                centers, radius = self.find_pupils_from_frame(frame=frame)
                used_mod = prev_r
            else:
                score, centers, radius, used_mod = best
                # Re-apply best geometry (may have been overwritten by later try)
                self.set_pyramid_geometry(centers)
                self._pupil_radius = float(radius)
            self._last_pupil_find_mod_mrad = (
                None if used_mod is None else float(used_mod))
            self._last_pupil_find_note = (
                'find @ %.1f mrad (prev %.1f); score=%.4f' % (
                    float(used_mod) if used_mod is not None else -1.0,
                    float(prev_r) if prev_r is not None else -1.0,
                    float(best[0]) if best else -1.0))
            return centers, float(self._pupil_radius)
        finally:
            if restore_mod and prev_r is not None:
                try:
                    self.set_modulation_radius_mrad(prev_r)
                    _time.sleep(min(settle, 0.35))
                except Exception:
                    pass

    def find_pupils_from_frame(self, frame=None):
        """Find A/B/C/D pupils with per-quadrant thresholds + outside-pupil dark.

        Order (Prisma): A=BL, B=BR, C=TL, D=TR.

        Dark: prefer mean of pixels outside the four pupils (exclusion radius
        = 1.2×r). Falls back to corner/percentile provisional dark when
        geometry is unknown. Each quadrant gets its own adaptive threshold on
        the dark-subtracted image. Centroids use a two-pass ROI refine and a
        shared median radius so the four spots stay mutually consistent.

        Prefer ``find_pupils()`` from the GUI so modulation is bumped to
        10/20 mrad for acquisition, then restored.
        """
        if frame is None:
            if hasattr(self._camera_raw, 'getFrame'):
                raw = self._camera_raw.getFrame()
            elif hasattr(self._camera_raw, 'getRawFrame'):
                raw = self._camera_raw.getRawFrame()
            else:
                raw = self._camera_raw.getFrameForDisplay()
            if hasattr(raw, 'toNumpyArray'):
                raw = raw.toNumpyArray()
            frame = np.asarray(raw, dtype=np.float64)
        else:
            frame = np.asarray(frame, dtype=np.float64)
        frame = np.squeeze(frame)
        h, w = frame.shape[:2]

        dark_global = self._dark_for_frame(frame)
        work = np.clip(frame - dark_global, 0.0, None)

        # Pass 1: independent quadrant finds on dark-subtracted frame
        quads = [
            work[h // 2:h, 0:w // 2],       # A BL
            work[h // 2:h, w // 2:w],       # B BR
            work[0:h // 2, 0:w // 2],       # C TL
            work[0:h // 2, w // 2:w],       # D TR
        ]
        offsets = [
            (h // 2, 0),
            (h // 2, w // 2),
            (0, 0),
            (0, w // 2),
        ]
        centers = []
        radii = []
        thr_info = []
        contrasts = []
        for q, (oy, ox) in zip(quads, offsets):
            cy, cx, r, thr = self._centroid_in_quadrant(q, return_thr=True)
            centers.append([cy + oy, cx + ox])
            radii.append(r)
            thr_info.append(thr)
            contrasts.append(float(np.percentile(q, 99) - self._quadrant_local_dark(q)))
        centers = np.asarray(centers, dtype=float)
        radii = np.asarray(radii, dtype=float)
        contrasts = np.asarray(contrasts, dtype=float)

        # If a quadrant collapsed to a small core (dim pupil / thr too high),
        # re-find with a deliberately lower threshold targeting the reference area.
        r_hi = float(np.percentile(radii, 75))
        for i, q in enumerate(quads):
            if radii[i] >= 0.55 * r_hi:
                continue
            oy, ox = offsets[i]
            cy, cx, r2, thr2 = self._centroid_in_quadrant_lowthr(
                q, target_r=r_hi)
            centers[i] = [cy + oy, cx + ox]
            radii[i] = r2
            thr_info[i] = thr2

        # Shared radius: contrast-weighted median (prefer well-lit pupils)
        wts = np.clip(contrasts, 1.0, None)
        order = np.argsort(radii)
        # weighted median
        rw = radii[order]
        ww = wts[order]
        cum = np.cumsum(ww)
        r_common = float(rw[np.searchsorted(cum, 0.5 * cum[-1])])
        r_common = max(r_common, 8.0)

        # Pass 2: refine centroids only (keep r_common)
        refined = []
        for cy, cx in centers:
            cy2, cx2 = self._refine_pupil_center(work, cy, cx, r_common)
            refined.append([cy2, cx2])
        centers = np.asarray(refined, dtype=float)

        # Soft rectangularization
        centers = self._rectangularize_pupils(centers)

        self.set_pyramid_geometry(centers)
        self._pupil_radius = r_common
        self._last_pupil_thresholds = list(thr_info)
        self._last_provisional_dark = float(dark_global)
        # Refine dark with the newly found geometry (outside 1.2×r disks).
        try:
            dark_out, n_out = self.estimate_dark_outside_pupils(
                frame, centers, pupil_radius=r_common,
                diameter_overshoot=DARK_OUTSIDE_DIAMETER_OVERSHOOT,
                return_count=True)
            self._last_outside_dark = float(dark_out)
            self._last_outside_dark_n = int(n_out)
            self._last_provisional_dark = float(dark_out)
            self._apply_scalar_dark_frame(frame.shape, dark_out)
        except Exception:
            pass
        return centers, self._pupil_radius

    def last_outside_dark(self) -> float:
        """Last estimated outside-pupil dark level (ADU)."""
        return float(self._last_outside_dark)

    def _dark_for_frame(self, frame: np.ndarray) -> float:
        """Prefer outside-pupil dark; fall back to provisional corners."""
        centers = getattr(self, '_pupil_centers', None)
        radius = float(getattr(self, '_pupil_radius', 0.0) or 0.0)
        if (centers is not None and np.asarray(centers).shape == (4, 2)
                and radius > 1.0):
            try:
                dark, n = self.estimate_dark_outside_pupils(
                    frame, centers, pupil_radius=radius,
                    diameter_overshoot=DARK_OUTSIDE_DIAMETER_OVERSHOOT,
                    return_count=True)
                if n >= 64:
                    self._last_outside_dark = float(dark)
                    self._last_outside_dark_n = int(n)
                    return float(dark)
            except Exception:
                pass
        dark = self._estimate_provisional_dark(frame)
        self._last_provisional_dark = float(dark)
        return float(dark)

    @staticmethod
    def estimate_dark_outside_pupils(
            frame,
            pupils,
            diameter_overshoot=DARK_OUTSIDE_DIAMETER_OVERSHOOT,
            pupil_radius=None,
            return_count=False):
        """Estimate dark as the mean of pixels outside the four pupils.

        Geometry (lab "overshoot di 120% del diametro"):
          pupil radius ``r``, diameter ``d = 2r``.
          Exclusion disk **diameter** = ``diameter_overshoot × d``
          → exclusion radius ``r_excl = diameter_overshoot × r``.
          Default ``diameter_overshoot=1.2`` ⇒ ``r_excl = 1.2 × r``
          (20% margin beyond the pupil edge). Pixels inside any of the four
          exclusion disks are ignored; the mean of the rest is the dark.

        Parameters
        ----------
        frame : array (H, W)
        pupils : (4, 2) centers [row, col], or object with centers+radius
        diameter_overshoot : float
            Exclusion diameter / pupil diameter (default 1.2).
        pupil_radius : float, optional
            Shared pupil radius in pixels (required if ``pupils`` is an array).
        return_count : bool
            If True, return ``(dark, n_pixels)``.
        """
        f = np.asarray(frame, dtype=np.float64)
        f = np.squeeze(f)
        if f.ndim != 2:
            raise ValueError('frame must be 2-D, got shape %s' % (f.shape,))
        h, w = f.shape

        if pupils is None:
            raise ValueError('pupils (centers) required')
        if hasattr(pupils, 'pupilCenters'):
            centers = np.asarray(pupils.pupilCenters, dtype=float).reshape(4, 2)
        else:
            centers = np.asarray(pupils, dtype=float).reshape(4, 2)
        r = float(pupil_radius) if pupil_radius is not None else None
        if r is None or not np.isfinite(r) or r <= 0:
            raise ValueError('pupil_radius must be a positive float')

        overshoot = float(diameter_overshoot)
        if overshoot <= 0:
            raise ValueError('diameter_overshoot must be > 0')
        # exclusion diameter = overshoot × pupil diameter → r_excl = overshoot × r
        r_excl = overshoot * r
        r2 = r_excl * r_excl

        yy = np.arange(h, dtype=np.float64)[:, None]
        xx = np.arange(w, dtype=np.float64)[None, :]
        outside = np.ones((h, w), dtype=bool)
        for cy, cx in centers:
            outside &= ((yy - float(cy)) ** 2 + (xx - float(cx)) ** 2) >= r2

        vals = f[outside]
        # Drop non-finite; use robust mean (trim extreme high streaks)
        vals = vals[np.isfinite(vals)]
        n = int(vals.size)
        if n < 64:
            dark = MetrologyEngine._estimate_provisional_dark(f)
        else:
            # Trim top 1% (stray light / dust spikes in "outside")
            hi = float(np.percentile(vals, 99))
            lo = float(np.percentile(vals, 1))
            core = vals[(vals >= lo) & (vals <= hi)]
            dark = float(np.mean(core if core.size else vals))
        if return_count:
            return dark, n
        return dark

    def refresh_dark_outside_pupils(self, frame=None,
                                    diameter_overshoot=None):
        """Estimate outside-pupil dark and install it on MeasurementManager."""
        if frame is None:
            if hasattr(self._camera_raw, 'getFrame'):
                raw = self._camera_raw.getFrame()
            elif hasattr(self._camera_raw, 'getRawFrame'):
                raw = self._camera_raw.getRawFrame()
            else:
                raw = self._camera_raw.getFrameForDisplay()
            if hasattr(raw, 'toNumpyArray'):
                raw = raw.toNumpyArray()
            frame = np.asarray(raw, dtype=np.float64)
        frame = np.squeeze(np.asarray(frame, dtype=np.float64))
        overshoot = float(
            DARK_OUTSIDE_DIAMETER_OVERSHOOT
            if diameter_overshoot is None else diameter_overshoot)
        dark, n = self.estimate_dark_outside_pupils(
            frame, self._pupil_centers, pupil_radius=self._pupil_radius,
            diameter_overshoot=overshoot, return_count=True)
        self._last_outside_dark = float(dark)
        self._last_outside_dark_n = int(n)
        self._last_provisional_dark = float(dark)
        self._apply_scalar_dark_frame(frame.shape, dark)
        return float(dark)

    def _apply_scalar_dark_frame(self, shape, dark_adu):
        """Install a constant dark frame for MeasurementManager subtraction."""
        sh = tuple(int(x) for x in shape[:2])
        arr = np.full(sh, float(dark_adu), dtype=np.float64)
        try:
            self._mgr.setDarkFrame(CameraFrame(arr))
        except Exception:
            pass

    @staticmethod
    def _estimate_provisional_dark(frame: np.ndarray) -> float:
        """Background without lamp-off: corners + global low percentile.

        Uses 8% corner patches and the 5th percentile of the full frame;
        returns a robust low estimate suitable for Mono12 continuum.
        Fallback when pupil geometry is unknown / outside mask is empty.
        """
        f = np.asarray(frame, dtype=np.float64)
        h, w = f.shape[:2]
        ph, pw = max(8, h // 12), max(8, w // 12)
        corners = np.concatenate([
            f[:ph, :pw].ravel(),
            f[:ph, -pw:].ravel(),
            f[-ph:, :pw].ravel(),
            f[-ph:, -pw:].ravel(),
        ])
        # Reject any corner that accidentally hosts a pupil streak
        c_med = float(np.median(corners))
        c_mad = float(np.median(np.abs(corners - c_med))) + 1e-6
        corner_ok = corners[corners < c_med + 4.0 * c_mad]
        if corner_ok.size < 16:
            corner_ok = corners
        p5 = float(np.percentile(f, 5))
        corner_p = float(np.percentile(corner_ok, 25))
        return float(min(p5, corner_p, c_med))

    @staticmethod
    def _quadrant_local_dark(q: np.ndarray) -> float:
        """Border-strip background inside one quadrant (provisional)."""
        q = np.asarray(q, dtype=np.float64)
        h, w = q.shape[:2]
        b = max(4, min(h, w) // 16)
        border = np.concatenate([
            q[:b, :].ravel(), q[-b:, :].ravel(),
            q[:, :b].ravel(), q[:, -b:].ravel(),
        ])
        return float(np.percentile(border, 20))

    @staticmethod
    def _quadrant_threshold(q: np.ndarray) -> float:
        """Per-quadrant adaptive threshold on (preferably dark-subtracted) data."""
        q = np.asarray(q, dtype=np.float64)
        if q.size == 0 or not np.isfinite(q).any():
            return 0.0
        local_dark = MetrologyEngine._quadrant_local_dark(q)
        # Work relative to local continuum
        q2 = np.clip(q - local_dark, 0.0, None)
        # Target bright fraction for a ~circular pupil in a quadrant (~3–20%)
        frac_lo, frac_hi = 0.02, 0.28

        try:
            from skimage.filters import threshold_otsu
            thr = float(threshold_otsu(q2)) + local_dark
            frac = float(np.mean(q >= thr))
            if frac_lo <= frac <= frac_hi:
                return thr
        except Exception:
            pass

        # Sweep percentiles for a sensible bright fraction
        for pct in (85, 88, 90, 92, 80, 75):
            thr_p = float(np.percentile(q, pct))
            frac_p = float(np.mean(q >= thr_p))
            if frac_lo <= frac_p <= frac_hi:
                return thr_p

        # Background + k·σ of border (captures full disk, not just core)
        border = q2
        bh, bw = q2.shape
        bb = max(4, min(bh, bw) // 16)
        rim = np.concatenate([
            q2[:bb, :].ravel(), q2[-bb:, :].ravel(),
            q2[:, :bb].ravel(), q2[:, -bb:].ravel(),
        ])
        sig = float(np.std(rim)) + 1e-6
        thr_bg = local_dark + 4.0 * sig
        # Ensure we don't take almost everything
        if float(np.mean(q >= thr_bg)) > frac_hi:
            thr_bg = float(np.percentile(q, 90))
        return float(thr_bg)

    @classmethod
    def _centroid_in_quadrant(cls, q: np.ndarray, return_thr: bool = False):
        q = np.asarray(q, dtype=np.float64)
        thr = cls._quadrant_threshold(q)
        mask = q >= thr
        try:
            from scipy import ndimage as ndi
            # Fill holes / clean flecks so radius tracks the disk, not the core
            mask = ndi.binary_opening(mask, iterations=1)
            mask = ndi.binary_closing(mask, iterations=2)
            labeled, nlab = ndi.label(mask)
            if nlab > 0:
                sizes = ndi.sum(mask, labeled, index=np.arange(1, nlab + 1))
                best = int(np.argmax(sizes)) + 1
                if sizes[best - 1] >= max(64, 0.005 * q.size):
                    mask = labeled == best
                    # Fill interior holes for stable area/radius
                    mask = ndi.binary_fill_holes(mask)
        except Exception:
            pass
        if not np.any(mask):
            yy, xx = np.unravel_index(int(np.argmax(q)), q.shape)
            out = (float(yy), float(xx), float(min(q.shape) * 0.2))
            return out + (thr,) if return_thr else out
        ys, xs = np.nonzero(mask)
        # Binary (unweighted) centroid — intensity weighting collapses onto
        # saturated cores and mis-centers dimmer pupils relative to bright ones.
        cy = float(ys.mean())
        cx = float(xs.mean())
        area = float(mask.sum())
        r = float(np.sqrt(area / np.pi))
        r = max(r, 8.0)
        out = (cy, cx, r)
        return out + (thr,) if return_thr else out

    @classmethod
    def _centroid_in_quadrant_lowthr(cls, q: np.ndarray, target_r: float):
        """Lower-threshold find when the first pass collapsed onto a bright core."""
        q = np.asarray(q, dtype=np.float64)
        local_dark = cls._quadrant_local_dark(q)
        # Aim for area ≈ π target_r²
        target_frac = float(np.pi * target_r ** 2) / float(q.size)
        target_frac = float(np.clip(target_frac, 0.03, 0.30))
        # Choose percentile so bright frac ≈ target
        pct = float(np.clip(100.0 * (1.0 - target_frac), 60.0, 95.0))
        thr = float(np.percentile(q, pct))
        thr = max(thr, local_dark + 2.0)
        mask = q >= thr
        try:
            from scipy import ndimage as ndi
            mask = ndi.binary_opening(mask, iterations=1)
            mask = ndi.binary_closing(mask, iterations=2)
            labeled, nlab = ndi.label(mask)
            if nlab > 0:
                sizes = ndi.sum(mask, labeled, index=np.arange(1, nlab + 1))
                best = int(np.argmax(sizes)) + 1
                mask = ndi.binary_fill_holes(labeled == best)
        except Exception:
            pass
        if not np.any(mask):
            return cls._centroid_in_quadrant(q, return_thr=True)
        ys, xs = np.nonzero(mask)
        cy, cx = float(ys.mean()), float(xs.mean())
        r = float(np.sqrt(float(mask.sum()) / np.pi))
        return cy, cx, max(r, 8.0), thr

    @classmethod
    def _refine_pupil_center(cls, frame, cy, cx, r_guess):
        """Refine centroid inside a disk of radius ``r_guess`` (radius unchanged)."""
        f = np.asarray(frame, dtype=np.float64)
        h, w = f.shape[:2]
        r = max(float(r_guess), 16.0)
        pad = int(round(1.35 * r))
        y0 = max(0, int(round(cy)) - pad)
        y1 = min(h, int(round(cy)) + pad)
        x0 = max(0, int(round(cx)) - pad)
        x1 = min(w, int(round(cx)) + pad)
        roi = f[y0:y1, x0:x1]
        if roi.size < 64:
            return float(cy), float(cx)
        yy, xx = np.mgrid[0:roi.shape[0], 0:roi.shape[1]]
        # Disk centered on pass-1 guess (in ROI coords)
        cy_l, cx_l = float(cy) - y0, float(cx) - x0
        disk = (yy - cy_l) ** 2 + (xx - cx_l) ** 2 <= (1.05 * r) ** 2
        if not np.any(disk):
            return float(cy), float(cx)
        # Soft threshold inside disk: above mid of (p30, p70) of disk pixels
        vals = roi[disk]
        lo, hi = np.percentile(vals, [30, 70])
        thr = 0.5 * (lo + hi)
        mask = disk & (roi >= thr)
        if mask.sum() < 32:
            mask = disk & (roi >= np.percentile(vals, 40))
        if not np.any(mask):
            mask = disk
        # Unweighted centroid of mask
        ys, xs = np.nonzero(mask)
        return float(ys.mean() + y0), float(xs.mean() + x0)

    @classmethod
    def _refine_pupil_roi(cls, frame, cy, cx, r_guess, dark_hint=0.0):
        """Backward-compatible wrapper returning (cy, cx, r)."""
        cy2, cx2 = cls._refine_pupil_center(frame, cy, cx, r_guess)
        return cy2, cx2, float(r_guess)

    @staticmethod
    def _rectangularize_pupils(centers: np.ndarray) -> np.ndarray:
        """Snap A/B/C/D to a rectangle while preserving the figure's center.

        A=BL, B=BR, C=TL, D=TR. Soft average of opposite sides.
        """
        c = np.asarray(centers, dtype=float).reshape(4, 2).copy()
        # rows: A,B bottom; C,D top
        y_bot = 0.5 * (c[0, 0] + c[1, 0])
        y_top = 0.5 * (c[2, 0] + c[3, 0])
        # cols: A,C left; B,D right
        x_left = 0.5 * (c[0, 1] + c[2, 1])
        x_right = 0.5 * (c[1, 1] + c[3, 1])
        # Only snap if the correction is modest (< 12% of separation) —
        # avoid inventing geometry when a pupil is truly missing.
        sep_y = abs(y_bot - y_top) + 1e-6
        sep_x = abs(x_right - x_left) + 1e-6
        max_shift = 0.12 * min(sep_x, sep_y)
        target = np.array([
            [y_bot, x_left],   # A
            [y_bot, x_right],  # B
            [y_top, x_left],   # C
            [y_top, x_right],  # D
        ], dtype=float)
        shift = np.linalg.norm(target - c, axis=1)
        if float(np.max(shift)) <= max_shift * 2.5:
            # Strong snap to rectangle — raw find only seeds the side lengths
            c = 0.9 * target + 0.1 * c
        return c

    def _set_theoretical_tilt_response(self):
        self._mgr.setPyramidTiltResponse(
            PyramidTiltResponse.createTheoreticalFor(
                self._mod.getRadiusInMilliRad(),
                self.DEFAULT_FIBER_UM))

    def set_exposure_ms(self, exposure_ms):
        """Prisma: exposure and f_mod stay locked (t_exp = 1/f)."""
        exposure_ms = float(exposure_ms)
        self._cam.setExposureTime(exposure_ms)
        self._mod.setFrequencyInHz(1000.0 / max(exposure_ms, 1e-6))
        if hasattr(self._camera_raw, 'set_modulation'):
            self._camera_raw.set_modulation(
                self._mod.getFrequencyInHz(),
                self._mod.getRadiusInMilliRad(),
                self._mod.getCenterInMilliRad())

    def get_exposure_ms(self):
        return self._cam.exposureTime()

    def set_modulation_radius_mrad(self, radius_mrad):
        self._mod.setRadiusInMilliRad(float(radius_mrad))
        self._set_theoretical_tilt_response()
        if hasattr(self._camera_raw, 'set_modulation'):
            self._camera_raw.set_modulation(
                self._mod.getFrequencyInHz(),
                self._mod.getRadiusInMilliRad(),
                self._mod.getCenterInMilliRad())

    def set_modulation_frequency_hz(self, freq_hz):
        self._mod.setFrequencyInHz(float(freq_hz))
        # keep Prisma coupling when user sets freq from GUI lock
        if hasattr(self._camera_raw, 'set_modulation'):
            self._camera_raw.set_modulation(
                self._mod.getFrequencyInHz(),
                self._mod.getRadiusInMilliRad(),
                self._mod.getCenterInMilliRad())

    def set_modulation_center_mrad(self, center):
        self._mod.setCenterInMilliRad(center)
        if hasattr(self._camera_raw, 'set_modulation'):
            self._camera_raw.set_modulation(
                self._mod.getFrequencyInHz(),
                self._mod.getRadiusInMilliRad(),
                self._mod.getCenterInMilliRad())

    def take_measurement(self, frames_to_average=3, apply_automatic_mask=True,
                         circular_mask=None, remove_zernikes=None):
        # Refresh outside-pupil dark so slopes use a current continuum estimate.
        try:
            self.refresh_dark_outside_pupils()
        except Exception:
            pass
        meas = self._mgr.takeAMeasurement(
            int(frames_to_average), snapshot={}, storeMeasurement=True)
        meas.setModalDecomposer(ModalDecomposer())
        if apply_automatic_mask:
            try:
                meas.applyAutomaticMask()
            except Exception:
                sh = meas.slopes().mapX().shape
                r = max(8, min(sh) // 2 - 4)
                meas.setCircularMask(CircularMask(sh, maskRadius=r))
        elif circular_mask is not None:
            meas.setCircularMask(circular_mask)
        self._last_measure = meas
        self._measure_history.append(meas)
        if remove_zernikes is None:
            remove_zernikes = [2, 3]
        # touch products so GUI can read them
        _ = meas.slopes()
        _ = meas.pupilImage()
        _ = meas.zernikeCoefficients()
        try:
            _ = meas.wavefront(removeZernikes=remove_zernikes)
        except Exception:
            # fallback: WF from zernikes only
            _ = meas.wavefrontFromZernikes(removeZernikes=remove_zernikes)
        return meas

    def last_measure(self):
        return self._last_measure

    def measure_history(self):
        return list(self._measure_history)

    def measurement_products(self, remove_zernikes=None):
        """Arrays for GUI canvases (Nm for WF / Zernike)."""
        from prima.metrology.constants import Constants
        if self._last_measure is None:
            return None
        if remove_zernikes is None:
            remove_zernikes = [2, 3]
        meas = self._last_measure
        slopes = meas.slopes()
        mask = meas.circularMask().mask()
        norm = meas.slopesNormalizationInRadians()
        sX = np.ma.masked_array(slopes.mapX() / norm, mask=mask)
        sY = np.ma.masked_array(slopes.mapY() / norm, mask=mask)
        slopes_arr = np.ma.hstack([sX, sY])
        try:
            wf = meas.wavefront(removeZernikes=remove_zernikes)
        except Exception:
            wf = meas.wavefrontFromZernikes(removeZernikes=remove_zernikes)
        wf_nm = np.ma.array(
            np.asarray(wf.toNumpyArray()) * Constants.METER_2_NANOMETER)
        pupil = np.asarray(meas.pupilImage(), dtype=np.float64)
        masked_pupil = pupil + mask * 0.5 * (pupil.max() if pupil.size else 0)
        zc = meas.zernikeCoefficients().toNumpyArray()
        zc_nm = zc * Constants.METER_2_NANOMETER
        rms_nm = float(np.ma.std(wf_nm))
        return {
            'slopes': slopes_arr,
            'wavefront_nm': wf_nm,
            'pupil': masked_pupil,
            'zernike_nm': zc_nm,
            'rms_nm': rms_nm,
        }

    def enable_auto_align(self, enabled=True):
        self._auto_align = bool(enabled)

    def is_auto_align_enabled(self):
        return self._auto_align

    def set_auto_align_gain(self, gain):
        self._align_gain = float(gain)

    def auto_align_step(self):
        """Simple tip/tilt null using last measure Zernike (Drop 1 stand-in).

        Full Prisma path uses calibrated zernike→modulator reconstructor;
        until Drop 3 / calib files exist, null tip/tilt by offsetting center.
        """
        if self._last_measure is None:
            self.take_measurement(frames_to_average=1)
        zc = self._last_measure.zernikeCoefficients().toNumpyArray()
        # indices: FIRST_ZERNIKE_MODE handling — tip/tilt typically modes 2,3
        tip = float(zc[1]) if len(zc) > 1 else 0.0
        tilt = float(zc[2]) if len(zc) > 2 else 0.0
        # crude scale tip/tilt meters → mrad offset
        scale = self._align_gain * 1e6
        cur = self._mod.getCenterInMilliRad()
        new = cur - scale * np.array([tip, tilt])
        self.set_modulation_center_mrad(new)
        return new, (tip, tilt)
