"""In-process fake BMC + Pyramid for pipeline tests (no HW)."""
from __future__ import annotations

import numpy as np

from opticalib.devices._API.base_devices import (
    BaseCamera, BaseDeformableMirror, BaseWavefrontSensor)

from prima.gui.dm_panel import N_ACT


def _make_influence(n_acts: int = N_ACT, n_slopes: int = 200) -> np.ndarray:
    """Synthetic zonal IM: each actuator → localized slope pattern."""
    rng = np.random.default_rng(42)
    im = rng.normal(0.0, 1.0, size=(n_slopes, n_acts))
    # Smooth columns so nearby acts correlate slightly
    for k in range(3):
        im = 0.7 * im + 0.3 * np.roll(im, 1, axis=1)
    # Normalize columns
    norms = np.linalg.norm(im, axis=0) + 1e-12
    return (im / norms).astype(float)


class FakeBmcDm(BaseDeformableMirror):
    """140-act fake DM with bias + clip, matching ``BmcMultiDm`` surface."""

    def __init__(
            self,
            n_acts: int = N_ACT,
            bias: float | np.ndarray = 0.5,
            max_step: float = 1.0,
    ):
        self._name = 'FakeBmcDm'
        self.n_acts = int(n_acts)
        self.cmdHistory = None
        self.slave_ids: list[int] = []
        self.border_ids: list[int] = []
        self._max_step = float(max_step)
        if np.isscalar(bias):
            self._bias = np.full(self.n_acts, float(bias))
        else:
            self._bias = np.asarray(bias, dtype=float).ravel()
            if self._bias.size != self.n_acts:
                raise ValueError('bias size mismatch')
        self._cmd = self._bias.copy()

    def get_shape(self) -> np.ndarray:
        return self._cmd.copy()

    def set_shape(self, cmd, differential: bool = False, *, slave=False, **_):
        cmd = np.asarray(cmd, dtype=float).ravel()
        if cmd.size != self.n_acts:
            raise ValueError('cmd size mismatch')
        cmd = self._apply_slaving(cmd=cmd, slave=slave)
        target = self._bias + cmd if differential else cmd
        target = np.clip(target, 0.0, 1.0)
        if self._max_step > 0:
            d = np.clip(target - self._cmd, -self._max_step, self._max_step)
            target = np.clip(self._cmd + d, 0.0, 1.0)
        self._cmd = target

    def upload_cmd_history(self, tcmdhist, *, slave: bool | str = False):
        arr = np.asarray(tcmdhist, dtype=float)
        if arr.ndim != 2:
            raise ValueError('need 2-D history')
        if arr.shape[0] != self.n_acts and arr.shape[1] == self.n_acts:
            arr = arr.T
        self.cmdHistory = arr

    def run_cmd_history(self, wfs=None, differential: bool = True,
                        save=None, delay: float = 0.0, **kw):
        if self.cmdHistory is None:
            raise RuntimeError('no history')
        start = self.get_shape().copy()
        images = []
        for col in self.cmdHistory.T:
            self.set_shape(col, differential=differential, **kw)
            if wfs is not None:
                images.append(np.asarray(wfs.acquire_map(), dtype=float))
        self.set_shape(start, differential=False)
        return images

    def bias(self) -> np.ndarray:
        return self._bias.copy()

    def park(self, **_):
        self.set_shape(self._bias, differential=False, max_step=1.0)


class FakePyramid(BaseWavefrontSensor):
    """Fake PWFS: slopes = IM @ (cmd − bias) + noise (+ optional disturbance)."""

    def __init__(
            self,
            dm: FakeBmcDm,
            n_slopes: int = 200,
            noise_rms: float = 1e-4,
            disturbance: np.ndarray | None = None,
            seed: int = 0,
    ):
        self._name = 'FakePyramid'
        self._dm = dm
        self._im = _make_influence(dm.n_acts, n_slopes)
        self._n_slopes = int(n_slopes)
        self._noise = float(noise_rms)
        self._rng = np.random.default_rng(seed)
        # Extra static aberration in command space (to be flattened)
        if disturbance is None:
            self._dist = self._rng.normal(0.0, 0.05, size=dm.n_acts)
        else:
            self._dist = np.asarray(disturbance, dtype=float).ravel()
        self._frame = np.zeros((64, 64), dtype=float)

    @property
    def influence(self) -> np.ndarray:
        return self._im.copy()

    def acquire_detector(self, nframes: int = 1):
        return self._frame.copy()

    def acquire_map(self, nframes: int = 1, output_type: str = 'slopes1d', **_):
        """Return 1-D slope vector (default) or 2-D dummy image."""
        delta = (self._dm.get_shape() - self._dm.bias()) + self._dist
        slopes = self._im @ delta
        if self._noise > 0:
            slopes = slopes + self._rng.normal(0.0, self._noise, size=slopes.shape)
        if output_type in ('slopes2d', 'image', 'pupils'):
            # Pack into a fake 2-D map for APIs that expect images
            side = int(np.ceil(np.sqrt(slopes.size)))
            canvas = np.zeros((side, side), dtype=float)
            canvas.ravel()[: slopes.size] = slopes
            return canvas
        return slopes.astype(float)

    def set_exptime(self, *_a, **_k):
        return None

    def get_exptime(self):
        return 1.0


class FakeCamera(BaseCamera):
    """Minimal camera returning a static frame (for dry-run scripts)."""

    def __init__(self, shape=(256, 256), level: float = 100.0):
        self._frame = np.full(shape, float(level), dtype=float)

    def reconnect(self, *args):
        return None

    def acquire_frames(self, nframes=None, multiframe_out_mode='mean'):
        return self._frame.copy()

    def set_exptime(self, exptime_us):
        return None

    def get_exptime(self):
        return 1000.0
