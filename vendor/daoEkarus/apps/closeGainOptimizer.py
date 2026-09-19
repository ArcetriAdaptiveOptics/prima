#!/usr/bin/env python3

import numpy as np
import dao
import daoEkarusShmNames as shm_names 

freq = dao.shm(shm_names.SHM_OCAM_FPS).get_data()[0,0]
lpLeak = dao.shm(shm_names.SHM_DM1_LOOP_LEAK).get_data()[0,0]
shmGains = dao.shm(shm_names.SHM_WFS1_RECONSTRUCTED_MODES_GAIN)
shmModes = dao.shm(shm_names.SHM_WFS1_RECONSTRUCTED_MODES_WITH_GAIN)

delay = 480e-6+92e-6+220e-6+375e-6
p = 0.3
r = -0.2

q_plus = 1e-2
q_minus = 5*q_plus

Nmodes = len(shmModes.get_data())
dt = 2*delay/freq+1

shift = int(np.ceil(dt))
frac_shift = shift-dt
N1 = np.zeros(Nmodes)
Ndt = np.zeros(Nmodes)

modes_vec = np.zeros([shift,Nmodes])
gains = shmGains.get_data()
new_gains = gains.copy()

ctr = int(0)

while 1:
    # Fill modes vector
    while ctr < shift:
        modes = shmModes.get_data(check=True, semNb=3)
        modes_vec[ctr] = modes.squeeze()
        ctr = int(ctr+1)
    nModes = np.sum(abs(modes)>0)
    m_dt = modes_vec[0]*(1-frac_shift) + modes_vec[1]*frac_shift
    m_k = modes_vec[-1]
    N1 = p*m_k**2 + (1-p)*N1
    Ndt = p*m_k[0]*m_dt + (1-p)*Ndt
    aux = Ndt[:nModes]/N1[:nModes]-r
    q = q_plus * (aux > 0) + q_minus * (aux <= 0)
    new_gains[:nModes] = np.dot(gains[:nModes],(1+np.dot(q,aux)))
    new_gains = np.clip(new_gains,1e-4,10)
    # Update gains
    shmGains.set_data(gains * 0 + new_gains.astype(np.float32))
    # Update modes vector
    modes_vec = np.roll(modes_vec,axis=0,shift=-1)
    modes_vec[-1] = shmModes.get_data(check=True, semNb=3).squeeze()

shmGains.set_data(np.ones_like(gains))