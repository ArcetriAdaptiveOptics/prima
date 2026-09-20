#!/usr/bin/env python
"""Smoke: sequential DaoPrima loop (DM → frame → recon → DM)."""
from __future__ import annotations

import argparse
import sys
import time

import numpy as np

from daoprima.create_shm import create_default_graph
from daoprima.loop import close_loop, set_loop_gain
from daoprima.sequential_loop import SequentialClosedLoop
from daoprima import shm as shm_mod
from daoprima import shm_names as N


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--steps', type=int, default=120)
    p.add_argument('--fps', type=float, default=60.0)
    p.add_argument('--uncapped', action='store_true',
                   help='No sleep; measure max sequential Hz')
    p.add_argument('--close', action='store_true', default=True)
    args = p.parse_args(argv)

    info = create_default_graph()
    print('graph=%s' % info)
    print('shm_backend=%s' % shm_mod.backend_name())

    loop = SequentialClosedLoop(target_fps=args.fps)
    set_loop_gain(0.4)
    if args.close:
        close_loop()

    # Causality: force a distinctive DM command, then next step's frame
    # must differ from a zero-DM frame (DemoCamera couples to DM).
    zero_cmd = np.zeros(N.SHM_DM1_N_ACTUATORS, dtype=np.float32)
    poke = zero_cmd.copy()
    poke[0] = 0.35
    poke[1] = -0.22
    shm_mod.shm(N.SHM_DM1_CMD).set_data(zero_cmd)
    loop.dm_bridge.step()  # apply zero
    frame_zero = np.asarray(loop.cam_bridge.step(), dtype=float)
    shm_mod.shm(N.SHM_DM1_CMD).set_data(poke)
    loop.dm_bridge.step()  # apply poke
    frame_poke = np.asarray(loop.cam_bridge.step(), dtype=float)
    causal_delta = float(np.max(np.abs(frame_poke - frame_zero)))
    print('causal_frame_delta=%.4f (expect >0)' % causal_delta)
    assert causal_delta > 1.0, 'frame did not react to applied DM'

    # Reset for timed sequential run
    shm_mod.shm(N.SHM_DM1_CMD).set_data(zero_cmd)
    loop = SequentialClosedLoop(target_fps=args.fps)
    set_loop_gain(0.4)
    close_loop()

    wall = not args.uncapped
    dts = []
    last = None
    t0 = time.perf_counter()
    for i, last in enumerate(loop.run(n_steps=args.steps, wall_clock=wall)):
        dts.append(last['dt_s'])
        if i % 30 == 0:
            print('step=%d seq=%s rms_cmd=%.4f rms_modes=%.4f dt_ms=%.2f' % (
                last['steps'], '→'.join(last['sequence']),
                last['rms_cmd'], last['rms_modes'], 1e3 * last['dt_s']))
    elapsed = time.perf_counter() - t0
    loop.assert_sequential()

    dts = np.asarray(dts)
    mean_hz = args.steps / elapsed
    uncapped_hz = 1.0 / float(np.mean(dts))
    print('smoke_ok sequential=1 causal_delta=%.4f' % causal_delta)
    print('achieved_Hz=%.2f  mean_step_Hz=%.1f  wall_clock=%s' % (
        mean_hz, uncapped_hz, wall))
    print('dt_breakdown_ms dm=%.2f frame=%.2f recon=%.3f cmd=%.3f' % (
        1e3 * last['dt_dm_s'], 1e3 * last['dt_frame_s'],
        1e3 * last['dt_recon_s'], 1e3 * last['dt_cmd_s']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
