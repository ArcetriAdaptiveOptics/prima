#!/usr/bin/env python3
#
# Ekarus DM channel modal control GUI.
#
# Drives one DM command channel (shm passed with -s) through the M2C modal basis.
# Same idea as daoDmCtrl.py, but poppy-free: the modes displayed and applied are
# taken straight from the M2C (modes-to-command) matrix.  Each column of the M2C
# is one mode expressed as a 468-actuator command vector; the DM map is used to
# scatter that vector back into a 2D image, so no analytic (poppy) basis is
# needed to show the mode being controlled.

from PyQt5.uic import loadUiType
import sys
import argparse
import os

from PyQt5.QtWidgets import QApplication
from pyqtgraph.Qt import QtCore
import numpy as np
import pyqtgraph as pg
import dao
import daoEkarusShmNames as shm_names

# ---------------------------------------------------------------------------
# Ekarus GUI theme (matches GUIUtils.py / EkarusCtrl.ui)
# ---------------------------------------------------------------------------
THEME_BG = "#0b1740"
THEME_FG = "#e8eef7"
MODE_CMAP = "viridis"

pg.setConfigOption('background', THEME_BG)
pg.setConfigOption('foreground', THEME_FG)

# Load the .ui next to this file, falling back to the installed copy.
_here = os.path.dirname(os.path.abspath(__file__))
_uiPath = os.path.join(_here, 'ekarusDmChannelCtrl.ui')
if not os.path.exists(_uiPath):
    _uiPath = os.path.join(os.getenv('DAOROOT', ''), 'data', 'ekarusDmChannelCtrl.ui')
Ui_MainWindow, QMainWindow = loadUiType(_uiPath)

DARK_STYLESHEET = """
    QMainWindow, QWidget {
        background-color: #0b1740;
        color: #e8eef7;
    }
    QPushButton {
        background-color: rgba(24, 72, 120, 0.55);
        color: #eaf6f2;
        border: 1px solid #30c0a8;
        border-radius: 4px;
        padding: 3px 6px;
    }
    QPushButton:hover   { background-color: rgba(48, 192, 168, 0.30); }
    QPushButton:pressed { background-color: rgba(48, 192, 168, 0.50); }
    QPushButton:checked { background-color: rgba(48, 192, 168, 0.50); }
    QCheckBox, QLabel   { color: #e8eef7; }
    QDoubleSpinBox, QSpinBox, QComboBox {
        background-color: rgba(5, 12, 34, 0.6);
        color: #e8eef7;
        border: 1px solid #1860a8;
    }
    QSlider::groove:horizontal {
        background: rgba(5, 12, 34, 0.6);
        height: 6px;
        border-radius: 3px;
    }
    QSlider::handle:horizontal {
        background: #30c0a8;
        width: 14px;
        height: 14px;
        margin: -4px 0;
        border-radius: 7px;
    }
    QSlider::sub-page:horizontal {
        background: #1860a8;
        border-radius: 3px;
    }
"""

NMODES = 10  # number of sliders / modes exposed by the GUI


