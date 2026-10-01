"""Drop 1 / Prisma lab work-mode defaults.

Single source for GUI spins, metrology engine, and Aravis full-frame setup.
Relaunch with ``prima-gui --live`` comes up at these values.

Geometry note for dark: see ``DARK_OUTSIDE_DIAMETER_OVERSHOOT`` in
``prima.metrology.engine`` (exclusion radius = 1.2× pupil radius).
"""
from __future__ import annotations

import os

# --- PWFS modulator (PI S-334 @ E-518) ---
DEFAULT_MOD_RADIUS_MRAD = float(os.environ.get('PRIMA_MOD_RADIUS_MRAD', '4.0'))
DEFAULT_MOD_FREQ_HZ = float(os.environ.get('PRIMA_MOD_FREQ_HZ', '20.0'))
DEFAULT_MOD_CENTER_MRAD = (0.0, 0.0)

# --- Camera (Manta Mono12) ---
# Integration time with Lock off — pick so pupils sit well below 4095 ADU
# at the lab fiber / 4 mrad work point. Override with PRIMA_EXPOSURE_MS.
DEFAULT_EXPOSURE_MS = float(os.environ.get('PRIMA_EXPOSURE_MS', '40.0'))
DEFAULT_LOCK_EXP_TO_FREQ = False  # keep unlocked so Mono12 can stay unsaturated
CAMERA_FULL_WIDTH = int(os.environ.get('PRIMA_CAMERA_WIDTH', '2048'))
CAMERA_FULL_HEIGHT = int(os.environ.get('PRIMA_CAMERA_HEIGHT', '2048'))
DEFAULT_PIXEL_FORMAT = 'Mono12'

# Display ROI = full frame (not a crop). Sensor ROI is also forced full-frame.
DEFAULT_DISPLAY_ROI = (0, 0, CAMERA_FULL_WIDTH, CAMERA_FULL_HEIGHT)

# Hosts (lab NIC)
DEFAULT_MANTA_IP = os.environ.get('PRIMA_ARAVIS_IP', '192.168.30.189')
DEFAULT_E518_HOST = os.environ.get('PRIMA_E518_HOST', '192.168.30.190')
DEFAULT_E518_PORT = int(os.environ.get('PRIMA_E518_PORT', '50000'))
