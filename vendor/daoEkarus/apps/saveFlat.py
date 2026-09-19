#!/usr/bin/env python3
#
import dao
import numpy as np
import astropy.io.fits as fits
import sys
import os
from daoEkarusShmNames import *
from datetime import datetime

dmCmd = dao.shm(sys.argv[1])
stage = sys.argv[2]

# keep compatibility with direct calls while adding TN prefix
default_flat_path = os.path.join(
    os.getenv("DAODATA"), "inputs", stage, "flat_dm.fits"
)
fits.writeto(
    default_flat_path,
    dmCmd.get_data().astype(np.float32),
    overwrite=True,
)

# If no explicit path is provided, generate a TN-prefixed flat name
if len(sys.argv) <= 3:
    tn = datetime.now().strftime("%Y%m%d_%H%M%S")
    flat_path = os.path.join(
        os.getenv("DAODATA"), "inputs", stage, 'flats', f"{tn}_flat_dm.fits"
    )
    fits.writeto(
        flat_path,
        dmCmd.get_data().astype(np.float32),
        overwrite=True,
    )
