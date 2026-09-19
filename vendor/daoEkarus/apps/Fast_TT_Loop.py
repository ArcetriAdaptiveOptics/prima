#!/usr/bin/env python3
#
import dao
import numpy as np
from daoEkarusShmNames import *
import time

fast_tt_res_shm = dao.shm(SHM_FASTTT_RESIDUAL_TT)
fast_tt_res_offload_shm = dao.shm(SHM_FASTTT_RESIDUAL_TT_OFFLOAD)
lpCmdFastTT = dao.shm(SHM_FASTTT_LOOP_CL_SWITCH)
lpLeakFastTT = dao.shm(SHM_FASTTT_LOOP_LEAK)
lpGainFastTT = dao.shm(SHM_FASTTT_LOOP_GAIN)
shm_offload_TT = dao.shm(SHM_DM_2_FASTTT_OFFLOAD_TOGGLE)
# modes_shm = dao.shm

# lpCmd = dao.shm(SHM_DM1_LOOP_CL_SWITCH)
fastTtCh1Shm = dao.shm(SHM_FASTTT_CHANNEL_1)
fastTtCh2Shm = dao.shm(SHM_FASTTT_CHANNEL_2)

max_freq = 100 # was 50/500 (offload/centering)
DT = 1/max_freq
next_time = time.perf_counter()

TT1 = fastTtCh1Shm.get_data()
TT2 = fastTtCh2Shm.get_data()

while 1:
    if shm_offload_TT.get_data()[0,0] == 1:
        data = -fast_tt_res_offload_shm.get_data(check=True, semNb=2)
    elif lpCmdFastTT.get_data()[0,0] == 1:
        data = fast_tt_res_shm.get_data(check=True, semNb=2)
    else:
        data = TT1*0

    if lpCmdFastTT.get_data()[0,0]:
        gain = lpGainFastTT.get_data()
        leak = lpLeakFastTT.get_data()
        TT1 = TT1 * leak - data * gain
        fastTtCh1Shm.set_data(TT1.astype(np.float32))
    else:
        TT1 = TT1 * 0
        fastTtCh1Shm.set_data(TT1.astype(np.float32))

    if shm_offload_TT.get_data()[0,0]:
        gain = lpGainFastTT.get_data()
        leak = lpLeakFastTT.get_data()
        TT2 = TT2 * leak - data * gain
        fastTtCh2Shm.set_data(TT2.astype(np.float32))
    else:
        TT2 = TT2 * 0
        fastTtCh2Shm.set_data(TT2.astype(np.float32))


    next_time += DT
    remaining = next_time - time.perf_counter()
    if remaining > 0:
        time.sleep(remaining)
    else:
        # We're behind schedule; resynchronize
        next_time = time.perf_counter()


# ############################### OLD SCRIPT ##########################
# while 1:
#     if shm_offload_TT.get_data()[0,0] == 0 and not lpCmd.get_data()[0,0]:
#         data = fast_tt_res_shm.get_data(check=True, semNb=2)
#         # max_freq = 500
#     elif shm_offload_TT.get_data()[0,0] == 1:
#         data = -fast_tt_res_offload_shm.get_data(check=True, semNb=2)
#         # max_freq = 50
#     else:
#         data = -fast_tt_res_offload_shm.get_data(check=True, semNb=2)*0
#         # max_freq = 50

#     DT = 1/max_freq

#     if lpCmdFastTT.get_data()[0,0]:
#         gain = lpGainFastTT.get_data()
#         leak = lpLeakFastTT.get_data()
#         TT = TT * leak - data * gain
#         fastTtShm.set_data(TT.astype(np.float32))
#     else:
#         TT = TT * 0
#         fastTtShm.set_data(TT.astype(np.float32))


#     next_time += DT
#     remaining = next_time - time.perf_counter()
#     if remaining > 0:
#         time.sleep(remaining)
#     else:
#         # We're behind schedule; resynchronize
#         next_time = time.perf_counter()


