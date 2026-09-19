#!/usr/bin/env python3
"""
Hamamatsu ORCA (DCAM-API) -> DAO shared memory streamer
DIT, readout speed, FPS, cooling setpoint control via SHM
Sensor temperature published to a SHM ~1 Hz
ROI via CLI or SHM (SHM overrides CLI)

Scientific sCMOS ORCA models have no analog gain; "Readout speed"
(DCAM READOUTSPEED, e.g. 1 = ultra quiet / low noise, 2 = standard) is
the equivalent noise/rate knob and is what this streamer exposes.

Control only, no GUI. Modeled on ids/daoUeyeCtrl.py; the camera is driven
through the minimal ctypes DCAM-API binding in dcam_mini.py.

ROI precedence:
  1) --shm-roi (x,y,w,h)
  2) --roi-x/y/w/h
  3) Full sensor
"""

import sys
import time
import signal
import threading
import argparse
import contextlib

import numpy as np

try:
    from dcam_mini import (
        DCAMCamera,
        DCAMError,
        DCAM_PIXELTYPE_MONO8,
        DCAM_PIXELTYPE_MONO16,
        DCAM_IDPROP_IMAGE_WIDTH,
        DCAM_IDPROP_IMAGE_HEIGHT,
        DCAM_IDPROP_IMAGE_PIXELTYPE,
        DCAM_IDPROP_SUBARRAYHPOS,
        DCAM_IDPROP_SUBARRAYHSIZE,
        DCAM_IDPROP_SUBARRAYVPOS,
        DCAM_IDPROP_SUBARRAYVSIZE,
        DCAM_IDPROP_SUBARRAYMODE,
        DCAM_IDPROP_READOUTSPEED,
    )
except ImportError:
    print(
        "Error: dcam_mini module not found. It must sit next to this script "
        "(or on PYTHONPATH) and needs the Hamamatsu DCAM-API Lite runtime "
        "(libdcamapi.so) installed.",
        file=sys.stderr,
    )
    raise
import dao


# DCAM property IDs not carried by dcam_mini.py (from dcamprop.h).
DCAM_IDPROP_INTERNALFRAMERATE = 0x00403810
DCAM_IDPROP_SENSORTEMPERATURE = 0x00200110         # read-only, degrees C
DCAM_IDPROP_SENSORTEMPERATURETARGET = 0x00200120   # cooling setpoint (model dependent)

# dcamprop.h DCAMPROP_MODE
DCAMPROP_MODE_OFF = 1
DCAMPROP_MODE_ON = 2

# ORCA subarray positions/sizes must be multiples of 4.
SUBARRAY_STEP = 4


@contextlib.contextmanager
def _blocked_signals(*signums):
    """Defer the given signals for the duration of the block.

    The DCAM teardown takes a couple of seconds; a second Ctrl-C, a SIGTERM or
    a SIGHUP (tmux kill-session/kill-server) landing in the middle of
    dcamapi_uninit() leaves the USB device wedged. Blocking them here holds them
    pending until the camera is fully closed, then lets them through.
    """
    try:
        old = signal.pthread_sigmask(signal.SIG_BLOCK, set(signums))
    except (AttributeError, ValueError, OSError):
        old = None
    try:
        yield
    finally:
        if old is not None:
            signal.pthread_sigmask(signal.SIG_SETMASK, old)


def _align(value, step=SUBARRAY_STEP, floor=True):
    value = int(value)
    if floor:
        return value - (value % step)
    return value + ((step - value % step) % step)


