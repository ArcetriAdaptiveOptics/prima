#!/usr/bin/env python3
"""!
@file daoHwBaslerAce.py
@brief Basler Ace camera interface with shared-memory image and parameter control.

@details
This script opens a Basler camera via pypylon, reports camera configuration,
publishes image frames to shared memory, and monitors shared-memory control
channels for runtime updates to frame rate, gain, and exposure time.

@section dependencies Dependencies
- threading
- time
- pypylon.pylon
- pypylon.genicam
- numpy
- dao

@section shm_layout Shared Memory Attributes
- `/tmp/camera.im.shm`      : Latest image frame.
- `/tmp/cameraFps.im.shm`   : Requested camera FPS (float32 scalar).
- `/tmp/cameraGain.im.shm`  : Requested camera gain (float32 scalar).
- `/tmp/cameraDit.im.shm`   : Requested exposure time in microseconds (float32 scalar).
"""

import threading
import time
import argparse
import pypylon.pylon as pylon
from pypylon import genicam
import numpy as np

import dao

## @brief Stop event for the frame-receive worker thread.
camera_receive_thread_stop_event = threading.Event()
## @brief Stop event for the parameter-control worker thread.
camera_control_thread_stop_event = threading.Event()

## @brief Shared-memory handle for the latest image frame.
camShm = None
## @brief Shared-memory handle for FPS control value.
camFpsShm = None
## @brief Shared-memory handle for gain control value.
camGainShm = None
## @brief Shared-memory handle for exposure-time control value.
camDitShm = None


def derive_control_shm_name(camera_shm_name, suffix):
    """!
    @brief Derive control shm filename by adding suffix to camera shm basename.
    @param camera_shm_name Base camera shm filename.
    @param suffix Suffix to append (e.g. `Fps`, `Gain`, `Dit`).
    @return Derived shm filename.
    """
    marker = ".im.shm"
    if camera_shm_name.endswith(marker):
        return f"{camera_shm_name[:-len(marker)]}{suffix}{marker}"
    return f"{camera_shm_name}{suffix}"

def dtype_to_numpy_dtype(dtype):
    """!
    @brief Convert a GenICam pixel format to a NumPy dtype string.
    @param dtype Pixel format name or GenICam pixel type constant.
    @return NumPy dtype string (`uint8` or `uint16`).
    @throws ValueError If the pixel format is unsupported.
    """
    if dtype == "Mono8" or dtype == genicam.PixelType_Mono8:
        return "uint8"
    elif dtype == "Mono10" or dtype == genicam.PixelType_Mono10:
        return "uint16"
    elif dtype == "Mono12" or dtype == genicam.PixelType_Mono12:
        return "uint16"
    elif dtype == "Mono14" or dtype == genicam.PixelType_Mono14:
        return "uint16"
    elif dtype == "Mono16" or dtype == genicam.PixelType_Mono16:
        return "uint16"
    elif dtype == "RGB8packed" or dtype == genicam.PixelType_RGB8packed:
        return "uint8"  # 3 channels, 8 bits each
    elif dtype == "BGR8packed" or dtype == genicam.PixelType_BGR8packed:
        return "uint8"  # 3 channels, 8 bits each
    elif dtype == "RGB10packed" or dtype == genicam.PixelType_RGB10packed:
        return "uint16"  # 3 channels, 10 bits each
    elif dtype == "RGB12packed" or dtype == genicam.PixelType_RGB12packed:
        return "uint16"  # 3 channels, 12 bits each
    elif dtype == "RGB14packed" or dtype == genicam.PixelType_RGB14packed:
        return "uint16"  # 3 channels, 14 bits each
    elif dtype == "RGB16packed" or dtype == genicam.PixelType_RGB16packed:
        return "uint16"  # 3 channels, 16 bits each
    else:
        raise ValueError(f"Unsupported pixel format: {dtype}")

