#!/usr/bin/env python3
#

import os
import dao
import argparse
import daoEkarusShmNames as shm_names
import numpy as np


def parse_args():
    parser = argparse.ArgumentParser(
        description="Characterize the system's response on a mode"
    )
    parser.add_argument("mode", type=int, help="mode ids to be characterized")
    parser.add_argument("amp", type=float, help="RMS amplitude of the random commands")
    parser.add_argument("--dec", type=int, default=0, help="DM commands decimation. Default: 0")
    parser.add_argument("--n_steps", type=int, default=5000, help="number of random commands for the characterization. Default: 5000")
    return parser.parse_args()


def characterize_mode_dynamic(
    mode_id:int,
    amp:float,
    dec:int=0,
    N:int=5000,
    orders:int=8,
    sem:int=8,
):
    # Attach to Shared Memory streams
    m2c = dao.shm(shm_names.SHM_DM1_M2C).get_data(semNb=sem)
    c2m = dao.shm(shm_names.SHM_DM1_C2M).get_data(semNb=sem)
    dm_dist_shm = dao.shm(shm_names.SHM_DM1_CHANNEL_3)
    dm_cmd_shm = dao.shm(shm_names.SHM_DM1_CMD)
    wfs_modes_shm = dao.shm(shm_names.SHM_WFS1_RECONSTRUCTED_MODES_WITH_GAIN)

    nb_act = m2c.shape[0]
    n_wfs_modes = wfs_modes_shm.get_data().shape[0]

    # Pre-generate random disturbance
    mode_cmds = np.random.randn(N)*amp
    mode_cmds = np.clip(mode_cmds,-0.1,0.1)
    mode_cmds = mode_cmds.astype(np.float32)

    # Buffers to record telemetry over n_steps
    dm_tot_hist = np.zeros((nb_act, N), dtype=np.float32)
    wfs_modes_hist = np.zeros((n_wfs_modes, N), dtype=np.float32)

    for i in range(N):
        if i % (dec+1) == 0:
            # Send command
            dm_dist_shm.set_data(dm_dist_shm.get_data()*0 + m2c[:, mode_id] * mode_cmds[i]) 
        # Read response
        dm_tot_hist[:, i] = dm_cmd_shm.get_data(check=True, semNb=sem).flatten()
        wfs_modes_hist[:, i] = wfs_modes_shm.get_data(check=True, semNb=sem).flatten()

    # Reset DM channel 3 to zero after acquisition
    dm_dist_shm.set_data(np.zeros((nb_act, 1), dtype=np.float32))

    # Project DM total command vectors into modal space using C2M
    dm_modes_hist = c2m @ dm_tot_hist

    # Define input and output
    in_mode_cmd = dm_modes_hist[mode_id].copy()
    out_mode_meas = dm_modes_hist[mode_id].copy()

    err = np.zeros(orders)
    min_err = np.inf
    for jj in range(orders):
        M = jj+1
        X = np.zeros([N-M,M])
        for j in range(N-M):
            X[j,:] = in_mode_cmd[j:j+M][::-1]
        A = (np.linalg.pinv(X) @ out_mode_meas[M:])
        err[jj] = np.sum(abs(out_mode_meas[M:] - (X @ A)))
        if err[jj] < min_err:
            min_err = err[jj]
            best_coeffs = A.copy()

    print(err)
    print(f'Best regression coefficients {best_coeffs} found')

    fps = dao.shm(shm_names.SHM_OCAM_FPS).get_data(semNb=sem)[0,0]
    out_filename = os.path.join(os.getenv("DAODATA"),'calibration','dynamics',f"dm468_mode{mode_id}_{fps:1.0f}Hz_dynamics.npz")
    np.savez(out_filename, dm_modes_hist=dm_modes_hist, wfs_modes_hist=wfs_modes_hist, ar_coeffs=best_coeffs, m2c=m2c, cmd_hist=mode_cmds, reg_errors=err)
    print(f"\nCharacterization finished. Data saved to '{out_filename}'.")

    return best_coeffs


if __name__ == "__main__":
    args = parse_args()
    characterize_mode_dynamic(mode_id=args.mode,amp=args.amp,dec=args.dec,N=args.n_steps)
