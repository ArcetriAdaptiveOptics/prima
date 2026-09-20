#!/usr/bin/env python
"""Smoke: create SHM graph, run integrator + bridges for N steps (no Qt)."""
from __future__ import annotations

import argparse
import sys

import numpy as np

from daoprima.create_shm import create_default_graph
from daoprima.loop import SimpleIntegratorLoop, close_loop, set_loop_gain
from daoprima.bridges import CameraToShmBridge, DemoCamera, DemoDm, ShmToDmBridge
from daoprima import shm as shm_mod
from daoprima import shm_names as N


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--steps', type=int, default=120)
    p.add_argument('--fps', type=float, default=60.0)
    p.add_argument('--close', action='store_true', default=True)
    args = p.parse_args(argv)

    info = create_default_graph()
    print('graph=%s' % info)
    cam = CameraToShmBridge(DemoCamera(), period_s=1.0 / args.fps)
    dm = ShmToDmBridge(DemoDm(), period_s=1.0 / args.fps)
    loop = SimpleIntegratorLoop(target_fps=args.fps)
    set_loop_gain(0.4)
    if args.close:
        close_loop()

    last = None
    for i, last in enumerate(loop.run(n_steps=args.steps, wall_clock=False)):
        cam.step()
        dm.step()
        if i % 30 == 0:
            print('step=%d closed=%s rms_cmd=%.4f rms_modes=%.4f' % (
                last['steps'], last['closed'], last['rms_cmd'],
                last['rms_modes']))

    cmd = shm_mod.shm(N.SHM_DM1_CMD).get_data()
    assert cmd.size == N.SHM_DM1_N_ACTUATORS
    assert last is not None and last['steps'] == args.steps
    print('smoke_ok n_act=%d final_rms_cmd=%.4f' % (
        cmd.size, float(np.std(cmd))))
    return 0


if __name__ == '__main__':
    sys.exit(main())
