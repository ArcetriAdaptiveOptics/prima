"""Connect to plico camera / modulator servers, with demo fallback."""
from __future__ import annotations

import numpy as np

from prima.demo.backends import DemoCamera, DemoModulator


DEFAULT_CAMERA_HOST = 'localhost'
DEFAULT_CAMERA_PORT = 7130
DEFAULT_MODULATOR_HOST = 'localhost'
DEFAULT_MODULATOR_PORT = 7030


class LiveCameraWrapper:
    """pysilico CameraClient → DemoCamera-shaped surface for GUI + engine."""

    def __init__(self, client, name='LiveCamera'):
        self._c = client
        self._name = name
        self._readout_ms = 8.0

    def name(self):
        return self._name

    def _as_array(self, frame):
        if hasattr(frame, 'toNumpyArray'):
            return np.asarray(frame.toNumpyArray())
        return np.asarray(frame)

    def getFrameForDisplay(self):
        arr = self._as_array(self._c.getFrameForDisplay())
        arr = np.squeeze(arr)
        if arr.dtype != np.uint8:
            a = arr.astype(np.float64)
            a = a - a.min()
            mx = a.max()
            if mx > 0:
                a = a / mx
            arr = (a * 255).astype(np.uint8)
        return arr

    def getFutureFrames(self, n, numberOfFramesToAverageForEachImage=1):
        return self._c.getFutureFrames(
            n, numberOfFramesToAverageForEachImage=numberOfFramesToAverageForEachImage)

    def setExposureTime(self, ms):
        self._c.setExposureTime(float(ms))

    def exposureTime(self):
        return float(self._c.exposureTime())

    def getFrameRate(self):
        try:
            return float(self._c.getFrameRate())
        except Exception:
            return 1000.0 / max(self.framePeriodMs(), 1e-6)

    def framePeriodMs(self):
        try:
            fps = float(self._c.getFrameRate())
            if fps > 0:
                return 1000.0 / fps
        except Exception:
            pass
        return self.exposureTime() + self._readout_ms

    def setBinning(self, b):
        if hasattr(self._c, 'setBinning'):
            self._c.setBinning(int(b))

    def getBinning(self):
        if hasattr(self._c, 'getBinning'):
            return int(self._c.getBinning())
        return 1

    def shape(self):
        sh = self._c.shape()
        return tuple(sh)

    def set_modulation(self, freq_hz, radius_mrad, center_mrad):
        # live camera has no synthetic modulation; no-op
        pass

    def tipTiltSignal(self):
        return 0.0

    def beatAmplitude(self, freq_hz=None, exposure_ms=None):
        f = float(freq_hz if freq_hz is not None else 20.0)
        T = float(exposure_ms if exposure_ms is not None else self.exposureTime()) / 1000.0
        if f <= 0 or T <= 0:
            return 1.0
        x = f * T
        return float(abs(np.sin(np.pi * x) / (np.pi * x)))


def connect_camera(host=DEFAULT_CAMERA_HOST, port=DEFAULT_CAMERA_PORT, timeout_s=2.0):
    import pysilico
    client = pysilico.camera(host, int(port))
    # poke status so connect fails fast if server down
    _ = client.shape()
    return LiveCameraWrapper(client, name='pysilico@%s:%s' % (host, port))


def connect_modulator(host=DEFAULT_MODULATOR_HOST, port=DEFAULT_MODULATOR_PORT):
    import plico_dm
    return plico_dm.modulator(host, int(port))


def try_connect_live(camera_host=DEFAULT_CAMERA_HOST, camera_port=DEFAULT_CAMERA_PORT,
                     modulator_host=DEFAULT_MODULATOR_HOST,
                     modulator_port=DEFAULT_MODULATOR_PORT):
    """Return (camera, modulator, errors). Missing sides stay None."""
    cam, mod, errors = None, None, []
    try:
        cam = connect_camera(camera_host, camera_port)
    except Exception as e:
        errors.append('camera: %s' % e)
    try:
        mod = connect_modulator(modulator_host, modulator_port)
    except Exception as e:
        errors.append('modulator: %s' % e)
    return cam, mod, errors


def demo_pair(rows=512, cols=512):
    return DemoCamera(rows=rows, cols=cols), DemoModulator()
