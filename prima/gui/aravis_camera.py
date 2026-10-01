"""Aravis (GenICam) live camera for Allied Vision GigE Vision.

Drop 1 primary camera path: Manta on the lab NIC via Aravis continuous grab.
Captures **Mono12** (12-bit right-aligned in uint16, ADU 0–4095). Display may
scale for the screen; metrology uses raw 12-bit arrays via ``getFrame``.
"""
from __future__ import annotations

import threading
import time

import numpy as np


from prima.drop1_defaults import (
    DEFAULT_MANTA_IP as _DROP1_MANTA_IP,
    DEFAULT_PIXEL_FORMAT as _DROP1_PIXEL_FORMAT,
    CAMERA_FULL_WIDTH,
    CAMERA_FULL_HEIGHT,
)

DEFAULT_MANTA_IP = _DROP1_MANTA_IP
# Full-well for Mono12 (right-aligned in 16-bit words).
MONO12_FULL_WELL = 4095
PREFERRED_PIXEL_FORMAT = _DROP1_PIXEL_FORMAT


class AravisLiveCamera:
    """Continuous GigE grab via PyGObject Aravis → DemoCamera-shaped API."""

    def __init__(self, ip_address=DEFAULT_MANTA_IP, name=None,
                 packet_size=1500, n_buffers=8,
                 pixel_format=PREFERRED_PIXEL_FORMAT):
        import gi
        gi.require_version('Aravis', '0.8')
        from gi.repository import Aravis

        self._Aravis = Aravis
        self._ip = str(ip_address)
        self._name = name or ('Aravis@%s' % self._ip)
        self._mutex = threading.RLock()
        self._last = np.zeros((64, 64), dtype=np.uint16)
        self._binning = 1
        self._readout_ms = 8.0
        self._running = False
        self._thread = None
        self._stop = threading.Event()
        self._pixel_format = str(pixel_format or PREFERRED_PIXEL_FORMAT)
        self._bit_depth = 12
        self._full_well = MONO12_FULL_WELL
        self._bytes_per_pixel = 2

        Aravis.update_device_list()
        self._cam = None
        self._stream = None
        self._dev = None
        last_err = None
        # Retry: prior GUI / crashed owner may still hold GigE control for ~1–3 s.
        for attempt in range(6):
            try:
                self._cam = Aravis.Camera.new(self._ip)
                if self._cam is None:
                    raise RuntimeError(
                        'Aravis could not open camera at %s' % self._ip)
                self._dev = self._cam.get_device()
                if self._dev is not None and hasattr(self._dev, 'is_controller'):
                    if not self._dev.is_controller():
                        try:
                            self._dev.take_control()
                        except Exception as exc:
                            raise RuntimeError(
                                'Camera control busy (another process?). '
                                'Close other prima-gui / Vision apps and retry. '
                                '(%s)' % exc) from exc
                try:
                    self._cam.gv_set_packet_size(int(packet_size))
                except Exception:
                    pass
                self._configure_pixel_format()
                self._ensure_full_frame()
                try:
                    self._cam.set_string('AcquisitionMode', 'Continuous')
                except Exception:
                    pass
                self._stream = self._cam.create_stream(None, None)
                if self._stream is None:
                    raise RuntimeError(
                        'Aravis create_stream failed for %s' % self._ip)
                break
            except Exception as exc:
                last_err = exc
                self._safe_leave()
                time.sleep(0.4 * (attempt + 1))
        else:
            raise RuntimeError(
                'Aravis open failed for %s after retries: %s'
                % (self._ip, last_err))

        payload = self._cam.get_payload()
        for _ in range(int(n_buffers)):
            self._stream.push_buffer(Aravis.Buffer.new_allocate(payload))
        self._start_acquisition()
        # Wait briefly for first real frame (avoid returning 64x64 zeros).
        t0 = time.time()
        while time.time() - t0 < 3.0:
            with self._mutex:
                if self._last.shape != (64, 64) or int(self._last.max()) > 0:
                    break
            time.sleep(0.05)

    def _configure_pixel_format(self):
        """Force Mono12 when available; fall back to Mono8 only if needed."""
        wanted = self._pixel_format
        for fmt in (wanted, 'Mono12', 'Mono8'):
            try:
                self._cam.set_string('PixelFormat', fmt)
                got = self._cam.get_string('PixelFormat')
                self._pixel_format = got
                break
            except Exception:
                continue
        else:
            try:
                self._pixel_format = self._cam.get_string('PixelFormat')
            except Exception:
                self._pixel_format = 'unknown'

        pf = (self._pixel_format or '').upper()
        if '12' in pf:
            self._bit_depth = 12
            self._full_well = MONO12_FULL_WELL
            self._bytes_per_pixel = 2 if 'PACKED' not in pf else 0  # packed handled later
        elif '8' in pf:
            self._bit_depth = 8
            self._full_well = 255
            self._bytes_per_pixel = 1
        else:
            self._bit_depth = 12
            self._full_well = MONO12_FULL_WELL
            self._bytes_per_pixel = 2
        self._name = 'Aravis@%s [%s]' % (self._ip, self._pixel_format)

    def _ensure_full_frame(self):
        """Force sensor ROI to full frame (default 2048×2048 Mono12)."""
        w_want = int(CAMERA_FULL_WIDTH)
        h_want = int(CAMERA_FULL_HEIGHT)
        # Offset first (some GenICam cams reject Width while offset non-zero).
        for feat, val in (
                ('OffsetX', 0), ('OffsetY', 0),
                ('Width', w_want), ('Height', h_want)):
            try:
                self._cam.set_integer(feat, int(val))
            except Exception:
                try:
                    self._cam.set_float(feat, float(val))
                except Exception:
                    pass
        try:
            x, y, w, h = self._cam.get_region()
            self._name = 'Aravis@%s [%s %dx%d]' % (
                self._ip, self._pixel_format, w, h)
        except Exception:
            pass

    def _decode_buffer(self, data, w, h):
        """Decode GigE buffer → uint16 ADU in [0, full_well]."""
        pf = (self._pixel_format or '').upper()
        n = int(w) * int(h)
        buf = bytes(data) if not isinstance(data, (bytes, bytearray, memoryview)) else data
        if 'PACKED' in pf and '12' in pf:
            # Mono12Packed: 3 bytes → 2 pixels; uncommon path — unpack LE nibble packing
            raw = np.frombuffer(buf, dtype=np.uint8)
            if raw.size < (n * 3 + 1) // 2:
                raise ValueError('Mono12Packed buffer too small')
            # AVT packing: b0=[A7..0], b1=[B3..0|A11..8], b2=[B11..4]
            out = np.empty(n, dtype=np.uint16)
            triplets = raw.size // 3
            usable = min(triplets * 2, n)
            b0 = raw[0:triplets * 3:3].astype(np.uint16)
            b1 = raw[1:triplets * 3:3].astype(np.uint16)
            b2 = raw[2:triplets * 3:3].astype(np.uint16)
            a = b0 | ((b1 & 0x0F) << 8)
            b = (b2 << 4) | ((b1 & 0xF0) >> 4)
            out[0:usable:2] = a[: usable // 2]
            out[1:usable:2] = b[: usable // 2]
            return out.reshape(int(h), int(w))
        if self._bytes_per_pixel >= 2 or len(buf) >= n * 2:
            arr = np.frombuffer(buf, dtype='<u2', count=n).reshape(int(h), int(w))
            # Allied Vision Mono12 via Aravis: right-aligned 0..4095.
            # If left-aligned (values > 4095), shift down.
            if int(arr.max()) > self._full_well:
                arr = (arr >> 4).astype(np.uint16)
            return arr
        # Mono8
        arr8 = np.frombuffer(buf, dtype=np.uint8, count=n).reshape(int(h), int(w))
        return arr8.astype(np.uint16)

    def _safe_leave(self):
        try:
            if self._cam is not None:
                try:
                    self._cam.stop_acquisition()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            if self._dev is not None and hasattr(self._dev, 'leave_control'):
                self._dev.leave_control()
        except Exception:
            pass
        self._stream = None
        self._cam = None
        self._dev = None

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
            if self._stream is None:
                break
            buf = self._stream.timeout_pop_buffer(500000)
            if buf is None:
                continue
            try:
                if buf.get_status() == Aravis.BufferStatus.SUCCESS:
                    data = buf.get_data()
                    x, y, w, h = self._cam.get_region()
                    try:
                        arr = self._decode_buffer(data, w, h)
                    except Exception:
                        continue
                    with self._mutex:
                        self._last = arr
            finally:
                try:
                    self._stream.push_buffer(buf)
                except Exception:
                    pass

    def close(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._safe_leave()
        self._running = False

    def name(self):
        return self._name

    @property
    def bit_depth(self):
        return int(self._bit_depth)

    @property
    def full_well(self):
        return int(self._full_well)

    @property
    def pixel_format(self):
        return str(self._pixel_format)

    def getFrame(self):
        """Raw metrology frame in native ADU (uint16, Mono12 → 0..4095)."""
        with self._mutex:
            arr = np.asarray(self._last)
        b = self._binning
        if b > 1:
            h, w = arr.shape
            arr = arr[: h - h % b: b, : w - w % b: b]
        return arr

    def getRawFrame(self):
        return self.getFrame()

    def getFrameForDisplay(self):
        """Same 12-bit ADU array as metrology (GUI scales with levels 0..4095)."""
        return self.getFrame()

    def getFutureFrames(self, n, numberOfFramesToAverageForEachImage=1):
        frames = []
        n_avg = max(1, int(numberOfFramesToAverageForEachImage))
        for _ in range(int(n) * n_avg):
            frames.append(self.getFrame().astype(np.float64))
            time.sleep(0.01)
        if not frames:
            return self.getFrame()
        if int(n) == 1:
            return np.mean(frames, axis=0)
        # Return list of n averaged frames
        out = []
        for i in range(int(n)):
            chunk = frames[i * n_avg:(i + 1) * n_avg]
            out.append(np.mean(chunk, axis=0))
        return out

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

    def getGain(self):
        try:
            return float(self._cam.get_float('Gain'))
        except Exception:
            try:
                return float(self._cam.get_integer('GainRaw'))
            except Exception:
                return 0.0

    def setGain(self, gain):
        try:
            self._cam.set_float('Gain', float(gain))
        except Exception:
            try:
                self._cam.set_integer('GainRaw', int(round(gain)))
            except Exception:
                pass

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
