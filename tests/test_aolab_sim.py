"""End-to-end tests of the AO lab stack on the numerical bench twin.

    python -m pytest -q tests/test_aolab_sim.py
"""
import time

import numpy as np
import pytest

from prima.aolab import dm_geometry as G
from prima.aolab.calibration import InteractionMatrix, make_reconstructor
from prima.aolab.devices.hw import FACTORY_FLAT, load_flat
from prima.aolab.devices.sim import make_sim_bench
from prima.aolab.engine import AOEngine


def test_bases_orthonormal():
    act = G.pupil_actuators()
    assert act.sum() == 96
    for kind in ('kl', 'zernike'):
        B = G.make_basis(kind, act, 50)
        Ba = B[act]
        gram = Ba.T @ Ba / act.sum()
        assert np.allclose(gram, np.eye(50), atol=1e-8)
        assert np.allclose(B[~act], 0)


def test_reconstructor_inverts_im():
    rng = np.random.default_rng(0)
    im = rng.normal(size=(400, 30))
    imat = InteractionMatrix(im, np.zeros((140, 30)), 0.01, 'kl')
    rec = make_reconstructor(imat)
    assert np.allclose(rec.rec @ im, np.eye(30), atol=1e-8)


@pytest.fixture(scope='module')
def engine():
    flat = load_flat(FACTORY_FLAT)
    cam, dm, mod, model = make_sim_bench(flat=flat, fps=1000)
    e = AOEngine(cam, dm, mod, flat, log=lambda m: None)
    e.model = model
    e.start()
    yield e
    e.stop()


def _wf(e):
    w = e.model.wavefront_nm()
    return w[e.model.pmask].std()


def test_calibrate_and_close(engine):
    e = engine
    e.detect_pupils()
    e.set_reference(zero=True)
    e.cp.n_modes = 50
    e.cp.amplitude = 0.005
    e.cp.n_avg = 1
    e.cp.settle = 1
    e.lp.n_modes = 50
    e.start_calibration()
    while e.calibrating:
        time.sleep(0.2)
    assert e.rec is not None and e.rec.n_modes == 50
    e.set_turbulence(True, rms=0.01, wind=0.3, seed=3)
    time.sleep(1.5)
    open_rms = np.mean([(_wf(e), time.sleep(0.05))[0] for _ in range(10)])
    e.lp.gain = 0.4
    e.close_loop()
    time.sleep(3)
    closed_rms = np.mean([(_wf(e), time.sleep(0.05))[0] for _ in range(10)])
    e.open_loop(reset=True)
    e.set_turbulence(False)
    assert closed_rms < 0.35 * open_rms, (open_rms, closed_rms)


def test_dm_safety_clip(engine):
    e = engine
    e.set_channel('user', np.full(140, 5.0))
    cmd = e.total_command()
    assert np.all(cmd <= 1.0)
    assert np.all(np.abs(cmd - np.clip(e.flat, 0, 1)) <= e.lp.max_delta + 1e-9)
    e.set_channel('user', None)


def test_record_telemetry(engine, tmp_path, monkeypatch):
    import json
    from astropy.io import fits
    from prima.aolab import engine as engine_mod
    monkeypatch.setattr(engine_mod, 'REC_DIR', tmp_path)
    e = engine
    assert e.rec is not None             # calibrated by the test above
    e.set_turbulence(True, rms=0.01, wind=0.3, seed=1)
    e.close_loop()
    done = []
    d = e.start_recording(40, label='test run_1', n_cam_frames=3,
                          done_cb=done.append)
    assert d.name.count('_') == 1 and d.name.endswith('-test-run-1')
    t0 = time.time()
    while not done and time.time() - t0 < 20:
        time.sleep(0.05)
    e.open_loop(reset=True)
    e.set_turbulence(False)
    assert done and done[0] == d and not e.recording
    meta = json.loads((d / 'meta.json').read_text())
    assert meta['n_frames'] == 40 and meta['kind'] == 'telemetry'
    assert meta['turbulence']['on'] and meta['loop_closed']
    n_modes, n_slopes = meta['n_modes'], meta['n_slopes']
    assert fits.getdata(d / 'slopes.fits').shape == (40, n_slopes)
    m = fits.getdata(d / 'modes.fits')
    c = fits.getdata(d / 'int_modes.fits')
    assert m.shape == c.shape == (40, n_modes) and np.all(np.isfinite(m))
    assert fits.getdata(d / 'dm_cmd.fits').shape == (40, 140)
    assert fits.getdata(d / 'frames.fits').shape[0] == 3
    sc = fits.getdata(d / 'scalars.fits')
    assert np.all(np.diff(sc['frame']) >= 1)
    # integrator law on the recorded data: c_k = leak c_{k-1} - g m_k
    lp = e.lp
    assert np.allclose(c[1:], lp.leak * c[:-1] - lp.gain * m[1:], atol=1e-5)
    with fits.open(d / 'calib.fits') as h:
        assert h[0].data.shape == (n_slopes, n_modes)      # IM
        assert h['REC'].data.shape == (n_modes, n_slopes)
    # offline analysis of the same recording
    import matplotlib
    matplotlib.use('Agg')
    from prima.aolab.analysis import PrimaAnalyzer, list_tags
    assert list_tags(root=tmp_path) == [d.name]
    an = PrimaAnalyzer(d)
    assert an.loop.closed and an.loop.gain == lp.gain
    r = an.loop.residual_modes
    assert r.get_data().shape == (40, n_modes) and r.data_unit() == 'nm'
    assert r.power().shape[1] == n_modes
    assert np.allclose(r.get_data().value,
                       m * meta['nm_per_unit'], rtol=1e-6)
    pol = an.loop.pseudo_open_loop_modes.get_data().value
    assert pol.shape == (40 - an.delay_frames, n_modes)
    assert an.calib.im.shape == (n_slopes, n_modes)
    sx, sy = an.wfs.slopes.to_maps(an.wfs.slopes.get_data()[0])
    assert sx.shape == an.wfs.slopes.valid2d.shape
    an.modalplot()
