"""Drop 1 main GUI — Prisma-like WFS viewer + system_gui metrology."""
from __future__ import annotations

import sys
import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QPushButton, QDoubleSpinBox,
    QFormLayout, QStatusBar, QMessageBox, QCheckBox, QSpinBox,
    QSizePolicy, QButtonGroup, QRadioButton, QScrollArea,
    QGraphicsEllipseItem,
)

from prima.gui.branding import build_brand_row, install_watermark
from prima.gui.sync_dialog import SyncDialog
from prima.gui.live_clients import try_connect_live, demo_pair
from prima.gui.metrology_views import MetrologyViews
from prima.demo.backends import DemoModulator, DemoCamera
from prima.metrology.engine import (
    MetrologyEngine, MODULATION_GAIN_PRESETS_MRAD)
from prima.metrology.types.mask import CircularMask
from prima.hardware import MAX_SAFE_RADIUS_MRAD


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
        self._circles = []
        self._labels = []
        self._roi_offset = (0, 0)  # x0, y0 of displayed crop

    def set_roi_offset(self, x0, y0):
        self._roi_offset = (int(x0), int(y0))

    def set_frame(self, frame: np.ndarray):
        self._img.setImage(frame, autoLevels=False, levels=(0, 255))
        h, w = frame.shape[:2]
        self._vb.setRange(xRange=(0, w), yRange=(0, h), padding=0.02)

    def clear_pupils(self):
        for item in self._circles + self._labels:
            self._vb.removeItem(item)
        self._circles = []
        self._labels = []

    def set_pupils(self, centers_yx, radius, names=None,
                   show_circles=True, show_names=True):
        self.clear_pupils()
        if centers_yx is None:
            return
        names = names or ['A', 'B', 'C', 'D']
        x0, y0 = self._roi_offset
        pen = pg.mkPen(QColor('#f07070'), width=2)
        for i, cyx in enumerate(np.asarray(centers_yx)):
            # geometry is [row, col] = [y, x]
            y, x = float(cyx[0]) - y0, float(cyx[1]) - x0
            if show_circles:
                circ = QGraphicsEllipseItem(
                    x - radius, y - radius, 2 * radius, 2 * radius)
                circ.setPen(pen)
                circ.setBrush(pg.mkBrush(0, 0, 0, 0))
                self._vb.addItem(circ)
                self._circles.append(circ)
            if show_names and i < len(names):
                txt = pg.TextItem(names[i], color='#f07070', anchor=(0.5, 0.5))
                txt.setPos(x, y)
                self._vb.addItem(txt)
                self._labels.append(txt)


