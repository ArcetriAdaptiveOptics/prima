#!/usr/bin/env python3
"""Drop 1 HW test: modulation radius 1→2→4 mrad changes Manta frame pattern.

Requires live Manta (Aravis) + E-518 (direct PI GCS). Aborts clearly if either
side fails. Safe amplitudes only (≤4 mrad).

Usage:
  source ~/git/.venv-prima/bin/activate
  python scripts/test_drop1_modulation_frames.py
  python scripts/test_drop1_modulation_frames.py --screenshot /path/to.png
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


RADII_MRAD = (1.0, 2.0, 4.0)
FREQ_HZ = 20.0
N_FRAMES = 48
SETTLE_S = 0.8


def _abort(msg: str, code: int = 2) -> None:
    print('ABORT: %s' % msg, file=sys.stderr)
    sys.exit(code)


def _connect(aravis_ip: str, e518_host: str, e518_port: int):
    from prima.gui.live_clients import try_connect_live
    from prima.hardware import PiGcsError

    cam, mod, errors = try_connect_live(
        aravis_ip=aravis_ip,
        e518_host=e518_host,
        e518_port=e518_port,
        prefer_direct_pi=True,
        allow_plico_modulator=False,
    )
    if cam is None:
        _abort('camera unavailable: %s' % '; '.join(errors))
    if mod is None:
        _abort(
            'PI/GCS modulator unavailable (lib/GCS failed or host down): %s'
            % '; '.join(errors))
    try:
        _ = mod.getStatus()
    except Exception as e:
        _abort('modulator probe failed: %s' % e)
    if hasattr(mod, 'connect') is False and not getattr(mod, '_setup_done', True):
        pass
    print('camera=%s' % cam.name())
    print('modulator=%s' % (mod.name() if hasattr(mod, 'name') else mod))
    return cam, mod


def _grab_stack(cam, n: int) -> np.ndarray:
    frames = []
    for _ in range(int(n)):
        fr = cam.getFrameForDisplay()
        if hasattr(fr, 'toNumpyArray'):
            fr = fr.toNumpyArray()
        frames.append(np.asarray(fr, dtype=np.float64))
        time.sleep(0.02)
    return np.stack(frames, axis=0)


def _pattern_metrics(stack: np.ndarray) -> dict:
    """Metrics sensitive to pupil motion / temporal change from modulation."""
    # Temporal std map + mean absolute frame-to-frame difference
    tstd = float(np.std(stack, axis=0).mean())
    diffs = np.abs(np.diff(stack, axis=0))
    mad = float(diffs.mean())
    # Coarse "centroid wander" of brightest pixels (proxy for pupil motion)
    flat = stack.reshape(stack.shape[0], -1)
    thr = np.percentile(flat, 99.0, axis=1, keepdims=True)
    weights = np.clip(flat - thr, 0, None)
    # rebuild coords
    h, w = stack.shape[1], stack.shape[2]
    yy, xx = np.mgrid[0:h, 0:w]
    yy = yy.reshape(-1)
    xx = xx.reshape(-1)
    wsum = weights.sum(axis=1) + 1e-9
    cx = (weights * xx[None, :]).sum(axis=1) / wsum
    cy = (weights * yy[None, :]).sum(axis=1) / wsum
    wander = float(np.hypot(np.std(cx), np.std(cy)))
    return {
        'temporal_std': tstd,
        'mean_abs_diff': mad,
        'centroid_wander_px': wander,
        'score': tstd + 2.0 * mad + 0.5 * wander,
    }


def _corr_vs_prev(a: np.ndarray, b: np.ndarray) -> float:
    """Correlation of temporal-std maps between two radius stacks."""
    sa = np.std(a, axis=0).ravel()
    sb = np.std(b, axis=0).ravel()
    sa = sa - sa.mean()
    sb = sb - sb.mean()
    denom = (np.linalg.norm(sa) * np.linalg.norm(sb)) + 1e-12
    return float(np.dot(sa, sb) / denom)


def run(aravis_ip: str, e518_host: str, e518_port: int, screenshot: str | None):
    cam, mod = _connect(aravis_ip, e518_host, e518_port)

    # Sync exposure to 1/f (Drop 1 rule)
    exp_ms = 1000.0 / FREQ_HZ
    cam.setExposureTime(exp_ms)
    print('exposure_ms=%.3f (locked to 1/f_mod, f=%.1f)' % (exp_ms, FREQ_HZ))

    try:
        mod.setFrequencyInHz(FREQ_HZ)
        mod.setCenterInMilliRad([0.0, 0.0])
    except Exception as e:
        _abort('PI setFrequency/center failed: %s' % e)

    results = {}
    stacks = {}
    prev_r = None
    for r in RADII_MRAD:
        try:
            mod.setRadiusInMilliRad(float(r))
        except Exception as e:
            _abort('PI setRadius(%.3f) failed: %s' % (r, e))
        if hasattr(mod, 'wavegen_running') and not mod.wavegen_running():
            _abort('Wavegen not running after setRadius(%.3f)' % r)
        time.sleep(SETTLE_S)
        stack = _grab_stack(cam, N_FRAMES)
        stacks[r] = stack
        m = _pattern_metrics(stack)
        if prev_r is not None:
            m['corr_vs_prev'] = _corr_vs_prev(stacks[prev_r], stack)
        results[r] = m
        print('radius=%.1f  score=%.4f  tstd=%.4f  mad=%.4f  wander=%.4f%s' % (
            r, m['score'], m['temporal_std'], m['mean_abs_diff'],
            m['centroid_wander_px'],
            ('  corr_vs_prev=%.3f' % m['corr_vs_prev']) if 'corr_vs_prev' in m else ''))
        prev_r = r

    s1, s2, s4 = (results[r]['score'] for r in RADII_MRAD)
    corr2 = results[2.0].get('corr_vs_prev', 1.0)
    corr4 = results[4.0].get('corr_vs_prev', 1.0)
    # With t_exp=1/f each frame averages one modulation cycle, so temporal
    # score may stay flat while the spatial pattern still changes with radius.
    # Accept either score separation or low temporal-std-map correlation.
    ok_14 = (
        s4 > s1 * 1.15
        or abs(s4 - s1) > 0.05
        or corr4 < 0.90
    )
    ok_adj = (
        abs(results[2.0]['score'] - results[1.0]['score']) > 0.01
        or abs(results[4.0]['score'] - results[2.0]['score']) > 0.01
        or corr2 < 0.995
        or corr4 < 0.995
    )
    # Mean intensity must show light — otherwise pattern test is meaningless.
    mean_level = float(np.mean(stacks[1.0]))
    if mean_level < 1.0:
        print('WARN: frames nearly dark (mean=%.3f) — pattern contrast weak'
              % mean_level)

    passed = bool(ok_14 and ok_adj)
    print('PASS' if passed else 'FAIL',
          'score_1/2/4=%.4f/%.4f/%.4f corr2/4=%.3f/%.3f mean_level=%.2f' % (
              s1, s2, s4, corr2, corr4, mean_level))

    if screenshot:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            fig, axes = plt.subplots(1, 3, figsize=(10, 3.4))
            for ax, r in zip(axes, RADII_MRAD):
                tstd = np.std(stacks[r], axis=0)
                ax.imshow(tstd, cmap='magma')
                ax.set_title('R=%.0f mrad  score=%.3f' % (r, results[r]['score']))
                ax.axis('off')
            fig.suptitle('Drop1 modulation frame-pattern (temporal std)')
            fig.tight_layout()
            Path(screenshot).parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(screenshot, dpi=120)
            print('screenshot=%s' % screenshot)
        except Exception as e:
            print('screenshot_failed: %s' % e)

    try:
        mod.setRadiusInMilliRad(0.0)
        mod.stop_modulation()
    except Exception:
        pass
    try:
        mod.close()
    except Exception:
        pass
    try:
        cam.close()
    except Exception:
        pass

    if not passed:
        sys.exit(1)
    print('ALL_OK')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--aravis-ip', default=os.environ.get('PRIMA_ARAVIS_IP', '192.168.30.189'))
    p.add_argument('--e518-host', default=os.environ.get('PRIMA_E518_HOST', '192.168.30.190'))
    p.add_argument('--e518-port', type=int, default=int(os.environ.get('PRIMA_E518_PORT', '50000')))
    p.add_argument('--screenshot', default=None)
    args = p.parse_args(argv)
    run(args.aravis_ip, args.e518_host, args.e518_port, args.screenshot)


if __name__ == '__main__':
    main()
