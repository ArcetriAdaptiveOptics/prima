#!/usr/bin/env python3
#
import dao
import numpy as np
import sys
from daoEkarusShmNames import *

acq = dao.shm(SHM_CBLUE_ACQ)
acq.set_data(acq.get_data() * 0 + 1)
print("CBLUE Acquisition started.")
