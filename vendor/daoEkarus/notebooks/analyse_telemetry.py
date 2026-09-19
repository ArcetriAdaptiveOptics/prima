import numpy as np
import matplotlib.pyplot as plt
from astropy.io import fits
import os
from scipy.signal import welch

#################### IMAGE UTILS ######################################
def reshape_on_mask(a,mask):
    img_2d = np.zeros(mask.shape)
    img_2d[~mask] = a.copy()
    img_2d = img_2d.reshape(mask.shape)
    return img_2d

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


################################ DATA AND SCALING ##########################

def get_scaling(m2c, show=False):
    SF2WF = 2 # surface to wavefront conversion factor
    IFs = fits.getdata(os.path.join(os.getenv('DAODATA'), "inputs", 'dm468', 'reordered_DM468_ifunc.fits')).T*SF2WF
    mode_amps = np.std(IFs @ m2c,axis=0) #np.sqrt(np.mean((iff @ m2c)**2,axis=0))
    if show:
        plt.figure()
        plt.loglog(np.arange(len(mode_amps))+1,mode_amps)
        plt.grid()
    return mode_amps

def get_data(tn:str):
    try:
        data = np.load(os.path.join(os.getenv('DAODATA'), "telemetry_snapshots", '20'+tn.split('T')[0], '20'+tn+'_telemetry_data.npy'),allow_pickle=True).item()
    except FileNotFoundError:
        try:
            data = np.load(os.path.join(os.getenv('DAODATA'), "telemetry", tn.split('_')[0], tn+'_telemetry_data.npy'),allow_pickle=True).item()
        except FileNotFoundError:
            data = np.load(os.path.join(os.getenv('DAODATA'), "telemetry", '20'+tn.split('T')[0], '20'+tn+'_telemetry_data_cblue.npy'),allow_pickle=True).item()
    # print(data.keys())
    return data

def get_filelist(date:str='26-08-03',fromtn:str='00_00_00',totn:str='23_59_59',doprint:bool=True):
    date_key = '20' + date.replace('_', '-')
    root_dir = os.path.join(os.getenv('DAODATA'), "telemetry_snapshots", date_key)
    flist = os.listdir(root_dir)
    root_dir = os.path.join(os.getenv('DAODATA'), "telemetry", date_key) # CBLUE data directory
    flist+=os.listdir(root_dir)
    ftime = [ff.split('T')[1] for ff in flist]
    ftime = [ff.split('_telemetry')[0] for ff in ftime]
    ftime = [int(ff.replace('_','')) for ff in ftime]
    sortids = np.argsort(np.array(ftime)).astype(int)
    flistsort = np.array(flist)[sortids]
    fromtime = int(fromtn.replace('_',''))
    totime = int(totn.replace('_',''))
    ftime = np.array(ftime)[sortids]
    fcut = flistsort[np.logical_and(ftime>fromtime,ftime<totime)]
    if doprint:
        print(fcut)
    return fcut


##################### FRAME ANALYSIS ##########################

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


def show_avg_frame(data,tn=''):
    nPix = np.sum(data['validPixels'])
    flux = data['ocamCube'][data['validPixels'].astype(bool)]/data['ocamGain']
    plt.figure()
    plt.imshow(data['ocamCube']/np.mean(flux),origin='lower',cmap='hot')
    plt.title(f'{np.sum(flux)/nPix*4:1.1f} phot/subap/frame\n{tn}')


def plot_frame_centers(data,radius_px=20,tn='',xhalf=100,yhalf=120,obsratio=0.3,norm_gain=True):
    frame = data['ocamCube'] - data['ocamDark']
    thr = 0.23 if norm_gain else 0.7
    centers = get_frame_pupil_centers(frame,xhalf=xhalf,yhalf=yhalf,thr=thr)
    avg_center = np.mean(centers,axis=0)

    _, ax = plt.subplots(figsize=(6,6))
    ax.imshow(frame, cmap='hot')
    for (cx, cy) in centers:
        circle = plt.Circle((cx, cy), radius=radius_px, fill=False, edgecolor='white', linewidth=1.2)
        ax.add_patch(circle)
        if obsratio > 0:
            circle = plt.Circle((cx, cy), radius=radius_px*obsratio, fill=False, edgecolor='white', linestyle='--', linewidth=1.2)
            ax.add_patch(circle)
        # ax.text(cx, cy, f'{cy:1.1f}, {cx:1.1f}', color='white', fontsize=10, ha='center', va='center')

    ax.plot(avg_center[0], avg_center[1], '+', color='white', markersize=6, markeredgewidth=2)
    ax.set_xlim(0, frame.shape[1])
    ax.set_ylim(frame.shape[0], 0)
    ax.set_aspect('equal')

    nPix = np.sum(data['validPixels'])
    if norm_gain:
        flux = data['ocamCube'][data['validPixels'].astype(bool)]/data['ocamGain']
        ax.set_title(f'{tn}\n{np.sum(flux)/nPix*4:1.1f} phot/subap/frame ({data['ocamFps']} fps, gain: {data['ocamGain']:1.0f})')
    else:
        flux = data['ocamCube'][data['validPixels'].astype(bool)]
        ax.set_title(f'{tn}\n{np.sum(flux)/nPix*4:1.1f} phot/subap/frame ({data['ocamFps']} fps)')
    plt.show()

    return avg_center

