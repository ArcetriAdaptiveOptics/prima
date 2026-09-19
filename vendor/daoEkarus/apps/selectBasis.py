#!/usr/bin/env python3
import dao
import numpy as np
import sys
from daoEkarusShmNames import *

dmCmd = dao.shm(SHM_DM1_CHANNEL_3)
number_of_actuators = dmCmd.get_data().shape[0]
basisArg = sys.argv[1]

if basisArg == "Influence":
    temp_m2c = np.eye(number_of_actuators, dtype=np.float32)
else:
    temp_m2c = np.load(basisArg).astype(np.float32)

if number_of_actuators not in temp_m2c.shape:
    raise ValueError(
        f"Selected M2C is not made for this DM. "
        f"Expected {number_of_actuators} actuators, "
        f"but M2C has shape {tuple(temp_m2c.shape)}."
    )

# orient so rows == actuators
if temp_m2c.shape[0] != number_of_actuators:
    temp_m2c = temp_m2c.T

m2c = np.zeros((number_of_actuators, number_of_actuators), dtype=np.float32)
_, n_modes = temp_m2c.shape
m2c[:, :n_modes] = temp_m2c

dao.shm(SHM_DM1_M2C).set_data(dao.shm(SHM_DM1_M2C).get_data()*0 + m2c)

c2m = np.zeros((number_of_actuators,number_of_actuators)).astype(np.float32)
c2m[ : n_modes,:] = np.linalg.pinv(m2c[:,:n_modes]).astype(np.float32)
dm1c2z = dao.shm(SHM_DM1_C2M,c2m)