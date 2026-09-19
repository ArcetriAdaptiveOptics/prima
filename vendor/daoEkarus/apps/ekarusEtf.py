#!/usr/bin/env python3
#

import argparse
import dao
import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
import time
import sys
from astropy.io import fits
import os
from ekalib import create_tracking_number

def TF_Her_Hcl_Hol_Hn(fp, loop_gain, Ti, Tau, Tdm, Tocam):
    # dfp = fp[1] - fp[0]
    I = 1j
    S = I * 2.0 * np.pi * fp
    # H_WFS = (1.-np.exp(-S*Ti)) / (S*Ti)
    H_WFS = np.exp(-1.0 * Ti / 2 * S)  # ; like in simulation
    H_RTC = np.exp(-1.0 * Tau * S)
    H_DM = np.exp(-1.0 * Tdm * S)
    H_READOUT = np.exp(-1.0 * Tocam * S)
    H_DAC = (1.0 - np.exp(-S * Ti)) / (S * Ti)
    CC = loop_gain / (1 - np.exp(-S * Ti))
    H_OL = H_WFS * H_READOUT * H_RTC * H_DAC * H_DM * CC
    H_CL = H_OL / (1 + H_OL)
    H_ER = 1.0 / (1.0 + H_OL)
    H_N = H_CL / H_WFS
    return H_ER, H_CL, H_OL, H_N


def parse_args():
    parser = argparse.ArgumentParser(
        description="Measure ETF for one mode."
    )

    parser.add_argument("mode", type=int, help="index of the mode to be used")
    parser.add_argument("amp_mode", type=float, help="amplitude of the mode to be used")
    parser.add_argument("fs", type=float, help="sampling frequency [Hz]")

    parser.add_argument(
        "-t",
        "--duration",
        type=float,
        default=30.0,
        help="duration of each acquisition, in seconds. Default: 30",
    )

    parser.add_argument(
        "--start",
        type=int,
        default=50,
        help="first sample used for ETF computation. Default: 50",
    )

    parser.add_argument(
        "--end",
        type=int,
        default=15000,
        help="last sample used for ETF computation. Default: 15000",
    )

    parser.add_argument(
        "-N",
        type=int,
        default=6,
        help="nperseg factor used as nperseg=N*64. Default: 6",
    )

    parser.add_argument(
        "--tau",
        type=float,
        default=0.000290+0.000021,
        help="RTC delay Tau [s]. Default: 0.000311", # RTC latency + data transfer to DM
    )

    parser.add_argument(
        "--tdm",
        type=float,
        default=0.000375, # 750/2
        help="DM delay Tdm [s]. Default: 0.000375",
    )

    parser.add_argument(
        "--tocam",
        type=float,
        default=0.000480+0.000092, # transfer delay is 240x240 16 bits on 10 Gbit/s port: 240x240x16/10^10=92e-6
        help="OCAM readout + data transfer Tocam [s]. Default: 0.000572",
    )

    parser.add_argument(
        "--sem",
        type=int,
        default=8,
        help="semaphore number used by get_data(check=True). Default: 8",
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="random seed. Default: none",
    )

    parser.add_argument(
        "--no-plot",
        action="store_true",
        help="do not show the matplotlib plot",
    )

    parser.add_argument(
        "--no-save",
        action="store_true",
        help="do not save the telemetry .npy file",
    )

    return parser.parse_args()


args = parse_args()

# Parameters
mode = args.mode
amp_mode = args.amp_mode
fs = args.fs

if args.seed is not None:
    np.random.seed(args.seed)

nIter = int(fs) * int(args.duration)

lpCmd = dao.shm("/tmp/dm1_lpCmd.im.shm")  # set closed loop
lpGain = dao.shm("/tmp/dm1_lpGain.im.shm")  # set closed loop
modes = dao.shm("/tmp/wfs1Modes.im.shm")  # measured modes  in system
dm = dao.shm("/tmp/dm1Cmd.im.shm")  # computed commands
dmDist = dao.shm("/tmp/dm1Cmd03.im.shm")  # any dm offset
m2c = dao.shm("/tmp/dm1m2c.im.shm")

