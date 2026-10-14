#!/usr/bin/env python3
"""04 — acquire modal IFF at 4 mrad (Hadamard default; --apply for HW)."""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np

from prima.flattening.devices.fake import FakeBmcDm, FakePyramid
from prima.flattening.pipeline import acquire_modal_iff, make_modal_base
from prima.flattening.scripts._common import (
    add_apply_flag, is_dry_run, media_path, internal_path)
from prima.flattening.scripts._vis import (
    save_actuator_map, save_frame_with_pupils, save_signed_actuator_map,
    save_slope_vector, montage)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    add_apply_flag(p)
    p.add_argument('--amp', type=float, default=0.04)
    p.add_argument('--n-modes', type=int, default=140,
                   help='Number of modal columns to poke (default all)')
    p.add_argument('--modal-base', default='hadamard',
                   choices=['hadamard', 'zonal'],
                   help='Modal base (opticalib iff modal_base)')
    p.add_argument('--settle', type=float, default=0.08)
    p.add_argument('--prefer', default='dao')
    p.add_argument('--out', default=None, help='Directory for npy cube')
    p.add_argument(
        '--no-autocenter', action='store_true',
        help='Skip pre-IFF autocenter (NOT recommended — pupils may saturate)')
    p.add_argument('--autocenter-duration', type=float, default=8.0,
                   help='Auto Align duration seconds (default 8, like GUI)')
    args = p.parse_args(argv)
    dry = is_dry_run(args)
    stack = None

    if dry:
        dm = FakeBmcDm()
        dist = np.zeros(dm.n_acts)
        dist[5:15] = 0.05
        wfs = FakePyramid(dm, disturbance=dist, noise_rms=1e-5)
        mode = 'fake/dry'
        frame = None
        centers, radius = None, None
    else:
        from prima.flattening.scripts._hw import open_live_stack
        # Autocenter BEFORE IFF — otherwise PWFS pupils saturate / unbalanced
        stack = open_live_stack(
            prefer=args.prefer, park_dm=True,
            autocenter=not args.no_autocenter,
            autocenter_duration_s=args.autocenter_duration)
        dm, wfs = stack.dm, stack.wfs
        mode = 'live/%s' % wfs.mode
        frame = np.asarray(wfs.acquire_detector(2), dtype=float)
        centers = getattr(wfs, '_centers', None)
        radius = getattr(wfs, '_radius', None)
        if stack.autocenter_result is not None:
            ac = stack.autocenter_result
            print('IFF will use mod center (mrad) %.3f, %.3f after autocenter' % (
                ac.center_after[0], ac.center_after[1]))

    n_modes = min(int(args.n_modes), dm.n_acts)
    modes = np.arange(n_modes)
    print('acquiring IFF mode=%s modal_base=%s n_modes=%d amp=%.3f settle=%.3f' % (
        mode, args.modal_base, n_modes, args.amp, args.settle))

    # Pre-vis: pupils + Hadamard mode-0 pattern
    H = make_modal_base(dm.n_acts, args.modal_base)
    save_signed_actuator_map(
        H[:, 0], 'flatten-vis-hadamard-mode0.png',
        title='Hadamard mode 0 (±1) amp-scale')
    save_signed_actuator_map(
        H[:, min(1, n_modes - 1)], 'flatten-vis-hadamard-mode1.png',
        title='Hadamard mode 1 (±1)')
    if frame is not None and centers is not None and radius is not None:
        save_frame_with_pupils(
            frame, centers, radius, 'flatten-vis-hadamard-pupils.png',
            title='Manta @ 4 mrad + pupils (pre-IFF)')

    # Warm-up slopes → freeze mask, then save geometry before long IFF
    s_ref = np.asarray(wfs.acquire_map(output_type='slopes1d'), dtype=float)
    save_slope_vector(s_ref, 'flatten-vis-hadamard-slopes-ref.png',
                      title='slopes ref (flat)')
    out_dir = Path(args.out) if args.out else Path(
        str(media_path('flatten-iff')) + '_cube')
    out_dir.mkdir(parents=True, exist_ok=True)
    if hasattr(wfs, 'save_geometry'):
        wfs.save_geometry(out_dir)

    # Optional registration poke: one Hadamard column response map
    poke = float(args.amp) * H[:, 0]
    dm.set_shape(poke, differential=True)
    if args.settle:
        time.sleep(args.settle)
    s_plus = np.asarray(wfs.acquire_map(output_type='slopes1d'), dtype=float)
    dm.set_shape(-poke, differential=True)
    if args.settle:
        time.sleep(args.settle)
    s_minus = np.asarray(wfs.acquire_map(output_type='slopes1d'), dtype=float)
    dm.set_shape(dm.bias() if hasattr(dm, 'bias') else dm.get_shape(),
                 differential=False)
    if hasattr(dm, 'park'):
        dm.set_shape(dm.bias(), differential=False, max_step=1.0)
    resp = (s_plus - s_minus) / (2.0 * max(args.amp, 1e-12))
    save_slope_vector(resp, 'flatten-vis-hadamard-response-m0.png',
                      title='push-pull response mode 0')
    if not dry and frame is not None:
        try:
            frame2 = np.asarray(wfs.acquire_detector(1), dtype=float)
            save_frame_with_pupils(
                frame2, centers, radius, 'flatten-vis-hadamard-manta.png',
                title='Manta during IFF setup')
        except Exception as exc:
            print('manta mid-vis skip:', exc)

    iff = acquire_modal_iff(
        dm, wfs, amplitude=args.amp, modal_base=args.modal_base,
        mode_list=modes, settle_s=args.settle, progress_every=10)

    np.save(out_dir / 'im.npy', iff.im)
    np.save(out_dir / 'plus.npy', iff.plus)
    np.save(out_dir / 'minus.npy', iff.minus)
    np.save(out_dir / 'amps.npy', iff.amplitudes)
    if iff.modal_base is not None:
        np.save(out_dir / 'modal_base.npy', iff.modal_base)
    if iff.im_actuator is not None:
        np.save(out_dir / 'im_actuator.npy', iff.im_actuator)
    (out_dir / 'mode.txt').write_text(
        '%s\nmodal_base=%s\n' % (mode, iff.modal_base_id))
    if hasattr(wfs, 'save_geometry'):
        wfs.save_geometry(out_dir)

    col_rms = np.sqrt(np.mean(iff.im ** 2, axis=0))
    save_actuator_map(
        col_rms, 'flatten-vis-04-iff.png',
        title='IFF modal-col RMS (%s) amp=%.3f' % (iff.modal_base_id, args.amp))
    save_actuator_map(
        col_rms, 'flatten-vis-hadamard-colrms.png',
        title='Hadamard IFF column RMS')
    # A few mode response energy snapshots from plus-minus
    for mi in (0, 1, min(10, n_modes - 1)):
        save_slope_vector(
            iff.im[:, mi], 'flatten-vis-hadamard-im-m%d.png' % mi,
            title='IM column mode %d' % mi)

    paths = [
        media_path('flatten-vis-hadamard-pupils.png'),
        media_path('flatten-vis-hadamard-mode0.png'),
        media_path('flatten-vis-hadamard-response-m0.png'),
        media_path('flatten-vis-hadamard-colrms.png'),
    ]
    try:
        montage(paths, 'flatten-vis-hadamard-overview.png',
                title='Hadamard IFF overview @ 4 mrad', cols=2)
    except Exception as exc:
        print('montage skip:', exc)

    note = internal_path('flatten-iff-status.md')
    note.write_text(
        '---\ncursor:\n  subagentId: "bc-65ca8cba-a805-5352-89dc-c0054d937fc6"\n---\n\n'
        '# Flatten IFF status\n\n'
        '## Acquire (04) — Hadamard\n'
        '- mode: **%s**\n'
        '- modal_base: **%s** (opticalib-compatible)\n'
        '- autocenter: **yes** (pre-IFF; see `flatten-vis-autocenter-*.png`)\n'
        '- amp: %.3f settle: %.3f n_modes: %d\n'
        '- IM shape: %s\n'
        '- cube: `%s`\n'
        '- col_rms[min,max,mean]: %.4g %.4g %.4g\n'
        '\n### Crosscheck media\n'
        '- `media/flatten-vis-autocenter-before.png` / `-after.png`\n'
        '- `media/flatten-vis-hadamard-pupils.png` — Manta + pupil overlays\n'
        '- `media/flatten-vis-hadamard-manta.png` — Manta frame mid-setup\n'
        '- `media/flatten-vis-hadamard-mode0.png` / `mode1.png` — Hadamard patterns\n'
        '- `media/flatten-vis-hadamard-slopes-ref.png` — slopes at flat\n'
        '- `media/flatten-vis-hadamard-response-m0.png` — push-pull response m0\n'
        '- `media/flatten-vis-hadamard-colrms.png` / `04-iff.png` — modal col RMS\n'
        '- `media/flatten-vis-hadamard-overview.png` — montage\n' % (
            mode, iff.modal_base_id, args.amp, args.settle, n_modes,
            iff.im.shape, out_dir,
            float(col_rms.min()), float(col_rms.max()), float(col_rms.mean())))
    print('saved cube', out_dir, 'IM', iff.im.shape)

    if stack is not None:
        try:
            stack.dm.park()
        except Exception:
            pass
        stack.close(park_dm=False, leave_modulating=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
