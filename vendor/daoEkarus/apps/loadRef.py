#!/usr/bin/env python3
#
import os
import sys

import numpy as np
import astropy.io.fits as fits

import dao
import daoEkarusShmNames as shm_names

ref = dao.shm(shm_names.SHM_OCAM_REFERENCE)

configDir = os.path.join(os.getenv("DAODATA"), "calibration",'referenceFrames')
ref_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(configDir, "ocamRef.fits")

validMask = dao.shm(shm_names.SHM_PYRAMID_VALID_PIXELS)
refFlux = dao.shm(shm_names.SHM_OCAM_REFERENCE_FLUX)

raw_ref_data = fits.getdata(ref_path).astype(np.float32)
flux = np.sum(raw_ref_data * validMask.get_data())    
if flux == 0:
    print("ERROR: zero flux on the valid pixels; reference not updated.")
    sys.exit(1)

ref_data = raw_ref_data/flux
ref.set_data(ref.get_data() * 0 + ref_data.astype(np.float32))

refFlux.set_data(refFlux.get_data() * 0 + flux.astype(np.float32))
