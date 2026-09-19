import dao
import numpy as np
import time
# import matplotlib.pyplot as plt
# import sys
import os
import re
import daoEkarusShmNames as shm_names

dmSleep = 0.004 # time to wait for DM to settle
# TODO check if this can be lowered: how much time does 
# actually pass between the command sent and frame
# acquisition? I bet it is (non-neglibly) more than the sleep time in Python

def get_fps():
    command = "fps"
    cmdShm = dao.shm(shm_names.SHM_OCAM_CMD)
    command += "\0" + "000000000000000000000000000000000000"
    cmdShm.set_data(np.frombuffer(command.encode("utf8"), dtype=np.uint8))
    rspShm = dao.shm(shm_names.SHM_OCAM_RSP)
    time.sleep(0.1)
    fullResponse = rspShm.get_data()
    null_index = np.where(fullResponse == 0)[0]
    text = fullResponse[: null_index[0]].tobytes().decode("latin-1", errors="replace")
    number = re.search(r"\d+", text)
    return int(number.group())


def get_gain():
    command = "gain"
    cmdShm = dao.shm(shm_names.SHM_OCAM_CMD)
    command += "\0" + "000000000000000000000000000000000000"
    cmdShm.set_data(np.frombuffer(command.encode("utf8"), dtype=np.uint8))
    rspShm = dao.shm(shm_names.SHM_OCAM_RSP)
    time.sleep(0.1)
    fullResponse = rspShm.get_data()
    null_index = np.where(fullResponse == 0)[0]
    text = fullResponse[: null_index[0]].tobytes().decode("latin-1", errors="replace")
    number = re.search(r"\d+", text)
    return int(number.group())


def get_temp():
    command = "temp"
    cmdShm = dao.shm(shm_names.SHM_OCAM_CMD)
    command += "\0" + "000000000000000000000000000000000000"
    cmdShm.set_data(np.frombuffer(command.encode("utf8"), dtype=np.uint8))
    rspShm = dao.shm(shm_names.SHM_OCAM_RSP)
    time.sleep(0.1)
    fullResponse = rspShm.get_data()
    null_index = np.where(fullResponse == 0)[0]
    text = fullResponse[: null_index[0]].tobytes().decode("latin-1", errors="replace")
    lines = text.splitlines()

    # Keep first line
    first_line = lines[0]

    # Extract name/value pairs from first line
    matches = re.findall(r"(\w+)\[([-+]?\d*\.?\d+)\]", first_line)

    # Convert to dictionary with float values
    temp_dict = {name: float(value) for name, value in matches}

    return temp_dict


def get_pixels_from_random_inputs(dmCmd, ocam, amp=0.3, n_iter=1000):
    bgp = dao.shm(shm_names.SHM_OCAM_DARK_MAP_PERCENT, np.zeros((1, 1)).astype(np.uint32))
    valid_pix_map = ocam.get_data(check = True, semNb=5) * 0
    cmdSize = dmCmd.get_data().shape[0]
    for i in range(n_iter):
        # cmd = (np.random.rand(cmdSize, 1) * 2 * amp - amp).astype(np.float32) # (unclipped) commands with mean -amp: was this intended ???
        cmd = np.clip(np.random.rand(cmdSize, 1) * amp, a_min=-1, a_max=1).astype(np.float32)
        dmCmd.set_data(cmd)
        time.sleep(dmSleep)
        im = ocam.get_data(check = True, semNb=5)
        valid_pix_map += im
        bgp.set_data(bgp.get_data() * 0 + np.uint32(100 * (i + 1) / n_iter))
    dmCmd.set_data(dmCmd.get_data() * 0)
    bgp.set_data(bgp.get_data() * 0 + np.uint32(100))
    return valid_pix_map / n_iter


def create_tracking_number(name_data, data, tracking_number = None ):
    '''
    Function to 
    - Create the folder in the telemetry folder
    - return the filename full path
    '''
    print("\n")
    obs_date = time.strftime("%Y_%m_%d")

    if tracking_number is None:
        tracking_number = time.strftime("%Y%m%d_%H%M%S", time.localtime())
    save_loc = os.path.join(os.getenv('DAODATA'), "telemetry",obs_date, tracking_number)
    # Check if the folder exists
    if not os.path.isdir(save_loc):
        # If the folder does not exist, create it
        os.makedirs(save_loc)
    
    file_name = os.path.join(save_loc,tracking_number +"_"+name_data + ".npy")
    np.save(file_name, data)
    print(f"Saved: {name_data}")
    return save_loc

