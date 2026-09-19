#!/usr/bin/env python3
#
import dao
import numpy as np
import sys
from daoEkarusShmNames import *

lpGain = dao.shm(sys.argv[1])
lpGain.set_data(lpGain.get_data() * 0 + float(sys.argv[2]))
print(f"Loop gain set to {lpGain.get_data()[0,0]}")