nbAct = m2c.get_data().shape[0]

loop_gain = lpGain.get_data()[0, 0]
nMode = modes.get_data().shape[0]

if mode < 0 or mode >= nMode:
    print(f"ERROR: mode {mode} is outside valid range 0:{nMode - 1}")
    sys.exit(1)

modeCubeCL = np.zeros((nMode, nIter))
modeCubeOL = np.zeros((nMode, nIter))

print("\n======================================================")
print("ETF TEST PARAMETERS")
print("======================================================")
print(f"mode        : {mode}")
print(f"amp_mode    : {amp_mode}")
print(f"fs          : {fs} Hz")
print(f"duration    : {args.duration} s")
print(f"nIter       : {nIter}")
print(f"loop_gain   : {loop_gain}")
print(f"nMode       : {nMode}")
print(f"nbAct       : {nbAct}")
print(f"start       : {args.start}")
print(f"end         : {args.end}")
print(f"N           : {args.N}")
print(f"nperseg     : {args.N * 64}")
print(f"Tau         : {args.tau}")
print(f"Tdm         : {args.tdm}")
print(f"sem         : {args.sem}")
print("======================================================\n")

#
modeVector = np.zeros(m2c.get_data().shape[1])
modeVector[mode] = 1
modeCmd = np.matmul(m2c.get_data(), modeVector).reshape(nbAct, 1)

random_cmd = np.random.randn(nbAct, nIter).astype(np.float32)
randModes = np.zeros((nMode, nIter))

print("Generating random disturbance...")

for i in range(nIter):
    modeVector[mode] = 1 - 2 * np.random.rand()
    modeCmd = np.matmul(m2c.get_data(), modeVector).reshape(nbAct, 1)
    random_cmd[:, i] = amp_mode * modeCmd.flatten()

print("Random disturbance ready.")
print(f"random_cmd rms : {np.std(random_cmd):.4g}")
print(f"random_cmd min : {np.min(random_cmd):.4g}")
print(f"random_cmd max : {np.max(random_cmd):.4g}")

lpCmd.set_data(lpCmd.get_data() * 0 + 1)
time.sleep(0.1)

#  Save closed Loop in modal space
print("\nStarting closed-loop acquisition...")
t0 = time.time()

dm.get_data(check=True, semNb=args.sem)
modes.get_data(check=True, semNb=args.sem)

