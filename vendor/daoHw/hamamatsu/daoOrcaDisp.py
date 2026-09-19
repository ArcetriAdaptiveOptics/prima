#!/usr/bin/env python3
"""
daoOrcaDisp.py -- minimal display + control GUI for a Hamamatsu ORCA camera.

Talks only to the shared memory published by the streamer:

    daoOrcaCtrl.py -S /tmp/orca.im.shm

i.e. the frame stream plus the Dit / Fps / ReadoutSpeed / SetTemp / Roi / Temp
control SHMs. No acquisition / telemetry / background tooling -- just live view
and camera control. Dark-grey theme.
"""

from PyQt5.uic import loadUiType
import sys
import getopt
import os
import time
from collections import deque

from PyQt5 import QtCore
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon, QFont

import pyqtgraph as pg
import numpy as np
import dao

# ---------------------------------------------------------------------------
# Theme (dark grey)
# ---------------------------------------------------------------------------
THEME_BG = "#1e1e1e"
THEME_FG = "#dcdcdc"
pg.setConfigOption('background', THEME_BG)
pg.setConfigOption('foreground', THEME_FG)

DEFAULT_SATURATION = 2 ** 16

COLORMAPS = {
    'grey':     [(0, 0, 0), (255, 255, 255)],
    'hot':      [(0, 0, 0), (128, 0, 0), (255, 128, 0), (255, 255, 0), (255, 255, 255)],
    'viridis':  [(68, 1, 84), (59, 82, 139), (33, 145, 140), (94, 201, 98), (253, 231, 37)],
    'inferno':  [(0, 0, 4), (120, 28, 109), (238, 71, 41), (252, 177, 57), (252, 255, 164)],
}

# DCAM READOUTSPEED enum -> label (1 = lowest read noise / slowest ... faster).
READOUT_SPEED_NAMES = {1: "Ultra quiet", 2: "Standard", 3: "Fast"}


def make_colormap(name):
    colors = COLORMAPS.get(name, COLORMAPS['grey'])
    return pg.ColorMap(np.linspace(0, 1, len(colors)), colors)


def readout_speed_label(value):
    v = int(round(float(value)))
    return f"{v} - {READOUT_SPEED_NAMES.get(v, f'mode {v}')}"


# get the directory of ui files
_UI_DIR = os.getenv('DAOROOT', '.') + '/data/'
Ui_MainWindow, QMainWindow = loadUiType(os.path.join(_UI_DIR, 'daoOrcaDisp.ui'))


