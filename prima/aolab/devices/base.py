"""Minimal device interfaces used by the AO lab engine.

Every backend (real hardware or simulator) implements these three small
classes, so the engine / GUI never knows which one it is talking to.
"""
from __future__ import annotations

import numpy as np


class Camera:
    name = 'camera'

    def start(self) -> None: ...
    def stop(self) -> None: ...

    def get_frame(self, wait_new: bool = True, timeout_s: float = 2.0
                  ) -> tuple[int, np.ndarray]:
        """Return (frame_counter, image float32).  If ``wait_new`` block
        until a frame newer than the last returned one is available."""
        raise NotImplementedError

    def set_exposure_ms(self, ms: float) -> None: ...
    def get_exposure_ms(self) -> float: return 0.0
    def get_fps(self) -> float: return 0.0
    def set_roi(self, x0: int, y0: int, w: int, h: int) -> None: ...
    def get_roi(self) -> tuple[int, int, int, int]: return (0, 0, 0, 0)
    def set_binning(self, b: int) -> None: ...
    def get_binning(self) -> int: return 1
    def full_well(self) -> float: return 4095.0
    def close(self) -> None: self.stop()


class DeformableMirror:
    name = 'dm'
    n_act = 140

    def send(self, cmd: np.ndarray) -> None:
        """Absolute command in [0, 1] (already clipped by the caller)."""
        raise NotImplementedError

    def last(self) -> np.ndarray:
        raise NotImplementedError

    def close(self) -> None: ...


class Modulator:
    name = 'modulator'

    def set_modulation(self, radius_mrad: float, freq_hz: float) -> None: ...
    def set_center(self, cx_mrad: float, cy_mrad: float) -> None: ...

    def state(self) -> dict:
        return {'radius_mrad': 0.0, 'freq_hz': 0.0, 'center': (0.0, 0.0)}

    def close(self) -> None: ...
