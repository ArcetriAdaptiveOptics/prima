"""Vimba X / vmbpy live camera for Allied Vision GigE (Manta).

Preferred Drop 1 camera path when Vimba X GenTL is installed. Opens by
IP (discovery on this bench often returns an empty list even though the
camera is reachable). Falls back callers can still use Aravis / pysilico.
"""
from __future__ import annotations

import os
import threading
import time

import numpy as np

DEFAULT_MANTA_IP = '192.168.30.189'
DEFAULT_VIMBAX_CTI = os.path.expanduser(
    '~/git/vendor-sdks/VimbaX_2025-2/cti')


def ensure_vimbax_env(cti_dir: str | None = None) -> str:
    """Put Vimba X CTI / libs on the process environment (idempotent)."""
    cti = os.path.abspath(cti_dir or os.environ.get(
        'PRIMA_VIMBAX_CTI', DEFAULT_VIMBAX_CTI))
    if not os.path.isdir(cti):
        raise RuntimeError('Vimba X CTI directory missing: %s' % cti)
    # Prefer VimbaX GenTL; keep any pre-existing extra paths after ours.
    prev = os.environ.get('GENICAM_GENTL64_PATH', '')
    parts = [p for p in prev.split(':') if p and p != cti]
    os.environ['GENICAM_GENTL64_PATH'] = ':'.join([cti] + parts)
    api_lib = os.path.abspath(os.path.join(cti, '..', 'api', 'lib'))
    bindir = os.path.abspath(os.path.join(cti, '..', 'bin'))
    ld = os.environ.get('LD_LIBRARY_PATH', '')
    ld_parts = [p for p in ld.split(':') if p]
    for p in (api_lib, bindir):
        if p not in ld_parts:
            ld_parts.insert(0, p)
    os.environ['LD_LIBRARY_PATH'] = ':'.join(ld_parts)
    return cti


