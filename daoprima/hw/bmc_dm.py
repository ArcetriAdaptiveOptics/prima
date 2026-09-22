"""High-level BMC Multi-DM handle (vendor ``bmc`` module | pyusb | sim).

Preferred order matches Drop 2 bring-up on Linux:
  1. Vendor Python ``bmc.BmcDm`` if a Linux SDK is installed
  2. Direct USB via ``daoprima.hw.bmc_usb.MultiDmUsb`` (DAO/daoHw spirit)
  3. In-process sim (140 act) for GUI / SHM smoke without hardware
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from daoprima.hw import bmc_constants as C
from daoprima.hw.bmc_usb import MultiDmUsb, probe_usb


@dataclass
class BmcInfo:
    backend: str
    serial: str
    n_actuators: int
    message: str


class SimulatedBmc:
    """140-act stand-in (same surface as vendor BmcDm / MultiDmUsb)."""

    def __init__(self, n: int = C.N_ACTUATORS_USER):
        self.n_actuators = n
        self.serial = 'SIM-MultiDM-140'
        self._data = np.zeros(n, dtype=np.float64)

    def open(self):
        return

    def send_data(self, cmd):
        arr = np.asarray(cmd, dtype=np.float64).ravel()
        if arr.size != self.n_actuators:
            raise ValueError('need %d, got %d' % (self.n_actuators, arr.size))
        self._data = np.clip(arr, 0.0, 1.0)

    def get_actuator_data(self):
        return self._data.copy()

    def close(self):
        return

    def num_actuators(self):
        return self.n_actuators


class VendorBmc:
    """Wrap Windows/Linux vendor ``bmc.BmcDm`` if importable."""

    def __init__(self, serial: str = 'MultiUSB000'):
        import bmc  # type: ignore
        self._bmc = bmc
        self._dm = bmc.BmcDm()
        self.serial = serial
        self.n_actuators = C.N_ACTUATORS_USER

    def open(self):
        err = self._dm.open_dm(str(self.serial))
        if err:
            msg = self._dm.error_string(err)
            raise RuntimeError('bmc.open_dm(%s): %s (%s)' % (
                self.serial, msg, err))
        self.n_actuators = int(self._dm.num_actuators())

    def send_data(self, cmd):
        arr = np.asarray(cmd, dtype=float).ravel()
        self._dm.send_data(arr.tolist())

    def get_actuator_data(self):
        return np.asarray(self._dm.get_actuator_data(), dtype=float)

    def close(self):
        self._dm.close_dm()


class BmcMultiDm:
    """Uniform API used by ``daodm_bmc_ctrl`` and Drop 2 GUI."""

    def __init__(self, backend_obj, info: BmcInfo):
        self._hw = backend_obj
        self.info = info

    @property
    def backend(self) -> str:
        return self.info.backend

    @property
    def serial(self) -> str:
        return self.info.serial

    def num_actuators(self) -> int:
        return int(self.info.n_actuators)

    def send_data(self, cmd) -> None:
        self._hw.send_data(cmd)

    def get_actuator_data(self) -> np.ndarray:
        return np.asarray(self._hw.get_actuator_data(), dtype=float)

    def close(self) -> None:
        self._hw.close()


def probe_bmc_usb():
    return probe_usb()


def open_bmc_dm(prefer: str = 'auto', serial: str = 'MultiUSB000',
                map_name: str = 'MultiDM-01.map') -> BmcMultiDm:
    """Open BMC Multi-DM.

    ``prefer``: ``auto`` | ``vendor`` | ``usb`` | ``sim``
    """
    prefer = (prefer or 'auto').lower()

    if prefer == 'sim':
        hw = SimulatedBmc()
        hw.open()
        return BmcMultiDm(hw, BmcInfo(
            'sim', hw.serial, hw.n_actuators, 'simulated 140-act Multi-DM'))

    if prefer in ('auto', 'vendor'):
        try:
            hw = VendorBmc(serial=serial)
            hw.open()
            return BmcMultiDm(hw, BmcInfo(
                'vendor-bmc', hw.serial, hw.n_actuators,
                'vendor bmc.BmcDm open_dm(%s)' % serial))
        except Exception as exc:
            if prefer == 'vendor':
                raise
            vendor_err = str(exc)
    else:
        vendor_err = 'skipped'

    if prefer in ('auto', 'usb'):
        try:
            hw = MultiDmUsb(map_name=map_name)
            hw.open()
            return BmcMultiDm(hw, BmcInfo(
                'usb', hw.serial, hw.n_actuators,
                'pyusb MultiDM map=%s' % map_name))
        except Exception as exc:
            if prefer == 'usb':
                raise
            usb_err = str(exc)
    else:
        usb_err = 'skipped'

    # Fall back to sim so GUI / SHM path still runs
    hw = SimulatedBmc()
    hw.open()
    return BmcMultiDm(hw, BmcInfo(
        'sim', hw.serial, hw.n_actuators,
        'fallback sim (vendor: %s; usb: %s)' % (vendor_err, usb_err)))
