#!/usr/bin/env python3
#

import os
import sys
import time
import numpy as np
from scipy.optimize import curve_fit
import dao
from astropy.io import fits
import daoEkarusShmNames as shm_names

import argparse
from scipy.special import j1

def get_dmV2nm_conversion(m2c):
    SF2WF = 2 # surface to wavefront conversion factor
    IFs = fits.getdata(os.path.join(os.getenv('DAODATA'), "inputs", 'dm468', 'reordered_DM468_ifunc.fits')).T*SF2WF
    mode_amps = np.std(IFs @ m2c,axis=0) 
    return mode_amps*1e+9

# TODO: generalize this function to accept SHMs for 
# camera and DM channels as inputs. Currently,
# this is only working for NCPA on ORCA with DM1

def parse_args():
    parser = argparse.ArgumentParser(
        description="Compute NCPA offset command on the DM"
    )

    parser.add_argument("--n_modes", type=int, default=10, help="number of modes for NCPA fit. Default: 10")
    parser.add_argument("--amp", type=float, default=0.02, help="max amplitude of mode offset (DM units). Default: 0.02")
    parser.add_argument("--n_it", type=int, default=1, help="number of iterations. Default: 2")
    parser.add_argument("--n_steps", type=int, default=9, help="number of steps per amplitude. Default: 9")
    parser.add_argument("--n_frames", type=int, default=20, help="number of frames to average. Default: 20")
    parser.add_argument("--use_gaussian", type=bool, default=True, help="type of fit to use: gaussian or jinc. Default: True (gaussian)")

    return parser.parse_args()


def gaussian_2d(coords, amp, xo, yo, sigma, offset):
    """Simple symmetric 2D Gaussian model for PSF peak fitting."""
    x, y = coords
    g = offset + amp * np.exp(-((x - xo)**2 + (y - yo)**2) / (2 * sigma**2))
    return g.ravel()

def jinc_2d(coords, amp, xo, yo, w, offset):
    """2D jinc modes for PSF peak fitting."""
    x, y = coords
    r = np.sqrt((x-xo)**2 + (y-yo)**2)
    z = np.pi*r/w
    z_safe = np.where(z==0,1e-9,z) # avoid division by 0
    jinc = (2 * j1(z_safe)) / z_safe
    jinc = np.where(z==0,1.0,jinc) # impose correct value
    g = offset + amp * (jinc**2)
    return g.ravel()


def compute_metric(cam_shm, bg_shm, n_frames, half_w:int=12, use_gaussian:bool=True):
    """
    Reads N frames from the camera, subtracts the background, averages them, 
    and returns the peak amplitude computed via a 2D Gaussian fit.
    """
    time.sleep(0.005) # Allow DM to settle (5 ms)
    # Accumulate and average N frames (blocking on new frames)
    frame_sum = None
    for _ in range(n_frames):
        frame = cam_shm.get_data(check=True,semNb=8).astype(np.float32)
        if frame_sum is None:
            frame_sum = np.zeros_like(frame)
        frame_sum += frame
        
    avg_frame = frame_sum / n_frames
    bg = bg_shm.get_data().astype(np.float32)
    img = avg_frame - bg

    # Find the global maximum to crop a bounding box
    ymax, xmax = np.unravel_index(np.argmax(img), img.shape)
    
    # Define a window around the max pixel for fitting
    y0 = max(0, ymax - half_w)
    y1 = min(img.shape[0], ymax + half_w + 1)
    x0 = max(0, xmax - half_w)
    x1 = min(img.shape[1], xmax + half_w + 1)

    sub_img = img[y0:y1, x0:x1]
    Y, X = np.mgrid[y0:y1, x0:x1]
    
    try: # Fit Gaussian/Jinc to the sub-image
        initial_guess = (sub_img.max(), xmax, ymax, 2.0, np.median(sub_img))
        if use_gaussian:
            popt, _ = curve_fit(gaussian_2d, (X, Y), sub_img.ravel(), p0=initial_guess) # Gaussian fit
        else:
            popt, _ = curve_fit(jinc_2d, (X, Y), sub_img.ravel(), p0=initial_guess) # Jinc fit
        peak_value = popt[0]
        return peak_value
    except Exception:
        return sub_img.max()

