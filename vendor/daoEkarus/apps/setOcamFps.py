#!/usr/bin/env python3
#
import dao
import numpy as np
import sys
from daoEkarusShmNames import *

is_simulation = dao.shm(SHM_OOPAO_MODE).get_data()[0, 0]
fps_shm = dao.shm(SHM_OCAM_FPS)

val = sys.argv[1]

if is_simulation == 0:
    command = "fps " + val
    print(command)
    cmdShm = dao.shm(SHM_OCAM_CMD)
    command += "\0" + "000000000000000000000000000000000000"
    cmdShm.set_data(np.frombuffer(command.encode("utf8"), dtype=np.uint8))
else:
    fps_shm.set_data(fps_shm.get_data() * 0 + int(val))