def compute_valid_pix_map(dmCmd, ocam, amp=0.3, n_iter=1000):
    valid_pix_map = get_pixels_from_random_inputs(dmCmd, ocam, amp=amp, n_iter=n_iter)
    sx, sy = np.shape(valid_pix_map)
    for j in range(2):
        for k in range(2):
            block = valid_pix_map[
                j * sx // 2:(j + 1) * sx // 2, k * sy // 2:(k + 1) * sy // 2
            ]
            m = np.max(block)
            block /= m if m > 0 else 1.0   # guard empty/zero quadrant
    return valid_pix_map


def calibration(m2c, dmCmd, ocam, frames2avg:int=100, amp=0.05, n_rep:int=5, progressBar:bool=False):
    valid_pix = dao.shm(shm_names.SHM_PYRAMID_VALID_PIXELS).get_data().astype(bool)
    sx, sy = ocam.get_data().shape
    n_modes = (np.abs(m2c).sum(axis = 0) > 0).sum()
    if np.isscalar(amp):
        amp = np.one(n_modes)*amp
    if progressBar:
        bgp = dao.shm(shm_names.SHM_OCAM_DARK_MAP_PERCENT)

    n_avg = frames2avg
    if dao.shm(shm_names.SHM_OOPAO_MODE).get_data()==1:
        n_avg = 1
        n_rep = 1
    imat = np.zeros((sx * sy, n_modes))
    for i_rep in range(n_rep):
        count = 0
        imat_ = np.zeros((sx * sy, n_modes))
        for i in range(n_modes):
            count+=1
            push = np.zeros((sx, sy))
            pull = np.zeros((sx, sy))
            dmCmd.set_data((m2c[:, i].reshape(m2c.shape[0], 1) * amp[i]).astype(np.float32))
            time.sleep(dmSleep)
            for j in range(n_avg):
                frame = ocam.get_data(check = True, semNb=5)
                push += frame / frame[valid_pix].sum() #.mean()

            dmCmd.set_data(-(m2c[:, i].reshape(m2c.shape[0], 1) * amp[i]).astype(np.float32))
            time.sleep(dmSleep)
            for j in range(n_avg):
                frame = ocam.get_data(check = True, semNb=5)
                pull += frame / frame[valid_pix].sum() #.mean()

            imat_[:, i] = ((push - pull) / (2 * n_avg * amp[i])).reshape(sx * sy)

            if progressBar:
                bgp.set_data(bgp.get_data() * 0 + np.uint32(100 * count / n_modes / n_rep + 100 * i_rep / n_rep))

        imat+=imat_/n_rep
    dmCmd.set_data(dmCmd.get_data() * 0)
    if progressBar:
        bgp.set_data(bgp.get_data() * 0 + np.uint32(100))
    # ocam_centroids = dao.shm(shm_names.SHM_PYRAMID_SIGNAL)
    # sx, sy = ocam_centroids.get_data().shape
    # imat *= (sx*sy)/np.sum(valid_pix)
    return imat

def compute_rec(im, pixel_mask, rec_shape, recModes:int, 
                mmse:bool=False, RON:float=0.0, avg_flux=None):
    imat,_ = get_valid_imat(im,pixel_mask,recModes)
    nPix = int(pixel_mask.sum())

    if mmse is False:
        rec = np.linalg.pinv(imat)
    else:
        phot_cov = avg_flux.flatten()[pixel_mask.flatten()]
        cov_inv = np.diag(1/(phot_cov+RON)) # diagonal matrix inversion
        aux = imat.T @ cov_inv
        rec = np.linalg.pinv(aux @ imat) @ aux # MMSE formula
    rec_correct_size = np.zeros(rec_shape).astype(np.float32)
    rec_correct_size[:imat.shape[1], :nPix] = rec
    return rec_correct_size


def get_valid_imat(im,pixel_mask,nRecModes:int):
    ocam_centroids = dao.shm(shm_names.SHM_PYRAMID_SIGNAL)
    sx, sy = ocam_centroids.get_data().shape
    nPix = int(pixel_mask.sum())
    pixel_mask = (pixel_mask).astype(bool)
    nPix_full = sx * sy
    imfull = np.zeros((nPix_full, im.shape[1]))
    imfull[:nPix] = im[pixel_mask.flatten()]
    imat = imfull[:nPix,:nRecModes]
    # imat *= nPix/nPix_full # rescale to current number of valid pixels
    return imat,nPix_full

