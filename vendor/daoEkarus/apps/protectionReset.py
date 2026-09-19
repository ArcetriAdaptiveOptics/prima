#!/usr/bin/env python3
#
import dao
import numpy as np
import sys
from daoEkarusShmNames import *

command = "protection reset"
print(command)
cmdShm = dao.shm(SHM_OCAM_CMD)
command += "\0" + "000000000000000000000000000000000000"
cmdShm.set_data(np.frombuffer(command.encode("utf8"), dtype=np.uint8))
