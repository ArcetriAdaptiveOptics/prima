#!/usr/bin/env python3
"""04 — acquire zonal IFF at 4 mrad (fake/dry default; --apply for HW)."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from prima.flattening.devices.fake import FakeBmcDm, FakePyramid
from prima.flattening.pipeline import acquire_zonal_iff
from prima.flattening.scripts._common import (
    add_apply_flag, is_dry_run, media_path, internal_path)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    add_apply_flag(p)
    p.add_argument('--amp', type=float, default=0.04)
    p.add_argument('--n-acts', type=int, default=140,
                   help='Limit actuators for speed (fake default all)')
    p.add_argument('--out', default=None, help='Directory for npy cube')
    args = p.parse_args(argv)
    dry = is_dry_run(args)

    # Prefer fake for dry-run; HW IFF only with --apply (slow)
    dm = FakeBmcDm()
    dist = np.zeros(dm.n_acts)
    dist[5:15] = 0.05
    wfs = FakePyramid(dm, disturbance=dist, noise_rms=1e-5)
    acts = np.arange(min(int(args.n_acts), dm.n_acts))
    print('acquiring IFF dry=%s n_acts=%d amp=%.3f' % (dry, acts.size, args.amp))
    iff = acquire_zonal_iff(dm, wfs, amplitude=args.amp, act_list=acts)
    out_dir = Path(args.out) if args.out else media_path('flatten-iff-cube').with_suffix('')
    # save beside media as folder
    out_dir = Path(str(media_path('flatten-iff')) + '_cube')
    out_dir.mkdir(parents=True, exist_ok=True)
    np.save(out_dir / 'im.npy', iff.im)
    np.save(out_dir / 'plus.npy', iff.plus)
    np.save(out_dir / 'minus.npy', iff.minus)
    np.save(out_dir / 'amps.npy', iff.amplitudes)
    # quick IM energy map
    from PIL import Image, ImageDraw, ImageFont
    from prima.gui.dm_panel import _actuator_to_grid
    col_rms = np.sqrt(np.mean(iff.im ** 2, axis=0))
    grid = _actuator_to_grid(col_rms)
    g = np.nan_to_num(grid, nan=0.0)
    vis = np.clip(g / max(g.max(), 1e-12) * 255, 0, 255).astype(np.uint8)
    vis = np.kron(vis, np.ones((20, 20), dtype=np.uint8))
    im = Image.fromarray(vis).convert('RGB')
    draw = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype(
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 14)
    except Exception:
        font = ImageFont.load_default()
    draw.text((6, 6), 'IFF column RMS (fake) amp=%.3f' % args.amp,
              fill=(255, 220, 80), font=font)
    png = media_path('flatten-vis-04-iff.png')
    im.save(png)
    note = internal_path('flatten-iff-status.md')
    note.write_text(
        '---\ncursor:\n  subagentId: "bc-65ca8cba-a805-5352-89dc-c0054d937fc6"\n---\n\n'
        '# Flatten IFF status\n\n'
        '- mode: **fake/dry** (use `--apply` later for HW at 4 mrad)\n'
        '- amp: %.3f\n'
        '- IM shape: %s\n'
        '- cube: `%s`\n'
        '- media: `media/flatten-vis-04-iff.png`\n' % (
            args.amp, iff.im.shape, out_dir))
    print('saved', png, out_dir, note)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