def get_camera_details(camera, camera_shm_name="/tmp/camera.im.shm"):
    """!
    @brief Print camera metadata and initialize shared-memory channels.
    @param camera Opened pypylon camera object.
    @details
    Reads key transport/acquisition nodes, prints value ranges when available,
    and allocates shared-memory objects for image data and control parameters.
    """

    def get_value(node_names, default="N/A"):
        """!
        @brief Read first available/readable node value from candidate names.
        @param node_names Ordered list of camera node names.
        @param default Value returned when no node can be read.
        @return Node value or @p default.
        """
        for name in node_names:
            node = getattr(camera, name, None)
            if node is None:
                continue
            try:
                if genicam.IsAvailable(node) and genicam.IsReadable(node):
                    return node.GetValue()
            except Exception:
                continue
        return default

    def get_range(node_names):
        """!
        @brief Get node min/max limits if supported.
        @param node_names Ordered list of camera node names.
        @return Tuple `(min, max)` or `("N/A", "N/A")`.
        """
        for name in node_names:
            node = getattr(camera, name, None)
            if node is None:
                continue
            try:
                if genicam.IsAvailable(node) and genicam.IsReadable(node):
                    return node.GetMin(), node.GetMax()
            except Exception:
                continue  # enum/bool/string nodes don't have GetMin/GetMax
        return "N/A", "N/A"

    def fmt(node_names, unit="", default="N/A"):
        """!
        @brief Format a node value as `value [min - max]` when available.
        @param node_names Ordered list of camera node names.
        @param unit Optional suffix appended to displayed values.
        @param default Fallback value when no node is readable.
        @return Formatted string for status output.
        """
        value = get_value(node_names, default)
        min_v, max_v = get_range(node_names)
        if min_v == "N/A":
            return f"{value}{unit}"
        return f"{value}{unit}  [{min_v} - {max_v}]"

    was_open = camera.IsOpen()
    if not was_open:
        camera.Open()

    print("=" * 60)
    print("CAMERA DETAILS")
    print("=" * 60)

    # --- Identification ---
    print(f"Model Name:        {camera.DeviceInfo.ModelName}")
    print(f"Serial Number:     {camera.DeviceInfo.SerialNumber}")
    print(f"Vendor:            {camera.DeviceInfo.VendorName}")
    try:
        print(f"Device Version:    {camera.DeviceInfo.GetDeviceVersion()}")
    except Exception:
        print("Device Version:    N/A")
    try:
        print(f"Interface:         {camera.DeviceInfo.GetDeviceClass()}")
    except Exception:
        pass

    print("-" * 60)

    # --- Image geometry ---
    print(f"Width:             {fmt(['Width'])}")
    print(f"Height:            {fmt(['Height'])}")
    print(f"Offset X:          {fmt(['OffsetX'])}")
    print(f"Offset Y:          {fmt(['OffsetY'])}")
    print(f"Pixel Format:      {get_value(['PixelFormat'])}")

    # get sensor size if available
    sensor_width = get_value(["SensorWidth"])
    sensor_height = get_value(["SensorHeight"])
    sensor_dtype = dtype_to_numpy_dtype(get_value(["PixelFormat"]))
    print(f"Sensor Size:       {sensor_width} x {sensor_height} ({sensor_dtype})")
    startingFps = float(get_value(["AcquisitionFrameRate", "AcquisitionFrameRateAbs"]))
    startingGain = float(get_value(["Gain", "GainRaw"]))
    startingExposure = float(get_value(["ExposureTime", "ExposureTimeAbs"]))
    fps_shm_name = derive_control_shm_name(camera_shm_name, "Fps")
    gain_shm_name = derive_control_shm_name(camera_shm_name, "Gain")
    dit_shm_name = derive_control_shm_name(camera_shm_name, "Dit")

    global camShm
    camShm = dao.shm(camera_shm_name, np.zeros((sensor_height, sensor_width), dtype=sensor_dtype))
    global camFpsShm
    camFpsShm = dao.shm(fps_shm_name, np.zeros((1,1), dtype=np.float32)+startingFps)
    global camGainShm
    camGainShm = dao.shm(gain_shm_name, np.zeros((1,1), dtype=np.float32)+startingGain)
    global camDitShm
    camDitShm = dao.shm(dit_shm_name, np.zeros((1,1), dtype=np.float32)+startingExposure)
    print("-" * 60)

    # --- Exposure ---
    print(f"Exposure Time:     {fmt(['ExposureTime', 'ExposureTimeAbs'], unit=' us')}")
    print(f"Exposure Mode:     {get_value(['ExposureMode'])}")
    print(f"Exposure Auto:     {get_value(['ExposureAuto'])}")

    print("-" * 60)

    # --- Gain ---
    print(f"Gain:              {fmt(['Gain', 'GainRaw'])}")
    print(f"Gain Auto:         {get_value(['GainAuto'])}")

    print("-" * 60)

    # --- Frame rate ---
    print(f"FPS Enable:        {get_value(['AcquisitionFrameRateEnable'])}")
    print(f"FPS (target):      {fmt(['AcquisitionFrameRate', 'AcquisitionFrameRateAbs'])}")
    print(f"FPS (resulting):   {get_value(['ResultingFrameRate', 'ResultingFrameRateAbs'])}")

    print("-" * 60)

    # --- Acquisition / trigger ---
    print(f"Acquisition Mode:  {get_value(['AcquisitionMode'])}")
    print(f"Trigger Mode:      {get_value(['TriggerMode'])}")
    print(f"Trigger Source:    {get_value(['TriggerSource'])}")

    print("-" * 60)

    # --- Misc useful info ---
    print(f"Black Level:       {fmt(['BlackLevel', 'BlackLevelRaw'])}")
    print(f"Device Temp (C):   {get_value(['DeviceTemperature', 'TemperatureAbs'])}")
    print(f"Link Throughput Limit: {fmt(['DeviceLinkThroughputLimit'])}")
    print(f"Current Throughput:    {get_value(['BslDeviceLinkCurrentThroughput', 'DeviceLinkCurrentThroughput'])}")

    print("=" * 60)

    return


