"""
DaoPrima main control GUI — structure adapted from daoEkarus ``EkarusCtrl.py``.

Talks only to SHM (``daoprima.shm_names``). Device I/O is via bridges;
RTC is ``daoprima.loop`` until daoBase replaces it.
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QPushButton, QDoubleSpinBox, QFormLayout,
    QStatusBar, QGridLayout, QSizePolicy,
)

from daoprima import shm as shm_mod
from daoprima import shm_names as N
from daoprima.create_shm import create_default_graph
from daoprima.loop import (
    SimpleIntegratorLoop, close_loop, open_loop, set_loop_gain, set_loop_leak,
)
from daoprima.bridges import CameraToShmBridge, DemoCamera, DemoDm, ShmToDmBridge


pg.setConfigOptions(imageAxisOrder='row-major', antialias=True)

STYLESHEET = """
QMainWindow, QWidget { background-color: #0b1740; color: #e8eef7; }
QLabel#brand { font-size: 22px; font-weight: 700; color: #30c0a8; }
QLabel#tagline { color: #9bb4d0; font-size: 12px; }
QGroupBox {
  border: 1px solid #1e3a66; border-radius: 4px; margin-top: 10px;
  font-weight: 600; color: #c5d6ec;
}
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
QPushButton {
  background: rgba(24, 72, 120, 0.55); color: #eaf6f2;
  border: 1px solid #30c0a8; border-radius: 4px; padding: 6px 10px;
}
QPushButton:hover { background: rgba(48, 192, 168, 0.30); }
QPushButton#danger { border-color: #e07070; }
QPushButton#primary { background: rgba(48, 192, 168, 0.25); }
QDoubleSpinBox {
  background: #0a1230; border: 1px solid #1e3a66; color: #e8eef7; padding: 2px;
}
QStatusBar { color: #9bb4d0; }
"""


def _grid_from_cmd(cmd: np.ndarray, grid=12) -> np.ndarray:
    out = np.full((grid, grid), np.nan)
    idx = 0
    for r in range(grid):
        for c in range(grid):
            if (r in (0, grid - 1)) and (c in (0, grid - 1)):
                continue
            if idx >= cmd.size:
                break
            out[r, c] = float(cmd[idx])
            idx += 1
    return out


class DaoPrimaMain(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('DaoPrima — Drop 2 · AO loop (sim)')
        self.resize(1180, 780)
        self.setStyleSheet(STYLESHEET)

        create_default_graph()
        self._loop = SimpleIntegratorLoop(target_fps=60.0)
        self._cam_bridge = CameraToShmBridge(DemoCamera((256, 256)))
        self._dm_bridge = ShmToDmBridge(DemoDm())

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)

        left = QVBoxLayout()
        brand_row = QHBoxLayout()
        brand = QLabel('DaoPrima')
        brand.setObjectName('brand')
        tag = QLabel('Drop 2 · PWFS + BMC Multi-DM · SHM ICD (daoEkarus-shaped)')
        tag.setObjectName('tagline')
        brand_row.addWidget(brand)
        brand_row.addWidget(tag)
        brand_row.addStretch(1)
        left.addLayout(brand_row)

        viewers = QHBoxLayout()
        self._wfs_plot = pg.GraphicsLayoutWidget()
        self._wfs_plot.setBackground('#0b1740')
        vb = self._wfs_plot.addViewBox(lockAspect=True, invertY=True)
        self._wfs_img = pg.ImageItem()
        vb.addItem(self._wfs_img)
        viewers.addWidget(self._wfs_plot, stretch=1)

        self._dm_plot = pg.GraphicsLayoutWidget()
        self._dm_plot.setBackground('#0b1740')
        vb2 = self._dm_plot.addViewBox(lockAspect=True, invertY=True)
        self._dm_img = pg.ImageItem()
        vb2.addItem(self._dm_img)
        cmap = pg.colormap.get('viridis')
        self._dm_img.setLookupTable(cmap.getLookupTable(nPts=256))
        viewers.addWidget(self._dm_plot, stretch=1)
        left.addLayout(viewers, stretch=1)

        self._mode_plot = pg.PlotWidget()
        self._mode_plot.setBackground('#0b1740')
        self._mode_plot.showGrid(x=True, y=True, alpha=0.2)
        self._mode_curve = self._mode_plot.plot(pen=pg.mkPen('#30c0a8', width=2))
        self._mode_plot.setLabel('left', 'mode coeff')
        self._mode_plot.setLabel('bottom', 'mode #')
        left.addWidget(self._mode_plot, stretch=0)
        root.addLayout(left, stretch=1)

        side = QVBoxLayout()
        side.addWidget(self._build_loop())
        side.addWidget(self._build_dm())
        side.addWidget(self._build_modulator())
        side.addWidget(self._build_telemetry())
        side.addStretch(1)
        root.addLayout(side)

        self.setStatusBar(QStatusBar())
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(16)  # ~60 Hz GUI tick
        self._on_tick()

    def _build_loop(self):
        box = QGroupBox('Loop control')
        form = QFormLayout(box)
        self._gain = QDoubleSpinBox()
        self._gain.setRange(0.0, 2.0)
        self._gain.setSingleStep(0.05)
        self._gain.setValue(0.3)
        self._leak = QDoubleSpinBox()
        self._leak.setRange(0.0, 1.0)
        self._leak.setSingleStep(0.01)
        self._leak.setValue(0.99)
        form.addRow('Gain', self._gain)
        form.addRow('Leak', self._leak)
        row = QHBoxLayout()
        b_close = QPushButton('Close loop')
        b_close.setObjectName('primary')
        b_close.clicked.connect(self._on_close)
        b_open = QPushButton('Open loop')
        b_open.setObjectName('danger')
        b_open.clicked.connect(self._on_open)
        row.addWidget(b_close)
        row.addWidget(b_open)
        form.addRow(row)
        apply_btn = QPushButton('Apply gain / leak')
        apply_btn.clicked.connect(self._on_apply_gains)
        form.addRow(apply_btn)
        self._loop_state = QLabel('OPEN')
        form.addRow('State', self._loop_state)
        return box

    def _build_dm(self):
        box = QGroupBox('Deformable mirror (140-act BMC)')
        lay = QVBoxLayout(box)
        zero = QPushButton('Zero command channels')
        zero.clicked.connect(self._on_zero_dm)
        mid = QPushButton('Load mid-flat → ch0')
        mid.clicked.connect(self._on_mid_flat)
        lay.addWidget(zero)
        lay.addWidget(mid)
        self._dm_rms = QLabel('rms —')
        lay.addWidget(self._dm_rms)
        return box

    def _build_modulator(self):
        box = QGroupBox('Modulator / tip-tilt (S-334)')
        form = QFormLayout(box)
        self._mod_info = QLabel('—')
        form.addRow('SHM', self._mod_info)
        note = QLabel('Drop 2: PWFS modulator · Drop 3: TT DM role')
        note.setWordWrap(True)
        form.addRow(note)
        return box

    def _build_telemetry(self):
        box = QGroupBox('Telemetry')
        form = QFormLayout(box)
        self._tel = QLabel('steps=0')
        form.addRow(self._tel)
        return box

    def _on_close(self):
        set_loop_gain(self._gain.value())
        set_loop_leak(self._leak.value())
        close_loop()

    def _on_open(self):
        open_loop()

    def _on_apply_gains(self):
        set_loop_gain(self._gain.value())
        set_loop_leak(self._leak.value())

    def _on_zero_dm(self):
        z = np.zeros(N.SHM_DM1_N_ACTUATORS, dtype=np.float32)
        for path in (
                N.SHM_DM1_CHANNEL_0, N.SHM_DM1_CHANNEL_1,
                N.SHM_DM1_CHANNEL_2, N.SHM_DM1_CHANNEL_3,
                N.SHM_DM1_CMD, N.SHM_DM1_CMD_OFFSET):
            shm_mod.shm(path).set_data(z)

    def _on_mid_flat(self):
        shm_mod.shm(N.SHM_DM1_CHANNEL_0).set_data(
            np.full(N.SHM_DM1_N_ACTUATORS, 0.5, dtype=np.float32))

    def _on_tick(self):
        self._cam_bridge.step()
        info = self._loop.step()
        self._dm_bridge.step()

        frame = shm_mod.shm(N.SHM_WFS_FRAME).get_data()
        self._wfs_img.setImage(frame, levels=(0, 255))

        cmd = np.asarray(shm_mod.shm(N.SHM_DM1_CMD).get_data(), dtype=float).ravel()
        grid = _grid_from_cmd(cmd)
        finite = grid[np.isfinite(grid)]
        if finite.size:
            lo, hi = float(finite.min()), float(finite.max())
            if lo == hi:
                lo, hi = lo - 0.01, hi + 0.01
        else:
            lo, hi = -0.1, 0.1
        self._dm_img.setImage(np.nan_to_num(grid, nan=lo), levels=(lo, hi))
        self._dm_rms.setText('cmd rms=%.4f' % float(np.std(cmd)))

        modes = np.asarray(
            shm_mod.shm(N.SHM_WFS1_RECONSTRUCTED_MODES).get_data()).ravel()
        self._mode_curve.setData(np.arange(modes.size), modes)

        mod = np.asarray(shm_mod.shm(N.SHM_MODULATOR).get_data()).ravel()
        if mod.size >= 4:
            self._mod_info.setText(
                'r=%.2f mrad  f=%.1f Hz  c=(%.2f, %.2f)' % tuple(mod[:4]))

        self._loop_state.setText('CLOSED' if info['closed'] else 'OPEN')
        self._tel.setText(
            'steps=%d  closed_steps=%d  mode_rms=%.4f  fps≈%.0f' % (
                info['steps'], self._loop._closed_steps,
                info['rms_modes'], self._loop.target_fps))
        self.statusBar().showMessage(
            'SHM backend: %s · bridges: demo camera + demo DM' % (
                'dao' if shm_mod.has_dao() else 'in-process'))


def build_app(argv=None):
    app = QApplication(argv or ['daoprima-gui'])
    win = DaoPrimaMain()
    win.show()
    return app, win


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    parser = argparse.ArgumentParser(description='DaoPrima Drop 2 main GUI')
    parser.add_argument('--screenshot', metavar='PATH')
    parser.add_argument('--close-loop', action='store_true',
                        help='Close the loop before screenshot / run')
    parser.add_argument('--platform', default=None)
    args, qt_args = parser.parse_known_args(argv)

    if args.platform:
        os.environ['QT_QPA_PLATFORM'] = args.platform
    elif args.screenshot:
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

    app, win = build_app(['daoprima-gui'] + qt_args)
    if args.close_loop:
        win._on_close()
        for _ in range(30):
            win._on_tick()
            app.processEvents()

    if args.screenshot:
        app.processEvents()
        for _ in range(10):
            win._on_tick()
            app.processEvents()
        ok = win.grab().save(args.screenshot)
        print('screenshot_saved=%s path=%s' % (ok, args.screenshot))
        return 0 if ok else 1

    return app.exec_()


if __name__ == '__main__':
    sys.exit(main())
