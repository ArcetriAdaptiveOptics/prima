"""Fake IFF → process → flatten; residual must drop ≥10×."""
from __future__ import annotations

import numpy as np

from prima.flattening.devices.fake import FakeBmcDm, FakePyramid
from prima.flattening.pipeline import flatten_from_iff


def test_fake_pipeline_residual_drop():
    dm = FakeBmcDm(bias=0.5)
    # Static disturbance to remove
    dist = np.zeros(dm.n_acts)
    dist[10:20] = 0.08
    dist[50:60] = -0.06
    wfs = FakePyramid(dm, n_slopes=200, noise_rms=1e-5, disturbance=dist, seed=1)

    iff, r, result = flatten_from_iff(
        dm, wfs, amplitude=0.05, gain=1.0, svd_threshold=1e-4, n_iter=2)

    assert iff.im.shape[1] == dm.n_acts
    assert r.shape[0] == dm.n_acts
    assert result.rms_before > 0
    ratio = result.rms_before / max(result.rms_after, 1e-15)
    assert ratio >= 10.0, (
        'residual drop %.2f× < 10× (before=%.4g after=%.4g)'
        % (ratio, result.rms_before, result.rms_after))


if __name__ == '__main__':
    test_fake_pipeline_residual_drop()
    print('OK fake pipeline ≥10×')
