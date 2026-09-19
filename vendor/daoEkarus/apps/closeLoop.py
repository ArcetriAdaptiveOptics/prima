#!/usr/bin/env python3
#
import dao
import numpy as np
from daoEkarusShmNames import *
import sys

lpCmd = dao.shm(sys.argv[1])
lpCmd.set_data(lpCmd.get_data() * 0 + 1)
print("Loop Closed")
