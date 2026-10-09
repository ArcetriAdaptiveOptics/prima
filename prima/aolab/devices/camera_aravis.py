"""Allied Vision Manta G-419 via Aravis (GigE Vision), for the AO loop.

Differences w.r.t. the Drop-1 viewer camera:
  * explicit GigE packet size (default 1500: the laptop NIC has MTU 1500;
    jumbo packets would be silently dropped -> zero frames);
  * sensor ROI + hardware binning, so the loop runs at the camera rate;
  * a frame counter and ``get_frame(wait_new=True)`` so every loop step
    uses a *new* frame (no double-processing of the same image);
  * auto exposure / auto gain forced off.
"""
from __future__ import annotations

import threading
import time

import numpy as np

from prima.aolab.devices.base import Camera

MONO8 = 0x01080001


class AravisCamera(Camera):
    def __init__(self, ip: str = '192.168.30.189', packet_size: int = 1500,
                 pixel_format: str = 'Mono12', n_buffers: int = 8,
                 exposure_ms: float | None = None):
        import gi
        gi.require_version('Aravis', '0.8')
        from gi.repository import Aravis
        self._A = Aravis
        self.ip = ip
        self.name = 'Manta@%s' % ip
        self._packet = int(packet_size)
        self._pf = pixel_format
        self._nbuf = int(n_buffers)
        self._lock = threading.Condition()
        self._frame = None
        self._count = 0
        self._returned = 0
        self._t_frames: list[float] = []
        self._n_err = 0
        self._stop = threading.Event()
        self._thread = None
        self._cam = None
        self._stream = None
        self._open()
        if exposure_ms is not None:
            self.set_exposure_ms(exposure_ms)

    # ------------------------------------------------------------ setup
    def _open(self):
        A = self._A
        last = None
        for attempt in range(5):
            try:
                self._cam = A.Camera.new(self.ip)
                break
            except Exception as exc:     # control held by a dying process
                last = exc
                time.sleep(0.5 * (attempt + 1))
        if self._cam is None:
            raise RuntimeError('cannot open camera %s: %s' % (self.ip, last))
        cam = self._cam
        cam.gv_set_packet_size(self._packet)
        for feat, val in (('ExposureAuto', 'Off'), ('GainAuto', 'Off'),
                          ('TriggerMode', 'Off')):
            try:
                cam.set_string(feat, val)
            except Exception:
                pass
        try:
            cam.set_string('PixelFormat', self._pf)
        except Exception:
            cam.set_string('PixelFormat', 'Mono8')
        cam.set_acquisition_mode(A.AcquisitionMode.CONTINUOUS)

    def _start_stream(self):
        A = self._A
        self._stream = self._cam.create_stream(None, None)
        payload = self._cam.get_payload()
        for _ in range(self._nbuf):
            self._stream.push_buffer(A.Buffer.new_allocate(payload))
        self._cam.start_acquisition()
        self._stop.clear()
        self._thread = threading.Thread(target=self._grab, daemon=True,
                                        name='aravis-grab')
        self._thread.start()

    def _stop_stream(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(2.0)
            self._thread = None
        try:
            self._cam.stop_acquisition()
        except Exception:
            pass
        self._stream = None

    def _grab(self):
        A = self._A
        while not self._stop.is_set():
            st = self._stream
            if st is None:
                break
            buf = st.timeout_pop_buffer(200000)
            if buf is None:
                continue
            try:
                if buf.get_status() == A.BufferStatus.SUCCESS:
                    w, h = buf.get_image_width(), buf.get_image_height()
                    dt = np.uint8 if buf.get_image_pixel_format() == MONO8 \
                        else np.dtype('<u2')
                    arr = np.frombuffer(buf.get_data(), dtype=dt,
                                        count=w * h).reshape(h, w)
                    arr = arr.astype(np.float32)
                    now = time.time()
                    with self._lock:
                        self._frame = arr
                        self._count += 1
                        self._t_frames.append(now)
                        if len(self._t_frames) > 50:
                            self._t_frames = self._t_frames[-50:]
                        self._lock.notify_all()
                else:
                    self._n_err += 1
            finally:
                st.push_buffer(buf)

    # ------------------------------------------------------------- API
    def start(self):
        if self._thread is None:
            self._start_stream()

    def stop(self):
        self._stop_stream()

    def get_frame(self, wait_new=True, timeout_s=2.0):
        with self._lock:
            if wait_new:
                ok = self._lock.wait_for(
                    lambda: self._count > self._returned, timeout_s)
                if not ok:
                    raise TimeoutError('no new frame from %s in %.1fs '
                                       '(errors so far %d)'
                                       % (self.name, timeout_s, self._n_err))
            if self._frame is None:
                raise TimeoutError('no frame yet')
            self._returned = self._count
            return self._count, self._frame

    def _restart_after(self, fn):
        running = self._thread is not None
        if running:
            self._stop_stream()
        try:
            fn()
        finally:
            if running:
                self._start_stream()

    def set_exposure_ms(self, ms):
        self._cam.set_float('ExposureTimeAbs', float(ms) * 1e3)

    def get_exposure_ms(self):
        return float(self._cam.get_float('ExposureTimeAbs')) / 1e3

    def get_fps(self):
        with self._lock:
            t = list(self._t_frames)
        if len(t) < 2:
            return 0.0
        return (len(t) - 1) / max(t[-1] - t[0], 1e-6)

    def max_fps(self):
        try:
            return float(self._cam.get_float('AcquisitionFrameRateLimit'))
        except Exception:
            return 0.0

    def set_roi(self, x0, y0, w, h):
        def f():
            b = self.get_binning()
            # Manta: Width/Height multiples of 2 (8 is always safe)
            ww = max(64, int(w) // 8 * 8)
            hh = max(64, int(h) // 8 * 8)
            self._cam.set_region(int(x0) // 2 * 2, int(y0) // 2 * 2, ww, hh)
        self._restart_after(f)

    def get_roi(self):
        return tuple(int(v) for v in self._cam.get_region())

    def set_binning(self, b):
        def f():
            self._cam.set_region(0, 0, 64, 64)
            self._cam.set_binning(int(b), int(b))
            # full sensor in binned pixels
            wmax = int(self._cam.get_integer('WidthMax'))
            hmax = int(self._cam.get_integer('HeightMax'))
            self._cam.set_region(0, 0, wmax, hmax)
        self._restart_after(f)

    def get_binning(self):
        try:
            return int(self._cam.get_binning()[0])
        except Exception:
            return 1

    def full_well(self):
        return 255.0 if 'Mono8' in self._pf else 4095.0

    @property
    def n_errors(self):
        return self._n_err

    def close(self):
        self._stop_stream()
        self._cam = None
