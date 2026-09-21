"""Aravis (GenICam) live camera for Allied Vision GigE when Vimba SDK is absent.

Used as a Drop 1 bring-up path: Manta is reachable on the lab NIC, but
pysilico `model=avt` needs Allied Vision Vimba / VimbaPython (not installed).
Aravis streams the same GigE Vision camera; this wrapper matches DemoCamera /
LiveCameraWrapper so prima-gui can display frames.
"""
from __future__ import annotations

import threading
import time

import numpy as np


DEFAULT_MANTA_IP = '192.168.30.189'


class AravisLiveCamera:
    """Continuous GigE grab via PyGObject Aravis → DemoCamera-shaped API."""

    def __init__(self, ip_address=DEFAULT_MANTA_IP, name=None,
                 packet_size=1500, n_buffers=8):
        import gi
        gi.require_version('Aravis', '0.8')
        from gi.repository import Aravis

        self._Aravis = Aravis
        self._ip = str(ip_address)
        self._name = name or ('Aravis@%s' % self._ip)
        self._mutex = threading.RLock()
        self._last = np.zeros((64, 64), dtype=np.uint8)
        self._binning = 1
        self._readout_ms = 8.0
        self._running = False
        self._thread = None
        self._stop = threading.Event()

        Aravis.update_device_list()
        self._cam = Aravis.Camera.new(self._ip)
        if self._cam is None:
            raise RuntimeError('Aravis could not open camera at %s' % self._ip)
        try:
            self._cam.gv_set_packet_size(int(packet_size))
        except Exception:
            pass
        try:
            self._cam.set_string('AcquisitionMode', 'Continuous')
        except Exception:
            pass
        self._stream = self._cam.create_stream(None, None)
        if self._stream is None:
            raise RuntimeError('Aravis create_stream failed for %s' % self._ip)
        # Match working arv-camera-test: avoid raw packet socket privilege issues
        try:
            self._stream.set_property('packet-socket', False)
        except Exception:
            pass
        payload = self._cam.get_payload()
        for _ in range(int(n_buffers)):
            self._stream.push_buffer(Aravis.Buffer.new_allocate(payload))
        self._start_acquisition()

    def _start_acquisition(self):
        self._cam.start_acquisition()
        self._running = True
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._grab_loop, name='aravis-grab', daemon=True)
        self._thread.start()

    def _grab_loop(self):
        Aravis = self._Aravis
        while not self._stop.is_set():
            buf = self._stream.timeout_pop_buffer(500000)
            if buf is None:
                continue
            try:
                if buf.get_status() == Aravis.BufferStatus.SUCCESS:
                    data = buf.get_data()
                    x, y, w, h = self._cam.get_region()
                    arr = np.frombuffer(data, dtype=np.uint8).reshape(int(h), int(w))
                    with self._mutex:
                        self._last = arr.copy()
            finally:
                self._stream.push_buffer(buf)

    def close(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        try:
            self._cam.stop_acquisition()
        except Exception:
            pass
        self._running = False

    def name(self):
        return self._name

    def getFrameForDisplay(self):
        with self._mutex:
            arr = self._last
        if arr.dtype != np.uint8:
            a = arr.astype(np.float64)
            a = a - a.min()
            mx = a.max()
            if mx > 0:
                a = a / mx
            arr = (a * 255).astype(np.uint8)
        b = self._binning
        if b > 1:
            h, w = arr.shape
            arr = arr[: h - h % b: b, : w - w % b: b]
        return arr

    def getFutureFrames(self, n, numberOfFramesToAverageForEachImage=1):
        frames = []
        for _ in range(int(n)):
            frames.append(self.getFrameForDisplay())
            time.sleep(0.01)
        return frames

    def setExposureTime(self, ms):
        # Manta ExposureTimeAbs is microseconds
        us = float(ms) * 1000.0
        try:
            self._cam.set_float('ExposureTimeAbs', us)
        except Exception:
            try:
                self._cam.set_exposure_time(us)
            except Exception:
                pass

    def exposureTime(self):
        try:
            return float(self._cam.get_float('ExposureTimeAbs')) / 1000.0
        except Exception:
            try:
                return float(self._cam.get_exposure_time()) / 1000.0
            except Exception:
                return 15.0

    def getFrameRate(self):
        try:
            return float(self._cam.get_float('AcquisitionFrameRateAbs'))
        except Exception:
            return 1000.0 / max(self.framePeriodMs(), 1e-6)

    def framePeriodMs(self):
        fps = self.getFrameRate()
        if fps > 0:
            return 1000.0 / fps
        return self.exposureTime() + self._readout_ms

    def setBinning(self, b):
        b = int(b)
        self._binning = max(1, b)
        try:
            self._cam.set_integer('BinningHorizontal', self._binning)
            self._cam.set_integer('BinningVertical', self._binning)
        except Exception:
            pass

    def getBinning(self):
        try:
            return int(self._cam.get_integer('BinningHorizontal'))
        except Exception:
            return self._binning

    def shape(self):
        try:
            x, y, w, h = self._cam.get_region()
            return (int(h) // self._binning, int(w) // self._binning)
        except Exception:
            with self._mutex:
                return self._last.shape

    def set_modulation(self, freq_hz, radius_mrad, center_mrad):
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


def connect_aravis(ip_address=DEFAULT_MANTA_IP):
    return AravisLiveCamera(ip_address=ip_address)
