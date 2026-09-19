#!/usr/bin/env python3
#

import dao
import os
import numpy as np
import daoEkarusShmNames as shm_names 
# import astropy.io.fits as fits
ocamSize = 240
ocamRawSizeX = 1056
ocamRawSizeY = 121

nCentroids = 6000 # number of pixels to extract and normalise from the OCAM frame, maximum number of valid pixels allowed in the pyramid pupil

print("Creating SHM for Ocam raw frame")
imunscr = dao.shm(shm_names.SHM_OCAM_RAW_FRAME, np.zeros((ocamRawSizeX, ocamRawSizeY)).astype(np.uint8))
imunscrAcq = dao.shm(shm_names.SHM_OCAM_RAW_ACQ, np.zeros((1, 1)).astype(np.uint32))
# dit = dao.shm(shm_names.SHM_OCAM_DIT, np.ones((1, 1)).astype(np.float32))
# fps = dao.shm(shm_names.SHM_OCAM_RAW_FPS, np.ones((1, 1)).astype(np.float32))
imscr = dao.shm(shm_names.SHM_OCAM_FRAME, np.zeros((ocamSize, ocamSize)).astype(np.uint16))
shmOcam2gain = dao.shm(shm_names.SHM_OCAM_GAIN, np.zeros((1, 1)).astype(np.uint32))
shmOcam2fps = dao.shm(shm_names.SHM_OCAM_FPS, np.zeros((1, 1)).astype(np.uint32))
shmOcam2temp = dao.shm(shm_names.SHM_OCAM_TEMPERATURE, np.zeros((1, 1)).astype(np.float32))

bg = np.load(os.getenv("DAODATA") + "/inputs/calibration/Dark.npy").astype(np.float32)
bg = dao.shm(shm_names.SHM_OCAM_BACKGROUND, bg)
ff = dao.shm(shm_names.SHM_OCAM_FLAT_FIELD, np.ones((ocamSize, ocamSize)).astype(np.float32))
imcal = dao.shm(shm_names.SHM_OCAM_REDUCED_FRAME, np.zeros((ocamSize, ocamSize)).astype(np.float32))
imref = dao.shm(shm_names.SHM_OCAM_REFERENCE, np.zeros((ocamSize, ocamSize)).astype(np.float32))
imrefnormflux = dao.shm(shm_names.SHM_OCAM_REFERENCE_FLUX, np.ones((1,1)).astype(np.float32))
valid_mask_std = dao.shm(shm_names.SHM_PYRAMID_VALID_PIXELS_STD, np.ones((ocamSize, ocamSize)).astype(np.float32))

extractedPixels = dao.shm(shm_names.SHM_PYRAMID_SIGNAL, np.zeros((nCentroids, 1)).astype(np.float32))
pupil_relative_illuminations = dao.shm(shm_names.SHM_PYRAMID_PUPIL_FLUX, np.ones((4,1)).astype(np.float32))
pupil_centers = dao.shm(shm_names.SHM_PYRAMID_PUPIL_CENTERS, np.ones((2,1)).astype(np.float32))

timeDesc = dao.shm(shm_names.SHM_OCAM_DESCRAMBLE_TIME, np.zeros((1, 1)).astype(np.float32))
timeDescAvg = dao.shm(shm_names.SHM_OCAM_DESCRAMBLE_TIME_AVG, np.zeros((1, 1)).astype(np.float32))
timeDescRms = dao.shm(shm_names.SHM_OCAM_DESCRAMBLE_TIME_RMS, np.zeros((1, 1)).astype(np.float32))

# shmOcam2gain = dao.shm(shm_names.SHM_OCAM_GAIN, np.zeros((1, 1)).astype(np.uint32))
# shmOcam2fps = dao.shm(shm_names.SHM_OCAM_FPS, np.zeros((1, 1)).astype(np.uint32))
# shmOcam2temp = dao.shm(shm_names.SHM_OCAM_TEMP, np.zeros((1, 1)).astype(np.float32))

