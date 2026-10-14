"""Modulator: requested vs obtained circle (POS? sampling) vs frequency."""
import json, time, sys
import numpy as np
from prima.aolab.devices.pi_modulator import PiTipTiltModulator
m = PiTipTiltModulator()
out = []
for f in [float(v) for v in (sys.argv[2] if len(sys.argv) > 2 else "20,50,100,200").split(",")]:
    for r in (10.0,):
        m.set_modulation(r, f); time.sleep(0.5)
        rb = m.readback(40, dt=0.0)
        want = 2 * r / 0.87
        o = dict(freq=f, r=r, r_cmd=round(m.commanded_radius(), 2), n_pts=m.n_pts, want_ptp=round(want, 2), got_ptp=rb['pos_gcs_ptp'],
                 mid=rb['pos_gcs_mid'], vol_min=rb['vol_min'], vol_max=rb['vol_max'])
        print(json.dumps(o), flush=True); out.append(o)
m.set_modulation(10.0, 20.0)
m.close()
json.dump(out, open(sys.argv[1] if len(sys.argv) > 1 else '/tmp/mod_bench.json', 'w'), indent=1)