class Main(QMainWindow, Ui_MainWindow):
    def __init__(self, dmId, shmDmName, shmMapName, shmM2cName):
        super(Main, self).__init__()
        self.setupUi(self)
        self.setStyleSheet(DARK_STYLESHEET)

        self.dmId = dmId
        self.scale = 100.0

        # --- SHM objects ----------------------------------------------------
        print(shmDmName)
        self.shmdm  = dao.shm(shmDmName)
        self.shmMap = dao.shm(shmMapName)
        self.shmM2c = dao.shm(shmM2cName)

        self.dmMap = self.shmMap.get_data()
        self.mapH, self.mapW = self.dmMap.shape
        self.nAct = int((self.dmMap == 1).sum())

        # M2C: shape (nAct, nModes).  Column k is mode k as an actuator command.
        self.m2c = np.asarray(self.shmM2c.get_data(), dtype=np.float32)
        if self.m2c.shape[0] != self.nAct:
            # tolerate a transposed matrix
            self.m2c = self.m2c.T
        self.nAvail = min(NMODES, self.m2c.shape[1])

        # per-mode amplitude (volt), driven by the sliders
        self.z = np.zeros(NMODES, dtype=np.float32)

        # --- image items --------------------------------------------------
        self.vbMain = pg.ViewBox()
        self.graphicsView.setCentralItem(self.vbMain)
        self.vbMain.setAspectLocked(True)
        self.imgMain = pg.ImageItem()
        self.imgMain.setColorMap(MODE_CMAP)
        self.vbMain.addItem(self.imgMain)
        self.vbMain.setRange(QtCore.QRectF(0, 0, self.mapW, self.mapH))

        self.hist = pg.HistogramLUTItem()
        self.hist.setImageItem(self.imgMain)
        self.hist.gradient.loadPreset(MODE_CMAP)
        self.hist.setLevels(-0.1, 0.1)
        self.graphicsView_11.setCentralItem(self.hist)

        # one small preview per mode, built from the M2C column + DM map
        self.modeViews = []
        self.modeImgs = []
        for k in range(NMODES):
            gv = getattr(self, 'graphicsView_%d' % (k + 1))
            vb = pg.ViewBox()
            gv.setCentralItem(vb)
            vb.setAspectLocked(True)
            img = pg.ImageItem()
            img.setColorMap(MODE_CMAP)
            vb.addItem(img)
            self.modeViews.append(vb)
            self.modeImgs.append(img)
            img.setImage(self._modeImage(k))

        # accumulated command shape shown in the main view
        self.modeShape = np.full((self.mapH, self.mapW), np.nan, dtype=np.float32)
        self.imgMain.setImage(np.nan_to_num(self.modeShape), autoLevels=False)

        # --- slider wiring ----------------------------------------------
        for k in range(NMODES):
            slider = getattr(self, 'horizontalSlider_%d' % (k + 1))
            slider.valueChanged.connect(self._makeSliderCB(k))
            if k >= self.nAvail:
                slider.setEnabled(False)
                getattr(self, 'label_%d' % (k + 1)).setText('n/a')

        self.pushButton.clicked.connect(self.ResetZ)
        self.autoScaleCheckBox.toggled.connect(lambda _: self._setMainImage(self.modeShape))

        # --- refresh timer --------------------------------------------
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.Update)

        # Show the channel's current content without touching the DM: opening
        # the GUI must not write (reset) the channel.
        self._showCurrentChannel()

    # ------------------------------------------------------------------
    def _modeImage(self, k):
        """2D image of mode k: scatter its M2C column through the DM map."""
        img = np.full((self.mapH, self.mapW), np.nan, dtype=np.float32)
        if k < self.m2c.shape[1]:
            img[self.dmMap == 1] = self.m2c[:, k]
        return img

    def _makeSliderCB(self, k):
        def cb():
            amplitude = float(getattr(self, 'horizontalSlider_%d' % (k + 1)).value())
            volt = amplitude / self.scale
            getattr(self, 'label_%d' % (k + 1)).setText('%.2f volt' % volt)
            self.z[k] = np.float32(volt)
            self.SendToDM()
        return cb

    def ResetZ(self):
        for k in range(NMODES):
            getattr(self, 'horizontalSlider_%d' % (k + 1)).setValue(0)
        # setValue already fires the callbacks, but force a clean push anyway
        self.z[:] = 0
        self.SendToDM()

    # ------------------------------------------------------------------
    def _setMainImage(self, shape2d):
        """Push a 2D shape to the main view, honouring the auto-scale toggle.

        Auto-scale on : stretch the colour map to the actuator values only
                        (NaN background excluded), so even a small pure tilt
                        fills the full range.
        Auto-scale off: leave the levels wherever the histogram is set, so the
                        user can pin a fixed scale and read absolute amplitude.
        """
        self.imgMain.setImage(np.nan_to_num(shape2d), autoLevels=False)
        if self.autoScaleCheckBox.isChecked():
            finite = shape2d[np.isfinite(shape2d)]
            if finite.size and float(np.ptp(finite)) > 0:
                lo, hi = float(np.min(finite)), float(np.max(finite))
            else:
                lo, hi = -1e-6, 1e-6
            self.imgMain.setLevels((lo, hi))
            self.hist.setLevels(lo, hi)

    def _showCurrentChannel(self):
        """Render the channel's current command in the main view (read only)."""
        cur = np.nan_to_num(self.shmdm.get_data())
        self.modeShape[:] = np.nan
        self.modeShape[self.dmMap == 1] = cur[:, 0]
        self._setMainImage(self.modeShape)

    def SendToDM(self):
        """Combine the active modes into a 468 command vector and push it."""
        cmd = np.zeros((self.nAct, 1), dtype=np.float32)
        for k in range(self.nAvail):
            cmd[:, 0] += self.z[k] * self.m2c[:, k]
        cmd = np.nan_to_num(cmd)
        self.shmdm.set_data(cmd.astype(np.float32))

        # update the accumulated shape shown in the main view
        self.modeShape[:] = np.nan
        self.modeShape[self.dmMap == 1] = cmd[:, 0]
        self._setMainImage(self.modeShape)

    def Start(self):
        self.timer.start()

    def Stop(self):
        self.timer.stop()

    @QtCore.pyqtSlot()
    def Update(self):
        # As long as no mode is dialed in, track the channel's live content;
        # once the sliders are used, show what this GUI is applying.
        if not np.any(self.z):
            self._showCurrentChannel()
        else:
            self._setMainImage(self.modeShape)


def parse_args(argv=None):
    """Parse the command line.

    All arguments are optional; the defaults target DM1 and the shm names
    declared in daoEkarusShmNames.py, so the GUI can be started with no
    arguments at all:

        ekarusDmChannelCtrl.py

    or pointed at another command channel / DM:

        ekarusDmChannelCtrl.py -s /tmp/dm1CmdOffset.im.shm
    """
    p = argparse.ArgumentParser(
        prog="ekarusDmChannelCtrl.py",
        description=(
            "Ekarus DM channel modal control GUI. Drives one DM command "
            "channel (-s) through the M2C modal basis: each column of the M2C "
            "is one mode, applied to the channel and rendered in 2D through "
            "the DM map -- no poppy / analytic basis needed. The 10 sliders "
            "set the amplitude (in volt) of the first 10 M2C modes; Reset "
            "zeroes them."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("-i", "--dmId", default="1",
                   help="DM identifier (used in the window title only)")
    p.add_argument("-s", "--shmDm", default=shm_names.SHM_DM1_CHANNEL_3,
                   metavar="SHM",
                   help="DM command channel shm to drive (468x1 float32)")
    p.add_argument("-m", "--shmMap", default=shm_names.SHM_DM1_468_MASK,
                   metavar="SHM",
                   help="DM actuator map shm: binary mask of the controlled "
                        "actuators")
    p.add_argument("-z", "--shmM2c", default=shm_names.SHM_DM1_M2C,
                   metavar="SHM",
                   help="modes-to-command (M2C) matrix shm (nAct x nModes "
                        "float32)")
    return p.parse_args(argv)


if __name__ == '__main__':
    args = parse_args()

    app = QApplication([])
    main = Main(args.dmId, args.shmDm, args.shmMap, args.shmM2c)
    main.setWindowTitle('Ekarus DM%s Channel Control  [%s]'
                        % (args.dmId, os.path.basename(args.shmDm)))
    main.show()
    main.Start()
    sys.exit(app.exec_())