# Optical gain
cbim = dao.shm(shm_names.SHM_CBLUE_FRAME, np.zeros((624, 816)).astype(np.uint16))
cbima = dao.shm(shm_names.SHM_CBLUE_ACQ, np.zeros((1, 1)).astype(np.uint32))
cbdit = dao.shm(shm_names.SHM_CBLUE_DIT, np.ones((1, 1)).astype(np.float32))
cbfps = dao.shm(shm_names.SHM_CBLUE_FPS, np.ones((1, 1)).astype(np.float32))
cbGain = dao.shm(shm_names.SHM_CBLUE_GAIN, np.ones((1, 1)).astype(np.float32))
cbbg = dao.shm(shm_names.SHM_CBLUE_BACKGROUND, np.zeros((624, 816)).astype(np.float32))
cbff = dao.shm(shm_names.SHM_CBLUE_FLAT_FIELD, np.ones((624, 816)).astype(np.float32))
cbimcal = dao.shm(shm_names.SHM_CBLUE_REFERENCE, np.zeros((624, 816)).astype(np.float32))
ogCmd = dao.shm(shm_names.SHM_CBLUE_OG_CMD, np.zeros((1, 1)).astype(np.uint32))


# dm1 loop ctrl
lpCmd = dao.shm(shm_names.SHM_DM1_LOOP_CL_SWITCH, np.zeros((1, 1)).astype(np.uint32))
lpLeak = dao.shm(shm_names.SHM_DM1_LOOP_LEAK, np.ones((1, 1)).astype(np.float32))
lpGain = dao.shm(shm_names.SHM_DM1_LOOP_GAIN, np.zeros((1, 1)).astype(np.float32))

# fast TT loop ctrl
lpCmdFastTT = dao.shm(shm_names.SHM_FASTTT_LOOP_CL_SWITCH, np.zeros((1, 1)).astype(np.uint32))
lpLeakFastTT = dao.shm(shm_names.SHM_FASTTT_LOOP_LEAK, np.ones((1, 1)).astype(np.float32))
lpGainFastTT = dao.shm(shm_names.SHM_FASTTT_LOOP_GAIN, (0.1 * np.ones((1, 1))).astype(np.float32))


dm468Map = np.array([
    [0,0,0,0,0,0,0,0,1,1,1,1,1,1,1,1,0,0,0,0,0,0,0,0],
    [0,0,0,0,0,0,1,1,1,1,1,1,1,1,1,1,1,1,0,0,0,0,0,0],
    [0,0,0,0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0,0,0,0],
    [0,0,0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0,0,0],
    [0,0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0,0],
    [0,0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0,0],
    [0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0],
    [0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0],
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    [0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0],
    [0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0],
    [0,0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0,0],
    [0,0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0,0],
    [0,0,0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0,0,0],
    [0,0,0,0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0,0,0,0],
    [0,0,0,0,0,0,1,1,1,1,1,1,1,1,1,1,1,1,0,0,0,0,0,0],
    [0,0,0,0,0,0,0,0,1,1,1,1,1,1,1,1,0,0,0,0,0,0,0,0]
 ]
)

n_act_dm1 = int(dm468Map.sum())

dm468Mask = dao.shm(shm_names.SHM_DM1_468_MASK, dm468Map.astype(np.uint32))
# create DM channels
dm1ResWf = dao.shm(shm_names.SHM_DM1_RESIDUAL_ZONAL_COMMANDS, np.zeros((n_act_dm1, 1)).astype(np.float32))
dm1CmdOffset = dao.shm(shm_names.SHM_DM1_CMD_OFFSET, np.zeros((n_act_dm1, 1)).astype(np.float32))
dm1Cmd0 = dao.shm(shm_names.SHM_DM1_CHANNEL_0, np.zeros((n_act_dm1, 1)).astype(np.float32))
dm1Cmd1 = dao.shm(shm_names.SHM_DM1_CHANNEL_1, np.zeros((n_act_dm1, 1)).astype(np.float32))
dm1Cmd2 = dao.shm(shm_names.SHM_DM1_CHANNEL_2, np.zeros((n_act_dm1, 1)).astype(np.float32))
dm1Cmd3 = dao.shm(shm_names.SHM_DM1_CHANNEL_3, np.zeros((n_act_dm1, 1)).astype(np.float32))
dm1Cmd = dao.shm(shm_names.SHM_DM1_CMD, np.zeros((n_act_dm1, 1)).astype(np.float32))

