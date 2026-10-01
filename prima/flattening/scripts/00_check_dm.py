#!/usr/bin/env python3
"""00 — open BMC, report backend, bias stats; optional park to flat."""
from __future__ import annotations

import argparse
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from prima.flattening.devices.bmc_dm import BmcMultiDm
from prima.flattening.devices.fake import FakeBmcDm
from prima.flattening.scripts._common import (
    add_apply_flag, is_dry_run, media_path)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    add_apply_flag(p)
    p.add_argument('--fake', action='store_true', help='Use FakeBmcDm')
    p.add_argument('--prefer', default='usb')
    args = p.parse_args(argv)
    dry = is_dry_run(args)

    if args.fake or dry:
        dm = FakeBmcDm() if args.fake else BmcMultiDm(dry_run=True)
        mode = 'fake' if args.fake else 'dry-run'
    else:
        dm = BmcMultiDm(prefer=args.prefer, dry_run=False)
        mode = 'apply'
        dm.park()

    bias = dm.bias()
    shape = dm.get_shape()
    print('mode=%s n=%d bias[min,max,mean]=%.4f %.4f %.4f cmd_mean=%.4f' % (
        mode, dm.n_acts, bias.min(), bias.max(), bias.mean(), shape.mean()))

    # Save 12×12-ish grid visualization of bias
    from prima.gui.dm_panel import _actuator_to_grid
    grid = _actuator_to_grid(bias)
    g = np.nan_to_num(grid, nan=0.0)
    lo, hi = float(np.nanmin(grid)), float(np.nanmax(grid))
    vis = np.clip((g - lo) / max(hi - lo, 1e-9) * 255, 0, 255).astype(np.uint8)
    vis = np.kron(vis, np.ones((24, 24), dtype=np.uint8))
    im = Image.fromarray(vis).convert('RGB')
    draw = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype(
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 16)
    except Exception:
        font = ImageFont.load_default()
    draw.text((8, 8), 'BMC bias (shipped flat) mode=%s' % mode,
              fill=(255, 220, 80), font=font)
    out = media_path('flatten-vis-00-dm.png')
    im.save(out)
    print('saved', out)
    if hasattr(dm, 'close'):
        dm.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
