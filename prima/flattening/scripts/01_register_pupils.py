#!/usr/bin/env python3
"""01 — register PWFS pupils at 4 mrad (Prima and/or opticalib).

Keeps both measurement procedures in parallel:
  - ``prima``: MetrologyEngine free centroids (no rectangular snap)
  - ``opticalib``: PyramidPupilData.from_img (ArcetriLAB square-fit)
  - ``both``: run both, save comparison overlays (default)
"""
from __future__ import annotations

import argparse
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from prima.drop1_defaults import (
    DEFAULT_MOD_FREQ_HZ, DEFAULT_MOD_RADIUS_MRAD,
    exposure_ms_one_mod_period)
from prima.flattening.pupils import (
    find_pupils_both, find_pupils_opticalib, find_pupils_prima, compare_geometries)
from prima.flattening.scripts._common import (
    add_apply_flag, is_dry_run, media_path, internal_path)


def _font(size=14):
    try:
        return ImageFont.truetype(
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', size)
    except Exception:
        return ImageFont.load_default()


def _norm_u8(frame):
    lo, hi = np.percentile(frame, [1, 99.5])
    return np.clip((frame - lo) / max(hi - lo, 1) * 255, 0, 255).astype(np.uint8)


def _draw_pupils(im, centers, radius, color, scale, width=2, label=None, origin=(8, 8)):
    draw = ImageDraw.Draw(im)
    for cy, cx in np.asarray(centers).reshape(-1, 2):
        if not np.isfinite(cy) or not np.isfinite(cx):
            continue
        x, y = float(cx) / scale, float(cy) / scale
        rr = float(radius) / scale
        draw.ellipse([x - rr, y - rr, x + rr, y + rr], outline=color, width=width)
    if label:
        draw.text(origin, label, fill=color, font=_font(14))
    return im


def save_overlay(frame, geos: dict, name: str, title: str) -> str:
    vis = _norm_u8(frame)
    scale = 2 if vis.shape[0] > 800 else 1
    if scale > 1:
        vis = vis[::scale, ::scale]
    im = Image.fromarray(np.stack([vis] * 3, -1))
    draw = ImageDraw.Draw(im)
    draw.text((8, 8), title, fill=(255, 220, 80), font=_font(16))
    y0 = 30
    # Prima = yellow, opticalib = cyan
    if 'prima' in geos and np.isfinite(geos['prima'].centers).all():
        g = geos['prima']
        _draw_pupils(im, g.centers, g.radius, (255, 220, 60), scale, 2,
                     label='prima r=%.1f' % g.radius, origin=(8, y0))
        y0 += 20
    if 'opticalib' in geos and np.isfinite(geos['opticalib'].centers).all():
        g = geos['opticalib']
        _draw_pupils(im, g.centers, g.radius, (80, 220, 255), scale, 2,
                     label='opticalib r=%.1f' % g.radius, origin=(8, y0))
    out = media_path(name)
    im.save(out)
    return str(out)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    add_apply_flag(p)
    p.add_argument('--fake', action='store_true')
    p.add_argument(
        '--method', default='both',
        choices=['prima', 'opticalib', 'both'],
        help='Pupil finder (default: both in parallel)')
    p.add_argument('--opticalib-threshold', type=float, default=400.0)
    p.add_argument(
        '--touch-modulator', action='store_true',
        help='Reconnect E-518 and reassert 4 mrad work defaults')
    args = p.parse_args(argv)
    dry = is_dry_run(args)

    if args.fake or dry:
        frame = np.zeros((512, 512), dtype=float)
        centers = np.array([[368, 144], [368, 368], [144, 144], [144, 368]], float)
        r = 56.0
        yy, xx = np.ogrid[:512, :512]
        for cy, cx in centers:
            frame[(yy - cy) ** 2 + (xx - cx) ** 2 <= r ** 2] = 2000
        mode = 'fake/dry'
    else:
        from prima.gui.aravis_camera import AravisLiveCamera
        if args.touch_modulator:
            from prima.hardware.pi_e518_modulator import PiE518Modulator
            m = PiE518Modulator(connect=True)
            m.setFrequencyInHz(float(DEFAULT_MOD_FREQ_HZ))
            m.setRadiusInMilliRad(float(DEFAULT_MOD_RADIUS_MRAD))
            time.sleep(0.8)
            try:
                m._gcs.close(); m._setup_done = False
            except Exception:
                pass
        cam = AravisLiveCamera(ip_address='192.168.30.189')
        # Sync exposure to one modulator period (t_exp = 1/f_mod)
        cam.setExposureTime(float(exposure_ms_one_mod_period(DEFAULT_MOD_FREQ_HZ)))
        time.sleep(0.4)
        frame = np.mean(
            [np.asarray(cam.getFrame(), dtype=float) for _ in range(4)], 0)
        mode = 'live'
        cam.close()

    geos = {}
    if args.method in ('prima', 'both'):
        try:
            geos['prima'] = find_pupils_prima(frame)
            print('prima centers=\n%s r=%.1f' % (
                geos['prima'].centers, geos['prima'].radius))
        except Exception as exc:
            print('prima FAILED:', exc)
    if args.method in ('opticalib', 'both'):
        try:
            geos['opticalib'] = find_pupils_opticalib(
                frame, threshold=args.opticalib_threshold)
            g = geos['opticalib']
            print('opticalib centers=\n%s r=%.1f notes=%s' % (
                g.centers, g.radius, g.notes))
        except Exception as exc:
            print('opticalib FAILED:', exc)

    # Per-method overlays
    if 'prima' in geos:
        save_overlay(
            frame, {'prima': geos['prima']},
            'flatten-vis-01-pupils.png',
            'Pupils PRIMA @ 4 mrad (%s)' % mode)
        save_overlay(
            frame, {'prima': geos['prima']},
            'flatten-vis-pupils-prima.png',
            'Pupils PRIMA (free centroids) mode=%s' % mode)
    if 'opticalib' in geos:
        save_overlay(
            frame, {'opticalib': geos['opticalib']},
            'flatten-vis-pupils-opticalib.png',
            'Pupils opticalib PWFS (square-fit) mode=%s' % mode)

    cmp = None
    if 'prima' in geos and 'opticalib' in geos:
        cmp = compare_geometries(geos['prima'], geos['opticalib'])
        print('compare center_rms_px=%.2f Δr=%.2f' % (
            cmp['center_rms_px'], cmp['radius_delta']))
        out = save_overlay(
            frame, geos,
            'flatten-vis-pupils-prima-vs-opticalib.png',
            'Pupils PRIMA (yellow) vs opticalib (cyan)  Δrms=%.1fpx' % (
                cmp['center_rms_px']))
        print('saved compare', out)

    note = internal_path('flatten-pupils-methods.md')
    lines = [
        '---',
        'cursor:',
        '  subagentId: "bc-65ca8cba-a805-5352-89dc-c0054d937fc6"',
        '---',
        '',
        '# Pupil measurement methods (parallel)',
        '',
        '- mode: **%s** method_flag=%s' % (mode, args.method),
        '- opticalib_threshold: %.1f' % args.opticalib_threshold,
        '',
    ]
    if 'prima' in geos:
        g = geos['prima']
        lines += [
            '## Prima',
            '- r=%.2f' % g.radius,
            '- centers (y,x) A,B,C,D:',
            '```',
            str(g.centers),
            '```',
            '- media: `media/flatten-vis-pupils-prima.png`',
            '',
        ]
    if 'opticalib' in geos:
        g = geos['opticalib']
        lines += [
            '## Opticalib PWFS',
            '- r=%.2f avg_d=%.2f' % (g.radius, g.avg_diameter),
            '- notes: %s' % g.notes,
            '- centers (y,x) A,B,C,D:',
            '```',
            str(g.centers),
            '```',
            '- media: `media/flatten-vis-pupils-opticalib.png`',
            '',
        ]
    if cmp is not None:
        lines += [
            '## Compare',
            '- center_rms_px: **%.2f**' % cmp['center_rms_px'],
            '- radius_delta (prima−opticalib): %.2f' % cmp['radius_delta'],
            '- media: `media/flatten-vis-pupils-prima-vs-opticalib.png`',
            '',
        ]
    note.write_text('\n'.join(lines))
    print('note', note)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
