"""Drop 2 open-loop BMC Multi-DM panel (140-act shapes via plico_dm)."""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QPushButton, QSpinBox, QDoubleSpinBox,
    QFormLayout, QStatusBar, QComboBox, QSizePolicy,
)

from prima.gui.branding import make_header_logo, install_watermark


pg.setConfigOptions(imageAxisOrder='row-major', antialias=True)

# Approximate Multi-DM square packing for display (12x12 with corners unused).
N_ACT = 140
GRID = 12


def _actuator_to_grid(cmd: np.ndarray) -> np.ndarray:
    """Map 140-vector onto a 12x12 display grid (unused corner cells = nan)."""
    grid = np.full((GRID, GRID), np.nan, dtype=float)
    # MultiDM-01-like raster: fill row-major skipping 4 corners of outer ring
    # for visibility; exact USB mapping stays on the BMC SDK / flat map.
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


class DemoDm:
    """In-process 140-act stand-in when no plico server is running."""

    def __init__(self):
        self._shape = np.zeros(N_ACT)

    def getNumberOfActuators(self):
        return N_ACT

    def get_number_of_actuators(self):
        return self.getNumberOfActuators()

    def getShape(self):
        return self._shape.copy()

    def get_shape(self):
        return self.getShape()

    def setShape(self, shape):
        shape = np.asarray(shape, dtype=float).ravel()
        assert shape.size == N_ACT
        self._shape = shape.copy()

    def set_shape(self, shape):
        self.setShape(shape)

    def getStatus(self):
        return type('S', (), {
            'serial_number': 'BMC-DEMO-140',
            'shape': self._shape,
        })()


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


def _n_actuators(dm):
    if hasattr(dm, 'get_number_of_actuators'):
        return int(dm.get_number_of_actuators())
    return int(dm.getNumberOfActuators())


def _get_shape(dm):
    if hasattr(dm, 'get_shape'):
        return np.asarray(dm.get_shape(), dtype=float).ravel()
    return np.asarray(dm.getShape(), dtype=float).ravel()


def _set_shape(dm, shape):
    if hasattr(dm, 'set_shape'):
        dm.set_shape(shape)
    else:
        dm.setShape(shape)


