"""Drop 1 main GUI — Prisma-like PWFS metrology control surface."""
from __future__ import annotations

import sys
import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QPushButton, QDoubleSpinBox, QComboBox,
    QFormLayout, QStatusBar, QSplitter, QMessageBox, QCheckBox,
)

from prima.demo.backends import DemoCamera, DemoModulator
from prima.process_manager import ProcessManager


# Visual direction: cool slate lab console (avoid purple / cream AI defaults)
pg.setConfigOptions(imageAxisOrder='row-major', antialias=True)


class MainWindow(QMainWindow):
    def __init__(self, demo=True):
        super().__init__()
        self.setWindowTitle('Prima — Drop 1 · PWFS metrology')
        self.resize(1280, 800)
        self.setStyleSheet(self._stylesheet())

        self._demo = demo
        self._camera = DemoCamera()
        self._modulator = DemoModulator()
        self._pm = ProcessManager(profile='sim')
        self._live_camera = None
        self._live_modulator = None
        self._sync_freqs = []
        self._sync_beats = []

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter)

        left = QWidget()
        left_l = QVBoxLayout(left)
        left_l.setSpacing(10)
        left_l.addWidget(self._build_brand())
        left_l.addWidget(self._build_servers())
        left_l.addWidget(self._build_camera())
        left_l.addWidget(self._build_modulator())
        left_l.addStretch(1)

        right = QWidget()
        right_l = QVBoxLayout(right)
        right_l.addWidget(self._build_frame_view(), stretch=3)
        right_l.addWidget(self._build_sync_tool(), stretch=2)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([380, 900])

        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage('Demo backends active — no hardware required')

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(50)
        self._sync_mod_to_camera()

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
        QDoubleSpinBox, QComboBox {
            background: #151c24;
            border: 1px solid #3a4a5c;
            padding: 4px;
            color: #e6edf3;
        }
        QLabel#brand {
            font-family: "IBM Plex Serif", "Source Serif 4", "DejaVu Serif", serif;
            font-size: 28px;
            font-weight: 600;
            color: #f0f6fc;
        }
        QLabel#tagline { color: #8b9cb3; font-size: 12px; }
        QLabel#matchOk { color: #7dd3c0; font-weight: 600; }
        QLabel#matchBad { color: #f0a060; font-weight: 600; }
        QStatusBar { background: #0b1015; color: #8b9cb3; }
        """

    def _build_brand(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        brand = QLabel('Prima')
        brand.setObjectName('brand')
        tag = QLabel('Drop 1 · PWFS absolute optical metrology')
        tag.setObjectName('tagline')
        l.addWidget(brand)
        l.addWidget(tag)
        return w

    def _build_servers(self):
        box = QGroupBox('1 · plico servers')
        lay = QVBoxLayout(box)
        row = QHBoxLayout()
        self._profile = QComboBox()
        self._profile.addItems(['sim (laptop)', 'lab (Manta+E-518)'])
        self._btn_start = QPushButton('Start servers')
        self._btn_start.setObjectName('primary')
        self._btn_stop = QPushButton('Stop')
        self._btn_start.clicked.connect(self._on_start_servers)
        self._btn_stop.clicked.connect(self._on_stop_servers)
        row.addWidget(self._profile)
        row.addWidget(self._btn_start)
        row.addWidget(self._btn_stop)
        lay.addLayout(row)
        self._server_status = QLabel('Mode: in-process demo (no subprocesses)')
        lay.addWidget(self._server_status)
        hint = QLabel('Start uses conf under prima/conf/. Demo frames work without Start.')
        hint.setWordWrap(True)
        hint.setStyleSheet('color:#6b7c90; font-size:11px;')
        lay.addWidget(hint)
        return box

    def _build_camera(self):
        box = QGroupBox('2 · Manta / WFS camera')
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
        self._lock_exp = QCheckBox('Lock exposure = 1 / f_mod')
        self._lock_exp.setChecked(True)
        self._lock_exp.stateChanged.connect(self._on_lock_toggled)
        form.addRow('Exposure', self._exp_spin)
        form.addRow('Frame rate (≈)', self._fps_label)
        form.addRow('Frame period', self._period_label)
        form.addRow('vs modulation', self._match_label)
        form.addRow(self._lock_exp)
        return box

    def _build_modulator(self):
        box = QGroupBox('3 · PWFS modulator')
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
            s.setValue(0.0)
        self._freq_spin.valueChanged.connect(self._on_mod_changed)
        self._radius_spin.valueChanged.connect(self._on_mod_changed)
        self._cx_spin.valueChanged.connect(self._on_mod_changed)
        self._cy_spin.valueChanged.connect(self._on_mod_changed)
        self._btn_apply_mod = QPushButton('Apply modulator')
        self._btn_apply_mod.setObjectName('primary')
        self._btn_apply_mod.clicked.connect(self._apply_modulator)
        form.addRow('Frequency', self._freq_spin)
        form.addRow('Radius', self._radius_spin)
        form.addRow('Center X', self._cx_spin)
        form.addRow('Center Y', self._cy_spin)
        form.addRow(self._btn_apply_mod)
        self._mod_period_label = QLabel('1/f = 50.00 ms')
        form.addRow('Modulation period', self._mod_period_label)
        return box

    def _build_frame_view(self):
        box = QGroupBox('Live WFS frame')
        lay = QVBoxLayout(box)
        self._img = pg.ImageView(view=pg.PlotItem())
        self._img.ui.roiBtn.hide()
        self._img.ui.menuBtn.hide()
        self._img.ui.histogram.hide()
        try:
            view = self._img.getView()
            view.setAspectLocked(True)
            view.invertY(True)
            view.hideAxis('left')
            view.hideAxis('bottom')
        except Exception:
            pass
        lay.addWidget(self._img)
        self._frame_info = QLabel('frame —')
        self._frame_info.setStyleSheet('color:#8b9cb3;')
        lay.addWidget(self._frame_info)
        return box

    def _build_sync_tool(self):
        box = QGroupBox('4 · Sync tool — exposure ↔ modulation beat')
        lay = QVBoxLayout(box)
        row = QHBoxLayout()
        self._btn_sync = QPushButton('Run beat sweep')
        self._btn_sync.setObjectName('primary')
        self._btn_sync.clicked.connect(self._run_sync_sweep)
        self._btn_match = QPushButton('Apply best match')
        self._btn_match.clicked.connect(self._apply_best_match)
        row.addWidget(self._btn_sync)
        row.addWidget(self._btn_match)
        lay.addLayout(row)
        explain = QLabel(
            'Sweeps f_mod while holding exposure; beat amplitude rises when '
            't_exp ≠ 1/f_mod. Distinguishes exposure from frame period (readout).')
        explain.setWordWrap(True)
        explain.setStyleSheet('color:#6b7c90; font-size:11px;')
        lay.addWidget(explain)
        self._sync_plot = pg.PlotWidget()
        self._sync_plot.setBackground('#151c24')
        self._sync_plot.showGrid(x=True, y=True, alpha=0.2)
        self._sync_plot.setLabel('bottom', 'f_mod (Hz)')
        self._sync_plot.setLabel('left', 'beat amplitude (sinc residual)')
        self._sync_plot.getPlotItem().getAxis('bottom').enableAutoSIPrefix(False)
        self._sync_curve = self._sync_plot.plot(
            pen=pg.mkPen('#7dd3c0', width=2))
        self._sync_best = pg.InfiniteLine(
            angle=90, pen=pg.mkPen('#f0a060', width=1.5, style=Qt.DashLine))
        self._sync_plot.addItem(self._sync_best)
        lay.addWidget(self._sync_plot)
        self._sync_result = QLabel('No sweep yet.')
        lay.addWidget(self._sync_result)
        return box

    # --- actions ---

    def _on_start_servers(self):
        profile = 'lab' if self._profile.currentIndex() == 1 else 'sim'
        self._pm.profile = profile
        try:
            st = self._pm.start()
            self._server_status.setText(
                'camera running=%s  modulator running=%s' % (
                    st.get('camera', {}).get('running'),
                    st.get('modulator', {}).get('running')))
            self._status.showMessage(
                'Started plico servers (%s) — still showing demo frames until live clients wired' % profile)
        except FileNotFoundError as e:
            QMessageBox.warning(self, 'Start failed', str(e))
        except Exception as e:
            QMessageBox.warning(
                self, 'Start failed',
                'Could not start servers (%s). Demo backends remain active.' % e)

    def _on_stop_servers(self):
        st = self._pm.stop()
        self._server_status.setText('Stopped. %s' % st)
        self._status.showMessage('Servers stopped — demo backends active')

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
            'Modulator applied: f=%.2f Hz  R=%.3f mrad' % (
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
            '%.2f ms  (exp %.2f + readout %.2f)' % (
                period, exp, period - exp))
        if rel < 0.02:
            self._match_label.setText('MATCH · t_exp ≈ 1/f_mod')
            self._match_label.setObjectName('matchOk')
        else:
            self._match_label.setText(
                'MISMATCH · want %.2f ms (Δ %.1f%%)' % (want, 100 * rel))
            self._match_label.setObjectName('matchBad')
        # refresh style
        self._match_label.style().unpolish(self._match_label)
        self._match_label.style().polish(self._match_label)

    def _on_tick(self):
        frame = self._camera.getFrameForDisplay()
        self._img.setImage(frame, autoLevels=False, levels=(0, 255))
        self._frame_info.setText(
            'shape %s · demo frame' % (frame.shape,))
        self._update_timing_labels()

    def _run_sync_sweep(self):
        """Hold exposure, sweep f_mod, measure tip/tilt beat amplitude."""
        exp = self._exp_spin.value()
        self._camera.setExposureTime(exp)
        freqs = np.linspace(5.0, 40.0, 71)
        beats = [self._camera.beatAmplitude(f, exp) for f in freqs]
        self._sync_freqs = freqs.tolist()
        self._sync_beats = beats
        self._sync_curve.setData(freqs, beats)
        best_i = int(np.argmin(beats))
        best_f = float(freqs[best_i])
        self._best_freq = best_f
        self._sync_best.setValue(best_f)
        want_f = 1000.0 / exp
        self._sync_result.setText(
            'Held t_exp=%.2f ms → ideal f=%.2f Hz. '
            'Min beat at f=%.2f Hz (apply to match exposure).' % (
                exp, want_f, best_f))
        self._status.showMessage('Beat sweep complete')

    def _apply_best_match(self):
        if not hasattr(self, '_best_freq'):
            QMessageBox.information(self, 'Sync', 'Run beat sweep first.')
            return
        self._freq_spin.setValue(self._best_freq)
        self._lock_exp.setChecked(True)
        self._apply_exp_from_freq()
        self._apply_modulator()
        self._status.showMessage(
            'Applied matched pair f=%.2f Hz, t_exp=%.2f ms' % (
                self._best_freq, self._exp_spin.value()))

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