class MainWindow(QMainWindow):
    def __init__(self, demo=True):
        super().__init__()
        self.setWindowTitle('Prima — Drop 1 · PWFS metrology')
        self.resize(1480, 980)
        self.setStyleSheet(self._stylesheet())

        self._demo = demo
        self._using_live = False
        cam, mod = demo_pair(512, 512)
        self._camera = cam
        self._modulator = mod
        self._engine = MetrologyEngine(camera=cam, modulator=mod)
        self._roi = (0, 0, 512, 512)
        self._sync_dlg = None
        self._measure_enabled = False
        # Debounce hardware apply while dragging spins (safe for E-518).
        self._mod_apply_timer = QTimer(self)
        self._mod_apply_timer.setSingleShot(True)
        self._mod_apply_timer.setInterval(350)
        self._mod_apply_timer.timeout.connect(self._apply_modulator)
        self._auto_align_active = False
        self._zernike_to_remove = [2, 3]

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(10, 10, 14, 10)
        root.setSpacing(10)

        # --- center column: WFS + metrology products ---
        frame_host = QWidget()
        frame_host.setObjectName('frameHost')
        frame_col = QVBoxLayout(frame_host)
        frame_col.setContentsMargins(0, 0, 0, 0)
        frame_col.setSpacing(4)
        brand_row, _, _ = build_brand_row(
            'Drop 1 · PWFS absolute optical metrology',
            logo_height=30, variant='light')
        frame_col.addLayout(brand_row)

        self._view = IsoscaleImageView()
        self._view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._view.setMinimumHeight(360)
        frame_col.addWidget(self._view, stretch=3)

        self._frame_info = QLabel('frame —')
        self._frame_info.setObjectName('muted')
        frame_col.addWidget(self._frame_info)

        self._metro = MetrologyViews()
        self._metro.setMinimumHeight(220)
        frame_col.addWidget(self._metro, stretch=2)

        root.addWidget(frame_host, stretch=1)
        # Subtle mark in free bottom-left chrome — not over WFS center
        install_watermark(
            frame_host, variant='light', opacity=0.10,
            anchor='bottom-left', height_hint=200)

        # --- right: scrollable control strip ---
        side = QWidget()
        side.setFixedWidth(360)
        side.setMinimumWidth(360)
        side_l = QVBoxLayout(side)
        side_l.setContentsMargins(6, 0, 12, 0)
        side_l.setSpacing(8)
        side_l.addWidget(self._build_servers())
        side_l.addWidget(self._build_camera())
        side_l.addWidget(self._build_roi())
        side_l.addWidget(self._build_modulator())
        side_l.addWidget(self._build_gain_presets())
        side_l.addWidget(self._build_pupils())
        side_l.addWidget(self._build_measure())
        side_l.addWidget(self._build_mask())
        side_l.addWidget(self._build_tools())
        side_l.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedWidth(380)
        scroll.setFrameShape(scroll.NoFrame)
        scroll.setWidget(side)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        root.addWidget(scroll, stretch=0)

        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage('Demo backends · metrology engine ready')

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(50)

        self._measure_timer = QTimer(self)
        self._measure_timer.timeout.connect(self._on_measure_tick)

        self._align_timer = QTimer(self)
        self._align_timer.timeout.connect(self._on_align_tick)

        self._align_stop_timer = QTimer(self)
        self._align_stop_timer.setSingleShot(True)
        self._align_stop_timer.timeout.connect(self._auto_align_stop)

        # Throttled E-518 GCS readback (GWD is ~0.5 s — not on frame tick).
        self._mod_gcs_timer = QTimer(self)
        self._mod_gcs_timer.setInterval(1200)
        self._mod_gcs_timer.timeout.connect(self._refresh_mod_gcs_readback)
        self._mod_gcs_timer.start()

        self._sync_mod_to_camera()
        self._apply_exp_from_freq()
        self._refresh_pupil_overlay()

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
        QPushButton:checked {
            background: #3a2a18;
            border-color: #f0a060;
            color: #ffe8d0;
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
        QRadioButton { color: #c8d4e0; spacing: 4px; }
        QScrollArea { background: transparent; border: none; }
        QTableWidget {
            background: #151c24;
            gridline-color: #2a3441;
            color: #e6edf3;
            border: 1px solid #2a3441;
        }
        QHeaderView::section {
            background: #1c2834;
            color: #9fb0c3;
            border: 1px solid #2a3441;
            padding: 2px;
        }
        """

    def _build_servers(self):
        box = QGroupBox('Live hardware')
        lay = QVBoxLayout(box)
        self._btn_connect = QPushButton('Connect live')
        self._btn_connect.setObjectName('primary')
        self._btn_connect.setToolTip(
            'Manta via Aravis @192.168.30.189 + E-518 via direct GCS TCP '
            '@192.168.30.190:50000')
        self._btn_demo = QPushButton('Use demo')
        self._btn_connect.clicked.connect(self._on_connect_live)
        self._btn_demo.clicked.connect(self._on_use_demo)
        row = QHBoxLayout()
        row.addWidget(self._btn_connect)
        row.addWidget(self._btn_demo)
        lay.addLayout(row)
        self._server_status = QLabel(
            'Demo — Connect live for Aravis Manta + direct E-518 GCS')
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
        self._lock_exp.setToolTip(
            'Drop 1 rule: exposure follows frequency only. '
            'When locked, the exposure spin is disabled — '
            'change f_mod to change t_exp. Radius never touches exposure.')
        self._lock_exp.stateChanged.connect(self._on_lock_toggled)
        form.addRow('Exposure', self._exp_spin)
        form.addRow('Frame rate', self._fps_label)
        form.addRow('Frame period', self._period_label)
        form.addRow('vs 1/f_mod', self._match_label)
        form.addRow(self._lock_exp)
        self._sync_exposure_spin_enabled()
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
        self._radius_spin.setRange(0.0, float(MAX_SAFE_RADIUS_MRAD))
        self._radius_spin.setDecimals(3)
        self._radius_spin.setSuffix(' mrad')
        self._radius_spin.setValue(1.5)
        self._radius_spin.setToolTip(
            'Modulation radius (safe max %.0f mrad for S-334/E-518)'
            % MAX_SAFE_RADIUS_MRAD)
        self._cx_spin = QDoubleSpinBox()
        self._cy_spin = QDoubleSpinBox()
        for s in (self._cx_spin, self._cy_spin):
            s.setRange(-20.0, 20.0)
            s.setDecimals(3)
            s.setSuffix(' mrad')
        # Frequency alone may drive t_exp lock; radius/center must not.
        self._freq_spin.valueChanged.connect(self._on_freq_changed)
        self._radius_spin.valueChanged.connect(self._on_radius_or_center_changed)
        self._cx_spin.valueChanged.connect(self._on_radius_or_center_changed)
        self._cy_spin.valueChanged.connect(self._on_radius_or_center_changed)
        self._btn_apply_mod = QPushButton('Apply to E-518')
        self._btn_apply_mod.setObjectName('primary')
        self._btn_apply_mod.setToolTip(
            'Push radius/freq/center to direct PI GCS (E-518). '
            'Spins also auto-apply (~350 ms). Radius does not change exposure.')
        self._btn_apply_mod.clicked.connect(self._apply_modulator)
        form.addRow('Frequency', self._freq_spin)
        form.addRow('Radius', self._radius_spin)
        form.addRow('Center X', self._cx_spin)
        form.addRow('Center Y', self._cy_spin)
        form.addRow(self._btn_apply_mod)
        self._mod_period_label = QLabel('1/f = 50.00 ms')
        form.addRow('Period', self._mod_period_label)
        self._mod_live_label = QLabel('cmd R=—  C=—')
        self._mod_live_label.setObjectName('muted')
        form.addRow('Commanded', self._mod_live_label)
        self._mod_gcs_label = QLabel(
            'E-518: Vpp=—  f=—  VOL=—  WGO=—')
        self._mod_gcs_label.setObjectName('muted')
        self._mod_gcs_label.setWordWrap(True)
        self._mod_gcs_label.setToolTip(
            'Live GCS readback: wave-table Vpp (GWD), frequency from '
            'table length × controller SAMPLE_TIME, VOL?, WGO?.')
        form.addRow('E-518 live', self._mod_gcs_label)
        return box

    def _build_gain_presets(self):
        box = QGroupBox('Modulation gain [mrad]')
        lay = QHBoxLayout(box)
        self._gain_group = QButtonGroup(self)
        for i, g in enumerate(MODULATION_GAIN_PRESETS_MRAD):
            btn = QRadioButton(str(int(g) if g == int(g) else g))
            btn.setProperty('gain_mrad', g)
            self._gain_group.addButton(btn, i)
            lay.addWidget(btn)
            if abs(g - 1.0) < 1e-9:
                btn.setChecked(True)
            btn.clicked.connect(self._on_gain_preset)
        return box

    def _build_pupils(self):
        box = QGroupBox('Pupils')
        lay = QVBoxLayout(box)
        self._show_circles = QCheckBox('Show pupil circles')
        self._show_circles.setChecked(True)
        self._show_names = QCheckBox('Show pupil names')
        self._show_names.setChecked(True)
        self._show_circles.stateChanged.connect(self._refresh_pupil_overlay)
        self._show_names.stateChanged.connect(self._refresh_pupil_overlay)
        self._btn_find_pupils = QPushButton('Find pupils')
        self._btn_find_pupils.clicked.connect(self._on_find_pupils)
        self._pupil_text = QLabel('—')
        self._pupil_text.setObjectName('muted')
        self._pupil_text.setWordWrap(True)
        lay.addWidget(self._show_circles)
        lay.addWidget(self._show_names)
        lay.addWidget(self._btn_find_pupils)
        lay.addWidget(self._pupil_text)
        return box

    def _build_measure(self):
        box = QGroupBox('Metrology (system_gui)')
        lay = QVBoxLayout(box)
        row = QHBoxLayout()
        self._btn_take = QPushButton('Take Measure')
        self._btn_take.setCheckable(True)
        self._btn_take.setObjectName('primary')
        self._btn_take.clicked.connect(self._on_take_measure_toggled)
        self._btn_once = QPushButton('Once')
        self._btn_once.clicked.connect(self._on_take_once)
        self._btn_align = QPushButton('Auto Align')
        self._btn_align.clicked.connect(self._on_auto_align)
        row.addWidget(self._btn_take)
        row.addWidget(self._btn_once)
        lay.addLayout(row)
        lay.addWidget(self._btn_align)

        rem = QHBoxLayout()
        self._chk_tt = QCheckBox('Tip/Tilt')
        self._chk_tt.setChecked(True)
        self._chk_fo = QCheckBox('Focus')
        self._chk_as = QCheckBox('Astigmatism')
        for c in (self._chk_tt, self._chk_fo, self._chk_as):
            c.stateChanged.connect(self._on_zernike_remove_changed)
            rem.addWidget(c)
        lay.addLayout(rem)

        self._btn_copy_z = QPushButton('Store Coeffs >>')
        self._btn_copy_z.clicked.connect(self._metro.store_zernike_copy)
        lay.addWidget(self._btn_copy_z)

        avg_row = QHBoxLayout()
        avg_row.addWidget(QLabel('Frames avg'))
        self._frames_avg = QSpinBox()
        self._frames_avg.setRange(1, 50)
        self._frames_avg.setValue(3)
        avg_row.addWidget(self._frames_avg)
        lay.addLayout(avg_row)
        return box

    def _build_mask(self):
        box = QGroupBox('Mask')
        form = QFormLayout(box)
        self._auto_mask = QCheckBox('automatic mask')
        self._auto_mask.setChecked(True)
        self._mask_r = QSpinBox()
        self._mask_r.setRange(1, 2048)
        self._mask_r.setValue(80)
        self._mask_cx = QSpinBox()
        self._mask_cy = QSpinBox()
        for s in (self._mask_cx, self._mask_cy):
            s.setRange(0, 4096)
            s.setValue(112)
        for s in (self._mask_r, self._mask_cx, self._mask_cy):
            s.valueChanged.connect(self._on_mask_changed)
        form.addRow(self._auto_mask)
        form.addRow('Radius', self._mask_r)
        form.addRow('Center X', self._mask_cx)
        form.addRow('Center Y', self._mask_cy)
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

    # --- backends ---

    def _release_live_backends(self):
        """Drop existing Aravis / GCS owners so Connect live can reclaim them."""
        old_cam = getattr(self, '_camera', None)
        old_mod = getattr(self, '_modulator', None)
        # Swap to demo first so the tick timer never hits a half-closed device.
        demo_cam, demo_mod = demo_pair(512, 512)
        self._camera = demo_cam
        self._modulator = demo_mod
        try:
            self._engine.rebind(camera=demo_cam, modulator=demo_mod)
        except Exception:
            pass
        if old_mod is not None and hasattr(old_mod, 'close') and not isinstance(
                old_mod, DemoModulator):
            try:
                old_mod.close()
            except Exception:
                pass
        if old_cam is not None and hasattr(old_cam, 'close') and not isinstance(
                old_cam, DemoCamera):
            try:
                old_cam.close()
            except Exception:
                pass
        # Brief pause so GigE control / E-518 TCP release before reopen.
        from time import sleep
        sleep(0.35)

    def _is_live_modulator(self):
        return (
            self._modulator is not None
            and not isinstance(self._modulator, DemoModulator))

    def _on_connect_live(self):
        self._btn_connect.setEnabled(False)
        self._status.showMessage('Connecting Aravis + E-518…')
        QApplication.processEvents()
        try:
            self._release_live_backends()
            cam, mod, errors = try_connect_live()
            live_mod = None
            if mod is not None:
                try:
                    _ = mod.getStatus()
                    live_mod = mod
                except Exception as e:
                    errors.append('modulator(probe): %s' % e)
                    try:
                        mod.close()
                    except Exception:
                        pass
                    live_mod = None
            if cam is None and live_mod is None:
                QMessageBox.warning(
                    self, 'Connect failed',
                    'No live hardware.\n' + '\n'.join(errors)
                    + '\n\nExpected: Aravis Manta @192.168.30.189 and '
                      'direct PI GCS @192.168.30.190:50000.\n'
                      'Tip: close any other Drop1/Vision session, wait ~3 s, '
                      'then Connect live again.')
                self._using_live = False
                self._server_status.setText(
                    'Connect failed — ' + ('; '.join(errors) or 'no devices'))
                return
            if cam is not None:
                self._camera = cam
            if live_mod is not None:
                self._modulator = live_mod
            self._engine.rebind(
                camera=self._camera if cam else None,
                modulator=live_mod if live_mod is not None else None)
            self._using_live = True

            def _mod_name(m):
                if m is None:
                    return 'demo (not connected)'
                if isinstance(m, DemoModulator):
                    return 'demo'
                if hasattr(m, 'name') and callable(m.name):
                    try:
                        return m.name()
                    except Exception:
                        pass
                return type(m).__name__

            mod_label = _mod_name(
                live_mod if live_mod is not None else self._modulator)
            if live_mod is None:
                mod_label = 'DEMO — E-518 GCS unreachable'
            self._server_status.setText(
                'LIVE  cam=%s  mod=%s%s' % (
                    cam.name() if cam else 'demo',
                    mod_label,
                    ('\n' + '; '.join(errors)) if errors else ''))
            if live_mod is not None:
                self._pull_mod_to_spins()
                self._apply_modulator()
                self._status.showMessage(
                    'Connected — Aravis Manta + direct E-518 GCS')
            else:
                self._status.showMessage(
                    'Camera live; modulator still DEMO (E-518 GCS unreachable)')
            self._sync_exposure_spin_enabled()
            if self._lock_exp.isChecked():
                self._apply_exp_from_freq()
        finally:
            self._btn_connect.setEnabled(True)

    def _on_use_demo(self):
        self._release_live_backends()
        cam, mod = demo_pair(512, 512)
        self._camera = cam
        self._modulator = mod
        self._engine = MetrologyEngine(camera=cam, modulator=mod)
        self._using_live = False
        self._server_status.setText(
            'Demo — Connect live for Aravis Manta + direct E-518 GCS')
        self._apply_modulator()
        self._refresh_pupil_overlay()
        self._sync_exposure_spin_enabled()
        self._status.showMessage('Switched to in-process demo backends')

    def _pull_mod_to_spins(self):
        try:
            self._freq_spin.blockSignals(True)
            self._radius_spin.blockSignals(True)
            self._cx_spin.blockSignals(True)
            self._cy_spin.blockSignals(True)
            self._freq_spin.setValue(self._modulator.getFrequencyInHz())
            self._radius_spin.setValue(self._modulator.getRadiusInMilliRad())
            c = self._modulator.getCenterInMilliRad()
            self._cx_spin.setValue(float(c[0]))
            self._cy_spin.setValue(float(c[1]))
        finally:
            self._freq_spin.blockSignals(False)
            self._radius_spin.blockSignals(False)
            self._cx_spin.blockSignals(False)
            self._cy_spin.blockSignals(False)

    # --- camera / modulator ---

    def _on_exposure_changed(self, _=None):
        # When lock is on the spin is disabled; ignore stray signals.
        if self._lock_exp.isChecked():
            return
        self._camera.setExposureTime(self._exp_spin.value())
        self._engine.set_exposure_ms(self._exp_spin.value())
        self._update_timing_labels()

    def _sync_exposure_spin_enabled(self):
        locked = bool(self._lock_exp.isChecked())
        self._exp_spin.setEnabled(not locked)

    def _on_lock_toggled(self, _=None):
        self._sync_exposure_spin_enabled()
        if self._lock_exp.isChecked():
            self._apply_exp_from_freq()
        self._update_timing_labels()

    def _on_freq_changed(self, _=None):
        f = self._freq_spin.value()
        self._mod_period_label.setText('1/f = %.2f ms' % (1000.0 / max(f, 1e-6)))
        # Only frequency drives the exposure lock — never radius/center.
        if self._lock_exp.isChecked():
            self._apply_exp_from_freq()
        self._schedule_mod_apply()
        self._update_timing_labels()

    def _on_radius_or_center_changed(self, _=None):
        # Radius/center must NEVER reset exposure (even with lock checked).
        self._schedule_mod_apply()
        self._update_timing_labels()

    def _schedule_mod_apply(self):
        self._mod_apply_timer.start()

    def _on_roi_changed(self, _=None):
        self._roi = (
            self._roi_x.value(), self._roi_y.value(),
            self._roi_w.value(), self._roi_h.value())
        self._view.set_roi_offset(self._roi[0], self._roi[1])
        self._refresh_pupil_overlay()

    def _apply_exp_from_freq(self):
        f = max(self._freq_spin.value(), 1e-6)
        exp_ms = 1000.0 / f
        self._exp_spin.blockSignals(True)
        self._exp_spin.setValue(exp_ms)
        self._exp_spin.blockSignals(False)
        # Camera only — do not call engine.set_exposure_ms here (it would
        # re-set modulator frequency and fight spinning widgets).
        self._camera.setExposureTime(exp_ms)

    def _apply_modulator(self):
        try:
            self._engine.set_modulation_frequency_hz(self._freq_spin.value())
            self._engine.set_modulation_radius_mrad(self._radius_spin.value())
            self._engine.set_modulation_center_mrad(
                [self._cx_spin.value(), self._cy_spin.value()])
            self._sync_mod_to_camera()
            self._last_mod_error = None
            if self._is_live_modulator():
                self._status.showMessage(
                    'E-518 modulator: f=%.2f Hz  R=%.3f mrad' % (
                        self._freq_spin.value(), self._radius_spin.value()))
            else:
                self._status.showMessage(
                    'Demo modulator only (f=%.2f Hz R=%.3f) — '
                    'Connect live for E-518' % (
                        self._freq_spin.value(), self._radius_spin.value()))
        except Exception as e:
            msg = str(e)
            # Debounce identical refuse dialogs (spin/timer used to spam and
            # block further radius changes while the modal was up).
            if getattr(self, '_last_mod_error', None) == msg:
                self._status.showMessage('Modulator apply failed: %s' % msg)
                return
            self._last_mod_error = msg
            self._status.showMessage('Modulator apply failed: %s' % msg)
            QMessageBox.warning(
                self, 'Modulator apply failed',
                'Could not push modulation to backend:\n%s' % e)

    def _sync_mod_to_camera(self):
        if hasattr(self._camera, 'set_modulation'):
            self._camera.set_modulation(
                self._freq_spin.value(),
                self._radius_spin.value(),
                [self._cx_spin.value(), self._cy_spin.value()])

    def _on_gain_preset(self):
        btn = self._gain_group.checkedButton()
        if btn is None:
            return
        g = float(btn.property('gain_mrad'))
        # setValue triggers _on_radius_or_center_changed → apply; avoid double.
        self._radius_spin.blockSignals(True)
        self._radius_spin.setValue(g)
        self._radius_spin.blockSignals(False)
        self._apply_modulator()
        self._status.showMessage('Modulation gain preset %.3g mrad' % g)

    def _update_timing_labels(self):
        fps = self._camera.getFrameRate()
        period = self._camera.framePeriodMs()
        exp = self._camera.exposureTime()
        f = max(self._freq_spin.value(), 1e-6)
        want = 1000.0 / f
        rel = abs(exp - want) / want
        self._fps_label.setText('%.1f Hz' % fps)
        self._period_label.setText(
            '%.1f ms (exp+%.0f readout)' % (period, max(0.0, period - exp)))
        if rel < 0.02:
            self._match_label.setText('MATCH')
            self._match_label.setObjectName('matchOk')
        else:
            self._match_label.setText('MISMATCH Δ%.0f%%' % (100 * rel))
            self._match_label.setObjectName('matchBad')
        self._match_label.style().unpolish(self._match_label)
        self._match_label.style().polish(self._match_label)
        try:
            c = self._modulator.getCenterInMilliRad()
            self._mod_live_label.setText(
                'cmd R=%.2f mrad  f=%.2f Hz  C=%.2f,%.2f' % (
                    self._modulator.getRadiusInMilliRad(),
                    self._modulator.getFrequencyInHz(),
                    c[0], c[1]))
        except Exception:
            pass

    def _refresh_mod_gcs_readback(self):
        """Poll E-518 for Vpp / frequency / VOL / WGO (direct GCS only)."""
        mod = getattr(self, '_modulator', None)
        if mod is None or isinstance(mod, DemoModulator):
            self._mod_gcs_label.setText(
                'E-518: (demo — Connect live for GCS Vpp / f)')
            return
        if not hasattr(mod, 'getControllerReadback'):
            self._mod_gcs_label.setText('E-518: (no GCS readback API)')
            return
        try:
            # Refresh wave-table Vpp/freq from GWD when modulating.
            if hasattr(mod, 'refresh_wave_table_readback') and getattr(
                    mod, '_modulating', False):
                try:
                    mod.refresh_wave_table_readback()
                except Exception:
                    pass
            rb = mod.getControllerReadback()
            wgo = 'ON' if rb.wavegen_running else 'OFF'
            self._mod_gcs_label.setText(
                'E-518: A=%.2f Vpp  B=%.2f Vpp  f=%.2f Hz\n'
                'VOL A=%.1f B=%.1f  WGO=%s' % (
                    rb.vpp_a, rb.vpp_b, rb.freq_hz,
                    rb.vol_a, rb.vol_b, wgo))
        except Exception as e:
            self._mod_gcs_label.setText('E-518 readback error: %s' % e)

    def _crop_roi(self, frame):
        x0, y0, w, h = self._roi
        H, W = frame.shape[:2]
        x0 = max(0, min(x0, W - 1))
        y0 = max(0, min(y0, H - 1))
        x1 = max(x0 + 1, min(x0 + w, W))
        y1 = max(y0 + 1, min(y0 + h, H))
        return frame[y0:y1, x0:x1]

    def _on_tick(self):
        try:
            frame = self._camera.getFrameForDisplay()
            if hasattr(frame, 'toNumpyArray'):
                frame = frame.toNumpyArray()
            frame = np.asarray(frame)
            if frame.dtype != np.uint8:
                a = frame.astype(np.float64)
                a = a - np.nanmin(a)
                mx = np.nanmax(a)
                if mx > 0:
                    a = a / mx
                frame = (a * 255).astype(np.uint8)
            shown = self._crop_roi(frame)
            self._view.set_frame(shown)
            mode = 'live' if self._using_live else 'demo'
            self._frame_info.setText(
                'display %s · full %s · isoscale · %s' % (
                    shown.shape, frame.shape, mode))
            self._update_timing_labels()
        except Exception as e:
            self._frame_info.setText('frame error: %s' % e)

    # --- pupils / measure ---

    def _refresh_pupil_overlay(self, _=None):
        centers = self._engine.pupil_centers()
        radius = self._engine.pupil_radius()
        self._view.set_roi_offset(self._roi[0], self._roi[1])
        self._view.set_pupils(
            centers, radius,
            show_circles=self._show_circles.isChecked(),
            show_names=self._show_names.isChecked())
        lines = []
        for i, name in enumerate(['A', 'B', 'C', 'D']):
            if i >= len(centers):
                break
            cy, cx = centers[i]
            lines.append('%s: c=%.1f,%.1f r=%.1f' % (name, cx, cy, radius))
        self._pupil_text.setText('\n'.join(lines) if lines else '—')

    def _on_find_pupils(self):
        try:
            centers, radius = self._engine.find_pupils_from_frame()
            self._refresh_pupil_overlay()
            self._status.showMessage(
                'Pupils found · r=%.1f px · %d spots' % (
                    radius, len(centers)))
        except Exception as e:
            QMessageBox.warning(self, 'Find pupils', str(e))

    def _zernike_remove_list(self):
        z = []
        if self._chk_tt.isChecked():
            z.extend([2, 3])
        if self._chk_fo.isChecked():
            z.append(4)
        if self._chk_as.isChecked():
            z.extend([5, 6])
        return z

    def _on_zernike_remove_changed(self, _=None):
        self._zernike_to_remove = self._zernike_remove_list()
        if self._engine.last_measure() is not None:
            self._refresh_products()

    def _manual_mask(self):
        return None  # applied after measure with correct pupil shape

    def _on_mask_changed(self, _=None):
        if self._auto_mask.isChecked():
            return
        meas = self._engine.last_measure()
        if meas is None:
            return
        try:
            sh = meas.pupilImage().shape
            mask = CircularMask(
                sh,
                maskRadius=self._mask_r.value(),
                maskCenter=np.array(
                    [self._mask_cy.value(), self._mask_cx.value()]))
            meas.setCircularMask(mask)
            self._refresh_products()
        except Exception as e:
            self._status.showMessage('Mask update failed: %s' % e)

    def _run_measure(self):
        remove = self._zernike_remove_list()
        auto = self._auto_mask.isChecked()
        self._engine.take_measurement(
            frames_to_average=self._frames_avg.value(),
            apply_automatic_mask=auto,
            circular_mask=None,
            remove_zernikes=remove)
        if not auto:
            meas = self._engine.last_measure()
            sh = meas.pupilImage().shape
            mask = CircularMask(
                sh,
                maskRadius=self._mask_r.value(),
                maskCenter=np.array(
                    [self._mask_cy.value(), self._mask_cx.value()]))
            meas.setCircularMask(mask)
        # sync mask spinboxes from automatic result
        try:
            m = self._engine.last_measure().circularMask()
            if m is not None and auto:
                self._mask_r.blockSignals(True)
                self._mask_cx.blockSignals(True)
                self._mask_cy.blockSignals(True)
                self._mask_r.setValue(int(round(m.radius())))
                c = m.center()
                self._mask_cy.setValue(int(round(c[0])))
                self._mask_cx.setValue(int(round(c[1])))
                self._mask_r.blockSignals(False)
                self._mask_cx.blockSignals(False)
                self._mask_cy.blockSignals(False)
        except Exception:
            pass
        self._refresh_products()
        # keep center spins in sync after measure/align side effects
        self._pull_mod_to_spins()

    def _refresh_products(self):
        products = self._engine.measurement_products(
            remove_zernikes=self._zernike_remove_list())
        self._metro.update_products(products)

    def _on_take_once(self):
        try:
            self._run_measure()
            self._status.showMessage(
                'Measure OK · RMS %.1f nm · history %d' % (
                    self._engine.measurement_products(
                        self._zernike_remove_list())['rms_nm'],
                    len(self._engine.measure_history())))
        except Exception as e:
            QMessageBox.warning(self, 'Take Measure', str(e))

    def _on_take_measure_toggled(self, checked):
        self._measure_enabled = bool(checked)
        if checked:
            self._measure_timer.start(400)
            self._status.showMessage('Take Measure continuous ON')
        else:
            self._measure_timer.stop()
            self._status.showMessage('Take Measure continuous OFF')

    def _on_measure_tick(self):
        if not self._measure_enabled or self._auto_align_active:
            return
        try:
            self._run_measure()
        except Exception as e:
            self._measure_enabled = False
            self._btn_take.setChecked(False)
            self._measure_timer.stop()
            self._status.showMessage('Measure stopped: %s' % e)

    def _on_auto_align(self):
        self._auto_align_active = True
        self._btn_align.setEnabled(False)
        was = self._measure_enabled
        self._btn_take.setEnabled(False)
        self._measure_timer.stop()
        self._engine.enable_auto_align(True)
        self._align_timer.start(350)
        self._align_stop_timer.start(8000)
        self._status.showMessage('Auto Align running (8 s)…')
        self._align_was_measuring = was

    def _on_align_tick(self):
        try:
            self._engine.take_measurement(
                frames_to_average=1,
                apply_automatic_mask=self._auto_mask.isChecked(),
                remove_zernikes=[2, 3])
            new, (tip, tilt) = self._engine.auto_align_step()
            self._cx_spin.blockSignals(True)
            self._cy_spin.blockSignals(True)
            self._cx_spin.setValue(float(new[0]))
            self._cy_spin.setValue(float(new[1]))
            self._cx_spin.blockSignals(False)
            self._cy_spin.blockSignals(False)
            self._refresh_products()
            self._status.showMessage(
                'Align tip=%.3g tilt=%.3g → C=%.3f,%.3f' % (
                    tip, tilt, new[0], new[1]))
        except Exception as e:
            self._status.showMessage('Align step failed: %s' % e)
            self._auto_align_stop()

    def _auto_align_stop(self):
        self._align_timer.stop()
        self._align_stop_timer.stop()
        self._engine.enable_auto_align(False)
        self._auto_align_active = False
        self._btn_align.setEnabled(True)
        self._btn_take.setEnabled(True)
        if getattr(self, '_align_was_measuring', False):
            self._btn_take.setChecked(True)
            self._measure_enabled = True
            self._measure_timer.start(400)
        self._status.showMessage('Auto Align done')

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
            self._timer.stop()
            self._measure_timer.stop()
            self._align_timer.stop()
            self._mod_gcs_timer.stop()
        except Exception:
            pass
        try:
            mod = getattr(self, '_modulator', None)
            if mod is not None and hasattr(mod, 'close') and not isinstance(
                    mod, DemoModulator):
                mod.close()
        except Exception:
            pass
        try:
            cam = getattr(self, '_camera', None)
            if cam is not None and hasattr(cam, 'close'):
                cam.close()
        except Exception:
            pass
        super().closeEvent(event)


def build_app(argv=None, demo=True):
    argv = argv if argv is not None else sys.argv
    app = QApplication.instance() or QApplication(argv)
    win = MainWindow(demo=demo)
    win.show()
    return app, win