class DmPanelWindow(QMainWindow):
    def __init__(self, dm=None, host='localhost', port=7050):
        super().__init__()
        self.setWindowTitle('Prima — Drop 2 · BMC Multi-DM open loop')
        self.resize(900, 640)
        self.setStyleSheet(STYLESHEET)
        self._host = host
        self._port = port
        self._dm = dm if dm is not None else DemoDm()
        self._using_live = dm is not None and not isinstance(dm, DemoDm)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)

        left_host = QWidget()
        left = QVBoxLayout(left_host)
        left.setContentsMargins(0, 0, 0, 0)
        brand_row = QHBoxLayout()
        brand_row.setSpacing(12)
        brand_row.addWidget(make_header_logo(height=28, variant='light'))
        tag = QLabel('Drop 2 · BMC Multi-DM 5.5 µm · open-loop shapes')
        tag.setObjectName('tagline')
        brand_row.addWidget(tag)
        brand_row.addStretch(1)
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
        side.addWidget(self._build_connect())
        side.addWidget(self._build_shapes())
        side.addWidget(self._build_poke())
        side.addStretch(1)
        root.addLayout(side)

        self.setStatusBar(QStatusBar())
        self._refresh_status()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(200)
        self._on_tick()

    def _build_connect(self):
        box = QGroupBox('Connection')
        form = QFormLayout(box)
        self._mode = QComboBox()
        self._mode.addItems(['Demo (in-process)', 'Live plico_dm'])
        form.addRow('Backend', self._mode)
        btn = QPushButton('Connect / refresh')
        btn.setObjectName('primary')
        btn.clicked.connect(self._on_connect)
        form.addRow(btn)
        self._info = QLabel('%d actuators' % N_ACT)
        form.addRow('Info', self._info)
        return box

    def _build_shapes(self):
        box = QGroupBox('Open-loop shapes')
        lay = QVBoxLayout(box)
        for label, slot in (
                ('Zero', self._on_zero),
                ('Flat mid (0.5)', self._on_flat),
                ('Random ±0.05', self._on_random),
                ('Checkerboard', self._on_checker),
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
        self._poke_amp.setRange(-1.0, 1.0)
        self._poke_amp.setSingleStep(0.05)
        self._poke_amp.setValue(0.15)
        form.addRow('Actuator', self._poke_idx)
        form.addRow('Amplitude', self._poke_amp)
        b = QPushButton('Apply poke')
        b.setObjectName('primary')
        b.clicked.connect(self._on_poke)
        form.addRow(b)
        return box

    def _on_connect(self):
        if self._mode.currentIndex() == 0:
            self._dm = DemoDm()
            self._using_live = False
        else:
            try:
                import plico_dm
                self._dm = plico_dm.deformableMirror(self._host, self._port)
                n = _n_actuators(self._dm)
                if n != N_ACT:
                    self.statusBar().showMessage(
                        'warning: server reports %d acts (expected %d)' % (
                            n, N_ACT), 5000)
                self._using_live = True
            except Exception as exc:
                self._dm = DemoDm()
                self._using_live = False
                self.statusBar().showMessage('live connect failed: %s' % exc, 8000)
        self._refresh_status()
        self._on_tick()

    def _refresh_status(self):
        backend = 'live' if self._using_live else 'demo'
        try:
            n = _n_actuators(self._dm)
        except Exception:
            n = N_ACT
        self._info.setText('%s · %d actuators · %s:%d' % (
            backend, n, self._host, self._port))

    def _apply(self, shape):
        _set_shape(self._dm, np.asarray(shape, dtype=float))
        self._on_tick()

    def _on_zero(self):
        self._apply(np.zeros(N_ACT))

    def _on_flat(self):
        self._apply(np.full(N_ACT, 0.5))

    def _on_random(self):
        rng = np.random.default_rng(0)
        self._apply(rng.uniform(-0.05, 0.05, N_ACT))

    def _on_checker(self):
        cmd = np.zeros(N_ACT)
        cmd[0::2] = 0.1
        cmd[1::2] = -0.1
        self._apply(cmd)

    def _on_poke(self):
        cmd = np.zeros(N_ACT)
        cmd[int(self._poke_idx.value())] = float(self._poke_amp.value())
        self._apply(cmd)

    def _on_tick(self):
        try:
            shape = _get_shape(self._dm)
        except Exception:
            shape = np.zeros(N_ACT)
        if shape.size != N_ACT:
            shape = np.resize(shape, N_ACT)
        grid = _actuator_to_grid(shape)
        finite = grid[np.isfinite(grid)]
        if finite.size:
            lo, hi = float(finite.min()), float(finite.max())
            if lo == hi:
                lo, hi = lo - 0.01, hi + 0.01
        else:
            lo, hi = -0.1, 0.1
        self._img.setImage(np.nan_to_num(grid, nan=lo), levels=(lo, hi))
        self._minmax.setText(
            'min=%.4f  max=%.4f  rms=%.4f' % (
                float(shape.min()), float(shape.max()), float(shape.std())))


def build_app(argv=None, dm=None, host='localhost', port=7050):
    app = QApplication(argv or ['prima-dm-gui'])
    win = DmPanelWindow(dm=dm, host=host, port=port)
    win.show()
    return app, win


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    parser = argparse.ArgumentParser(description='Prima Drop 2 BMC DM panel')
    parser.add_argument('--screenshot', metavar='PATH')
    parser.add_argument('--host', default='localhost')
    parser.add_argument('--port', type=int, default=7050)
    parser.add_argument('--live', action='store_true',
                        help='Connect to plico_dm server on start')
    parser.add_argument('--platform', default=None)
    args, qt_args = parser.parse_known_args(argv)

    if args.platform:
        os.environ['QT_QPA_PLATFORM'] = args.platform
    elif args.screenshot:
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

    dm = None
    if args.live:
        try:
            import plico_dm
            dm = plico_dm.deformableMirror(args.host, args.port)
        except Exception as exc:
            print('live connect failed, using demo: %s' % exc)
            dm = None

    app, win = build_app(['prima-dm-gui'] + qt_args, dm=dm,
                         host=args.host, port=args.port)
    if args.live and dm is not None:
        win._mode.setCurrentIndex(1)
        win._using_live = True
        win._refresh_status()

    if args.screenshot:
        # Show a distinctive open-loop shape for the visibility capture
        win._on_checker()
        app.processEvents()
        for _ in range(4):
            win._on_tick()
            app.processEvents()
        ok = win.grab().save(args.screenshot)
        print('screenshot_saved=%s path=%s' % (ok, args.screenshot))
        return 0 if ok else 1

    return app.exec_()


if __name__ == '__main__':
    sys.exit(main())