with open(os.getenv("DAODATA") + "/inputs/dm468/current_m2c.txt") as f:
    m2c_path = f.read().strip()
dm1m2c = np.load(m2c_path).astype(np.float32)
n_modes = dm1m2c.shape[1]

# NCPA
ncpaFrameOffset = dao.shm(shm_names.SHM_OCAM_REFERENCE_BEFORE_NCPA_OFFSET, np.zeros((ocamSize,ocamSize)).astype(np.float32))

# DAO requires a full matrix nact x nact
m2c = np.zeros((n_act_dm1,n_act_dm1)).astype(np.float32)
m2c[:, : n_modes] = np.load(m2c_path).astype(np.float32)
dm1m2c = dao.shm(shm_names.SHM_DM1_M2C, m2c)

c2m = np.zeros((n_act_dm1,n_act_dm1)).astype(np.float32)
c2m[: n_modes,:] = np.linalg.pinv(m2c[:,:n_modes]).astype(np.float32)
dm1c2z = dao.shm(shm_names.SHM_DM1_C2M,c2m)

wfs1modes = dao.shm(shm_names.SHM_WFS1_RECONSTRUCTED_MODES, np.zeros((n_act_dm1, 1)).astype(np.float32))
wfs1modesGain = dao.shm(shm_names.SHM_WFS1_RECONSTRUCTED_MODES_GAIN, np.ones((n_act_dm1, 1)).astype(np.float32))
wfs1modesWithGain = dao.shm(shm_names.SHM_WFS1_RECONSTRUCTED_MODES_WITH_GAIN, np.zeros((n_act_dm1, 1)).astype(np.float32))

modShm = dao.shm(shm_names.SHM_MODULATOR, np.zeros((5, 1)).astype(np.float32))
fastTtShm = dao.shm(shm_names.SHM_FASTTT_RESIDUAL_TT, np.zeros((2, 1)).astype(np.float32))
fastTtShm = dao.shm(shm_names.SHM_FASTTT_RESIDUAL_TT_OFFLOAD, np.zeros((2, 1)).astype(np.float32))
fastTtShm = dao.shm(shm_names.SHM_FASTTT_CMD, np.zeros((2, 1)).astype(np.float32))
fastTtRef = np.load(os.getenv("DAODATA") + "/inputs/fasttt/RefPos.npy")
fastTtShm0 = dao.shm(shm_names.SHM_FASTTT_CHANNEL_0, fastTtRef.astype(np.float32))
fastTtShm1 = dao.shm(shm_names.SHM_FASTTT_CHANNEL_1, np.zeros((2, 1)).astype(np.float32))
fastTtShm2 = dao.shm(shm_names.SHM_FASTTT_CHANNEL_2, np.zeros((2, 1)).astype(np.float32))
oopao_mode = dao.shm(shm_names.SHM_OOPAO_MODE, np.zeros((1, 1)).astype(np.uint32))  # SHM for the oopao simulated mode

