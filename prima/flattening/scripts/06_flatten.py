#!/usr/bin/env python3
"""06 — compute / apply flatten command (gain default 0.5).

Always writes SV+cmd visibility first. Real DM apply only with ``--apply``.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from prima.flattening.devices.fake import FakeBmcDm, FakePyramid
from prima.flattening.pipeline import flatten_from_iff, process_iff, IffResult
from prima.flattening.scripts._common import (
    add_apply_flag, is_dry_run, media_path, internal_path)
from prima.gui.dm_panel import _actuator_to_grid


def _save_cmd_vis(cmd_delta, svals, rms_before, rms_after, gain, mode, path):
    grid = _actuator_to_grid(cmd_delta)
    g = np.nan_to_num(grid, nan=0.0)
    a = np.abs(g)
    vis = np.clip(a / max(a.max(), 1e-12) * 255, 0, 255).astype(np.uint8)
    vis = np.kron(vis, np.ones((22, 22), dtype=np.uint8))
    # side panel for SV
    panel_w = 280
    canvas = Image.new('RGB', (vis.shape[1] + panel_w, max(vis.shape[0], 280)), (15, 15, 15))
    canvas.paste(Image.fromarray(vis).convert('RGB'), (0, 0))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype(
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 13)
    except Exception:
        font = ImageFont.load_default()
    x0 = vis.shape[1] + 8
    draw.text((x0, 8), 'Flat cmd |Δ| map', fill=(255, 220, 80), font=font)
    draw.text((x0, 28), 'mode=%s gain=%.2f' % (mode, gain), fill=(180, 255, 180), font=font)
    draw.text((x0, 48), 'RMS before=%.4g' % rms_before, fill=(200, 200, 255), font=font)
    draw.text((x0, 68), 'RMS after =%.4g' % rms_after, fill=(200, 200, 255), font=font)
    ratio = rms_before / max(rms_after, 1e-15)
    draw.text((x0, 88), 'drop=%.2f×' % ratio, fill=(255, 180, 100), font=font)
    if svals is not None and np.size(svals):
        draw.text((x0, 120), 'SV (norm, log)', fill=(180, 220, 255), font=font)
        y = np.log10(np.maximum(np.asarray(svals) / svals[0], 1e-12))
        for i in range(min(len(y) - 1, 80)):
            xa = x0 + 2 + i * 3
            ya0 = 260 - 80 * (y[i] - y.min()) / max(np.ptp(y), 1e-9)
            ya1 = 260 - 80 * (y[i + 1] - y.min()) / max(np.ptp(y), 1e-9)
            draw.line([(xa, ya0), (xa + 3, ya1)], fill=(100, 180, 255), width=2)
    canvas.save(path)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    add_apply_flag(p)
    p.add_argument('--gain', type=float, default=0.5)
    p.add_argument('--amp', type=float, default=0.05)
    p.add_argument('--cube', default=None)
    args = p.parse_args(argv)
    dry = is_dry_run(args)

    # Fake path always for compute visibility; HW apply optional later
    dm = FakeBmcDm()
    dist = np.zeros(dm.n_acts)
    dist[8:18] = 0.07
    dist[40:55] = -0.05
    wfs = FakePyramid(dm, disturbance=dist, noise_rms=1e-5, seed=2)

    cube = Path(args.cube) if args.cube else Path(str(media_path('flatten-iff')) + '_cube')
    if (cube / 'reconstructor.npy').exists():
        r = np.load(cube / 'reconstructor.npy')
        svals = (np.load(cube / 'singular_values.npy')
                 if (cube / 'singular_values.npy').exists() else np.array([]))
        from prima.flattening.pipeline import apply_flatten
        # Need fresh IFF-consistent wfs — re-run flatten_from_iff for honesty
        iff, r, result = flatten_from_iff(
            dm, wfs, amplitude=args.amp, gain=args.gain, n_iter=2)
        svals = result.singular_values
    else:
        iff, r, result = flatten_from_iff(
            dm, wfs, amplitude=args.amp, gain=args.gain, n_iter=2)
        svals = result.singular_values

    out = media_path('flatten-vis-flat-cmd.png')
    mode = 'fake-compute' if dry else 'apply'
    _save_cmd_vis(
        result.cmd_delta, svals, result.rms_before, result.rms_after,
        args.gain, mode, out)

    note = internal_path('flatten-iff-status.md')
    prev = note.read_text() if note.exists() else (
        '---\ncursor:\n  subagentId: "bc-65ca8cba-a805-5352-89dc-c0054d937fc6"\n---\n\n')
    ratio = result.rms_before / max(result.rms_after, 1e-15)
    accept = ratio >= 3.0
    prev += (
        '\n## Flatten\n'
        '- dry_run=%s gain=%.2f\n'
        '- RMS before/after: %.4g → %.4g (%.2f×)%s\n'
        '- media: `media/flatten-vis-flat-cmd.png`\n'
        '- HW apply: **not run** in this pass (fake compute). '
        'Re-run with `--apply` on alienware when ready; restore bias on failure.\n'
        % (dry, args.gain, result.rms_before, result.rms_after, ratio,
           ' **≥3× OK**' if accept else ' **<3× — report honestly**'))
    note.write_text(prev)
    print('saved', out, 'drop=%.2f×' % ratio, 'accept_3x', accept)

    if not dry:
        # Real HW path: open USB DM, apply computed-style flatten using live WFS
        # (placeholder: park to bias — full HW slopes need Aravis+Pyramid wiring)
        print('WARNING: --apply HW live flatten not fully wired to Aravis slopes yet; '
              'restoring bias / parking fake path only.')
        try:
            from prima.flattening.devices.bmc_dm import BmcMultiDm
            hwdm = BmcMultiDm(prefer='usb', dry_run=False)
            hwdm.park()
            hwdm.close()
            print('HW DM parked at shipped flat')
        except Exception as e:
            print('HW apply skipped:', e)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