def get_mask_from_frame(frame,obs:float=0.0,diam=40):
    Y,X = image_grid(frame.shape)
    centers = get_frame_pupil_centers(frame,thr=0.25)
    mask = np.zeros(frame.shape)
    for j in range(4):
        cj = centers[j]
        rho = np.sqrt((X-cj[1])**2+(Y-cj[0])**2)
        mask += np.logical_and(rho>diam/2*obs,rho<diam/2)
    pflux = np.sum(frame*mask)
    return mask,centers,pflux

def mask_from_frame(frame,diams=np.linspace(30,44,50),cobs=np.linspace(0.0,0.4,50)):
    Y,X = image_grid(frame.shape)
    centers = get_frame_pupil_centers(frame,thr=0.25)
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
        if dflux < 0.005:
            break
    for cob in cobs:
        old_flux = flux
        flux,_ = get_masked_flux(diam,obs=cob)
        dflux = (flux-old_flux)/old_flux
        if dflux < -0.001:
            break
    flux,mask = get_masked_flux(diam,obs=cob)
    print(diam,cob)
    return mask,centers

######################### SPECTRAL ANALYSIS ##################################

def modal_plot(data,tn='',idx=0,useWelch:bool=False,onBench:bool=False):
    modes = data['modeCube'][:,:,0]
    cmd = data['dmCmdCube'][:,:,0]
    flat = data['dmFlatCube'][:,:,0]
    m2c = data['m2c']
    fps = data['ocamFps']
    if onBench:
        turb = data['dmTurbulenceCube'][:,:,0]
        pol_modes = (np.linalg.pinv(m2c) @ (turb).T).T
    else:
        disturb = cmd-flat
        pol_modes = (np.linalg.pinv(m2c) @ (disturb).T).T + modes
    modes2Nm = get_scaling(m2c)*1e+9
    modes *= modes2Nm
    pol_modes *= modes2Nm
    vec_rms = lambda vec: np.sqrt(np.mean(vec**2,axis=0))
    nModes = np.sum(np.sum(abs(data['s2m']),axis=1)>1e-6)
    x = np.arange(nModes)+1
    if useWelch:
        nperseg = 512
        f,psd=welch(modes[:,idx:idx+5],fs=fps,nperseg=nperseg,scaling='density',axis=0)
        f,pol_psd=welch(pol_modes[:,idx:idx+5],fs=fps,nperseg=nperseg,scaling='density',axis=0)
    else:
        psd,f = get_spectrum(modes[:,idx:idx+5],dt=1/fps,axis=0)
        pol_psd,f = get_spectrum(pol_modes[:,idx:idx+5],dt=1/fps,axis=0) 
    plt.figure(figsize=(12,5))
    plt.subplot(1,2,1)
    plt.loglog(x,vec_rms(modes)[:nModes],label='meas residual')
    plt.loglog(x,vec_rms(pol_modes)[:nModes],label='POL (no OGC, no delay)')
    plt.legend()
    plt.grid(which='both',alpha=0.4)
    plt.xlabel('Mode #')
    plt.ylabel('residual [nm]')
    plt.ylim([0.5,3e+3])
    if np.sum(abs(data['dmClosedLoopCube'])) > 1e-6:
        plt.title(tn+f"\nGain: {data['lpGain'][0][0]:1.2f}, Leak: {data['lpLeak'][0][0]:1.3f}")
    else:
        plt.title(tn+f"\nOpen loop")
    plt.subplot(1,2,2)
    plt.loglog(f,psd[:,0],label='meas residual')
    plt.loglog(f,pol_psd[:,0],label='POL (no OGC, no delay)')    
    # plt.loglog(f,psd[:,0]/pol_psd[:,0],label='POL (no OGC, no delay)')    
    plt.legend()
    plt.grid(which='both',alpha=0.4)
    plt.xlabel('Frequency [Hz]')
    ttloop = 'ON' if data['TTisClosedLoop'] else 'OFF'
    plt.title(f'{tn}\nMode {idx} temporal spectrum (TT {ttloop})')  

