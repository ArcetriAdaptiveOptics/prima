"""Camera frame rate vs decimation / ROI / exposure (light ok, no DM)."""
import json, time, sys
import numpy as np
from prima.aolab.devices.camera_aravis import AravisCamera

# pupil footprint at full resolution (2026-10-09): rows/cols min..max incl. radius
R0, R1, C0, C1 = 300, 1930, 230, 1840
res = []
cam = AravisCamera(exposure_ms=50)
for dec in [int(v) for v in (sys.argv[2] if len(sys.argv) > 2 else '1,2,4').split(',')]:
    cam.set_binning(dec)
    for roi in ('full', 'pupils'):
        if roi == 'pupils':
            m = 10
            cam.set_roi((C0 - m) // dec, (R0 - m) // dec, (C1 - C0 + 2 * m) // dec, (R1 - R0 + 2 * m) // dec)
        for exp in (20, 10, 5, 2):
            cam.set_exposure_ms(exp)
            cam.start(); time.sleep(0.6)
            e0 = cam.n_errors; time.sleep(2.5)
            fps = cam.get_fps(); err = cam.n_errors - e0
            _, f = cam.get_frame()
            cam.stop()
            r = dict(dec=dec, roi=roi, exp_ms=exp, fps=round(fps, 1), max_fps=round(cam.max_fps(), 1), set_fps=round(cam.get_set_fps(), 1),
                     errors=err, shape=list(f.shape), region=cam.get_roi())
            print(json.dumps(r), flush=True); res.append(r)
        if roi == 'pupils':
            cam.set_binning(dec)   # back to full frame
cam.close()
json.dump(res, open(sys.argv[1] if len(sys.argv) > 1 else '/tmp/cam_bench.json', 'w'), indent=1)
