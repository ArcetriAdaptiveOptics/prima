"""PRIMA AO Lab — single-window control panel (daoEkarus style).

    python -m prima.aolab.gui --sim        # numerical twin, no hardware
    python -m prima.aolab.gui --hw         # real bench

Panels: WFS camera | slopes | calibration | modal reconstruction |
time history | loop control | deformable mirror | disturbance | log.
All amplitudes shown to the user are in nm of wavefront (approximate
conversion from DM units, see ``AOEngine.nm_per_unit``).
"""
from __future__ import annotations

import argparse
import sys
import time
import traceback

import numpy as np
import pyqtgraph as pg
from PyQt5 import QtCore, QtGui, QtWidgets

from prima.aolab import dm_geometry as G
from prima.aolab.engine import AOEngine, DATA_DIR

pg.setConfigOptions(imageAxisOrder='row-major', antialias=False)

STYLE = """
QWidget { background: #0f1923; color: #dfe8f1; font-size: 12px; }
QGroupBox { border: 1px solid #2f8f9d; border-radius: 6px; margin-top: 14px;
            padding-top: 6px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px;
                   color: #6fd3d3; font-size: 14px; }
QPushButton { background: #1d3446; border: 1px solid #3f6f86;
              border-radius: 4px; padding: 5px 10px; }
QPushButton:hover { border-color: #6fd3d3; }
QPushButton:disabled { color: #5a6b78; }
QPushButton#close { background: #1f6b3a; font-weight: bold; }
QPushButton#open { background: #6b2a1f; font-weight: bold; }
QDoubleSpinBox, QSpinBox, QComboBox, QLineEdit {
    background: #15222e; border: 1px solid #2f4b5e; padding: 2px; }
QProgressBar { border: 1px solid #2f4b5e; text-align: center; }
QProgressBar::chunk { background: #2f8f9d; }
QPlainTextEdit { background: #0a121a; font-family: monospace; font-size: 11px; }
QLabel#big { font-size: 20px; font-weight: bold; }
"""

CMAP = pg.colormap.get('viridis')
CMAP_DIV = pg.colormap.get('CET-D1')


def dspin(v, lo, hi, step, dec=3, suffix=''):
    w = QtWidgets.QDoubleSpinBox()
    w.setRange(lo, hi)
    w.setDecimals(dec)
    w.setSingleStep(step)
    w.setValue(v)
    if suffix:
        w.setSuffix(' ' + suffix)
    w.setKeyboardTracking(False)
    return w


def ispin(v, lo, hi):
    w = QtWidgets.QSpinBox()
    w.setRange(lo, hi)
    w.setValue(v)
    w.setKeyboardTracking(False)
    return w


def image_panel(title=None, cmap=CMAP):
    glw = pg.GraphicsLayoutWidget()
    vb = glw.addViewBox(lockAspect=True, invertY=False)
    vb.setMouseEnabled(True, True)
    img = pg.ImageItem()
    img.setColorMap(cmap)
    vb.addItem(img)
    if title:
        glw.ci.layout.setContentsMargins(2, 2, 2, 2)
    return glw, vb, img


class Bridge(QtCore.QObject):
    log = QtCore.pyqtSignal(str)
    calib_done = QtCore.pyqtSignal(bool)


