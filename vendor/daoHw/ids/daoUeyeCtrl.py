#!/usr/bin/env python3
"""
uEye camera -> DAO shared memory streamer
DIT, Gain, FPS control via SHM
ROI via CLI or SHM (SHM overrides CLI)

ROI precedence:
  1) --shm-roi (x,y,w,h)
  2) --roi-x/y/w/h
  3) Full sensor
"""

import sys
import time
import threading
import argparse

import numpy as np
try:
    from pyueye import ueye
except ImportError:
    print("Error: pyueye module not found. Please install the uEye SDK and pyueye package.", file=sys.stderr)
import dao


class UeyeShmApp:
    def __init__(
        self,
        shm_image_name,
        shm_dit_name,
        shm_gain_name,
        shm_fps_name,
        shm_roi_name=None,
        roi_x=0,
        roi_y=0,
        roi_w=None,
        roi_h=None,
    ):
        # Names
        self.shm_image_name = shm_image_name
        self.shm_dit_name = shm_dit_name
        self.shm_gain_name = shm_gain_name
        self.shm_fps_name = shm_fps_name
        self.shm_roi_name = shm_roi_name

        # CLI ROI
        self.roi_x = roi_x
        self.roi_y = roi_y
        self.roi_w = roi_w
        self.roi_h = roi_h

        # uEye objects (must stay alive)
        self.hCam = ueye.HIDS(0)
        self.sInfo = ueye.SENSORINFO()
        self.cInfo = ueye.CAMINFO()
        self.rectAOI = ueye.IS_RECT()
        self.pcImageMemory = ueye.c_mem_p()
        self.MemID = ueye.int()
        self.pitch = ueye.INT()
        self.nBitsPerPixel = ueye.INT(8)
        self.m_nColorMode = ueye.INT(ueye.IS_CM_MONO8)

        self.width = None   # Python int
        self.height = None  # Python int

        # SHM objects
        self.shm_image = None
        self.shm_dit = None
        self.shm_gain = None
        self.shm_fps = None
        self.shm_roi = None

        # Threads
        self.stop_event = threading.Event()
        self.control_thread = None

    # ------------------------------------------------------------------
    # AOI helper
    # ------------------------------------------------------------------
    def apply_roi(self, x, y, w, h):
        rect = ueye.IS_RECT()
        rect.s32X = int(x)
        rect.s32Y = int(y)
        rect.s32Width = int(w)
        rect.s32Height = int(h)

        ret = ueye.is_AOI(
            self.hCam,
            ueye.IS_AOI_IMAGE_SET_AOI,
            rect,
            ueye.sizeof(rect),
        )
        if ret != ueye.IS_SUCCESS:
            raise RuntimeError(f"is_AOI_IMAGE_SET_AOI failed (ret={ret})")

        ret = ueye.is_AOI(
            self.hCam,
            ueye.IS_AOI_IMAGE_GET_AOI,
            self.rectAOI,
            ueye.sizeof(self.rectAOI),
        )
        if ret != ueye.IS_SUCCESS:
            raise RuntimeError("is_AOI_IMAGE_GET_AOI failed")

        self.width = int(self.rectAOI.s32Width)
        self.height = int(self.rectAOI.s32Height)

        print(f"[AOI] x={x} y={y} w={self.width} h={self.height}")

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
            print(f"ROI from SHM: x={x} y={y} w={w} h={h}")
            return int(x), int(y), int(w), int(h)

        x = int(self.roi_x)
        y = int(self.roi_y)

        if self.roi_w is None or self.roi_h is None:
            w = int(self.sInfo.nMaxWidth)
            h = int(self.sInfo.nMaxHeight)
            print("ROI from CLI: full sensor")
        else:
            w = int(self.roi_w)
            h = int(self.roi_h)
            print(f"ROI from CLI: x={x} y={y} w={w} h={h}")

        return x, y, w, h

    # ------------------------------------------------------------------
    # Camera init (opens camera, applies ROI, alloc mem, starts capture)
    # ------------------------------------------------------------------
    def init_camera(self):
        print("START\n")

        if ueye.is_InitCamera(self.hCam, None) != ueye.IS_SUCCESS:
            raise RuntimeError("is_InitCamera failed")

        ueye.is_GetCameraInfo(self.hCam, self.cInfo)
        ueye.is_GetSensorInfo(self.hCam, self.sInfo)
        ueye.is_ResetToDefault(self.hCam)

        # Decide ROI now that we know sensor max size
        x, y, w, h = self.determine_initial_roi()

        # Apply AOI now -> sets self.width/self.height
        self.apply_roi(x, y, w, h)

        # Allocate image memory (must use AOI width/height)
        if ueye.is_AllocImageMem(
            self.hCam,
            self.width,
            self.height,
            self.nBitsPerPixel,
            self.pcImageMemory,
            self.MemID,
        ) != ueye.IS_SUCCESS:
            raise RuntimeError("is_AllocImageMem failed")

        ueye.is_SetImageMem(self.hCam, self.pcImageMemory, self.MemID)
        ueye.is_SetColorMode(self.hCam, self.m_nColorMode)
        ueye.is_CaptureVideo(self.hCam, ueye.IS_DONT_WAIT)

        # Inquire pitch etc - requires ctypes INT arguments
        width_ct = ueye.INT(self.width)
        height_ct = ueye.INT(self.height)

        ret = ueye.is_InquireImageMem(
            self.hCam,
            self.pcImageMemory,
            self.MemID,
            width_ct,
            height_ct,
            self.nBitsPerPixel,
            self.pitch,
        )
        if ret != ueye.IS_SUCCESS:
            raise RuntimeError("is_InquireImageMem failed")

        print("Camera:", self.sInfo.strSensorName.decode())
        print("Serial:", self.cInfo.SerNo.decode())
        print("Press Ctrl+C to stop")

    # ------------------------------------------------------------------
    # SHM init
    # IMPORTANT: create ROI/Dit/Gain/Fps first, but create IMAGE shm only
    # AFTER we know width/height (after AOI has been applied).
    # ------------------------------------------------------------------
    def init_shm_pre(self):
        # Controls can exist before image size is known
        self.shm_dit = dao.shm(
            self.shm_dit_name,
            np.ones((1, 1), dtype=np.float32) * 35.0,
        )

        self.shm_gain = dao.shm(
            self.shm_gain_name,
            np.ones((1, 1), dtype=np.float32),
        )

        self.shm_fps = dao.shm(
            self.shm_fps_name,
            np.ones((1, 1), dtype=np.float32) * 20.0,
        )

        # ROI control SHM must exist early so it can override CLI ROI
        if self.shm_roi_name:
            self.shm_roi = dao.shm(
                self.shm_roi_name,
                np.array([[0, 0, 0, 0]], dtype=np.int32),
            )

    def init_shm_image(self):
        """
        Create shm_image *immediately* with the correct AOI shape.
        This fixes "receiver sees wrong pixel size" problems.
        """
        if self.width is None or self.height is None:
            raise RuntimeError("init_shm_image called before AOI width/height known")

        self.shm_image = dao.shm(
            self.shm_image_name,
            np.zeros((self.height, self.width), dtype=np.uint8),
        )

    # ------------------------------------------------------------------
    # Control loop
    # ------------------------------------------------------------------
    def control_loop(self):
        last_dit = self.shm_dit.get_counter()
        last_gain = self.shm_gain.get_counter()
        last_roi = self.shm_roi.get_counter() if self.shm_roi else None

        while not self.stop_event.is_set():
            if self.shm_dit.get_counter() != last_dit:
                last_dit = self.shm_dit.get_counter()
                dit = ueye.double(float(self.shm_dit.get_data()[0, 0]))
                ueye.is_Exposure(
                    self.hCam,
                    ueye.IS_EXPOSURE_CMD_SET_EXPOSURE,
                    dit,
                    ueye.sizeof(dit),
                )

            if self.shm_gain.get_counter() != last_gain:
                last_gain = self.shm_gain.get_counter()
                g = int(self.shm_gain.get_data()[0, 0])
                ueye.is_SetHardwareGain(self.hCam, g, 0, 0, 0)

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
        ueye.is_StopLiveVideo(self.hCam, ueye.IS_FORCE_VIDEO_STOP)
        ueye.is_FreeImageMem(self.hCam, self.pcImageMemory, self.MemID)

        self.apply_roi(x, y, w, h)

        if ueye.is_AllocImageMem(
            self.hCam,
            self.width,
            self.height,
            self.nBitsPerPixel,
            self.pcImageMemory,
            self.MemID,
        ) != ueye.IS_SUCCESS:
            print("[CTRL] is_AllocImageMem failed", file=sys.stderr)
            return

        ueye.is_SetImageMem(self.hCam, self.pcImageMemory, self.MemID)
        ueye.is_CaptureVideo(self.hCam, ueye.IS_DONT_WAIT)

        # Recreate image shm with NEW correct shape
        self.init_shm_image()

    # ------------------------------------------------------------------
    # Acquisition loop
    # ------------------------------------------------------------------
    def run_acquisition(self):
        t0 = time.time()
        frames = 0

        while not self.stop_event.is_set():
            fps = max(1.0, float(self.shm_fps.get_data()[0, 0]))
            tloop = time.time()

            arr = ueye.get_data(
                self.pcImageMemory,
                self.width,
                self.height,
                self.nBitsPerPixel,
                self.pitch,
                copy=False,
            )

            self.shm_image.set_data(arr.reshape(self.height, self.width))

            frames += 1
            sys.stdout.write(f"\rFrame {frames} @ {frames/(time.time()-t0):.2f} fps")
            sys.stdout.flush()

            time.sleep(max(0, 1.0 / fps - (time.time() - tloop)))

    # ------------------------------------------------------------------
    def start(self):
        # Create control SHMs first (including ROI shm if requested)
        self.init_shm_pre()

        # Init camera & AOI (this sets width/height)
        self.init_camera()

        # NOW create image SHM at correct size immediately
        self.init_shm_image()

        # Start control thread
        self.control_thread = threading.Thread(target=self.control_loop, daemon=True)
        self.control_thread.start()

        try:
            self.run_acquisition()
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self):
        self.stop_event.set()
        if self.control_thread:
            self.control_thread.join(1.0)

        ueye.is_FreeImageMem(self.hCam, self.pcImageMemory, self.MemID)
        ueye.is_ExitCamera(self.hCam)
        print("\nEND")


