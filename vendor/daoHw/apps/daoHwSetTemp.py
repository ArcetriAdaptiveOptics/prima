#!/usr/bin/env python3
#
import dao
import numpy as np
import sys

cameraName = sys.argv[1]
setTemp = float(sys.argv[2])
shmSetTempName = f"/tmp/{cameraName}SetTemp.im.shm"

shm = dao.shm(shmSetTempName)
shm.set_data(shm.get_data()*0+setTemp)
print(f"Setting FPS to {setTemp}")

