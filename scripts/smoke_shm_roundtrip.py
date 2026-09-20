#!/usr/bin/env python
"""
DaoPrima SHM round-trip smoke — synthetic Manta frames + BMC 140-act commands.

Exercises daoEkarus-shaped paths in ``daoprima.shm_names`` via the DaoPrima SHM
backend (real ``dao.shm`` if installed, else file-backed memmap under /tmp).

Modes:
  default     single-process producer→consumer integrity
  --cross-process  two OS processes (writer then reader) on the same files

Exit 0 on PASS, 1 on FAIL.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from daoprima import shm as shm_mod  # noqa: E402
from daoprima import shm_names as N  # noqa: E402
from daoprima.bridges import DemoDm  # noqa: E402


FRAME_HW = (128, 128)
N_ACT = N.SHM_DM1_N_ACTUATORS
TOL = 0.0  # float32 exact for our synthetic payloads


def _checksum(arr: np.ndarray) -> str:
    a = np.ascontiguousarray(arr)
    return hashlib.sha256(a.tobytes(order='C')).hexdigest()[:16]


def _synthetic_frame(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:FRAME_HW[0], 0:FRAME_HW[1]]
    frame = np.zeros(FRAME_HW, dtype=np.float32)
    centers = [(0.30, 0.30), (0.30, 0.70), (0.70, 0.30), (0.70, 0.70)]
    for i, (cy, cx) in enumerate(centers):
        r2 = (yy - cy * FRAME_HW[0]) ** 2 + (xx - cx * FRAME_HW[1]) ** 2
        frame += (80.0 + 10 * i) * np.exp(-r2 / (2 * (0.09 * FRAME_HW[0]) ** 2))
    frame += 5.0 * np.sin(0.2 * seed + xx / 15.0)
    frame += rng.normal(0, 0.5, FRAME_HW).astype(np.float32)
    return np.clip(frame, 0, 255).astype(np.float32)


def _synthetic_dm_cmd(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed + 1000)
    cmd = 0.05 * np.sin(
        0.07 * seed + np.arange(N_ACT, dtype=np.float32) * 0.21)
    cmd += rng.normal(0, 0.01, N_ACT).astype(np.float32)
    cmd[3] = 0.123456  # distinctive poke for log visibility
    return cmd.astype(np.float32)


def produce(seed: int = 7) -> dict:
    """Writer: synthetic WFS frame + 140-act DM command into SHM paths."""
    shm_mod.reset_registry()
    frame = _synthetic_frame(seed)
    cmd = _synthetic_dm_cmd(seed)

    wfs = shm_mod.shm(N.SHM_WFS_FRAME, frame)
    dm = shm_mod.shm(N.SHM_DM1_CMD, cmd)
    # also stamp fps / acq like a camera bridge would
    shm_mod.shm(N.SHM_WFS_FPS, np.array([[60.0]], dtype=np.float32))
    shm_mod.shm(N.SHM_WFS_ACQ, np.ones((1, 1), dtype=np.uint32))

    meta = {
        'role': 'produce',
        'backend': getattr(wfs, 'backend', shm_mod.backend_name()),
        'shm_backend': shm_mod.backend_name(),
        'seed': seed,
        'frame_path': N.SHM_WFS_FRAME,
        'dm_path': N.SHM_DM1_CMD,
        'frame_shape': list(frame.shape),
        'frame_dtype': str(frame.dtype),
        'frame_checksum': _checksum(frame),
        'frame_minmax': [float(frame.min()), float(frame.max())],
        'dm_shape': list(cmd.shape),
        'dm_dtype': str(cmd.dtype),
        'dm_checksum': _checksum(cmd),
        'dm_act3': float(cmd[3]),
        'dm_rms': float(cmd.std()),
    }
    # force flush for file backend
    wfs.set_data(frame)
    dm.set_data(cmd)
    return meta


def consume(expected: dict, apply_dm: bool = True) -> dict:
    """Reader: pull SHM, check integrity, optionally apply to DemoDm."""
    shm_mod.reset_registry()  # drop stale handles; re-open files fresh
    # reopen without creating zeros if file exists
    wfs = shm_mod.shm(N.SHM_WFS_FRAME)
    dm = shm_mod.shm(N.SHM_DM1_CMD)

    frame = np.asarray(wfs.get_data())
    cmd = np.asarray(dm.get_data()).ravel()

    frame_err = None
    dm_err = None
    # compare against expected synthetic regeneration
    want_frame = _synthetic_frame(int(expected['seed']))
    want_cmd = _synthetic_dm_cmd(int(expected['seed']))

    if frame.shape != want_frame.shape:
        frame_ok = False
        frame_max_abs = float('inf')
    else:
        frame_max_abs = float(np.max(np.abs(frame.astype(np.float64) -
                                            want_frame.astype(np.float64))))
        frame_ok = frame_max_abs <= TOL and _checksum(frame) == expected[
            'frame_checksum']

    if cmd.shape != want_cmd.shape:
        dm_ok = False
        dm_max_abs = float('inf')
    else:
        dm_max_abs = float(np.max(np.abs(cmd.astype(np.float64) -
                                         want_cmd.astype(np.float64))))
        dm_ok = dm_max_abs <= TOL and _checksum(cmd) == expected['dm_checksum']

    dm_applied_ok = True
    applied_err = 0.0
    if apply_dm:
        sim = DemoDm(n=N_ACT)
        sim.set_shape(cmd)
        got = sim.get_shape()
        applied_err = float(np.max(np.abs(got - cmd)))
        dm_applied_ok = applied_err <= TOL and got.shape == (N_ACT,)

    result = {
        'role': 'consume',
        'backend': getattr(wfs, 'backend', shm_mod.backend_name()),
        'shm_backend': shm_mod.backend_name(),
        'frame_shape_read': list(frame.shape),
        'frame_checksum_read': _checksum(frame),
        'frame_max_abs_error': frame_max_abs,
        'frame_ok': bool(frame_ok),
        'dm_shape_read': list(cmd.shape),
        'dm_checksum_read': _checksum(cmd),
        'dm_max_abs_error': dm_max_abs,
        'dm_act3_read': float(cmd[3]) if cmd.size > 3 else None,
        'dm_ok': bool(dm_ok),
        'dm_applied_ok': bool(dm_applied_ok),
        'dm_applied_max_abs_error': applied_err,
        'pass': bool(frame_ok and dm_ok and dm_applied_ok),
    }
    if frame_err:
        result['frame_err'] = frame_err
    if dm_err:
        result['dm_err'] = dm_err
    return result


def _save_plot(out_png: Path, frame: np.ndarray, cmd: np.ndarray) -> None:
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except Exception as exc:
        print('plot_skip=%s' % exc)
        return
    fig, axes = plt.subplots(1, 2, figsize=(8.5, 3.6))
    fig.patch.set_facecolor('#0b1015')
    for ax in axes:
        ax.set_facecolor('#0b1015')
        ax.tick_params(colors='#c5d0dc')
        for spine in ax.spines.values():
            spine.set_color('#2a3441')
    im = axes[0].imshow(frame, cmap='gray', origin='upper')
    axes[0].set_title('Synthetic WFS → SHM_WFS_FRAME', color='#e8eef7', fontsize=10)
    axes[0].set_xlabel('col', color='#8a9bb0')
    axes[0].set_ylabel('row', color='#8a9bb0')
    fig.colorbar(im, ax=axes[0], fraction=0.046)
    axes[1].plot(cmd, color='#7ec8e3', lw=1.0)
    axes[1].axhline(0, color='#2a3441', lw=0.8)
    axes[1].set_title('Synthetic DM cmd → SHM_DM1_CMD (140 act)',
                      color='#e8eef7', fontsize=10)
    axes[1].set_xlabel('actuator', color='#8a9bb0')
    axes[1].set_ylabel('cmd', color='#8a9bb0')
    axes[1].set_xlim(0, N_ACT - 1)
    fig.suptitle('DaoPrima SHM round-trip (synthetic Manta + BMC)',
                 color='#7ec8e3', fontsize=11)
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=120, facecolor=fig.get_facecolor())
    plt.close(fig)
    print('plot_saved=%s' % out_png)


def run_single(seed: int, plot, apply_dm: bool) -> dict:
    produced = produce(seed)
    print(json.dumps(produced, indent=2))
    consumed = consume(produced, apply_dm=apply_dm)
    print(json.dumps(consumed, indent=2))
    if plot:
        frame = shm_mod.shm(N.SHM_WFS_FRAME).get_data()
        cmd = shm_mod.shm(N.SHM_DM1_CMD).get_data().ravel()
        _save_plot(plot, frame, cmd)
    return {'produce': produced, 'consume': consumed,
            'pass': consumed['pass']}


def run_cross_process(seed: int, plot, apply_dm: bool) -> dict:
    """Writer subprocess then reader subprocess sharing /tmp SHM files."""
    meta_path = Path('/tmp/prima_shm_roundtrip_meta.json')
    py = sys.executable
    script = str(Path(__file__).resolve())
    env = os.environ.copy()
    env.pop('DAOPRIMA_SHM_INPROCESS', None)  # force file backend

    w = subprocess.run(
        [py, script, '--role', 'produce', '--seed', str(seed),
         '--meta-out', str(meta_path)],
        env=env, capture_output=True, text=True)
    print(w.stdout)
    if w.returncode != 0:
        print(w.stderr)
        return {'pass': False, 'error': 'produce_failed', 'stderr': w.stderr}

    time.sleep(0.05)
    r = subprocess.run(
        [py, script, '--role', 'consume', '--meta-in', str(meta_path)]
        + ([] if apply_dm else ['--no-apply-dm']),
        env=env, capture_output=True, text=True)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr)
        return {'pass': False, 'error': 'consume_failed', 'stderr': r.stderr}

    produced = json.loads(meta_path.read_text())
    # last JSON object in stdout is consume result — parse from file we write
    consume_path = Path('/tmp/prima_shm_roundtrip_consume.json')
    if not consume_path.exists():
        return {'pass': False, 'error': 'missing_consume_json'}
    consumed = json.loads(consume_path.read_text())
    if plot:
        # reopen in parent for plot
        shm_mod.reset_registry()
        frame = shm_mod.shm(N.SHM_WFS_FRAME).get_data()
        cmd = shm_mod.shm(N.SHM_DM1_CMD).get_data().ravel()
        _save_plot(plot, frame, cmd)
    return {'produce': produced, 'consume': consumed,
            'pass': bool(consumed.get('pass')), 'mode': 'cross-process'}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seed', type=int, default=7)
    p.add_argument('--cross-process', action='store_true')
    p.add_argument('--role', choices=('produce', 'consume', 'all'),
                   default='all')
    p.add_argument('--meta-out', type=Path, default=None)
    p.add_argument('--meta-in', type=Path, default=None)
    p.add_argument('--no-apply-dm', action='store_true')
    p.add_argument('--plot', type=Path, default=None,
                   help='Write summary PNG (frame + DM cmd)')
    p.add_argument('--log', type=Path, default=None,
                   help='Write JSON log snippet')
    args = p.parse_args(argv)

    apply_dm = not args.no_apply_dm

    if args.role == 'produce':
        meta = produce(args.seed)
        out = args.meta_out or Path('/tmp/prima_shm_roundtrip_meta.json')
        out.write_text(json.dumps(meta, indent=2))
        print(json.dumps(meta, indent=2))
        print('produce_ok checksum_frame=%s checksum_dm=%s' % (
            meta['frame_checksum'], meta['dm_checksum']))
        return 0

    if args.role == 'consume':
        meta_path = args.meta_in or Path('/tmp/prima_shm_roundtrip_meta.json')
        expected = json.loads(meta_path.read_text())
        result = consume(expected, apply_dm=apply_dm)
        Path('/tmp/prima_shm_roundtrip_consume.json').write_text(
            json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
        print('consume_%s frame_err=%.3e dm_err=%.3e' % (
            'PASS' if result['pass'] else 'FAIL',
            result['frame_max_abs_error'], result['dm_max_abs_error']))
        return 0 if result['pass'] else 1

    if args.cross_process:
        summary = run_cross_process(args.seed, args.plot, apply_dm)
    else:
        summary = run_single(args.seed, args.plot, apply_dm)

    if args.log:
        args.log.parent.mkdir(parents=True, exist_ok=True)
        args.log.write_text(json.dumps(summary, indent=2))
        print('log_saved=%s' % args.log)

    ok = bool(summary.get('pass'))
    print('ROUNDTRIP_%s backend=%s mode=%s' % (
        'PASS' if ok else 'FAIL',
        shm_mod.backend_name(),
        'cross-process' if args.cross_process else 'single-process'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
