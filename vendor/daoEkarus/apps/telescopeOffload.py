#!/usr/bin/env python3
#
# telescopeOffload.py
#
# Automatic fast-TT -> telescope offload loop.
#
# Every telOffloadPeriod seconds, if the offload is ENABLED and the fast-TT loop
# is CLOSED, it pushes the current TT offload vector to the telescope:
#
#     telGuiding = gain * telTtOffload          [dRA, dDec] arcsec
#
# telescopeCtrl.py then forwards telGuiding to the TCS as a guiding correction
# (still subject to its own master telControlEnable switch). telTtOffload is
# kept up to date by computeTelescopeOffload.py.
#
# Control SHMs (defaults from daoEkarusCreateShm.py):
#     SHM_TELESCOPE_OFFLOAD_ENABLE   0/1    active / inactive        (default 0)
#     SHM_TELESCOPE_OFFLOAD_PERIOD   [s]    seconds between pushes    (default 20)
#     SHM_TELESCOPE_OFFLOAD_GAIN     gain   applied to telTtOffload   (default 0.5)
#
import argparse
import time

import numpy as np
import dao

from daoEkarusShmNames import (
    SHM_TELESCOPE_TT_OFFLOAD,
    SHM_TELESCOPE_GUIDING,
    SHM_TELESCOPE_OFFLOAD_ENABLE,
    SHM_TELESCOPE_OFFLOAD_PERIOD,
    SHM_TELESCOPE_OFFLOAD_GAIN,
    SHM_FASTTT_LOOP_CL_SWITCH,
)

# The loop whose "closed" state gates the offload: we are offloading the fast
# TT mirror, so its command average is only meaningful with that loop closed.
LOOP_SWITCH_SHM = SHM_FASTTT_LOOP_CL_SWITCH

MIN_PERIOD = 1.0    # s, floor applied to the period shm value
POLL = 0.5          # s, how often the loop wakes to re-check enable / period


def _scalar(shm, default=0.0):
    try:
        return float(np.asarray(shm.get_data(), dtype=float).ravel()[0])
    except Exception:
        return default


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="telescopeOffload.py",
        description=(
            "Automatic fast-TT -> telescope offload. Every telOffloadPeriod "
            "seconds, when enabled and the fast-TT loop is closed, writes "
            "gain * telTtOffload into telGuiding."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--once", action="store_true",
                   help="do a single offload push and exit "
                        "(ignores the enable / loop / period gating)")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    ttOffloadShm = dao.shm(SHM_TELESCOPE_TT_OFFLOAD)
    guidingShm = dao.shm(SHM_TELESCOPE_GUIDING)
    enableShm = dao.shm(SHM_TELESCOPE_OFFLOAD_ENABLE)
    periodShm = dao.shm(SHM_TELESCOPE_OFFLOAD_PERIOD)
    gainShm = dao.shm(SHM_TELESCOPE_OFFLOAD_GAIN)
    loopShm = dao.shm(LOOP_SWITCH_SHM)

    def push():
        gain = _scalar(gainShm, 0.5)
        off = np.asarray(ttOffloadShm.get_data(), dtype=np.float32).reshape(-1, 1)[:2]
        cmd = (gain * off).astype(np.float32)
        guidingShm.set_data(cmd)
        return gain, off.ravel(), cmd.ravel()

    if args.once:
        g, o, c = push()
        print(f"offload push (once): gain={g}  telTtOffload={o}  -> telGuiding={c}")
        return

    print(f"telescopeOffload: enable<-{SHM_TELESCOPE_OFFLOAD_ENABLE}  "
          f"period<-{SHM_TELESCOPE_OFFLOAD_PERIOD}  gain<-{SHM_TELESCOPE_OFFLOAD_GAIN}  "
          f"loop<-{LOOP_SWITCH_SHM}")

    next_push = time.monotonic()
    while True:
        now = time.monotonic()
        if now >= next_push:
            period = max(_scalar(periodShm, 20.0), MIN_PERIOD)
            enabled = _scalar(enableShm) > 0.5
            loop_closed = _scalar(loopShm) > 0.5
            stamp = time.strftime('%H:%M:%S')
            if enabled and loop_closed:
                g, o, c = push()
                print(f"\r{stamp} offload  gain={g:.3f}  "
                      f"telTtOffload=({o[0]:+.3f},{o[1]:+.3f}) -> "
                      f"telGuiding=({c[0]:+.3f},{c[1]:+.3f})   next in {period:.0f}s   ",
                      end="", flush=True)
            else:
                why = "disabled" if not enabled else "loop OPEN"
                print(f"\r{stamp} offload skipped ({why})   recheck in {period:.0f}s"
                      f"                          ", end="", flush=True)
            next_push = now + period
        time.sleep(POLL)


if __name__ == "__main__":
    main()