class PgCamImageView:
    """PyQtGraph image display wired onto the `imageView` GraphicsView from the
    .ui file: colormap, Linear/Sqrt/Log scaling, freeze, autoscale + manual
    Min/Max levels, crosshair readout, zoom -> ROI, rolling average."""

    def __init__(self, graphics_view, im=np.zeros((128, 128)), cmap='grey',
                 min_spin=None, max_spin=None, pos_label=None):
        self.frozen = False
        self.autoscale = True
        self.manual_levels = (0.0, 1.0)
        self.min_spin = min_spin
        self.max_spin = max_spin
        self.pos_label = pos_label

        self.vb = pg.ViewBox()
        self.vb.setAspectLocked(True)
        graphics_view.setCentralItem(self.vb)

        self.img_item = pg.ImageItem(border=None)
        self.vb.addItem(self.img_item)
        self.img_item.setColorMap(make_colormap(cmap))

        self.hline = pg.InfiniteLine(angle=0, movable=False,
                                     pen=pg.mkPen('#ff6666', width=1, style=QtCore.Qt.DashLine))
        self.vline = pg.InfiniteLine(angle=90, movable=False,
                                     pen=pg.mkPen('#ff6666', width=1, style=QtCore.Qt.DashLine))
        self.vb.addItem(self.hline)
        self.vb.addItem(self.vline)
        self.hline.setVisible(False)
        self.vline.setVisible(False)
        self.crosshair_enabled = False

        self._mouse_proxy = pg.SignalProxy(graphics_view.scene().sigMouseMoved,
                                           rateLimit=60, slot=self._mouse_moved)

        self.rollingImageBuffer = np.zeros((100, im.shape[0], im.shape[1]))
        self._ring_idx = 0
        self.nrows, self.ncols = im.shape
        self.title = ''
        self.last_image = im

        self.set_image(im)
        self.reset_zoom()

    def resize_to(self, im):
        self.nrows, self.ncols = im.shape
        self.rollingImageBuffer = np.zeros((100, im.shape[0], im.shape[1]))
        self._ring_idx = 0
        self.set_image(im)
        self.reset_zoom()

    def set_colormap(self, name):
        self.img_item.setColorMap(make_colormap(name))

    def set_frozen(self, frozen):
        self.frozen = frozen

    def set_autoscale(self, enabled):
        self.autoscale = enabled
        if self.min_spin is not None:
            self.min_spin.setEnabled(not enabled)
        if self.max_spin is not None:
            self.max_spin.setEnabled(not enabled)

    def set_manual_levels(self, vmin, vmax):
        self.manual_levels = (vmin, vmax)

    def set_crosshair(self, visible):
        self.crosshair_enabled = visible
        self.hline.setVisible(visible)
        self.vline.setVisible(visible)
        if self.pos_label is not None and not visible:
            self.pos_label.setText("")

    def _mouse_moved(self, evt):
        if not self.crosshair_enabled:
            return
        pos = evt[0]
        if not self.vb.sceneBoundingRect().contains(pos):
            return
        mp = self.vb.mapSceneToView(pos)
        x, y = int(mp.x()), int(mp.y())
        self.hline.setPos(mp.y())
        self.vline.setPos(mp.x())
        if self.pos_label is None:
            return
        try:
            img = self.img_item.image
            if img is not None and 0 <= x < img.shape[0] and 0 <= y < img.shape[1]:
                self.pos_label.setText(f"x={x} y={y} val={img[x, y]:.1f}")
            else:
                self.pos_label.setText(f"x={x} y={y}")
        except Exception:
            self.pos_label.setText(f"x={x} y={y}")

    def set_image(self, im):
        self.img_item.setImage(im.T, autoLevels=True)

    def get_zoom_roi(self):
        (xmin, xmax), (ymin, ymax) = self.vb.viewRange()
        col_min = max(0, int(np.floor(xmin + 0.5)))
        col_max = min(self.ncols, int(np.ceil(xmax + 0.5)))
        row_min = max(0, int(np.floor(ymin + 0.5)))
        row_max = min(self.nrows, int(np.ceil(ymax + 0.5)))
        return {'width': col_max - col_min, 'height': row_max - row_min,
                'cx': (col_min + col_max) // 2, 'cy': (row_min + row_max) // 2}

    def reset_zoom(self):
        self.vb.setRange(xRange=(-0.5, self.ncols - 0.5),
                         yRange=(-0.5, self.nrows - 0.5), padding=0)

    def plot_image(self, image, saturation_lim=DEFAULT_SATURATION,
                   scale="Linear", rollingAverage=False):
        if self.frozen:
            return self.last_image

        if image.shape == self.rollingImageBuffer.shape[1:]:
            self.rollingImageBuffer[self._ring_idx] = image
            self._ring_idx = (self._ring_idx + 1) % self.rollingImageBuffer.shape[0]

        temp_image = np.mean(self.rollingImageBuffer, axis=0) if rollingAverage else image.copy()
        temp_image[temp_image < 0] = 0

        if scale == "Sqrt":
            shown = np.sqrt(temp_image)
        elif scale == "Log":
            shown = np.log10(1 + temp_image)
        else:
            shown = temp_image

        dmax = float(image.max())
        if self.autoscale:
            levels = (float(np.nanmin(shown)), float(np.nanmax(shown)))
            if self.min_spin is not None and self.max_spin is not None:
                for spin, val in ((self.min_spin, levels[0]), (self.max_spin, levels[1])):
                    spin.blockSignals(True)
                    spin.setValue(val)
                    spin.blockSignals(False)
        else:
            levels = self.manual_levels

        self.img_item.setImage(shown.T, levels=levels, autoLevels=False)
        self.last_image = temp_image
        self.title = 'SATURATION' if dmax > saturation_lim else ''
        return temp_image


class OrcaDispApp(QMainWindow, Ui_MainWindow):
    def __init__(self, shmName):
        super(OrcaDispApp, self).__init__()
        self.setupUi(self)

        self.shmName = shmName
        self.shmim = dao.shm(shmName)

        base = shmName.split('/')[-1].split('.')[0]
        self.shmDit = dao.shm(f"/tmp/{base}Dit.im.shm")
        self.shmFps = dao.shm(f"/tmp/{base}Fps.im.shm")
        self.shmReadoutSpeed = self._try_attach(f"/tmp/{base}ReadoutSpeed.im.shm")
        self.shmSetTemp = self._try_attach(f"/tmp/{base}SetTemp.im.shm")
        self.shmRoi = self._try_attach(f"/tmp/{base}Roi.im.shm")
        self.shmTemp = self._try_attach(f"/tmp/{base}Temp.im.shm")

        self.imageSizeX, self.imageSizeY = self.shmim.get_data().shape[:2]
        self.saturation_lim = 2 ** 8 if self.shmim.get_data().dtype == np.uint8 else DEFAULT_SATURATION

        im = self.shmim.get_data().astype(np.float32).reshape(self.imageSizeX, self.imageSizeY)
        self.canvas = PgCamImageView(self.imageView, im, cmap='grey',
                                     min_spin=self.minSpin, max_spin=self.maxSpin,
                                     pos_label=self.posLabel)

        stats_font = QFont("Monospace")
        stats_font.setStyleHint(QFont.TypeWriter)
        self.statsLabel.setFont(stats_font)

        # --- view controls
        self.cmapComboBox.currentTextChanged.connect(self.canvas.set_colormap)
        self.freezeButton.toggled.connect(self._toggle_freeze)
        self.extractZoomButton.clicked.connect(self.extract_zoom_roi)
        self.resetZoomButton.clicked.connect(self.canvas.reset_zoom)
        self.autoCheckBox.toggled.connect(self.canvas.set_autoscale)
        self.minSpin.valueChanged.connect(
            lambda v: self.canvas.set_manual_levels(v, self.maxSpin.value()))
        self.maxSpin.valueChanged.connect(
            lambda v: self.canvas.set_manual_levels(self.minSpin.value(), v))
        self.crossCheckBox.toggled.connect(self.canvas.set_crosshair)

        # --- camera controls
        self.ditBox.setValue(float(self.shmDit.get_data()[0, 0]))
        self.fpsBox.setValue(float(self.shmFps.get_data()[0, 0]))
        self.ditButton.clicked.connect(self.updateDit)
        self.fpsButton.clicked.connect(self.updateFps)

        if self.shmReadoutSpeed is not None:
            self.readoutSpeedComboBox.clear()
            for val, name in READOUT_SPEED_NAMES.items():
                self.readoutSpeedComboBox.addItem(f"{val} - {name}", val)
            self._select_readout_speed(self.shmReadoutSpeed.get_data()[0, 0])
            self.readoutSpeedComboBox.activated.connect(self.updateReadoutSpeed)
        else:
            self.readoutSpeedComboBox.setEnabled(False)
            self.readoutSpeedLabel.setText("Readout speed (n/a)")

        if self.shmSetTemp is not None:
            self.setTempBox.setValue(float(self.shmSetTemp.get_data()[0, 0]))
            self.setTempButton.clicked.connect(self.updateSetTemp)
        else:
            self.setTempBox.setEnabled(False)
            self.setTempButton.setEnabled(False)

        # --- ROI
        self.ImageCenterXBox.setValue(self.imageSizeX // 2)
        self.ImageCenterYBox.setValue(self.imageSizeY // 2)
        self.roiApplyButton.clicked.connect(self.applyRoi)
        self.roiFullButton.clicked.connect(self.fullFrameRoi)
        if self.shmRoi is None:
            for w in (self.ImageWidthBox, self.ImageCenterXBox, self.ImageCenterYBox,
                      self.roiApplyButton, self.roiFullButton):
                w.setEnabled(False)
            self.roiLabel.setText("ROI  (start daoOrcaCtrl.py without --no-roi)")

        self.canvas.plot_image(im, self.saturation_lim)

        # rolling frame-rate estimate over the last FPS_WINDOW_S seconds
        self.FPS_WINDOW_S = 2.0
        self._fps_hist = deque([(time.time(), self.shmim.get_counter())])

        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.Update)

    # ------------------------------------------------------------------
    @staticmethod
    def _try_attach(name):
        try:
            return dao.shm(name)
        except Exception:
            return None

    def _toggle_freeze(self, checked):
        self.canvas.set_frozen(checked)
        self.freezeButton.setText("Unfreeze" if checked else "Freeze")

    def Start(self):
        self.timer.start()

    def Stop(self):
        self.timer.stop()

    # ------------------------------------------------------------------
    @QtCore.pyqtSlot()
    def Update(self):
        im = self.shmim.get_data().astype(np.float32)

        if im.shape != (self.imageSizeX, self.imageSizeY):
            self.imageSizeX, self.imageSizeY = im.shape
            self.canvas.resize_to(im)
            return

        im = self.canvas.plot_image(im, self.saturation_lim,
                                    scale=self.scaleComboBox.currentText(),
                                    rollingAverage=self.rollingCheckBox.isChecked())

        self.statsLabel.setText(
            f"min={im.min():8.1f}  max={im.max():8.1f}  "
            f"mean={im.mean():8.1f}  std={im.std():7.1f}   {self.canvas.title}")

        # Saturation meter: bar = % of full scale, text = raw peak count so it
        # stays readable even on a dark frame where the percentage rounds to 0.
        peak = float(im.max())
        self.saturationProgressBar.setValue(int(min(100, round(peak * 100 / self.saturation_lim))))
        self.saturationProgressBar.setFormat(f"{int(peak)}")

        t = time.time()
        cnt = self.shmim.get_counter()
        self._fps_hist.append((t, cnt))
        while len(self._fps_hist) > 2 and t - self._fps_hist[0][0] > self.FPS_WINDOW_S:
            self._fps_hist.popleft()
        t0, c0 = self._fps_hist[0]
        if t - t0 > 0:
            self.freqLabel.setText(f'{(cnt - c0) / (t - t0):.2f} Hz')

        self.ditStatusLabel.setText(f"{float(self.shmDit.get_data()[0, 0]):.3f} ms")
        self.fpsStatusLabel.setText(f"{float(self.shmFps.get_data()[0, 0]):.2f} Hz")
        if self.shmReadoutSpeed is not None:
            self.readoutSpeedStatusLabel.setText(
                readout_speed_label(self.shmReadoutSpeed.get_data()[0, 0]))
        if self.shmTemp is not None:
            self.tempStatusLabel.setText(f"{float(self.shmTemp.get_data()[0, 0]):.1f} C")

    # ------------------------------------------------------------------
    # Camera controls -- write the SHMs daoOrcaCtrl.py watches
    # ------------------------------------------------------------------
    def updateDit(self):
        self.shmDit.set_data(self.shmDit.get_data() * 0 + np.float32(self.ditBox.value()))

    def updateFps(self):
        self.shmFps.set_data(self.shmFps.get_data() * 0 + np.float32(self.fpsBox.value()))

    def _select_readout_speed(self, value):
        idx = self.readoutSpeedComboBox.findData(int(round(float(value))))
        if idx >= 0:
            self.readoutSpeedComboBox.blockSignals(True)
            self.readoutSpeedComboBox.setCurrentIndex(idx)
            self.readoutSpeedComboBox.blockSignals(False)

    def updateReadoutSpeed(self, *_):
        if self.shmReadoutSpeed is None:
            return
        v = self.readoutSpeedComboBox.currentData()
        if v is not None:
            self.shmReadoutSpeed.set_data(self.shmReadoutSpeed.get_data() * 0 + np.float32(v))

    def updateSetTemp(self):
        if self.shmSetTemp is None:
            return
        self.shmSetTemp.set_data(
            self.shmSetTemp.get_data() * 0 + np.float32(self.setTempBox.value()))

    # ------------------------------------------------------------------
    # ROI (writes the Roi SHM watched by daoOrcaCtrl.py)
    # ------------------------------------------------------------------
    def extract_zoom_roi(self):
        roi = self.canvas.get_zoom_roi()
        width = max(roi['width'], roi['height'])
        width = int(np.clip(width - (width % 4),
                            self.ImageWidthBox.minimum(), self.ImageWidthBox.maximum()))
        self.ImageWidthBox.setValue(width)
        self.ImageCenterXBox.setValue(int(np.clip(roi['cx'], 0, self.ImageCenterXBox.maximum())))
        self.ImageCenterYBox.setValue(int(np.clip(roi['cy'], 0, self.ImageCenterYBox.maximum())))
        self.msgLabel.setText(f"ROI staged: w={width} cx={roi['cx']} cy={roi['cy']}  (Apply ROI)")

    def applyRoi(self):
        if self.shmRoi is None:
            return
        w = int(self.ImageWidthBox.value())
        x = max(0, int(self.ImageCenterXBox.value()) - w // 2)
        y = max(0, int(self.ImageCenterYBox.value()) - w // 2)
        self.shmRoi.set_data(np.array([[x, y, w, w]], dtype=np.int32))
        self.msgLabel.setText(f"ROI applied: x={x} y={y} w={w} h={w}")

    def fullFrameRoi(self):
        if self.shmRoi is None:
            return
        self.shmRoi.set_data(np.array([[0, 0, 0, 0]], dtype=np.int32))
        self.msgLabel.setText("ROI reset to full frame")


if __name__ == '__main__':
    shmimName = '/tmp/orca.im.shm'
    try:
        opts, _ = getopt.getopt(sys.argv[1:], "hs:", ["help", "shmimName="])
    except getopt.GetoptError:
        print('usage: daoOrcaDisp.py -s <shmimName>')
        sys.exit(2)
    for opt, arg in opts:
        if opt in ('-h', '--help'):
            print('usage: daoOrcaDisp.py -s <shmimName>')
            sys.exit()
        elif opt in ("-s", "--shm", "--shmimName"):
            shmimName = str(arg)

    app = QApplication([])
    QtCore.QLocale.setDefault(QtCore.QLocale(QtCore.QLocale.English, QtCore.QLocale.UnitedStates))

    dao_root = os.getenv("DAOROOT")
    if dao_root:
        icon_path = os.path.join(dao_root, "data/GSC.png")
        if os.path.exists(icon_path):
            app.setWindowIcon(QIcon(icon_path))

    gui = OrcaDispApp(shmimName)
    gui.setWindowTitle(shmimName)
    gui.show()
    gui.Start()
    sys.exit(app.exec_())
