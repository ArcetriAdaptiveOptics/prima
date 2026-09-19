#!/usr/bin/env python3
#
import dao
import numpy as np
import sys

cameraName = sys.argv[1]
pixelFormat = sys.argv[2]
shmPixelFormatName = f"/tmp/{cameraName}PixelFormat.im.shm"

# 0 = Mono12, 1 = Mono14 (see daoHwStandaloneCblueCtrl.c)
value = {"Mono12": 0, "Mono14": 1}[pixelFormat]

shm = dao.shm(shmPixelFormatName)
shm.set_data(shm.get_data()*0+value)
print(f"Setting PixelFormat to {pixelFormat}")
