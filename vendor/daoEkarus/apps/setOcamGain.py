#!/usr/bin/env python3
#
import dao
import numpy as np
import sys
from daoEkarusShmNames import *

is_simulation = dao.shm(SHM_OOPAO_MODE).get_data()[0, 0]
gain_shm = dao.shm(SHM_OCAM_GAIN)

val = sys.argv[1]

if is_simulation == 0:
    command = "gain " + val
    print(command)
    cmdShm = dao.shm(SHM_OCAM_CMD)
    command += "\0" + "000000000000000000000000000000000000"
    cmdShm.set_data(np.frombuffer(command.encode("utf8"), dtype=np.uint8))
else:
    gain_shm.set_data(gain_shm.get_data() * 0 + int(val))
