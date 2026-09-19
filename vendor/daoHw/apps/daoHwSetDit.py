#!/usr/bin/env python3
#
import dao
import numpy as np
import sys

cameraName = sys.argv[1]
dit = float(sys.argv[2])
shmDitName = f"/tmp/{cameraName}Dit.im.shm"

shm = dao.shm(shmDitName)
# parameters in millisecond... convert to microsecond
shm.set_data(shm.get_data()*0+dit*1000)
print(f"Setting DIT to {dit} ms")

