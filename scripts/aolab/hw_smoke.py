"""Step-by-step hardware checks of the AO lab stack (headless).

    python scripts/aolab/hw_smoke.py cam          # camera binning / fps
    python scripts/aolab/hw_smoke.py dm           # stop old daemon, DM to flat, poke test
    python scripts/aolab/hw_smoke.py loop         # pupils, IM, closed loop tests

Figures/data go to ~/git/prima/work/data/<date>_<step>/.
"""
from __future__ import annotations

import json
import os
import signal
import sys
import time
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from prima.aolab import dm_geometry as G

STEP = sys.argv[1] if len(sys.argv) > 1 else 'cam'
OUT = Path.home() / 'git/prima/work/data' / (time.strftime('%Y%m%d_%H%M') + '_' + STEP)
OUT.mkdir(parents=True, exist_ok=True)
REPORT = {}


def save_report():
    (OUT / 'report.json').write_text(json.dumps(REPORT, indent=1, default=str))
    print(json.dumps(REPORT, indent=1, default=str))


def step_cam():
    from prima.aolab.devices.camera_aravis import AravisCamera
    cam = AravisCamera(exposure_ms=float(os.environ.get('EXP', '20')))
    for b in (1, 2, 4):
        cam.set_binning(b)
        cam.start()
        time.sleep(2.5)
        fps = cam.get_fps()
        fid, f = cam.get_frame()
        REPORT['bin%d' % b] = {'shape': f.shape, 'fps': round(fps, 2),
                               'max_fps': cam.max_fps(), 'errors': cam.n_errors,
                               'max': float(f.max()), 'roi': cam.get_roi()}
        np.save(OUT / ('frame_bin%d.npy' % b), f)
        cam.stop()
    cam.close()
    save_report()


def stop_daemon():
    from prima.aolab.devices.hw import dm_owner_pids
    pids = dm_owner_pids()
    for p in pids:
        print('stopping daodm_bmc_ctrl pid', p)
        os.kill(p, signal.SIGTERM)
    t0 = time.time()
    while dm_owner_pids() and time.time() - t0 < 10:
        time.sleep(0.3)
    if dm_owner_pids():
        raise RuntimeError('daemon still alive')
    REPORT['daemon_stopped'] = pids
    time.sleep(1.0)


def step_dm():
    from prima.aolab.devices.camera_aravis import AravisCamera
    from prima.aolab.devices.hw import BmcUsbDM, load_flat, FACTORY_FLAT
    stop_daemon()
    flat = load_flat(FACTORY_FLAT)
    dm = BmcUsbDM(flat)
    cam = AravisCamera(exposure_ms=50.0)
    cam.set_binning(2)
    cam.start()
    time.sleep(1.5)
    def avg(n=4):
        cam.get_frame(); cam.get_frame()
        return np.mean([cam.get_frame()[1] for _ in range(n)], axis=0)
    ref = avg()
    acts = [int(a) for a in os.environ.get('ACTS', '64,69,75').split(',')]
    amp = float(os.environ.get('AMP', '0.03'))
    diffs = {}
    for a in acts:
        out = []
        for s in (+1, -1):
            c = flat.copy(); c[a] += s * amp
            dm.send(c)
            out.append(avg())
        dm.send(flat)
        diffs[a] = out[0] - out[1]
        REPORT['poke_%d' % a] = {'rms_diff': float(diffs[a].std()),
                                 'max_abs': float(np.abs(diffs[a]).max())}
    # a low-order mode
    act = G.pupil_actuators()
    B = G.make_basis('zernike', act, 5)
    out = []
    for s in (+1, -1):
        dm.send(flat + s * 0.02 * B[:, 2])     # focus
        out.append(avg())
    dm.send(flat)
    diffs['focus'] = out[0] - out[1]
    REPORT['focus_rms_diff'] = float(diffs['focus'].std())
    fig, ax = plt.subplots(1, len(diffs) + 1, figsize=(4 * (len(diffs) + 1), 4))
    ax[0].imshow(ref, origin='lower', cmap='inferno'); ax[0].set_title('flat')
    for a_, (k, d) in zip(ax[1:], diffs.items()):
        lim = np.percentile(np.abs(d), 99.5)
        a_.imshow(d, origin='lower', cmap='RdBu_r', vmin=-lim, vmax=lim)
        a_.set_title('push-pull %s' % k)
    fig.tight_layout(); fig.savefig(OUT / 'dm_pokes.png', dpi=70)
    cam.close()
    dm.close()   # HV off
    REPORT['note'] = 'DM HV disabled at the end (driver close)'
    save_report()


