"""Live PWFS slopes: opticalib ``Pyramid`` over Prima ``AravisCamera``.

Falls back to Prima ``MetrologyEngine`` slopes if opticalib pupil detect fails.
"""
from __future__ import annotations

import numpy as np

from opticalib.devices._API.base_devices import BaseWavefrontSensor
from opticalib.devices.wfs import Pyramid

from prima.flattening.devices.aravis_camera import AravisCamera
from prima.metrology.engine import MetrologyEngine


class LivePyramid(BaseWavefrontSensor):
    """WFS with ``acquire_map(..., output_type='slopes1d')`` for the pipeline."""

    def __init__(
            self,
            camera: AravisCamera,
            detect_threshold: float = 400.0,
            nframes: int = 2,
            use_metrology_fallback: bool = True,
            modulator=None,
    ):
        self._name = 'LivePyramid'
        self._camera = camera
        self._nframes = max(1, int(nframes))
        self._pyr = Pyramid(camera)
        self._pyr.detect_threshold = float(detect_threshold)
        self._pupils_ready = False
        self._use_metrology = bool(use_metrology_fallback)
        self._eng: MetrologyEngine | None = None
        self._modulator = modulator
        self._mode = 'opticalib'
        self._slope_mask: np.ndarray | None = None
        self._n_slopes: int | None = None
        self._centers: np.ndarray | None = None
        self._radius: float | None = None

    def save_geometry(self, path) -> None:
        """Persist metrology pupils + frozen slope mask for IFF reopen."""
        from pathlib import Path
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        if self._centers is not None:
            np.save(path / 'pupil_centers.npy', self._centers)
        if self._radius is not None:
            np.save(path / 'pupil_radius.npy', np.array([self._radius]))
        if self._slope_mask is not None:
            np.save(path / 'slope_mask.npy', self._slope_mask.astype(np.uint8))
        if self._n_slopes is not None:
            np.save(path / 'n_slopes.npy', np.array([self._n_slopes]))
        (path / 'wfs_mode.txt').write_text(self._mode + '\n')

    def load_geometry(self, path) -> bool:
        """Load frozen geometry from an IFF cube directory."""
        from pathlib import Path
        path = Path(path)
        cpath = path / 'pupil_centers.npy'
        rpath = path / 'pupil_radius.npy'
        if not (cpath.exists() and rpath.exists()):
            return False
        self._centers = np.load(cpath)
        self._radius = float(np.load(rpath).ravel()[0])
        if (path / 'slope_mask.npy').exists():
            self._slope_mask = np.load(path / 'slope_mask.npy').astype(bool)
        if (path / 'n_slopes.npy').exists():
            self._n_slopes = int(np.load(path / 'n_slopes.npy').ravel()[0])
        self._eng = MetrologyEngine(
            camera=self._camera._cam, modulator=self._modulator)
        self._eng.set_pyramid_geometry(self._centers)
        self._eng.set_pupil_radius(self._radius)
        self._pupils_ready = True
        self._mode = 'metrology'
        print('LivePyramid loaded geometry r=%.1f n_slopes=%s' % (
            self._radius, self._n_slopes))
        return True

    def ensure_pupils(self, detect: bool = True) -> str:
        """Detect pupil geometry. Returns mode used (``opticalib`` / ``metrology``)."""
        if self._pupils_ready and self._eng is not None and self._mode == 'metrology':
            return self._mode
        frame = np.asarray(
            self._camera.acquire_frames(self._nframes), dtype=float)
        if detect:
            try:
                self._pyr._detect_pupils(frame)
                n_sub = int(self._pyr.pupil_info.n_subap)
                if n_sub < 8:
                    raise RuntimeError('too few subaps: %d' % n_sub)
                self._pupils_ready = True
                self._mode = 'opticalib'
                print('LivePyramid opticalib n_subap=%d avg_d=%.1f' % (
                    n_sub, self._pyr.pupil_info.avg_d))
                return self._mode
            except Exception as exc:
                print('opticalib pupil detect failed:', exc)

        if not self._use_metrology:
            raise RuntimeError('Pyramid pupils not ready')
        self._eng = MetrologyEngine(
            camera=self._camera._cam, modulator=self._modulator)
        centers, r = self._eng.find_pupils_from_frame(frame)
        self._eng.set_pyramid_geometry(centers)
        self._eng.set_pupil_radius(r)
        self._centers = np.asarray(centers, dtype=float)
        self._radius = float(r)
        self._pupils_ready = True
        self._mode = 'metrology'
        print('LivePyramid MetrologyEngine pupils r=%.1f centers=\n%s' % (
            r, centers))
        return self._mode

    @property
    def mode(self) -> str:
        return self._mode

    def acquire_detector(self, nframes: int = 1):
        return self._camera.acquire_frames(nframes)

    def acquire_map(
            self,
            nframes: int | None = None,
            output_type: str = 'slopes1d',
            detect_pupils: bool = False,
            **_,
    ):
        n = self._nframes if nframes is None else max(1, int(nframes))
        if not self._pupils_ready or detect_pupils:
            self.ensure_pupils(detect=True)

        if self._mode == 'metrology':
            assert self._eng is not None
            # Fast path: slopes only (skip WF/Zernike products used by GUI).
            try:
                self._eng.refresh_dark_outside_pupils()
            except Exception:
                pass
            meas = self._eng._mgr.takeAMeasurement(
                int(n), snapshot={}, storeMeasurement=False)
            try:
                meas.applyAutomaticMask()
            except Exception:
                pass
            slopes = meas.slopes()
            try:
                norm = float(meas.slopesNormalizationInRadians())
            except Exception:
                norm = 1.0
            sX = np.asarray(slopes.mapX(), dtype=float) / max(norm, 1e-30)
            sY = np.asarray(slopes.mapY(), dtype=float) / max(norm, 1e-30)
            try:
                mask = np.asarray(meas.circularMask().mask(), dtype=bool)
            except Exception:
                mask = ~np.isfinite(sX)
            # Freeze mask on first acquire so IFF columns stay aligned.
            if self._slope_mask is None or self._slope_mask.shape != mask.shape:
                self._slope_mask = mask
            m = self._slope_mask
            sX = np.where(m, 0.0, sX)
            sY = np.where(m, 0.0, sY)
            # Fixed-length valid-pixel vector (same indices every frame).
            valid = ~m.ravel()
            vec = np.concatenate([sX.ravel()[valid], sY.ravel()[valid]])
            if self._n_slopes is None:
                self._n_slopes = int(vec.size)
            elif vec.size != self._n_slopes:
                # Pad / trim if geometry drifts (should be rare with frozen mask).
                out = np.zeros(self._n_slopes, dtype=float)
                n = min(self._n_slopes, vec.size)
                out[:n] = vec[:n]
                vec = out
            if output_type in ('slopes2d', 'image', 'pupils'):
                side = int(np.ceil(np.sqrt(max(vec.size, 1))))
                canvas = np.zeros((side, side), dtype=float)
                canvas.ravel()[: vec.size] = vec
                return canvas
            return vec

        ot = output_type
        if ot in ('slopes1d', 'slopes_vector', 'slopes'):
            return np.asarray(
                self._pyr.acquire_map(
                    nframes=n, output_type='slopes', detect_pupils=False),
                dtype=float).ravel()
        return self._pyr.acquire_map(
            nframes=n, output_type=ot, detect_pupils=False)

    def set_exptime(self, exposure_ms):
        self._pyr.set_exptime(exposure_ms)

    def get_exptime(self):
        return self._pyr.get_exptime()
