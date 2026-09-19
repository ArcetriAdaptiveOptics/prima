#!/usr/bin/env python3
#

import os
import sys
import numpy as np
import dao
from PyQt5.QtWidgets import QApplication
import daoEkarusShmNames as shm_names
from ekalib import compute_valid_pix_map
from validPixelSelector import ValidPixelSelector

def main():
    # argv[1] is the number of frames (nbFramePupilBox value in the GUI).
    shm_dm_channel_3 = dao.shm(shm_names.SHM_DM1_CHANNEL_3)
    shm_ocam_frame = dao.shm(shm_names.SHM_OCAM_REDUCED_FRAME)
    shm_valid_pix_map = dao.shm(shm_names.SHM_PYRAMID_VALID_PIXELS)
    shm_valid_pix_map_std = dao.shm(shm_names.SHM_PYRAMID_VALID_PIXELS_STD)
    max_nCentroids =  dao.shm(shm_names.SHM_PYRAMID_SIGNAL).get_data().shape[0]

    if sys.argv[1] == 'skip_measurement':
        # print('here')
        valid_pix_map = shm_valid_pix_map_std.get_data()
    else:
        nFrame = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
        amp = 0.05  # reduced from 0.3 to minimize DM ageing
        valid_pix_map = compute_valid_pix_map(
            shm_dm_channel_3, shm_ocam_frame, amp=amp, n_iter=nFrame
        )
        shm_valid_pix_map_std.set_data(shm_valid_pix_map_std.get_data()*0 + valid_pix_map)
    app = QApplication(sys.argv)

    dlg = ValidPixelSelector(valid_pix_map)   # no parent: standalone window
    if not dlg.exec_():
        print("Cancelled; valid pixels unchanged.")
        return

    valid_pix = dlg.result_mask()

    existing = shm_valid_pix_map.get_data()
    if valid_pix.shape != existing.shape:
        print(
            f"ERROR: mask shape {valid_pix.shape} != SHM shape {existing.shape}; "
            "not writing valid pixels."
        )
        sys.exit(1)

    if valid_pix.shape[0] > max_nCentroids:
        print(
            f"ERROR: mask shape {valid_pix.shape} bigger than maximum allowed ({max_nCentroids} pixels); "
            "not writing valid pixels."
        )
        sys.exit(1)
        
    shm_valid_pix_map.set_data(shm_valid_pix_map.get_data()*0 + valid_pix.astype(np.uint32))
    np.save(os.getenv("DAODATA") + "/inputs/calibration/valid_pix_map.npy", valid_pix)


if __name__ == "__main__":
    main()


# #!/usr/bin/env python3
# #
# import dao
# import os
# import numpy as np
# import sys
# import daoEkarusShmNames as shm_names
# from ekalib import select_valid_pixels, mask_from_frame

# nFrame = int(sys.argv[1])

# shm_dm_channel_3 = dao.shm(shm_names.SHM_DM1_CHANNEL_3)
# shm_ocam_frame = dao.shm(shm_names.SHM_OCAM_REDUCED_FRAME)
# shm_valid_pix_map = dao.shm(shm_names.SHM_PYRAMID_VALID_PIXELS)

# amp = 0.05 # reduced from 0.3 to minimize DM ageing
# threshold = 0.03

# valid_pix_map = select_valid_pixels(shm_dm_channel_3, shm_ocam_frame, threshold, amp, nFrame, dofilter=True)
# # valid_pix_map = mask_from_frame(shm_dm_channel_3, shm_ocam_frame, amp, nFrame) # circular pupils
# shm_valid_pix_map.set_data(valid_pix_map.astype(np.uint32))

# # dm1z2c = np.load(os.getenv("DAODATA") + "/inputs/dm468/M2C_KL_OOPAO_central_obstruction.npy").astype(np.float32) # synthetic SPECULA
# # dm1z2c = np.load(os.getenv("DAODATA") + "/inputs/dm468/M2C_KL_simul_slaves_cut.npy").astype(np.float32)/150 # synthetic SPECULA
# # n_act_dm1 = 468
# # m2c = np.zeros((n_act_dm1,n_act_dm1)).astype(np.float32)
# # W,H = dm1z2c.shape
# # m2c[:, :H] = dm1z2c
# # dm1m2c = dao.shm(shm_names.SHM_DM1_M2C, m2c)
# # valid_mask = np.load(os.getenv("DAODATA") + "/inputs/" + "OnSky_pixMask.npy").astype(np.uint32)
# # shm_valid_pix_map.set_data(valid_mask.astype(np.uint32))

# np.save(os.getenv("DAODATA") + "/inputs/Papyrus/valid_pix_map.npy", valid_pix_map)