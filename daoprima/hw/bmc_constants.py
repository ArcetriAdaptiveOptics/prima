"""BMC Multi-DM USB constants (from CiGenUSB.inf + CIUsbLib.h + BMC SW Design)."""
from __future__ import annotations

# Cambridge Innovations Multi / Mini Driver (CiGenUSB.inf)
BMC_MULTI_VID = 0x1781
BMC_MULTI_PID = 0x0ED8
BMC_MINI_PID = 0x0ED9
# Unprogrammed Cypress FX2 (firmware may still need load)
CYPRESS_VID = 0x04B4
CYPRESS_PID_NO_EEPROM = 0x8613

# USB frame (Multi): 160 DAC words × 2 bytes = 320
USB_NUM_WORDS_MULTI = 160
USB_BYTES_PER_FRAME_MULTI = USB_NUM_WORDS_MULTI * 2
N_ACTUATORS_USER = 140  # Multi-DM 5.5 µm CDM

# FX2 vendor requests (BMC SW Design USB §6.4)
VR_GET_FIRMWARE_VER = 0xF0
VR_GET_STATUS = 0xF4
VR_SET_CONTROL = 0xF5

# CIUsb_SetControl codes
CTRL_ASSERT_FRAME_SYNC = 0
CTRL_DEASSERT_FRAME_SYNC = 1
CTRL_ASSERT_FRESET = 2
CTRL_DEASSERT_FRESET = 3
CTRL_ASSERT_HV_ENAB = 4
CTRL_DEASSERT_HV_ENAB = 5

# EP2 bulk OUT (FX2 FIFO) — typical Cypress alt-setting; discovered at open
DEFAULT_OUT_EP = 0x02
