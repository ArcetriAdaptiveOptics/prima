#!/usr/bin/env python3
#
#%%
import dao
import numpy as np
import sys
from astropy.io import fits
import matplotlib.pyplot as plt
import threading

sys.path.append("/home/daouser/dao/Ekarus/daoEkarus/src/python/")
sys.path.append("/home/daouser/OOPAO/")
sys.path.append("/home/daouser/OOPAO/tutorials/EKARUS/")

from daoEkarusShmNames import *

dao.shm(SHM_OOPAO_MODE).set_data(dao.shm(SHM_OOPAO_MODE).get_data() * 0 + 1)

# %% OOPAO objects
import time
import matplotlib.pyplot as plt
import numpy as np
from OOPAO.calibration.CalibrationVault import CalibrationVault
from OOPAO.calibration.InteractionMatrix import InteractionMatrix
from OOPAO.tools.displayTools import cl_plot, displayMap
from Ekarus import Ekarus
import os

#%% Compute the OOPAO Objects

Ekatwin = Ekarus()
# telescope object
tel     = Ekatwin.tel
# source object VIS
ngs     = Ekatwin.ngs
# deformable mirror object
dm      = Ekatwin.dm
# Pyramid WFS object
wfs     = Ekatwin.wfs
# atmosphere object
atm     = Ekatwin.atm
# Tip/Tilt mirror object
tt = Ekatwin.tt
# parameter file
param   = Ekatwin.param

atm.initializeAtmosphere(telescope=tel)
atm.update()
print('here_0')

#%%

dao.shm(SHM_OCAM_GAIN).set_data(dao.shm(SHM_OCAM_GAIN).get_data() * 0 + wfs.cam.gain)
dao.shm(SHM_OCAM_FPS).set_data(
    dao.shm(SHM_OCAM_FPS).get_data() * 0 + int(1 / tel.samplingTime)
)


# get shm

# dao.shm(SHM_PYRAMID_VALID_PIXELS).set_data(
#     dao.shm(SHM_PYRAMID_VALID_PIXELS).get_data() * 0
#     + wfs.valid_signal_2D.astype(np.uint32)
#     )

ocam_fps = dao.shm(SHM_OCAM_FPS)
ocam_gain = dao.shm(SHM_OCAM_GAIN)
ocam_frame = dao.shm(SHM_OCAM_FRAME)
ocam_bg = dao.shm(SHM_OCAM_BACKGROUND)
pwfs_modulator = dao.shm(SHM_MODULATOR)
dm_commands = dao.shm(SHM_DM1_CMD)
dm_flat = dao.shm(SHM_DM1_CHANNEL_0)
atm_stop = dao.shm(SHM_DM1_ATM_STOP)
atm_stop.set_data(atm_stop.get_data() + 1)
atm_seeing = dao.shm(SHM_DM1_ATM_SEEING)
atm_wind_speed = dao.shm(SHM_DM1_ATM_WINDSPEED)
ocam_bg.set_data(ocam_bg.get_data()*0)
dm_flat.set_data(dm_flat.get_data() * 0)

print('here_1')
# ---------------------------
# Shared memory functions
# ---------------------------

#%%
def OcamGainCtrl(ocam_obj, ocam_shm):
    while 1:
        gain = ocam_shm.get_data(check=True)[0, 0]
        ocam_obj.gain = gain


def PyramidModulationCtrl(wfs_obj, modulation_shm):
    while 1:
        modulation = modulation_shm.get_data(check=True)[1, 0]
        wfs_obj.modulation = modulation


def AtmosphereWindSpeedCtrl(atm_obj, wind_speed_shm):
    while 1:
        wind_speed = wind_speed_shm.get_data(check=True)[0, 0] * (5 / 1000)
        atm_obj.windSpeed = [wind_speed]


def AtmosphereSeeingCtrl(atm_obj, seeing_shm):
    while 1:
        seeing_from_dao = seeing_shm.get_data(check=True)[0, 0] * (np.pi / 180 / 3600)
        r0 = (500e-9) / seeing_from_dao
        if r0 < 2:
            atm_obj.r0 = r0
            atm.generateNewPhaseScreen()


def WFSSamplingTimeCtrl(tel_obj, atm_obj, ocam_fps_shm):
    while 1:
        fps = ocam_fps_shm.get_data(check=True)[0, 0]
        tel_obj.samplingTime = 1 / fps
        # re-assign the wind-speed to the atmosphere to be in line with the new frequency rate
        atm_obj.windSpeed = atm_obj.windSpeed


# ---------------------------
# Set Shared memory threads
# ---------------------------

ocamGainThread = threading.Thread(
    target=OcamGainCtrl, args=(wfs.cam, ocam_gain), daemon=True
)
pyramidModulationThread = threading.Thread(
    target=PyramidModulationCtrl, args=(wfs, pwfs_modulator), daemon=True
)
atmosphereWindSpeedThread = threading.Thread(
    target=AtmosphereWindSpeedCtrl, args=(atm, atm_wind_speed), daemon=True
)
atmosphereSeeingThread = threading.Thread(
    target=AtmosphereSeeingCtrl, args=(atm, atm_seeing), daemon=True
)
wfsSamplingTimeThread = threading.Thread(
    target=WFSSamplingTimeCtrl,
    args=(tel, atm, ocam_fps),
    daemon=True,
)

ocamGainThread.start()
pyramidModulationThread.start()
atmosphereWindSpeedThread.start()
atmosphereSeeingThread.start()
wfsSamplingTimeThread.start()

# ---------------------------
# Simulation loop
# ---------------------------
running = True

ocam_frame.set_data(wfs.cam.frame.astype(np.uint16))

print(dm.coefs.shape, dm_commands.get_data(check=False, semNb=3).shape)

try:
    while running:
        print('running oopao')
        dm.coefs = np.squeeze(dm_commands.get_data(check=False, semNb=3))
        if atm_stop.get_data()[0, 0] == 0 and np.isfinite(atm.r0):
            atm.update()
            ngs**atm * tel * dm * wfs
        else:
            ngs**tel * dm * wfs
        ocam_frame.set_data(wfs.cam.frame.astype(np.uint16))

except KeyboardInterrupt:
     print("Interrupted by user. Exiting...")