for i in range(nIter):
    # apply distrubance frame
    dmDist.set_data(dmDist.get_data() * 0 + random_cmd[:, i].reshape(nbAct, 1))
    # dm.get_data(check=True, semNb=args.sem)
    modeCubeCL[:, i] = modes.get_data(check=True, semNb=args.sem).flatten()

    if i % max(1, nIter // 20) == 0:
        print(f"CL {100*i/nIter:5.1f}% ({i}/{nIter})", end="\r", flush=True)

print(f"CL 100.0% ({nIter}/{nIter})")
print(f"Closed-loop acquisition done in {time.time() - t0:.1f} s")

dmDist.set_data(dmDist.get_data() * 0)

# RUN OPEN LOOP
lpCmd.set_data(lpCmd.get_data() * 0)
time.sleep(0.1)

print("\nStarting open-loop acquisition...")
t0 = time.time()

dm.get_data(check=True, semNb=args.sem)
modes.get_data(check=True, semNb=args.sem)

for i in range(nIter):
    # apply distrubance frame
    dmDist.set_data(dmDist.get_data() * 0 + random_cmd[:, i].reshape(nbAct, 1))
    # dm.get_data(check=True, semNb=9)
    modeCubeOL[:, i] = modes.get_data(check=True, semNb=args.sem).flatten()

    if i % max(1, nIter // 20) == 0:
        print(f"OL {100*i/nIter:5.1f}% ({i}/{nIter})", end="\r", flush=True)

print(f"OL 100.0% ({nIter}/{nIter})")
print(f"Open-loop acquisition done in {time.time() - t0:.1f} s")

dmDist.set_data(dmDist.get_data() * 0)


out = modeCubeCL  # (modal_reconstructor@signal_out.T)
inp = modeCubeOL  # (modal_reconstructor@signal_in.T)


# time step
samplingTime = 1 / fs


end = args.end  # where to stop
start = args.start  # where to start

if end > nIter:
    print(f"\nWARNING: end={end} is larger than nIter={nIter}. Using end=nIter.")
    end = nIter

if start >= end:
    print(f"ERROR: start={start} must be smaller than end={end}")
    sys.exit(1)

mod_test = [mode]  # index of the mode that was used during the acquisition
N = args.N

for i_mode in range(1):
    mode = mod_test[i_mode]
    # DSP of the closed-loop data (residuals)
    f, Poi = signal.csd(out[mode, start:end], inp[mode, start:end], fs, nperseg=N * 64)
    # DSP of the open-loop data (open loop)
    f, Pii = signal.csd(inp[mode, start:end], inp[mode, start:end], fs, nperseg=N * 64)
    fp = (f.copy())[1:]
    Ti = 1 * samplingTime
    Tau = args.tau  
    Tdm = args.tdm
    Tocam = args.tocam

    Her, Hcl, Hol, Hn = TF_Her_Hcl_Hol_Hn(fp, loop_gain, Ti, Tau, Tdm, Tocam)

    Her_dB = 20.0 * np.log10(np.abs(Her))
    FTR = 20.0 * np.log10(np.abs(Poi / Pii))
    DSP = 20.0 * np.log10(np.abs(Pii))

    print("\nETF STATUS")
    print("----------")
    print(f"mode        : {mode}")
    print(f"loop_gain   : {loop_gain}")
    print(f"CL rms      : {np.std(out[mode, start:end]):.4g}")
    print(f"OL rms      : {np.std(inp[mode, start:end]):.4g}")
    print(f"FTR min     : {np.min(FTR):.2f} dB")
    print(f"FTR max     : {np.max(FTR):.2f} dB")

    if not args.no_plot:
        plt.figure()
        plt.semilogx(f[1:], Her_dB, label="RTF from Theory")
        plt.semilogx(f, FTR, label="RTF from WFS slopes")
        plt.title("KL Mode " + str(mode) + " - Gain " + str(loop_gain) +" - Latency " + str((Ti + Tau + Tdm + Tocam)*1000) +
            " ms \n Ti = " +str(np.round(Ti*1000,3)) +" ms, Tau = " +
            str(np.round(Tau*1000,3)) +" ms, Tdm = " +str(np.round(Tdm*1000,3)) +" ms, Tocam = " +str(np.round(Tocam*1000,3)) +" ms" )
        plt.grid(which="both")
        plt.xlabel("Frequency [Hz]")
        plt.ylabel(r"20 log($\frac{\Phi_{res}}{\Phi_{turb}}$)")
        plt.legend()

if not args.no_plot:
    plt.show()

data_rtf = {
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
    "loop_gain": loop_gain,
    "FTR": FTR,
    "frequency_vector": f,
}
print("\n")

desc = f"mode_{mode}_amp_{amp_mode}_fs_{fs}_gain_{np.round(loop_gain,2)}"

data_objects = {
    "data_rtf": data_rtf,
}
if not args.no_save:
    dao_data = os.getenv("DAODATA")
    if dao_data is None:
        print("ERROR: DAODATA is not defined, cannot save.")
        sys.exit(1)
    for i_file in data_objects:
        folder_path = create_tracking_number(name_data=i_file, data = data_objects[i_file])
        with open(os.getenv("DAODATA") + "/telemetry/tmp/current_telemetry_folder.txt", "w") as f:
            f.write(folder_path)
            f.close()
    # outfile = dao_data + "/telemetry/etf_" + desc + ".npy"
    # print(f"Saving in {outfile}")
    # np.save(outfile, data)
else:
    print("Not saving because --no-save was used.")