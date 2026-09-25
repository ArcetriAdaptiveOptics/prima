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


# Demo pupil centers [row, col] matching DemoCamera 4-spot layout (512²)
DEFAULT_DEMO_PUPIL_CENTERS = np.array(
    [[368, 144], [368, 368], [144, 144], [144, 368]], dtype=float)

# Prisma pygo_gui.ui rbtnGain0..6 labels (mrad)
MODULATION_GAIN_PRESETS_MRAD = [0.0, 1.0, 2.0, 4.0, 10.0, 20.0, 40.0]

# Demo pupil radius in pixels (matches DemoCamera ~0.14 * 512)
DEFAULT_DEMO_PUPIL_RADIUS = 72


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

    DEFAULT_EXPOSURE_MS = 1.0
    DEFAULT_MOD_RADIUS_MRAD = 1.5
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
        # apply default timing coupling like Prisma arbitrator
        self.set_exposure_ms(self.DEFAULT_EXPOSURE_MS)
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

    def find_pupils_from_frame(self, frame=None):
        """Quadrant pupil find with adaptive intensity thresholds.

        Per-quadrant Otsu (Prisma ``convertToBinary`` spirit), with percentile
        and robust mean/max fallbacks. Old recipe ``mean+0.5*(max-mean)`` fails
        when ``max`` is saturated (255): threshold ~140 and centroids collapse
        onto bright cores.
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
        # Prisma / demo A–D order (see PyramidPupils._reorderAccordingToGeometry):
        #   A = bottom-left, B = bottom-right, C = top-left, D = top-right
        quads = [
            frame[h // 2:h, 0:w // 2],       # A BL
            frame[h // 2:h, w // 2:w],       # B BR
            frame[0:h // 2, 0:w // 2],       # C TL
            frame[0:h // 2, w // 2:w],       # D TR
        ]
        offsets = [
            (h // 2, 0),
            (h // 2, w // 2),
            (0, 0),
            (0, w // 2),
        ]
        centers = []
        radii = []
        for q, (oy, ox) in zip(quads, offsets):
            cy, cx, r = self._centroid_in_quadrant(q)
            centers.append([cy + oy, cx + ox])
            radii.append(r)
        centers = np.asarray(centers, dtype=float)
        self.set_pyramid_geometry(centers)
        self._pupil_radius = float(np.median(radii))
        return centers, self._pupil_radius

    @staticmethod
    def _quadrant_threshold(q: np.ndarray) -> float:
        """Adaptive bright-pupil threshold for one quadrant."""
        q = np.asarray(q, dtype=np.float64)
        if q.size == 0 or not np.isfinite(q).any():
            return 0.0
        # Prefer Otsu (handles continuum + saturated cores)
        try:
            from skimage.filters import threshold_otsu
            thr = float(threshold_otsu(q))
            # Reject pathological Otsu that takes almost everything / nothing
            frac = float(np.mean(q >= thr))
            if 0.01 <= frac <= 0.35:
                return thr
        except Exception:
            pass
        # Percentile: keep brightest ~10%
        thr_p = float(np.percentile(q, 90))
        frac_p = float(np.mean(q >= thr_p))
        if 0.01 <= frac_p <= 0.35:
            return thr_p
        # Robust mid-of-(mean, p99.5) — avoids single saturated max=255
        hi = float(np.percentile(q, 99.5))
        return float(q.mean() + 0.5 * (hi - q.mean()))

    @classmethod
    def _centroid_in_quadrant(cls, q: np.ndarray):
        q = np.asarray(q, dtype=np.float64)
        thr = cls._quadrant_threshold(q)
        mask = q >= thr
        # Largest connected component (drop continuum flecks)
        try:
            from scipy import ndimage as ndi
            labeled, nlab = ndi.label(mask)
            if nlab > 0:
                sizes = ndi.sum(mask, labeled, index=np.arange(1, nlab + 1))
                best = int(np.argmax(sizes)) + 1
                # Require a minimum area (~0.5% of quadrant or 64 px)
                if sizes[best - 1] >= max(64, 0.005 * q.size):
                    mask = labeled == best
        except Exception:
            pass
        if not np.any(mask):
            yy, xx = np.unravel_index(int(np.argmax(q)), q.shape)
            return float(yy), float(xx), float(min(q.shape) * 0.2)
        ys, xs = np.nonzero(mask)
        # Intensity-weighted centroid (more stable than binary mean)
        wts = q[ys, xs]
        wsum = float(wts.sum()) + 1e-12
        cy = float(np.dot(ys, wts) / wsum)
        cx = float(np.dot(xs, wts) / wsum)
        # Radius from enclosed bright area
        area = float(mask.sum())
        r = float(np.sqrt(area / np.pi))
        r = max(r, 8.0)
        return cy, cx, r

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
