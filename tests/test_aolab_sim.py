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
