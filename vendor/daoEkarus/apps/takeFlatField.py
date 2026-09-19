#!/usr/bin/env python3
#
import sys
import dao
import daoEkarusShmNames as shm_names
import numpy as np


def main():
    ocamCal = dao.shm(shm_names.SHM_OCAM_REDUCED_FRAME)
    ff = dao.shm(shm_names.SHM_OCAM_FLAT_FIELD)

    nFrame = 1000
    if len(sys.argv) > 1:
        nFrame = int(sys.argv[1])
    acc = ocamCal.get_data().astype(np.float64) * 0
    for k in range(nFrame):
        sys.stdout.write(f"\raveraging... {k+1}/{nFrame}")
        sys.stdout.flush()
        acc = acc + ocamCal.get_data(check=True, semNb=5)
    print()

    avg = (acc / nFrame)

    flux = avg.sum()
    if flux == 0:
        print("ERROR: zero flux on the valid pixels; reference not updated.")
        sys.exit(1)

    ff.set_data(ff.get_data() * 0 + (avg / flux).astype(np.float32))


if __name__ == "__main__":
    main()
