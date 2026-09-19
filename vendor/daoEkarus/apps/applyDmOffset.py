#!/usr/bin/env python3
#
import dao
import numpy as np
import time
import sys
from daoEkarusShmNames import *
import os

dmCmd = dao.shm(SHM_DM1_CHANNEL_3)
number_of_actuators = dmCmd.get_data().shape[0]

modeNumber = int(sys.argv[1])
modeAmplitude = float(sys.argv[2])
basisSelection = sys.argv[3]

if basisSelection == "KL":
    with open(os.getenv("DAODATA") + "/inputs/dm468/current_m2c.txt") as f:
        m2c_path = f.read().strip()
        f.close()
    m2c = (np.load(m2c_path).astype(np.float32))

elif basisSelection == "Zernike":
    m2c = (np.load("/home/daouser/DAODATA/inputs/dm468/dm486_z2c.npy").astype(np.float32))

elif basisSelection == "Hadamard":
    m2c = (np.load("/home/daouser/DAODATA/inputs/dm468/dm486_z2c.npy").astype(np.float32))

elif basisSelection == "Zonal":
    m2c = np.eye(number_of_actuators, dtype = np.float32)

if number_of_actuators not in m2c.shape:
    raise ValueError(
        f"Selected M2C is not made for this DM. "
        f"Expected {number_of_actuators} actuators, "
        f"but M2C has shape {tuple(m2c.shape)}."
    )

if number_of_actuators != m2c.shape[0]:
    m2c = m2c.T

nModes = m2c.shape[1]
if modeNumber < nModes:
    voltage_command = m2c[:, modeNumber] * modeAmplitude
    voltage_command = voltage_command.reshape(m2c.shape[0], 1).astype(np.float32)


pauseTime = 0.01
time.sleep(pauseTime)
dmCmd.set_data(dmCmd.get_data() + voltage_command)
time.sleep(pauseTime)
