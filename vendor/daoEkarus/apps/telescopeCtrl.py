#!/usr/bin/env python3
#
# telescopeCtrl.py
#
# Ekarus telescope control loop.  Must run in the "ekarus" conda environment
# (it imports ekarus_tcs):  conda run -n ekarus telescopeCtrl.py
#
# Inputs - waits (blocking on their semaphores) for either SHM to change and
# forwards the request to the telescope through the ICS / TCS interface:
#     SHM_TELESCOPE_OFFSET  (/tmp/telOffset.im.shm)  -> client.set_offset()
#     SHM_TELESCOPE_GUIDING (/tmp/telGuiding.im.shm) -> client.set_guiding()
# each a (2, 1) float32 array [x_arcsec, y_arcsec].
#
# Outputs - polls the TCS and republishes everything it exposes:
#     SHM_TELESCOPE_RADEC   (/tmp/telRaDec.im.shm)   [RA, Dec] deg          ~1 Hz
#     SHM_TELESCOPE_ALTAZ   (/tmp/telAltAz.im.shm)   [Alt, Az, HA] deg      ~1 Hz
#     SHM_TELESCOPE_STATUS  (/tmp/telStatus.im.shm)  [power_on, tracking_on,
#                                                     is_slewing,
#                                                     ha_limit_reached,
#                                                     alt_limit_reached]    ~1 Hz
#     SHM_TELESCOPE_AIRMASS (/tmp/telAirmass.im.shm) [airmass]            ~0.2 Hz
#     SHM_TELESCOPE_FOCUS   (/tmp/telFocus.im.shm)   [M2 Z focus] mm      ~0.2 Hz
#     SHM_TELESCOPE_DOME    (/tmp/telDome.im.shm)    [shutter 0/1/2]      ~0.2 Hz
#
import threading
import time

import dao
import numpy as np
from daoEkarusShmNames import (
    SHM_TELESCOPE_OFFSET,
    SHM_TELESCOPE_GUIDING,
    SHM_TELESCOPE_RADEC,
    SHM_TELESCOPE_ALTAZ,
    SHM_TELESCOPE_STATUS,
    SHM_TELESCOPE_AIRMASS,
    SHM_TELESCOPE_FOCUS,
    SHM_TELESCOPE_DOME,
    SHM_TELESCOPE_CONTROL_ENABLE,
)
from ekarus_tcs.client.client_factory import create_tcs_client

# Fast telemetry rate (position + status) [Hz]; the slow telemetry (airmass,
# focus, dome) is polled once every SLOW_EVERY fast ticks.
POSITION_POLL_HZ = 1.0
SLOW_EVERY = 5

# Per-axis sign applied to telGuiding / telOffset (sky RA/Dec convention) just
# before it is handed to the TCS. The Copernico guiding Dec axis runs opposite
# to sky Dec, so a +Dec value in the shm must be sent as -Dec. This is the ONE
# place the flip lives: everything upstream (the hand paddle, ekarusComputeTel-
# Offload, the compass) works in plain sky convention, so "what the GUI shows is
# what the telescope does".
TCS_GUIDING_SIGN = (1.0, 1.0)   # (RA, Dec)

client = create_tcs_client()
# The TCS client talks to the server over a single REQ socket, so every call has
# to be serialized between the input threads and the polling loop.
clientLock = threading.Lock()

offsetShm = dao.shm(SHM_TELESCOPE_OFFSET)
guidingShm = dao.shm(SHM_TELESCOPE_GUIDING)
enableShm = dao.shm(SHM_TELESCOPE_CONTROL_ENABLE)
raDecShm = dao.shm(SHM_TELESCOPE_RADEC)
altAzShm = dao.shm(SHM_TELESCOPE_ALTAZ)
statusShm = dao.shm(SHM_TELESCOPE_STATUS)
airmassShm = dao.shm(SHM_TELESCOPE_AIRMASS)
focusShm = dao.shm(SHM_TELESCOPE_FOCUS)
domeShm = dao.shm(SHM_TELESCOPE_DOME)


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------
def _num(d, *keys, default=np.nan):
    """First numeric value found under any of `keys` in dict `d`."""
    if isinstance(d, dict):
        for k in keys:
            if k in d and d[k] is not None:
                try:
                    return float(d[k])
                except (TypeError, ValueError):
                    pass
    return default


def _call(fn, *args, **kw):
    """Run a TCS client call under the lock, returning None on any error."""
    try:
        with clientLock:
            return fn(*args, **kw)
    except Exception as e:  # noqa: BLE001 - keep the loop alive on any TCS hiccup
        print(f"{getattr(fn, '__name__', fn)} failed: {e}")
        return None


def _write(shm, values):
    shm.set_data(np.asarray(values, dtype=np.float32).reshape(-1, 1))


