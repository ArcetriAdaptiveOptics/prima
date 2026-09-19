#!/usr/bin/env python3
#
import dao
import numpy as np
import astropy.io.fits as fits
import sys
import os
from daoEkarusShmNames import *

ocamValidPixels = dao.shm(sys.argv[1])
max_nCentroids =  dao.shm(SHM_PYRAMID_SIGNAL).get_data().shape[0]

valid_pix = fits.getdata(sys.argv[2]).astype(np.uint32)

if valid_pix.shape[0] >= max_nCentroids:
    print(
        f"ERROR: mask shape {valid_pix.shape} != maximum shape {max_nCentroids}; "
        "not writing valid pixels."
    )
    sys.exit(1)

ocamValidPixels.set_data(ocamValidPixels.get_data()*0 + valid_pix)
np.save(os.getenv("DAODATA") + "/inputs/calibration/valid_pix_map.npy", valid_pix)