def optimize_ncpa(
    amp:float=0.02, 
    n_modes:int=12, 
    n_steps:int=9, 
    Nit:int=2, 
    n_frames:int=20,
    use_gaussian:bool=True,
    dm:str = 'DM1',
    camera:str ='ORCA',
    wfs:str = 'OCAM'
): 
    """
    Performs modal amplitude ramps to compensate Non-Common Path Aberrations.
    """
    if n_steps % 2 == 0:
        print("Warning: n_steps should be odd. Automatically adding 1.")
        n_steps += 1

    # Initialize SHM connections
    if dm == 'DM1':
        m2c = dao.shm(shm_names.SHM_DM1_M2C).get_data(semNb=8)
        dm_flat = dao.shm(shm_names.SHM_DM1_CHANNEL_0).get_data(semNb=8)
        dm_cmd_offset_shm = dao.shm(shm_names.SHM_DM1_CMD_OFFSET)
        dm_cmd_shm = dao.shm(shm_names.SHM_DM1_CMD)
    else:
        raise NotImplementedError('Currently only DM1 is available')
    if wfs == 'OCAM':
        wfscam = dao.shm(shm_names.SHM_OCAM_REDUCED_FRAME)
        validMask = dao.shm(shm_names.SHM_PYRAMID_VALID_PIXELS)
        refFrame = dao.shm(shm_names.SHM_OCAM_REFERENCE)
        refFrameBkp = dao.shm(shm_names.SHM_OCAM_REFERENCE_BEFORE_NCPA_OFFSET)
    else:
        raise NotImplementedError('Currently only OCAM is available')
    if camera == 'ORCA':
        cam_shm = dao.shm(shm_names.SHM_ORCA_FRAME)
        bg_shm = dao.shm(shm_names.SHM_ORCA_BACKGROUND)
        # cam_fps_shm = dao.shm(shm_names.SHM_ORCA_FPS)
        # cam_dit_shm = dao.shm(shm_names.SHM_ORCA_DIT)
    else:
        raise NotImplementedError('Currently only ORCA camera is implemented')

    nb_act = m2c.shape[0]
    total_modes = m2c.shape[1]
    
    # Store the accumulated optimized shape
    accumulated_modes = np.zeros(total_modes, dtype=np.float32)
    
    # Prepare the output metric cube [Nit, Nmodes, len(ramps)]
    metric_cube = np.zeros((Nit, n_modes, n_steps), dtype=np.float32)

    start_offset = dm_cmd_offset_shm.get_data(semNb=8)
    
    print("\nStarting NCPA Optimization")
    print(f"Modes: {n_modes}, Iterations: {Nit}, Ramp Steps: {n_steps}, Amplitude bounds: +/-{amp}")
    
    for it in range(Nit):
        print(f"\n--- Iteration {it + 1}/{Nit} ---")

        ramp_vals = np.linspace(-amp, amp, n_steps)/((4/3)**it)
        
        # Start from column 2 (index 2), discarding tip (0) and tilt (1)
        for i, mode_idx in enumerate(range(2, 2 + n_modes)):
            
            # Step 1: Measure initial metric before touching this mode
            init_metric = compute_metric(cam_shm, bg_shm, n_frames, use_gaussian=use_gaussian)
            
            # Step 2: Print dynamic line status
            sys.stdout.write(f"Mode {mode_idx:3d} | Initial metric: {init_metric:8.2f} | Final metric: ...\r")
            sys.stdout.flush()

            # Step 3: Run the ramp
            for j, step_amp in enumerate(ramp_vals):
                test_modes = accumulated_modes.copy()
                test_modes[mode_idx] += step_amp

                if step_amp == 0: # use initial metric
                    metric_cube[it, i, j] = init_metric
                else:
                    # Project modes to actuators and send to DM Offset channel
                    act_cmd = (m2c @ test_modes).reshape(nb_act, 1)
                    dm_cmd_offset_shm.set_data(start_offset + act_cmd)
                    metric = compute_metric(cam_shm, bg_shm, n_frames, use_gaussian=use_gaussian)
                    metric_cube[it, i, j] = metric

            # Step 4: Extract best amplitude from the ramp for this mode
            y = metric_cube[it, i, :].copy()
            pp = np.polyfit(ramp_vals,y,deg=2)
            if pp[0] < 0:
                best_delta_amp = -pp[1]/(2*pp[0])
                best_delta_amp = np.clip(best_delta_amp,-3/2*amp,3/2*amp)
            else: # fallback to argmax
                best_j = np.argmax(y)
                best_delta_amp = ramp_vals[best_j]
            
            # Step 5: Update the best accumulated modal basis
            accumulated_modes[mode_idx] += best_delta_amp.astype(np.float32)
            
            # Project the new best total shape to DM
            best_act_cmd = (m2c @ accumulated_modes).reshape(nb_act, 1)
            dm_cmd_offset_shm.set_data(start_offset + best_act_cmd)
            
            # Step 6: Measure final metric with the new optimized shape 
            final_metric = compute_metric(cam_shm, bg_shm, n_frames, use_gaussian=use_gaussian)
            
            # Overwrite the line with the final resulting string
            sys.stdout.write(f"Mode {mode_idx:3d} | Initial metric: {init_metric:8.2f} | Final metric: {final_metric:8.2f}\n")
            sys.stdout.flush()

    # Save the final DM command, averaging over 2000 frames and removing the flat
    Nframes = 2000
    avg_cmd = np.zeros_like(dm_flat)
    print('Averaging DM command...')
    for i in range(Nframes):
        avg_cmd += dm_cmd_shm.get_data(semNb=8)/Nframes
    dm_cmd = avg_cmd - dm_flat

    # Acquire reference frame    
    avg_frame = np.zeros_like(wfscam.get_data(semNb=8))
    print('Averaging ocam frames...')
    for i in range(Nframes):
        avg_frame += wfscam.get_data(semNb=8)/Nframes
    norm_frame = avg_frame/np.sum(avg_frame * validMask.get_data())
    
    # Set reference frame
    oldRef = refFrame.get_data()
    refFrameBkp.set_data(refFrameBkp.get_data()*0 + oldRef.astype(np.float32))
    refFrame.set_data(oldRef*0 + norm_frame.astype(np.float32))

    # Remove offset
    dm_cmd_offset_shm.set_data(start_offset)

    # Output and prints
    dm_modes = np.linalg.pinv(m2c) @ dm_cmd
    ncpa_modes = get_dmV2nm_conversion(m2c) * dm_modes.squeeze()
    print(f'NCPA mode 2-{n_modes} amplitudes [nm] are: {ncpa_modes[2:n_modes]}')
    print(f'Total NCPA RMS: {np.sqrt(np.sum(ncpa_modes**2)):1.0f}nm')

    # Save the history of metrics to disk
    tn = time.strftime("%Y%m%d_%H%M%S", time.localtime())
    out_filename = os.path.join(os.getenv("DAODATA"),'calibration','ncpa',f"{tn}_{dm}_{camera}_ncpa.npz")
    np.savez(out_filename, avg_cmd=dm_cmd, cmd_offset=best_act_cmd, ncpa_modes=ncpa_modes, metrics=metric_cube, frame_offset=norm_frame)
    print(f"\nOptimization finished. Data saved to '{out_filename}'.")



if __name__ == "__main__":
    args = parse_args()
    optimize_ncpa(dm = 'DM1', camera = 'ORCA', wfs = 'OCAM',
                amp=args.amp, n_modes=args.n_modes, 
                n_steps=args.n_steps, Nit=args.n_it, 
                n_frames=args.n_frames, use_gaussian=args.use_gaussian)