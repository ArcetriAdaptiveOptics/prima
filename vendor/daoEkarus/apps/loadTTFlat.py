#!/usr/bin/env python3
#
import dao
import numpy as np
import astropy.io.fits as fits
import sys
import os
from daoEkarusShmNames import *

fastTT_flat = dao.shm(SHM_FASTTT_CHANNEL_0)

# load flat
flat = np.load(
    os.getenv("DAODATA") + "/inputs/fasttt/RefPos.npy"
)

fastTT_flat.set_data(flat.astype(np.float32))

dao.shm(SHM_FASTTT_CHANNEL_2).set_data(np.zeros((2,1)).astype(np.float32))