def set_camera_parameter(camera, node_names, value, label=""):
    """!
    @brief Set a camera parameter by trying multiple node names.
    @param camera Opened pypylon camera object.
    @param node_names Ordered candidate node names.
    @param value Requested parameter value.
    @param label Optional label used in log output.
    @return `True` if a writable node was set, otherwise `False`.
    @details
    If supported by the selected node, value is clamped to `[min, max]`.
    """
    for name in node_names:
        node = getattr(camera, name, None)
        if node is None:
            continue
        try:
            if not (genicam.IsAvailable(node) and genicam.IsWritable(node)):
                continue

            # Clamp to valid range if the node supports it (float/int nodes do)
            try:
                min_val = node.GetMin()
                max_val = node.GetMax()
                if value < min_val or value > max_val:
                    print(f"[{label or name}] {value} out of range "
                          f"({min_val}-{max_val}), clamping.")
                    value = max(min_val, min(value, max_val))
            except Exception:
                pass  # enum/bool nodes don't have GetMin/GetMax

            node.SetValue(value)
            print(f"[{label or name}] set to {value}")
            return True
        except Exception as e:
            print(f"[{label or name}] failed to set via '{name}': {e}")
            continue

    print(f"[{label or node_names}] no writable node found, not set.")
    return False


def set_gain(camera, gain_value):
    """!
    @brief Set manual camera gain.
    @param camera Opened pypylon camera object.
    @param gain_value Gain value in camera units (often dB-like).
    """
    # Turn off auto-gain first, otherwise the manual value gets overridden
    gain_auto = getattr(camera, "GainAuto", None)
    if gain_auto is not None and genicam.IsWritable(gain_auto):
        gain_auto.SetValue("Off")

    set_camera_parameter(camera, ["Gain", "GainRaw"], gain_value, label="Gain")


def set_exposure_time(camera, exposure_us):
    """!
    @brief Set manual exposure/integration time.
    @param camera Opened pypylon camera object.
    @param exposure_us Exposure time in microseconds.
    """
    # Turn off auto-exposure first
    exposure_auto = getattr(camera, "ExposureAuto", None)
    if exposure_auto is not None and genicam.IsWritable(exposure_auto):
        exposure_auto.SetValue("Off")

    set_camera_parameter(
        camera, ["ExposureTime", "ExposureTimeAbs"], exposure_us, label="ExposureTime"
    )


def set_fps(camera, fps_value):
    """!
    @brief Set target camera frame rate.
    @param camera Opened pypylon camera object.
    @param fps_value Requested frames per second.
    """
    # Must explicitly enable frame rate control, otherwise the camera
    # ignores the target and just runs as fast as exposure/bandwidth allow
    fps_enable = getattr(camera, "AcquisitionFrameRateEnable", None)
    if fps_enable is not None and genicam.IsWritable(fps_enable):
        fps_enable.SetValue(True)

    set_camera_parameter(
        camera,
        ["AcquisitionFrameRate", "AcquisitionFrameRateAbs"],
        fps_value,
        label="FPS",
    )