class AOLabWindow(QtWidgets.QMainWindow):
    def __init__(self, engine: AOEngine, mode: str):
        super().__init__()
        self.e = engine
        self.mode = mode
        self.bridge = Bridge()
        self.bridge.log.connect(self._append_log)
        self.bridge.calib_done.connect(self._on_calib_done)
        self.e.log = lambda m: self.bridge.log.emit(m)
        self.setWindowTitle('PRIMA AO Lab  [%s]   DM: %s' % (mode.upper(), engine.dm.name))
        self.setStyleSheet(STYLE)
        self._pupil_items = []
        self._dm_channel = 'total'
        self._build()
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._refresh)
        self.timer.start(100)
        self._t_slow = 0.0
        self.resize(1800, 1050)

    # ================================================================ UI
    def _build(self):
        cw = QtWidgets.QWidget()
        self.setCentralWidget(cw)
        grid = QtWidgets.QGridLayout(cw)
        grid.setSpacing(6)
        grid.addWidget(self._box_camera(), 0, 0, 2, 1)
        grid.addWidget(self._box_wfs_ctrl(), 2, 0)
        grid.addWidget(self._box_slopes(), 0, 1)
        grid.addWidget(self._box_calib(), 1, 1, 2, 1)
        grid.addWidget(self._box_modal(), 0, 2, 1, 2)
        grid.addWidget(self._box_history(), 1, 2, 1, 2)
        grid.addWidget(self._box_loop(), 2, 2)
        grid.addWidget(self._box_dm(), 2, 3)
        grid.addWidget(self._box_dist(), 3, 2, 1, 2)
        grid.addWidget(self._box_log(), 3, 0, 1, 2)
        for c, s in enumerate((5, 5, 4, 4)):
            grid.setColumnStretch(c, s)
        for r, s in enumerate((5, 4, 4, 2)):
            grid.setRowStretch(r, s)

    # ---------------------------------------------------------- camera
    def _box_camera(self):
        box = QtWidgets.QGroupBox('WFS camera (pyramid pupils)')
        v = QtWidgets.QVBoxLayout(box)
        self.cam_glw, self.cam_vb, self.cam_img = image_panel(cmap=pg.colormap.get('inferno'))
        v.addWidget(self.cam_glw, 1)
        h = QtWidgets.QHBoxLayout()
        self.lbl_cam = QtWidgets.QLabel('-')
        self.chk_pupils = QtWidgets.QCheckBox('show pupils')
        self.chk_pupils.setChecked(True)
        self.chk_log = QtWidgets.QCheckBox('sqrt scale')
        h.addWidget(self.lbl_cam, 1)
        h.addWidget(self.chk_log)
        h.addWidget(self.chk_pupils)
        v.addLayout(h)
        return box

    def _box_wfs_ctrl(self):
        box = QtWidgets.QGroupBox('Camera && modulation')
        g = QtWidgets.QGridLayout(box)
        self.sp_exp = dspin(self.e.cam.get_exposure_ms(), 0.05, 2000, 5, 2, 'ms')
        self.sp_exp.valueChanged.connect(
            lambda v: self._safe(self.e.cam.set_exposure_ms, v))
        st = self.e.mod.state()
        self.sp_rmod = dspin(st['radius_mrad'], 0, 40, 1, 1, 'mrad')
        self.sp_fmod = dspin(st['freq_hz'], 1, 500, 5, 1, 'Hz')
        self.sp_cx = dspin(st['center'][0], -20, 20, 0.1, 2, 'mrad')
        self.sp_cy = dspin(st['center'][1], -20, 20, 0.1, 2, 'mrad')
        b_mod = QtWidgets.QPushButton('Apply modulation')
        b_mod.clicked.connect(self._on_mod)
        b_cen = QtWidgets.QPushButton('Apply centre')
        b_cen.clicked.connect(lambda: self._safe(
            self.e.mod.set_center, self.sp_cx.value(), self.sp_cy.value()))
        b_lock = QtWidgets.QPushButton('t_exp = 1/f_mod')
        b_lock.setToolTip('integrate exactly one modulation period')
        b_lock.clicked.connect(lambda: self.sp_exp.setValue(
            1000.0 / self.sp_fmod.value()))
        rows = [('Exposure', self.sp_exp, b_lock),
                ('Mod. radius', self.sp_rmod, None),
                ('Mod. frequency', self.sp_fmod, b_mod),
                ('Centre x', self.sp_cx, None),
                ('Centre y', self.sp_cy, b_cen)]
        for i, (lab, w, b) in enumerate(rows):
            g.addWidget(QtWidgets.QLabel(lab), i, 0)
            g.addWidget(w, i, 1)
            if b is not None:
                g.addWidget(b, i, 2)
        return box

    # ---------------------------------------------------------- slopes
    def _box_slopes(self):
        box = QtWidgets.QGroupBox('Slopes  (Sx | Sy | pupil intensity)')
        h = QtWidgets.QHBoxLayout(box)
        self.sl_imgs = []
        for cmap in (CMAP_DIV, CMAP_DIV, CMAP):
            glw, vb, img = image_panel(cmap=cmap)
            h.addWidget(glw)
            self.sl_imgs.append(img)
        return box

    # ------------------------------------------------------- calibration
    def _box_calib(self):
        box = QtWidgets.QGroupBox('Calibration')
        v = QtWidgets.QVBoxLayout(box)
        g = QtWidgets.QGridLayout()
        b_pup = QtWidgets.QPushButton('1. Find pupils')
        b_pup.clicked.connect(self._on_find_pupils)
        b_ref = QtWidgets.QPushButton('2. Reference = now')
        b_ref.setToolTip('slopes measured now become the zero of the loop')
        b_ref.clicked.connect(lambda: self._safe(self.e.set_reference))
        b_ref0 = QtWidgets.QPushButton('Reference = 0')
        b_ref0.setToolTip('absolute: loop drives the pyramid signals to 0')
        b_ref0.clicked.connect(lambda: self._safe(self.e.set_reference,
                                                   zero=True))
        g.addWidget(b_pup, 0, 0)
        g.addWidget(b_ref, 0, 1)
        g.addWidget(b_ref0, 0, 2)
        self.cb_basis = QtWidgets.QComboBox()
        self.cb_basis.addItems(['kl', 'zernike', 'zonal', 'hadamard'])
        self.sp_nmodes_cal = ispin(self.e.cp.n_modes, 1, 140)
        self.sp_amp = dspin(self.e.cp.amplitude * self.e.nm_per_unit,
                            1, 2000, 10, 0, 'nm')
        self.sp_navg = ispin(self.e.cp.n_avg, 1, 50)
        self.sp_settle = ispin(self.e.cp.settle, 0, 20)
        for i, (lab, w) in enumerate([('Modal basis', self.cb_basis),
                                      ('# modes', self.sp_nmodes_cal),
                                      ('Push-pull amp.', self.sp_amp),
                                      ('Frames / poke', self.sp_navg),
                                      ('Settle frames', self.sp_settle)]):
            g.addWidget(QtWidgets.QLabel(lab), 1 + i, 0)
            g.addWidget(w, 1 + i, 1)
        self.b_im = QtWidgets.QPushButton('3. Acquire IM')
        self.b_im.clicked.connect(self._on_calibrate)
        b_stop = QtWidgets.QPushButton('Stop')
        b_stop.clicked.connect(self.e.stop_calibration)
        g.addWidget(self.b_im, 1, 2)
        g.addWidget(b_stop, 2, 2)
        b_save = QtWidgets.QPushButton('Save calib')
        b_save.clicked.connect(lambda: self._safe(self.e.save))
        b_load = QtWidgets.QPushButton('Load calib...')
        b_load.clicked.connect(self._on_load)
        g.addWidget(b_save, 4, 2)
        g.addWidget(b_load, 5, 2)
        v.addLayout(g)
        self.pb = QtWidgets.QProgressBar()
        v.addWidget(self.pb)
        h = QtWidgets.QHBoxLayout()
        self.sp_nmodes = ispin(self.e.lp.n_modes, 1, 140)
        self.sp_ncut = ispin(0, 0, 139)
        b_rec = QtWidgets.QPushButton('4. Compute reconstructor')
        b_rec.clicked.connect(lambda: self._safe(
            self.e.update_reconstructor, self.sp_nmodes.value(),
            self.sp_ncut.value()))
        h.addWidget(QtWidgets.QLabel('modes'))
        h.addWidget(self.sp_nmodes)
        h.addWidget(QtWidgets.QLabel('SVD cut'))
        h.addWidget(self.sp_ncut)
        h.addWidget(b_rec)
        v.addLayout(h)
        self.svd_plot = pg.PlotWidget(title='IM: singular values / mode sensitivity')
        self.svd_plot.setLogMode(y=True)
        self.svd_plot.addLegend(offset=(-5, 5))
        self.svd_curve = self.svd_plot.plot(pen=None, symbol='o', symbolSize=4,
                                            symbolBrush='#6fd3d3', name='singular values')
        self.sens_curve = self.svd_plot.plot(pen='#e0a040', name='mode sensitivity')
        v.addWidget(self.svd_plot, 1)
        self.lbl_cal = QtWidgets.QLabel('no IM')
        v.addWidget(self.lbl_cal)
        return box

    # ----------------------------------------------------------- modal
    def _box_modal(self):
        box = QtWidgets.QGroupBox('Modal reconstruction')
        h = QtWidgets.QHBoxLayout(box)
        self.modal_plot = pg.PlotWidget()
        self.modal_plot.setLabel('bottom', 'mode #')
        self.modal_plot.setLabel('left', 'nm rms')
        self.modal_plot.addLegend(offset=(-5, 5))
        self.bar_inst = pg.BarGraphItem(x=[], height=[], width=0.8,
                                        brush='#2f8f9d')
        self.modal_plot.addItem(self.bar_inst)
        self.curve_res = self.modal_plot.plot(pen=pg.mkPen('#f0f0f0', width=2),
                                              name='residual (running rms)')
        self.curve_dist = self.modal_plot.plot(pen=pg.mkPen('#e0a040', width=2,
                                               style=QtCore.Qt.DashLine),
                                               name='DM disturbance (rms)')
        h.addWidget(self.modal_plot, 3)
        vv = QtWidgets.QVBoxLayout()
        self.chk_abs = QtWidgets.QCheckBox('|coeff| (else signed)')
        vv.addWidget(self.chk_abs)
        glw, vb, self.wf_img = image_panel(cmap=CMAP_DIV)
        vv.addWidget(QtWidgets.QLabel('reconstructed WF on DM'))
        vv.addWidget(glw, 1)
        self.lbl_wf = QtWidgets.QLabel('-')
        vv.addWidget(self.lbl_wf)
        h.addLayout(vv, 1)
        return box

    def _box_history(self):
        box = QtWidgets.QGroupBox('Time history (running mean)')
        v = QtWidgets.QVBoxLayout(box)
        h = QtWidgets.QHBoxLayout()
        h.addWidget(QtWidgets.QLabel('running mean window'))
        self.sp_win = ispin(20, 1, 2000)
        h.addWidget(self.sp_win)
        h.addWidget(QtWidgets.QLabel('frames,  history'))
        self.sp_hist = ispin(600, 50, 3000)
        h.addWidget(self.sp_hist)
        h.addStretch(1)
        self.lbl_rate = QtWidgets.QLabel('-')
        h.addWidget(self.lbl_rate)
        v.addLayout(h)
        self.hist_plot = pg.PlotWidget()
        self.hist_plot.addLegend(offset=(-5, 5))
        self.hist_plot.setLabel('bottom', 'frames ago')
        self.hist_plot.setLabel('left', 'nm rms')
        self.c_mode = self.hist_plot.plot(pen=pg.mkPen('#f0f0f0', width=2),
                                          name='reconstructed WF')
        self.c_dist = self.hist_plot.plot(pen=pg.mkPen('#e0a040', width=1),
                                          name='DM disturbance')
        self.c_cmd = self.hist_plot.plot(pen=pg.mkPen('#6fd3d3', width=1),
                                         name='loop command')
        self.hist2 = pg.ViewBox()
        self.hist_plot.scene().addItem(self.hist2)
        self.hist_plot.getAxis('right').linkToView(self.hist2)
        self.hist_plot.showAxis('right')
        self.hist_plot.getAxis('right').setLabel('slope rms', color='#d070d0')
        self.hist2.setXLink(self.hist_plot)
        self.c_slope = pg.PlotCurveItem(pen=pg.mkPen('#d070d0', width=1))
        self.hist2.addItem(self.c_slope)
        self.hist_plot.getViewBox().sigResized.connect(
            lambda: self.hist2.setGeometry(
                self.hist_plot.getViewBox().sceneBoundingRect()))
        self.c_closed = self.hist_plot.plot(
            pen=None, fillLevel=0, brush=(40, 200, 90, 60),
            name='loop closed')
        v.addWidget(self.hist_plot, 1)
        return box

    # ------------------------------------------------------------ loop
    def _box_loop(self):
        box = QtWidgets.QGroupBox('Loop control')
        g = QtWidgets.QGridLayout(box)
        self.lbl_loop = QtWidgets.QLabel('OPEN')
        self.lbl_loop.setObjectName('big')
        g.addWidget(QtWidgets.QLabel('Status'), 0, 0)
        g.addWidget(self.lbl_loop, 0, 1, 1, 2)
        self.sp_gain = dspin(self.e.lp.gain, 0, 2, 0.05, 3)
        self.sp_gain.valueChanged.connect(lambda v: setattr(self.e.lp, 'gain', v))
        self.sl_gain = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.sl_gain.setRange(0, 150)
        self.sl_gain.setValue(int(self.e.lp.gain * 100))
        self.sl_gain.valueChanged.connect(lambda v: self.sp_gain.setValue(v / 100))
        self.sp_gain.valueChanged.connect(lambda v: self.sl_gain.blockSignals(True)
                                          or self.sl_gain.setValue(int(v * 100))
                                          or self.sl_gain.blockSignals(False))
        self.sp_leak = dspin(self.e.lp.leak, 0.5, 1.0, 0.005, 3)
        self.sp_leak.valueChanged.connect(lambda v: setattr(self.e.lp, 'leak', v))
        g.addWidget(QtWidgets.QLabel('Gain'), 1, 0)
        g.addWidget(self.sp_gain, 1, 1)
        g.addWidget(self.sl_gain, 1, 2)
        g.addWidget(QtWidgets.QLabel('Leak'), 2, 0)
        g.addWidget(self.sp_leak, 2, 1)
        b_close = QtWidgets.QPushButton('CLOSE LOOP')
        b_close.setObjectName('close')
        b_close.clicked.connect(lambda: self._safe(self.e.close_loop))
        b_open = QtWidgets.QPushButton('OPEN LOOP')
        b_open.setObjectName('open')
        b_open.clicked.connect(lambda: self.e.open_loop())
        b_reset = QtWidgets.QPushButton('Reset integrator')
        b_reset.clicked.connect(self.e.reset_loop)
        g.addWidget(b_close, 3, 0, 1, 2)
        g.addWidget(b_open, 3, 2)
        g.addWidget(b_reset, 4, 0, 1, 3)
        self.lbl_sat = QtWidgets.QLabel('-')
        g.addWidget(self.lbl_sat, 5, 0, 1, 3)
        return box

    # -------------------------------------------------------------- DM
    def _box_dm(self):
        box = QtWidgets.QGroupBox('Deformable mirror (Multi-DM 140)')
        v = QtWidgets.QVBoxLayout(box)
        h = QtWidgets.QHBoxLayout()
        self.cb_dmch = QtWidgets.QComboBox()
        self.cb_dmch.addItems(['total - flat', 'loop', 'turb', 'static',
                               'calib', 'user', 'absolute'])
        h.addWidget(QtWidgets.QLabel('show'))
        h.addWidget(self.cb_dmch, 1)
        v.addLayout(h)
        glw, vb, self.dm_img = image_panel(cmap=CMAP_DIV)
        rp = 0.5 * self.e.cp.pupil_diam_mm / G.PITCH_MM   # pupil radius, pitches
        circ = QtWidgets.QGraphicsEllipseItem(6 - rp, 6 - rp, 2 * rp, 2 * rp)
        circ.setPen(pg.mkPen('#ffffff', width=1, style=QtCore.Qt.DashLine))
        vb.addItem(circ)
        vb.setRange(QtCore.QRectF(-0.5, -0.5, 13, 13), padding=0)
        vb.setMouseEnabled(False, False)
        glw.setMinimumHeight(150)
        v.addWidget(glw, 1)
        self.lbl_dm = QtWidgets.QLabel('-')
        v.addWidget(self.lbl_dm)
        g = QtWidgets.QGridLayout()
        self.sp_act = ispin(70, 0, 139)
        self.sp_pamp = dspin(100, -2000, 2000, 25, 0, 'nm')
        b_poke = QtWidgets.QPushButton('Poke act.')
        b_poke.clicked.connect(self._on_poke)
        self.sp_mode = ispin(1, 1, 139)
        b_mode = QtWidgets.QPushButton('Apply mode')
        b_mode.clicked.connect(self._on_mode)
        b_clear = QtWidgets.QPushButton('Clear user')
        b_clear.clicked.connect(lambda: self.e.set_channel('user', None))
        b_flat = QtWidgets.QPushButton('Park to flat')
        b_flat.clicked.connect(lambda: self._safe(self.e.park_dm))
        b_sflat = QtWidgets.QPushButton('Save as flat')
        b_sflat.setToolTip('current total command becomes the new flat')
        b_sflat.clicked.connect(self._on_save_flat)
        b_fflat = QtWidgets.QPushButton('Factory flat')
        b_fflat.clicked.connect(self._on_factory_flat)
        g.addWidget(QtWidgets.QLabel('actuator'), 0, 0)
        g.addWidget(self.sp_act, 0, 1)
        g.addWidget(self.sp_pamp, 0, 2)
        g.addWidget(b_poke, 0, 3)
        g.addWidget(QtWidgets.QLabel('mode #'), 1, 0)
        g.addWidget(self.sp_mode, 1, 1)
        g.addWidget(b_mode, 1, 3)
        g.addWidget(b_clear, 2, 0, 1, 2)
        g.addWidget(b_flat, 2, 2, 1, 2)
        g.addWidget(b_sflat, 3, 0, 1, 2)
        g.addWidget(b_fflat, 3, 2, 1, 2)
        v.addLayout(g)
        return box

    # ------------------------------------------------------ disturbance
    def _box_dist(self):
        box = QtWidgets.QGroupBox('Disturbance generated by the DM')
        h = QtWidgets.QHBoxLayout(box)
        g = QtWidgets.QGridLayout()
        self.chk_turb = QtWidgets.QCheckBox('Turbulence (frozen flow)')
        self.chk_turb.toggled.connect(self._on_turb)
        self.sp_trms = dspin(150, 0, 2000, 25, 0, 'nm')
        self.sp_trms.valueChanged.connect(self._on_turb)
        self.sp_wind = dspin(0.3, 0, 5, 0.05, 2, 'px/frame')
        self.sp_wind.valueChanged.connect(self._on_turb)
        b_new = QtWidgets.QPushButton('New screen')
        b_new.clicked.connect(lambda: self._on_turb(new=True))
        g.addWidget(self.chk_turb, 0, 0, 1, 2)
        g.addWidget(b_new, 0, 2)
        g.addWidget(QtWidgets.QLabel('rms'), 1, 0)
        g.addWidget(self.sp_trms, 1, 1)
        g.addWidget(QtWidgets.QLabel('wind'), 2, 0)
        g.addWidget(self.sp_wind, 2, 1)
        h.addLayout(g)
        g2 = QtWidgets.QGridLayout()
        self.zsp = {}
        for i, j in enumerate((2, 3, 4, 5, 6, 7, 8, 11)):
            sp = dspin(0, -2000, 2000, 25, 0, 'nm')
            sp.valueChanged.connect(self._on_static)
            self.zsp[j] = sp
            g2.addWidget(QtWidgets.QLabel('Z%d %s' % (j, G.ZERNIKE_NAMES[j])),
                         i // 4 * 2, i % 4)
            g2.addWidget(sp, i // 4 * 2 + 1, i % 4)
        b_zero = QtWidgets.QPushButton('Clear static')
        b_zero.clicked.connect(self._on_clear_static)
        g2.addWidget(b_zero, 0, 4, 2, 1)
        h.addLayout(g2, 1)
        return box

    def _box_log(self):
        box = QtWidgets.QGroupBox('Log')
        v = QtWidgets.QVBoxLayout(box)
        self.txt = QtWidgets.QPlainTextEdit()
        self.txt.setReadOnly(True)
        self.txt.setMaximumBlockCount(2000)
        v.addWidget(self.txt)
        return box

    # ========================================================= actions
    def _append_log(self, msg):
        self.txt.appendPlainText(time.strftime('%H:%M:%S  ') + msg)

    def _safe(self, fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except Exception as exc:
            self._append_log('ERROR: %s' % exc)
            traceback.print_exc()

    def _on_mod(self):
        self._safe(self.e.mod.set_modulation, self.sp_rmod.value(),
                   self.sp_fmod.value())
        self._append_log('modulation R=%.1f mrad f=%.1f Hz'
                         % (self.sp_rmod.value(), self.sp_fmod.value()))

    def _on_find_pupils(self):
        g = self._safe(self.e.detect_pupils)
        if g is not None:
            self._draw_pupils()

    def _draw_pupils(self):
        for it in self._pupil_items:
            self.cam_vb.removeItem(it)
        self._pupil_items = []
        g = self.e.geom
        if g is None:
            return
        ds = self._cam_ds
        for k, (cy, cx) in enumerate(g.centers):
            r = g.radius / ds
            it = QtWidgets.QGraphicsEllipseItem(cx / ds - r, cy / ds - r,
                                                2 * r, 2 * r)
            it.setPen(pg.mkPen('#40ff80', width=1))
            self.cam_vb.addItem(it)
            t = pg.TextItem(str(k), color='#40ff80')
            t.setPos(cx / ds, cy / ds)
            self.cam_vb.addItem(t)
            self._pupil_items += [it, t]

    def _on_calibrate(self):
        cp = self.e.cp
        cp.basis = self.cb_basis.currentText()
        cp.n_modes = self.sp_nmodes_cal.value()
        cp.amplitude = self.sp_amp.value() / self.e.nm_per_unit
        cp.n_avg = self.sp_navg.value()
        cp.settle = self.sp_settle.value()
        self.b_im.setEnabled(False)
        self._safe(self.e.start_calibration,
                   lambda ok: self.bridge.calib_done.emit(ok))
        if not self.e.calibrating:
            self.b_im.setEnabled(True)

    def _on_calib_done(self, ok):
        self.b_im.setEnabled(True)
        if ok and self.e.imat is not None:
            self.sp_nmodes.setMaximum(self.e.imat.n_modes)
            self.sp_nmodes.setValue(self.e.rec.n_modes)
            self._update_svd_plot()

    def _update_svd_plot(self):
        if self.e.rec is None:
            return
        sv = self.e.rec.singular_values
        self.svd_curve.setData(np.arange(sv.size), sv)
        sens = self.e.imat.sensitivity()
        self.sens_curve.setData(np.arange(sens.size), sens)
        im = self.e.imat
        self.lbl_cal.setText(
            'IM %s  %d modes  amp %.0f nm  | REC %d modes, %d SVD kept, '
            'cond %.1f' % (im.basis, im.n_modes, im.amplitude * self.e.nm_per_unit,
                           self.e.rec.n_modes, self.e.rec.n_kept,
                           sv[0] / sv[-1]))

    def _on_load(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(
            self, 'calibration folder', str(DATA_DIR))
        if d:
            self._safe(self.e.load, d)
            self._draw_pupils()
            self._update_svd_plot()

    def _on_poke(self):
        v = np.zeros(G.N_ACT)
        v[self.sp_act.value()] = self.sp_pamp.value() / self.e.nm_per_unit
        self.e.set_channel('user', self.e.ch['user'] + v)

    def _on_mode(self):
        try:
            B = (self.e.rec.m2c if self.e.rec is not None else self.e.basis())
            k = self.sp_mode.value() - 1
            if k >= B.shape[1]:
                raise ValueError('mode %d > %d' % (k + 1, B.shape[1]))
            v = B[:, k] * self.sp_pamp.value() / self.e.nm_per_unit
            self.e.set_channel('user', v)
        except Exception as exc:
            self._append_log('ERROR: %s' % exc)

    def _on_save_flat(self):
        from prima.aolab.devices.hw import save_user_flat
        flat = self.e.flat_from_current()
        r = QtWidgets.QMessageBox.question(
            self, 'Save flat', 'Use the current DM command as the new flat?\n'
            '(all channels are folded into the flat and reset)')
        if r != QtWidgets.QMessageBox.Yes:
            return
        if self.mode == 'hw':
            p = save_user_flat(flat)
            self._append_log('flat saved to %s' % p)
        self.e.open_loop()
        for k in list(self.e.ch):
            self.e.ch[k] = np.zeros(G.N_ACT)
        self.e.set_flat(flat)

    def _on_factory_flat(self):
        from prima.aolab.devices.hw import FACTORY_FLAT, load_flat
        self.e.open_loop(reset=True)
        self.e.set_flat(load_flat(FACTORY_FLAT))
        self._append_log('factory flat loaded')

    def _on_turb(self, *_, new=False):
        on = self.chk_turb.isChecked()
        self._safe(self.e.set_turbulence, on,
                   rms=self.sp_trms.value() / self.e.nm_per_unit,
                   wind=self.sp_wind.value(),
                   seed=int(time.time()) % 1000 if new else None)

    def _on_static(self, *_):
        self.e.set_static({j: sp.value() / self.e.nm_per_unit
                           for j, sp in self.zsp.items()})

    def _on_clear_static(self):
        for sp in self.zsp.values():
            sp.blockSignals(True)
            sp.setValue(0)
            sp.blockSignals(False)
        self._on_static()

    # ========================================================= refresh
    _cam_ds = 1

    def _refresh(self):
        e = self.e
        try:
            self._refresh_camera()
            self._refresh_slopes()
            self._refresh_modal()
            self._refresh_history()
            self._refresh_dm()
            self._refresh_status()
        except Exception:
            traceback.print_exc()

    def _refresh_camera(self):
        f = self.e.last_frame
        if f is None:
            return
        ds = max(1, int(np.ceil(max(f.shape) / 512)))
        if ds != self._cam_ds:
            self._cam_ds = ds
            self._draw_pupils()
        img = f[::ds, ::ds]
        if self.chk_log.isChecked():
            img = np.sqrt(np.clip(img, 0, None))
        self.cam_img.setImage(img, autoLevels=True)
        for it in self._pupil_items:
            it.setVisible(self.chk_pupils.isChecked())
        fw = self.e.cam.full_well()
        mx = float(f.max())
        warn = '  SATURATED!' if mx >= fw * 0.98 else ''
        self.lbl_cam.setText('%dx%d  max %.0f / %.0f ADU%s   cam %.1f fps'
                             % (f.shape[1], f.shape[0], mx, fw, warn,
                                self.e.cam.get_fps()))

    def _refresh_slopes(self):
        e = self.e
        res = e._last
        if not res or e.proc is None:
            return
        mx, my = e.proc.to_maps(res['slopes'])
        lim = np.nanmax(np.abs(np.concatenate([mx[np.isfinite(mx)],
                                                my[np.isfinite(my)]]))) or 1
        self.sl_imgs[0].setImage(mx, levels=(-lim, lim))
        self.sl_imgs[1].setImage(my, levels=(-lim, lim))
        self.sl_imgs[2].setImage(e.proc.intensity_map(res['I']),
                                 autoLevels=True)

    def _refresh_modal(self):
        e = self.e
        if e.rec is None:
            return
        k = e.nm_per_unit
        m = e.tel.last_modes()
        if m is None or not np.all(np.isfinite(m)):
            return
        x = np.arange(1, m.size + 1)
        h = np.abs(m) if self.chk_abs.isChecked() else m
        self.bar_inst.setOpts(x=x, height=h * k, width=0.8)
        w = self.sp_win.value()
        self.curve_res.setData(x, e.tel.modal_rms(w) * k)
        d = e.tel.modal_rms(w, 'dist') * k
        if np.all(np.isfinite(d)):
            self.curve_dist.setData(x, d)
        wf = G.to_grid(e.rec.m2c @ m) * k
        lim = np.nanmax(np.abs(wf)) or 1
        self.wf_img.setImage(wf, levels=(-lim, lim))
        self.lbl_wf.setText('WF on DM: %.1f nm rms' %
                            (np.nanstd((e.rec.m2c @ m)[e.active]) * k))

    @staticmethod
    def _rmean(x, w):
        x = np.nan_to_num(np.asarray(x, float))
        if x.size == 0:
            return x
        c = np.cumsum(np.insert(x, 0, 0.0))
        k = np.arange(1, x.size + 1)
        a = np.maximum(0, k - int(w))
        return (c[k] - c[a]) / (k - a)

    def _refresh_history(self):
        e = self.e
        n = self.sp_hist.value()
        w = self.sp_win.value()
        k = e.nm_per_unit
        d = e.tel.dump()                     # one consistent snapshot
        if d['t'].size == 0:
            return
        sl = slice(-n, None)
        y = self._rmean(d['mode_rms'], w)[sl] * k
        x = np.arange(-y.size + 1, 1)
        yd = self._rmean(d['dist_rms'], w)[sl] * k
        self.c_mode.setData(x, y)
        self.c_dist.setData(x, yd)
        self.c_cmd.setData(x, self._rmean(d['loop_cmd_rms'], w)[sl] * k)
        self.c_slope.setData(x, self._rmean(d['slope_rms'], w)[sl])
        self.hist2.enableAutoRange()
        lc = np.nan_to_num(d['loop_closed'][sl])
        top = max(float(np.max(y)) if y.size else 0,
                  float(np.max(yd)) if yd.size else 0, 1e-3)
        self.c_closed.setData(x, lc * 0.08 * top)
        self.lbl_rate.setText('loop %.1f Hz | compute %.1f ms'
                              % (e.loop_rate_hz(), e.compute_time_ms()))

    def _refresh_dm(self):
        e = self.e
        sel = self.cb_dmch.currentText()
        if sel == 'absolute':
            v = e.total_command()
            img = G.to_grid(v)
            self.dm_img.setImage(img, levels=(0, 1))
        else:
            if sel.startswith('total'):
                v = e.total_command() - e.flat
            else:
                v = e.ch[sel]
            img = G.to_grid(v) * e.nm_per_unit
            lim = np.nanmax(np.abs(img)) or 1
            self.dm_img.setImage(img, levels=(-lim, lim))
        tot = e.total_command()
        self.lbl_dm.setText('cmd min %.3f max %.3f | saturated %.0f%%'
                            % (tot.min(), tot.max(), 100 * e.sat_frac))

    def _refresh_status(self):
        e = self.e
        if e.loop_closed:
            self.lbl_loop.setText('CLOSED')
            self.lbl_loop.setStyleSheet('color: #40ff80')
        else:
            self.lbl_loop.setText('OPEN' if not e.calibrating
                                  else 'CALIBRATING')
            self.lbl_loop.setStyleSheet('color: #ff8060' if not e.calibrating
                                        else 'color: #e0c040')
        self.pb.setValue(int(100 * e.calib_progress))
        self.lbl_sat.setText('DM saturation %.0f%%   status: %s'
                             % (100 * e.sat_frac, e.status))

    def closeEvent(self, ev):
        self.timer.stop()
        try:
            self.e.stop(park=True)
        finally:
            for d in (self.e.dm, self.e.mod, self.e.cam):
                try:
                    d.close()
                except Exception:
                    pass
        ev.accept()


def build_engine(mode: str, args) -> AOEngine:
    if mode == 'sim':
        from prima.aolab.devices.sim import make_sim_bench
        from prima.aolab.devices.hw import FACTORY_FLAT, load_flat
        flat = load_flat(FACTORY_FLAT)
        cam, dm, mod, model = make_sim_bench(flat=flat, fps=args.fps)
        e = AOEngine(cam, dm, mod, flat)
        e.sim_model = model
        return e
    from prima.aolab.devices.hw import make_hw_bench
    cam, dm, mod, flat = make_hw_bench(exposure_ms=args.exposure,
                                       binning=args.binning,
                                       radius_mrad=args.radius,
                                       use_dm=not args.no_dm)
    return AOEngine(cam, dm, mod, flat)


def main(argv=None):
    ap = argparse.ArgumentParser(description='PRIMA AO Lab GUI')
    g = ap.add_mutually_exclusive_group()
    g.add_argument('--sim', action='store_true', help='numerical twin')
    g.add_argument('--hw', action='store_true', help='real bench')
    ap.add_argument('--fps', type=float, default=30.0)
    ap.add_argument('--exposure', type=float, default=50.0)
    ap.add_argument('--binning', type=int, default=2)
    ap.add_argument('--radius', type=float, default=10.0)
    ap.add_argument('--no-dm', action='store_true',
                    help='real camera + modulator, DM not driven')
    ap.add_argument('--screenshot', default=None,
                    help='(testing) save a screenshot after N s and quit')
    ap.add_argument('--script', default=None,
                    help='(testing) python file run with `win`, `e` defined')
    args = ap.parse_args(argv)
    mode = 'hw' if args.hw else 'sim'
    app = QtWidgets.QApplication(sys.argv[:1])
    e = build_engine(mode, args)
    win = AOLabWindow(e, mode)
    e.start()
    win.show()
    if args.script:
        code = open(args.script).read()
        ns = {'win': win, 'e': e, 'app': app, 'np': np, 'time': time,
              'QtCore': QtCore, 'QtWidgets': QtWidgets}
        QtCore.QTimer.singleShot(500, lambda: exec(code, ns))
    return app.exec_()


if __name__ == '__main__':
    sys.exit(main())
