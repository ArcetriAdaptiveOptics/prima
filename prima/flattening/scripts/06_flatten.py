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
from prima.flattening.pipeline import (
    IffResult, apply_flatten, flatten_from_iff, process_iff)
from prima.flattening.scripts._common import (
    add_apply_flag, is_dry_run, media_path, internal_path)
from prima.flattening.scripts._vis import (
    save_signed_actuator_map, save_slope_vector, save_sv_plot, montage)
from prima.gui.dm_panel import _actuator_to_grid


def _save_cmd_vis(cmd_delta, svals, rms_before, rms_after, gain, mode, path):
    grid = _actuator_to_grid(cmd_delta)
    g = np.nan_to_num(grid, nan=0.0)
    a = np.abs(g)
    vis = np.clip(a / max(a.max(), 1e-12) * 255, 0, 255).astype(np.uint8)
    vis = np.kron(vis, np.ones((22, 22), dtype=np.uint8))
    panel_w = 280
    canvas = Image.new(
        'RGB', (vis.shape[1] + panel_w, max(vis.shape[0], 280)), (15, 15, 15))
    canvas.paste(Image.fromarray(vis).convert('RGB'), (0, 0))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype(
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 13)
    except Exception:
        font = ImageFont.load_default()
    x0 = vis.shape[1] + 8
    draw.text((x0, 8), 'Flat cmd |Δ| map', fill=(255, 220, 80), font=font)
    draw.text((x0, 28), 'mode=%s gain=%.2f' % (mode, gain),
              fill=(180, 255, 180), font=font)
    draw.text((x0, 48), 'RMS before=%.4g' % rms_before,
              fill=(200, 200, 255), font=font)
    draw.text((x0, 68), 'RMS after =%.4g' % rms_after,
              fill=(200, 200, 255), font=font)
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
    p.add_argument('--n-iter', type=int, default=2)
    p.add_argument('--prefer', default='dao')
    p.add_argument('--cube', default=None)
    p.add_argument('--svd-threshold', type=float, default=1e-3)
    args = p.parse_args(argv)
    dry = is_dry_run(args)
    stack = None
    cube = Path(args.cube) if args.cube else Path(
        str(media_path('flatten-iff')) + '_cube')

    if dry:
        dm = FakeBmcDm()
        dist = np.zeros(dm.n_acts)
        dist[8:18] = 0.07
        dist[40:55] = -0.05
        wfs = FakePyramid(dm, disturbance=dist, noise_rms=1e-5, seed=2)
        mode = 'fake-compute'
        if (cube / 'im.npy').exists() and (cube / 'reconstructor.npy').exists():
            r = np.load(cube / 'reconstructor.npy')
            svals = (np.load(cube / 'singular_values.npy')
                     if (cube / 'singular_values.npy').exists()
                     else np.array([]))
            result = apply_flatten(
                dm, wfs, r, gain=args.gain, n_iter=args.n_iter,
                singular_values=svals)
        else:
            _, r, result = flatten_from_iff(
                dm, wfs, amplitude=args.amp, gain=args.gain,
                n_iter=args.n_iter)
            svals = result.singular_values
    else:
        from prima.flattening.scripts._hw import open_live_stack
        if not (cube / 'im.npy').exists():
            raise SystemExit('missing IFF cube %s — run 04 --apply first' % cube)
        if not (cube / 'reconstructor.npy').exists():
            raise SystemExit(
                'missing reconstructor — run 05 on cube first: %s' % cube)
        r = np.load(cube / 'reconstructor.npy')
        svals = (np.load(cube / 'singular_values.npy')
                 if (cube / 'singular_values.npy').exists() else np.array([]))
        # Re-process if slope count mismatch after reopen
        # Restore IFF mod center from cube (no re-autocenter — match IM WP)
        stack = open_live_stack(
            prefer=args.prefer, park_dm=True, geometry_dir=cube,
            autocenter=False, restore_mod_center=True)
        dm, wfs = stack.dm, stack.wfs
        mode = 'live-apply/%s' % wfs.mode
        # Warm up one acquire so frozen mask / n_slopes are active
        s0 = np.asarray(wfs.acquire_map(output_type='slopes1d'), dtype=float)
        save_slope_vector(
            s0, 'flatten-vis-hadamard-slopes-before.png',
            title='slopes BEFORE flatten')
        if s0.size != r.shape[1]:
            raise SystemExit(
                'IM slopes %d != live slopes %d after loading geometry — '
                're-run 04 --apply (cube incomplete?)' % (r.shape[1], s0.size))
        result = apply_flatten(
            dm, wfs, r, gain=args.gain, n_iter=args.n_iter,
            singular_values=svals)

    out = media_path('flatten-vis-flat-cmd.png')
    _save_cmd_vis(
        result.cmd_delta, result.singular_values, result.rms_before,
        result.rms_after, args.gain, mode, out)
    save_signed_actuator_map(
        result.cmd_delta, 'flatten-vis-hadamard-flat-cmd.png',
        title='flat Δcmd gain=%.2f %s' % (args.gain, mode))
    # Re-measure slopes for before/after vis if live (already in result)
    # Placeholder vectors from RMS annotation only — full maps saved during apply
    if not dry and stack is not None:
        try:
            s_after = np.asarray(
                stack.wfs.acquire_map(output_type='slopes1d'), dtype=float)
            save_slope_vector(
                s_after, 'flatten-vis-hadamard-slopes-after.png',
                title='slopes AFTER flatten')
        except Exception as exc:
            print('after-slopes vis skip:', exc)
    if result.singular_values is not None and np.size(result.singular_values):
        save_sv_plot(result.singular_values, 'flatten-vis-hadamard-sv.png',
                     title='SV at flatten')

    ratio = result.rms_before / max(result.rms_after, 1e-15)
    accept = ratio >= 3.0
    note = internal_path('flatten-iff-status.md')
    prev = note.read_text() if note.exists() else (
        '---\ncursor:\n  subagentId: "bc-65ca8cba-a805-5352-89dc-c0054d937fc6"\n---\n\n')
    # Trim prior Flatten section if re-running
    if '\n## Flatten' in prev:
        prev = prev.split('\n## Flatten')[0].rstrip() + '\n'
    prev += (
        '\n## Flatten (06) — live Hadamard\n'
        '- mode: **%s** dry_run=%s gain=%.2f n_iter=%d\n'
        '- RMS before/after: **%.4g → %.4g (%.2f×)**%s\n'
        '- media: `media/flatten-vis-flat-cmd.png`, '
        '`media/flatten-vis-hadamard-flat-cmd.png`\n'
        '- cmd |Δ| max=%.4g mean=%.4g\n'
        % (mode, dry, args.gain, args.n_iter,
           result.rms_before, result.rms_after, ratio,
           ' **≥3× OK**' if accept else ' **<3× — below acceptance**',
           float(np.max(np.abs(result.cmd_delta))),
           float(np.mean(np.abs(result.cmd_delta)))))
    note.write_text(prev)
    print('saved', out, 'drop=%.2f×' % ratio, 'accept_3x', accept)

    if stack is not None:
        # Leave flattened shape briefly for inspection, then park to flat
        print('parking DM to shipped flat after flatten')
        stack.close(park_dm=True, leave_modulating=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
