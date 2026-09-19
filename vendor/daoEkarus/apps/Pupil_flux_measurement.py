#!/usr/bin/env python3
#
import dao
import numpy as np
import daoEkarusShmNames as shm_names
import time

ocamShm = dao.shm(shm_names.SHM_OCAM_REDUCED_FRAME)
pupil_flux_shm = dao.shm(shm_names.SHM_PYRAMID_PUPIL_FLUX)
pupil_centers_shm = dao.shm(shm_names.SHM_PYRAMID_PUPIL_CENTERS)
valid_mask_shm = dao.shm(shm_names.SHM_PYRAMID_VALID_PIXELS)
# pupil_selector_mask = np.load("/home/daouser/DAODATA/inputs/fasttt/pupil_selector_mask.npy")

# sx, sy = ocamShm.get_data().shape
# pupil_selector_mask = pupil_selector_mask[:, :sx]

# max_freq = 500
# DT = 1/max_freq

# next_time = time.perf_counter()

# frame = dao.shm(shm_names.SHM_OCAM_FRAME).get_data()
# validMask = dao.shm(shm_names.SHM_PYRAMID_VALID_PIXELS).get_data().astype(bool)
# H,W = frame.shape
# y_grid, x_grid = np.indices((H,W))
# X_coords = x_grid[validMask]
# Y_coords = y_grid[validMask]

xHalf = 100
yHalf = 120

x = np.arange(240)
X,Y = np.meshgrid(x,x)


def _two_level_thresholding(image, thr1: float = 0.1, thr2: float = 0.25):
    """ Use two level thresholding to define active pixels """
    min_val, max_val = float(np.min(image)), float(np.max(image))
    s1 = min_val + (max_val - min_val) * thr1
    thresh_img = image.copy()
    thresh_img[thresh_img < s1] = 0
    s2 = float(np.mean(thresh_img[thresh_img > 0])) * thr2
    mask = thresh_img >= s2
    return mask

while 1:
    data = ocamShm.get_data(check=True, semNb=3).astype(np.float32).squeeze()
    valid_mask = valid_mask_shm.get_data()
    masked_data = data*valid_mask
    # data[data < 0.01 * data.max()] = 0
    # data[data < data.mean()-4*data.std()] = 0
    p1 = masked_data[:xHalf, :yHalf].sum()
    p2 = masked_data[xHalf:, :yHalf].sum()
    p3 = masked_data[:xHalf, yHalf:].sum()
    p4 = masked_data[xHalf:, yHalf:].sum()

    pupil_flux = np.array([p1, p2, p3, p4]).reshape(4,1)
    pupil_flux /= pupil_flux.sum()
    pupil_flux_shm.set_data(pupil_flux.astype(np.float32))

    data_thr = _two_level_thresholding(data,thr1=0.1,thr2=0.25)

    cx1 = np.sum(X[:xHalf, :yHalf] * data_thr[:xHalf, :yHalf])/data_thr[:xHalf, :yHalf].sum()
    cx2 = np.sum(X[xHalf:, :yHalf] * data_thr[xHalf:, :yHalf])/data_thr[xHalf:, :yHalf].sum()
    cx3 = np.sum(X[:xHalf, yHalf:] * data_thr[:xHalf, yHalf:])/data_thr[:xHalf, yHalf:].sum()
    cx4 = np.sum(X[xHalf:, yHalf:] * data_thr[xHalf:, yHalf:])/data_thr[xHalf:, yHalf:].sum()

    cy1 = np.sum(Y[:xHalf, :yHalf] * data_thr[:xHalf, :yHalf])/data_thr[:xHalf, :yHalf].sum()
    cy2 = np.sum(Y[xHalf:, :yHalf] * data_thr[xHalf:, :yHalf])/data_thr[xHalf:, :yHalf].sum()
    cy3 = np.sum(Y[:xHalf, yHalf:] * data_thr[:xHalf, yHalf:])/data_thr[:xHalf, yHalf:].sum()
    cy4 = np.sum(Y[xHalf:, yHalf:] * data_thr[xHalf:, yHalf:])/data_thr[xHalf:, yHalf:].sum()

    pupil_centers = np.array([[cx1,cy1],[cx2,cy2],[cx3,cy3],[cx4,cy4]]).reshape(4,2)
    pupil_centers_shm.set_data(np.mean(pupil_centers,axis=0).astype(np.float32))

    # threshold = 0.1
    # weighted_sectors = pupil_selector_mask * data * (data > threshold)
    # sector_norms = weighted_sectors.sum(axis=1) # = value ?
    # photocenter_x = np.sum(weighted_sectors*X_coords,axis=1) / sector_norms
    # photocenter_y = np.sum(weighted_sectors*Y_coords,axis=1) / sector_norms
    
    # next_time += DT
    # remaining = next_time - time.perf_counter()
    # if remaining > 0:
    #     time.sleep(remaining)
    # else:
    #     # We're behind schedule; resynchronize
    #     next_time = time.perf_counter()
