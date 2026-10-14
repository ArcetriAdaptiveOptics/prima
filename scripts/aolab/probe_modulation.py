"""Probe: modulation radius vs pupil illumination.  Leaves 10 mrad / 20 Hz."""
import sys, time, json
from pathlib import Path
import numpy as np
from prima.aolab.devices.camera_aravis import AravisCamera
from prima.hardware.pi_e518_modulator import PiE518Modulator

out = Path.home() / 'git/prima/work/data'; out.mkdir(parents=True, exist_ok=True)
radii = [float(r) for r in (sys.argv[1:] or ['0', '5', '10', '20'])]
cam = AravisCamera(exposure_ms=50.0)
cam.start()
mod = PiE518Modulator()
print('E-518 connected', mod.getStatus() if hasattr(mod, 'getStatus') else '')
mod.setFrequencyInHz(20.0)
frames = {}
for r in radii:
    mod.setRadiusInMilliRad(r)
    time.sleep(0.5)
    for _ in range(2):
        cam.get_frame()
    imgs = [cam.get_frame()[1].copy() for _ in range(3)]
    frames[r] = np.mean(imgs, axis=0)
    f = frames[r]
    print('R=%5.1f mrad: max %.0f mean %.1f p99.9 %.0f fps %.1f err %d' % (
        r, f.max(), f.mean(), np.percentile(f, 99.9), cam.get_fps(), cam.n_errors))
mod.setRadiusInMilliRad(10.0)
print('readback', mod.getControllerReadback())
cam.close()
mod._gcs.close()   # leave wavegen running at 10 mrad
np.savez_compressed(out / 'probe_modulation.npz', **{'r%g' % k: v.astype(np.float32) for k, v in frames.items()})
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
fig, ax = plt.subplots(1, len(frames), figsize=(4 * len(frames), 4))
for a, (r, f) in zip(np.atleast_1d(ax), frames.items()):
    a.imshow(f[::4, ::4], origin='lower', cmap='inferno', vmax=np.percentile(f, 99.9))
    a.set_title('R = %g mrad' % r)
fig.tight_layout(); fig.savefig(out / 'probe_modulation.png', dpi=70)
