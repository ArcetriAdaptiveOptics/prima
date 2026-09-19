#!/usr/bin/env python3
#
# This init script create the shared memory for all the camera in harmoni
# to be run once after a reboot for example or if the SHM have been deleted

import shmlib
import numpy as np
import matplotlib.pyplot as plt

imShm = shmlib.shm('/tmp/testImage.im.shm')
ditShm = shmlib.shm('/tmp/testImageDit.im.shm')
fpsShm = shmlib.shm('/tmp/testImageFps.im.shm')
gainShm = shmlib.shm('/tmp/testImageGain.im.shm')

image = imShm.get_data()
# Create unit (1sec) fps
fps = fpsShm.get_data()*0+1
# Create unit (1usec) exposure time
dit = ditShm.get_data()*0+1
# Create unit (1usec) gain
gain = gainShm.get_data()*0+1

# set fps to 10 Hz
fpsShm.set_data(10*fps)
# set fps to 10 ms
ditShm.set_data(1e5*dit)
# Set gain to 1
gainShm.set_data(gain)

# plot the image
plt.ion()
plt.imshow(imShm.get_data())