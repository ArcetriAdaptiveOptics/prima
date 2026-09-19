#!/usr/bin/env python3
#
import dao
import numpy as np
import sys
from daoEkarusShmNames import *

acq = dao.shm(SHM_OCAM_RAW_ACQ)
acq.set_data(acq.get_data() * 0 + 1)
print("OCAM2K Acquisition started.")
