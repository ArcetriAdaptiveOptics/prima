"""Create the Prima SHM graph with safe default arrays (sim / cold start)."""
from __future__ import annotations

import numpy as np

from daoprima import shm as shm_mod
from daoprima import shm_names as N


def create_default_graph(frame_hw=(256, 256), n_modes=20):
    """Allocate the SHM images DaoPrima GUIs / bridges expect.

    Pattern mirrors daoEkarus ``daoEkarusCreateShm.py`` (vendor), adapted for
    140-act BMC + GigE WFS.
    """
    h, w = frame_hw
    n_act = N.SHM_DM1_N_ACTUATORS

    shm_mod.shm(N.SHM_WFS_FRAME, np.zeros((h, w), dtype=np.float32))
    shm_mod.shm(N.SHM_WFS_ACQ, np.ones((1, 1), dtype=np.uint32))
    shm_mod.shm(N.SHM_WFS_BACKGROUND, np.zeros((h, w), dtype=np.float32))
    shm_mod.shm(N.SHM_WFS_REFERENCE, np.zeros((h, w), dtype=np.float32))
    shm_mod.shm(N.SHM_WFS_FPS, np.array([[60.0]], dtype=np.float32))
    shm_mod.shm(N.SHM_WFS_EXPOSURE_MS, np.array([[10.0]], dtype=np.float32))

    shm_mod.shm(N.SHM_DM1_MASK, np.ones((n_act,), dtype=np.float32))
    for path in (
            N.SHM_DM1_CHANNEL_0, N.SHM_DM1_CHANNEL_1,
            N.SHM_DM1_CHANNEL_2, N.SHM_DM1_CHANNEL_3,
            N.SHM_DM1_CMD, N.SHM_DM1_CMD_OFFSET,
            N.SHM_DM1_RESIDUAL_ZONAL_COMMANDS):
        shm_mod.shm(path, np.zeros((n_act,), dtype=np.float32))

    # Identity-ish M2C placeholder (modes → actuators); replace after calib
    m2c = np.eye(n_act, n_modes, dtype=np.float32)
    shm_mod.shm(N.SHM_DM1_M2C, m2c)
    shm_mod.shm(N.SHM_DM1_C2M, m2c.T.copy())

    shm_mod.shm(N.SHM_DM1_LOOP_CL_SWITCH, np.zeros((1, 1), dtype=np.uint32))
    shm_mod.shm(N.SHM_DM1_LOOP_GAIN, np.array([[0.3]], dtype=np.float32))
    shm_mod.shm(N.SHM_DM1_LOOP_LEAK, np.array([[0.99]], dtype=np.float32))

    shm_mod.shm(N.SHM_WFS1_RECONSTRUCTED_MODES,
                np.zeros((n_modes,), dtype=np.float32))
    shm_mod.shm(N.SHM_WFS1_RECONSTRUCTED_MODES_GAIN,
                np.ones((n_modes,), dtype=np.float32))
    shm_mod.shm(N.SHM_WFS1_RECONSTRUCTED_MODES_WITH_GAIN,
                np.zeros((n_modes,), dtype=np.float32))
    shm_mod.shm(N.SHM_PYRAMID_SIGNAL, np.zeros((n_modes,), dtype=np.float32))
    shm_mod.shm(N.SHM_PYRAMID_PUPIL_FLUX, np.zeros((4,), dtype=np.float32))
    shm_mod.shm(N.SHM_PYRAMID_PUPIL_CENTERS, np.zeros((4, 2), dtype=np.float32))
    shm_mod.shm(N.SHM_PYRAMID_VALID_PIXELS, np.ones((h, w), dtype=np.uint8))

    # frame_id + per-stage stamps (DaoPrima divergence from daoEkarus)
    for path in (
            N.SHM_FRAME_ID, N.SHM_FRAME_ID_RECON,
            N.SHM_FRAME_ID_RTC, N.SHM_FRAME_ID_DM):
        shm_mod.shm(path, np.zeros((1, 1), dtype=np.uint32))

    # Modulator telemetry vector: [radius_mrad, freq_hz, cx, cy]
    shm_mod.shm(N.SHM_MODULATOR, np.array(
        [[1.5, 20.0, 0.0, 0.0]], dtype=np.float32))
    shm_mod.shm(N.SHM_FASTTT_CMD, np.zeros((2,), dtype=np.float32))
    shm_mod.shm(N.SHM_FASTTT_LOOP_CL_SWITCH, np.zeros((1, 1), dtype=np.uint32))
    shm_mod.shm(N.SHM_FASTTT_LOOP_GAIN, np.array([[0.5]], dtype=np.float32))
    shm_mod.shm(N.SHM_FASTTT_LOOP_LEAK, np.array([[0.99]], dtype=np.float32))

    # Placeholder reconstructor (modes from "slopes")
    shm_mod.shm(N.SHM_PYRAMID_2_DM1_REC,
                np.eye(n_modes, dtype=np.float32) * 0.1)

    return {
        'n_actuators': n_act,
        'n_modes': n_modes,
        'frame_hw': frame_hw,
        'has_dao': shm_mod.has_dao(),
    }
