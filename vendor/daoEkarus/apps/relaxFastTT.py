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


fastTtShm = dao.shm(SHM_FASTTT_CHANNEL_2)

pos = fastTtShm.get_data()

t0 = time.time()

tau = 1
t1 = 5
t2 = 7

freq = 10


while 1:
    t = time.time() - t0
    pos[0][0] = 50 * np.cos(2*np.pi*freq*t)
    pos[1][0] = 50 * np.sin(2*np.pi*freq*t)

    if t < t1:
        pos *= t/t1
    elif t < t2:
        pass
    else:
        pos *= np.exp(-(t - t2)/tau)

    fastTtShm.set_data(pos.astype(np.float32))

    time.sleep(1e-3)
    sys.stdout.write(f"\rpositions = {pos[0,0]:.2f} {pos[1,0]:.2f}")
    sys.stdout.flush()

    if t > 15:
        fastTtShm.set_data(pos.astype(np.float32) * 0)
        break

    