def image_grid(shape, recenter:bool = False):
    ny, nx = shape
    cy, cx = (0,0)
    if recenter:
        cy, cx = ny//2, nx//2
    x = np.arange(nx, dtype=float) - cx
    y = np.arange(ny, dtype=float) - cy
    X,Y = np.meshgrid(x, y)
    return X,Y

def get_photocenter(image,offset:bool=False):
    X,Y = image_grid(image.shape)
    qy = np.sum(Y * image) / np.sum(image)
    qx = np.sum(X * image) / np.sum(image)
    if offset:
        qy += 0.5
        qx += 0.5
    return qx,qy 

def get_frame_pupil_centers(frame,thr=0.3,xhalf=100,yhalf=120):
    Y,X = image_grid(frame.shape)
    ll = (X<=xhalf) * (Y<=yhalf)
    lr = (X>xhalf) * (Y<=yhalf)
    ul = (X<=xhalf) * (Y>yhalf)
    ur = (X>xhalf) * (Y>yhalf)
    centers = np.zeros([4,2])
    mask = (frame*ll > thr*np.nanmax(frame*ll)).astype(bool)
    qx,qy = get_photocenter(mask)
    centers[0,:] = np.array([qx,qy])
    mask = (frame*lr > thr*np.nanmax(frame*lr)).astype(bool)
    qx,qy = get_photocenter(mask)
    centers[1,:] = np.array([qx,qy])
    mask = (frame*ul > thr*np.nanmax(frame*ul)).astype(bool)
    qx,qy = get_photocenter(mask)
    centers[2,:] = np.array([qx,qy])
    mask = (frame*ur > thr*np.nanmax(frame*ur)).astype(bool)
    qx,qy = get_photocenter(mask)
    centers[3,:] = np.array([qx,qy])
    return centers

def mask_from_frame(dmCmd, ocam, amp=0.3, n_iter=1000,
                    diams=np.linspace(30,44,50),cobs=np.linspace(0.0,0.4,50)):
    frame = get_pixels_from_random_inputs(
        dmCmd, ocam, amp=amp, n_iter=n_iter
    )
    Y,X = image_grid(frame.shape)
    centers = get_frame_pupil_centers(frame)
    def get_masked_flux(diam,obs):
        mask = np.zeros(frame.shape)
        for j in range(4):
            cj = centers[j]
            rho = np.sqrt((X-cj[1])**2+(Y-cj[0])**2)
            mask += np.logical_and(rho>diam/2*obs,rho<diam/2)
        return np.sum(frame*mask),mask
    flux = 0
    for diam in diams:
        old_flux = flux
        flux,_ = get_masked_flux(diam,obs=0)
        dflux = (flux-old_flux)/old_flux
        if dflux < 0.007:
            break
    for cob in cobs:
        old_flux = flux
        flux,_ = get_masked_flux(diam,obs=cob)
        dflux = (flux-old_flux)/old_flux
        if dflux < -0.002:
            break
    flux,mask = get_masked_flux(diam,obs=cob)
    print(diam,cob)
    return mask,centers


def minimum_rms_slaving_matrix(slave_ids, stiffMat_fname='StiffMat_rcond0.01.npy'):
    K = np.load(os.path.join(os.getenv('DAODATA'), "inputs",'dm468','StiffMat',stiffMat_fname))
    is_master = np.ones(468)
    ids = np.arange(468)
    is_master[slave_ids] = 0
    master_ids = ids[is_master.astype(bool)]
    Km = K[master_ids,:]
    Ks = K[slave_ids,:]
    Kmm = Km[:,master_ids]
    Kms = Km[:,slave_ids]
    Ksm = Ks[:,master_ids]
    Kss = Ks[:,slave_ids]
    aux = Kms.T @ Kms + Kss.T @ Kss
    temp = Kms.T @ Kmm + Kss.T @ Ksm
    Qs = - np.linalg.pinv(aux) @ temp
    return Qs


