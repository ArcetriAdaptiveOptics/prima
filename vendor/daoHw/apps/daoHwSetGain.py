#!/usr/bin/env python3
#
import dao
import numpy as np
import sys

cameraName = sys.argv[1]
gain = float(sys.argv[2])
shmGainName = f"/tmp/{cameraName}Gain.im.shm"

shm = dao.shm(shmGainName)
shm.set_data(shm.get_data()*0+gain)
print(f"Setting Gain to {gain}")

