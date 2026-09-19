#!/usr/bin/env python3
#
import dao
import numpy as np
import astropy.io.fits as fits
import time
import matplotlib.pyplot as plt
import sys
import os
from daoEkarusShmNames import *

posx = float(sys.argv[1])
posy = float(sys.argv[2])

fastTtShm = dao.shm(SHM_FASTTT_CMD)

pos = fastTtShm.get_data()

t0 = time.time()

freq = 10

while 1:
    t = time.time() - t0

    pos[0][0] = posx * np.cos(2*np.pi*freq*t)
    pos[1][0] = posy * np.sin(2*np.pi*freq*t)

    fastTtShm.set_data(pos.astype(np.float32))

    time.sleep(1e-3)

