#!/usr/bin/env python3
#
import dao
import numpy as np
import astropy.io.fits as fits
import time
import matplotlib.pyplot as plt
import sys
import os
import argparse
from daoEkarusShmNames import *

# def GetNormalizedOcamFrame():
#     ocamShm.get_data(check=True, semNb=2)
#     frame = ocamShm.get_data(check=True, semNb=2).astype(np.float32) * 0.
#     frame = frame
#     N = 1000
#     for i in range(N):
#         frame += ocamShm.get_data(check=True, semNb=2).astype(np.float32)
#     frame /= N
#     return frame

def GetNormalizedOcamFrame(n_frames):
    pupil_flux_shm.get_data(check=True, semNb=2)
    flux_frame = np.zeros_like(pupil_flux_shm.get_data(), dtype=np.float32)
    dm_frame = np.zeros_like(residual_zonal_commands_shm.get_data(), dtype=np.float32)
    ocam_frame = np.zeros_like(ocamShm.get_data(), dtype=np.float32)
    for i in range(n_frames):
        flux_frame += pupil_flux_shm.get_data(check=True, semNb=2).astype(np.float32)
        dm_frame += residual_zonal_commands_shm.get_data(check=False, semNb=2).astype(np.float32)
        ocam_frame += ocamShm.get_data(check=True, semNb=2).astype(np.float32)
    flux_frame /= n_frames
    dm_frame /= n_frames
    ocam_frame /= n_frames
    return flux_frame, dm_frame, ocam_frame


parser = argparse.ArgumentParser(description="Calibrate the fast tip-tilt interaction matrices")
parser.add_argument(
    "N", nargs="?", type=int, default=1000,
    help="number of frames averaged for each measurement (default: 1000)",
)
parser.add_argument(
    "n_reps", nargs="?", type=int, default=1,
    help="number of push-pull repetitions (default: 1)",
)
args = parser.parse_args()
if args.N < 1 or args.n_reps < 1:
    parser.error("N and n_reps must be positive integers")

fastTtShm = dao.shm(SHM_FASTTT_CHANNEL_2)
ocamShm = dao.shm(SHM_PYRAMID_SIGNAL)
pupil_flux_shm = dao.shm(SHM_PYRAMID_PUPIL_FLUX)
residual_zonal_commands_shm = dao.shm(SHM_DM1_RESIDUAL_ZONAL_COMMANDS)

sx, sy = residual_zonal_commands_shm.get_data().shape
TT_2_DM_iMat = np.zeros((sx*sy, 2)).astype(np.float32)

TT_2_pupilFlux_iMat = np.zeros((4, 2)).astype(np.float32)
TTiMatShm = dao.shm("/tmp/TTiMat.im.shm", TT_2_pupilFlux_iMat)
ocam_shape = ocamShm.get_data().shape
TT_2_ocam_iMat = np.zeros((ocam_shape[0] * ocam_shape[1], 2), dtype=np.float32)

pos = fastTtShm.get_data().copy()
amp = 2

for _ in range(args.n_reps):
    pos[0][0] += amp
    fastTtShm.set_data(pos)
    push_x_flux, push_x_dm, push_x_ocam = GetNormalizedOcamFrame(args.N)

    pos[0][0] += -2 * amp
    fastTtShm.set_data(pos)
    pull_x_flux, pull_x_dm, pull_x_ocam = GetNormalizedOcamFrame(args.N)

    pos[0][0] += amp

    pos[1][0] += amp
    fastTtShm.set_data(pos)
    push_y_flux, push_y_dm, push_y_ocam = GetNormalizedOcamFrame(args.N)

    pos[1][0] += -2 * amp
    fastTtShm.set_data(pos)
    pull_y_flux, pull_y_dm, pull_y_ocam = GetNormalizedOcamFrame(args.N)

    pos[1][0] += amp
    fastTtShm.set_data(pos)

    push_pull_x_flux = (push_x_flux - pull_x_flux) / 2 / amp
    push_pull_y_flux = (push_y_flux - pull_y_flux) / 2 / amp

    push_pull_x_dm = (push_x_dm - pull_x_dm) / 2 / amp
    push_pull_y_dm = (push_y_dm - pull_y_dm) / 2 / amp

    push_pull_x_ocam = (push_x_ocam - pull_x_ocam) / 2 / amp
    push_pull_y_ocam = (push_y_ocam - pull_y_ocam) / 2 / amp

    TT_2_pupilFlux_iMat[:, 0] += push_pull_x_flux.flatten()
    TT_2_pupilFlux_iMat[:, 1] += push_pull_y_flux.flatten()
    TT_2_DM_iMat[:, 0] += push_pull_x_dm.flatten()
    TT_2_DM_iMat[:, 1] += push_pull_y_dm.flatten()
    TT_2_ocam_iMat[:, 0] += push_pull_x_ocam.flatten()
    TT_2_ocam_iMat[:, 1] += push_pull_y_ocam.flatten()

TT_2_pupilFlux_iMat /= args.n_reps
TT_2_DM_iMat /= args.n_reps
TT_2_ocam_iMat /= args.n_reps

pupilFlux_2_TT_recon = np.linalg.pinv(TT_2_pupilFlux_iMat)
DM_2_TT_recon = np.linalg.pinv(TT_2_DM_iMat)
pupilFlux_2_DM_recon = TT_2_DM_iMat @ pupilFlux_2_TT_recon

_ = dao.shm(SHM_PYRAMID_FLUX_2_FASTTT_REC, pupilFlux_2_TT_recon.astype(np.float32))
_ = dao.shm(SHM_PYRAMID_FLUX_2_DM1_REC, pupilFlux_2_DM_recon.astype(np.float32))
_ = dao.shm(SHM_DM1_2_FASTTT_REC, DM_2_TT_recon.astype(np.float32))

np.save(
        os.getenv("DAODATA") + f"/inputs/fasttt/pupilFlux_2_TT_recon.npy",
        pupilFlux_2_TT_recon.astype(np.float32)
    )

np.save(
        os.getenv("DAODATA") + f"/inputs/fasttt/DM_2_TT_recon.npy",
        DM_2_TT_recon.astype(np.float32)
    )

np.save(
        os.getenv("DAODATA") + f"/inputs/fasttt/pupilFlux_2_DM_recon.npy",
        pupilFlux_2_DM_recon.astype(np.float32)
    )

np.save(
        os.getenv("DAODATA") + f"/inputs/fasttt/TT_2_ocam_iMat.npy",
        TT_2_ocam_iMat.astype(np.float32)
    )



# TTiMatShm.set_data(TT_2_pupilFlux_iMat.astype(np.float32))



