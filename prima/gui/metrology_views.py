"""Metrology canvases: wavefront, slopes, pupil image, Zernike table."""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QSizePolicy,
)

from prima.metrology.constants import Constants


class ArrayImageView(pg.GraphicsLayoutWidget):
    def __init__(self, title=''):
        super().__init__()
        self.setBackground('#0b1015')
        self.setMinimumHeight(140)
        self._vb = self.addViewBox(lockAspect=True, invertY=True, enableMenu=False)
        self._vb.setAspectLocked(True, ratio=1.0)
        self._img = pg.ImageItem(axisOrder='row-major')
        self._vb.addItem(self._img)
        self._title = title
        self._caption = QLabel(title or '—')
        self._caption.setObjectName('muted')

    def caption_label(self):
        return self._caption

    def set_array(self, arr, caption=None):
        if arr is None:
            return
        data = np.ma.filled(np.ma.array(arr), np.nan).astype(np.float64)
        finite = data[np.isfinite(data)]
        if finite.size == 0:
            return
        lo, hi = float(np.percentile(finite, 2)), float(np.percentile(finite, 98))
        if hi <= lo:
            hi = lo + 1.0
        self._img.setImage(data, autoLevels=False, levels=(lo, hi))
        h, w = data.shape[:2]
        self._vb.setRange(xRange=(0, w), yRange=(0, h), padding=0.02)
        if caption is not None:
            self._caption.setText(caption)
        elif self._title:
            self._caption.setText(
                '%s  min=%.3g max=%.3g' % (self._title, lo, hi))


class MetrologyViews(QWidget):
    """WF / slopes / pupil strip + Zernike table (Prisma system_gui products)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        imgs = QHBoxLayout()
        imgs.setSpacing(6)
        self._wf = ArrayImageView('wavefront [nm]')
        self._slopes = ArrayImageView('slopes Sx|Sy')
        self._pupil = ArrayImageView('pupil')
        for view in (self._wf, self._slopes, self._pupil):
            col = QVBoxLayout()
            col.setSpacing(2)
            col.addWidget(view, stretch=1)
            col.addWidget(view.caption_label())
            wrap = QWidget()
            wrap.setLayout(col)
            wrap.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            imgs.addWidget(wrap, stretch=1)
        root.addLayout(imgs, stretch=3)

        zcol = QVBoxLayout()
        zcol.setSpacing(4)
        self._rms = QLabel('RMS — nm')
        self._rms.setObjectName('tagline')
        self._tbl = QTableWidget(Constants.n_zernikes, 2)
        self._tbl.setHorizontalHeaderLabels(['Z [nm]', 'stored'])
        self._tbl.verticalHeader().setVisible(True)
        self._tbl.setVerticalHeaderLabels(
            ['Z%d' % (i + 1) for i in range(Constants.n_zernikes)])
        self._tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl.setSelectionMode(QAbstractItemView.NoSelection)
        for r in range(Constants.n_zernikes):
            for c in range(2):
                item = QTableWidgetItem('—')
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self._tbl.setItem(r, c, item)
        zcol.addWidget(self._rms)
        zcol.addWidget(self._tbl, stretch=1)
        zwrap = QWidget()
        zwrap.setFixedWidth(220)
        zwrap.setLayout(zcol)
        root.addWidget(zwrap, stretch=0)

    def update_products(self, products):
        if not products:
            return
        self._wf.set_array(
            products['wavefront_nm'],
            'wavefront  RMS %.1f nm' % products['rms_nm'])
        self._slopes.set_array(products['slopes'], 'slopes Sx | Sy [norm]')
        self._pupil.set_array(products['pupil'], 'pupil (+ mask tint)')
        self._rms.setText('RMS  %.1f nm' % products['rms_nm'])
        zc = products['zernike_nm']
        n = min(len(zc), Constants.n_zernikes)
        for i in range(Constants.n_zernikes):
            txt = '%5.0f' % zc[i] if i < n else '—'
            self._tbl.item(i, 0).setText(txt)

    def store_zernike_copy(self):
        for r in range(self._tbl.rowCount()):
            self._tbl.item(r, 1).setText(self._tbl.item(r, 0).text())
