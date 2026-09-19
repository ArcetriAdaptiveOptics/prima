#!/usr/bin/env python3
"""
orcaCtrl.py -- DAO control GUI for a Hamamatsu ORCA camera.

Adapted from cblueCtrl.py. Talks only to shared memory: the frame stream and
the Dit / Fps / ReadoutSpeed / Roi / Temp control SHMs published by

    daoOrcaCtrl.py -S /tmp/orca.im.shm

so this GUI needs that streamer running. Science/PSF/OG tooling from
cblueCtrl.py has been removed -- this is a plain camera control + viewer.
"""

from PyQt5.uic import loadUiType
import sys, getopt
from PyQt5 import QtCore
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QRunnable, QThreadPool, pyqtSlot, QObject, pyqtSignal
from PyQt5.QtGui import QIcon, QFont

import pyqtgraph as pg
import numpy as np
import time
import os
import re
import subprocess
from collections import deque
import dao

# ---------------------------------------------------------------------------
# GUI theme -- same colors as EkarusCtrl.py / GUIUtils.py
# ---------------------------------------------------------------------------
THEME_BG = "#0b1740"
THEME_FG = "#e8eef7"

pg.setConfigOption('background', THEME_BG)
pg.setConfigOption('foreground', THEME_FG)

# ORCA sCMOS sensors read out MONO16; the ADC full-scale used for the
# saturation meter. Overridden below if the stream is actually 8-bit.
DEFAULT_SATURATION = 2 ** 16

# DCAM READOUTSPEED enum -> label. Values match dcamprop.h / daoOrcaCtrl.py
# (1 = lowest read noise / slowest ... higher = faster). Names as used by the
# ORCA-Fusion / Flash4 families; an out-of-range value falls back to "mode N".
READOUT_SPEED_NAMES = {
    1: "Ultra quiet",
    2: "Standard",
    3: "Fast",
}


def readout_speed_label(value):
    v = int(round(float(value)))
    return f"{v} - {READOUT_SPEED_NAMES.get(v, f'mode {v}')}"

COLORMAPS = {
    'grey':     [(0, 0, 0), (255, 255, 255)],
    'hot':      [(0, 0, 0), (128, 0, 0), (255, 128, 0), (255, 255, 0), (255, 255, 255)],
    'viridis':  [(68, 1, 84), (59, 82, 139), (33, 145, 140), (94, 201, 98), (253, 231, 37)],
    'inferno':  [(0, 0, 4), (120, 28, 109), (238, 71, 41), (252, 177, 57), (252, 255, 164)],
}


def make_colormap(name):
    colors = COLORMAPS.get(name, COLORMAPS['grey'])
    return pg.ColorMap(np.linspace(0, 1, len(colors)), colors)


class SubprocessWorker(QRunnable):
    def __init__(self, command):
        super(SubprocessWorker, self).__init__()
        self.command = command
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self):
        try:
            result = subprocess.run(self.command, check=True, capture_output=True, text=True)
            self.signals.finished.emit(result.stdout)
            match = re.search(r'Saved to (.+)', result.stdout)
            if match:
                self.signals.path_extracted.emit(match.group(1))
        except subprocess.CalledProcessError as e:
            self.signals.error.emit(e.stderr)


class WorkerSignals(QObject):
    """Signals available from a running worker thread."""
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    path_extracted = pyqtSignal(str)


# get the directory of ui files
path = os.getenv('DAOROOT') + '/data/'
Ui_MainWindow, QMainWindow = loadUiType(os.path.join(path, 'orcaCtrl.ui'))


