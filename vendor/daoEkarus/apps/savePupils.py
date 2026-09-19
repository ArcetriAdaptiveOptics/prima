#!/usr/bin/env python3
#
import dao
import numpy as np
import astropy.io.fits as fits
import sys
import os
from daoEkarusShmNames import *
from datetime import datetime

ocamValidPixels = dao.shm(sys.argv[1])

tn = datetime.now().strftime("%Y%m%d_%H%M%S")
pupils_path = os.path.join(
    os.getenv("DAODATA"), "calibration", 'pupils', f"{tn}_valid_pixels.fits"
)

fits.writeto(
    pupils_path,
    ocamValidPixels.get_data().astype(np.uint32),
    overwrite=True,
)