# ======================================================================
# CLI
# ======================================================================
def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("-S", "--shm-image", default="/tmp/ueye.im.shm")
    p.add_argument("--shm-dit")
    p.add_argument("--shm-gain")
    p.add_argument("--shm-fps")
    p.add_argument("--shm-roi")

    p.add_argument("--roi-x", type=int, default=0)
    p.add_argument("--roi-y", type=int, default=0)
    p.add_argument("--roi-w", type=int)
    p.add_argument("--roi-h", type=int)
    return p.parse_args()


def derive_names(base):
    root = base[:-7] if base.endswith(".im.shm") else base
    return (
        root + "Dit.im.shm",
        root + "Gain.im.shm",
        root + "Fps.im.shm",
    )


def main():
    a = parse_args()
    shm_dit, shm_gain, shm_fps = derive_names(a.shm_image)

    app = UeyeShmApp(
        shm_image_name=a.shm_image,
        shm_dit_name=a.shm_dit or shm_dit,
        shm_gain_name=a.shm_gain or shm_gain,
        shm_fps_name=a.shm_fps or shm_fps,
        shm_roi_name=a.shm_roi,
        roi_x=a.roi_x,
        roi_y=a.roi_y,
        roi_w=a.roi_w,
        roi_h=a.roi_h,
    )
    app.start()


if __name__ == "__main__":
    main()