def enslave_m2c(m2c, slave_ids, slaving_method:str='zero', nNonZeroModes:int=0, p:int=1, d_thr:float=np.inf):
    """
    Apply slaving to the provided modes-to-commands matrix on
    the selected slave actuators (slave_ids) according to
    the input slaving strategy (slaving_method).

    Parameters
    ----------
    m2c : ndarray [nActs,nActs]
        Full modes-to-command matrix for all actuators.
    slave_ids : ndarray [nSlaves,]
        Indices of slave actuators.
    slaving_method : str, optional
        Slaving strategy:
        - 'zero': leave slave actuators at zero (Default).
        - 'weighted_mmean': weighted mean over nearby masters.
        - 'nearest': assign each slave to its nearest master.
        - 'minimum_rms': minimize command RMS on actuators.
    nNonZeroModes : int, optional
        Modes to keep when using the 'zero' method.
        Default is 0: no modes are kept.
    p : int, optional
        Distance exponent used for the 'weighted_mean' method.
    d_thr : float, optional
        Distance threshold for the 'weighted_mmean' method.
        Masters further than this are ignored.

    Returns
    -------
    slaved_m2c : ndarray
        The modes-to-command matrix after applying slaving.
    slaveMat : ndarray
        The actuator slaving matrix, mapping slave to master actuators.
    """
    dmMap = dao.shm(shm_names.SHM_DM1_468_MASK).get_data()
    nActs = np.sum(dmMap)
    slave_ids = slave_ids.astype(int)

    # find master ids
    is_master = np.ones(nActs)
    ids = np.arange(nActs,dtype=int)
    is_master[slave_ids] = 0
    master_ids = (ids[is_master.astype(bool)]).astype(int)

    # Initialize slaveMat
    slaveMat = np.zeros([nActs,nActs],dtype=np.float32)
    for master in master_ids:
        slaveMat[master,master] = 1

    X,Y = image_grid(dmMap.shape)
    coords = np.zeros([2,nActs])
    coords[0,:] = X[dmMap.astype(bool)]
    coords[1,:] = Y[dmMap.astype(bool)]
    master_coords = coords[:,master_ids]
    dist = lambda xy: np.sqrt((xy[0]-master_coords[0])**2 + (xy[1]-master_coords[1])**2)

    if slaving_method == 'zero':
        slaved_m2c = m2c.copy()
        slaved_m2c[slave_ids,nNonZeroModes:] = 0.0

    elif slaving_method == 'weighted_mean':
        for slave in slave_ids:
            d_slave = dist(coords[:,slave])**p
            masters = master_ids[d_slave <= d_thr]
            d_slave = d_slave[d_slave <= d_thr]
            slaveMat[slave,masters] = 1/d_slave/np.sum(1/d_slave)
        # slaveMat = slaveMat[:,master_ids]
        # slaved_m2c = slaveMat @ m2c[master_ids,:]
        slaved_m2c = slaveMat @ m2c

    elif slaving_method == 'nearest':
        for slave in slave_ids:
            d_slave = dist(coords[:,slave])
            nearest_master = master_ids[np.argmin(d_slave)]
            slaveMat[slave,nearest_master] = 1
        # slaveMat = slaveMat[:,master_ids]
        # slaved_m2c = slaveMat @ m2c[master_ids,:]
        slaved_m2c = slaveMat @ m2c

    elif slaving_method == 'minimum_rms':
        slaveMat = minimum_rms_slaving_matrix(slave_ids)
        slaved_m2c = m2c.copy()
        slaved_m2c[slave_ids,:] = slaveMat @ m2c[master_ids,:]

    else:
        raise NotImplementedError(f"{slaving_method} is not an available slaving method.\
                                    Available methods are: 'zero', 'nearest', 'weighted_mean', 'minimum_rms' ")

    return slaved_m2c, slaveMat


######################################################## OLD SCRIPTS #######################################################################
# def calibration(m2c, dmCmd, ocam, frames2avg:int=100, max_amp=0.05, template_len:int=5, nRepeats:int=1, progressBar:bool=False):
#     valid_pix = dao.shm(shm_names.SHM_PYRAMID_VALID_PIXELS).get_data().astype(bool)
#     sx, sy = ocam.get_data().shape
#     nModes = (np.abs(m2c).sum(axis = 0) > 0).sum()
#     template = (-1)**np.arange(template_len)
#     if progressBar:
#         bgp = dao.shm(shm_names.SHM_OCAM_DARK_MAP_PERCENT, np.zeros((1, 1)).astype(np.uint32))

