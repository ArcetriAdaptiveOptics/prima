#!/usr/bin/env python
"""Smoke: pipelined DaoPrima loop with frame_id end-to-end + GPU MVM status."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from daoprima.create_shm import create_default_graph
from daoprima.loop import close_loop, set_loop_gain
from daoprima.mvm import gpu_status, MatrixVectorMultiply
from daoprima.pipeline import PipelinedClosedLoop
from daoprima import shm as shm_mod
from daoprima import shm_names as N


def _maybe_plot(out: Path, ids: list) -> None:
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except Exception as exc:
        print('plot_skip=%s' % exc)
        return
    cam = [s['cam'] for s in ids]
    dm = [s['dm'] for s in ids]
    fig, ax = plt.subplots(figsize=(7.5, 3.2))
    fig.patch.set_facecolor('#0b1015')
    ax.set_facecolor('#0b1015')
    ax.plot(cam, color='#7ec8e3', lw=1.2, label='cam frame_id')
    ax.plot(dm, color='#30c0a8', lw=1.2, label='dm frame_id stamp')
    ax.set_xlabel('pipeline sample', color='#8a9bb0')
    ax.set_ylabel('frame_id', color='#8a9bb0')
    ax.tick_params(colors='#c5d0dc')
    for spine in ax.spines.values():
        spine.set_color('#2a3441')
    ax.legend(facecolor='#121820', edgecolor='#2a3441', labelcolor='#e8eef7')
    ax.set_title('DaoPrima frame_id cam→DM (pipelined)', color='#e8eef7')
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=120, facecolor=fig.get_facecolor())
    plt.close(fig)
    print('plot_saved=%s' % out)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--frames', type=int, default=80,
                   help='DM-stage frames to wait for')
    p.add_argument('--fps', type=float, default=60.0)
    p.add_argument('--cpu-only', action='store_true',
                   help='Force NumPy MVM (skip CuPy even if present)')
    p.add_argument('--plot', type=Path, default=None)
    p.add_argument('--log', type=Path, default=None)
    args = p.parse_args(argv)

    info = create_default_graph()
    print('graph=%s' % info)
    print('shm_backend=%s' % shm_mod.backend_name())

    gstat = gpu_status()
    print('gpu_status=%s' % json.dumps(gstat))

    # Unit check: MVM CPU vs GPU (if available) agree
    rng = np.random.default_rng(0)
    m = rng.standard_normal((140, 20)).astype(np.float32)
    v = rng.standard_normal(20).astype(np.float32)
    cpu = MatrixVectorMultiply(m, prefer_gpu=False)
    y_cpu = cpu.multiply(v)
    prefer = not args.cpu_only
    gpu_m = MatrixVectorMultiply(m, prefer_gpu=prefer)
    y_pref = gpu_m.multiply(v)
    mvm_err = float(np.max(np.abs(y_cpu - y_pref)))
    print('mvm_backend=%s mvm_vs_cpu_max_abs=%.3e' % (
        gpu_m.backend, mvm_err))
    assert mvm_err < 1e-4, 'GPU/CPU MVM mismatch'

    loop = PipelinedClosedLoop(
        target_fps=args.fps, prefer_gpu=prefer)
    set_loop_gain(0.4)
    close_loop()
    loop.start()
    try:
        ok = loop.wait_for_frames(args.frames, timeout=max(15.0, args.frames / max(args.fps, 1) * 3))
        snap = loop.snapshot()
        print('snapshot=%s' % {k: snap[k] for k in (
            'cam_frames', 'recon_frames', 'rtc_frames', 'dm_frames',
            'frame_id', 'frame_id_recon', 'frame_id_rtc', 'frame_id_dm',
            'mvm_backend', 'rms_cmd', 'rms_modes', 'closed')})
        if not ok:
            print('FAIL: timed out waiting for %d dm frames' % args.frames)
            return 1
        loop.assert_frame_ids_match(min_samples=min(20, max(5, args.frames // 4)))
        # Live SHM stamps must agree on the latest completed DM frame
        fid_r = int(shm_mod.shm(N.SHM_FRAME_ID_RECON).get_data().ravel()[0])
        fid_t = int(shm_mod.shm(N.SHM_FRAME_ID_RTC).get_data().ravel()[0])
        fid_d = int(shm_mod.shm(N.SHM_FRAME_ID_DM).get_data().ravel()[0])
        fid_c = int(shm_mod.shm(N.SHM_FRAME_ID).get_data().ravel()[0])
        print('shm_frame_ids cam=%d recon=%d rtc=%d dm=%d' % (
            fid_c, fid_r, fid_t, fid_d))
        assert fid_r == fid_t == fid_d, 'live SHM frame_id stamps disagree'
        assert fid_c >= fid_d, 'camera frame_id behind DM'
    finally:
        loop.stop()

    summary = {
        'pass': True,
        'pipeline': 'cam→recon→rtc→dm',
        'mvm_backend': snap['mvm_backend'],
        'gpu_status': gstat,
        'dm_frames': snap['dm_frames'],
        'last_frame_ids': {
            'cam': fid_c, 'recon': fid_r, 'rtc': fid_t, 'dm': fid_d,
        },
        'id_log_tail': loop.id_log[-10:],
        'mvm_vs_cpu_max_abs': mvm_err,
    }
    if args.plot:
        _maybe_plot(args.plot, loop.id_log)
    if args.log:
        args.log.parent.mkdir(parents=True, exist_ok=True)
        args.log.write_text(json.dumps(summary, indent=2))
        print('log_saved=%s' % args.log)

    print('smoke_ok pipelined=1 frame_id_match=1 mvm=%s' % snap['mvm_backend'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
