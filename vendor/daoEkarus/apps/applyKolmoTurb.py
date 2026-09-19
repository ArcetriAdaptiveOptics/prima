#!/usr/bin/env python3
#

import dao
import numpy as np
# import matplotlib.pyplot as plt
# from scipy import signal
import time
import sys
from daoEkarusShmNames import *


# Load all shm
dmDist = dao.shm(SHM_DM1_CHANNEL_2)  # any dm offset
atmStop = dao.shm(SHM_DM1_ATM_STOP)
atmSeeing = dao.shm(SHM_DM1_ATM_SEEING)
atmSpeed = dao.shm(SHM_DM1_ATM_WINDSPEED)
is_simulation = dao.shm(SHM_OOPAO_MODE).get_data()[0, 0]

atmStop.set_data(atmStop.get_data() * 0 + 1)
time.sleep(0.1)
atmStop.set_data(atmStop.get_data() * 0)

if is_simulation == 0:

    seeing_file = 1.
    # C2PHI = np.load("/home/daouser/DAODATA/inputs/dm468/atm_coefs_r0_0p1m_v0_6p5mps_freq_1000Hz.npy").astype(np.float32)
    C2PHI = np.load("/home/daouser/DAODATA/inputs/dm468/atmo_coeffs_r0_0.1m_v0_5.8mps_freq_1000Hz.npy").astype(np.float32)
    nIter = C2PHI.shape[0]

    FILE_RATE = 1000.0          # Hz
    FILE_SPEED = 5.8 #6.5            # m/s

    # Desired loop frequency
    LOOP_RATE = dao.shm(SHM_OCAM_FPS).get_data()[0,0]        # Hz
    DT = 1.0 / LOOP_RATE

    idx = 0.0                   # floating-point index in C2PHI
    direction = 1               # +1 forward, -1 backward

    next_time = time.perf_counter()

    while True:

        # ---------------------------------------------------
        # Read user parameters
        # ---------------------------------------------------
        desired_speed = float(atmSpeed.get_data()[0, 0])   # m/s

        dmseeing = atmSeeing.get_data()[0, 0]
        seeing2phase = (dmseeing / seeing_file) ** (5 / 6)

        # ---------------------------------------------------
        # Advance through the file
        # ---------------------------------------------------
        step = direction * desired_speed * FILE_RATE / (FILE_SPEED * LOOP_RATE)

        idx += step

        # Reflect at the ends
        if idx >= nIter - 2:
            idx = 2 * (nIter - 2) - idx
            direction *= -1

        elif idx <= 0:
            idx = -idx
            direction *= -1

        # ---------------------------------------------------
        # Linear interpolation
        # ---------------------------------------------------
        i0 = int(np.floor(idx))
        alpha = idx - i0

        coef_tur = (
            (1.0 - alpha) * C2PHI[i0]
            + alpha * C2PHI[i0 + 1]
        )

        coef_tur *= seeing2phase
        coef_tur -= coef_tur.mean()

        dmDist.set_data(coef_tur.astype(np.float32))

        if atmStop.get_data():
            break

        # ---------------------------------------------------
        # Wait until next 500-Hz tick
        # ---------------------------------------------------
        next_time += DT

        remaining = next_time - time.perf_counter()
        if remaining > 0:
            time.sleep(remaining)
        else:
            # We're behind schedule; resynchronize
            next_time = time.perf_counter()

        sys.stdout.write(
            f"\rPlayback speed = {desired_speed:4.2f} m/s"
        )
        sys.stdout.flush()


    dmDist.set_data(coef_tur * 0)
