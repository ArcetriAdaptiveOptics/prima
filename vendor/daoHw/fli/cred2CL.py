#!/usr/bin/env -S ipython3 -i
# -*- coding: utf-8 -*-
"""
CRED-2 camera daemon — single-owner, thread-safe, frame-boundary control app.

Design:
- ONLY the acquisition thread executes camera control / serial commands.
- All setters are ENQUEUED asynchronously.
- All getters using serial commands are ENQUEUED synchronously and block
  until the acquisition thread executes them safely between frames.
- Control operations are applied with:
      Stop -> optional quiesce -> command(s) -> optional quiesce -> Start
- This avoids overlap between image grabbing and serial/control calls.

IMPORTANT:
- While acquisition is running, do NOT call FliSdk.* directly from the prompt.
- Use only the wrapper functions below:
      setFps(), setTint(), setGain(), setExtSynchro(),
      getFps(), getTint(), getTintRange(), getGain(), getTemp(), get_roi()
"""

import sys
import os
import time
import threading
import queue
import re

import numpy as np

# --- SDK / deps --------------------------------------------------------------
sys.path.append(os.getenv('FLISDK_DIR') + '/Python/lib')
import FliSdk_V2 as FliSdk
import dao

# --- Global sync -------------------------------------------------------------
roi_reconfig_lock = threading.RLock()
imAcqT = None
stop_imAcq_event = None
shm = None
shmPos = None
shmName = None

cam_lock = threading.RLock()   # serialize all FliSdk* calls
control_q = queue.Queue()      # queue of ControlRequest objects

QUIESCE_AFTER_STOP_S = 0.10
QUIESCE_BEFORE_START_S = 0.10
CONTROL_BATCH_MAX = 16

