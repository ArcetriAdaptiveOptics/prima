#!/usr/bin/env python3
"""05 — process IFF cube → reconstructor + SV plot."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from prima.flattening.pipeline import IffResult, process_iff
from prima.flattening.scripts._common import media_path, internal_path


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cube', default=None,
                   help='Directory with im.npy (default: media flatten-iff_cube)')
    p.add_argument('--svd-threshold', type=float, default=1e-3)
    args = p.parse_args(argv)
    cube = Path(args.cube) if args.cube else Path(str(media_path('flatten-iff')) + '_cube')
    im = np.load(cube / 'im.npy')
    amps = np.load(cube / 'amps.npy') if (cube / 'amps.npy').exists() else np.ones(im.shape[1])
    iff = IffResult(
        amplitudes=amps,
        plus=np.load(cube / 'plus.npy') if (cube / 'plus.npy').exists() else im,
        minus=np.load(cube / 'minus.npy') if (cube / 'minus.npy').exists() else np.zeros_like(im),
        im=im)
    r, svals = process_iff(iff, svd_threshold=args.svd_threshold)
    np.save(cube / 'reconstructor.npy', r)
    np.save(cube / 'singular_values.npy', svals)

    # SV plot
    w, h = 720, 360
    img = Image.new('RGB', (w, h), (18, 18, 18))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 14)
    except Exception:
        font = ImageFont.load_default()
    draw.text((10, 8), 'IFF singular values (log)', fill=(255, 220, 80), font=font)
    if svals.size:
        y = np.log10(np.maximum(svals / svals[0], 1e-12))
        margin = 40
        for i in range(len(y) - 1):
            x0 = margin + (w - 2 * margin) * i / max(len(y) - 1, 1)
            x1 = margin + (w - 2 * margin) * (i + 1) / max(len(y) - 1, 1)
            y0 = h - margin - (h - 2 * margin) * (y[i] - y.min()) / max(np.ptp(y), 1e-9)
            y1 = h - margin - (h - 2 * margin) * (y[i + 1] - y.min()) / max(np.ptp(y), 1e-9)
            draw.line([(x0, y0), (x1, y1)], fill=(120, 200, 255), width=2)
        keep = int(np.sum(svals > args.svd_threshold * svals[0]))
        draw.text((10, 28), 'n_sv=%d keep@thr=%.1e → %d' % (
            svals.size, args.svd_threshold, keep), fill=(180, 255, 180), font=font)
    out = media_path('flatten-vis-05-sv.png')
    img.save(out)
    note = internal_path('flatten-iff-status.md')
    prev = note.read_text() if note.exists() else ''
    note.write_text(
        prev + '\n## Process\n- reconstructor %s\n- SV media `media/flatten-vis-05-sv.png`\n'
        '- svd_threshold=%.1e\n' % (r.shape, args.svd_threshold))
    print('saved', out, 'R', r.shape, 's0', float(svals[0]) if svals.size else None)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
