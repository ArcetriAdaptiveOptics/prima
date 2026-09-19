"""Drop 1 main GUI — Prisma-like layout: large isoscale WFS frame + side panel."""
from __future__ import annotations

import sys
import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QPushButton, QDoubleSpinBox, QComboBox,
    QFormLayout, QStatusBar, QMessageBox, QCheckBox, QSpinBox,
    QSizePolicy,
)

from prima.demo.backends import DemoCamera, DemoModulator
from prima.process_manager import ProcessManager
from prima.gui.sync_dialog import SyncDialog


pg.setConfigOptions(imageAxisOrder='row-major', antialias=True)


class IsoscaleImageView(pg.GraphicsLayoutWidget):
    """Full-bleed frame viewer that always keeps pixel aspect = 1."""

    def __init__(self):
        super().__init__()
        self.setBackground('#0b1015')
        self._vb = self.addViewBox(lockAspect=True, invertY=True, enableMenu=False)
        self._vb.setAspectLocked(True, ratio=1.0)
        self._img = pg.ImageItem(axisOrder='row-major')
        self._vb.addItem(self._img)
        self._vb.setBorder(pg.mkPen('#2a3441'))

    def set_frame(self, frame: np.ndarray):
        self._img.setImage(frame, autoLevels=False, levels=(0, 255))
        h, w = frame.shape[:2]
        self._vb.setRange(xRange=(0, w), yRange=(0, h), padding=0.02)


