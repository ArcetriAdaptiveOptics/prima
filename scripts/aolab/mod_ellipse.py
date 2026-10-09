"""Shape of the modulation circle vs frequency: POS? A,B sampled together,
ellipse axes from the covariance (circle -> axis ratio 1)."""
import json, sys, time
import numpy as np
from prima.aolab.devices.pi_modulator import PiTipTiltModulator
m = PiTipTiltModulator()
out = []
for f in (20.0, 50.0, 100.0):
    m.set_modulation(10.0, f); time.sleep(0.5)
    pts = []
    for _ in range(80):
        p = m._parse(m.g.query('POS?', wait_s=0.12))
        pts.append([p.get('A', np.nan), p.get('B', np.nan)])
    P = np.array(pts); P = P[np.all(np.isfinite(P), 1)]
    C = np.cov((P - P.mean(0)).T); w, V = np.linalg.eigh(C)
    ax = 2 * np.sqrt(2 * w)       # p-p of a sinusoid = 2*sqrt(2)*std
    ang = np.degrees(np.arctan2(V[1, 1], V[0, 1]))
    o = dict(freq=f, n=len(P), ptp_major=round(ax[1], 2), ptp_minor=round(ax[0], 2),
             ratio=round(ax[0] / ax[1], 3), major_angle_deg=round(ang, 1),
             want_ptp=round(2 * 10 / 0.87, 2))
    print(json.dumps(o), flush=True); out.append(o)
    np.save('/tmp/ell_%d.npy' % f, P)
m.set_modulation(10.0, 20.0); m.close()