## Telescope control (TCS / ICS interface)
telOffsetShm = dao.shm(shm_names.SHM_TELESCOPE_OFFSET, np.zeros((2, 1)).astype(np.float32))
telGuidingShm = dao.shm(shm_names.SHM_TELESCOPE_GUIDING, np.zeros((2, 1)).astype(np.float32))
telRaDecShm = dao.shm(shm_names.SHM_TELESCOPE_RADEC, np.zeros((2, 1)).astype(np.float32))
telAltAzShm = dao.shm(shm_names.SHM_TELESCOPE_ALTAZ, np.zeros((3, 1)).astype(np.float32))
telStatusShm = dao.shm(shm_names.SHM_TELESCOPE_STATUS, np.zeros((5, 1)).astype(np.float32))
telAirmassShm = dao.shm(shm_names.SHM_TELESCOPE_AIRMASS, np.zeros((1, 1)).astype(np.float32))
telFocusShm = dao.shm(shm_names.SHM_TELESCOPE_FOCUS, np.zeros((1, 1)).astype(np.float32))
telDomeShm = dao.shm(shm_names.SHM_TELESCOPE_DOME, np.zeros((1, 1)).astype(np.float32))
# pointing-offset calibration constants + outputs (ekarusComputeTheta.py)
telTheta0Shm = dao.shm(shm_names.SHM_TELESCOPE_THETA0, (-100.0 * np.ones((1, 1))).astype(np.float32))
telScaleShm = dao.shm(shm_names.SHM_TELESCOPE_SCALE, np.array([[0.58], [0.43]]).astype(np.float32))
telThetaShm = dao.shm(shm_names.SHM_TELESCOPE_THETA, np.zeros((1, 1)).astype(np.float32))
telRotMatShm = dao.shm(shm_names.SHM_TELESCOPE_ROTMAT, np.eye(2).astype(np.float32))
telTtOffloadShm = dao.shm(shm_names.SHM_TELESCOPE_TT_OFFLOAD, np.zeros((2, 1)).astype(np.float32))
telControlEnableShm = dao.shm(shm_names.SHM_TELESCOPE_CONTROL_ENABLE, np.zeros((1, 1)).astype(np.uint32))
telOffloadEnableShm = dao.shm(shm_names.SHM_TELESCOPE_OFFLOAD_ENABLE, np.zeros((1, 1)).astype(np.uint32))
telOffloadPeriodShm = dao.shm(shm_names.SHM_TELESCOPE_OFFLOAD_PERIOD, (20.0 * np.ones((1, 1))).astype(np.float32))
telOffloadGainShm = dao.shm(shm_names.SHM_TELESCOPE_OFFLOAD_GAIN, (0.5 * np.ones((1, 1))).astype(np.float32))


## Atmosphere simulator
atm_stop = dao.shm(shm_names.SHM_DM1_ATM_STOP, np.ones((1, 1)).astype(np.int32))
atm_seeing = dao.shm(shm_names.SHM_DM1_ATM_SEEING, np.ones((1, 1)).astype(np.float32))
atm_windspeed = dao.shm(shm_names.SHM_DM1_ATM_WINDSPEED, 500 * np.ones((1, 1)).astype(np.float32))

valid_mask = np.load(os.getenv("DAODATA") + "/inputs/calibration/valid_pix_map.npy").astype(np.uint32)
shm_valid_mask = dao.shm(shm_names.SHM_PYRAMID_VALID_PIXELS, valid_mask)

s2m = dao.shm(shm_names.SHM_PYRAMID_2_DM1_REC, np.zeros((n_act_dm1,nCentroids)).astype(np.float32))

TT_recon = np.load(os.getenv("DAODATA") + f"/inputs/fasttt/pupilFlux_2_TT_recon.npy")
TT_recon_shm = dao.shm(shm_names.SHM_PYRAMID_FLUX_2_FASTTT_REC, TT_recon.astype(np.float32))
TT_recon = np.load(os.getenv("DAODATA") + f"/inputs/fasttt/pupilFlux_2_DM_recon.npy")
TT_recon_shm = dao.shm(shm_names.SHM_PYRAMID_FLUX_2_DM1_REC, TT_recon.astype(np.float32))
TT_recon = np.load(os.getenv("DAODATA") + f"/inputs/fasttt/DM_2_TT_recon.npy")
TT_recon_shm = dao.shm(shm_names.SHM_DM1_2_FASTTT_REC, TT_recon.astype(np.float32))

## Offloads
dm_2_fasttt_offload_shm = dao.shm(shm_names.SHM_DM_2_FASTTT_OFFLOAD_TOGGLE, np.ones((1, 1)).astype(np.int32))
# atm_seeing = dao.shm(shm_names.SHM_DM1_ATM_SEEING, np.ones((1, 1)).astype(np.float32))
