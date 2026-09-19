#!/usr/bin/env python3
#
import dao
import numpy as np
import time
import sys
import os
from daoEkarusShmNames import *
from ekalib import create_tracking_number


def telemetry_save(nData):
    cam = dao.shm(SHM_CBLUE_FRAME)  # Frame
    cbbg = dao.shm(SHM_CBLUE_BACKGROUND)  # Background
    cbfps = dao.shm(SHM_CBLUE_FPS)  # Fps
    cbdit = dao.shm(SHM_CBLUE_DIT)  # Integration
    cam_gain = dao.shm(SHM_CBLUE_GAIN)  # Gain analog in dB
    cam_temp = dao.shm(SHM_CBLUE_TEMP)  # Temperature in °C
    cam_conv_eff = dao.shm(SHM_CBLUE_CONV_EFFICIENCY)  # Conversion Efficiency (0 = Low, 1 = High)
    # Modulator
    modulator = dao.shm(SHM_MODULATOR)

    camCube = np.zeros((nData, cam.get_data().shape[0], cam.get_data().shape[1])).astype(np.float32)
    timeStampCblue = []

    for k in range(nData):
        camCube[k, :, :] = cam.get_data(check=True, semNb=8)
        timeStampCblue.append(cam.get_timestamp())
    
    lpCmd = dao.shm(SHM_DM1_CMD)
    data = lpCmd.get_data()
    # check if the loop is open (all values are 0)
    if (data == 0).all():
        LoopStatus = "OL"  # Open Loop
    else:
        LoopStatus = "CL"  # Closed Loop

    roi_file = os.path.join(os.getenv("DAODATA"), "inputs", "cblue_roi.txt")
    roi = {}
    with open(roi_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            roi[key.strip()] = int(value.strip())

    """Crop a frame to the ROI. cx is a column index, cy a row index."""
    w = roi['width']
    r0 = roi['cy'] - w // 2
    c0 = roi['cx'] - w // 2

    # # clamp so the window stays inside the frame
    # r0 = max(0, min(r0, frame.shape[0] - w))
    # c0 = max(0, min(c0, frame.shape[1] - w))

    cblue_data = {
        "cblueCube": camCube[:,r0:r0 + w, c0:c0 + w],
        "cblueBg": cbbg.get_data()[r0:r0 + w, c0:c0 + w],
        "cblueBg_no_ROI": cbbg.get_data(),
        "cblueFps": cbfps.get_data()[0, 0],
        "cblueDIT": cbdit.get_data()[0, 0],
        "cblueGain": cam_gain.get_data()[0, 0],
        "cblueTemp": cam_temp.get_data()[0, 0],
        "cblueConvEfficiency": cam_conv_eff.get_data()[0, 0],
        "timeStampDmCube": timeStampCblue,
        "modulatorFrequency": modulator.get_data()[0, 0],
        "modulatorRadius": modulator.get_data()[1, 0],
        "modulatorOn-Off": modulator.get_data()[4, 0],
        "LoopStatus": LoopStatus,
    }

    data_objects = {
        "cblue_data": cblue_data}

    for i_file in data_objects:
        folder_path = create_tracking_number(name_data=i_file,data = data_objects[i_file])

if __name__ == "__main__":
    import sys

    if sys.argv[1:]:
        n_frames = int(sys.argv[1])
    else:
        n_frames = 1000
    n_frames = int(sys.argv[1])
    telemetry_save(n_frames)
