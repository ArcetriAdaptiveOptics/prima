#!/usr/bin/env python3
#
import dao
import numpy as np
# import astropy.io.fits as fits
# import matplotlib.pyplot as plt
import time
import sys
import os
import daoEkarusShmNames as shmNames
from ekalib import create_tracking_number
from ekarus_telemetry_keys import EkarusTelemetryKeys as etk
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import Qt
from GUIUtils import style_messagebox_alert

nData = int(sys.argv[1])
nData_cblue = int(sys.argv[2])
nData_orca = int(sys.argv[2])
data_list_str = sys.argv[3] # input is a unique str delimited by comas ','
data_list = data_list_str.split(",")  # Parse back to list
tracking_number = sys.argv[4] # input is a unique str delimited by comas ','

# DM COMMANDS
dm1_cmd_offset = dao.shm(shmNames.SHM_DM1_CMD_OFFSET)
dm1_channel_0 = dao.shm(shmNames.SHM_DM1_CHANNEL_0) # static offset (DM flat)
dm1_channel_1 = dao.shm(shmNames.SHM_DM1_CHANNEL_1) # Commands computed from WFS slopes
dm1_channel_2 = dao.shm(shmNames.SHM_DM1_CHANNEL_2) # offset 1 => used for intMat calib
dm1_channel_3 = dao.shm(shmNames.SHM_DM1_CHANNEL_3) # offset 2 => used for valid pixel selection
dm1_cmd = dao.shm(shmNames.SHM_DM1_CMD) # sum of all channels

# LOOP DATA
wfs1_reconstructed_modes = dao.shm(shmNames.SHM_WFS1_RECONSTRUCTED_MODES) # => reconstructed modal coefficients
pyramid_2_dm1_rec = dao.shm(shmNames.SHM_PYRAMID_2_DM1_REC)
dm1_m2c = dao.shm(shmNames.SHM_DM1_M2C)
dm1_loop_gain = dao.shm(shmNames.SHM_DM1_LOOP_GAIN)
dm1_loop_leak = dao.shm(shmNames.SHM_DM1_LOOP_LEAK)
dm1_loop_cl_switch = dao.shm(shmNames.SHM_DM1_LOOP_CL_SWITCH) # flag for open or closed loop

# FAST TT 
pyramid_pupil_flux = dao.shm(shmNames.SHM_PYRAMID_PUPIL_FLUX)
fasttt_loop_cl_switch = dao.shm(shmNames.SHM_FASTTT_LOOP_CL_SWITCH)
fasttt_loop_leak = dao.shm(shmNames.SHM_FASTTT_LOOP_LEAK)
fasttt_loop_gain = dao.shm(shmNames.SHM_FASTTT_LOOP_GAIN)
fasttt_cmd = dao.shm(shmNames.SHM_FASTTT_CMD)
pyramid_flux_2_fasttt_rec = dao.shm(shmNames.SHM_PYRAMID_FLUX_2_FASTTT_REC)
fasttt_residual_tt_offload = dao.shm(shmNames.SHM_FASTTT_RESIDUAL_TT_OFFLOAD)
dm_2_fasttt_offload_toggle = dao.shm(shmNames.SHM_DM_2_FASTTT_OFFLOAD_TOGGLE)
fasttt_residual_tt = dao.shm(shmNames.SHM_FASTTT_RESIDUAL_TT)

# PYRAMID
modulator = dao.shm(shmNames.SHM_MODULATOR)
ocam_gain = dao.shm(shmNames.SHM_OCAM_GAIN)
ocam_fps = dao.shm(shmNames.SHM_OCAM_FPS)
ocam_temperature = dao.shm(shmNames.SHM_OCAM_TEMPERATURE)
pyramid_signal = dao.shm(shmNames.SHM_PYRAMID_SIGNAL)
ocam_frame = dao.shm(shmNames.SHM_OCAM_FRAME)
ocam_background = dao.shm(shmNames.SHM_OCAM_BACKGROUND)
ocam_flat_field = dao.shm(shmNames.SHM_OCAM_FLAT_FIELD)
pyramid_valid_pixels = dao.shm(shmNames.SHM_PYRAMID_VALID_PIXELS)
ocam_reference = dao.shm(shmNames.SHM_OCAM_REFERENCE)

# TELESCOPE DATA
telescope_offset = dao.shm(shmNames.SHM_TELESCOPE_OFFSET)
telescope_guiding = dao.shm(shmNames.SHM_TELESCOPE_GUIDING)
telescope_radec = dao.shm(shmNames.SHM_TELESCOPE_RADEC)

