"""Drop 2 open-loop BMC Multi-DM panel — DAO SHM path (not plico).

Writes shapes to ``/tmp/prima_dm1Cmd.im.shm``. Hardware apply is done by
``daodm_bmc_ctrl`` (daoEkarus ``daodmAlpaoCtrl`` pattern). In Demo mode the
panel also applies in-process for immediate visual feedback.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QPushButton, QSpinBox, QDoubleSpinBox,
    QFormLayout, QStatusBar, QComboBox, QSizePolicy, QFileDialog,
)

from prima.gui.branding import build_brand_row, install_watermark

pg.setConfigOptions(imageAxisOrder='row-major', antialias=True)

N_ACT = 140
GRID = 12


def _actuator_to_grid(cmd: np.ndarray) -> np.ndarray:
    grid = np.full((GRID, GRID), np.nan, dtype=float)
    idx = 0
    for r in range(GRID):
        for c in range(GRID):
            corner = (r in (0, GRID - 1)) and (c in (0, GRID - 1))
            if corner:
                continue
            if idx >= len(cmd):
                break
            grid[r, c] = float(cmd[idx])
            idx += 1
    return grid


STYLESHEET = """
QMainWindow, QWidget { background-color: #0b1015; color: #e8eef7; }
QLabel#brand { font-size: 22px; font-weight: 700; color: #7ec8e3; }
QLabel#tagline { color: #8a9bb0; font-size: 12px; }
QGroupBox {
  border: 1px solid #2a3441; border-radius: 4px; margin-top: 10px;
  font-weight: 600; color: #c5d0dc;
}
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
QPushButton {
  background: #1a2836; border: 1px solid #3a5168; border-radius: 3px;
  padding: 6px 10px; color: #e8eef7;
}
QPushButton:hover { background: #243446; border-color: #7ec8e3; }
QPushButton#primary { background: #1e4a5c; border-color: #7ec8e3; }
QStatusBar { color: #8a9bb0; }
QSpinBox, QDoubleSpinBox, QComboBox {
  background: #121820; border: 1px solid #2a3441; color: #e8eef7;
  padding: 2px 4px;
}
"""


class DmPanelWindow(QMainWindow):
    def __init__(self, prefer: str = 'auto'):
        super().__init__()
        self.setWindowTitle('Prima — Drop 2 · BMC Multi-DM (DAO)')
        self.resize(1020, 700)
        self.setStyleSheet(STYLESHEET)
        self._prefer = prefer
        self._ctrl_proc = None
        self._shape = np.zeros(N_ACT, dtype=np.float32)
        self._usb_status = 'probe pending'

        from daoprima.create_shm import create_default_graph
        from daoprima.bridges import ShmCommandWriter
        from daoprima.hw.bmc_dm import probe_bmc_usb

        create_default_graph()
        self._writer = ShmCommandWriter()
        probe = probe_bmc_usb()
        self._usb_status = probe.message

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(10, 10, 14, 10)
        root.setSpacing(10)

        left_host = QWidget()
        left = QVBoxLayout(left_host)
        left.setContentsMargins(0, 0, 4, 0)
        brand_row, _, _ = build_brand_row(
            'Drop 2 · BMC Multi-DM 5.5 µm · DAO SHM',
            logo_height=28, variant='light')
        left.addLayout(brand_row)

        self._plot = pg.GraphicsLayoutWidget()
        self._plot.setBackground('#0b1015')
        self._vb = self._plot.addViewBox(lockAspect=True, invertY=True)
        self._img = pg.ImageItem(axisOrder='row-major')
        self._vb.addItem(self._img)
        cmap = pg.colormap.get('viridis')
        self._img.setLookupTable(cmap.getLookupTable(nPts=256))
        left.addWidget(self._plot, stretch=1)

        self._minmax = QLabel('shape —')
        self._minmax.setObjectName('tagline')
        left.addWidget(self._minmax)
        root.addWidget(left_host, stretch=1)
        install_watermark(
            left_host, variant='light', opacity=0.10,
            anchor='bottom-left', height_hint=180)

        side = QVBoxLayout()
        side.setContentsMargins(6, 0, 10, 0)
        side.setSpacing(8)
        side.addWidget(self._build_connect())
        side.addWidget(self._build_shapes())
        side.addWidget(self._build_poke())
        side.addStretch(1)
        side_host = QWidget()
        side_host.setMinimumWidth(320)
        side_host.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)
        side_host.setLayout(side)
        root.addWidget(side_host, stretch=0)

        self.setStatusBar(QStatusBar())
        self._refresh_status()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(200)
        self._on_tick()

    def _build_connect(self):
        box = QGroupBox('DAO connection')
        form = QFormLayout(box)
        self._mode = QComboBox()
        self._mode.addItems([
            'SHM + daodm_bmc_ctrl (auto)',
            'SHM + USB only',
            'SHM + sim controller',
            'SHM only (no HW process)',
        ])
        form.addRow('Mode', self._mode)
        row = QHBoxLayout()
        b_start = QPushButton('Start controller')
        b_start.setObjectName('primary')
        b_start.clicked.connect(self._on_start_ctrl)
        b_stop = QPushButton('Stop controller')
        b_stop.clicked.connect(self._on_stop_ctrl)
        row.addWidget(b_start)
        row.addWidget(b_stop)
        form.addRow(row)
        self._info = QLabel('')
        self._info.setWordWrap(True)
        self._info.setMinimumWidth(160)
        form.addRow('Status', self._info)
        return box

    def _build_shapes(self):
        box = QGroupBox('Open-loop shapes → SHM')
        lay = QVBoxLayout(box)
        for label, slot in (
                ('Zero', self._on_zero),
                ('Flat mid (0.5)', self._on_flat),
                ('Random ±0.05 about mid', self._on_random),
                ('Checkerboard about mid', self._on_checker),
                ('Load CSV shape…', self._on_load_csv),
        ):
            b = QPushButton(label)
            b.clicked.connect(slot)
            lay.addWidget(b)
        return box

    def _build_poke(self):
        box = QGroupBox('Single actuator poke')
        form = QFormLayout(box)
        self._poke_idx = QSpinBox()
        self._poke_idx.setRange(0, N_ACT - 1)
        self._poke_amp = QDoubleSpinBox()
        self._poke_amp.setRange(0.0, 1.0)
        self._poke_amp.setSingleStep(0.05)
        self._poke_amp.setValue(0.65)
        form.addRow('Actuator', self._poke_idx)
        form.addRow('Value [0,1]', self._poke_amp)
        b = QPushButton('Apply poke')
        b.setObjectName('primary')
        b.clicked.connect(self._on_poke)
        form.addRow(b)
        return box

    def _prefer_from_ui(self) -> str:
        idx = self._mode.currentIndex()
        return {0: 'auto', 1: 'usb', 2: 'sim'}.get(idx, 'sim')

    def _on_start_ctrl(self):
        self._on_stop_ctrl()
        if self._mode.currentIndex() == 3:
            self.statusBar().showMessage('SHM-only — start daodm_bmc_ctrl externally', 5000)
            self._refresh_status()
            return
        prefer = self._prefer_from_ui()
        cmd = [
            sys.executable, '-m', 'daoprima.apps.daodm_bmc_ctrl',
            '--prefer', prefer, '--create-graph',
        ]
        self._ctrl_proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.statusBar().showMessage('started daodm_bmc_ctrl prefer=%s pid=%s' % (
            prefer, self._ctrl_proc.pid), 5000)
        self._refresh_status()

    def _on_stop_ctrl(self):
        if self._ctrl_proc is not None and self._ctrl_proc.poll() is None:
            self._ctrl_proc.terminate()
            try:
                self._ctrl_proc.wait(timeout=2)
            except Exception:
                self._ctrl_proc.kill()
        self._ctrl_proc = None

    def closeEvent(self, event):
        self._on_stop_ctrl()
        super().closeEvent(event)

    def _refresh_status(self):
        alive = (
            self._ctrl_proc is not None and self._ctrl_proc.poll() is None)
        self._info.setText(
            '%d actuators · SHM /tmp/prima_dm1Cmd.im.shm\n'
            'controller: %s\nUSB: %s' % (
                N_ACT,
                'running pid=%s' % self._ctrl_proc.pid if alive else 'stopped',
                self._usb_status))

    def _apply(self, shape):
        self._shape = np.asarray(shape, dtype=np.float32).ravel()
        if self._shape.size != N_ACT:
            self._shape = np.resize(self._shape, N_ACT)
        self._writer.set_shape(self._shape)
        self._on_tick()

    def _on_zero(self):
        self._apply(np.zeros(N_ACT))

    def _on_flat(self):
        self._apply(np.full(N_ACT, 0.5))

    def _on_random(self):
        rng = np.random.default_rng()
        self._apply(np.clip(0.5 + rng.uniform(-0.05, 0.05, N_ACT), 0, 1))

    def _on_checker(self):
        cmd = np.full(N_ACT, 0.5)
        cmd[0::2] = 0.55
        cmd[1::2] = 0.45
        self._apply(cmd)

    def _on_poke(self):
        cmd = np.full(N_ACT, 0.5, dtype=np.float32)
        cmd[int(self._poke_idx.value())] = float(self._poke_amp.value())
        self._apply(cmd)

    def _on_load_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Load shape CSV', '', 'CSV (*.csv);;All (*)')
        if not path:
            return
        try:
            data = np.loadtxt(path, delimiter=',', dtype=float).ravel()
        except Exception:
            data = np.loadtxt(path, dtype=float).ravel()
        if data.size < N_ACT:
            data = np.resize(data, N_ACT)
        self._apply(data[:N_ACT])

    def _on_tick(self):
        try:
            shape = self._writer.get_shape()
        except Exception:
            shape = self._shape
        if shape.size != N_ACT:
            shape = np.resize(shape, N_ACT)
        grid = _actuator_to_grid(shape)
        finite = grid[np.isfinite(grid)]
        if finite.size:
            lo, hi = float(finite.min()), float(finite.max())
            if lo == hi:
                lo, hi = lo - 0.01, hi + 0.01
        else:
            lo, hi = 0.0, 1.0
        self._img.setImage(grid, autoLevels=False, levels=(lo, hi))
        self._minmax.setText('min=%.3f  max=%.3f  mean=%.3f' % (
            float(np.nanmin(grid)), float(np.nanmax(grid)),
            float(np.nanmean(grid))))
        self._refresh_status()


def build_app(argv=None, prefer: str = 'auto'):
    app = QApplication(argv or [sys.argv[0]])
    win = DmPanelWindow(prefer=prefer)
    win.show()
    return app, win


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    parser = argparse.ArgumentParser(description='Prima Drop 2 DM GUI (DAO)')
    parser.add_argument('--prefer', default='auto',
                        choices=['auto', 'usb', 'vendor', 'sim'])
    parser.add_argument('--screenshot', metavar='PATH')
    parser.add_argument('--platform', default=None)
    args, qt_args = parser.parse_known_args(argv)
    if args.platform:
        os.environ['QT_QPA_PLATFORM'] = args.platform
    elif args.screenshot:
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

    app, win = build_app(['prima-dm-gui'] + qt_args, prefer=args.prefer)
    if args.screenshot:
        QTimer.singleShot(400, lambda: _shot(win, args.screenshot, app))
    return app.exec_()


def _shot(win, path, app):
    win.grab().save(path)
    app.quit()


if __name__ == '__main__':
    sys.exit(main())
