#!/usr/bin/env python3
#

import dao
import numpy as np
import os

from daoEkarusShmNames import *

dm_flat = dao.shm(SHM_DM1_CHANNEL_0)
c2m = np.load(os.getenv("DAODATA") + "/inputs/dm468/dm486_c2z.npy").astype(np.float32)[:2]
m2c = np.load(os.getenv("DAODATA") + "/inputs/dm468/dm486_z2c.npy").astype(np.float32)[:, :2]

TT = c2m @ dm_flat.get_data()
new_flat = dm_flat.get_data() - m2c @ TT
dm_flat.set_data(new_flat.reshape(-1, 1).astype(np.float32))