class OrcaShmApp:
    def __init__(
        self,
        shm_image_name,
        shm_dit_name,
        shm_readoutspeed_name,
        shm_fps_name,
        shm_roi_name=None,
        shm_temp_name=None,
        shm_settemp_name=None,
        cam_index=0,
        lib_path=None,
        nbuf=10,
        roi_x=0,
        roi_y=0,
        roi_w=None,
        roi_h=None,
        init_dit_ms=35.0,
        init_readout_speed=None,
        init_set_temp=None,
        init_fps=20.0,
    ):
        # Names
        self.shm_image_name = shm_image_name
        self.shm_dit_name = shm_dit_name
        self.shm_readoutspeed_name = shm_readoutspeed_name
        self.shm_fps_name = shm_fps_name
        self.shm_roi_name = shm_roi_name
        self.shm_temp_name = shm_temp_name
        self.shm_settemp_name = shm_settemp_name

        # CLI ROI
        self.roi_x = roi_x
        self.roi_y = roi_y
        self.roi_w = roi_w
        self.roi_h = roi_h

        # Init values for the control SHMs
        self.init_dit_ms = init_dit_ms
        self.init_readout_speed = init_readout_speed
        self.init_set_temp = init_set_temp
        self.init_fps = init_fps

        # Camera
        self.cam_index = cam_index
        self.lib_path = lib_path
        self.nbuf = nbuf
        self.cam = None

        self.sensor_w = None  # Python int, full sensor
        self.sensor_h = None
        self.width = None     # Python int, current AOI
        self.height = None
        self.dtype = np.uint16

        self._rs_supported = True
        self.rs_range = None  # (min, max) once known
        self._settemp_supported = True
        self.settemp_range = None

        # SHM objects
        self.shm_image = None
        self.shm_dit = None
        self.shm_readoutspeed = None
        self.shm_fps = None
        self.shm_roi = None
        self.shm_temp = None
        self.shm_settemp = None
        self._temp_supported = True

        # Threads
        self.stop_event = threading.Event()
        self.control_thread = None
        # Serialises every call into the DCAM handle (acquisition thread,
        # control thread, and the final close()). RLock: _apply_readout_speed /
        # reconfigure_roi are called with it already held.
        self._cam_lock = threading.RLock()
        self._stopped = False

    # ------------------------------------------------------------------
    # AOI helper (DCAM subarray)
    # ------------------------------------------------------------------
    def apply_roi(self, x, y, w, h):
        x = _align(x)
        y = _align(y)
        w = _align(w)
        h = _align(h)
        w = max(w, SUBARRAY_STEP)
        h = max(h, SUBARRAY_STEP)

        full = (x == 0 and y == 0 and w == self.sensor_w and h == self.sensor_h)

        # SUBARRAYMODE must be OFF while the pos/size are changed.
        self.cam.set_property(DCAM_IDPROP_SUBARRAYMODE, DCAMPROP_MODE_OFF)
        if not full:
            self.cam.set_property(DCAM_IDPROP_SUBARRAYHPOS, x)
            self.cam.set_property(DCAM_IDPROP_SUBARRAYHSIZE, w)
            self.cam.set_property(DCAM_IDPROP_SUBARRAYVPOS, y)
            self.cam.set_property(DCAM_IDPROP_SUBARRAYVSIZE, h)
            self.cam.set_property(DCAM_IDPROP_SUBARRAYMODE, DCAMPROP_MODE_ON)

        self.width = int(self.cam.get_property(DCAM_IDPROP_IMAGE_WIDTH))
        self.height = int(self.cam.get_property(DCAM_IDPROP_IMAGE_HEIGHT))

        pixeltype = int(self.cam.get_property(DCAM_IDPROP_IMAGE_PIXELTYPE))
        self.dtype = np.uint8 if pixeltype == DCAM_PIXELTYPE_MONO8 else np.uint16

        print(f"[AOI] x={x} y={y} w={self.width} h={self.height} dtype={np.dtype(self.dtype).name}")

    # ------------------------------------------------------------------
    # Decide ROI before we create shm_image
    # ------------------------------------------------------------------
    def determine_initial_roi(self):
        """
        ROI precedence:
          1) shm_roi (x,y,w,h)
          2) CLI params
          3) full sensor
        """
        if self.shm_roi is not None:
            roi = self.shm_roi.get_data().astype(int).ravel()
            if roi.size != 4:
                raise RuntimeError("ROI SHM must be shape (1,4): x,y,w,h")
            x, y, w, h = roi
            if w > 0 and h > 0:
                print(f"ROI from SHM: x={x} y={y} w={w} h={h}")
                return int(x), int(y), int(w), int(h)

        x = int(self.roi_x)
        y = int(self.roi_y)

        if self.roi_w is None or self.roi_h is None:
            w = int(self.sensor_w)
            h = int(self.sensor_h)
            print("ROI from CLI: full sensor")
        else:
            w = int(self.roi_w)
            h = int(self.roi_h)
            print(f"ROI from CLI: x={x} y={y} w={w} h={h}")

        return x, y, w, h

    # ------------------------------------------------------------------
    # Camera init (opens camera, applies ROI, starts capture)
    # ------------------------------------------------------------------
    def init_camera(self):
        print("START\n")

        self.cam = DCAMCamera(index=self.cam_index, lib_path=self.lib_path)
        self.cam.open()

        # Full-sensor size = subarray OFF image size
        self.cam.set_property(DCAM_IDPROP_SUBARRAYMODE, DCAMPROP_MODE_OFF)
        self.sensor_w = int(self.cam.get_property(DCAM_IDPROP_IMAGE_WIDTH))
        self.sensor_h = int(self.cam.get_property(DCAM_IDPROP_IMAGE_HEIGHT))

        # Apply initial exposure from the SHM seed value
        self._apply_dit(self.shm_dit.get_data()[0, 0])

        # Readout speed (the sCMOS noise/rate knob; no analog gain on ORCA)
        try:
            lo, hi, _ = self.cam.get_property_range(DCAM_IDPROP_READOUTSPEED)
            self.rs_range = (int(lo), int(hi))
            if self.init_readout_speed is not None:
                self._apply_readout_speed(self.init_readout_speed)
            cur = self.cam.get_readout_speed()
            self.shm_readoutspeed.set_data(np.array([[cur]], dtype=np.float32))
            print(f"Readout speed: current={cur:.0f}, range [{lo:.0f}..{hi:.0f}]")
        except DCAMError:
            self._rs_supported = False
            print("Readout speed: not supported by this camera model (SHM ignored)")

        # Cooling setpoint (fixed on most sCMOS ORCA models)
        try:
            lo, hi, _ = self.cam.get_property_range(DCAM_IDPROP_SENSORTEMPERATURETARGET)
            self.settemp_range = (lo, hi)
            if lo == hi:
                self._settemp_supported = False
                print(f"Cooling setpoint: fixed at {lo:.1f} C on this model (SHM ignored)")
            else:
                if self.init_set_temp is not None:
                    self._apply_set_temp(self.init_set_temp)
                cur = self.cam.get_property(DCAM_IDPROP_SENSORTEMPERATURETARGET)
                self.shm_settemp.set_data(np.array([[cur]], dtype=np.float32))
                print(f"Cooling setpoint: current={cur:.1f} C, range [{lo:.1f}..{hi:.1f}]")
        except DCAMError:
            self._settemp_supported = False
            print("Cooling setpoint: not adjustable on this camera model (SHM ignored)")

        # Decide ROI now that we know the sensor size
        x, y, w, h = self.determine_initial_roi()
        self.apply_roi(x, y, w, h)

        self.cam.start(nbuf=self.nbuf)

        try:
            temp = self.cam.get_property(DCAM_IDPROP_SENSORTEMPERATURE)
            print(f"Sensor temperature: {temp:.1f} C")
        except DCAMError:
            pass
        print(f"Camera index {self.cam_index} streaming, {self.nbuf} ring buffers")
        print("Press Ctrl+C to stop")

    # ------------------------------------------------------------------
    # Property helpers
    # ------------------------------------------------------------------
    def _apply_dit(self, dit_ms):
        self.cam.set_exposure(max(float(dit_ms), 1e-3) / 1000.0)

    def _apply_readout_speed(self, value):
        if not self._rs_supported:
            return
        value = int(round(float(value)))
        if self.rs_range is not None:
            value = max(self.rs_range[0], min(self.rs_range[1], value))
        # READOUTSPEED cannot be changed mid-capture on most models.
        streaming = bool(getattr(self.cam, "_streaming", False))
        try:
            if streaming:
                self.cam.stop()
            self.cam.set_readout_speed(value)
        except DCAMError as e:
            print(f"\n[CTRL] readout speed {value} rejected ({e})", file=sys.stderr)
        finally:
            if streaming and not self.cam._streaming:
                self.cam.start(nbuf=self.nbuf)

    def _apply_set_temp(self, celsius):
        if not self._settemp_supported:
            return
        value = float(celsius)
        if self.settemp_range is not None:
            lo, hi = self.settemp_range
            value = max(lo, min(hi, value))
        try:
            self.cam.set_property(DCAM_IDPROP_SENSORTEMPERATURETARGET, value)
        except DCAMError as e:
            print(f"\n[CTRL] cooling setpoint {value:.1f} C rejected ({e})", file=sys.stderr)

    # ------------------------------------------------------------------
    # SHM init
    # Controls exist before the image size is known; the IMAGE shm is
    # created only after the AOI has been applied.
    # ------------------------------------------------------------------
    def init_shm_pre(self):
        self.shm_dit = dao.shm(
            self.shm_dit_name,
            np.ones((1, 1), dtype=np.float32) * float(self.init_dit_ms),
        )

        self.shm_readoutspeed = dao.shm(
            self.shm_readoutspeed_name,
            np.ones((1, 1), dtype=np.float32) * float(self.init_readout_speed or 0),
        )

        self.shm_fps = dao.shm(
            self.shm_fps_name,
            np.ones((1, 1), dtype=np.float32) * float(self.init_fps),
        )

        if self.shm_roi_name:
            self.shm_roi = dao.shm(
                self.shm_roi_name,
                np.array([[0, 0, 0, 0]], dtype=np.int32),
            )

        if self.shm_temp_name:
            self.shm_temp = dao.shm(
                self.shm_temp_name,
                np.zeros((1, 1), dtype=np.float32),
            )

        if self.shm_settemp_name:
            self.shm_settemp = dao.shm(
                self.shm_settemp_name,
                np.ones((1, 1), dtype=np.float32) * float(
                    self.init_set_temp if self.init_set_temp is not None else 0.0),
            )

    def init_shm_image(self):
        if self.width is None or self.height is None:
            raise RuntimeError("init_shm_image called before AOI width/height known")

        self.shm_image = dao.shm(
            self.shm_image_name,
            np.zeros((self.height, self.width), dtype=self.dtype),
        )

    # ------------------------------------------------------------------
    # Control loop
    # ------------------------------------------------------------------
    def control_loop(self):
        last_dit = self.shm_dit.get_counter()
        last_rs = self.shm_readoutspeed.get_counter()
        last_st = self.shm_settemp.get_counter() if self.shm_settemp else None
        last_roi = self.shm_roi.get_counter() if self.shm_roi else None
        last_temp = 0.0

        while not self.stop_event.is_set():
            # Hold the camera lock only around the DCAM calls, never across the
            # sleep, so the acquisition thread and stop() are not starved.
            with self._cam_lock:
                if self.stop_event.is_set() or self.cam is None:
                    break

                # Publish sensor temperature ~1 Hz
                if self.shm_temp is not None and self._temp_supported:
                    now = time.time()
                    if now - last_temp > 1.0:
                        last_temp = now
                        try:
                            t = self.cam.get_property(DCAM_IDPROP_SENSORTEMPERATURE)
                            self.shm_temp.set_data(np.array([[t]], dtype=np.float32))
                        except DCAMError:
                            self._temp_supported = False

                if self.shm_dit.get_counter() != last_dit:
                    last_dit = self.shm_dit.get_counter()
                    self._apply_dit(self.shm_dit.get_data()[0, 0])

                if self.shm_readoutspeed.get_counter() != last_rs:
                    last_rs = self.shm_readoutspeed.get_counter()
                    self._apply_readout_speed(self.shm_readoutspeed.get_data()[0, 0])
                    # reflect what the camera actually accepted
                    if self._rs_supported:
                        try:
                            self.shm_readoutspeed.set_data(
                                np.array([[self.cam.get_readout_speed()]], dtype=np.float32))
                            last_rs = self.shm_readoutspeed.get_counter()
                        except DCAMError:
                            pass

                if (self.shm_settemp is not None and self._settemp_supported
                        and self.shm_settemp.get_counter() != last_st):
                    last_st = self.shm_settemp.get_counter()
                    self._apply_set_temp(self.shm_settemp.get_data()[0, 0])

                # Live ROI update via shm
                if self.shm_roi and self.shm_roi.get_counter() != last_roi:
                    last_roi = self.shm_roi.get_counter()
                    x, y, w, h = self.shm_roi.get_data().astype(int).ravel()
                    print("\n[CTRL] ROI update")
                    self.reconfigure_roi(int(x), int(y), int(w), int(h))

            time.sleep(0.01)

    # ------------------------------------------------------------------
    # ROI reconfiguration
    # ------------------------------------------------------------------
    def reconfigure_roi(self, x, y, w, h):
        if w <= 0 or h <= 0:
            x, y, w, h = 0, 0, self.sensor_w, self.sensor_h

        self.cam.stop()
        self.apply_roi(x, y, w, h)
        self.cam.start(nbuf=self.nbuf)

        # Recreate image shm with the NEW shape
        self.init_shm_image()

    # ------------------------------------------------------------------
    # Acquisition loop
    # ------------------------------------------------------------------
    def run_acquisition(self):
        frames = 0
        # Rolling-window rate: frames since the last printed measurement,
        # refreshed ~2x/s, so the number tracks the *current* rate instead
        # of a cumulative average since startup.
        win_t0 = time.time()
        win_frames = 0
        rate = 0.0

        while not self.stop_event.is_set():
            fps = float(self.shm_fps.get_data()[0, 0])
            tloop = time.time()

            try:
                with self._cam_lock:
                    if self.stop_event.is_set() or self.cam is None:
                        break
                    arr = self.cam.get_frame(timeout_ms=2000)
            except DCAMError as e:
                # stop() calls cam.abort_wait(), which makes the in-flight
                # get_frame return with an error - that is expected, not a fault.
                if not self.stop_event.is_set():
                    sys.stdout.write(f"\n[ACQ] frame grab failed: {e}\n")
                continue

            if arr.shape != (self.height, self.width):
                # AOI changed under us between lockframe and reshape; skip.
                continue

            self.shm_image.set_data(arr)

            frames += 1
            win_frames += 1
            dt = tloop - win_t0
            if dt >= 0.5:
                rate = win_frames / dt
                win_t0 = tloop
                win_frames = 0
            sys.stdout.write(f"\rFrame {frames} @ {rate:6.2f} fps")
            sys.stdout.flush()

            if fps > 0:
                time.sleep(max(0.0, 1.0 / fps - (time.time() - tloop)))

    # ------------------------------------------------------------------
    def start(self):
        # Create control SHMs first (including ROI shm if requested)
        self.init_shm_pre()

        try:
            # Init camera & AOI (this sets width/height/dtype), then create the
            # image SHM at the right size and start the control thread. All
            # inside the try so a SIGINT during open() still runs stop().
            self.init_camera()
            self.init_shm_image()

            self.control_thread = threading.Thread(
                target=self.control_loop, daemon=True)
            self.control_thread.start()

            self.run_acquisition()
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self):
        """Clean, ordered, uninterruptible shutdown of the camera.

        1. tell both loops to quit and unblock the acquisition wait
        2. wait for the control thread to leave its DCAM section
        3. with SIGINT/TERM/HUP deferred, run the full DCAM teardown under the
           camera lock so nothing else touches the handle and no signal can
           interrupt dcamapi_uninit()
        """
        if self._stopped:
            return
        self._stopped = True

        with _blocked_signals(signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            self.stop_event.set()
            if self.cam is not None:
                self.cam.abort_wait()

            if self.control_thread is not None:
                self.control_thread.join(timeout=10.0)
                if self.control_thread.is_alive():
                    print("\n[stop] control thread did not exit in time",
                          file=sys.stderr)

            with self._cam_lock:
                if self.cam is not None:
                    try:
                        self.cam.close()
                    except Exception as e:
                        print(f"\n[stop] camera close error: {e}", file=sys.stderr)
                    self.cam = None
        print("\nEND")


# ======================================================================
# CLI
# ======================================================================
def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-S", "--shm-image", default="/tmp/orca.im.shm")
    p.add_argument("--shm-dit")
    p.add_argument("--shm-readoutspeed")
    p.add_argument("--shm-fps")
    p.add_argument("--shm-roi")
    p.add_argument("--shm-temp")
    p.add_argument("--shm-settemp")
    p.add_argument("--no-roi", action="store_true",
                   help="do not create/watch the ROI control SHM")

    p.add_argument("--index", type=int, default=0, help="DCAM camera index (default 0)")
    p.add_argument("--lib-path", default=None,
                   help="explicit path to libdcamapi.so if auto-detection fails")
    p.add_argument("--nbuf", type=int, default=10, help="number of ring buffers (default 10)")

    p.add_argument("--dit", type=float, default=35.0, help="initial exposure time [ms]")
    p.add_argument("--readout-speed", type=int, default=None,
                   help="initial DCAM readout speed (1 = low noise ... higher = faster); "
                        "default: leave the camera's current setting")
    p.add_argument("--set-temp", type=float, default=None,
                   help="initial cooling setpoint [C]; ignored if the model has "
                        "fixed cooling. Default: leave the camera's current setting")
    p.add_argument("--fps", type=float, default=20.0,
                   help="initial target loop rate [Hz], 0 = free run")

    p.add_argument("--roi-x", type=int, default=0)
    p.add_argument("--roi-y", type=int, default=0)
    p.add_argument("--roi-w", type=int)
    p.add_argument("--roi-h", type=int)
    return p.parse_args()


def derive_names(base):
    root = base[:-7] if base.endswith(".im.shm") else base
    return {
        "dit": root + "Dit.im.shm",
        "readoutspeed": root + "ReadoutSpeed.im.shm",
        "fps": root + "Fps.im.shm",
        "roi": root + "Roi.im.shm",
        "temp": root + "Temp.im.shm",
        "settemp": root + "SetTemp.im.shm",
    }


def main():
    a = parse_args()
    names = derive_names(a.shm_image)

    app = OrcaShmApp(
        shm_image_name=a.shm_image,
        shm_dit_name=a.shm_dit or names["dit"],
        shm_readoutspeed_name=a.shm_readoutspeed or names["readoutspeed"],
        shm_fps_name=a.shm_fps or names["fps"],
        shm_roi_name=None if a.no_roi else (a.shm_roi or names["roi"]),
        shm_temp_name=a.shm_temp or names["temp"],
        shm_settemp_name=a.shm_settemp or names["settemp"],
        cam_index=a.index,
        lib_path=a.lib_path,
        nbuf=a.nbuf,
        roi_x=a.roi_x,
        roi_y=a.roi_y,
        roi_w=a.roi_w,
        roi_h=a.roi_h,
        init_dit_ms=a.dit,
        init_readout_speed=a.readout_speed,
        init_set_temp=a.set_temp,
        init_fps=a.fps,
    )

    # SIGTERM (process manager) and SIGHUP (tmux kill-session / kill-server, or
    # a closed terminal) must still run the full camera teardown, otherwise the
    # DCAM device is left open/streaming and the next start has to wait out the
    # USB stack. Route them through the same path as Ctrl-C. stop() then blocks
    # these signals while it closes the device, so a second one cannot
    # interrupt dcamapi_uninit().
    def _on_signal(signum, _frame):
        app.stop_event.set()
        raise KeyboardInterrupt()
    for _sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(_sig, _on_signal)

    try:
        app.start()
    except KeyboardInterrupt:
        # a signal that arrived in the tiny window after stop() unblocked them
        pass


if __name__ == "__main__":
    main()