class MainWindow(QMainWindow):
    def __init__(self, demo=True):
        super().__init__()
        self.setWindowTitle('Prima — Drop 1 · PWFS metrology')
        self.resize(1400, 860)
        self.setStyleSheet(self._stylesheet())

        self._demo = demo
        self._camera = DemoCamera(rows=512, cols=512)
        self._modulator = DemoModulator()
        self._pm = ProcessManager(profile='sim')
        self._roi = (0, 0, 512, 512)  # x0, y0, w, h in unbinned demo pixels
        self._sync_dlg = None

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # --- center: dominant isoscale WFS frame (Prisma-style) ---
        frame_col = QVBoxLayout()
        frame_col.setSpacing(4)
        brand_row = QHBoxLayout()
        brand = QLabel('Prima')
        brand.setObjectName('brand')
        tag = QLabel('Drop 1 · PWFS absolute optical metrology')
        tag.setObjectName('tagline')
        brand_row.addWidget(brand)
        brand_row.addWidget(tag)
        brand_row.addStretch(1)
        frame_col.addLayout(brand_row)

        self._view = IsoscaleImageView()
        self._view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        frame_col.addWidget(self._view, stretch=1)

        self._frame_info = QLabel('frame —')
        self._frame_info.setObjectName('muted')
        frame_col.addWidget(self._frame_info)

        root.addLayout(frame_col, stretch=1)

        # --- right: narrow control strip (like Prisma info panel) ---
        side = QWidget()
        side.setFixedWidth(340)
        side_l = QVBoxLayout(side)
        side_l.setContentsMargins(0, 0, 0, 0)
        side_l.setSpacing(8)
        side_l.addWidget(self._build_servers())
        side_l.addWidget(self._build_camera())
        side_l.addWidget(self._build_roi())
        side_l.addWidget(self._build_modulator())
        side_l.addWidget(self._build_pupils_stub())
        side_l.addWidget(self._build_tools())
        side_l.addStretch(1)
        root.addWidget(side, stretch=0)

        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage(
            'Demo backends — not yet Prisma system_gui parity (see gap list)')

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(50)
        self._sync_mod_to_camera()
        self._apply_exp_from_freq()

    def _stylesheet(self):
        return """
        QMainWindow, QWidget {
            background-color: #0f1419;
            color: #e6edf3;
            font-family: "IBM Plex Sans", "Source Sans 3", "DejaVu Sans", sans-serif;
            font-size: 13px;
        }
        QGroupBox {
            border: 1px solid #2a3441;
            margin-top: 12px;
            padding-top: 10px;
            font-weight: 600;
            color: #9fb0c3;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 8px;
            padding: 0 4px;
            color: #7dd3c0;
        }
        QPushButton {
            background: #1c2834;
            border: 1px solid #3a4a5c;
            padding: 6px 12px;
            color: #e6edf3;
        }
        QPushButton:hover { background: #243447; border-color: #7dd3c0; }
        QPushButton#primary {
            background: #1a4d45;
            border-color: #7dd3c0;
            color: #e8fff8;
            font-weight: 600;
        }
        QDoubleSpinBox, QSpinBox, QComboBox {
            background: #151c24;
            border: 1px solid #3a4a5c;
            padding: 3px;
            color: #e6edf3;
        }
        QLabel#brand {
            font-family: "IBM Plex Serif", "Source Serif 4", "DejaVu Serif", serif;
            font-size: 26px;
            font-weight: 600;
            color: #f0f6fc;
        }
        QLabel#tagline { color: #8b9cb3; font-size: 12px; }
        QLabel#muted { color: #6b7c90; font-size: 11px; }
        QLabel#matchOk { color: #7dd3c0; font-weight: 600; }
        QLabel#matchBad { color: #f0a060; font-weight: 600; }
        QStatusBar { background: #0b1015; color: #8b9cb3; }
        """

    def _build_servers(self):
        box = QGroupBox('plico servers')
        lay = QVBoxLayout(box)
        self._profile = QComboBox()
        self._profile.addItems(['sim (laptop)', 'lab (Manta+E-518)'])
        row = QHBoxLayout()
        self._btn_start = QPushButton('Start')
        self._btn_start.setObjectName('primary')
        self._btn_stop = QPushButton('Stop')
        self._btn_start.clicked.connect(self._on_start_servers)
        self._btn_stop.clicked.connect(self._on_stop_servers)
        row.addWidget(self._btn_start)
        row.addWidget(self._btn_stop)
        lay.addWidget(self._profile)
        lay.addLayout(row)
        self._server_status = QLabel('Demo (in-process)')
        self._server_status.setObjectName('muted')
        self._server_status.setWordWrap(True)
        lay.addWidget(self._server_status)
        return box

    def _build_camera(self):
        box = QGroupBox('Manta / WFS timing')
        form = QFormLayout(box)
        self._exp_spin = QDoubleSpinBox()
        self._exp_spin.setRange(0.1, 5000.0)
        self._exp_spin.setDecimals(2)
        self._exp_spin.setSuffix(' ms')
        self._exp_spin.setValue(50.0)
        self._exp_spin.valueChanged.connect(self._on_exposure_changed)
        self._fps_label = QLabel('—')
        self._period_label = QLabel('—')
        self._match_label = QLabel('—')
        self._lock_exp = QCheckBox('Lock t_exp = 1/f_mod')
        self._lock_exp.setChecked(True)
        self._lock_exp.stateChanged.connect(self._on_lock_toggled)
        form.addRow('Exposure', self._exp_spin)
        form.addRow('Frame rate', self._fps_label)
        form.addRow('Frame period', self._period_label)
        form.addRow('vs 1/f_mod', self._match_label)
        form.addRow(self._lock_exp)
        return box

    def _build_roi(self):
        box = QGroupBox('ROI (display crop)')
        form = QFormLayout(box)
        self._roi_x = QSpinBox(); self._roi_y = QSpinBox()
        self._roi_w = QSpinBox(); self._roi_h = QSpinBox()
        for s in (self._roi_x, self._roi_y):
            s.setRange(0, 4096)
        for s in (self._roi_w, self._roi_h):
            s.setRange(32, 4096)
            s.setValue(512)
        for s in (self._roi_x, self._roi_y, self._roi_w, self._roi_h):
            s.valueChanged.connect(self._on_roi_changed)
        form.addRow('X0', self._roi_x)
        form.addRow('Y0', self._roi_y)
        form.addRow('Width', self._roi_w)
        form.addRow('Height', self._roi_h)
        note = QLabel('Applied on displayed frame; keep isoscale.')
        note.setObjectName('muted')
        note.setWordWrap(True)
        form.addRow(note)
        return box

    def _build_modulator(self):
        box = QGroupBox('PWFS modulator')
        form = QFormLayout(box)
        self._freq_spin = QDoubleSpinBox()
        self._freq_spin.setRange(0.1, 500.0)
        self._freq_spin.setDecimals(2)
        self._freq_spin.setSuffix(' Hz')
        self._freq_spin.setValue(20.0)
        self._radius_spin = QDoubleSpinBox()
        self._radius_spin.setRange(0.0, 50.0)
        self._radius_spin.setDecimals(3)
        self._radius_spin.setSuffix(' mrad')
        self._radius_spin.setValue(1.5)
        self._cx_spin = QDoubleSpinBox()
        self._cy_spin = QDoubleSpinBox()
        for s in (self._cx_spin, self._cy_spin):
            s.setRange(-20.0, 20.0)
            s.setDecimals(3)
            s.setSuffix(' mrad')
        self._freq_spin.valueChanged.connect(self._on_mod_changed)
        self._radius_spin.valueChanged.connect(self._on_mod_changed)
        self._cx_spin.valueChanged.connect(self._on_mod_changed)
        self._cy_spin.valueChanged.connect(self._on_mod_changed)
        self._btn_apply_mod = QPushButton('Apply')
        self._btn_apply_mod.setObjectName('primary')
        self._btn_apply_mod.clicked.connect(self._apply_modulator)
        form.addRow('Frequency', self._freq_spin)
        form.addRow('Radius', self._radius_spin)
        form.addRow('Center X', self._cx_spin)
        form.addRow('Center Y', self._cy_spin)
        form.addRow(self._btn_apply_mod)
        self._mod_period_label = QLabel('1/f = 50.00 ms')
        form.addRow('Period', self._mod_period_label)
        return box

    def _build_pupils_stub(self):
        box = QGroupBox('Pupils (Prisma overlay)')
        lay = QVBoxLayout(box)
        self._show_circles = QCheckBox('Show pupil circles')
        self._show_names = QCheckBox('Show pupil names')
        self._pupil_text = QLabel('— (pupil finder not wired yet)')
        self._pupil_text.setObjectName('muted')
        self._pupil_text.setWordWrap(True)
        lay.addWidget(self._show_circles)
        lay.addWidget(self._show_names)
        lay.addWidget(self._pupil_text)
        return box

    def _build_tools(self):
        box = QGroupBox('Tools')
        lay = QVBoxLayout(box)
        self._btn_sync = QPushButton('Sync exposure ↔ modulation…')
        self._btn_sync.clicked.connect(self._open_sync_dialog)
        note = QLabel(
            'Occasional commissioning only. Later: Drop 3 camera → LUT file.')
        note.setObjectName('muted')
        note.setWordWrap(True)
        lay.addWidget(self._btn_sync)
        lay.addWidget(note)
        return box

    # --- actions ---

    def _on_start_servers(self):
        self._pm.profile = (
            'lab' if self._profile.currentIndex() == 1 else 'sim')
        try:
            st = self._pm.start()
            self._server_status.setText(
                'cam=%s mod=%s' % (
                    st.get('camera', {}).get('running'),
                    st.get('modulator', {}).get('running')))
            self._status.showMessage('Started servers (%s)' % self._pm.profile)
        except Exception as e:
            QMessageBox.warning(
                self, 'Start failed',
                'Could not start servers (%s). Demo remains active.' % e)

    def _on_stop_servers(self):
        self._pm.stop()
        self._server_status.setText('Stopped · demo backends')
        self._status.showMessage('Servers stopped')

    def _on_exposure_changed(self, _=None):
        self._camera.setExposureTime(self._exp_spin.value())
        self._update_timing_labels()

    def _on_lock_toggled(self, _=None):
        if self._lock_exp.isChecked():
            self._apply_exp_from_freq()

    def _on_mod_changed(self, _=None):
        f = self._freq_spin.value()
        self._mod_period_label.setText('1/f = %.2f ms' % (1000.0 / f))
        if self._lock_exp.isChecked():
            self._apply_exp_from_freq()
        self._sync_mod_to_camera()
        self._update_timing_labels()

    def _on_roi_changed(self, _=None):
        self._roi = (
            self._roi_x.value(), self._roi_y.value(),
            self._roi_w.value(), self._roi_h.value())

    def _apply_exp_from_freq(self):
        f = max(self._freq_spin.value(), 1e-6)
        exp_ms = 1000.0 / f
        self._exp_spin.blockSignals(True)
        self._exp_spin.setValue(exp_ms)
        self._exp_spin.blockSignals(False)
        self._camera.setExposureTime(exp_ms)

    def _apply_modulator(self):
        self._modulator.setFrequencyInHz(self._freq_spin.value())
        self._modulator.setRadiusInMilliRad(self._radius_spin.value())
        self._modulator.setCenterInMilliRad(
            [self._cx_spin.value(), self._cy_spin.value()])
        self._sync_mod_to_camera()
        self._status.showMessage(
            'Modulator: f=%.2f Hz  R=%.3f mrad' % (
                self._freq_spin.value(), self._radius_spin.value()))

    def _sync_mod_to_camera(self):
        self._camera.set_modulation(
            self._freq_spin.value(),
            self._radius_spin.value(),
            [self._cx_spin.value(), self._cy_spin.value()])

    def _update_timing_labels(self):
        fps = self._camera.getFrameRate()
        period = self._camera.framePeriodMs()
        exp = self._camera.exposureTime()
        f = max(self._freq_spin.value(), 1e-6)
        want = 1000.0 / f
        rel = abs(exp - want) / want
        self._fps_label.setText('%.1f Hz' % fps)
        self._period_label.setText(
            '%.1f ms (exp+%.0f readout)' % (period, period - exp))
        if rel < 0.02:
            self._match_label.setText('MATCH')
            self._match_label.setObjectName('matchOk')
        else:
            self._match_label.setText('MISMATCH Δ%.0f%%' % (100 * rel))
            self._match_label.setObjectName('matchBad')
        self._match_label.style().unpolish(self._match_label)
        self._match_label.style().polish(self._match_label)

    def _crop_roi(self, frame):
        x0, y0, w, h = self._roi
        H, W = frame.shape[:2]
        x0 = max(0, min(x0, W - 1))
        y0 = max(0, min(y0, H - 1))
        x1 = max(x0 + 1, min(x0 + w, W))
        y1 = max(y0 + 1, min(y0 + h, H))
        return frame[y0:y1, x0:x1]

    def _on_tick(self):
        frame = self._camera.getFrameForDisplay()
        shown = self._crop_roi(frame)
        self._view.set_frame(shown)
        self._frame_info.setText(
            'display %s · full %s · isoscale · demo' % (
                shown.shape, frame.shape))
        self._update_timing_labels()

    def _open_sync_dialog(self):
        dlg = SyncDialog(
            self,
            camera=self._camera,
            get_exposure_ms=lambda: self._exp_spin.value(),
            apply_match_cb=self._apply_sync_match,
        )
        dlg.setStyleSheet(self.styleSheet())
        dlg.exec_()

    def _apply_sync_match(self, best_freq_hz):
        self._freq_spin.setValue(best_freq_hz)
        self._lock_exp.setChecked(True)
        self._apply_exp_from_freq()
        self._apply_modulator()
        self._status.showMessage(
            'Sync applied: f=%.2f Hz, t_exp=%.2f ms' % (
                best_freq_hz, self._exp_spin.value()))

    def closeEvent(self, event):
        try:
            self._pm.stop()
        except Exception:
            pass
        super().closeEvent(event)


def build_app(argv=None, demo=True):
    argv = argv if argv is not None else sys.argv
    app = QApplication.instance() or QApplication(argv)
    win = MainWindow(demo=demo)
    win.show()
    return app, win
