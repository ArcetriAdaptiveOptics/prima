#!/usr/bin/env python3
"""05 — process IFF cube → reconstructor + SV plot."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from prima.flattening.pipeline import IffResult, process_iff
from prima.flattening.scripts._common import media_path, internal_path
from prima.flattening.scripts._vis import save_sv_plot


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cube', default=None,
                   help='Directory with im.npy (default: media flatten-iff_cube)')
    p.add_argument('--svd-threshold', type=float, default=1e-3)
    args = p.parse_args(argv)
    cube = Path(args.cube) if args.cube else Path(str(media_path('flatten-iff')) + '_cube')
    im = np.load(cube / 'im.npy')
    amps = np.load(cube / 'amps.npy') if (cube / 'amps.npy').exists() else np.ones(im.shape[1])
    modal_base = (np.load(cube / 'modal_base.npy')
                  if (cube / 'modal_base.npy').exists() else None)
    mid = 'hadamard' if modal_base is not None else 'zonal'
    if (cube / 'mode.txt').exists():
        txt = (cube / 'mode.txt').read_text()
        for line in txt.splitlines():
            if line.startswith('modal_base='):
                mid = line.split('=', 1)[1].strip()
    iff = IffResult(
        amplitudes=amps,
        plus=np.load(cube / 'plus.npy') if (cube / 'plus.npy').exists() else im,
        minus=np.load(cube / 'minus.npy') if (cube / 'minus.npy').exists() else np.zeros_like(im),
        im=im,
        modal_base=modal_base,
        modal_base_id=mid,
        im_actuator=(np.load(cube / 'im_actuator.npy')
                     if (cube / 'im_actuator.npy').exists() else None))
    r, svals = process_iff(iff, svd_threshold=args.svd_threshold)
    np.save(cube / 'reconstructor.npy', r)
    np.save(cube / 'singular_values.npy', svals)

    save_sv_plot(
        svals, 'flatten-vis-05-sv.png',
        title='IFF SV (%s) log-norm' % mid, threshold=args.svd_threshold)
    save_sv_plot(
        svals, 'flatten-vis-hadamard-sv.png',
        title='Hadamard IFF singular values', threshold=args.svd_threshold)

    note = internal_path('flatten-iff-status.md')
    prev = note.read_text() if note.exists() else ''
    if '\n## Process\n' in prev:
        prev = prev.split('\n## Process\n')[0].rstrip() + '\n'
    keep = int(np.sum(svals > args.svd_threshold * svals[0])) if svals.size else 0
    note.write_text(
        prev + '\n## Process (05)\n'
        '- modal_base: **%s**\n'
        '- reconstructor %s (actuator-space if Hadamard)\n'
        '- SV media `media/flatten-vis-05-sv.png`, `media/flatten-vis-hadamard-sv.png`\n'
        '- svd_threshold=%.1e keep=%d / %d\n' % (
            mid, r.shape, args.svd_threshold, keep, svals.size))
    print('saved R', r.shape, 's0', float(svals[0]) if svals.size else None,
          'modal_base', mid)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
