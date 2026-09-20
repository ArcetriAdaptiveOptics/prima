"""SHM ↔ plico bridges (thin glue — RTC stays outside the USB/vendor API).

Architecture (from docs/drop2-bmc-multidm.md)::

    [daoBase or Python loop]  --writes-->  /tmp/prima_dm1Cmd.im.shm
            │
    [shm_to_dm bridge]  --plico_dm.set_shape-->  plico_dm_server (bmc|sim)
            │
         BMC Multi-DM / FakeBmc

Camera path is the inverse: pysilico frame → SHM_WFS_FRAME.
"""
from __future__ import annotations

import time
from typing import Optional

import numpy as np

from daoprima import shm as shm_mod
from daoprima import shm_names as N


class ShmToDmBridge:
    """Poll DM command SHM and push shapes to a plico DeformableMirrorClient."""

    def __init__(self, dm_client, shm_path: str = N.SHM_DM1_CMD,
                 period_s: float = 1.0 / 60.0):
        self.dm = dm_client
        self.shm = shm_mod.shm(shm_path)
        self.period_s = period_s
        self._last = None
        if hasattr(dm_client, 'get_number_of_actuators'):
            self.n_act = int(dm_client.get_number_of_actuators())
        else:
            self.n_act = int(dm_client.getNumberOfActuators())

    def step(self) -> bool:
        cmd = np.asarray(self.shm.get_data(), dtype=float).ravel()
        if cmd.size != self.n_act:
            cmd = np.resize(cmd, self.n_act)
        if self._last is not None and np.allclose(cmd, self._last):
            return False
        if hasattr(self.dm, 'set_shape'):
            self.dm.set_shape(cmd)
        else:
            self.dm.setShape(cmd)
        self._last = cmd.copy()
        return True

    def run_forever(self, n_steps: Optional[int] = None):
        i = 0
        while n_steps is None or i < n_steps:
            self.step()
            time.sleep(self.period_s)
            i += 1


class CameraToShmBridge:
    """Pull frames from a pysilico client into SHM_WFS_FRAME."""

    def __init__(self, camera_client, shm_path: str = N.SHM_WFS_FRAME,
                 period_s: float = 1.0 / 60.0):
        self.camera = camera_client
        self.shm = shm_mod.shm(shm_path)
        self.fps_shm = shm_mod.shm(N.SHM_WFS_FPS)
        self.period_s = period_s

    def step(self):
        frame = np.asarray(self.camera.getFutureFrames(1).toNumpyArray(),
                           dtype=np.float32)
        if frame.ndim == 3:
            frame = frame[0]
        self.shm.set_data(frame)
        self.fps_shm.set_data(np.array([[1.0 / max(self.period_s, 1e-6)]],
                                       dtype=np.float32))
        return frame

    def run_forever(self, n_steps: Optional[int] = None):
        i = 0
        while n_steps is None or i < n_steps:
            self.step()
            time.sleep(self.period_s)
            i += 1


class DemoCamera:
    """Synthetic PWFS-like frame generator when pysilico is offline."""

    def __init__(self, hw=(256, 256)):
        self.h, self.w = hw
        self._t = 0

    def getFutureFrames(self, n):
        self._t += 1
        yy, xx = np.mgrid[0:self.h, 0:self.w]
        frame = np.zeros((self.h, self.w), dtype=np.float32)
        # four soft pupils
        centers = [(0.30, 0.30), (0.30, 0.70), (0.70, 0.30), (0.70, 0.70)]
        for cy, cx in centers:
            r2 = (yy - cy * self.h) ** 2 + (xx - cx * self.w) ** 2
            frame += 120.0 * np.exp(-r2 / (2 * (0.08 * self.h) ** 2))
        frame += 8.0 * np.sin(0.05 * self._t + xx / 20.0)
        frame = np.clip(frame, 0, 255)

        class Bundle:
            def toNumpyArray(inner_self):
                return frame[None, ...] if n == 1 else np.stack([frame] * n)
        return Bundle()


class DemoDm:
    def __init__(self, n=N.SHM_DM1_N_ACTUATORS):
        self._n = n
        self._shape = np.zeros(n)

    def getNumberOfActuators(self):
        return self._n

    def get_number_of_actuators(self):
        return self._n

    def setShape(self, shape):
        self._shape = np.asarray(shape, dtype=float).ravel().copy()

    def set_shape(self, shape):
        self.setShape(shape)

    def getShape(self):
        return self._shape.copy()

    def get_shape(self):
        return self.getShape()
