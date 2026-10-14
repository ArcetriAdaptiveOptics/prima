#!/usr/bin/env python3
"""03 — amplitude linearity scan on one actuator (fake/dry by default)."""
from __future__ import annotations

import argparse

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from prima.flattening.devices.fake import FakeBmcDm, FakePyramid
from prima.flattening.scripts._common import (
    add_apply_flag, is_dry_run, media_path)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    add_apply_flag(p)
    p.add_argument('--act', type=int, default=70)
    p.add_argument('--amps', default='0.01,0.02,0.03,0.05')
    p.add_argument('--prefer', default='dao')
    p.add_argument('--settle', type=float, default=0.08)
    args = p.parse_args(argv)
    dry = is_dry_run(args)
    stack = None
    import time

    if dry:
        dm = FakeBmcDm()
        wfs = FakePyramid(dm, disturbance=np.zeros(dm.n_acts), noise_rms=1e-5)
        mode = 'fake'
    else:
        from prima.flattening.scripts._hw import open_live_stack
        stack = open_live_stack(prefer=args.prefer, park_dm=True)
        dm, wfs = stack.dm, stack.wfs
        mode = 'live/%s' % wfs.mode

    amps = [float(x) for x in args.amps.split(',')]
    # Differential response about flat (absolute slopes are large at 4 mrad).
    if hasattr(dm, 'park'):
        dm.park()
    if args.settle:
        time.sleep(args.settle)
    s0 = np.asarray(wfs.acquire_map(output_type='slopes1d'), dtype=float)
    xs, ys = [], []
    for a in amps:
        poke = np.zeros(dm.n_acts)
        poke[args.act] = a
        dm.set_shape(poke, differential=True)
        if args.settle:
            time.sleep(args.settle)
        s = np.asarray(wfs.acquire_map(output_type='slopes1d'), dtype=float)
        if hasattr(dm, 'park'):
            dm.set_shape(dm.bias(), differential=False, max_step=1.0)
        xs.append(a)
        ys.append(float(np.linalg.norm(s - s0)))
    xs, ys = np.asarray(xs), np.asarray(ys)

    w, h = 640, 360
    im = Image.new('RGB', (w, h), (20, 20, 20))
    draw = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype(
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 14)
    except Exception:
        font = ImageFont.load_default()
    draw.text((10, 8), 'Linearity act=%d |s| vs amp (%s)' % (args.act, mode),
              fill=(255, 220, 80), font=font)
    margin = 50
    for i in range(len(xs) - 1):
        x0 = margin + (w - 2 * margin) * (xs[i] - xs.min()) / max(np.ptp(xs), 1e-9)
        x1 = margin + (w - 2 * margin) * (xs[i + 1] - xs.min()) / max(np.ptp(xs), 1e-9)
        y0 = h - margin - (h - 2 * margin) * (ys[i] - ys.min()) / max(np.ptp(ys), 1e-9)
        y1 = h - margin - (h - 2 * margin) * (ys[i + 1] - ys.min()) / max(np.ptp(ys), 1e-9)
        draw.line([(x0, y0), (x1, y1)], fill=(100, 200, 255), width=2)
    for i, (a, s) in enumerate(zip(xs, ys)):
        draw.text((10, 30 + 16 * i),
                  'amp=%.3f  |s|=%.4g' % (a, s), fill=(180, 255, 180), font=font)
    out = media_path('flatten-vis-03-linearity.png')
    im.save(out)
    print('saved', out, 'mode', mode, 'amps', xs, 'norms', ys)
    if stack is not None:
        stack.close(park_dm=True, leave_modulating=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
