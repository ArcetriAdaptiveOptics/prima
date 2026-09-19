#!/usr/bin/env python3
#

import dao
import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
import time
import sys
from astropy.io import fits
import os
from daoEkarusShmNames import *
from tqdm import tqdm

def TF_Her_Hcl_Hol_Hn(fp, loop_gain, Ti, Tau, Tdm):
    dfp = fp[1] - fp[0]
    I = 1j
    S = I * 2.0 * np.pi * fp
    # H_WFS = (1.-np.exp(-S*Ti)) / (S*Ti)
    H_WFS = np.exp(-1.0 * Ti / 2 * S)  # ; like in simulation
    H_RTC = np.exp(-1.0 * Tau * S)
    H_DM = np.exp(-Tdm * S)
    H_DAC = (1.0 - np.exp(-S * Ti)) / (S * Ti)
    CC = loop_gain / (1 - np.exp(-S * Ti))
    H_OL = H_WFS * H_RTC * H_DAC * H_DM * CC
    H_CL = H_OL / (1 + H_OL)
    H_ER = 1.0 / (1.0 + H_OL)
    H_N = H_CL / H_WFS
    return H_ER, H_CL, H_OL, H_N


if sys.argv[1] == "-h" or sys.argv[1] == "--help":
    print("Usage: etf3.py <mode> <amp_mode> <fs>")
    print("mode: index of the mode to be used")
    print("amp_mode: amplitude of the mode to be used")
    print("fs: sampling frequency")
    sys.exit(0)
# Parameters
mode = int(sys.argv[1])
amp_mode = float(sys.argv[2])  # numerically add noise or use photon noise
# sampling frequency
fs = float(sys.argv[3])

nIter = int(fs) * 30
nbAct = 468

lpCmd = dao.shm(SHM_DM1_LOOP_CL_SWITCH)  # set closed loop
lpGain = dao.shm(SHM_DM1_LOOP_GAIN)  # set closed loop
modes = dao.shm(SHM_WFS1_RECONSTRUCTED_MODES)  # measured modes  in system
dm = dao.shm(SHM_DM1_CHANNEL_1)  # computed commands
dmDist = dao.shm(SHM_DM1_CHANNEL_2)  # any dm offset
dmCmd = dao.shm(SHM_DM1_CMD)  # any dm offset
m2c = dao.shm(SHM_DM1_M2C)

gain_ramp = np.linspace(0.1, 0.6, 7)
etf_ramp = {}

for gain in tqdm(gain_ramp):
    lpGain.set_data(lpGain.get_data()*0 + gain.astype(np.float32))
    loop_gain = lpGain.get_data()[0, 0]
    nMode = modes.get_data().shape[0]
    modeCubeCL = np.zeros((nMode, nIter))
    modeCubeOL = np.zeros((nMode, nIter))

    #
    modeVector = np.zeros(m2c.get_data().shape[1])
    modeVector[mode] = 1
    modeCmd = np.matmul(m2c.get_data(), modeVector).reshape(468, 1)

    random_cmd = np.random.randn(nbAct, nIter).astype(np.float32)
    randModes = np.zeros((nMode, nIter))

    for i in range(nIter):
        modeVector[mode] = 1 - 2 * np.random.rand()
        modeCmd = np.matmul(m2c.get_data(), modeVector).reshape(468, 1)
        random_cmd[:, i] = amp_mode * modeCmd.flatten()

    lpCmd.set_data(lpCmd.get_data() * 0 + 1)
    time.sleep(0.1)

    #  Save closed Loop in modal space
    dm.get_data(check=True, semNb=8)
    modes.get_data(check=True, semNb=8)
    for i in range(nIter):
        # apply distrubance frame
        dmDist.set_data(dmDist.get_data() * 0 + random_cmd[:, i].reshape(nbAct, 1))
        # dm.get_data(check=True, semNb=8)
        modeCubeCL[:, i] = modes.get_data(check=True, semNb=8).flatten()


    dmDist.set_data(dmDist.get_data() * 0)
    # RUN OPEN LOOP
    lpCmd.set_data(lpCmd.get_data() * 0)
    time.sleep(0.1)

    dm.get_data(check=True, semNb=8)
    modes.get_data(check=True, semNb=8)
    for i in range(nIter):
        # apply distrubance frame
        dmDist.set_data(dmDist.get_data() * 0 + random_cmd[:, i].reshape(nbAct, 1))
        # dm.get_data(check=True, semNb=9)
        modeCubeOL[:, i] = modes.get_data(check=True, semNb=8).flatten()

    dmDist.set_data(dmDist.get_data() * 0)


    out = modeCubeCL  # (modal_reconstructor@signal_out.T)
    inp = modeCubeOL  # (modal_reconstructor@signal_in.T)


    # time step
    samplingTime = 1 / fs


    end = 10000  # where to stop
    start = 10  # where to start

    mod_test = [mode]  # index of the mode that was used during the acquisition
    N = 6

    for i_mode in range(1):
        mode = mod_test[i_mode]
        # DSP of the closed-loop data (residuals)
        f, Poi = signal.csd(out[mode, start:end], inp[mode, start:end], fs, nperseg=N * 64)
        # DSP of the open-loop data (open loop)
        f, Pii = signal.csd(inp[mode, start:end], inp[mode, start:end], fs, nperseg=N * 64)
        fp = (f.copy())[1:]
        Ti = 1 * samplingTime
        Tau = 0.00065  # 1*samplingTime/3
        Tdm = 0.0005  # 1*samplingTime/4

        Her, Hcl, Hol, Hn = TF_Her_Hcl_Hol_Hn(fp, loop_gain, Ti, Tau, Tdm)

        Her_dB = 20.0 * np.log10(np.abs(Her))
        FTR = 20.0 * np.log10(np.abs(Poi / Pii))
        DSP = 20.0 * np.log10(np.abs(Pii))

        plt.figure()
        plt.semilogx(f[1:], Her_dB, label="RTF from Theory")
        plt.semilogx(f, (FTR), label="RTF from WFS slopes")
        plt.title("KL Mode " + str(mod_test[i_mode]) + "," + str(Ti + Tau + Tdm))
        plt.grid(which="both")
        plt.xlabel("Frequency [Hz]")
        plt.ylabel(r"20 log($\frac{\Phi_{res}}{\Phi_{turb}}$)")
        plt.legend()

    plt.show()

    data = {
        "out": out,
        "inp": inp,
        "fs": fs,
        "mode": mode,
        "amp_mode": amp_mode,
        "random+cmd": random_cmd,
        "N": N,
        "end": end,
        "start": start,
        "mod_test": mod_test,
        "gain": loop_gain
    }

    etf_ramp[f"gain_{loop_gain:.2f}"] = data

print("\n")
desc = f"mode_{mode}_amp_{amp_mode}_fs_{fs}_gain_{loop_gain}"
print(f"Saving in $DAODATA/telemetry/etf_{desc}.npy")
np.save(os.getenv("DAODATA") + "/telemetry/etf_ramp" + desc + ".npy", etf_ramp, allow_pickle=True)
