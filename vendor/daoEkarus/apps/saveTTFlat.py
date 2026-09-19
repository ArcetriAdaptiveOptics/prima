#!/usr/bin/env python3
#
import dao
import numpy as np
import astropy.io.fits as fits
import sys
import os
from daoEkarusShmNames import *

fastTT_flat = dao.shm(SHM_FASTTT_CMD)

# load flat
np.save(
    os.getenv("DAODATA") + "/inputs/fasttt/RefPos.npy",
    fastTT_flat.get_data().astype(np.float32)
)
