#!/usr/bin/env python3
"""02 — low-amp poke visibility (dry-run default; --apply for tiny poke)."""
from __future__ import annotations

import argparse

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from prima.flattening.devices.bmc_dm import BmcMultiDm
from prima.flattening.devices.fake import FakeBmcDm, FakePyramid
from prima.flattening.scripts._common import (
    add_apply_flag, is_dry_run, media_path)
from prima.gui.dm_panel import _actuator_to_grid


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    add_apply_flag(p)
    p.add_argument('--amp', type=float, default=0.03)
    p.add_argument('--act', type=int, default=70)
    p.add_argument('--fake', action='store_true')
    args = p.parse_args(argv)
    dry = is_dry_run(args)

    if args.fake or dry:
        dm = FakeBmcDm()
        wfs = FakePyramid(dm, disturbance=np.zeros(dm.n_acts))
        mode = 'fake/dry'
    else:
        dm = BmcMultiDm(prefer='usb', dry_run=False)
        wfs = None
        mode = 'apply'

    poke = np.zeros(dm.n_acts)
    poke[int(args.act)] = float(args.amp)
    s0 = None
    if wfs is not None:
        s0 = np.asarray(wfs.acquire_map(), dtype=float)
    dm.set_shape(poke, differential=True)
    s1 = np.asarray(wfs.acquire_map(), dtype=float) if wfs is not None else None
    dm.park() if hasattr(dm, 'park') else dm.set_shape(dm.bias(), differential=False)

    grid = _actuator_to_grid(poke)
    g = np.nan_to_num(grid, nan=0.0)
    vis = np.clip((g - g.min()) / max(np.ptp(g), 1e-9) * 255, 0, 255).astype(np.uint8)
    vis = np.kron(vis, np.ones((20, 20), dtype=np.uint8))
    im = Image.fromarray(vis).convert('RGB')
    draw = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype(
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 14)
    except Exception:
        font = ImageFont.load_default()
    ds = 0.0 if s0 is None else float(np.sqrt(np.mean((s1 - s0) ** 2)))
    draw.text((6, 6), 'poke act=%d amp=%.3f mode=%s dRMS=%.3g' % (
        args.act, args.amp, mode, ds), fill=(255, 220, 80), font=font)
    out = media_path('flatten-vis-02-poke.png')
    im.save(out)
    print('saved', out, 'dRMS', ds)
    if hasattr(dm, 'close'):
        dm.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