#     imat_avg = np.zeros((sx * sy, nModes))
#     for rep in range(nRepeats):
#         imat = np.zeros((sx * sy, nModes))
#         for i in range(nModes):
#             print(f'\rIteration {rep}/{nRepeats}, mode {i}/{nModes}',end='\r',flush=True)
#             radial_order = (np.ceil(-3.0/2.0+np.sqrt(1+8*(i+2))/2.0)).astype(int)
#             amp = max_amp/np.sqrt(radial_order)
#             signals = np.zeros((template_len, sx, sy))
#             for k in range(template_len):
#                 dmCmd.set_data((-1**k)*(m2c[:, i].reshape(m2c.shape[0], 1) * amp).astype(np.float32))
#                 time.sleep(dmSleep)
#                 for j in range(frames2avg):
#                     frame = ocam.get_data(check = True, semNb=5)
#                     signals[k] += frame / frame[valid_pix].sum()
#             signals_redux = np.zeros((sx, sy))
#             for k in range(template_len-1):
#                 signals_redux += signals[k]*template[k]+signals[k+1]*template[k+1]
#             imat[:, i] = (signals_redux / ((template_len-1) * frames2avg * amp)).reshape(sx * sy)
#             if progressBar:
#                 bgp.set_data(bgp.get_data() * 0 + np.uint32(100 * (i + 1) / nModes))
#         imat_avg += imat/nRepeats
        
#     if progressBar:
#         bgp.set_data(bgp.get_data() * 0 + np.uint32(100))

#     dmCmd.set_data(dmCmd.get_data() * 0)
#     return imat


# def s2m_slaving(im,m2c,pixel_mask,recModes:int, 
#                slave_ids = np.array([196, 197, 198, 199, 220, 221, 222, 223, 244, 245, 246, 247, 268, 269, 270, 271],dtype=int)):
#     # Select valid part of the IM    
#     nPix = int(pixel_mask.sum())
#     imat,nPix_full = get_valid_imat(im,pixel_mask,recModes)

#     # Define slaving matrix
#     is_master = np.ones(468)
#     ids = np.arange(468)
#     is_master[slave_ids] = 0
#     master_ids = ids[is_master.astype(bool)]
#     Km = K[master_ids,:]
#     Ks = K[slave_ids,:]
#     Kmm = Km[:,master_ids]
#     Kms = Km[:,slave_ids]
#     Ksm = Ks[:,master_ids]
#     Kss = Ks[:,slave_ids]
#     aux = Kms.T @ Kms + Kss.T @ Kss
#     temp = Kms.T @ Kmm + Kss.T @ Ksm
#     Qs = - np.linalg.pinv(aux) @ temp

#     # Compute slaved signals to modes matrix
#     D = m2c[:,:recModes] @ imat
#     Ds = D[:,master_ids] + D[:,slave_ids] @ Qs
#     Rs = np.zeros([len(master_ids)+len(slave_ids),imat.shape[0]])
#     Rm = np.linalg.pinv(Ds)
#     Rs[master_ids,:] = Rm
#     Rs[slave_ids,:] = Qs @ Rm
#     c2m = np.linalg.pinv(m2c[:,:recModes])
#     s2m = c2m @ Rs    
#     rec_correct_size = np.zeros([m2c.shape[1],nPix_full]).astype(np.float32)
#     rec_correct_size[:recModes, :nPix] = s2m
#     return rec_correct_size


# def select_valid_pixels(dmCmd, ocam, threshold=0.75, amp=0.3, n_iter=1000, dofilter:bool=False):
#     valid_pix_map = get_pixels_from_random_inputs(
#         dmCmd, ocam, amp=amp, n_iter=n_iter
#     )
#     sx, sy = np.shape(valid_pix_map)
#     for j in range(2):
#         for k in range(2):
#             valid_pix_map[
#                 j * sx // 2 : (j + 1) * sx // 2, k * sy // 2 : (k + 1) * sy // 2
#             ] /= np.max(
#                 valid_pix_map[
#                     j * sx // 2 : (j + 1) * sx // 2, k * sy // 2 : (k + 1) * sy // 2
#                 ]
#             )
#     valid_pix = valid_pix_map > threshold
#     if dofilter: 
#         # filter out all pixels with less than min_neighbours
#         # adjacent valid pixels. Guards against isolated 'hot' pixels
#         min_neighbours = 5
#         hpf = np.ones((3, 3), dtype=np.float32)
#         hpf[1, 1] = 0
#         padded = np.pad(valid_pix.astype(np.float32), pad_width=1, mode="constant")
#         sx, sy = valid_pix.shape
#         conv = np.zeros((sx, sy), dtype=np.float32)
#         for i in range(hpf.shape[0]):
#             for j in range(hpf.shape[1]):
#                 conv += padded[i : i + sx, j : j + sy] * hpf[i, j]
#         valid_pix = conv >= min_neighbours
#     return valid_pix

