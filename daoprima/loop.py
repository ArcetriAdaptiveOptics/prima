"""Python closed-loop placeholder pieces at ~Manta rates until daoBase plugs in.

**Authoritative cadence** (daoEkarus-aligned): ``daoprima.pipeline.PipelinedClosedLoop``
— free-run / pipelined SHM stages with ``frame_id`` propagation.

Legacy: ``daoprima.sequential_loop.SequentialClosedLoop`` (strict one-thread
hand-off) remains available for causality experiments only.

``SimpleIntegratorLoop`` below is the integrator kernel only (modes→commands).
"""
from __future__ import annotations

import time
from typing import Optional

import numpy as np

from daoprima import shm as shm_mod
from daoprima import shm_names as N


class SimpleIntegratorLoop:
    """Modal leaky integrator kernel: modes → M2C → dm1Cmd (+ flat channel 0).

    Prefer ``PipelinedClosedLoop`` for the full AO pipeline with frame_id.
    """

    def __init__(self, target_fps: float = 60.0):
        self.target_fps = target_fps
        self.period_s = 1.0 / target_fps
        self._steps = 0
        self._closed_steps = 0

    def step(self) -> dict:
        closed = int(shm_mod.shm(N.SHM_DM1_LOOP_CL_SWITCH).get_data().ravel()[0])
        gain = float(shm_mod.shm(N.SHM_DM1_LOOP_GAIN).get_data().ravel()[0])
        leak = float(shm_mod.shm(N.SHM_DM1_LOOP_LEAK).get_data().ravel()[0])

        modes = np.asarray(
            shm_mod.shm(N.SHM_WFS1_RECONSTRUCTED_MODES).get_data(),
            dtype=float).ravel()
        # Simulate a small residual disturbance when closed
        if closed:
            disturb = 0.02 * np.sin(
                0.15 * self._steps + np.arange(modes.size) * 0.3)
            modes = 0.85 * modes + disturb
            shm_mod.shm(N.SHM_WFS1_RECONSTRUCTED_MODES).set_data(modes)

        m2c = np.asarray(shm_mod.shm(N.SHM_DM1_M2C).get_data(), dtype=float)
        if m2c.ndim != 2:
            m2c = np.eye(N.SHM_DM1_N_ACTUATORS, modes.size)
        # m2c is (n_act, n_modes)
        if m2c.shape[1] != modes.size:
            modes = np.resize(modes, m2c.shape[1])

        integ = np.asarray(
            shm_mod.shm(N.SHM_DM1_CHANNEL_1).get_data(), dtype=float).ravel()
        if integ.size != m2c.shape[0]:
            integ = np.zeros(m2c.shape[0])

        if closed:
            delta = m2c @ (gain * modes)
            integ = leak * integ - delta
            self._closed_steps += 1
        flat = np.asarray(
            shm_mod.shm(N.SHM_DM1_CHANNEL_0).get_data(), dtype=float).ravel()
        if flat.size != integ.size:
            flat = np.zeros_like(integ)
        offset = np.asarray(
            shm_mod.shm(N.SHM_DM1_CMD_OFFSET).get_data(), dtype=float).ravel()
        if offset.size != integ.size:
            offset = np.zeros_like(integ)

        cmd = flat + integ + offset
        shm_mod.shm(N.SHM_DM1_CHANNEL_1).set_data(integ)
        shm_mod.shm(N.SHM_DM1_CMD).set_data(cmd)
        shm_mod.shm(N.SHM_DM1_RESIDUAL_ZONAL_COMMANDS).set_data(integ)

        self._steps += 1
        return {
            'closed': bool(closed),
            'gain': gain,
            'leak': leak,
            'rms_cmd': float(np.std(cmd)),
            'rms_modes': float(np.std(modes)),
            'steps': self._steps,
        }

    def run(self, n_steps: Optional[int] = None, wall_clock: bool = True):
        i = 0
        while n_steps is None or i < n_steps:
            t0 = time.perf_counter()
            info = self.step()
            if wall_clock:
                dt = time.perf_counter() - t0
                time.sleep(max(0.0, self.period_s - dt))
            i += 1
            yield info


def close_loop():
    """daoEkarus-compatible helper: set close-loop switch to 1."""
    shm_mod.shm(N.SHM_DM1_LOOP_CL_SWITCH).set_data(
        np.ones((1, 1), dtype=np.uint32))


def open_loop():
    shm_mod.shm(N.SHM_DM1_LOOP_CL_SWITCH).set_data(
        np.zeros((1, 1), dtype=np.uint32))


def set_loop_gain(gain: float):
    shm_mod.shm(N.SHM_DM1_LOOP_GAIN).set_data(
        np.array([[float(gain)]], dtype=np.float32))


def set_loop_leak(leak: float):
    shm_mod.shm(N.SHM_DM1_LOOP_LEAK).set_data(
        np.array([[float(leak)]], dtype=np.float32))
