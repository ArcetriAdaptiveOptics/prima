"""SHM bridges for DaoPrima — DAO path (no plico for science DM).

Architecture (daoEkarus / daoHw)::

    [GUI / Python loop / daoBase]
            │  writes float[140]
            ▼
    /tmp/prima_dm1Cmd.im.shm
            │
    [daodm_bmc_ctrl]  →  BMC Multi-DM USB (or sim)
            │
         Multi Driver

Camera may still use Aravis/direct in Drop 1; pysilico↔SHM remains optional.
"""
from __future__ import annotations

import time
from typing import Optional

import numpy as np

from daoprima import shm as shm_mod
from daoprima import shm_names as N


class ShmCommandWriter:
    """Write a shape into the DM command SHM (GUI / loop side)."""

    def __init__(self, shm_path: str = N.SHM_DM1_CMD,
                 n_act: int = N.SHM_DM1_N_ACTUATORS):
        self.n_act = n_act
        self.shm = shm_mod.shm(shm_path, np.zeros(n_act, dtype=np.float32))

    def set_shape(self, shape) -> None:
        arr = np.asarray(shape, dtype=np.float32).ravel()
        if arr.size != self.n_act:
            arr = np.resize(arr, self.n_act)
        self.shm.set_data(arr)

    def get_shape(self) -> np.ndarray:
        return np.asarray(self.shm.get_data(), dtype=float).ravel()


class CameraToShmBridge:
    """Pull frames from a camera client into SHM_WFS_FRAME."""

    def __init__(self, camera_client, shm_path: str = N.SHM_WFS_FRAME,
                 period_s: float = 1.0 / 60.0):
        self.camera = camera_client
        self.shm = shm_mod.shm(shm_path)
        self.fps_shm = shm_mod.shm(N.SHM_WFS_FPS)
        self.period_s = period_s

    def step(self):
        if hasattr(self.camera, 'getFutureFrames'):
            frame = np.asarray(
                self.camera.getFutureFrames(1).toNumpyArray(),
                dtype=np.float32)
        else:
            frame = np.asarray(self.camera.read(), dtype=np.float32)
        if frame.ndim == 3:
            frame = frame[0]
        self.shm.set_data(frame)
        self.fps_shm.set_data(np.array(
            [[1.0 / max(self.period_s, 1e-6)]], dtype=np.float32))
        return frame

    def run_forever(self, n_steps: Optional[int] = None):
        i = 0
        while n_steps is None or i < n_steps:
            self.step()
            time.sleep(self.period_s)
            i += 1


# Back-compat alias name used by older Drop2 scaffold
class ShmToDmBridge(ShmCommandWriter):
    """Deprecated name — use ShmCommandWriter; HW apply is daodm_bmc_ctrl."""

    def step(self) -> bool:
        return False

    def run_forever(self, n_steps: Optional[int] = None):
        raise RuntimeError(
            'ShmToDmBridge no longer pushes to plico; start daodm_bmc_ctrl')