# def calibration(m2c, dmCmd, ocam):
#     n_avg_global = 200
#     amp_global = 0.2
#     pauseTime = 0.02
#     sx, sy = ocam.get_data().shape
#     nModes = (np.abs(m2c).sum(axis = 0) > 0).sum()
#     imat = np.zeros((sx * sy, nModes))

#     for i in range(nModes):
#         radial_order = (np.ceil(-3.0/2.0+np.sqrt(1+8*(i+2))/2.0)).astype(int)
#         n_avg = int(n_avg_global/np.sqrt(radial_order))

#         print(f'\rCalibrating mode {i}/{nModes}',end='\r',flush=True)
#         # if i < 2:
#         #     # n_avg = int(20 * n_avg_global)
#         #     n_avg = n_avg_global
#         #     amp = 10 * amp_global
#         # elif i < 25:
#         #     # n_avg = int(1 / np.sqrt(i + 1) * np.sqrt(25) * n_avg_global)
#         #     amp = 3 * amp_global
#         # elif i > 155:
#         #     n_avg = n_avg_global
#         #     amp = 0.5 * amp_global  ## otherwise we exceed the linearity range
#         # else:
#         #     n_avg = n_avg_global
#         #     amp = amp_global
#         amp = amp_global/np.abs(radial_order)

#         push = np.zeros((sx, sy))
#         pull = np.zeros((sx, sy))
#         dmCmd.set_data((m2c[:, i].reshape(m2c.shape[0], 1) * amp).astype(np.float32))
#         time.sleep(pauseTime)
#         for j in range(n_avg):
#             push += ocam.get_data(check = True, semNb=5)

#         dmCmd.set_data(-(m2c[:, i].reshape(m2c.shape[0], 1) * amp).astype(np.float32))
#         time.sleep(pauseTime)

#         for j in range(n_avg):
#             pull += ocam.get_data(check = True, semNb=5)

#         imat[:, i] = ((push - pull) / (2 * n_avg * amp)).reshape(sx * sy)

#     dmCmd.set_data(dmCmd.get_data() * 0)
#     return imat


# def imat_valid_pixels(imat, valid_pix_map, max_valid):
#     imat_valid = np.copy(imat) * 0

#     for i in range(imat.shape[1]):
#         imat_valid[:, i] = imat[:, i] * valid_pix_map.flatten()
#         # imat_valid[:,i] = (imat[:,i].reshape(240,240))[np.where(valid_pix_map==1)]

#     imat_valid_small = np.zeros((max_valid.sum(), imat_valid.shape[1]))
#     for i in range(imat_valid.shape[1]):
#         imat_valid_small[:, i] = imat_valid[:, i][max_valid.flatten() == 1]
#         # imat_valid_small[:,i] = (imat_valid[:,i].reshape(240,240))[np.where(max_valid==1)]

#     return imat_valid_small

# def get_pixels_from_random_inputs(dmCmd, ocam, bg, amp=0.3, n_iter=1000):

#     valid_pix_map = get_data_normalized(ocam) * 0
#     cmdSize = dmCmd.get_data().shape[0]
#     sx, sy = np.shape(valid_pix_map)
#     for i in range(n_iter):
#         dmCmd.set_data((np.random.rand(cmdSize, 1) * 2 * amp - amp).astype(np.float32))
#         time.sleep(0.01)
#         im = get_data_normalized(ocam, bg)
#         valid_pix_map += im

#     dmCmd.set_data(dmCmd.get_data() * 0)
#     return valid_pix_map / n_iter

# def get_data(ocam):
#     for k in range(2):
#         ocam.get_data(check=True, semNb=7).astype(np.float32)
#     frame = ocam.get_data(check=True, semNb=7).astype(np.float32)
#     return frame


