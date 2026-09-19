#!/usr/bin/env python3
#
import dao
import numpy as np
import astropy.io.fits as fits
# import time
from datetime import datetime
# import matplotlib.pyplot as plt
import os
import daoEkarusShmNames as shm_names 
import sys
from ekalib import compute_rec


if __name__ == "__main__":

    nModes = int(sys.argv[1])
    basis = sys.argv[2]
    
    m2c = dao.shm(shm_names.SHM_DM1_M2C).get_data()
    validMask = dao.shm(shm_names.SHM_PYRAMID_VALID_PIXELS).get_data()
    ocam = dao.shm(shm_names.SHM_OCAM_REDUCED_FRAME)
    ocam_centroids = dao.shm(shm_names.SHM_PYRAMID_SIGNAL)
    s2mShm = dao.shm(shm_names.SHM_PYRAMID_2_DM1_REC)
    mod_radius = dao.shm(shm_names.SHM_MODULATOR).get_data()[1,0]

    with open(os.getenv("DAODATA") + "/inputs/calibration/interactionMatrix/current_imat.txt") as f:
        im_path = f.read().strip()
    imat = np.load(im_path).astype(np.float32) # [sx * sy, nModes]

    nPix, _ = ocam_centroids.get_data().shape
    nAct, nModesMax = m2c.shape

    rec_shape = s2mShm.get_data().shape
    mmse=False
    RON=0.4
    if mmse:
        N = 200
        avg_frame = ocam.get_data()*0
        for i in range(N):
            avg_frame += ocam.get_data()/N
    else:
        avg_frame = None

    rec = compute_rec(im=imat, 
                      pixel_mask=validMask,
                      rec_shape=(nModesMax, nPix), 
                      recModes=nModes, 
                      mmse=mmse, 
                      RON=RON, 
                      avg_flux=avg_frame)

    s2mShm.set_data(rec.astype(np.float32))

    np.save(
        os.getenv("DAODATA") + f"/inputs/calibration/reconstructor/S2M_{basis}_mod{mod_radius:.1f}_nModes{nModes}.npy",
        rec.astype(np.float32)
    )

    # Get the current timestamp
    timestamp = datetime.now()
    timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S")
    hdr = fits.Header()
    hdr['BASIS'] = basis
    hdr['R_MOD'] = mod_radius
    hdr['N_MODES'] = nModes
    hdr['MMSE'] = mmse
    hdr['RON'] = RON
    hdr['PHOT_COV'] = avg_frame

    fits.writeto(
            os.getenv("DAODATA") + f"/calibration/RecMat_{timestamp_str}.fits",
            rec.astype(np.float32),
            header=hdr,
            overwrite=True,
        )
