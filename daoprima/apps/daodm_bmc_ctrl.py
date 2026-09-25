#!/usr/bin/env python3
"""daodmBmcCtrl — DAO-style BMC Multi-DM controller (SHM → USB).

Pattern mirrors daoEkarus::

    daodmAlpaoCtrl -L BAX787 /tmp/dm1Cmd.im.shm

and daoHw meadowlark (open vendor device, poll command SHM, apply on change)::

    daodm_bmc_ctrl [--shm /tmp/prima_dm1Cmd.im.shm] [--prefer auto|usb|vendor|sim]

GUI / loop write ``SHM_DM1_CMD``; this process owns the USB cable.
"""
from __future__ import annotations

import argparse
import signal
import sys
import time

import numpy as np

from daoprima import shm as shm_mod
from daoprima import shm_names as N
from daoprima.create_shm import create_default_graph
from daoprima.hw.bmc_dm import open_bmc_dm


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='DAO BMC Multi-DM SHM controller')
    p.add_argument('-s', '--shm', default=N.SHM_DM1_CMD,
                   help='command SHM path (default: %s)' % N.SHM_DM1_CMD)
    p.add_argument('--prefer', default='auto',
                   choices=['auto', 'usb', 'vendor', 'sim'])
    p.add_argument('--serial', default='C30W052088',
                   help='BMC profile / serial (vendor SDK open_dm)')
    p.add_argument('--map', default='MULTI140.map',
                   help='actuator map (profile C30W052088 uses MULTI140.map)')
    p.add_argument('--period', type=float, default=0.002,
                   help='poll period seconds (default 2 ms)')
    p.add_argument('--create-graph', action='store_true',
                   help='allocate default Prima SHM graph before open')
    p.add_argument('--once', action='store_true',
                   help='apply current SHM once and exit (USB smoke)')
    p.add_argument('--poke', type=float, default=None,
                   help='with --once: write mid flat + this poke amp on act 0')
    args = p.parse_args(argv)

    if args.create_graph:
        create_default_graph()

    dm = open_bmc_dm(
        prefer=args.prefer, serial=args.serial, map_name=args.map)
    print('bmc_backend=%s serial=%s n_act=%d msg=%s' % (
        dm.backend, dm.serial, dm.num_actuators(), dm.info.message),
        flush=True)

    n = dm.num_actuators()
    cmd_shm = shm_mod.shm(args.shm, np.zeros(n, dtype=np.float32))

    stop = {'flag': False}

    def _stop(*_a):
        stop['flag'] = True

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    if args.once:
        if args.poke is not None:
            shape = np.full(n, 0.5, dtype=np.float32)
            shape[0] = float(np.clip(0.5 + args.poke, 0.0, 1.0))
            cmd_shm.set_data(shape)
        cmd = np.asarray(cmd_shm.get_data(), dtype=float).ravel()
        if cmd.size != n:
            cmd = np.resize(cmd, n)
        dm.send_data(cmd)
        rb = dm.get_actuator_data()
        print('applied min=%.4f max=%.4f readback_max=%.4f' % (
            float(cmd.min()), float(cmd.max()), float(np.max(np.abs(rb)))),
            flush=True)
        dm.close()
        return 0

    last = None
    last_gen = cmd_shm.get_counter()
    print('watching %s (backend=%s)' % (args.shm, shm_mod.backend_name()),
          flush=True)
    while not stop['flag']:
        # Prefer wait when possible; fall back to poll
        updated = False
        if hasattr(cmd_shm, 'wait_for_update'):
            updated = cmd_shm.wait_for_update(last_gen, timeout=args.period)
            if updated:
                last_gen = cmd_shm.get_counter()
        else:
            time.sleep(args.period)

        cmd = np.asarray(cmd_shm.get_data(), dtype=float).ravel()
        if cmd.size != n:
            cmd = np.resize(cmd, n)
        if last is not None and np.allclose(cmd, last):
            if not updated:
                continue
        try:
            dm.send_data(cmd)
            last = cmd.copy()
            # stamp frame_id_dm if present
            try:
                fid = shm_mod.shm(N.SHM_FRAME_ID)
                shm_mod.shm(N.SHM_FRAME_ID_DM).set_data(fid.get_data())
            except Exception:
                pass
        except Exception as exc:
            print('send_failed: %s' % exc, flush=True)
            time.sleep(0.2)

    print('closing BMC', flush=True)
    dm.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
