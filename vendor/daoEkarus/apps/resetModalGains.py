#!/usr/bin/env python3

import dao
import numpy as np
import daoEkarusShmNames as shm_names 

shmGains = dao.shm(shm_names.SHM_WFS1_RECONSTRUCTED_MODES_GAIN)
shmGains.set_data(shmGains.get_data()*0 + np.ones_like(shmGains.get_data()))