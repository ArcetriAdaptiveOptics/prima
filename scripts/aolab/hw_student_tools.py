"""Bench test of the student tools (lab.py + recorder + PrimaAnalyzer).

Same path as notebook 03 on the real bench (41 Hz configuration):
calibrate, open-loop recording with DM turbulence, delay D from the known
disturbance, closed-loop recordings at a few gains, measured RTF vs model.

    python scripts/aolab/hw_student_tools.py [--out work/figs] [--n 2048] [--sim]

The devices are always released at the end (DM flat + HV off); the
modulator keeps modulating, as with the GUI.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy import signal

from prima.aolab import lab


def rtf(f, g, leak=1.0, D=1):
    z = np.exp(2j * np.pi * f)
    return np.abs(1 / (1 + g * z ** -D / (1 - leak / z))) ** 2


def mismatch(m, d, D):
    a = m[D:] - m[D:].mean(0)
    b = d[:len(d) - D] - d[:len(d) - D].mean(0)
    return np.sqrt(((a - b) ** 2).sum(1).mean())


def psd(x, nperseg=256):
    fr, p = signal.welch(x - x.mean(0), fs=1.0, nperseg=nperseg, axis=0)
    return fr, p.mean(axis=1)


def tot_rms(x):
    return float(np.sqrt((x.std(0) ** 2).sum()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='work/figs')
    ap.add_argument('--n', type=int, default=2048)
    ap.add_argument('--n-modes', type=int, default=50)
    ap.add_argument('--rms', type=float, default=0.01)
    ap.add_argument('--wind', type=float, default=0.5)
    ap.add_argument('--gains', default='0.2,0.5,1.0')
    ap.add_argument('--sim', action='store_true',
                    help='dry run on the numerical twin (bench light)')
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    gains = [float(g) for g in a.gains.split(',')]
    res = {}

    if a.sim:
        e = lab.sim_engine(fps=41, calibrated=False, flux=2e4)
    else:
        e = lab.hw_engine()
    try:
        lab.settle(e, 30)
        t0 = time.time()
        lab.calibrate(e, n_modes=a.n_modes, amplitude=0.01, n_avg=2,
                      settle=2)
        res['calib_s'] = time.time() - t0
        res['loop_rate_hz'] = e.loop_rate_hz()
        print('calibrated in %.0f s, loop %.1f Hz'
              % (res['calib_s'], res['loop_rate_hz']), flush=True)

        # noise only, open loop
        e.set_turbulence(False)
        e.open_loop(reset=True)
        lab.settle(e, 30)
        nz = lab.record(e, a.n // 2, 'hwtest-noise')
        res['noise_nm'] = tot_rms(nz.loop.residual_modes.get_data().value)
        print('noise %.1f nm  [%s]' % (res['noise_nm'], nz.snapshot_tag()),
              flush=True)

        # open loop with turbulence -> D
        e.set_turbulence(True, rms=a.rms, wind=a.wind, seed=1)
        lab.settle(e, 50)
        ol = lab.record(e, a.n, 'hwtest-ol')
        m = ol.loop.residual_modes.get_data().value
        d = ol.loop.disturbance_modes.get_data().value
        mis = {D: mismatch(m, d, D) for D in range(6)}
        D = min(mis, key=mis.get)
        res.update(tag_ol=ol.snapshot_tag(), mismatch=mis, D=D,
                   dist_nm=tot_rms(d), ol_meas_nm=tot_rms(m),
                   dropped=ol.meta.get('dropped_frames'),
                   meta_rate=ol.meta.get('loop_rate_hz'))
        print('D = %d  mismatch %s' % (D, {k: round(v, 1)
                                           for k, v in mis.items()}),
              flush=True)

        fig, ax = plt.subplots(figsize=(9, 4))
        n_show = min(300, len(m))
        ax.plot(ol.time[:n_show], m[:n_show, 0] - m[:, 0].mean(),
                label='misurato m (modo 0)')
        ax.plot(ol.time[:n_show], d[:n_show, 0] - d[:, 0].mean(), '--',
                label='disturbo d (modo 0)')
        ax.set_xlabel('t [s]'); ax.set_ylabel('nm'); ax.legend()
        ax.set_title('Banco, anello aperto: D = %d frame' % D)
        fig.tight_layout(); fig.savefig(out / 'hw_ol_delay.png', dpi=110)

        # closed loop
        runs = {}
        for g in gains:
            e.lp.gain, e.lp.leak = g, 1.0
            e.reset_loop()
            e.close_loop()
            lab.settle(e, 150)
            if not e.loop_closed:
                print('g=%.1f: loop opened by watchdog' % g, flush=True)
                e.open_loop(reset=True)
                continue
            an = lab.record(e, a.n, 'hwtest-g%.1f' % g)
            e.open_loop(reset=True)
            runs[g] = an
            r = an.loop.residual_modes.get_data().value
            c = an.loop.integrated_modes.get_data().value
            dd = an.loop.disturbance_modes.get_data().value
            res['g%.1f' % g] = dict(tag=an.snapshot_tag(),
                                    meas_nm=tot_rms(r),
                                    true_nm=tot_rms(c + dd),
                                    dropped=an.meta.get('dropped_frames'),
                                    rate=an.meta.get('loop_rate_hz'))
            print('g=%.1f %s' % (g, res['g%.1f' % g]), flush=True)
            lab.settle(e, 30)

        if runs:
            fig, axs = plt.subplots(1, len(runs), figsize=(5 * len(runs), 4),
                                    sharey=True, squeeze=False)
            for ax, (g, an) in zip(axs[0], runs.items()):
                fr, p_res = psd(an.loop.residual_modes.get_data().value)
                _, p_pol = psd(an.pseudo_open_loop(D))
                fs = an.meta.get('loop_rate_hz') or res['loop_rate_hz']
                ax.loglog(fr[1:] * fs, (p_res / p_pol)[1:], '.',
                          label='misurata')
                for DD in sorted({D, max(D - 1, 1), D + 1}):
                    ax.loglog(fr[1:] * fs, rtf(fr[1:], g, D=DD),
                              lw=2 if DD == D else 0.8,
                              label='modello D=%d' % DD)
                ax.axhline(1, color='gray', lw=0.8)
                ax.set_title('banco, g = %.1f' % g); ax.set_xlabel('f [Hz]')
            axs[0, 0].set_ylabel('|H_rej|²'); axs[0, 0].legend()
            fig.tight_layout(); fig.savefig(out / 'hw_rtf.png', dpi=110)
    finally:
        try:
            e.set_turbulence(False)
        except Exception:
            pass
        lab.close(e)
        print(json.dumps(res, indent=1, default=str), flush=True)


if __name__ == '__main__':
    main()
