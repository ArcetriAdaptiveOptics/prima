#!/usr/bin/env python3
#
# This init script create the shared memory for all the camera in harmoni
# to be run once after a reboot for example or if the SHM have been deleted

import shmlib
import numpy as np


imageSizeX = 694
imageSizeY = 516
scaoCam = shmlib.shm('/tmp/testImage.im.shm', \
                np.zeros((imageSizeX, imageSizeY)).astype(np.uint8))
fps = shmlib.shm('/tmp/testImageFps.im.shm', np.zeros((1,1)).astype(np.float32))
dit = shmlib.shm('/tmp/testImageDit.im.shm', np.zeros((1,1)).astype(np.float32))
gain = shmlib.shm('/tmp/testImageGain.im.shm', np.zeros((1,1)).astype(np.float32))
bin = shmlib.shm('/tmp/testImageBin.im.shm', np.zeros((1,1)).astype(np.int32))