def step_loop():
    from prima.aolab.devices.hw import make_hw_bench
    from prima.aolab.engine import AOEngine
    from prima.aolab.calibration import make_reconstructor
    stop_daemon() if __import__('prima.aolab.devices.hw', fromlist=['x']).dm_owner_pids() else None
    exp = float(os.environ.get('EXP', '50'))
    rmod = float(os.environ.get('RMOD', '10'))
    cam, dm, mod, flat = make_hw_bench(exposure_ms=exp, binning=2, radius_mrad=rmod)
    e = AOEngine(cam, dm, mod, flat)
    try:
        e.start()
        time.sleep(2)
        g = e.detect_pupils()
        REPORT['pupils'] = g.to_dict()
        I = e.wait_measure()['I'].sum(axis=1)
        REPORT['flux_ratio'] = (I / I.mean()).round(3).tolist()
        e.set_reference(20)
        REPORT['rate_hz'] = e.loop_rate_hz()
        # linearity of KL mode 1 and 5
        act = G.pupil_actuators()
        B = G.make_basis('kl', act, 10)
        amps = np.array([-0.03, -0.02, -0.01, -0.005, 0, 0.005, 0.01, 0.02, 0.03])
        lin = {}
        for k in (0, 4):
            resp = []
            for a in amps:
                e.set_channel('user', a * B[:, k])
                e.wait_measure(skip=2)
                s = np.mean([e.wait_measure()['slopes'] for _ in range(3)], axis=0)
                resp.append(s)
            e.set_channel('user', None)
            resp = np.array(resp)
            d = resp[-1] - resp[0]
            lin[k] = resp @ d / (d @ d) * (amps[-1] - amps[0])
        REPORT['linearity'] = {str(k): v.round(4).tolist() for k, v in lin.items()}
        plt.figure(figsize=(5, 4))
        for k, v in lin.items():
            plt.plot(amps * e.nm_per_unit, v * e.nm_per_unit, 'o-', label='KL %d' % (k + 1))
        plt.plot(amps * e.nm_per_unit, amps * e.nm_per_unit, 'k:', label='ideal')
        plt.xlabel('applied [nm nominal]'); plt.ylabel('measured (proj.) [nm]'); plt.legend(); plt.grid(alpha=.3)
        plt.tight_layout(); plt.savefig(OUT / 'linearity.png', dpi=80)
        # IM
        e.cp.basis = os.environ.get('BASIS', 'kl')
        e.cp.n_modes = int(os.environ.get('NMODES', '60'))
        e.cp.amplitude = float(os.environ.get('AMP', '0.006'))
        e.cp.n_avg = 2; e.cp.settle = 2
        e.lp.n_modes = e.cp.n_modes
        e.start_calibration()
        while e.calibrating:
            time.sleep(1)
        if e.rec is None:
            raise RuntimeError('IM failed')
        REPORT['im'] = {'sv': e.rec.singular_values.round(2).tolist(),
                        'sens': e.imat.sensitivity().round(2).tolist(),
                        'duration_s': e.imat.meta.get('duration_s')}
        cal = e.save('hw_smoke')
        REPORT['calib_dir'] = str(cal)
        # closed loop on static + turbulence
        def run(label, secs):
            t0 = time.time()
            while time.time() - t0 < secs:
                time.sleep(0.2)
            r = e.tel.series('mode_rms', 40)
            REPORT.setdefault('phases', {})[label] = float(np.nanmean(r) * e.nm_per_unit)
        e.lp.gain = float(os.environ.get('GAIN', '0.3'))
        run('open_flat', 4)
        e.close_loop(); run('closed_flat', 6)
        e.open_loop(); e.set_static({4: 0.01, 6: 0.008}); run('open_static', 4)
        e.close_loop(); run('closed_static', 6)
        e.open_loop(reset=True); e.set_static({4: 0, 6: 0})
        e.set_turbulence(True, rms=0.008, wind=0.3); run('open_turb', 6)
        e.close_loop(); run('closed_turb', 10)
        e.open_loop(reset=True); e.set_turbulence(False)
        tel = e.tel.dump()
        np.savez_compressed(OUT / 'telemetry.npz', **tel)
        k = e.nm_per_unit
        fig, ax = plt.subplots(2, 1, figsize=(9, 6))
        ax[0].plot(tel['mode_rms'] * k, label='reconstructed WF')
        ax[0].plot(tel['dist_rms'] * k, label='DM disturbance')
        ax[0].plot(tel['loop_cmd_rms'] * k, label='loop command')
        ax[0].fill_between(np.arange(tel['t'].size), 0, np.nan_to_num(tel['loop_closed']) * 20,
                           color='g', alpha=.3, label='closed')
        ax[0].set_ylabel('nm rms (nominal)'); ax[0].legend(); ax[0].grid(alpha=.3)
        ax[1].semilogy(e.rec.singular_values, 'o', ms=3, label='singular values')
        ax[1].semilogy(e.imat.sensitivity(), label='sensitivity'); ax[1].legend(); ax[1].grid(alpha=.3)
        fig.tight_layout(); fig.savefig(OUT / 'loop.png', dpi=80)
        REPORT['nm_per_unit'] = e.nm_per_unit
    finally:
        e.stop(park=True)
        mod.close(keep_modulating=True)
        dm.close()
        cam.close()
        save_report()


{'cam': step_cam, 'dm': step_dm, 'loop': step_loop}[STEP]()
