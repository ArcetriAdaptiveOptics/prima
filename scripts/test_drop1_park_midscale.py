#!/usr/bin/env python3
"""Verify E-518 mid-scale park + centered modulation (Drop1 binding)."""
from __future__ import annotations

import time

import numpy as np

from prima.hardware import connect_pi_modulator


def sample_vol(m, n=40):
    g = m._gcs
    A, B = [], []
    for _ in range(n):
        sock = g._ensure()
        sock.sendall(b'VOL?\n')
        raw = g._recv_until_idle(idle_s=0.015, max_s=0.08)
        vals = m._parse_vol(raw)
        if 1 in vals and 2 in vals:
            A.append(vals[1])
            B.append(vals[2])
    return np.array(A), np.array(B)


def gwd_period(m):
    n_pts = m._wave_n_pts
    raw = m._gcs.query('GWD? 1', wait_s=3.0)
    body = raw.split('# END_HEADER', 1)[-1]
    a, b = [], []
    for line in body.splitlines():
        parts = line.strip().split()
        if len(parts) < 2:
            continue
        try:
            a.append(float(parts[0]))
            b.append(float(parts[1]))
        except ValueError:
            continue
        if len(a) >= n_pts:
            break
    return np.asarray(a[:n_pts]), np.asarray(b[:n_pts])


def main():
    m = connect_pi_modulator()
    # connect() already parks
    time.sleep(0.3)
    A, B = sample_vol(m, 30)
    print('R=0 park VOL A=%.3f B=%.3f parked=%s' % (
        A.mean(), B.mean(), m._parked))
    assert abs(A.mean() - 50) < 1.5 and abs(B.mean() - 50) < 1.5, (
        A.mean(), B.mean())

    for r in (1.0, 40.0):
        m.setFrequencyInHz(20.0)
        m.setRadiusInMilliRad(r)
        time.sleep(0.4)
        a, b = gwd_period(m)
        mid_a = 0.5 * (a.min() + a.max())
        mid_b = 0.5 * (b.min() + b.max())
        print('R=%.0f GWD A mid=%.3f Vpp=%.3f | B mid=%.3f Vpp=%.3f' % (
            r, mid_a, np.ptp(a), mid_b, np.ptp(b)))
        assert abs(mid_a - 50) < 0.5 and abs(mid_b - 50) < 0.5

    m.setRadiusInMilliRad(0.0)
    time.sleep(0.3)
    A, B = sample_vol(m, 30)
    print('R=0 after VOL A=%.3f B=%.3f parked=%s' % (
        A.mean(), B.mean(), m._parked))
    assert abs(A.mean() - 50) < 1.5 and abs(B.mean() - 50) < 1.5
    m.close()
    print('ALL_OK')


if __name__ == '__main__':
    main()
