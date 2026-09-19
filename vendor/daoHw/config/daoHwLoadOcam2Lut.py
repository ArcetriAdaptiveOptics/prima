#!/usr/bin/env python3

import sys, getopt
import numpy as np
import astropy.io.fits as pf
import time
import os
import dao
import daoTools

dirPath = os.getenv('DAODATA')+'/config/'
if not os.path.exists(dirPath):
    os.makedirs(dirPath)
descrambler = np.loadtxt(dirPath + 'ocam2Lut.txt', delimiter = ',').astype(np.int32)

descramblerBin = np.concatenate((descrambler[0:14400][0::2], descrambler[43200:][0::2]))

lut = dao.shm('/tmp/ocam2Lut.im.shm', descrambler.reshape(descrambler.shape[0],1))
lutbin = dao.shm('/tmp/ocam2LutBin.im.shm', descramblerBin.reshape(descramblerBin.shape[0],1))
