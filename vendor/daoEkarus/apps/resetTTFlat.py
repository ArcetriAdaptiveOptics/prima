#!/usr/bin/env python3
#
import dao
import numpy as np
import astropy.io.fits as fits
import sys
import os
from daoEkarusShmNames import *

fastTT_flat = dao.shm(SHM_FASTTT_CHANNEL_0)

fastTT_flat.set_data((fastTT_flat.get_data() * 0 + 50.).astype(np.float32))
