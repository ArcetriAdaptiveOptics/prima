"""In-process demo backends for Drop 1 GUI without live servers/hardware."""
import time
import numpy as np


class DemoCamera:
    """Synthetic pyramid-like WFS frames + exposure / FPS bookkeeping."""

    def __init__(self, rows=256, cols=256, name='DemoPyramidWFS'):
        self._name = name
        self._rows = rows
        self._cols = cols
        self._exposure_ms = 50.0
        self._binning = 1
        self._frame_counter = 0
        self._readout_ms = 8.0  # mock overhead so FPS < 1000/exp
        self._t0 = time.time()
        self._pupils = [
            (0.28, 0.28), (0.72, 0.28),
            (0.28, 0.72), (0.72, 0.72),
        ]
        self._pupil_radius_frac = 0.14
        self._mod_freq_hz = 20.0
        self._mod_radius = 1.5
        self._mod_center = np.zeros(2)

    def name(self):
        return self._name

    def set_modulation(self, freq_hz, radius_mrad, center_mrad):
        self._mod_freq_hz = float(freq_hz)
        self._mod_radius = float(radius_mrad)
        self._mod_center = np.asarray(center_mrad, dtype=float)

    def setExposureTime(self, exposureTimeInMilliSeconds):
        self._exposure_ms = float(exposureTimeInMilliSeconds)

    def exposureTime(self):
        return self._exposure_ms

    def getFrameRate(self):
        period_ms = self._exposure_ms + self._readout_ms
        return 1000.0 / period_ms

    def framePeriodMs(self):
        return self._exposure_ms + self._readout_ms

    def setBinning(self, binning):
        self._binning = int(binning)

    def getBinning(self):
        return self._binning

    def shape(self):
        return (self._rows // self._binning, self._cols // self._binning)

    def getFrameForDisplay(self):
        rows, cols = self.shape()
        yy, xx = np.mgrid[0:rows, 0:cols]
        img = np.zeros((rows, cols), dtype=np.float32)
        t = time.time() - self._t0
        # Beat when exposure != 1/f_mod: residual intensity modulation
        period_s = max(self._exposure_ms, 1e-3) / 1000.0
        want_period = 1.0 / max(self._mod_freq_hz, 1e-6)
        mismatch = abs(period_s - want_period) / want_period
        beat = 0.15 * mismatch * np.sin(2 * np.pi * self._mod_freq_hz * t)
        tip = 0.35 * self._mod_radius * np.sin(
            2 * np.pi * self._mod_freq_hz * t) + self._mod_center[0]
        tilt = 0.35 * self._mod_radius * np.cos(
            2 * np.pi * self._mod_freq_hz * t) + self._mod_center[1]
        for i, (cx_f, cy_f) in enumerate(self._pupils):
            cx = cx_f * cols + tip * 0.8
            cy = cy_f * rows + tilt * 0.8
            r = self._pupil_radius_frac * min(rows, cols)
            rr = (xx - cx) ** 2 + (yy - cy) ** 2
            pupil = np.exp(-rr / (2 * (r / 2.2) ** 2))
            flux = 0.55 + 0.2 * np.sin(0.4 * i + tip) + beat
            img += flux * pupil
        img += 0.02 * np.random.randn(rows, cols).astype(np.float32)
        img = np.clip(img, 0, None)
        if img.max() > 0:
            img = img / img.max()
        self._frame_counter += 1
        return (img * 255).astype(np.uint8)

    def tipTiltSignal(self):
        """Scalar tip/tilt proxy for sync-tool beat measurement."""
        t = time.time() - self._t0
        return float(np.sin(2 * np.pi * self._mod_freq_hz * t))

    def beatAmplitude(self, freq_hz=None, exposure_ms=None):
        """Residual of one modulation period integrated over exposure.

        Zero (min) when t_exp * f_mod is an integer — especially when
        t_exp == 1/f_mod. Separates the exposure constraint from FPS/readout.
        """
        f = float(self._mod_freq_hz if freq_hz is None else freq_hz)
        T = float(self._exposure_ms if exposure_ms is None else exposure_ms) / 1000.0
        if f <= 0 or T <= 0:
            return 1.0
        # |sinc(f T)| — nulls when f*T is integer
        x = f * T
        return float(abs(np.sin(np.pi * x) / (np.pi * x)))


class DemoModulator:
    """In-process stand-in matching Prisma-shaped modulator surface."""

    def __init__(self, name='DemoModulator'):
        self._name = name
        self._radius = 1.5
        self._freq = 20.0
        self._center = np.zeros(2)
        self._command_counter = 0

    def name(self):
        return self._name

    def getRadiusInMilliRad(self):
        return self._radius

    def getFrequencyInHz(self):
        return self._freq

    def getCenterInMilliRad(self):
        return self._center.copy()

    def setRadiusInMilliRad(self, r):
        self._radius = float(r)
        self._command_counter += 1

    def setFrequencyInHz(self, f):
        self._freq = float(f)
        self._command_counter += 1

    def setCenterInMilliRad(self, c):
        self._center = np.asarray(c, dtype=float)
        self._command_counter += 1

    def getStatus(self):
        return {
            'name': self._name,
            'radius_mrad': self._radius,
            'freq_hz': self._freq,
            'center_mrad': self._center.copy(),
            'command_counter': self._command_counter,
        }