class VmbpyLiveCamera:
    """Continuous grab via Allied Vision vmbpy → DemoCamera-shaped API."""

    def __init__(self, ip_address=DEFAULT_MANTA_IP, name=None,
                 cti_dir=None, buffer_count=5):
        ensure_vimbax_env(cti_dir)
        import vmbpy

        self._vmbpy = vmbpy
        self._ip = str(ip_address)
        self._name = name or ('vmbpy@%s' % self._ip)
        self._buffer_count = int(buffer_count)
        self._mutex = threading.RLock()
        self._last = np.zeros((64, 64), dtype=np.uint8)
        self._binning = 1
        self._readout_ms = 8.0
        self._running = False
        self._vmb_ctx = None
        self._cam = None
        self._cam_ctx = None

        self._vmb_ctx = vmbpy.VmbSystem.get_instance()
        self._vmb_ctx.__enter__()
        try:
            self._cam = self._vmb_ctx.get_camera_by_id(self._ip)
        except Exception as exc:
            self._vmb_ctx.__exit__(None, None, None)
            self._vmb_ctx = None
            raise RuntimeError(
                'vmbpy could not open camera id/IP %s: %s' % (self._ip, exc)
            ) from exc
        self._cam_ctx = self._cam
        self._cam.__enter__()
        try:
            self._configure()
            self._start_streaming()
        except Exception:
            self.close()
            raise

    def _configure(self):
        vmbpy = self._vmbpy
        cam = self._cam
        try:
            cam.set_pixel_format(vmbpy.PixelFormat.Mono8)
        except Exception:
            pass
        for feat_name, value in (
            ('GVSPPacketSize', 1500),
            ('GevSCPSPacketSize', 1500),
            ('StreamBytesPerSecond', 100000000),
        ):
            try:
                getattr(cam, feat_name).set(value)
            except Exception:
                pass

    def _handler(self, cam, stream, frame):
        try:
            if frame.get_status() == self._vmbpy.FrameStatus.Complete:
                arr = frame.as_numpy_ndarray()
                arr = np.asarray(arr)
                if arr.ndim == 3 and arr.shape[-1] == 1:
                    arr = arr[..., 0]
                with self._mutex:
                    self._last = np.ascontiguousarray(arr)
        finally:
            try:
                cam.queue_frame(frame)
            except Exception:
                pass

    def _start_streaming(self):
        self._cam.start_streaming(self._handler, buffer_count=self._buffer_count)
        self._running = True
        # Wait briefly for first frame
        t0 = time.time()
        while time.time() - t0 < 3.0:
            with self._mutex:
                if self._last.shape != (64, 64) or self._last.max() > 0:
                    break
            time.sleep(0.05)

    def close(self):
        if self._running and self._cam is not None:
            try:
                self._cam.stop_streaming()
            except Exception:
                pass
            self._running = False
        if self._cam is not None:
            try:
                self._cam.__exit__(None, None, None)
            except Exception:
                pass
            self._cam = None
        if self._vmb_ctx is not None:
            try:
                self._vmb_ctx.__exit__(None, None, None)
            except Exception:
                pass
            self._vmb_ctx = None

    def name(self):
        return self._name

    def getFrameForDisplay(self):
        with self._mutex:
            arr = self._last.copy()
        if arr.dtype != np.uint8:
            a = arr.astype(np.float64)
            a = a - a.min()
            mx = a.max()
            if mx > 0:
                a = a / mx
            arr = (a * 255).astype(np.uint8)
        b = self._binning
        if b > 1:
            h, w = arr.shape[:2]
            arr = arr[: h - h % b: b, : w - w % b: b]
        return arr

    def getFutureFrames(self, n, numberOfFramesToAverageForEachImage=1):
        frames = []
        for _ in range(int(n)):
            frames.append(self.getFrameForDisplay())
            time.sleep(0.01)
        return frames

    def setExposureTime(self, ms):
        us = float(ms) * 1000.0
        cam = self._cam
        if cam is None:
            return
        for feat in ('ExposureTimeAbs', 'ExposureTime'):
            try:
                getattr(cam, feat).set(us)
                return
            except Exception:
                continue

    def exposureTime(self):
        cam = self._cam
        if cam is None:
            return 15.0
        for feat in ('ExposureTimeAbs', 'ExposureTime'):
            try:
                return float(getattr(cam, feat).get()) / 1000.0
            except Exception:
                continue
        return 15.0

    def getFrameRate(self):
        cam = self._cam
        if cam is not None:
            for feat in ('AcquisitionFrameRateAbs', 'AcquisitionFrameRate'):
                try:
                    return float(getattr(cam, feat).get())
                except Exception:
                    continue
        return 1000.0 / max(self.framePeriodMs(), 1e-6)

    def framePeriodMs(self):
        fps = self.getFrameRate()
        if fps > 0:
            return 1000.0 / fps
        return self.exposureTime() + self._readout_ms

    def setBinning(self, b):
        self._binning = max(1, int(b))
        cam = self._cam
        if cam is None:
            return
        for feat in ('BinningHorizontal', 'BinningVertical'):
            try:
                getattr(cam, feat).set(self._binning)
            except Exception:
                pass

    def getBinning(self):
        cam = self._cam
        if cam is not None:
            try:
                return int(cam.BinningHorizontal.get())
            except Exception:
                pass
        return self._binning

    def shape(self):
        with self._mutex:
            h, w = self._last.shape[:2]
        return (h // self._binning, w // self._binning)

    def set_modulation(self, freq_hz, radius_mrad, center_mrad):
        pass

    def tipTiltSignal(self):
        return 0.0

    def beatAmplitude(self, freq_hz=None, exposure_ms=None):
        f = float(freq_hz if freq_hz is not None else 20.0)
        T = float(
            exposure_ms if exposure_ms is not None else self.exposureTime()
        ) / 1000.0
        if f <= 0 or T <= 0:
            return 1.0
        x = f * T
        return float(abs(np.sin(np.pi * x) / (np.pi * x)))


def connect_vmbpy(ip_address=DEFAULT_MANTA_IP, cti_dir=None):
    return VmbpyLiveCamera(ip_address=ip_address, cti_dir=cti_dir)
