"""Free-run / pipelined AO stages for DaoPrima (daoEkarus-shaped).

Stages run as independent threads, waking on SHM generation bumps
(semaphore-lite). Cadence matches daoEkarus: camera and DM are free-running;
recon → RTC are pipeline-ordered.

**DaoPrima divergence:** each new camera frame gets a ``frame_id`` written to
``SHM_FRAME_ID`` and stamped through recon / RTC / DM paths.
"""
from __future__ import annotations

import threading
import time
from typing import List, Optional

import numpy as np

from daoprima import shm as shm_mod
from daoprima import shm_names as N
from daoprima.bridges import (
    CameraToShmBridge, DemoCamera, DemoDm, ShmToDmBridge,
)
from daoprima.mvm import MatrixVectorMultiply, gpu_status, select_backend
from daoprima.sequential_loop import reconstruct_modes_from_frame


def _u32_scalar(v: int) -> np.ndarray:
    return np.array([[np.uint32(v)]], dtype=np.uint32)


def _read_u32(path: str) -> int:
    return int(np.asarray(shm_mod.shm(path).get_data()).ravel()[0])


def _write_u32(path: str, v: int) -> None:
    shm_mod.shm(path).set_data(_u32_scalar(v))


class PipelinedClosedLoop:
    """Threaded pipeline: cam → recon(MVM) → integrator → DM.

    Like daoEkarus pyramid apps, each stage waits on its input SHM update,
    computes, and finalizes the next SHM (waking the downstream stage).
    """

    def __init__(
            self,
            camera=None,
            dm=None,
            target_fps: float = 60.0,
            frame_hw=(256, 256),
            n_modes: int = 20,
            prefer_gpu: bool = True,
    ):
        self.target_fps = float(target_fps)
        self.period_s = 1.0 / self.target_fps if self.target_fps > 0 else 0.0
        self.n_modes = int(n_modes)
        self.prefer_gpu = bool(prefer_gpu)

        if dm is None:
            dm = DemoDm()
        if camera is None:
            camera = DemoCamera(frame_hw, dm=dm)

        self.dm = dm
        self.camera = camera
        self.cam_bridge = CameraToShmBridge(camera, period_s=self.period_s)
        self.dm_bridge = ShmToDmBridge(dm, period_s=self.period_s)

        backend, status = select_backend(prefer_gpu)
        self._gpu_status = status
        self.mvm_s2m = MatrixVectorMultiply(prefer_gpu=prefer_gpu)
        self.mvm_m2c = MatrixVectorMultiply(prefer_gpu=prefer_gpu)
        cm = np.asarray(
            shm_mod.shm(N.SHM_PYRAMID_2_DM1_REC).get_data(), dtype=np.float32)
        if cm.ndim != 2:
            cm = np.eye(n_modes, dtype=np.float32) * 0.1
        self.mvm_s2m.set_matrix(cm)
        m2c = np.asarray(shm_mod.shm(N.SHM_DM1_M2C).get_data(), dtype=np.float32)
        if m2c.ndim != 2:
            m2c = np.eye(N.SHM_DM1_N_ACTUATORS, n_modes, dtype=np.float32)
        self.mvm_m2c.set_matrix(m2c)
        self.mvm_backend = backend
        # Prefer reporting the actual backend used by MVM objects
        self.mvm_backend = self.mvm_s2m.backend

        self._stop = threading.Event()
        self._threads: List[threading.Thread] = []
        self._lock = threading.Lock()
        self._frame_id = 0
        self._cam_frames = 0
        self._recon_frames = 0
        self._rtc_frames = 0
        self._dm_frames = 0
        self._closed_steps = 0
        self._last_info = {
            'closed': False,
            'gain': 0.0,
            'leak': 0.0,
            'rms_cmd': 0.0,
            'rms_modes': 0.0,
            'steps': 0,
            'frame_id': 0,
            'frame_id_recon': 0,
            'frame_id_rtc': 0,
            'frame_id_dm': 0,
            'mvm_backend': self.mvm_backend,
            'pipeline': 'cam→recon→rtc→dm',
        }
        self.id_log: List[dict] = []  # {cam, recon, rtc, dm} samples

    def start(self) -> None:
        if self._threads:
            return
        self._stop.clear()
        specs = (
            ('cam', self._cam_loop),
            ('recon', self._recon_loop),
            ('rtc', self._rtc_loop),
            ('dm', self._dm_loop),
        )
        for name, target in specs:
            t = threading.Thread(
                target=target, name='daoprima-%s' % name, daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self, join_timeout: float = 2.0) -> None:
        self._stop.set()
        for t in self._threads:
            t.join(timeout=join_timeout)
        self._threads = []

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()

    # --- stages ---------------------------------------------------------

    def _cam_loop(self) -> None:
        wfs = shm_mod.shm(N.SHM_WFS_FRAME)
        fps = shm_mod.shm(N.SHM_WFS_FPS)
        while not self._stop.is_set():
            t0 = time.perf_counter()
            if hasattr(self.camera, 'set_dm'):
                self.camera.set_dm(self.dm)
            # Grab without notifying until frame_id is stamped
            raw = self.camera.getFutureFrames(1).toNumpyArray()
            frame = np.asarray(raw, dtype=np.float32)
            if frame.ndim == 3:
                frame = frame[0]
            with self._lock:
                self._frame_id += 1
                fid = self._frame_id
                self._cam_frames += 1
            _write_u32(N.SHM_FRAME_ID, fid)
            fps.set_data(np.array(
                [[1.0 / max(self.period_s, 1e-6)]], dtype=np.float32))
            # Finalize frame last so recon wakes with matching frame_id
            wfs.set_data(frame)
            if self.period_s > 0:
                dt = time.perf_counter() - t0
                time.sleep(max(0.0, self.period_s - dt))

    def _recon_loop(self) -> None:
        wfs = shm_mod.shm(N.SHM_WFS_FRAME)
        modes_shm = shm_mod.shm(N.SHM_WFS1_RECONSTRUCTED_MODES)
        slopes_shm = shm_mod.shm(N.SHM_PYRAMID_SIGNAL)
        gen = wfs.get_counter()
        while not self._stop.is_set():
            if not wfs.wait_for_update(gen, timeout=0.2):
                continue
            gen = wfs.get_counter()
            frame = np.asarray(wfs.get_data(), dtype=float)
            fid = _read_u32(N.SHM_FRAME_ID)
            # Synthetic "slopes" then S2M MVM (daoMvMGPU role)
            slopes = reconstruct_modes_from_frame(frame, self.n_modes)
            modes = self.mvm_s2m.multiply(slopes)
            gains = np.asarray(
                shm_mod.shm(N.SHM_WFS1_RECONSTRUCTED_MODES_GAIN).get_data(),
                dtype=float).ravel()
            if gains.size != modes.size:
                gains = np.ones(modes.size, dtype=np.float32)
            modes_g = (modes * gains).astype(np.float32)
            slopes_shm.set_data(slopes.astype(np.float32))
            shm_mod.shm(N.SHM_WFS1_RECONSTRUCTED_MODES_WITH_GAIN).set_data(
                modes_g)
            _write_u32(N.SHM_FRAME_ID_RECON, fid)
            modes_shm.set_data(modes.astype(np.float32))
            with self._lock:
                self._recon_frames += 1
                self._last_info['rms_modes'] = float(np.std(modes))
                self._last_info['frame_id_recon'] = fid

    def _rtc_loop(self) -> None:
        modes_shm = shm_mod.shm(N.SHM_WFS1_RECONSTRUCTED_MODES)
        cmd_shm = shm_mod.shm(N.SHM_DM1_CMD)
        gen = modes_shm.get_counter()
        while not self._stop.is_set():
            if not modes_shm.wait_for_update(gen, timeout=0.2):
                continue
            gen = modes_shm.get_counter()
            modes = np.asarray(modes_shm.get_data(), dtype=np.float32).ravel()
            fid = _read_u32(N.SHM_FRAME_ID_RECON)
            closed = int(
                shm_mod.shm(N.SHM_DM1_LOOP_CL_SWITCH).get_data().ravel()[0])
            gain = float(shm_mod.shm(N.SHM_DM1_LOOP_GAIN).get_data().ravel()[0])
            leak = float(shm_mod.shm(N.SHM_DM1_LOOP_LEAK).get_data().ravel()[0])

            integ = np.asarray(
                shm_mod.shm(N.SHM_DM1_CHANNEL_1).get_data(),
                dtype=float).ravel()
            n_act = N.SHM_DM1_N_ACTUATORS
            if integ.size != n_act:
                integ = np.zeros(n_act)

            if closed:
                # M2C MVM (daoMvM role) — GPU when available
                delta = self.mvm_m2c.multiply(gain * modes)
                if delta.size != n_act:
                    delta = np.resize(delta, n_act)
                integ = leak * integ - delta
                with self._lock:
                    self._closed_steps += 1

            flat = np.asarray(
                shm_mod.shm(N.SHM_DM1_CHANNEL_0).get_data(),
                dtype=float).ravel()
            if flat.size != n_act:
                flat = np.zeros(n_act)
            offset = np.asarray(
                shm_mod.shm(N.SHM_DM1_CMD_OFFSET).get_data(),
                dtype=float).ravel()
            if offset.size != n_act:
                offset = np.zeros(n_act)

            cmd = (flat + integ + offset).astype(np.float32)
            shm_mod.shm(N.SHM_DM1_CHANNEL_1).set_data(integ.astype(np.float32))
            shm_mod.shm(N.SHM_DM1_RESIDUAL_ZONAL_COMMANDS).set_data(
                integ.astype(np.float32))
            _write_u32(N.SHM_FRAME_ID_RTC, fid)
            cmd_shm.set_data(cmd)
            with self._lock:
                self._rtc_frames += 1
                self._last_info.update({
                    'closed': bool(closed),
                    'gain': gain,
                    'leak': leak,
                    'rms_cmd': float(np.std(cmd)),
                    'frame_id_rtc': fid,
                    'steps': self._rtc_frames,
                })

    def _dm_loop(self) -> None:
        cmd_shm = shm_mod.shm(N.SHM_DM1_CMD)
        gen = cmd_shm.get_counter()
        while not self._stop.is_set():
            if not cmd_shm.wait_for_update(gen, timeout=0.2):
                continue
            gen = cmd_shm.get_counter()
            fid = _read_u32(N.SHM_FRAME_ID_RTC)
            self.dm_bridge.step()
            _write_u32(N.SHM_FRAME_ID_DM, fid)
            with self._lock:
                self._dm_frames += 1
                self._last_info['frame_id_dm'] = fid
                self._last_info['frame_id'] = _read_u32(N.SHM_FRAME_ID)
                sample = {
                    'cam': int(self._last_info['frame_id']),
                    'recon': int(self._last_info.get('frame_id_recon', 0)),
                    'rtc': int(fid),
                    'dm': int(fid),
                }
                self.id_log.append(sample)

    # --- helpers for GUI / smoke ---------------------------------------

    def snapshot(self) -> dict:
        with self._lock:
            info = dict(self._last_info)
            info['cam_frames'] = self._cam_frames
            info['recon_frames'] = self._recon_frames
            info['rtc_frames'] = self._rtc_frames
            info['dm_frames'] = self._dm_frames
            info['closed_steps'] = self._closed_steps
            info['mvm_backend'] = self.mvm_backend
            info['gpu_status'] = dict(self._gpu_status)
            info['pipeline'] = 'cam→recon→rtc→dm'
        return info

    def wait_for_frames(self, n_dm: int, timeout: float = 10.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._dm_frames >= n_dm:
                return True
            time.sleep(0.01)
        return False

    def assert_frame_ids_match(self, min_samples: int = 20) -> None:
        """Require recon/rtc/dm stamps equal for completed pipeline samples."""
        samples = [s for s in self.id_log if s['dm'] > 0]
        if len(samples) < min_samples:
            raise AssertionError(
                'need ≥%d dm samples, got %d' % (min_samples, len(samples)))
        # Strong check: for every sample, recon == rtc == dm (same frame_id)
        bad = [s for s in samples if not (s['recon'] == s['rtc'] == s['dm'])]
        if bad:
            raise AssertionError(
                'frame_id mismatch examples: %s' % bad[:5])
        # Cam id should be ≥ dm id (pipeline lag ≥ 0)
        tail = samples[-min_samples:]
        lag_ok = all(s['cam'] >= s['dm'] for s in tail)
        if not lag_ok:
            raise AssertionError('camera frame_id behind DM stamp')
        # IDs must advance
        ids = [s['dm'] for s in tail]
        if ids[-1] <= ids[0]:
            raise AssertionError('frame_id not advancing: %s…%s' % (
                ids[0], ids[-1]))