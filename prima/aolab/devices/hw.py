"""Real bench devices: BMC Multi-DM (USB), PI E-518 modulator, Manta."""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import numpy as np

from prima.aolab import dm_geometry as G
from prima.aolab.devices.base import DeformableMirror, Modulator

REPO = Path(__file__).resolve().parents[3]
FACTORY_FLAT = REPO / 'data' / 'bmc' / 'multidm-flat.txt'
USER_FLAT = Path.home() / 'git' / 'prima_data' / 'flat_current.txt'


def load_flat(path: Path | str | None = None) -> np.ndarray:
    """Current flat: user flat if present, else the factory (BMC) flat."""
    if path is None:
        path = USER_FLAT if USER_FLAT.is_file() else FACTORY_FLAT
    arr = np.loadtxt(str(path), dtype=float, encoding='utf-8-sig').ravel()
    if arr.size != G.N_ACT or np.any(arr < 0) or np.any(arr > 1):
        raise ValueError('bad flat file %s' % path)
    return arr


def save_user_flat(flat: np.ndarray) -> Path:
    USER_FLAT.parent.mkdir(parents=True, exist_ok=True)
    if USER_FLAT.is_file():   # keep history
        USER_FLAT.rename(USER_FLAT.with_name(
            'flat_%s.txt' % time.strftime('%Y%m%d_%H%M%S')))
    np.savetxt(USER_FLAT, np.asarray(flat).ravel(), fmt='%.6f')
    return USER_FLAT


def dm_owner_pids() -> list[int]:
    """PIDs of other processes that hold the DM (old Drop-2 daemon)."""
    try:
        out = subprocess.run(['pgrep', '-f', 'daodm_bmc_ctrl'],
                             capture_output=True, text=True).stdout
        return [int(p) for p in out.split() if int(p) != os.getpid()]
    except Exception:
        return []


class BmcUsbDM(DeformableMirror):
    """Direct pyusb driver (daoprima.hw.bmc_usb), no daemon.

    Safety: every command is clipped to [0, 1]; on open the mirror goes to
    ``initial`` (the flat) without passing through mid-scale; on close the
    high voltage is disabled by the driver.
    """

    def __init__(self, initial: np.ndarray, map_name: str = 'MULTI140.map'):
        from daoprima.hw.bmc_usb import MultiDmUsb
        pids = dm_owner_pids()
        if pids:
            raise RuntimeError(
                'DM USB is held by daodm_bmc_ctrl (pid %s). Stop it first: '
                'kill %s' % (pids, ' '.join(map(str, pids))))
        self._hw = MultiDmUsb(map_name=map_name)
        self._hw.open(initial=np.clip(initial, 0, 1))
        self.name = 'BMC Multi-DM USB (%s)' % map_name
        self._last = np.clip(np.asarray(initial, float), 0, 1)

    def send(self, cmd):
        c = np.clip(np.asarray(cmd, float).ravel(), 0.0, 1.0)
        if c.size != G.N_ACT or not np.all(np.isfinite(c)):
            raise ValueError('invalid DM command')
        self._hw.send_data(c)
        self._last = c

    def last(self):
        return self._last.copy()

    def close(self):
        self._hw.close()


class NullDM(DeformableMirror):
    """Stand-in when the DM is not available: commands are only stored."""

    def __init__(self, initial):
        self.name = 'NO DM (commands discarded)'
        self._last = np.asarray(initial, float).copy()

    def send(self, cmd):
        self._last = np.clip(np.asarray(cmd, float).ravel(), 0, 1)

    def last(self):
        return self._last.copy()


class PiModulator(Modulator):
    """S-334 on E-518 with the correct pi_gcs-style setup (pivot 100 V,
    closed loop, circle centred on mid travel, R=0 -> DC at mid travel).
    See ``pi_modulator.py``."""

    def __init__(self, radius_mrad: float = 10.0, freq_hz: float = 20.0,
                 host: str | None = None):
        from prima.aolab.devices.pi_modulator import PiTipTiltModulator
        kw = {'host': host} if host else {}
        self._m = PiTipTiltModulator(**kw)
        self.name = 'PI S-334 / E-518'
        self.set_modulation(radius_mrad, freq_hz)

    def set_modulation(self, radius_mrad, freq_hz):
        self._m.set_modulation(float(radius_mrad), float(freq_hz))

    def set_center(self, cx, cy):
        self._m.set_center(cx, cy)

    def state(self):
        return self._m.state()

    def readback(self):
        return self._m.readback()

    def close(self, keep_modulating: bool = True):
        self._m.close(keep_state=keep_modulating)


def make_hw_bench(exposure_ms: float = 50.0, binning: int = 2,
                  radius_mrad: float = 10.0, freq_hz: float = 20.0,
                  use_dm: bool = True):
    from prima.aolab.devices.camera_aravis import AravisCamera
    flat = load_flat()
    cam = AravisCamera(exposure_ms=exposure_ms)
    if binning > 1:
        cam.set_binning(binning)
    dm = BmcUsbDM(flat) if use_dm else NullDM(flat)
    mod = PiModulator(radius_mrad, freq_hz)
    return cam, dm, mod, flat