def get_spectrum(signal, dt=1, axis=-1):
    hann = np.hanning(len(signal))
    if len(signal.shape) > 1:
        spe = np.fft.rfft(signal*hann[:,None], norm="ortho", axis=axis)
    else:
        spe = np.fft.rfft(signal*hann, norm="ortho", axis=axis)
    nn = np.sqrt(spe.shape[axis])
    spe_mod = (np.abs(spe)) / nn
    freq = np.fft.rfftfreq(signal.shape[axis], d=dt)
    spe_mod[0] = 0
    return spe_mod, freq

def modal_spectrum(data, tn=''):
    lomodes_ids = np.array([0,1,2,3,4,5,6])
    momodes_ids = np.array([10,20,30,40,50])
    homodes_ids = np.array([100,120,150,180,190])
    m2c = data['m2c']
    modes2Nm = get_scaling(m2c)*1e+9
    modes = data['modeCube'][:,:,0]*modes2Nm
    modes_spe, f = get_spectrum(modes-np.mean(modes),dt=1/data['ocamFps'],axis=0)
    plt.figure(figsize=(18,4))
    for j in range(3):
        plt.subplot(1,3,j+1)
        if j == 0:
            mod_ids = lomodes_ids
        elif j == 1:
            mod_ids = momodes_ids
        elif j == 2:
            mod_ids = homodes_ids
        for i,mode in enumerate(mod_ids):
            plt.loglog(f,modes_spe[:,mode],label=f'Mode {mode}')
        plt.grid(which='both',alpha=0.4)
        plt.legend(loc='best')
        plt.xlabel('Frequency [Hz]')
        plt.ylabel('residual [nm^2]')
        plt.ylim([1,2e+4])
        if j == 1:
            ttloop = 'ON' if data['TTisClosedLoop'] else 'OFF'
            plt.title(f'{tn}\nMeas modes temporal spectrum (TT {ttloop})')

def plot_etf(data,tn='',mode_ids=np.array([0]),onBench:bool=False,useWelch:bool=False):
    modes = data['modeCube'][:,:,0]
    cmd = data['dmCmdCube'][:,:,0]
    flat = data['dmFlatCube'][:,:,0]
    m2c = data['m2c']
    fps = data['ocamFps']
    if onBench:
        disturb = data['dmTurbulenceCube'][:,:,0]
        pol_modes = (np.linalg.pinv(m2c) @ (disturb).T).T
    else:
        disturb = cmd-flat
        pol_modes = (np.linalg.pinv(m2c) @ (disturb).T).T + modes
    modes2Nm = get_scaling(m2c)*1e+9
    modes *= modes2Nm
    pol_modes *= modes2Nm
    spe,f = get_spectrum(modes[:,mode_ids],dt=1/fps,axis=0)
    pol_spe,f = get_spectrum(pol_modes[:,mode_ids],dt=1/fps,axis=0) 
    if useWelch:
        nperseg = 512
        f,psd=welch(modes[:,mode_ids],fs=fps,nperseg=nperseg,scaling='density',axis=0)
        f,pol_psd=welch(pol_modes[:,mode_ids],fs=fps,nperseg=nperseg,scaling='density',axis=0)
    else:
        psd,f = get_spectrum(modes[:,mode_ids],dt=1/fps,axis=0)
        pol_psd,f = get_spectrum(pol_modes[:,mode_ids],dt=1/fps,axis=0)
    etf = psd/pol_psd 
    plt.figure()
    for j,mode in enumerate(mode_ids):
        plt.loglog(f,etf[:,j],label=f'Mode {mode}')   
    plt.legend()
    plt.grid(which='both',alpha=0.4)
    plt.xlabel('Frequency [Hz]')
    # plt.title(f'{tn}\nTransfer function')
    plt.title(tn+f"\n {data['ocamFps']}Hz, gain={data['lpGain'][0][0]:1.2f}, leak={data['lpLeak'][0][0]:1.3f}")
    return spe/pol_spe,f