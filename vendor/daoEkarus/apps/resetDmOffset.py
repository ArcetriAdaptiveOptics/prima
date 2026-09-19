#!/usr/bin/env python3
#
import dao
import time

from daoEkarusShmNames import *

dmCmd = dao.shm(SHM_DM1_CHANNEL_3)

pauseTime = 0.01

dmCmd.set_data(dmCmd.get_data() * 0)
time.sleep(pauseTime)