_FLOAT_RE = re.compile(r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")


# --- Request object ----------------------------------------------------------
class ControlRequest:
    """
    Request executed only by acquisition thread.

    Parameters
    ----------
    fn : callable
        Function called as fn(context, *args, **kwargs).
    args, kwargs :
        Arguments passed to fn.
    blocking : bool
        If True, caller waits on done event for result/error.
    name : str
        Optional debug label.
    """
    def __init__(self, fn, args=(), kwargs=None, blocking=False, name=""):
        self.fn = fn
        self.args = args
        self.kwargs = kwargs or {}
        self.blocking = blocking
        self.name = name

        self.done = threading.Event()
        self.result = None
        self.error = None


# --- Basic helpers -----------------------------------------------------------
def _with_lock(fn, *args, **kwargs):
    with cam_lock:
        return fn(*args, **kwargs)


def enqueue_async(fn, *args, name="", **kwargs):
    """
    Enqueue a non-blocking control request.
    """
    req = ControlRequest(fn=fn, args=args, kwargs=kwargs, blocking=False, name=name)
    control_q.put(req)
    return req


def enqueue_sync(fn, *args, timeout=5.0, name="", **kwargs):
    """
    Enqueue a blocking control request and wait for completion.
    """
    req = ControlRequest(fn=fn, args=args, kwargs=kwargs, blocking=True, name=name)
    control_q.put(req)

    ok = req.done.wait(timeout=timeout)
    if not ok:
        raise TimeoutError(f"Timed out waiting for camera request '{name or fn.__name__}'")

    if req.error is not None:
        raise req.error

    return req.result


def _serial_command_blocking(context, cmd, timeout=5.0):
    """
    Safe blocking serial command.
    Executed only by acquisition thread between frames.
    """
    def _cmd(ctx, c):
        return FliSdk.FliSerialCamera.SendCommand(ctx, c)

    return enqueue_sync(_cmd, cmd, timeout=timeout, name=f"SendCommand({cmd})")


def _send_command_get_float(context, cmd, default=float('nan'), timeout=5.0):
    ok, text = _serial_command_blocking(context, cmd, timeout=timeout)
    if not ok or not isinstance(text, str):
        return default

    m = _FLOAT_RE.search(text)
    return float(m.group(1)) if m else default


# --- Safe reads --------------------------------------------------------------
def get_roi(context):
    """
    ROI readback. This one does not use serial and is just lock-protected.
    """
    res, isenabled, roi = _with_lock(FliSdk.GetCroppingState, context)
    w, h = _with_lock(FliSdk.GetCurrentImageDimension, context)

    if isenabled:
        return (roi.col1, roi.row1,
                roi.col2 - roi.col1 + 1,
                roi.row2 - roi.row1 + 1)
    else:
        return (0, 0, w, h)


def getImage(context):
    """
    Get newest frame by watching buffer filling.
    Lock-protected, but only acquisition thread should normally call this.
    """
    currentfilling = _with_lock(FliSdk.GetBufferFilling, context)
    t0 = time.time()

    while True:
        filling = _with_lock(FliSdk.GetBufferFilling, context)
        if filling != currentfilling:
            return _with_lock(FliSdk.GetRawImageAsNumpyArray, context, -1)

        time.sleep(0.001)

        if time.time() - t0 > 2.0:
            return _with_lock(FliSdk.GetRawImageAsNumpyArray, context, -1)


def getFps(context, timeout=5.0):
    """
    Safe blocking FPS readback, executed by acquisition thread.
    """
    def _get(ctx):
        return FliSdk.FliSerialCamera.GetFps(ctx)

    ret = enqueue_sync(_get, timeout=timeout, name="GetFps")
    fps = ret[-1]
    print('Current FPS %.1f' % fps)
    return fps


def getTint(context, timeout=5.0):
    """
    Safe blocking tint readback using queued serial commands.
    """
    Tint = _send_command_get_float(context, 'tint', timeout=timeout)
    print('Integration time set to %.2e s' % Tint)

    return Tint


def getTintRange(context, timeout=5.0):
    """
    Safe blocking tint range readback using queued serial commands.
    """
    tmin = _send_command_get_float(context, 'mintint', timeout=timeout)
    tmax = _send_command_get_float(context, 'maxtint', timeout=timeout)
    return tmin, tmax

def getSyncDelay(context, timeout=5.0):
    """
    Safe blocking sync delay readback using queued serial commands.
    """
    syncDelay = _send_command_get_float(context, 'syncdelay', timeout=timeout)
    print('sync delay set to %.2e s' % syncDelay)

    return syncDelay

def getTemp(context, disp=True, timeout=5.0):
    """
    Safe blocking temperature readback using queued serial command.
    """
    ok, text = _serial_command_blocking(context, 'temperatures', timeout=timeout)

    if not isinstance(text, str):
        text = ""

    m = re.search(r"Sensor:\s*([0-9.]+)", text)
    temp = float(m.group(1)) if m else float('nan')

    if disp:
        print('Current sensor temperature %.2f°C' % temp)

    return temp


def getGain(context, disp=True, timeout=5.0):
    """
    Safe blocking gain readback using queued serial command.
    """
    ok, text = _serial_command_blocking(context, 'sensitivity', timeout=timeout)

    if ok and isinstance(text, str) and ':' in text:
        gain = text.split(':', 1)[1].strip().lower()
    else:
        gain = 'unknown'

    if disp:
        print('Conversion gain is %s' % gain)

    return gain


# --- Public API: async setters -----------------------------------------------
def setFps(context, fps):
    """
    Non-blocking: apply at next safe control window.
    """
    def _set(ctx, v):
        return FliSdk.FliSerialCamera.SetFps(ctx, float(v))

    enqueue_async(_set, fps, name=f"setFps({fps})")


def setTint(context, tInt):
    """
    Non-blocking: apply at next safe control window.
    """
    def _set(ctx, val):
        return FliSdk.FliSerialCamera.SendCommand(ctx, f"set tint {float(val):.9g}")

    enqueue_async(_set, tInt, name=f"setTint({tInt})")


def setIGain(context, gain):
    """
    Non-blocking integer gain selector:
        0 -> low
        1 -> medium
        2 -> high
    """
    if gain == 0:
        gain_str = 'low'
    elif gain == 1:
        gain_str = 'medium'
    elif gain == 2:
        gain_str = 'high'
    else:
        print("Gain is not valid, it should be 0 (low), 1 (medium) or 2 (high)")
        return

    setGain(context, gain_str)


def setGain(context, gain):
    """
    Non-blocking: apply at next safe control window.
    """
    g = str(gain).lower()

    def _set(ctx, gg):
        print(f"Setting gain to {gg}...")
        return FliSdk.FliSerialCamera.SendCommand(ctx, f"set sensitivity {gg}")

    enqueue_async(_set, g, name=f"setGain({g})")

def setSyncDelay(context, syncDelay):
    """
    Non-blocking: apply at next safe control window.
    """
    def _set(ctx, val):
        return FliSdk.FliSerialCamera.SendCommand(ctx, f"set syncdelay {float(val):.9g}")

    enqueue_async(_set, syncDelay, name=f"setSyncDelay({syncDelay})")

def setExtSynchroSource(context, source):
    """
    Non-blocking source mode selector:
        0 -> internal
        1 -> external
    """
    if source == 0:
        cmd = "set extsynchro source external"
    elif source == 1:
        cmd = "set extsynchro source internal"
    else:
        print("Source is not valid, it should be 0 (internal) or 1 (external)")
        return

    def _set(ctx, c):
        return FliSdk.FliSerialCamera.SendCommand(ctx, c)

    enqueue_async(_set, cmd, name=f"setExtSynchroSource({source})")

def setExtSynchroExposure(context, exposure):
    """
    Non-blocking exposure mode selector:
        0 -> internal
        1 -> external
    """
    if exposure == 0:
        cmd = "set extsynchro exposure internal"
    elif exposure == 1:
        cmd = "set extsynchro exposure external"
    else:
        print("exposure is not valid, it should be 0 (internal) or 1 (external)")
        return

    def _set(ctx, c):
        return FliSdk.FliSerialCamera.SendCommand(ctx, c)

    enqueue_async(_set, cmd, name=f"setExtSynchroExposure({exposure})")

def setExtSynchroPolarity(context, polarity):
    """
    Non-blocking polarity mode selector:
        0 -> standard
        1 -> inverted
    """
    if polarity == 0:
        cmd = "set extsynchro polarity standard"
    elif polarity == 1:
        cmd = "set extsynchro polarity inverted"
    else:
        print("polarity is not valid, it should be 0 (internal) or 1 (external)")
        return

    def _set(ctx, c):
        return FliSdk.FliSerialCamera.SendCommand(ctx, c)

    enqueue_async(_set, cmd, name=f"setExtSynchroPolarity({polarity})")

def setExtSynchro(context, trigger):
    """
    Non-blocking trigger mode selector:
        0 -> internal
        1 -> external
    """
    if trigger == 0:
        cmd = "set extsynchro off"
    elif trigger == 1:
        setExtSynchroSource(context, 1)
        setExtSynchroExposure(context, 0)
        cmd = "set extsynchro on"
    else:
        print("Trigger is not valid, it should be 0 (internal) or 1 (external)")
        return

    def _set(ctx, c):
        return FliSdk.FliSerialCamera.SendCommand(ctx, c)

    enqueue_async(_set, cmd, name=f"setExtSynchro({trigger})")

def setCroppingRows(context, start, end):
    """
    Set cropping rows.
    Must be called only while acquisition thread is stopped for ROI reconfiguration.
    """
    cmd = f"set cropping rows {int(start)}-{int(end)}"
    ok, result = FliSdk.FliSerialCamera.SendCommand(context, cmd)
    if ok:
        print(f"Cropping rows set to {start}-{end}")
    else:
        print(f"Failed to set cropping rows: {result}")
    return ok, result


def setCroppingColumns(context, start, end):
    """
    Set cropping columns.
    Must be called only while acquisition thread is stopped for ROI reconfiguration.
    """
    cmd = f"set cropping columns {int(start)}-{int(end)}"
    ok, result = FliSdk.FliSerialCamera.SendCommand(context, cmd)
    if ok:
        print(f"Cropping columns set to {start}-{end}")
    else:
        print(f"Failed to set cropping columns: {result}")
    return ok, result


def enableCropping(context, enable=True):
    """
    Enable or disable cropping.
    Must be called only while acquisition thread is stopped for ROI reconfiguration.
    """
    cmd = "set cropping on" if enable else "set cropping off"
    ok, result = FliSdk.FliSerialCamera.SendCommand(context, cmd)
    if ok:
        print(f"Cropping {'enabled' if enable else 'disabled'}")
    else:
        print(f"Failed to {'enable' if enable else 'disable'} cropping: {result}")
    return ok, result


def restartImAcqThread(context, shmName, buffer=None):
    """
    Stop the current acquisition thread, recreate the main image SHM
    if needed, and start a new acquisition thread.
    """
    global imAcqT, stop_imAcq_event, shm

    # Ask current acquisition thread to stop
    if stop_imAcq_event is not None:
        stop_imAcq_event.set()

    # Wait until it is really stopped
    if imAcqT is not None and imAcqT.is_alive():
        if threading.current_thread() is imAcqT:
            raise RuntimeError("restartImAcqThread() cannot be called from imAcq thread")
        imAcqT.join(timeout=5.0)
        if imAcqT.is_alive():
            raise RuntimeError("Acquisition thread did not stop cleanly before restart")

    with roi_reconfig_lock:
        if buffer is None:
            buffer = _with_lock(FliSdk.GetRawImageAsNumpyArray, context, -1)

        # Recreate shm only if geometry changed
        recreate = True
        if shm is not None:
            try:
                old_shape = shm.get_data().shape
                recreate = (old_shape != buffer.shape)
            except Exception:
                recreate = True

        if recreate:
            shm = dao.shm(f"/tmp/{shmName}.im.shm", buffer)
            print(f"restartImAcqThread: recreated shm with shape={buffer.shape}")
        else:
            print(f"restartImAcqThread: shm shape unchanged {buffer.shape}")

        stop_imAcq_event = threading.Event()
        imAcqT = threading.Thread(
            target=imAcq,
            args=(context, shm, stop_imAcq_event),
            daemon=True
        )
        imAcqT.start()


def setRoi(context, col1, row1, width, height):
    """
    Set ROI safely.

    Special case:
        setRoi(context, 0, 0, 0, 0)
    disables cropping and returns to full frame.

    Since frame dimensions may change, this function:
    - stops acquisition thread
    - stops camera
    - applies ROI / disables cropping
    - restarts camera
    - grabs a frame with new geometry
    - recreates shm if needed
    - restarts acquisition thread
    """
    global shmPos, shmName, imAcqT, stop_imAcq_event

    col1 = int(col1)
    row1 = int(row1)
    width = int(width)
    height = int(height)

    disable_mode = (col1 == 0 and row1 == 0 and width == 0 and height == 0)

    if not disable_mode:
        if width <= 0 or height <= 0:
            print("Error: width and height must be > 0, or use 0,0,0,0 to disable cropping")
            return False, "Invalid ROI size"

        if width % 32 != 0:
            print(f"Error: Width {width} is not a multiple of 32")
            return False, "Width not multiple of 32"

        if height % 4 != 0:
            print(f"Error: Height {height} is not a multiple of 4")
            return False, "Height not multiple of 4"

        col2 = col1 + width - 1
        row2 = row1 + height - 1

    try:
        # -------------------------------------------------
        # 1) Stop acquisition thread completely
        # -------------------------------------------------
        if stop_imAcq_event is not None:
            stop_imAcq_event.set()

        if imAcqT is not None and imAcqT.is_alive():
            if threading.current_thread() is imAcqT:
                raise RuntimeError("setRoi() cannot be called from imAcq thread")
            imAcqT.join(timeout=5.0)
            if imAcqT.is_alive():
                raise RuntimeError("Acquisition thread did not stop before ROI change")

        # -------------------------------------------------
        # 2) Reconfigure camera while thread is stopped
        # -------------------------------------------------
        with roi_reconfig_lock:
            with cam_lock:
                FliSdk.Stop(context)

                if QUIESCE_AFTER_STOP_S > 0:
                    time.sleep(QUIESCE_AFTER_STOP_S)

                if disable_mode:
                    ok, result = enableCropping(context, False)
                    if not ok:
                        FliSdk.Start(context)
                        return False, result

                    print("ROI 0,0,0,0 detected: cropping disabled, returning to full frame")

                else:
                    ok1, result1 = setCroppingRows(context, row1, row2)
                    ok2, result2 = setCroppingColumns(context, col1, col2)

                    if not ok1:
                        FliSdk.Start(context)
                        return False, result1

                    if not ok2:
                        FliSdk.Start(context)
                        return False, result2

                    ok3, result3 = enableCropping(context, True)
                    if not ok3:
                        FliSdk.Start(context)
                        return False, result3

                    print(f"ROI set to ({col1}, {row1}, {width}, {height})")

                if QUIESCE_BEFORE_START_S > 0:
                    time.sleep(QUIESCE_BEFORE_START_S)

                FliSdk.Start(context)

                # Let the camera deliver a frame with the new geometry
                time.sleep(0.2)

                buffer = FliSdk.GetRawImageAsNumpyArray(context, -1)

        # -------------------------------------------------
        # 3) Update ROI position/size shm
        # -------------------------------------------------
        if disable_mode:
            full_h, full_w = buffer.shape[0], buffer.shape[1]
            shmPos.set_data(np.array([[0, 0, full_w, full_h]], dtype=np.uint32).T)
        else:
            shmPos.set_data(np.array([[col1, row1, width, height]], dtype=np.uint32).T)

        # -------------------------------------------------
        # 4) Recreate image shm / restart acquisition thread
        # -------------------------------------------------
        restartImAcqThread(context, shmName, buffer=buffer)

        return True, "ROI set successfully"

    except Exception as e:
        print(f"Error while setting ROI: {e}")

        try:
            with cam_lock:
                FliSdk.Start(context)
        except Exception:
            pass

        return False, str(e)


def disableCropping(context):
    """
    Disable cropping and return to full frame mode.
    """
    return setRoi(context, 0, 0, 0, 0)

# --- Optional direct blocking control helper ---------------------------------
def setTint_blocking(context, tInt, timeout=5.0):
    """
    Safe blocking version, still goes through acquisition thread.
    """
    def _set(ctx, val):
        return FliSdk.FliSerialCamera.SendCommand(ctx, f"set tint {float(val):.9g}")

    return enqueue_sync(_set, tInt, timeout=timeout, name=f"setTint_blocking({tInt})")


# --- Drain controls exactly BETWEEN frames -----------------------------------
def _apply_pending_controls(context, max_ops=CONTROL_BATCH_MAX):
    """
    Drain up to max_ops queued requests.

    All queued control/serial operations are executed here, only here:
        Stop -> quiesce -> run batch -> quiesce -> Start

    This is the safe path for both setters and serial getters.
    """
    reqs = []

    while len(reqs) < max_ops:
        try:
            req = control_q.get_nowait()
        except queue.Empty:
            break
        reqs.append(req)

    if not reqs:
        return

    try:
        with cam_lock:
            FliSdk.Stop(context)

            if QUIESCE_AFTER_STOP_S > 0:
                time.sleep(QUIESCE_AFTER_STOP_S)

            for req in reqs:
                try:
                    req.result = req.fn(context, *req.args, **req.kwargs)
                except Exception as e:
                    req.error = e
                    print(f"Control error in {req.name or 'request'}: {e}")
                finally:
                    req.done.set()
                    control_q.task_done()

            if QUIESCE_BEFORE_START_S > 0:
                time.sleep(QUIESCE_BEFORE_START_S)

            FliSdk.Start(context)

    except Exception as batch_err:
        print("Batch control error:", batch_err)

        for req in reqs:
            if req.error is None:
                req.error = batch_err
            req.done.set()
            control_q.task_done()


# --- Threads -----------------------------------------------------------------
def imAcq(obj, shm, stop_event):
    """
    Acquisition thread:
    - acquires new frame
    - publishes frame
    - executes pending control requests between frames
    - stops when stop_event is set

    Important safety rule:
    - never write a frame into shm if the shapes do not match
    """
    try:
        while not stop_event.is_set():
            frame = getImage(obj)

            if stop_event.is_set():
                break

            with roi_reconfig_lock:
                if stop_event.is_set():
                    break

                shm_data = shm.get_data()
                if frame.shape != shm_data.shape:
                    print(f"imAcq: frame shape changed from {shm_data.shape} to {frame.shape}, stopping thread before set_data")
                    break

                shm.set_data(frame)

            if stop_event.is_set():
                break

            _apply_pending_controls(obj)

    except KeyboardInterrupt:
        print('\nEnd of acquisition')
    except Exception as e:
        print(f"Error in acquisition thread: {e}")


def fpsCtrl(obj, shm):
    while True:
        fps = float(shm.get_data(check=True)[0, 0])
        print(f"detection of new FPS : {fps} Hz, applying.")
        setFps(obj, fps)


def ditCtrl(obj, shm):
    while True:
        dit = float(shm.get_data(check=True)[0, 0])
        print(f"detection of new DIT : {dit} s, applying.")
        setTint(obj, dit)


def gainCtrl(obj, shm):
    while True:
        gain = float(shm.get_data(check=True)[0, 0])
        print(f"detection of new GAIN : {gain}.")
        setIGain(obj, gain)


def triggerCtrl(obj, shm):
    while True:
        trigger = float(shm.get_data(check=True)[0, 0])
        print(f"detection of new Trigger : {trigger}. (0=internal, 1=external)")
        setExtSynchro(obj, trigger)


def syncDelayCtrl(obj, shm):
    while True:
        syncDelay = float(shm.get_data(check=True)[0, 0])
        print(f"detection of new SYNC DELAY : {syncDelay} s, applying.")
        setSyncDelay(obj, syncDelay)

def roiPosCtrl(obj, shm):
    """
    Monitor shmPos for ROI changes.

    Expected layout:
        [[x],
         [y],
         [width],
         [height]]

    Special value:
        0,0,0,0 -> disable cropping
    """
    last_pos = shm.get_data().copy()

    while True:
        pos = shm.get_data(check=True)

        if not np.array_equal(pos, last_pos):
            last_pos = pos.copy()

            col1 = int(pos[0, 0])
            row1 = int(pos[1, 0])
            width = int(pos[2, 0])
            height = int(pos[3, 0])

            print(f"New ROI request: ({col1}, {row1}, {width}, {height}), applying.")
            ok, msg = setRoi(obj, col1, row1, width, height)
            if not ok:
                print(f"ROI change failed: {msg}")

# --- Main --------------------------------------------------------------------
if __name__ == '__main__':
    # ---------------------------------------------------------
    # Parse command line arguments
    # Usage: cred2CL.py [camId] [shmName]
    # Example:
    #     cred2CL.py 0 cred2
    # ---------------------------------------------------------
    camId = None
    shmName = None

    if len(sys.argv) >= 2:
        camId = int(sys.argv[1])

    if len(sys.argv) >= 3:
        shmName = sys.argv[2]

    # ---------------------------------------------------------
    # Init SDK
    # ---------------------------------------------------------
    fli_obj = _with_lock(FliSdk.Init)
    _ = _with_lock(FliSdk.DetectGrabbers, fli_obj)
    cameras_list = _with_lock(FliSdk.DetectCameras, fli_obj)

    # ---------------------------------------------------------
    # Camera selection
    # ---------------------------------------------------------
    if camId is None:
        print("Select the camera")
        for k in range(len(cameras_list)):
            print(f"{k} : {cameras_list[k]}")
        print("select camera #:")
        camId = int(input())

    if camId < 0 or camId >= len(cameras_list):
        raise ValueError(f"Invalid camera index {camId}")

    print(f"camera {camId} selected: {cameras_list[camId]}")

    # ---------------------------------------------------------
    # Shared memory name
    # ---------------------------------------------------------
    if shmName is None:
        print("select name for the shared memory: ")
        shmName = input()

    print(f"Shared memory name: {shmName}")

    if cameras_list and cameras_list[0] != 'Usb#':
        _with_lock(FliSdk.SetCamera, fli_obj, cameras_list[camId])
        _with_lock(FliSdk.Update, fli_obj)
    else:
        raise ConnectionError("No camera found...")

    _with_lock(FliSdk.Start, fli_obj)
    _with_lock(FliSdk.FliCred.EnableLed, fli_obj, True)
    # Disable cropping to start in full frame mode
    disableCropping(fli_obj)
    buffer = _with_lock(FliSdk.GetRawImageAsNumpyArray, fli_obj, -1)

    shm = dao.shm(f"/tmp/{shmName}.im.shm", buffer)
    shmBg = dao.shm(f"/tmp/{shmName}Bg.im.shm", buffer.astype(np.float32) * 0)
    shmFps = dao.shm(f"/tmp/{shmName}Fps.im.shm",
                     50 * np.ones((1, 1), dtype=np.float32))
    shmDit = dao.shm(f"/tmp/{shmName}Dit.im.shm",
                     np.ones((1, 1), dtype=np.float32)/shmFps.get_data()[0, 0])
    shmGain = dao.shm(f"/tmp/{shmName}Gain.im.shm",
                      np.zeros((1, 1), dtype=np.float32))
    shmTrigger = dao.shm(f"/tmp/{shmName}Trigger.im.shm",
                         np.zeros((1, 1), dtype=np.float32))
    shmSyncDelay = dao.shm(f"/tmp/{shmName}SyncDelay.im.shm",
                      np.zeros((1, 1), dtype=np.float32))
    # Create shmPos with full frame dimensions
    shmPos = dao.shm(
        f"/tmp/{shmName}PosSize.im.shm",
        np.array([[0, 0, buffer.shape[1], buffer.shape[0]]], dtype=np.uint32).T
    )

    fpsCtrlT=threading.Thread(target=fpsCtrl, args=(fli_obj, shmFps), daemon=True)
    ditCtrlT=threading.Thread(target=ditCtrl, args=(fli_obj, shmDit), daemon=True)
    gainCtrlT=threading.Thread(target=gainCtrl, args=(fli_obj, shmGain), daemon=True)
    triggerCtrlT=threading.Thread(target=triggerCtrl, args=(fli_obj, shmTrigger), daemon=True)
    syncDelayCtrlT=threading.Thread(target=syncDelayCtrl, args=(fli_obj, shmSyncDelay), daemon=True)
    roiPosCtrlT=threading.Thread(target=roiPosCtrl, args=(fli_obj, shmPos), daemon=True)
    # Create a stop event for the acquisition thread
    stop_imAcq_event = threading.Event()
    imAcqT=threading.Thread(target=imAcq, args=(fli_obj, shm, stop_imAcq_event), daemon=True)

    fpsCtrlT.start()
    ditCtrlT.start()
    gainCtrlT.start()
    triggerCtrlT.start()
    syncDelayCtrlT.start()
    roiPosCtrlT.start()
    imAcqT.start()

    shmFps.set_data(shmFps.get_data() * 0 + getFps(fli_obj))
    shmDit.set_data(shmDit.get_data() * 0 + getTint(fli_obj))
    print(
        "\nThreads started.\n"
        "Controls and serial readbacks are executed only by the acquisition thread.\n\n"
        "SAFE functions to use from IPython:\n"
        "  setFps(fli_obj, NEW_FPS)\n"
        "  setTint(fli_obj, NEW_TINT_S)\n"
        "  setGain(fli_obj, 'low|medium|high')\n"
        "  setIGain(fli_obj, 0|1|2)\n"
        "  setExtSynchro(fli_obj, 0|1)\n"
        "  getFps(fli_obj)\n"
        "  getTint(fli_obj)\n"
        "  getTintRange(fli_obj)\n"
        "  getGain(fli_obj)\n"
        "  getTemp(fli_obj)\n"
        "  get_roi(fli_obj)\n\n"
        "Shared memories:\n"
        f"  {shmName}PosSize.im.shm: ROI position and size (x, y, width, height)\n"
        "DO NOT call FliSdk.FliSerialCamera.SendCommand(...) directly while acquisition runs.\n"
    )