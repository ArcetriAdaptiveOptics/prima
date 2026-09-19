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

fastTtShm = dao.shm(SHM_FASTTT_CHANNEL_2)

pos = fastTtShm.get_data()

pos[0][0] = posx
pos[1][0] = posy

fastTtShm.set_data((pos).astype(np.float32))

