"""opticalib ``BaseDeformableMirror`` wrapper around DAO/USB BMC Multi-DM.

Bias = shipped lab flat (``data/bmc/multidm-flat.txt``). Commands are absolute
voltages in [0, 1] or differential about the bias. Optional √u linearization
maps linear stroke to drive command.
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from opticalib.devices._API.base_devices import BaseDeformableMirror

from daoprima.hw.bmc_dm import open_bmc_dm
from prima.gui.dm_panel import DEFAULT_FLAT_PATH, load_shipped_flat, N_ACT

# Default safety: max |Δcmd| per set_shape call (about bias units).
DEFAULT_MAX_STEP = 0.15
DEFAULT_PARK_RAMP_S = 0.4


class _DaoShmBackend:
    """Write shapes to ``/tmp/prima_dm1Cmd.im.shm`` for ``daodm_bmc_ctrl``."""

    def __init__(self):
        from daoprima.create_shm import create_default_graph
        from daoprima.bridges import ShmCommandWriter
        create_default_graph()
        self._writer = ShmCommandWriter()
        self.n_actuators = int(N_ACT)
        self.serial = 'DAO-SHM'
        self.backend = 'dao-shm'

    def send_data(self, cmd) -> None:
        self._writer.set_shape(cmd)
        # Let daodm_bmc_ctrl poll (~few ms) before next poke.
        time.sleep(0.015)

    def get_actuator_data(self) -> np.ndarray:
        return np.asarray(self._writer.get_shape(), dtype=float)

    def close(self) -> None:
        return


def _open_hw(prefer: str, serial: str, map_name: str):
    """Open USB/vendor/sim, or DAO SHM when ``prefer`` is dao/shm."""
    pref = (prefer or 'auto').lower()
    if pref in ('dao', 'shm', 'dao-shm'):
        return _DaoShmBackend()
    if pref == 'auto':
        try:
            return open_bmc_dm(prefer='usb', serial=serial, map_name=map_name)
        except Exception as usb_exc:
            # USB often held by daodm_bmc_ctrl — use SHM path.
            print('BMC USB open failed (%s); using dao-shm' % usb_exc)
            return _DaoShmBackend()
    hw = open_bmc_dm(prefer=pref, serial=serial, map_name=map_name)
    # Never silently use in-process sim for live flattening.
    if getattr(hw, 'backend', None) == 'sim' and pref not in ('sim',):
        print('open_bmc_dm returned sim; switching to dao-shm')
        try:
            hw.close()
        except Exception:
            pass
        return _DaoShmBackend()
    return hw


class BmcMultiDm(BaseDeformableMirror):
    """140-act BMC Multi-DM for opticalib IFF / flattening."""

    def __init__(
            self,
            prefer: str = 'dao',
            serial: str = 'C30W052088',
            map_name: str = 'MULTI140.map',
            bias: np.ndarray | None = None,
            bias_path: Path | str | None = None,
            max_step: float = DEFAULT_MAX_STEP,
            linearize_sqrt: bool = False,
            dry_run: bool = False,
            hw=None,
    ):
        self._name = 'BmcMultiDm'
        self.n_acts = int(N_ACT)
        self.cmdHistory = None
        self.slave_ids: list[int] = []
        self.border_ids: list[int] = []
        self._max_step = float(max_step)
        self._linearize_sqrt = bool(linearize_sqrt)
        self._dry_run = bool(dry_run)
        self._owns_hw = hw is None
        self._prefer = str(prefer)

        if bias is not None:
            self._bias = np.asarray(bias, dtype=float).ravel()
        else:
            path = Path(bias_path) if bias_path is not None else DEFAULT_FLAT_PATH
            self._bias = load_shipped_flat(path).astype(float)
        if self._bias.size != self.n_acts:
            raise ValueError('bias size %d != %d' % (self._bias.size, self.n_acts))
        self._bias = np.clip(self._bias, 0.0, 1.0)

        if hw is not None:
            self._hw = hw
        elif dry_run:
            self._hw = None
        else:
            self._hw = _open_hw(prefer, serial, map_name)

        # Absolute drive currently held (about [0,1]).
        self._cmd = self._bias.copy()
        if not dry_run and self._hw is not None:
            self._hw.send_data(self._to_drive(self._cmd))

    # --- opticalib API ---

    def get_shape(self) -> np.ndarray:
        """Return absolute command in linear units (pre-√u)."""
        return self._cmd.copy()

    def set_shape(
            self,
            cmd,
            differential: bool = False,
            *,
            slave: bool | str = False,
            max_step: float | None = None,
    ) -> None:
        cmd = np.asarray(cmd, dtype=float).ravel()
        if cmd.size != self.n_acts:
            raise ValueError('cmd size %d != %d' % (cmd.size, self.n_acts))
        cmd = self._apply_slaving(cmd=cmd, slave=slave)
        if differential:
            target = self._bias + cmd
        else:
            # Absolute: treat as full drive about [0,1], not about bias.
            target = cmd
        target = np.clip(target, 0.0, 1.0)
        step = self._max_step if max_step is None else float(max_step)
        if step > 0:
            delta = np.clip(target - self._cmd, -step, step)
            target = self._cmd + delta
            target = np.clip(target, 0.0, 1.0)
        self._cmd = target
        if self._dry_run or self._hw is None:
            return
        self._hw.send_data(self._to_drive(self._cmd))

    def upload_cmd_history(self, tcmdhist, *, slave: bool | str = False) -> None:
        arr = np.asarray(tcmdhist, dtype=float)
        if arr.ndim != 2:
            raise ValueError('cmd history must be 2-D (n_acts, n_modes)')
        if arr.shape[0] != self.n_acts and arr.shape[1] == self.n_acts:
            arr = arr.T
        if arr.shape[0] != self.n_acts:
            raise ValueError(
                'cmd history shape %s incompatible with n_acts=%d'
                % (arr.shape, self.n_acts))
        if slave:
            arr = np.asarray(self._slave_cmdmat(cmdmat=arr, slave=slave), dtype=float)
        self.cmdHistory = arr

    def run_cmd_history(
            self,
            wfs=None,
            differential: bool = True,
            save: str | None = None,
            delay: float = 0.05,
            **setshape_kwargs,
    ):
        """Apply each column of ``cmdHistory``; optionally acquire WFS maps."""
        if self.cmdHistory is None:
            raise RuntimeError('No Command History to run')
        hist = np.asarray(self.cmdHistory, dtype=float)
        start = self.get_shape().copy()
        images = []
        for i, col in enumerate(hist.T):
            if differential:
                self.set_shape(col, differential=True, **setshape_kwargs)
            else:
                self.set_shape(col, differential=False, **setshape_kwargs)
            if delay > 0:
                time.sleep(delay)
            if wfs is not None:
                img = wfs.acquire_map()
                images.append(np.asarray(img, dtype=float))
                if save is not None:
                    from pathlib import Path
                    Path(save).mkdir(parents=True, exist_ok=True)
                    np.save(Path(save) / ('image_%05d.npy' % i), images[-1])
        self.set_shape(start, differential=False)
        return images

    # --- helpers ---

    def bias(self) -> np.ndarray:
        return self._bias.copy()

    def set_bias(self, bias) -> None:
        b = np.clip(np.asarray(bias, dtype=float).ravel(), 0.0, 1.0)
        if b.size != self.n_acts:
            raise ValueError('bias size mismatch')
        self._bias = b

    def park(self, ramp_s: float = DEFAULT_PARK_RAMP_S, n_steps: int = 10) -> None:
        """Ramp back to shipped bias (flat)."""
        start = self._cmd.copy()
        target = self._bias.copy()
        n = max(1, int(n_steps))
        dt = float(ramp_s) / n
        for k in range(1, n + 1):
            self.set_shape(
                start + (target - start) * (k / n),
                differential=False, max_step=1.0)
            if dt > 0:
                time.sleep(dt)

    def _to_drive(self, linear_cmd: np.ndarray) -> np.ndarray:
        u = np.clip(np.asarray(linear_cmd, dtype=float), 0.0, 1.0)
        if self._linearize_sqrt:
            # Map desired linear stroke → drive: u_drive = √u_lin
            u = np.sqrt(u)
        return u.astype(np.float64)

    def close(self) -> None:
        if self._owns_hw and self._hw is not None:
            try:
                self._hw.close()
            except Exception:
                pass
            self._hw = None

    def __repr__(self) -> str:
        if self._dry_run or self._hw is None:
            backend = 'dry-run'
        else:
            backend = getattr(self._hw, 'backend', None)
            if backend is None and hasattr(self._hw, 'info'):
                backend = getattr(self._hw.info, 'backend', '?')
            backend = backend or '?'
        return 'BmcMultiDm(n=%d, backend=%s, sqrt=%s)' % (
            self.n_acts, backend, self._linearize_sqrt)
