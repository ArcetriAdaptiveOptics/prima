#!/usr/bin/env python3
#
import dao
import numpy as np
import sys

cameraName = sys.argv[1]
fps = float(sys.argv[2])
shmFpsName = f"/tmp/{cameraName}Fps.im.shm"

shm = dao.shm(shmFpsName)
shm.set_data(shm.get_data()*0+fps)
print(f"Setting FPS to {fps}")

