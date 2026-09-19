#!/usr/bin/env python3
#
import dao
import numpy as np
import sys
from daoEkarusShmNames import *

is_simulation = dao.shm(SHM_OOPAO_MODE).get_data()[0, 0]
pwfs_modulator = dao.shm(SHM_MODULATOR)
arr = pwfs_modulator.get_data()

freq = int(sys.argv[1])
radius  = float(sys.argv[2])

if is_simulation == 0:
    arr[0][0] = freq
    arr[1][0] = radius
    arr[2][0] = 50
    arr[3][0] = 50
    arr[4][0] = 1
else:
    arr[1] = float(radius)

pwfs_modulator.set_data(arr)