# CLOSED LOOP DATA
ocam_frame_cube = np.zeros((nData, ocam_frame.get_data().shape[0], ocam_frame.get_data().shape[1])).astype(np.float32)
ocam_counter = np.zeros(nData).astype(np.uint64)
dm1_cmd_cube = np.zeros((nData, dm1_cmd.get_data().shape[0], dm1_cmd.get_data().shape[1])).astype(np.float32)
dm1_cmd_counter = np.zeros(nData).astype(np.uint64)
wfs1_modes_cube = np.zeros((nData, wfs1_reconstructed_modes.get_data().shape[0], wfs1_reconstructed_modes.get_data().shape[1])).astype(np.float32)
fasttt_cmd_cube = np.zeros((nData, fasttt_cmd.get_data().shape[0], fasttt_cmd.get_data().shape[1])).astype(np.float32)
telescope_offset_cube = np.zeros((nData, telescope_offset.get_data().shape[0], telescope_offset.get_data().shape[1])).astype(np.float32)
telescope_guiding_cube = np.zeros((nData, telescope_guiding.get_data().shape[0], telescope_guiding.get_data().shape[1])).astype(np.float32)
telescope_radec_cube = np.zeros((nData, telescope_radec.get_data().shape[0], telescope_radec.get_data().shape[1])).astype(np.float32)
pyramid_signals_cube = np.zeros((nData, pyramid_signal.get_data().shape[0], pyramid_signal.get_data().shape[1])).astype(np.float32)
dm1_channel_0_cube = np.zeros((nData, dm1_channel_0.get_data().shape[0], dm1_channel_0.get_data().shape[1])).astype(np.float32)
dm1_channel_1_cube = np.zeros((nData, dm1_channel_1.get_data().shape[0], dm1_channel_1.get_data().shape[1])).astype(np.float32)
dm1_channel_2_cube = np.zeros((nData, dm1_channel_2.get_data().shape[0], dm1_channel_2.get_data().shape[1])).astype(np.float32)
dm1_channel_3_cube = np.zeros((nData, dm1_channel_3.get_data().shape[0], dm1_channel_3.get_data().shape[1])).astype(np.float32)

time_stamp_dm_cube = []
time_stamp_ocam_cube = []
if "loop_data" in data_list or "wfs_intensity" in data_list or "dm_channels" in data_list or "ocam_frames" in data_list:
    for k in range(nData):
        dm1_cmd_cube[k, :, :] = dm1_cmd.get_data(check=True, semNb=8)
        dm1_channel_1_cube[k, :, :] = dm1_channel_1.get_data()
        dm1_channel_0_cube[k, :, :] = dm1_channel_0.get_data()
        dm1_channel_2_cube[k, :, :] = dm1_channel_2.get_data()
        dm1_channel_3_cube[k, :, :] = dm1_channel_3.get_data()
        pyramid_signals_cube[k, :, :] = pyramid_signal.get_data()
        fasttt_cmd_cube[k,:,:] = fasttt_cmd.get_data()
        ocam_frame_cube[k, :, :] = ocam_frame.get_data()
        wfs1_modes_cube[k, :, :] = wfs1_reconstructed_modes.get_data()
        telescope_offset_cube[k,:,:] = telescope_offset.get_data()
        telescope_guiding_cube[k,:,:] = telescope_guiding.get_data()
        telescope_radec_cube[k,:,:] = telescope_radec.get_data()

        # timestamps
        time_stamp_ocam_cube.append(ocam_frame.get_timestamp())
        time_stamp_dm_cube.append(dm1_cmd.get_timestamp())

# Check if the loop is open (all values are 0)
dm1_cmd_data = dm1_cmd.get_data()
if (dm1_cmd_data == 0).all():
    loop_status = "OL"  # Open Loop
else:
    loop_status = "CL"  # Closed Loop

