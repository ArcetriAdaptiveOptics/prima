"""Strict sequential synthetic AO cycle for DaoPrima (legacy / causality tests).

Prefer ``daoprima.pipeline.PipelinedClosedLoop`` for daoEkarus-aligned free-run
stages with ``frame_id``. This module keeps a single-thread::

    apply DM  →  grab WFS frame  →  reconstruct  →  compute next DM

for experiments that need a causal lock. GPU is not used here (NumPy on CPU).
"""
from __future__ import annotations

import time
from typing import Optional

import numpy as np

from daoprima import shm as shm_mod
from daoprima import shm_names as N
from daoprima.bridges import (
    CameraToShmBridge, DemoCamera, DemoDm, ShmToDmBridge,
)


def reconstruct_modes_from_frame(frame: np.ndarray, n_modes: int) -> np.ndarray:
    """Lightweight synthetic reconstructor (CPU NumPy) — stand-in for MVM.

    Maps simple pupil / intensity features of the WFS frame into a modal
    vector. Not a calibrated IM; only for sequencing + rate tests.
    """
    frame = np.asarray(frame, dtype=float)
    h, w = frame.shape[:2]
    modes = np.zeros(n_modes, dtype=float)
    # global flux / contrast
    modes[0] = (frame.mean() - 60.0) / 80.0
    # left-right / top-bottom "tip-tilt-like"
    modes[1] = (frame[:, : w // 2].mean() - frame[:, w // 2 :].mean()) / 40.0
    modes[2] = (frame[: h // 2, :].mean() - frame[h // 2 :, :].mean()) / 40.0
    # quadrant differences (pyramid-ish)
    q = [
        frame[: h // 2, : w // 2].mean(),
        frame[: h // 2, w // 2 :].mean(),
        frame[h // 2 :, : w // 2].mean(),
        frame[h // 2 :, w // 2 :].mean(),
    ]
    for i in range(min(4, n_modes - 3)):
        modes[3 + i] = (q[i] - frame.mean()) / 40.0
    # fill remaining with weak spatial harmonics so M2C has content
    for i in range(7, n_modes):
        modes[i] = 0.01 * np.sin(0.3 * i + frame.std() * 0.05)
    return modes


class SequentialClosedLoop:
    """One-thread AO: DM apply → frame → recon → next DM command."""

    def __init__(
            self,
            camera=None,
            dm=None,
            target_fps: float = 60.0,
            frame_hw=(256, 256),
            n_modes: int = 20,
    ):
        self.target_fps = float(target_fps)
        self.period_s = 1.0 / self.target_fps if self.target_fps > 0 else 0.0
        self.n_modes = int(n_modes)
        self._steps = 0
        self._closed_steps = 0

        if dm is None:
            dm = DemoDm()
        if camera is None:
            camera = DemoCamera(frame_hw, dm=dm)

        self.dm = dm
        self.camera = camera
        self.cam_bridge = CameraToShmBridge(camera, period_s=self.period_s)
        self.dm_bridge = ShmToDmBridge(dm, period_s=self.period_s)

        # Provenance for sequencing checks
        self.last_applied_cmd = None
        self.last_frame_id = None
        self.last_modes = None
        self.last_cmd = None
        self.sequence_log = []  # list of stage tags per step

    def step(self) -> dict:
        """Run one sequential iteration. Returns timing + integrity fields."""
        stages = []
        t_all0 = time.perf_counter()

        closed = int(
            shm_mod.shm(N.SHM_DM1_LOOP_CL_SWITCH).get_data().ravel()[0])
        gain = float(shm_mod.shm(N.SHM_DM1_LOOP_GAIN).get_data().ravel()[0])
        leak = float(shm_mod.shm(N.SHM_DM1_LOOP_LEAK).get_data().ravel()[0])

        # --- 1) apply DM (command computed previous step, already in SHM) ---
        t0 = time.perf_counter()
        self.dm_bridge.step()
        applied = np.asarray(self.dm.get_shape(), dtype=float).ravel()
        self.last_applied_cmd = applied.copy()
        stages.append('dm_apply')
        t_dm = time.perf_counter() - t0

        # --- 2) grab WFS frame *after* DM is applied ---
        t0 = time.perf_counter()
        # DemoCamera reads current DM shape when coupled
        if hasattr(self.camera, 'set_dm'):
            self.camera.set_dm(self.dm)
        frame = self.cam_bridge.step()
        frame = np.asarray(frame, dtype=float)
        # embed applied-cmd fingerprint in frame metadata path via SHM fps slot
        # and a dedicated frame-id counter
        self.last_frame_id = int(getattr(self.camera, '_t', self._steps + 1))
        stages.append('frame')
        t_frame = time.perf_counter() - t0

        # --- 3) reconstruct modes from *this* frame ---
        t0 = time.perf_counter()
        modes = reconstruct_modes_from_frame(frame, self.n_modes)
        shm_mod.shm(N.SHM_WFS1_RECONSTRUCTED_MODES).set_data(
            modes.astype(np.float32))
        shm_mod.shm(N.SHM_PYRAMID_SIGNAL).set_data(modes.astype(np.float32))
        self.last_modes = modes.copy()
        stages.append('reconstruct')
        t_recon = time.perf_counter() - t0

        # --- 4) compute next DM command from modes (integrator) ---
        t0 = time.perf_counter()
        m2c = np.asarray(shm_mod.shm(N.SHM_DM1_M2C).get_data(), dtype=float)
        if m2c.ndim != 2:
            m2c = np.eye(N.SHM_DM1_N_ACTUATORS, self.n_modes)
        if m2c.shape[1] != modes.size:
            modes = np.resize(modes, m2c.shape[1])

        integ = np.asarray(
            shm_mod.shm(N.SHM_DM1_CHANNEL_1).get_data(), dtype=float).ravel()
        if integ.size != m2c.shape[0]:
            integ = np.zeros(m2c.shape[0])

        if closed:
            delta = m2c @ (gain * modes)  # CPU NumPy — no GPU
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
        shm_mod.shm(N.SHM_DM1_CHANNEL_1).set_data(integ.astype(np.float32))
        shm_mod.shm(N.SHM_DM1_CMD).set_data(cmd.astype(np.float32))
        shm_mod.shm(N.SHM_DM1_RESIDUAL_ZONAL_COMMANDS).set_data(
            integ.astype(np.float32))
        self.last_cmd = cmd.copy()
        stages.append('dm_compute')
        t_cmd = time.perf_counter() - t0

        self._steps += 1
        self.sequence_log.append(list(stages))
        t_all = time.perf_counter() - t_all0

        return {
            'closed': bool(closed),
            'gain': gain,
            'leak': leak,
            'rms_cmd': float(np.std(cmd)),
            'rms_modes': float(np.std(modes)),
            'steps': self._steps,
            'sequence': stages,
            'frame_id': self.last_frame_id,
            'applied_cmd_rms': float(np.std(applied)),
            'dt_s': t_all,
            'dt_dm_s': t_dm,
            'dt_frame_s': t_frame,
            'dt_recon_s': t_recon,
            'dt_cmd_s': t_cmd,
        }

    def run(self, n_steps: Optional[int] = None, wall_clock: bool = True):
        i = 0
        while n_steps is None or i < n_steps:
            info = self.step()
            if wall_clock and self.period_s > 0:
                time.sleep(max(0.0, self.period_s - info['dt_s']))
            i += 1
            yield info

    def assert_sequential(self) -> None:
        """Raise if any recorded step was not dm→frame→recon→dm_compute."""
        expected = ['dm_apply', 'frame', 'reconstruct', 'dm_compute']
        for i, stages in enumerate(self.sequence_log):
            if stages != expected:
                raise AssertionError(
                    'step %d sequence %s != %s' % (i, stages, expected))
