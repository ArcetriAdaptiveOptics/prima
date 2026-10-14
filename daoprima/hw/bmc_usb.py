"""Linux USB Multi-DM driver via pyusb (daoHw-style HW process backend).

Mirrors the Windows CIUsbLib Multi path without the COM DLL:
  VID/PID 1781:0ED8 → reset → HV enable → bulk OUT 320-byte frames on EP2.

Vendor commands use Cypress FX2 vendor requests documented in
``BMC SW Design USB.pdf`` (§6.2–6.4). Default map is ``MULTI140.map``
(from profile ``C30W052088.dm``); ``MultiDM-01.map`` remains available.

Normalized commands are float in ``[0, 1]`` (BMC SDK convention); packed to
14-bit-effective 16-bit DAC words (``V = 300 * D / 65536``).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

import numpy as np

from daoprima.hw import bmc_constants as C

_MAPS_DIR = Path(__file__).resolve().parent / 'maps'


@dataclass
class UsbProbeResult:
    present: bool
    devices: List[dict]
    message: str
    cypress_bootloader: bool = False


def probe_usb() -> UsbProbeResult:
    """Enumerate BMC Multi/Mini (and bare Cypress) without claiming the device."""
    try:
        import usb.core
        import usb.util
    except ImportError as exc:
        return UsbProbeResult(
            False, [], 'pyusb not installed (%s); pip install pyusb' % exc)

    found: List[dict] = []
    cypress = False
    for dev in usb.core.find(find_all=True):
        vid, pid = int(dev.idVendor), int(dev.idProduct)
        if vid == C.BMC_MULTI_VID and pid in (C.BMC_MULTI_PID, C.BMC_MINI_PID):
            kind = 'Multi' if pid == C.BMC_MULTI_PID else 'Mini'
            try:
                manu = usb.util.get_string(dev, dev.iManufacturer) or ''
            except Exception:
                manu = ''
            try:
                prod = usb.util.get_string(dev, dev.iProduct) or ''
            except Exception:
                prod = ''
            found.append({
                'vid': vid, 'pid': pid, 'kind': kind,
                'bus': int(getattr(dev, 'bus', -1) or -1),
                'address': int(getattr(dev, 'address', -1) or -1),
                'manufacturer': manu, 'product': prod,
            })
        elif vid == C.CYPRESS_VID and pid == C.CYPRESS_PID_NO_EEPROM:
            cypress = True
            found.append({
                'vid': vid, 'pid': pid, 'kind': 'Cypress-no-EEPROM',
                'bus': int(getattr(dev, 'bus', -1) or -1),
                'address': int(getattr(dev, 'address', -1) or -1),
                'manufacturer': '', 'product': '',
            })

    if found and any(d['kind'] in ('Multi', 'Mini') for d in found):
        return UsbProbeResult(
            True, found,
            'BMC USB device(s) present: %s' % ', '.join(
                '%s %04x:%04x' % (d['kind'], d['vid'], d['pid']) for d in found),
            cypress_bootloader=cypress)
    if cypress:
        return UsbProbeResult(
            False, found,
            'Cypress FX2 without EEPROM (04b4:8613) — firmware not loaded; '
            'power-cycle Multi Driver or load firmware with CIUsbLoader',
            cypress_bootloader=True)
    return UsbProbeResult(
        False, found,
        'No BMC Multi/Mini USB device (expected 1781:0ed8). '
        'Check Multi Driver power, Mini-B cable, and lsusb.')


def load_map(name: str = 'MULTI140.map') -> np.ndarray:
    path = _MAPS_DIR / name
    if not path.is_file():
        # fall back to vendor-sdks copy
        alt = Path.home() / 'git' / 'vendor-sdks' / 'bmc' / 'Map' / name
        if not alt.is_file():
            alt = Path.home() / 'git' / 'vendor-sdks' / 'bmc' / 'Usb' / name
        path = alt if alt.is_file() else path
    arr = np.loadtxt(str(path), dtype=np.int32)
    if arr.size != C.USB_NUM_WORDS_MULTI:
        raise ValueError('map %s has %d entries, need %d' % (
            path, arr.size, C.USB_NUM_WORDS_MULTI))
    return arr


def floats_to_dac(cmd: np.ndarray) -> np.ndarray:
    """Map float [0,1] (or small bipolar around 0 → clip) to uint16 DAC words."""
    x = np.asarray(cmd, dtype=np.float64).ravel()
    # Plain clip to [0, 1].  (The former implicit 'bipolar' remapping of
    # commands containing a negative value made a tiny negative number
    # jump the whole mirror to mid-scale: removed for safety.)
    x = np.clip(np.nan_to_num(x, nan=0.0), 0.0, 1.0)
    # 16-bit word; hardware drops 2 LSBs → 14-bit
    return (x * 65535.0 + 0.5).astype(np.uint16)


def pack_frame(act140: np.ndarray, act_map: np.ndarray) -> bytes:
    """Build 320-byte Multi frame: map[j] selects source index in 160-word buffer."""
    buf = np.zeros(C.USB_NUM_WORDS_MULTI, dtype=np.uint16)
    dac = floats_to_dac(act140)
    n = min(dac.size, C.N_ACTUATORS_USER)
    buf[:n] = dac[:n]
    mapped = buf[act_map]
    return mapped.astype('<u2').tobytes()


class MultiDmUsb:
    """Claim Cambridge Innovations Multi Driver and send mapped frames."""

    def __init__(self, map_name: str = 'MULTI140.map', timeout_ms: int = 1000):
        self.map_name = map_name
        self.timeout_ms = timeout_ms
        self._dev = None
        self._ep_out = None
        self._map = load_map(map_name)
        self._last = np.zeros(C.N_ACTUATORS_USER, dtype=np.float64)
        self.serial = 'USB-MultiDM'
        self.n_actuators = C.N_ACTUATORS_USER

    def open(self, initial=0.5) -> None:
        """Claim the device, enable HV and send ``initial`` (scalar or
        140-vector; ``None`` = send nothing)."""
        import usb.core
        import usb.util

        probe = probe_usb()
        if not probe.present:
            raise RuntimeError(probe.message)

        dev = usb.core.find(idVendor=C.BMC_MULTI_VID, idProduct=C.BMC_MULTI_PID)
        if dev is None:
            raise RuntimeError('Multi DM (1781:0ed8) not found after probe')

        try:
            if dev.is_kernel_driver_active(0):
                dev.detach_kernel_driver(0)
        except (NotImplementedError, usb.core.USBError):
            pass

        try:
            dev.set_configuration()
            usb.util.claim_interface(dev, 0)
        except usb.core.USBError as exc:
            raise RuntimeError(
                'Cannot claim BMC USB device (%s). '
                'Install udev rule (scripts/udev/99-bmc-multidm.rules) '
                'or run once: sudo chmod a+rw '
                '/dev/bus/usb/%03d/%03d' % (
                    exc, int(dev.bus), int(dev.address))) from exc

        cfg = dev.get_active_configuration()
        intf = cfg[(0, 0)]
        ep_out = usb.util.find_descriptor(
            intf,
            custom_match=lambda e: usb.util.endpoint_direction(
                e.bEndpointAddress) == usb.util.ENDPOINT_OUT)
        if ep_out is None:
            raise RuntimeError('No bulk OUT endpoint on BMC Multi USB')

        self._dev = dev
        self._ep_out = ep_out
        try:
            dev.clear_halt(ep_out.bEndpointAddress)
        except Exception:
            pass
        self._reset_and_hv()
        if initial is not None:
            init = np.broadcast_to(np.asarray(initial, dtype=float),
                                   (self.n_actuators,))
            self.send_data(np.clip(init, 0.0, 1.0))

    # ------------------------------------------------------------------
    # VR_SetControlBits (0xF5): wIndex is a BIT MASK, not a CIUsb code:
    #   bit7 = 1 set / 0 clear, bit1 = FRESET, bit2 = FRAME_SYNC,
    #   bit3 = HV_ENAB, bit4 = LV_SHDN, bit5 = EXT_I2C
    # (CIUsbShared.h, J. Codona BMCUSB Linux driver, U. Arizona 2011).
    # The previous implementation sent the CIUsbLib *codes* (0..10) as
    # wIndex, so HV_ENAB was never set and the driver never consumed
    # frames (FIFO full after 4 frames -> USB timeout).  Fixed 2026-10-09.
    BIT_FRESET = 0x02
    BIT_FRAME_SYNC = 0x04
    BIT_HV_ENAB = 0x08
    BIT_LV_SHDN = 0x10

    def _ctrl_bits(self, bit: int, value: bool) -> None:
        assert self._dev is not None
        self._dev.ctrl_transfer(
            0x40, C.VR_SET_CONTROL, 0, (0x80 if value else 0x00) | bit,
            None, timeout=self.timeout_ms)

    def _ctrl_set(self, code: int) -> None:
        """Legacy CIUsb control codes -> correct bit-mask request."""
        table = {C.CTRL_ASSERT_FRAME_SYNC: (self.BIT_FRAME_SYNC, True),
                 C.CTRL_DEASSERT_FRAME_SYNC: (self.BIT_FRAME_SYNC, False),
                 C.CTRL_ASSERT_FRESET: (self.BIT_FRESET, True),
                 C.CTRL_DEASSERT_FRESET: (self.BIT_FRESET, False),
                 C.CTRL_ASSERT_HV_ENAB: (self.BIT_HV_ENAB, True),
                 C.CTRL_DEASSERT_HV_ENAB: (self.BIT_HV_ENAB, False)}
        bit, val = table[code]
        self._ctrl_bits(bit, val)

    def status_bits(self) -> int:
        """bit0 FRAME_ERROR, bit1 RdHvaE (HV active), bit2 CABLE_OK."""
        st = self._ctrl_get_status()
        return int(st[0]) | (int(st[1]) << 8 if len(st) > 1 else 0)

    def _ctrl_get_status(self) -> bytes:
        assert self._dev is not None
        return bytes(self._dev.ctrl_transfer(
            0xC0, C.VR_GET_STATUS, 0, 0, 2, timeout=self.timeout_ms))

    def _reset_and_hv(self) -> None:
        # Codona sequence: FRESET clear -> set, then HV_ENAB set.
        try:
            self._dev.ctrl_transfer(
                0x40, C.VR_RESET_ALL, 0, 0, None, timeout=self.timeout_ms)
        except Exception as exc:
            self._hv_warning = 'ResetAll: %s' % exc
        time.sleep(0.02)
        self._ctrl_bits(self.BIT_FRESET, False)
        time.sleep(0.01)
        self._ctrl_bits(self.BIT_FRESET, True)
        time.sleep(0.01)
        self._ctrl_bits(self.BIT_HV_ENAB, True)
        time.sleep(0.05)

    def send_data(self, cmd: Sequence[float]) -> None:
        if self._dev is None or self._ep_out is None:
            raise RuntimeError('BMC USB not open')
        arr = np.asarray(cmd, dtype=np.float64).ravel()
        if arr.size != self.n_actuators:
            raise ValueError('need %d actuators, got %d' % (
                self.n_actuators, arr.size))
        frame = pack_frame(arr, self._map)
        # CIUsb_StepFrameData ≡ bulk OUT EP2; FRAME_SYNC is reserved/unused
        written = self._dev.write(
            self._ep_out.bEndpointAddress, frame, timeout=self.timeout_ms)
        if written < len(frame):
            raise RuntimeError('short USB write %d / %d' % (written, len(frame)))
        self._last = arr.copy()

    def get_actuator_data(self) -> np.ndarray:
        return self._last.copy()

    def cable_ok(self) -> Optional[bool]:
        """Best-effort CABLE_OK from PortE status (bit 2)."""
        try:
            st = self._ctrl_get_status()
            if not st:
                return None
            return bool(st[0] & 0x04)
        except Exception:
            return None

    def close(self) -> None:
        if self._dev is not None:
            try:
                self._ctrl_bits(self.BIT_HV_ENAB, False)
            except Exception:
                pass
            import usb.util
            try:
                usb.util.release_interface(self._dev, 0)
            except Exception:
                pass
            usb.util.dispose_resources(self._dev)
        self._dev = None
        self._ep_out = None