# ----------------------------------------------------------------------------
# input threads
# ----------------------------------------------------------------------------
def _control_enabled():
    """True when the operator has armed commanding the telescope (master switch)."""
    try:
        return float(enableShm.get_data().ravel()[0]) > 0.5
    except Exception:
        return False


def _is_slewing():
    """True when the telescope is slewing (set_offset is refused during a slew)."""
    try:
        return float(statusShm.get_data().ravel()[2]) > 0.5
    except Exception:
        return False


def waitOffsetLoop():
    """Send a pointing offset to the telescope whenever telOffset changes.

    Gated by the telescope-control master switch, and skipped while the
    telescope is slewing (the TCS refuses set_offset then). telOffset holds a
    sky RA/Dec delta; the per-axis TCS sign is applied here.
    """
    while True:
        data = offsetShm.get_data(check=True, semNb=5)
        xOff, yOff = float(data[0, 0]), float(data[1, 0])   # sky convention
        if xOff == 0.0 and yOff == 0.0:
            continue                       # [0, 0] is the "cleared" state, not a move
        if not _control_enabled():
            print(f"set_offset blocked (telescope control disabled): x={xOff} y={yOff}")
            continue
        if _is_slewing():
            print(f"set_offset blocked (telescope slewing): x={xOff} y={yOff}")
            continue
        xTcs = xOff * TCS_GUIDING_SIGN[0]
        yTcs = yOff * TCS_GUIDING_SIGN[1]
        print(f"set_offset shm(x={xOff} y={yOff}) -> tcs(x={xTcs} y={yTcs}) arcsec")
        res = _call(client.set_offset, xTcs, yTcs)
        print(f"  returned {res}")


def waitGuidingLoop():
    """Send a guiding correction to the telescope whenever the guiding SHM changes."""
    while True:
        data = guidingShm.get_data(check=True, semNb=6)
        xCorr, yCorr = float(data[0, 0]), float(data[1, 0])   # sky convention
        if not _control_enabled():
            print(f"set_guiding blocked (telescope control disabled): x={xCorr} y={yCorr}")
            continue
        xTcs = xCorr * TCS_GUIDING_SIGN[0]
        yTcs = yCorr * TCS_GUIDING_SIGN[1]
        print(f"set_guiding shm(x={xCorr} y={yCorr}) -> tcs(x={xTcs} y={yTcs}) arcsec")
        res = _call(client.set_guiding, x_corr_arcsec=xTcs, y_corr_arcsec=yTcs)
        print(f"  returned {res}")


# ----------------------------------------------------------------------------
# telemetry polling
# ----------------------------------------------------------------------------
def pollFast():
    pos = _call(client.get_position)
    if pos is not None:
        _write(raDecShm, [_num(pos, "Tel_RA", "RA", "RA_J2000"),
                          _num(pos, "Tel_Dec", "Dec", "Dec_J2000")])
        _write(altAzShm, [_num(pos, "Alt", "Tel_Alt"),
                          _num(pos, "Az", "Tel_Az"),
                          _num(pos, "HA", "Tel_HA")])

    status = _call(client.get_status)
    limits = _call(client.get_limits)
    if status is not None or limits is not None:
        status = status or {}
        limits = limits or {}
        _write(statusShm, [
            1.0 if status.get("power_on") else 0.0,
            1.0 if status.get("tracking_on") else 0.0,
            1.0 if status.get("is_slewing") else 0.0,
            1.0 if limits.get("ha_limit_reached") else 0.0,
            1.0 if limits.get("alt_limit_reached") else 0.0,
        ])


def pollSlow():
    tel = _call(client.get_telemetry_data)
    if tel is not None:
        _write(airmassShm, [_num(tel, "Airmass", "airmass")])

    focus = _call(client.get_focus_position)
    if focus is not None:
        try:
            _write(focusShm, [float(focus)])
        except (TypeError, ValueError):
            pass

    dome = _call(client.get_dome_status)
    if dome is not None:
        val = _num(dome, "DomeShutterStatus", "DomeShutter", "shutter") \
            if isinstance(dome, dict) else _num({"v": dome}, "v")
        _write(domeShm, [val])


# ----------------------------------------------------------------------------
threading.Thread(target=waitOffsetLoop, daemon=True).start()
threading.Thread(target=waitGuidingLoop, daemon=True).start()

dt = 1.0 / POSITION_POLL_HZ
tick = 0
nextTime = time.perf_counter()
while True:
    pollFast()
    if tick % SLOW_EVERY == 0:
        pollSlow()
    tick += 1

    nextTime += dt
    remaining = nextTime - time.perf_counter()
    if remaining > 0:
        time.sleep(remaining)
    else:
        nextTime = time.perf_counter()
