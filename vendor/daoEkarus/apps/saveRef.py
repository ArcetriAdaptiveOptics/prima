#!/usr/bin/env python3
#
import os
import sys

import numpy as np
import astropy.io.fits as fits

import dao
import daoEkarusShmNames as shm_names

ref = dao.shm(shm_names.SHM_OCAM_REFERENCE)
refFlux = dao.shm(shm_names.SHM_OCAM_REFERENCE_FLUX)

configDir = os.path.join(os.getenv("DAODATA"), "calibration",'referenceFrames')
os.makedirs(configDir, exist_ok=True)
prefix = sys.argv[1]+'_' if len(sys.argv) > 1 else ''
ref_path = os.path.join(configDir, prefix+"ocamRef.fits")

fits.writeto(
    ref_path,
    ref.get_data().astype(np.float32)*refFlux.get_data(), # save the unnormalized frame
    overwrite=True,
)
