#!/usr/bin/env python3
#
import dao
import numpy as np
# import astropy.io.fits as fits
# import time
# from datetime import datetime
import matplotlib.pyplot as plt
import os
import daoEkarusShmNames as shm_names 
import sys

from ekalib import *

is_simulation = dao.shm(shm_names.SHM_OOPAO_MODE).get_data()[0, 0]

if __name__ == "__main__":
    stage = sys.argv[1]
    plt.ion()
    # m2c=fits.getdata(os.getenv('DAODATA')+'/inputs/Papyrus/M2C.fits').astype(np.float32)
    if stage == "Papyrus":
        m2cShm = dao.shm(shm_names.SHM_DM1_M2C)
        m2c = m2cShm.get_data()
        ocam = dao.shm(shm_names.SHM_OCAM_FRAME)
        ocam_centroids = dao.shm(shm_names.SHM_OCAM_CENTROIDS)
        dmCmd = dao.shm(shm_names.SHM_DM1_CHANNEL_2)
        dmFlat = dao.shm(shm_names.SHM_DM1_CHANNEL_0)
        bg = dao.shm(shm_names.SHM_OCAM_BACKGROUND)
        s2mShm = dao.shm(shm_names.SHM_S2M)
        # iMatShm = dao.shm(shm_names.SHM_IMAT)
        validMaskShm = dao.shm(shm_names.SHM_OCAM_VALID_MASK)
        # illumPupilShm = dao.shm(shm_names.SHM_PWFS_VALID_PIXELS)

    elif stage == "Oziriis":
        m2cShm = dao.shm(shm_names.SHM_2ndM2C)
        m2c = m2cShm.get_data()
        ocam = dao.shm(shm_names.SHM_CRED2)
        dmCmd = dao.shm(shm_names.SHM_2ndDM_CHANNEL_2)
        dmFlat = dao.shm(shm_names.SHM_2ndDM_CHANNEL_0)
        bg = dao.shm(shm_names.SHM_CRED2_DARK_MAP)
        s2mShm = dao.shm(shm_names.SHM_2ndCM)
        iMatShm = dao.shm(shm_names.SHM_2ndIMAT)
        validMaskShm = dao.shm(shm_names.SHM_2ndVALID_MASK)
        illumPupilShm = dao.shm(shm_names.SHM_CRED2_PUPIL_ILLUMINATION)
        cred2Cal = dao.shm(shm_names.SHM_CRED2_REFERENCE)
    else:
        raise ValueError(f"Unknown stage: {stage}")

    # # load flat
    # flat = fits.getdata(os.getenv("DAODATA") + f"/inputs/{stage}/flat_dm.fits").astype(
    #     np.float32
    # )
    # # applys flat
    # dmFlat.set_data(flat)
    # get an image chack=True wait for a new image in the shared memory
    
    # imag = ocam.get_data(check=True, semNb=3)

    # bk = bg.get_data() * 0
    # bg.set_data(bk)

    # if is_simulation == 0:
    #     input("Turn off laser to measure bck. Press enter.")

    #     for k in range(1000):
    #         bk = bk + ocam.get_data(check=True, semNb=3)
    #         print(k)
    #     bk = bk / 1000
    #     bg.set_data(bk)
    #     fits.writeto(
    #         os.getenv("DAODATA") + f"/inputs/{stage}/Dark.fits",
    #         bk.astype(np.float32),
    #         overwrite=True,
    #     )

    input("Turn on laser for calibration. Press enter.")

    doPixelCalibration = input("Press 1 to calibrate the valid pixels. Press any other key to skip.")
    if doPixelCalibration == 1:
        print("Selecting valid pixels")
        n_iter = 1000 if is_simulation == 0 else 400
        if stage == "Papyrus":
            valid_pix_map = select_valid_pixels(
                dmCmd, ocam, threshold=0.05, n_iter=n_iter
            )
        else:
            bk = bg.get_data()
            pix_map = get_pixels_from_random_inputs(dmCmd, ocam, bk, amp=0.1, n_iter=n_iter)
            cred2Cal.set_data(pix_map.astype(np.float32))
            valid_pix_map = np.copy(pix_map)
            valid_pix_map[:128] /= np.max(valid_pix_map[:128])
            valid_pix_map[128:] /= np.max(valid_pix_map[128:])
            valid_pix_map = valid_pix_map > 0.1
        # valid_pix_map = get_pupil_union(valid_pix_map) # uncomment to get union of pupils
        print(f"Valid Pixel = {valid_pix_map.sum()}")

        if (valid_pix_map.sum() > ocam_centroids.get_data().shape[0]):
            raise ValueError("Too many valid pixels")
        
        validMaskShm.set_data(valid_pix_map.astype(np.uint32))
        np.save(
            os.getenv("DAODATA") + f"/inputs/{stage}/valid_pix_map.npy",
            valid_pix_map.astype(np.uint32)
        )
        # fits.writeto(
        #     os.getenv("DAODATA")
        #     + f"/calibration/pupilMap{extra_identifier}{timestamp_str}.fits",
        #     valid_pix_map.astype(np.uint64),
        #     overwrite=True,
        # )

    nModes = int(input("Number of modes for IM calibration: "))
    # imat = calibration(m2c.get_data(), dmCmd, ocam)
    imat = calibration(m2c[:,:nModes], dmCmd, ocam_centroids)
    # fits.writeto(
    #     os.getenv("DAODATA")
    #     + f"/calibration/IMFull{extra_identifier}{timestamp_str}.fits",
    #     imat.astype(np.float32),
    #     overwrite=True,
    # )
    np.save(
        os.getenv("DAODATA") + f"/inputs/{stage}/IM.npy",
        imat.astype(np.float32)
    )
    # fits.writeto(
    #     os.getenv("DAODATA") + f"/calibration/IM{extra_identifier}{timestamp_str}.fits",
    #     imat_valid.astype(np.float32),
    #     overwrite=True,
    # )
    
    # iMatShm.set_data(imat.astype(np.float32))

    # maxValid = dao.shm(SHM_OCAM_PUPIL_ILLUMINATION).get_data().astype(np.uint32)

    # imat_valid = imat_valid_pixels(imat, valid_pix_map, maxValid)
    # imat_valid = imat_valid_pixels(imat, maxValid)

    recModes = int(input("Number of modes for Reconstructor (enter 0 to skip computation): "))
    if recModes > 0:
        # rec = np.linalg.pinv(imat)
        # sx, sy = ocam_centroids.get_data().shape
        # rec_correct_size = np.zeros((m2c.shape[1], sx * sy)).astype(np.float32)
        # rec_correct_size[:imat.shape[1], :] = rec
        sx, sy = ocam_centroids.get_data().shape
        rec = compute_rec(imat,mmse=False,nModes=recModes)
        # Nframes = 200
        # avg_frame = ocam.get_data()/Nframes
        # for j in range(1,Nframes):
        #     avg_frame += ocam.get_data()/Nframes
        # rec = compute_rec(imat,mmse=True,nModes=recModes,RON=0.4,avg_flux=avg_flux)
        s2mShm.set_data(rec.astype(np.float32))
        np.save(
            os.getenv("DAODATA") + f"/inputs/{stage}/S2M.npy",
            rec.astype(np.float32)
        )
    else:
        print('Skipping reconstructor computation')

    # fits.writeto(
    #     os.getenv("DAODATA")
    #     + f"/calibration/S2M{extra_identifier}{timestamp_str}.fits",
    #     rec.astype(np.float32),
    #     overwrite=True,
    # )


    

    # store the valid pixel map in shared memory

    # illumPupilShm.set_data(valid_pix_map.astype(np.uint32))

    # # Get the current timestamp
    # timestamp = datetime.now()

    # # Format the timestamp as a string with second precision
    # timestamp_str = timestamp.strftime("%Y-%m-%d_%H-%M-%S")

    # extra_identifier = "_Oziriis" if stage == "Oziriis" else ""

