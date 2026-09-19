#!/usr/bin/env python3
#
import dao
import os
import numpy as np
import sys
from daoEkarusShmNames import *

if __name__ == "__main__":
    cam = dao.shm(SHM_OCAM_FRAME)
    bg = dao.shm(SHM_OCAM_BACKGROUND)
    bgp = dao.shm(SHM_OCAM_DARK_MAP_PERCENT, np.zeros((1, 1)).astype(np.uint32))
    bk = bg.get_data() * 0
    bg.set_data(bk)
    nFrame = int(sys.argv[1])
    for k in range(nFrame):
        sys.stdout.write(f"\raveraging... {k+1}/{nFrame}")
        sys.stdout.flush()
        bk = bk + cam.get_data(check=True, semNb=3)
        bgp.set_data(bgp.get_data() * 0 + np.uint32(100 * (k + 1) / nFrame))
    print("\n")
    bk = bk / nFrame
    bg.set_data(bk)
    bgp.set_data(bgp.get_data() * 0 + np.uint32(100))

    np.save(os.getenv("DAODATA") + "/inputs/calibration/Dark.npy", bk)
