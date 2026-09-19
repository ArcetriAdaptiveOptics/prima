#!/usr/bin/env python3
#
import dao
import numpy as np
import sys
from daoEkarusShmNames import *

lpLeak = dao.shm(sys.argv[1])
lpLeak.set_data(lpLeak.get_data() * 0 + float(sys.argv[2]))
print(f"Loop leak set to {lpLeak.get_data()[0,0]}")