class PgCamImageView:
    """
    PyQtGraph image display wired onto the `imageView` GraphicsView placeholder
    from the .ui file (same wrapping pattern as GUIUtils' DmShapeView).

    Colormap selection (grey default, hot/viridis/inferno), Linear/Sqrt/Log
    display scaling, freeze, autoscale + manual Min/Max levels, crosshair
    readout, pixel zoom -> ROI export, and an optional rolling average.
    """

    def __init__(self, graphics_view, im=np.zeros((128, 128)), cmap='grey',
                 min_spin=None, max_spin=None, pos_label=None, roi_pos_label=None):
        self.frozen = False
        self.display_mode = "Linear"
        self.autoscale = True
        self.manual_levels = (0.0, 1.0)

        self.min_spin = min_spin
        self.max_spin = max_spin
        self.pos_label = pos_label
        self.roi_pos_label = roi_pos_label

        self.vb = pg.ViewBox()
        self.vb.setAspectLocked(True)
        graphics_view.setCentralItem(self.vb)
        self.vb.sigRangeChanged.connect(self._update_roi_pos_label)

        self.img_item = pg.ImageItem(border=None)
        self.vb.addItem(self.img_item)
        self.img_item.setColorMap(make_colormap(cmap))

        self.hline = pg.InfiniteLine(angle=0, movable=False,
                                     pen=pg.mkPen('#ff4444', width=1,
                                                  style=QtCore.Qt.DashLine))
        self.vline = pg.InfiniteLine(angle=90, movable=False,
                                     pen=pg.mkPen('#ff4444', width=1,
                                                  style=QtCore.Qt.DashLine))
        self.vb.addItem(self.hline)
        self.vb.addItem(self.vline)
        self.hline.setVisible(False)
        self.vline.setVisible(False)
        self.crosshair_enabled = False

        self._mouse_proxy = pg.SignalProxy(
            graphics_view.scene().sigMouseMoved,
            rateLimit=60,
            slot=self._mouse_moved
        )

        self.rollingImageBuffer = np.zeros((100, im.shape[0], im.shape[1]), dtype=np.float32)
        self._ring_idx = 0

        # image geometry (rows, cols) -- needed to clamp the ROI
        self.nrows, self.ncols = im.shape

        self.title = ''
        self.last_image = im

        self.set_image(im)
        self.reset_zoom()

    def resize_to(self, im):
        """Rebuild internal buffers when the frame size changed (ROI update)."""
        self.nrows, self.ncols = im.shape
        self.rollingImageBuffer = np.zeros((100, im.shape[0], im.shape[1]), dtype=np.float32)
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
        pos = evt[0]
        if not self.crosshair_enabled:
            return
        if self.vb.sceneBoundingRect().contains(pos):
            mp = self.vb.mapSceneToView(pos)
            x, y = int(mp.x()), int(mp.y())
            self.hline.setPos(mp.y())
            self.vline.setPos(mp.x())
            if self.pos_label is None:
                return
            try:
                img = self.img_item.image  # shape (cols, rows) after .T
                if img is not None and 0 <= x < img.shape[0] and 0 <= y < img.shape[1]:
                    self.pos_label.setText(f"x={x} y={y} val={img[x, y]:.1f}")
                else:
                    self.pos_label.setText(f"x={x} y={y}")
            except Exception:
                self.pos_label.setText(f"x={x} y={y}")

    def set_image(self, im):
        """Push a raw frame with no scaling/levels change -- used at init."""
        self.img_item.setImage(im.T, autoLevels=True)

    def get_zoom_roi(self):
        """Return the currently displayed region as integer pixel indices."""
        (xmin, xmax), (ymin, ymax) = self.vb.viewRange()

        col_min = max(0, int(np.floor(xmin + 0.5)))
        col_max = min(self.ncols, int(np.ceil(xmax + 0.5)))
        row_min = max(0, int(np.floor(ymin + 0.5)))
        row_max = min(self.nrows, int(np.ceil(ymax + 0.5)))

        self.roi = {'col_min': col_min, 'col_max': col_max,
                    'row_min': row_min, 'row_max': row_max,
                    'width':  col_max - col_min,
                    'height': row_max - row_min,
                    'cx': (col_min + col_max) // 2,
                    'cy': (row_min + row_max) // 2}
        return self.roi

    def _update_roi_pos_label(self, *args):
        """Show the pyqtgraph view's current pan/zoom (pos + size) so it's
        obvious what region of the frame is being looked at."""
        if self.roi_pos_label is None:
            return
        roi = self.get_zoom_roi()
        self.roi_pos_label.setText(
            f"View: x={roi['col_min']}:{roi['col_max']} "
            f"y={roi['row_min']}:{roi['row_max']}  "
            f"size={roi['width']}x{roi['height']}  "
            f"center=({roi['cx']},{roi['cy']})")

    def reset_zoom(self):
        """Back to the full frame."""
        self.vb.setRange(xRange=(-0.5, self.ncols - 0.5),
                         yRange=(-0.5, self.nrows - 0.5),
                         padding=0)

    def plot_image(self, image, saturation_lim=DEFAULT_SATURATION, neg=False,
                   scale="Linear", rollingAverage=False):
        if self.frozen:
            return self.last_image

        # rolling buffer -- circular write (O(1))
        if image.shape == self.rollingImageBuffer.shape[1:]:
            self.rollingImageBuffer[self._ring_idx] = image
            self._ring_idx = (self._ring_idx + 1) % self.rollingImageBuffer.shape[0]

        if rollingAverage:
            temp_image = np.mean(self.rollingImageBuffer, axis=0)
        else:
            temp_image = image.copy()

        temp_image[temp_image < 0] = 0

        self.display_mode = scale
        if scale == "Sqrt":
            image_to_show = np.sqrt(temp_image)
        elif scale == "Log":
            image_to_show = np.log10(1 + temp_image)
        else:
            image_to_show = temp_image

        dmax = float(image.max())
        dmax_scaled = float(np.nanmax(image_to_show))
        dmin_scaled = float(np.nanmin(image_to_show))

        if self.autoscale:
            levels = (dmin_scaled, dmax_scaled) if neg else (0, dmax_scaled)
            if self.min_spin is not None and self.max_spin is not None:
                self.min_spin.blockSignals(True)
                self.max_spin.blockSignals(True)
                self.min_spin.setValue(levels[0])
                self.max_spin.setValue(levels[1])
                self.min_spin.blockSignals(False)
                self.max_spin.blockSignals(False)
        else:
            levels = self.manual_levels

        self.img_item.setImage(image_to_show.T, levels=levels, autoLevels=False)
        self.last_image = temp_image

        self.title = ' SATURATION' if dmax > saturation_lim else ''
        return temp_image


class OrcaCtrlApp(QMainWindow, Ui_MainWindow):
    def __init__(self, shmName):
        super(OrcaCtrlApp, self).__init__()
        self.setupUi(self)
        self.threadpool = QThreadPool()

        self.shmName = shmName
        self.shmim = dao.shm(shmName)

        # base name + derived SHM names (must match daoOrcaCtrl.derive_names)
        self.baseName = shmName.split('/')[-1].split('.')[0]
        self.shmDitName = f"/tmp/{self.baseName}Dit.im.shm"
        self.shmFpsName = f"/tmp/{self.baseName}Fps.im.shm"
        self.shmReadoutSpeedName = f"/tmp/{self.baseName}ReadoutSpeed.im.shm"
        self.shmRoiName = f"/tmp/{self.baseName}Roi.im.shm"
        self.shmTempName = f"/tmp/{self.baseName}Temp.im.shm"
        self.shmSetTempName = f"/tmp/{self.baseName}SetTemp.im.shm"
        self.shmBgName = f"/tmp/{self.baseName}Bg.im.shm"
        self.shmBgPercentName = f"/tmp/{self.baseName}BgPercent.im.shm"
        self.shmPercentName = f"/tmp/{self.baseName}Percent.im.shm"

        # Control SHMs are owned by daoOrcaCtrl.py -- attach, don't create.
        self.shmDit = dao.shm(self.shmDitName)
        self.shmFps = dao.shm(self.shmFpsName)
        self.shmReadoutSpeed = self._try_attach(self.shmReadoutSpeedName)
        self.shmRoi = self._try_attach(self.shmRoiName)
        self.shmTemp = self._try_attach(self.shmTempName)
        self.shmSetTemp = self._try_attach(self.shmSetTempName)

        self.imageSizeX = self.shmim.get_data().shape[0]
        self.imageSizeY = self.shmim.get_data().shape[1]

        # Background / progress SHMs -- created here, sized to the frame.
        self.shmBg = dao.shm(self.shmBgName,
                             np.zeros((self.imageSizeX, self.imageSizeY), dtype=np.float32))
        self.shmBgP = dao.shm(self.shmBgPercentName, np.zeros((1, 1), dtype=np.uint32))
        self.shmImP = dao.shm(self.shmPercentName, np.zeros((1, 1), dtype=np.uint32))

        self.saturation_lim = DEFAULT_SATURATION
        if self.shmim.get_data().dtype == np.uint8:
            self.saturation_lim = 2 ** 8

        im = self.shmim.get_data().astype(np.float32).reshape(self.imageSizeX, self.imageSizeY)

        self.canvas = PgCamImageView(self.imageView, im, cmap='grey',
                                     min_spin=self.minSpin, max_spin=self.maxSpin,
                                     pos_label=self.posLabel,
                                     roi_pos_label=self.roiPosLabel)

        self.saturationProgressBar.setStyleSheet(
            "QProgressBar { color: black; font-size: 8px; font-weight: bold; }"
        )

        stats_font = QFont("Monospace")
        stats_font.setStyleHint(QFont.TypeWriter)
        self.statsLabel.setFont(stats_font)

        # --- view controls
        self.cmapComboBox.setCurrentText('grey')
        self.cmapComboBox.currentTextChanged.connect(self.canvas.set_colormap)
        self.freezeButton.toggled.connect(self._toggle_freeze)
        self.extractZoomButton.clicked.connect(self.extract_zoom_roi)
        self.resetZoomButton.clicked.connect(self.canvas.reset_zoom)
        self.autoCheckBox.setChecked(True)
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

        # --- cooling setpoint (only if the streamer created the SHM)
        if self.shmSetTemp is not None:
            self.setTempBox.setValue(float(self.shmSetTemp.get_data()[0, 0]))
            self.setTempButton.clicked.connect(self.updateSetTemp)
        else:
            self.setTempBox.setEnabled(False)
            self.setTempButton.setEnabled(False)

        # --- ROI (writes the Roi SHM watched by daoOrcaCtrl.py)
        self.ImageWidthBox.setValue(min(self.imageSizeY, self.ImageWidthBox.value()))
        self.ImageCenterXBox.setValue(self.imageSizeX // 2)
        self.ImageCenterYBox.setValue(self.imageSizeY // 2)
        self.roiApplyButton.clicked.connect(self.applyRoi)
        self.roiFullButton.clicked.connect(self.fullFrameRoi)
        if self.shmRoi is None:
            for w in (self.ImageWidthBox, self.ImageCenterXBox, self.ImageCenterYBox,
                      self.roiApplyButton, self.roiFullButton):
                w.setEnabled(False)
            self.roiLabel.setText("ROI  (start daoOrcaCtrl.py without --no-roi)")

        # --- acquisition
        self.acqButton.clicked.connect(self.acqData)
        self.acqAvgButton.clicked.connect(self.acqAvgData)
        self.acqBgButton.clicked.connect(self.acqBgData)
        self.resetBgButton.clicked.connect(self.resetBg)

        self.canvas.plot_image(im, self.saturation_lim)

        # (time, image counter) samples for a rolling frame-rate estimate,
        # kept over the last FPS_WINDOW_S seconds so the readout is steady.
        self.FPS_WINDOW_S = 2.0
        self._fps_hist = deque([(time.time(), self.shmim.get_counter())])

        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(100)  # 10 Hz display refresh
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

        # Frame size changed under us (ROI applied) -- rewire everything.
        if im.shape != (self.imageSizeX, self.imageSizeY):
            self.imageSizeX, self.imageSizeY = im.shape
            self.canvas.resize_to(im)
            self.shmBg = dao.shm(self.shmBgName,
                                 np.zeros(im.shape, dtype=np.float32))
            return

        neg = False
        if self.bgCheckBox.isChecked():
            im = im - self.shmBg.get_data().astype(np.float32).reshape(im.shape)
            neg = True

        scale_text = self.scaleComboBox.currentText()
        useRolling = self.rollingCheckBox.isChecked()
        im = self.canvas.plot_image(im, self.saturation_lim, neg=neg,
                                    scale=scale_text, rollingAverage=useRolling)

        stats = (f"min={im.min():8.1f}  max={im.max():8.1f}  "
                 f"mean={im.mean():8.1f}  std={im.std():7.1f}   {self.canvas.title}")
        self.statsLabel.setText(stats)
        self.saturationProgressBar.setValue(
            int(min(100, (im.max() * 100) / self.saturation_lim)))

        # frame rate: rolling average over the last FPS_WINDOW_S seconds of
        # (time, counter) samples, instead of the noisy tick-to-tick delta.
        t = time.time()
        cnt = self.shmim.get_counter()
        self._fps_hist.append((t, cnt))
        while len(self._fps_hist) > 2 and t - self._fps_hist[0][0] > self.FPS_WINDOW_S:
            self._fps_hist.popleft()
        t0, c0 = self._fps_hist[0]
        if t - t0 > 0:
            self.freqLabel.setText(f'{(cnt - c0) / (t - t0):.2f} Hz')

        self.progressBar.setValue(int(self.shmImP.get_data()[0, 0]))
        self.progressBgBar.setValue(int(self.shmBgP.get_data()[0, 0]))
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
        """Point the combo at `value` without emitting activated()."""
        idx = self.readoutSpeedComboBox.findData(int(round(float(value))))
        if idx >= 0:
            self.readoutSpeedComboBox.blockSignals(True)
            self.readoutSpeedComboBox.setCurrentIndex(idx)
            self.readoutSpeedComboBox.blockSignals(False)

    def updateReadoutSpeed(self, *_):
        if self.shmReadoutSpeed is None:
            return
        v = self.readoutSpeedComboBox.currentData()
        if v is None:
            return
        self.shmReadoutSpeed.set_data(
            self.shmReadoutSpeed.get_data() * 0 + np.float32(v))

    def updateSetTemp(self):
        if self.shmSetTemp is None:
            return
        self.shmSetTemp.set_data(
            self.shmSetTemp.get_data() * 0 + np.float32(self.setTempBox.value()))

    # ------------------------------------------------------------------
    # ROI
    # ------------------------------------------------------------------
    def extract_zoom_roi(self):
        """Read the current pyqtgraph zoom into the ROI spin boxes (no apply)."""
        roi = self.canvas.get_zoom_roi()
        width = max(roi['width'], roi['height'])
        width = int(np.clip(width - (width % 4),
                            self.ImageWidthBox.minimum(), self.ImageWidthBox.maximum()))
        self.ImageWidthBox.setValue(width)
        self.ImageCenterXBox.setValue(int(np.clip(roi['cx'], 0, self.ImageCenterXBox.maximum())))
        self.ImageCenterYBox.setValue(int(np.clip(roi['cy'], 0, self.ImageCenterYBox.maximum())))
        self.logLabel.setText(f"ROI staged: w={width} cx={roi['cx']} cy={roi['cy']}  (Apply ROI)")

    def applyRoi(self):
        if self.shmRoi is None:
            return
        w = int(self.ImageWidthBox.value())
        cx = int(self.ImageCenterXBox.value())
        cy = int(self.ImageCenterYBox.value())
        # SHM layout is (x, y, w, h) with x/y the top-left corner.
        x = max(0, cx - w // 2)
        y = max(0, cy - w // 2)
        self.shmRoi.set_data(np.array([[x, y, w, w]], dtype=np.int32))
        self.logLabel.setText(f"ROI applied: x={x} y={y} w={w} h={w}")

    def fullFrameRoi(self):
        if self.shmRoi is None:
            return
        self.shmRoi.set_data(np.array([[0, 0, 0, 0]], dtype=np.int32))
        self.logLabel.setText("ROI reset to full frame")

    # ------------------------------------------------------------------
    # Acquisition (generic dao tools)
    # ------------------------------------------------------------------
    def _run(self, command, done=None, err=None, path=None, log=None):
        worker = SubprocessWorker(command)
        if done:
            worker.signals.finished.connect(done)
        if err:
            worker.signals.error.connect(err)
        if path:
            worker.signals.path_extracted.connect(path)
        self.threadpool.start(worker)
        if log:
            self.logLabel.setText(log)

    def acqData(self):
        w = str(self.ImageWidthBox.value())
        cmd = ["python3", os.getenv("DAOROOT") + "/bin/daoTakeDataCubeNPY.py",
               self.shmName, str(self.nbFrameBox.value()), str(self.frameIdBox.value()),
               w, str(self.ImageCenterXBox.value()), str(self.ImageCenterYBox.value())]
        self._run(cmd, done=self.on_acq_done, err=self.on_acq_error,
                  path=self.on_path_extracted, log="Data cube acquisition in progress...")

    def acqAvgData(self):
        cmd = ["python3", os.getenv("DAOROOT") + "/bin/daoTakeAverageDataNPY.py",
               self.shmName, str(self.nbFrameBox.value()), str(self.frameIdBox.value())]
        self._run(cmd, done=self.on_acq_done, err=self.on_acq_error,
                  path=self.on_path_extracted, log="Average acquisition in progress...")
        self.frameIdBox.setValue(self.frameIdBox.value() + 1)

    def acqBgData(self):
        cmd = ["python3", os.getenv("DAOROOT") + "/bin/daoTakeBg.py",
               self.shmName, str(self.nbFrameBgBox.value())]
        self._run(cmd, done=self.on_acq_bg_done, err=self.on_acq_bg_error,
                  log="Background acquisition in progress...")

    def resetBg(self):
        self.shmBg.set_data(self.shmBg.get_data() * 0)

    @pyqtSlot(str)
    def on_path_extracted(self, saving_path):
        self.logLabel.setText(f"Data saved at: {saving_path}")

    @pyqtSlot(str)
    def on_acq_done(self, output):
        saving_path = None
        for line in output.splitlines():
            if "saving in" in line:
                saving_path = line.split("saving in")[-1].strip()
                break
        self.logLabel.setText(
            f"Saved: {saving_path}" if saving_path else "Acquisition done")
        self.progressBar.setValue(100)

    @pyqtSlot(str)
    def on_acq_error(self, error):
        self.logLabel.setText("Error during acquisition")
        print(f"Error: {error}")

    @pyqtSlot(str)
    def on_acq_bg_done(self, output):
        self.logBgLabel.setText("Background acquisition done")
        self.progressBgBar.setValue(100)

    @pyqtSlot(str)
    def on_acq_bg_error(self, error):
        self.logBgLabel.setText("Error during background acquisition")
        print(f"Error: {error}")


if __name__ == '__main__':
    shmimName = '/tmp/orca.im.shm'
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hs:", ["help", "shmimName="])
    except getopt.GetoptError:
        print('err, usage: orcaCtrl.py -s <shmimName>')
        sys.exit(2)
    for opt, arg in opts:
        if opt in ('-h', '--help'):
            print('orcaCtrl.py -s <shmimName>')
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

    camCtrl = OrcaCtrlApp(shmimName)
    camCtrl.setWindowTitle(shmimName)
    camCtrl.show()
    camCtrl.Start()
    sys.exit(app.exec_())
