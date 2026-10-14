"""Popup: exposure ↔ modulation beat sync (rarely used; later → Drop 3 LUT)."""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox,
)


class SyncDialog(QDialog):
    """Hold exposure, sweep f_mod, apply best match. Not a daily control."""

    def __init__(self, parent, camera, get_exposure_ms, apply_match_cb):
        super().__init__(parent)
        self.setWindowTitle('Sync tool — exposure ↔ modulation')
        self.resize(720, 480)
        self._camera = camera
        self._get_exposure_ms = get_exposure_ms
        self._apply_match_cb = apply_match_cb
        self._best_freq = None

        lay = QVBoxLayout(self)
        explain = QLabel(
            'Rare commissioning tool. Sweeps f_mod while holding the current '
            'exposure; beat residual is |sinc(f·T)| (null when t_exp = n/f). '
            'After Drop 3 focal-plane calibration, prefer a saved LUT/config '
            'instead of repeating this sweep.')
        explain.setWordWrap(True)
        explain.setStyleSheet('color:#8b9cb3;')
        lay.addWidget(explain)

        row = QHBoxLayout()
        self._btn_run = QPushButton('Run beat sweep')
        self._btn_run.setObjectName('primary')
        self._btn_run.clicked.connect(self._run_sweep)
        self._btn_apply = QPushButton('Apply best match to main GUI')
        self._btn_apply.clicked.connect(self._apply)
        self._btn_close = QPushButton('Close')
        self._btn_close.clicked.connect(self.accept)
        row.addWidget(self._btn_run)
        row.addWidget(self._btn_apply)
        row.addWidget(self._btn_close)
        lay.addLayout(row)

        self._plot = pg.PlotWidget()
        self._plot.setBackground('#151c24')
        self._plot.showGrid(x=True, y=True, alpha=0.2)
        self._plot.setLabel('bottom', 'f_mod (Hz)')
        self._plot.setLabel('left', 'beat residual')
        self._plot.getPlotItem().getAxis('bottom').enableAutoSIPrefix(False)
        self._curve = self._plot.plot(pen=pg.mkPen('#7dd3c0', width=2))
        self._best_line = pg.InfiniteLine(
            angle=90, pen=pg.mkPen('#f0a060', width=1.5, style=Qt.DashLine))
        self._plot.addItem(self._best_line)
        lay.addWidget(self._plot, stretch=1)

        self._result = QLabel('No sweep yet.')
        lay.addWidget(self._result)

    def _run_sweep(self):
        exp = float(self._get_exposure_ms())
        self._camera.setExposureTime(exp)
        freqs = np.linspace(5.0, 40.0, 71)
        beats = [self._camera.beatAmplitude(f, exp) for f in freqs]
        self._curve.setData(freqs, beats)
        best_i = int(np.argmin(beats))
        self._best_freq = float(freqs[best_i])
        self._best_line.setValue(self._best_freq)
        want_f = 1000.0 / exp
        self._result.setText(
            'Held t_exp=%.2f ms → ideal f=%.2f Hz. Min beat at f=%.2f Hz.' % (
                exp, want_f, self._best_freq))

    def _apply(self):
        if self._best_freq is None:
            QMessageBox.information(self, 'Sync', 'Run beat sweep first.')
            return
        self._apply_match_cb(self._best_freq)
        self.accept()
