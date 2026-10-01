"""PNG crosscheck helpers for live flattening visibility."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from prima.flattening.scripts._common import media_path
from prima.gui.dm_panel import _actuator_to_grid


def _font(size: int = 14):
    try:
        return ImageFont.truetype(
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', size)
    except Exception:
        return ImageFont.load_default()


def _norm_u8(arr, p_lo=1.0, p_hi=99.5):
    a = np.asarray(arr, dtype=float)
    finite = a[np.isfinite(a)]
    if finite.size == 0:
        return np.zeros(a.shape, dtype=np.uint8)
    lo, hi = np.percentile(finite, [p_lo, p_hi])
    return np.clip((a - lo) / max(hi - lo, 1e-12) * 255, 0, 255).astype(np.uint8)


def save_frame_with_pupils(
        frame, centers, radius, name: str, title: str = '',
        scale: int | None = None) -> Path:
    vis = _norm_u8(frame)
    if scale is None:
        scale = 2 if vis.shape[0] > 800 else 1
    if scale > 1:
        vis = vis[::scale, ::scale]
    im = Image.fromarray(np.stack([vis] * 3, -1))
    draw = ImageDraw.Draw(im)
    for cy, cx in np.asarray(centers).reshape(-1, 2):
        x, y = float(cx) / scale, float(cy) / scale
        rr = float(radius) / scale
        draw.ellipse([x - rr, y - rr, x + rr, y + rr],
                     outline=(255, 220, 60), width=2)
    if title:
        draw.text((8, 8), title, fill=(255, 220, 80), font=_font(16))
    out = media_path(name)
    im.save(out)
    return out


def save_actuator_map(vec, name: str, title: str = '', cell: int = 20) -> Path:
    grid = _actuator_to_grid(np.asarray(vec, dtype=float))
    g = np.nan_to_num(grid, nan=0.0)
    a = np.abs(g)
    vis = np.clip(a / max(a.max(), 1e-12) * 255, 0, 255).astype(np.uint8)
    vis = np.kron(vis, np.ones((cell, cell), dtype=np.uint8))
    im = Image.fromarray(vis).convert('RGB')
    draw = ImageDraw.Draw(im)
    if title:
        draw.text((6, 6), title, fill=(255, 220, 80), font=_font(14))
    out = media_path(name)
    im.save(out)
    return out


def save_signed_actuator_map(vec, name: str, title: str = '', cell: int = 18) -> Path:
    """Blue=neg, red=pos actuator map."""
    grid = _actuator_to_grid(np.asarray(vec, dtype=float))
    g = np.nan_to_num(grid, nan=0.0)
    m = max(float(np.max(np.abs(g))), 1e-12)
    rgb = np.zeros(g.shape + (3,), dtype=np.uint8)
    pos = np.clip(g / m, 0, 1)
    neg = np.clip(-g / m, 0, 1)
    rgb[..., 0] = (pos * 255).astype(np.uint8)
    rgb[..., 2] = (neg * 255).astype(np.uint8)
    rgb[..., 1] = ((1 - pos - neg).clip(0, 1) * 40).astype(np.uint8)
    big = np.kron(rgb, np.ones((cell, cell, 1), dtype=np.uint8))
    im = Image.fromarray(big)
    draw = ImageDraw.Draw(im)
    if title:
        draw.text((6, 6), title, fill=(255, 220, 80), font=_font(13))
    out = media_path(name)
    im.save(out)
    return out


def save_slope_vector(slopes, name: str, title: str = '') -> Path:
    s = np.asarray(slopes, dtype=float).ravel()
    side = int(np.ceil(np.sqrt(max(s.size, 1))))
    canvas = np.zeros((side, side), dtype=float)
    canvas.ravel()[: s.size] = s
    vis = _norm_u8(canvas, 2, 98)
    # upsample for readability
    vis = np.kron(vis, np.ones((3, 3), dtype=np.uint8))
    im = Image.fromarray(np.stack([vis] * 3, -1))
    draw = ImageDraw.Draw(im)
    rms = float(np.sqrt(np.mean(s ** 2))) if s.size else 0.0
    draw.text((6, 6), '%s  RMS=%.4g  n=%d' % (title or 'slopes', rms, s.size),
              fill=(255, 220, 80), font=_font(14))
    out = media_path(name)
    im.save(out)
    return out


def save_sv_plot(svals, name: str, title: str = 'SV', threshold: float = 1e-3) -> Path:
    w, h = 720, 360
    img = Image.new('RGB', (w, h), (18, 18, 18))
    draw = ImageDraw.Draw(img)
    draw.text((10, 8), title, fill=(255, 220, 80), font=_font(14))
    svals = np.asarray(svals, dtype=float)
    if svals.size:
        y = np.log10(np.maximum(svals / svals[0], 1e-12))
        margin = 40
        for i in range(len(y) - 1):
            x0 = margin + (w - 2 * margin) * i / max(len(y) - 1, 1)
            x1 = margin + (w - 2 * margin) * (i + 1) / max(len(y) - 1, 1)
            y0 = h - margin - (h - 2 * margin) * (y[i] - y.min()) / max(np.ptp(y), 1e-9)
            y1 = h - margin - (h - 2 * margin) * (y[i + 1] - y.min()) / max(np.ptp(y), 1e-9)
            draw.line([(x0, y0), (x1, y1)], fill=(120, 200, 255), width=2)
        keep = int(np.sum(svals > threshold * svals[0]))
        draw.text((10, 28), 'n=%d keep@%.1e → %d' % (
            svals.size, threshold, keep), fill=(180, 255, 180), font=_font(13))
    out = media_path(name)
    img.save(out)
    return out


def montage(paths, name: str, title: str = '', cols: int = 2) -> Path:
    imgs = [Image.open(p).convert('RGB') for p in paths if Path(p).exists()]
    if not imgs:
        raise FileNotFoundError('no images for montage')
    tw = max(im.width for im in imgs)
    th = max(im.height for im in imgs)
    rows = int(np.ceil(len(imgs) / cols))
    canvas = Image.new('RGB', (cols * tw, rows * th + 28), (12, 12, 12))
    draw = ImageDraw.Draw(canvas)
    if title:
        draw.text((8, 4), title, fill=(255, 220, 80), font=_font(15))
    for i, im in enumerate(imgs):
        r, c = divmod(i, cols)
        canvas.paste(im.resize((tw, th)), (c * tw, 28 + r * th))
    out = media_path(name)
    canvas.save(out)
    return out