# def get_data_normalized(ocam, bg=0):
#     for k in range(2):
#         ocam.get_data(check=True, semNb=7).astype(np.float32)
#     frame_norm = ocam.get_data(check=True, semNb=3).astype(np.float32)
#     frame_norm -= bg
#     frame_norm[:1, :] = 0
#     frame_norm /= np.sum(frame_norm)
#     return frame_norm


# def get_data_normalized2(ocam):
#     for k in range(2):
#         ocam.get_data(check=True, semNb=7).astype(np.float32)
#     frame_norm = ocam.get_data(check=True, semNb=3).astype(np.float32)
#     frame_norm[:1, :] = 0
#     # frame_norm /= np.sum(frame_norm)
#     return frame_norm


# def get_cog(tab):
#     xx, yy = np.mgrid[0 : nx // 2, 0 : ny // 2]
#     cx = np.sum(tab * xx) / np.sum(tab)
#     cy = np.sum(tab * yy) / np.sum(tab)
#     return int(round(cx)), int(round(cy))


# def get_pupil_intersection(valid_pix_map):
#     nx, ny = np.shape(valid_pix_map)
#     intersect_pupil = np.ones((nx, ny), dtype=bool)
#     for i in range(2):
#         for j in range(2):
#             subpupil = valid_pix_map[
#                 i * nx // 2 : (i + 1) * nx // 2, j * ny // 2 : (j + 1) * ny // 2
#             ]
#             cx, cy = get_cog(subpupil)
#             subpupil = np.roll(subpupil, cx - nx // 2, axis=0)  # check roll sign !!!
#             subpupil = np.roll(subpupil, cy - ny // 2, axis=1)  # check roll sign !!!
#             intersect_pupil *= subpupil > 0
#     return intersect_pupil


# def get_pupil_union(valid_pix_map):
#     nx, ny = np.shape(valid_pix_map)
#     union_pupil = np.zeros((nx, ny), dtype=bool)
#     for i in range(2):
#         for j in range(2):
#             subpupil = valid_pix_map[
#                 i * nx // 2 : (i + 1) * nx // 2, j * ny // 2 : (j + 1) * ny // 2
#             ]
#             cx, cy = get_cog(subpupil)
#             subpupil = np.roll(subpupil, cx - nx // 2, axis=0)  # check roll sign !!!
#             subpupil = np.roll(subpupil, cy - ny // 2, axis=1)  # check roll sign !!!
#             union_pupil += subpupil > 0
#     return union_pupil > 0


# def calibration2(m2c, dmCmd, ocam):
#     n_avg = 50
#     amp = 0.1
#     pauseTime = 0.01
#     sx, sy = ocam.get_data().shape
#     imat = np.zeros((sx * sy, m2c.shape[1]))

#     i = 0
#     push = np.zeros((sx, sy))
#     dmCmd.set_data((m2c[:, i].reshape(m2c.shape[0], 1) * amp).astype(np.float32))
#     time.sleep(pauseTime)
#     for j in range(n_avg):
#         push += get_data_normalized2(ocam)
#     push /= n_avg

#     pull = np.zeros((sx, sy))
#     dmCmd.set_data(-(m2c[:, i].reshape(m2c.shape[0], 1) * amp).astype(np.float32))
#     time.sleep(pauseTime)
#     for j in range(n_avg):
#         pull += get_data_normalized2(ocam)
#     pull /= n_avg

#     imat[:, i] = ((push - pull) / (2 * amp)).reshape(sx * sy)

#     i = 1
#     push = np.zeros((sx, sy))
#     dmCmd.set_data((m2c[:, i].reshape(m2c.shape[0], 1) * amp).astype(np.float32))
#     time.sleep(pauseTime)
#     for j in range(n_avg):
#         push += get_data_normalized2(ocam)
#     push /= n_avg

#     pull = np.zeros((sx, sy))
#     dmCmd.set_data(-(m2c[:, i].reshape(m2c.shape[0], 1) * amp).astype(np.float32))
#     time.sleep(pauseTime)
#     for j in range(n_avg):
#         pull += get_data_normalized2(ocam)
#     pull /= n_avg

#     imat[:, i] = ((push - pull) / (2 * amp)).reshape(sx * sy)

#     dmCmd.set_data(dmCmd.get_data() * 0)
#     return imat


