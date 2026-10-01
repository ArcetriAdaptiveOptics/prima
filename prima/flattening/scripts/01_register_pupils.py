#!/usr/bin/env python3
"""01 — register PWFS pupils at 4 mrad (live or fake)."""
from __future__ import annotations

import argparse
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from prima.drop1_defaults import (
    DEFAULT_EXPOSURE_MS, DEFAULT_MOD_FREQ_HZ, DEFAULT_MOD_RADIUS_MRAD)
from prima.flattening.scripts._common import (
    add_apply_flag, is_dry_run, media_path)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    add_apply_flag(p)
    p.add_argument('--fake', action='store_true')
    args = p.parse_args(argv)
    dry = is_dry_run(args)

    if args.fake or dry:
        # Synthetic 4 spots
        frame = np.zeros((512, 512), dtype=float)
        centers = np.array([[368, 144], [368, 368], [144, 144], [144, 368]], float)
        r = 56.0
        yy, xx = np.ogrid[:512, :512]
        for cy, cx in centers:
            frame[(yy - cy) ** 2 + (xx - cx) ** 2 <= r ** 2] = 2000
        mode = 'fake/dry'
    else:
        from prima.hardware.pi_e518_modulator import PiE518Modulator
        from prima.gui.aravis_camera import AravisLiveCamera
        from prima.metrology.engine import MetrologyEngine
        m = PiE518Modulator(connect=True)
        m.setFrequencyInHz(float(DEFAULT_MOD_FREQ_HZ))
        m.setRadiusInMilliRad(float(DEFAULT_MOD_RADIUS_MRAD))
        time.sleep(0.8)
        cam = AravisLiveCamera(ip_address='192.168.30.189')
        cam.setExposureTime(float(DEFAULT_EXPOSURE_MS))
        time.sleep(0.4)
        frame = np.mean(
            [np.asarray(cam.getFrame(), dtype=float) for _ in range(4)], 0)
        eng = MetrologyEngine(camera=cam, modulator=m)
        m.setFrequencyInHz(float(DEFAULT_MOD_FREQ_HZ))
        m.setRadiusInMilliRad(float(DEFAULT_MOD_RADIUS_MRAD))
        centers, r = eng.find_pupils_from_frame(frame)
        mode = 'live'
        # leave modulating — release without park
        try:
            m._gcs.close(); m._setup_done = False
        except Exception:
            pass
        cam.close()

    lo, hi = np.percentile(frame, [1, 99.5])
    vis = np.clip((frame - lo) / max(hi - lo, 1) * 255, 0, 255).astype(np.uint8)
    scale = 2 if vis.shape[0] > 800 else 1
    if scale > 1:
        vis = vis[::scale, ::scale]
    im = Image.fromarray(np.stack([vis] * 3, -1))
    draw = ImageDraw.Draw(im)
    for cy, cx in np.asarray(centers).reshape(-1, 2):
        x, y = float(cx) / scale, float(cy) / scale
        rr = float(r) / scale
        draw.ellipse([x - rr, y - rr, x + rr, y + rr],
                     outline=(255, 220, 60), width=2)
    out = media_path('flatten-vis-01-pupils.png')
    im.save(out)
    print('mode=%s centers=%s r=%.1f saved=%s' % (mode, centers, r, out))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
