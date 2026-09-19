#!/usr/bin/env python3

import numpy as np
import matplotlib.pyplot as plt
import dao
import getopt
import sys
import time

if __name__ == '__main__':
    imunscrShmName = '/tmp/ocam2unscrCamera.im.shm'
    imscrShmName = '/tmp/ocam2Camera.im.shm'
    lutShmName = '/tmp/ocam2Lut.im.shm'
    try:
        opts, args = getopt.getopt(sys.argv[1:],"hu:s:l:",["help", "imunscrShm=", "imscrShm=", "lutShm"])
    except getopt.GetoptError:
      print('err, usage: daoHwOcamDescramble.py.py -u <imunscrShm> -s <imscrShm> -l <lutShm>')
      sys.exit(2)
    for opt, arg in opts:
        if opt == '-h':
            print('daoPrepCentroidLut.py daoHwOcamDescramble.py.py -u <imunscrShm> -s <imscrShm> -l <lutShm>')
            sys.exit()
        elif opt in ("-u", "--imunscrShm"):
            imunscrShmName = str(arg)
        elif opt in ("-s", "--imscrShm"):
            imscrShmName = str(arg)
        elif opt in ("-l", "--lutShm"):
            lutShmName = str(arg)

imlut = dao.shm(lutShmName);
descrambler = imlut.get_data()
imunscr = dao.shm(imunscrShmName)
imscr = dao.shm(imscrShmName)

# get size of unsc image
imgSize = imunscr.get_data().T.shape 
img=imunscr.get_data().reshape(imgSize[0], imgSize[1])

img_unscrambled_vector = np.zeros(np.shape(descrambler)[0])

while 1:
    img=(imunscr.get_data(check=True).reshape(imgSize[0], imgSize[1])).astype(np.uint16)
    cnt = imunscr.get_counter()
    sys.stdout.write(f"\rimage coutner = {cnt}")
    img16 = np.zeros((imgSize[0], int(imgSize[1] / 2)))
    for i in range(0, imgSize[1], 2):
        img16[:, int (i / 2)] = (img[:, i + 1]<<8) + (img[:, i])
    img16_vector = img16.flatten()
    for i in range(0, np.shape(descrambler)[0]):
        img_unscrambled_vector[i] = img16_vector[descrambler[i]]
    imscr.set_data(img_unscrambled_vector.reshape(240, 240).astype(np.uint16))