def camera_receive_thread_function(camera):
    """!
    @brief Acquire frames continuously and publish to shared memory.
    @param camera Opened pypylon camera object.
    @details
    Runs until `camera_receive_thread_stop_event` is set or grabbing ends.
    """
    print("Camera receive thread: running")
    global camShm
    # Start continuous (free-running) acquisition
    camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)

    try:
        while not camera_receive_thread_stop_event.is_set():
            if not camera.IsGrabbing():
                break

            try:
                grab_result = camera.RetrieveResult(
                    1000, pylon.TimeoutHandling_Return
                )
            except Exception as e:
                print(f"Receive thread: retrieve error: {e}")
                continue

            if grab_result is None:
                # Timeout with no frame — loop again and check stop event
                continue

            with grab_result:
                if grab_result.GrabSucceeded():
                    # Write to shared memory
                    camShm.set_data(grab_result.Array)
                else:
                    print(
                        "Receive thread: grab failed:",
                        f"{grab_result.ErrorCode:#x}",
                        grab_result.ErrorDescription,
                    )

    finally:
        if camera.IsGrabbing():
            camera.StopGrabbing()
        print("Camera receive thread: stopped grabbing")


def camera_control_thread_function(camera):
    """!
    @brief Monitor control shared memory and apply camera parameter updates.
    @param camera Opened pypylon camera object.
    @details
    Watches counters for FPS, gain, and exposure buffers and pushes updated
    values to camera nodes when changes are detected.
    """
    print("Camera control thread: running")
    global camFpsShm, camGainShm, camDitShm
    
    fpsCounter = camFpsShm.get_counter()
    gainCounter = camGainShm.get_counter()
    DITCounter = camDitShm.get_counter()
    while not camera_control_thread_stop_event.is_set():
        # check FPS
        if camFpsShm.get_counter() != fpsCounter:
            fpsCounter = camFpsShm.get_counter()
            new_fps = float(camFpsShm.get_data()[0,0])
            print(f"Camera control thread: setting FPS to {new_fps}")
            set_fps(camera, new_fps)
        # check exposure
        if camDitShm.get_counter() != DITCounter:
            DITCounter = camDitShm.get_counter()
            new_exposure = float(camDitShm.get_data()[0,0])
            print(f"Camera control thread: setting exposure to {new_exposure}")
            set_exposure_time(camera, new_exposure)
        # check gain
        if camGainShm.get_counter() != gainCounter:
            gainCounter = camGainShm.get_counter()
            new_gain = float(camGainShm.get_data()[0,0])
            print(f"Camera control thread: setting gain to {new_gain}")
            set_gain(camera, new_gain)

        time.sleep(1)


def start_camera_receive_thread(camera):
    """!
    @brief Start the camera receive worker thread.
    @param camera Opened pypylon camera object.
    @return Thread handle for the receive worker.
    """
    print("Main: Starting camera receive thread...")
    camera_receive_thread_stop_event.clear()
    t1 = threading.Thread(target=camera_receive_thread_function, args=(camera,), daemon=True)
    t1.start()
    return t1


def start_camera_control_thread(camera):
    """!
    @brief Start the camera control worker thread.
    @param camera Opened pypylon camera object.
    @return Thread handle for the control worker.
    """
    print("Main: Starting camera control thread...")
    camera_control_thread_stop_event.clear()
    t2 = threading.Thread(target=camera_control_thread_function, args=(camera,), daemon=True)
    t2.start()
    return t2


def stop_camera_receive_thread(thread=None):
    """!
    @brief Signal the receive thread to stop and optionally join it.
    @param thread Optional thread handle returned by start function.
    """
    print("Main: Stopping camera receive thread...")
    camera_receive_thread_stop_event.set()
    if thread is not None:
        thread.join()
        print("Main: Camera receive thread stopped.")


def stop_camera_control_thread(thread=None):
    """!
    @brief Signal the control thread to stop and optionally join it.
    @param thread Optional thread handle returned by start function.
    """
    print("Main: Stopping camera control thread...")
    camera_control_thread_stop_event.set()
    if thread is not None:
        thread.join()
        print("Main: Camera control thread stopped.")


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Basler Ace camera shared-memory interface")
    parser.add_argument(
        "--camera-shm",
        default="/tmp/camera.im.shm",
        help="Camera image shm filename (control shm names are auto-derived with Fps/Gain/Dit suffixes).",
    )
    args = parser.parse_args()

    print("Main: opening camera...")
    with pylon.InstantCamera(pylon.FirstFound) as camera:
        print("Using device:", camera.DeviceInfo.ModelName)
        
        # print camera details
        get_camera_details(camera, camera_shm_name=args.camera_shm)

        t1 = start_camera_receive_thread(camera)
        t2 = start_camera_control_thread(camera)

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            stop_camera_receive_thread(t1)
            stop_camera_control_thread(t2)
            camera.Close()
