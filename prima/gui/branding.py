"""Official Prima logo helpers — header mark + subtle watermark."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt, QEvent, QObject
from PyQt5.QtGui import QPixmap, QPainter
from PyQt5.QtWidgets import QLabel, QWidget, QHBoxLayout


def _repo_root() -> Path:
    # prima/gui/branding.py → repo root
    return Path(__file__).resolve().parents[2]


def logo_path(variant: str = 'light') -> Path:
    """Resolve logo PNG. variant: 'light' (dark UIs) or 'navy' (light UIs)."""
    env = os.environ.get('PRIMA_LOGO_PATH')
    if env:
        p = Path(env)
        if p.is_file():
            return p

    name = 'prima-logo-light.png' if variant == 'light' else 'prima-logo.png'
    candidates = [
        _repo_root() / 'media' / name,
        Path.home() / 'git' / 'prima' / 'media' / name,
        Path(__file__).resolve().parent / 'media' / name,
    ]
    for c in candidates:
        if c.is_file():
            return c
    # Fall back to navy if light missing (or vice versa)
    alt = 'prima-logo.png' if variant == 'light' else 'prima-logo-light.png'
    for c in candidates:
        other = c.with_name(alt)
        if other.is_file():
            return other
    return candidates[0]


def load_logo_pixmap(variant: str = 'light', height: int = 28) -> QPixmap:
    path = logo_path(variant)
    pm = QPixmap(str(path))
    if pm.isNull():
        return pm
    return pm.scaledToHeight(height, Qt.SmoothTransformation)


def make_header_logo(height: int = 28, variant: str = 'light') -> QLabel:
    """Small opaque header mark — keep breathing room around it."""
    lab = QLabel()
    lab.setObjectName('primaLogo')
    pm = load_logo_pixmap(variant=variant, height=height)
    if not pm.isNull():
        lab.setPixmap(pm)
        lab.setFixedSize(pm.size())
    else:
        lab.setText('PRIMA')
        lab.setObjectName('brand')
    lab.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
    lab.setToolTip('Prima')
    lab.setContentsMargins(0, 0, 8, 0)
    return lab


class _WatermarkOverlay(QWidget):
    """Low-opacity corner mark; ignores mouse so controls stay usable."""

    def __init__(self, parent: QWidget, pixmap: QPixmap, opacity: float = 0.10,
                 anchor: str = 'bottom-left'):
        super().__init__(parent)
        self._pm = pixmap
        self._opacity = float(opacity)
        self._anchor = anchor
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet('background: transparent;')
        self.setFocusPolicy(Qt.NoFocus)

    def paintEvent(self, event):
        if self._pm.isNull():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.setOpacity(self._opacity)
        margin = 16
        max_w = max(80, int(self.width() * 0.28))
        scaled = self._pm.scaledToWidth(max_w, Qt.SmoothTransformation)
        if self._anchor == 'top-right':
            x = self.width() - scaled.width() - margin
            y = margin
        elif self._anchor == 'bottom-right':
            x = self.width() - scaled.width() - margin
            y = self.height() - scaled.height() - margin
        else:  # bottom-left
            x = margin
            y = self.height() - scaled.height() - margin
        p.drawPixmap(x, y, scaled)
        p.end()


class _WatermarkHostFilter(QObject):
    def __init__(self, host: QWidget, overlay: _WatermarkOverlay):
        super().__init__(host)
        self._host = host
        self._overlay = overlay

    def eventFilter(self, obj, event):
        if obj is self._host and event.type() == QEvent.Resize:
            self._overlay.setGeometry(self._host.rect())
            self._overlay.raise_()
        return False


def install_watermark(host: QWidget, *, variant: str = 'light',
                      opacity: float = 0.10, anchor: str = 'bottom-left',
                      height_hint: int = 220) -> Optional[QWidget]:
    """Attach a subtle logo watermark over *host* (typically the frame column).

    Placed in a free corner so the central WFS / DM maps stay dominant.
    """
    pm = load_logo_pixmap(variant=variant, height=height_hint)
    if pm.isNull():
        return None
    overlay = _WatermarkOverlay(host, pm, opacity=opacity, anchor=anchor)
    overlay.setGeometry(host.rect())
    overlay.show()
    overlay.raise_()
    filt = _WatermarkHostFilter(host, overlay)
    host.installEventFilter(filt)
    # Keep filter alive
    overlay._host_filter = filt  # noqa: SLF001 — lifetime pin
    return overlay


def decorate_brand_row(layout: QHBoxLayout, tagline: str, *,
                       logo_height: int = 28, variant: str = 'light') -> QLabel:
    """Fill an empty QHBoxLayout with logo + tagline + stretch (logo left)."""
    logo = make_header_logo(height=logo_height, variant=variant)
    tag = QLabel(tagline)
    tag.setObjectName('tagline')
    layout.addWidget(logo)
    layout.addWidget(tag)
    layout.addStretch(1)
    return logo
