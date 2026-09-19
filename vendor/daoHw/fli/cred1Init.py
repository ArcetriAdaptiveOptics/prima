#!/usr/bin/env python3

import dao
import numpy as np

im=dao.shm('/tmp/cred1.im.shm', np.zeros((320,256)).astype(np.uint16))
fps=dao.shm('/tmp/cred1Fps.im.shm', np.zeros((1,1)).astype(np.float32))
dit=dao.shm('/tmp/cred1Dit.im.shm', np.zeros((1,1)).astype(np.float32))
gain=dao.shm('/tmp/cred1Gain.im.shm', np.zeros((1,1)).astype(np.float32))
rsp=dao.shm('/tmp/cred1Rsp.im.shm', np.zeros((32,1)).astype(np.uint8))
cmd=dao.shm('/tmp/cred1Cmd.im.shm', np.zeros((32,1)).astype(np.uint8))