if "cblue_data" in data_list:
    cblue_frame = dao.shm(shmNames.SHM_CBLUE_FRAME)  # Frame
    cblue_background = dao.shm(shmNames.SHM_CBLUE_BACKGROUND)  # Background
    cblue_fps = dao.shm(shmNames.SHM_CBLUE_FPS)  # Fps
    cblue_dit = dao.shm(shmNames.SHM_CBLUE_DIT)  # Integration
    cblue_gain = dao.shm(shmNames.SHM_CBLUE_GAIN)  # Gain analog in dB
    cblue_temperature = dao.shm(shmNames.SHM_CBLUE_TEMP)  # Temperature in °C
    cblue_conv_efficiency = dao.shm(shmNames.SHM_CBLUE_CONV_EFFICIENCY)  # Conversion Efficiency (0 = Low, 1 = High)

    cblue_cube = np.zeros((nData_cblue, cblue_frame.get_data().shape[0], cblue_frame.get_data().shape[1])).astype(np.float32)
    time_stamp_cblue = []

    for k in range(nData_cblue):
            cblue_cube[k, :, :] = cblue_frame.get_data(check=True, semNb=8)
            time_stamp_cblue.append(cblue_frame.get_timestamp())

    roi_file = os.path.join(os.getenv("DAODATA"), "inputs", "cblue_roi.txt")
    roi = {}
    with open(roi_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            roi[key.strip()] = int(value.strip())

    w = roi['width']
    cy = roi['cy'] - w // 2
    cx = roi['cx'] - w // 2
    cblue_roi_vector = [w, cy, cx]

    cblue_data = {
        etk.CBLUE_CUBE: cblue_cube[:, cy:cy + w, cx:cx + w], # data_cube of the CBLUE cropped to the current ROI
        etk.CBLUE_BACKGROUND: cblue_background.get_data()[cy:cy + w, cx:cx + w], # CBLUE background cropped to ROI
        etk.CBLUE_FULL_BACKGROUND: cblue_background.get_data(), # CBLUE background (full frame)
        etk.CBLUE_FPS: cblue_fps.get_data()[0, 0], # CBLUE framerate
        etk.CBLUE_DIT: cblue_dit.get_data()[0, 0], # CBLUE exposure time (s)
        etk.CBLUE_GAIN: cblue_gain.get_data()[0, 0], # CBLUE Gain
        etk.CBLUE_TEMPERATURE: cblue_temperature.get_data()[0, 0], # CBLUE temperature
        etk.CBLUE_CONVERSION_EFFICIENCY: cblue_conv_efficiency.get_data()[0, 0], # CBLUE conversion efficiency factor
        etk.CBLUE_TIMESTAMP: time_stamp_cblue, # CBLUE timestamps
        etk.MODULATOR_FREQUENCY: modulator.get_data()[0, 0], # TT modulator frequency
        etk.MODULATOR_RADIUS: modulator.get_data()[1, 0], # TT modulator radius
        etk.MODULATOR_ON_OFF: modulator.get_data()[4, 0], # TT modulator flag
        etk.LOOP_STATUS: loop_status, # Closed-loop flag
        etk.CBLUE_ROI_VECTOR: cblue_roi_vector, # values of the CBLUE ROI [width, cy, cx]
    }
else: 
    cblue_data = []


if "orca_data" in data_list:
    orca_frame = dao.shm(shmNames.SHM_ORCA_FRAME)  # Frame
    orca_background = dao.shm(shmNames.SHM_ORCA_BACKGROUND)  # Background
    orca_fps = dao.shm(shmNames.SHM_ORCA_FPS)  # Fps
    orca_dit = dao.shm(shmNames.SHM_ORCA_DIT)  # Integration
    orca_temperature = dao.shm(shmNames.SHM_ORCA_TEMP)  # Temperature in °C
    orca_roi = dao.shm(shmNames.SHM_ORCA_ROI)

    orca_cube = np.zeros((nData_orca, orca_frame.get_data().shape[0], orca_frame.get_data().shape[1])).astype(np.float32)
    time_stamp_orca = []

    for k in range(nData_orca):
            orca_cube[k, :, :] = orca_frame.get_data(check=True, semNb=8)
            time_stamp_orca.append(orca_frame.get_timestamp())
    orca_data = {
        etk.ORCA_CUBE: orca_cube, # data_cube of the CBLUE cropped to the current ROI
        etk.ORCA_BACKGROUND: orca_background.get_data(), # CBLUE background cropped to ROI
        etk.ORCA_FULL_BACKGROUND: orca_background.get_data(), # CBLUE background (full frame)
        etk.ORCA_FPS: orca_fps.get_data()[0, 0], # CBLUE framerate
        etk.ORCA_DIT: orca_dit.get_data()[0, 0], # CBLUE exposure time (s)
        # "orcaGain": orca_gain.get_data()[0, 0], # CBLUE Gain
        etk.ORCA_TEMPERATURE: orca_temperature.get_data()[0, 0], # CBLUE temperature
        # "orcaConvEfficiency": orca_conv_efficiency.get_data()[0, 0], # CBLUE conversion efficiency factor
        etk.ORCA_TIMESTAMP: time_stamp_orca, # CBLUE timestamps
        etk.LOOP_STATUS: loop_status, # Closed-loop flag
        # etk.ORCA_ROI_VECTOR: orca_roi.get_data(), # values of the ORCA ROI [width, cy, cx]
        }
else:
    orca_data = []

# Check if the loop is open (all values are 0)
dm1_cmd_data = dm1_cmd.get_data()
if (dm1_cmd_data == 0).all():
    loop_status = "OL"  # Open Loop
else:
    loop_status = "CL"  # Closed Loop
# TODO 20260723 - lbusoni
# are these all the available telemetry loop_data? Are we missing some? 
# - ekarus selector - pupil stabilizer position and angle => no not yet communicating with the RTC

# specific data (not always necessary)
dm_channels = {
    etk.DM_CHANNEL_0_CUBE: dm1_channel_0_cube,  # flat DM command
    etk.DM_CHANNEL_1_CUBE: dm1_channel_1_cube,  # command sent to the DM by the closed loop
    etk.DM_CHANNEL_2_CUBE: dm1_channel_2_cube,  # DM turbulence
    etk.DM_CHANNEL_3_CUBE: dm1_channel_3_cube,  # DM command offset
    } 

wfs_intensity = {
    etk.WFS1_SIGNALS_CUBE: pyramid_signals_cube # Reduced intensities from WFS 1 (Bg substracted, flux normalized)
    }

ocam_frames = {
    etk.OCAM_CUBE: ocam_frame_cube, # Full cube of OCAM frames
    etk.OCAM_TIMESTAMP_CUBE: time_stamp_ocam_cube, # timestamps of the ocam frames
    }

# TODO: add fast TT position and telescope RA, DEC !!!

# general data of the loop status and parameters
loop_data = {
    # Fast Tip Tilt
    etk.FAST_TT_COMMANDS_CUBE: fasttt_cmd_cube,
    etk.FAST_TT_RECONSTRUCTOR: pyramid_flux_2_fasttt_rec.get_data(),
    etk.FAST_TT_CLOSED_LOOP: fasttt_loop_cl_switch.get_data(),
    etk.FAST_TT_LOOP_GAIN: fasttt_loop_gain.get_data(),
    etk.FAST_TT_LOOP_LEAK: fasttt_loop_leak.get_data(),

    # OCAM data
    etk.OCAM_DARK: ocam_background.get_data().reshape(240, 240),
    etk.OCAM_GAIN: ocam_gain.get_data()[0, 0],
    etk.OCAM_FPS: ocam_fps.get_data()[0, 0],
    etk.OCAM_TEMPERATURE: ocam_temperature.get_data()[0, 0],
    etk.MEAN_OCAM_FRAME: np.mean(ocam_frame_cube, axis=0),
    # DM data
    etk.DM_OFFSET: dm1_cmd_offset.get_data(),
    etk.DM_CMD_CUBE: dm1_cmd_cube,    # sum of DM command channels
    etk.DM_TIMESTAMP_CUBE: time_stamp_dm_cube, # timestamps of the DM commands

    # TT modulation
    etk.MODULATOR_FREQUENCY: modulator.get_data()[0, 0],
    etk.MODULATOR_RADIUS: modulator.get_data()[1, 0],
    etk.MODULATOR_ON_OFF: modulator.get_data()[4, 0],

    # Loop data
    etk.LP_GAIN: dm1_loop_gain.get_data(), # loop gain
    etk.LP_LEAK: dm1_loop_leak.get_data(), # leak value
    etk.MODE_CUBE: wfs1_modes_cube, # modal coefficients
    etk.CLOSED_LOOP_STATUS: dm1_loop_cl_switch.get_data(), # flag for open/closed loop

    # Telescope data
    etk.TELESCOPE_OFFSET_CUBE: telescope_offset_cube,    # sum of DM command channels
    etk.TELESCOPE_GUIDING_CUBE: telescope_guiding_cube,    # sum of DM command channels
    etk.TELESCOPE_RADEC_CUBE: telescope_radec_cube,    # sum of DM command channels

    # Calibration data
    etk.OCAM_FLAT: ocam_flat_field.get_data(), # flat map of the OCAM
    etk.VALID_PIXELS: pyramid_valid_pixels.get_data(), # map of valid pixels
    etk.REF: ocam_reference.get_data().reshape(240, 240), # reference substracted to the OCAM frames
    etk.S2M: pyramid_2_dm1_rec.get_data(), # pyramid signals-to-modes reconstruction matrix
    etk.M2C: dm1_m2c.get_data(), # modes-to-command matrix
}


# list of potential objects to be saved
data_objects = {
    "dm_channels": dm_channels,
    "wfs_intensity": wfs_intensity,
    "ocam_frames": ocam_frames,
    "loop_data": loop_data,
    "cblue_data": cblue_data,
    "orca_data": orca_data,
}

for i_file in data_list:
    if i_file in data_objects:
        folder_path = create_tracking_number(name_data=i_file,
                                             data=data_objects[i_file],
                                             tracking_number=tracking_number)
        with open(os.getenv("DAODATA") + "/telemetry/tmp/current_telemetry_folder.txt", "w") as f:
            f.write(folder_path)
            f.close()
# display a warning if the orca frames were saturating
if np.max(orca_cube) > 65400:
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        
        msg_box = QMessageBox()
        msg_box.setWindowTitle("ORCA Camera Warning")
        msg_box.setText("The last ORCA Frames recorded were saturated!: TN# "+ tracking_number)
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setWindowFlags(msg_box.windowFlags() | Qt.WindowStaysOnTopHint)  # Keep on top
        style_messagebox_alert(msg_box)  # Apply GUIUtils styling
        msg_box.exec_()
