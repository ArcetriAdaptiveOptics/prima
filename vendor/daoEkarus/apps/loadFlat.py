#!/usr/bin/env python3
#
import dao
import numpy as np
import astropy.io.fits as fits
import sys
import os
from daoEkarusShmNames import *

dmFlat = dao.shm(sys.argv[1])
stage = sys.argv[2]

default_flat_path = os.path.join(
    os.getenv("DAODATA"), "inputs", stage, "flat_dm.fits"
)
flat_path = sys.argv[3] if len(sys.argv) > 3 else default_flat_path

flat = fits.getdata(flat_path).astype(np.float32)
dmFlat.set_data(dmFlat.get_data()*0 + flat)
