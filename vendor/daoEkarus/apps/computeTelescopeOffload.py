#!/usr/bin/env python3
#
# computeTelescopeOffload.py
#
# Fast-TT -> telescope offload: the whole pointing-offset calibration in one
# loop.  Every cycle it reads the current telescope pointing, the calibration
# constants and the averaged fast-TT command, and updates the computed-parameter
# SHMs:
#
#     theta  = theta0 + HA - Dec                          [deg]   (phi on the
#                                                                  calib slide)
#
#     rotMat = ( cos theta  -sin theta ) . ( Sx   0 )              (2 x 2)
#              ( sin theta   cos theta )   ( 0    Sy )
#
#     ( dAlpha )           ( vx )      with [vx, vy] = fastttAvg.im.shm - 50
#     ( dDelta ) = -rotMat  ( vy )     (rolling mean of the fast-TT commands,
#                                       from daoAvgShm; 50 = PI stage centre)
#
# The sign is inverted: the calib relation gives the sky shift produced by the
# TT command, and offloading it to the telescope requires the opposite.  The
# result stays in plain sky RA/Dec convention (what the GUI shows); the TCS
# guiding Dec-axis inversion is handled once in telescopeCtrl.py.
#
# Inputs
#     SHM_TELESCOPE_RADEC   (/tmp/telRaDec.im.shm)   [RA, Dec]        <- telescopeCtrl.py
#     SHM_TELESCOPE_ALTAZ   (/tmp/telAltAz.im.shm)   [Alt, Az, HA]    <- telescopeCtrl.py
#     SHM_FASTTT_CMD_AVG    (/tmp/fastttAvg.im.shm)  [vx, vy]         <- daoAvgShm
#     SHM_TELESCOPE_THETA0  (/tmp/telTheta0.im.shm)  [theta0]  default -100 deg
#     SHM_TELESCOPE_SCALE   (/tmp/telScale.im.shm)   [Sx, Sy]  default 0.58, 0.43
#
# Outputs (updated every cycle)
#     SHM_TELESCOPE_THETA      (/tmp/telThetaAngle.im.shm)  [theta] deg
#     SHM_TELESCOPE_ROTMAT     (/tmp/telRotMat.im.shm)      2 x 2 float32
#     SHM_TELESCOPE_TT_OFFLOAD (/tmp/telTtOffload.im.shm)   [dAlpha, dDelta]
#
# With --send it also writes [dAlpha, dDelta] into SHM_TELESCOPE_GUIDING each
# cycle, i.e. telescopeCtrl.py forwards it to the TCS as a guiding correction.
#
import argparse
import os
import time

import numpy as np
import dao

from daoEkarusShmNames import (
    SHM_TELESCOPE_RADEC,
    SHM_TELESCOPE_ALTAZ,
    SHM_TELESCOPE_THETA0,
    SHM_TELESCOPE_SCALE,
    SHM_TELESCOPE_THETA,
    SHM_TELESCOPE_ROTMAT,
    SHM_TELESCOPE_TT_OFFLOAD,
    SHM_TELESCOPE_GUIDING,
    SHM_FASTTT_CMD_AVG,
)

# HA published in SHM_TELESCOPE_ALTAZ[2] is assumed to be in degrees (matching
# Dec and theta0). Use --ha-hours if the TCS reports HA in hours.
HA_SCALE = 1.0


def wrap180(a):
    """Wrap an angle in degrees to (-180, 180]."""
    return (a + 180.0) % 360.0 - 180.0


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="computeTelescopeOffload.py",
        description=(
            "Fast-TT -> telescope offload. Computes theta = theta0 + HA - Dec, "
            "the 2x2 rotation*scale matrix and the averaged fast-TT command "
            "projected onto the sky, and keeps telThetaAngle / telRotMat / "
            "telTtOffload updated. With --send it also drives telGuiding."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--rate", type=float, default=1.0, help="update rate [Hz]")
    p.add_argument("--ha-hours", action="store_true",
                   help="the HA in telAltAz is in hours, not degrees (x15)")
    p.add_argument("--send", action="store_true",
                   help="also write [dAlpha, dDelta] into telGuiding each cycle "
                        "(telescopeCtrl.py then sends it to the TCS)")
    p.add_argument("--gain", type=float, default=1.0,
                   help="scale factor applied to the offload before --send")
    return p.parse_args(argv)


def _open_when_ready(name, warn_after=5.0):
    """dao.shm() segfaults on a missing shm; wait for the backing file first."""
    t0 = time.time()
    warned = False
    while not os.path.exists(name):
        if not warned and time.time() - t0 > warn_after:
            print(f"waiting for {name} "
                  f"(is daoAvgShm / daoEkarusStartFastTT running?)")
            warned = True
        time.sleep(0.5)
    return dao.shm(name)


def main(argv=None):
    args = parse_args(argv)
    ha_scale = 15.0 if args.ha_hours else HA_SCALE
    dt = 1.0 / args.rate if args.rate > 0 else 1.0

    raDecShm = dao.shm(SHM_TELESCOPE_RADEC)
    altAzShm = dao.shm(SHM_TELESCOPE_ALTAZ)
    theta0Shm = dao.shm(SHM_TELESCOPE_THETA0)
    scaleShm = dao.shm(SHM_TELESCOPE_SCALE)
    thetaShm = dao.shm(SHM_TELESCOPE_THETA)
    rotMatShm = dao.shm(SHM_TELESCOPE_ROTMAT)
    ttOffloadShm = dao.shm(SHM_TELESCOPE_TT_OFFLOAD)
    guidingShm = dao.shm(SHM_TELESCOPE_GUIDING) if args.send else None
    fastttAvgShm = _open_when_ready(SHM_FASTTT_CMD_AVG)

    while True:
        ha = float(altAzShm.get_data()[2, 0]) * ha_scale      # [deg]
        dec = float(raDecShm.get_data()[1, 0])                 # [deg]
        theta0 = float(theta0Shm.get_data()[0, 0])             # [deg]
        sx, sy = np.asarray(scaleShm.get_data(), dtype=float).ravel()[:2]
        v = np.asarray(fastttAvgShm.get_data(), dtype=float).reshape(-1, 1)[:2]-50

        theta = wrap180(theta0 + ha - dec)
        t = np.deg2rad(theta)
        rot = np.array([[np.cos(t), -np.sin(t)],
                        [np.sin(t),  np.cos(t)]])
        rotMat = rot @ np.diag([sx, sy])
        # calib relation gives the sky shift caused by the TT command; the
        # telescope offload is the opposite -> negate.
        dAlphaDelta = -(rotMat @ v)                            # (2, 1)
        dAlphaDelta[1, 0] = -dAlphaDelta[1, 0]

        thetaShm.set_data(np.array([[theta]], dtype=np.float32))
        rotMatShm.set_data(rotMat.astype(np.float32))
        ttOffloadShm.set_data(dAlphaDelta.astype(np.float32))
        if guidingShm is not None:
            guidingShm.set_data((args.gain * dAlphaDelta).astype(np.float32))

        print(f"\rHA={ha:8.3f} Dec={dec:8.3f} theta0={theta0:7.2f} "
              f"-> theta={theta:8.3f}  v=({v[0, 0]:+.4f},{v[1, 0]:+.4f}) "
              f"-> dRaDec=({dAlphaDelta[0, 0]:+.4f},{dAlphaDelta[1, 0]:+.4f})"
              f"{'  [sent]' if guidingShm is not None else ''}", end="")

        time.sleep(dt)


if __name__ == "__main__":
    main()
