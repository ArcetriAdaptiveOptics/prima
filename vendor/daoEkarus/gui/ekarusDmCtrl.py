#!/usr/bin/env python3
#
# Ekarus DM control GUI.
#
# Mirrors the "DM Channels" region of EkarusCtrl.py: it shows the DM command map
# for every DM1 command channel (same DmShapeView / DM map rendering), plus:
#   - the combined DM command (dm1Cmd),
#   - an extra "DM offset" channel (dm1CmdOffset), rendered in 2D through the DM
#     map exactly the way the offset is applied to the DM,
#   - one button per channel that opens ekarusDmChannelCtrl.py on that channel.

from PyQt5.uic import loadUiType
import sys
import argparse
import os
import time
import subprocess

from PyQt5.QtWidgets import QApplication
from pyqtgraph.Qt import QtCore
import numpy as np
import pyqtgraph as pg
import dao

import daoEkarusShmNames as shm_names
from daoEkarusShmNames import (
    SHM_DM1_CMD,
    SHM_DM1_CHANNEL_0,
    SHM_DM1_CHANNEL_1,
    SHM_DM1_CHANNEL_2,
    SHM_DM1_CHANNEL_3,
    SHM_DM1_CMD_OFFSET,
    SHM_DM1_468_MASK,
    SHM_DM1_M2C,
)
from GUIUtils import DmShapeView, THEME_BG, THEME_FG

MODE_CMAP = "viridis"
pg.setConfigOption('background', THEME_BG)
pg.setConfigOption('foreground', THEME_FG)

_here = os.path.dirname(os.path.abspath(__file__))
_uiPath = os.path.join(_here, 'ekarusDmCtrl.ui')
if not os.path.exists(_uiPath):
    _uiPath = os.path.join(os.getenv('DAOROOT', ''), 'data', 'ekarusDmCtrl.ui')
Ui_MainWindow, QMainWindow = loadUiType(_uiPath)

DARK_STYLESHEET = """
    QMainWindow, QWidget { background-color: #0b1740; color: #e8eef7; }
    QLabel { color: #e8eef7; }
    QPushButton {
        background-color: rgba(24, 72, 120, 0.55);
        color: #eaf6f2;
        border: 1px solid #30c0a8;
        border-radius: 4px;
        padding: 3px 6px;
    }
    QPushButton:hover   { background-color: rgba(48, 192, 168, 0.30); }
    QPushButton:pressed { background-color: rgba(48, 192, 168, 0.50); }
"""

# suffix -> (title, shm name, has "open channel ctrl" button)
# Layout order: top row = ch0, ch1, dm1Cmd ; bottom row = ch2, ch3, dm offset.
CHANNELS = [
    ('0',     'Channel 0 - flat',           SHM_DM1_CHANNEL_0,  True),
    ('1',     'Channel 1 - integrator',     SHM_DM1_CHANNEL_1,  True),
    ('total', 'DM command (dm1Cmd)',        SHM_DM1_CMD,        False),
    ('2',     'Channel 2',                  SHM_DM1_CHANNEL_2,  True),
    ('3',     'Channel 3',                  SHM_DM1_CHANNEL_3,  True),
    ('off',   'DM offset (dm1CmdOffset)',   SHM_DM1_CMD_OFFSET, True),
]


class Main(QMainWindow, Ui_MainWindow):
    def __init__(self, dmId, shmMapName, shmM2cName):
        super(Main, self).__init__()
        self.setupUi(self)
        self.setStyleSheet(DARK_STYLESHEET)

        self.dmId = dmId
        self.shmMapName = shmMapName
        self.shmM2cName = shmM2cName
        self._children = []

        self.shmMap = dao.shm(shmMapName)
        self.dmMask = self.shmMap.get_data()

        self.panels = {}   # suffix -> dict(shm, view, minmax label)
        for suffix, title, shmName, hasBtn in CHANNELS:
            gv = getattr(self, 'graphicsView_%s' % suffix)
            view = DmShapeView(gv, self.dmMask, colormap=MODE_CMAP)
            self.panels[suffix] = {
                'shm': dao.shm(shmName),
                'name': shmName,
                'view': view,
                'minmax': getattr(self, 'minmaxLabel_%s' % suffix),
            }
            if hasBtn:
                btn = getattr(self, 'openButton_%s' % suffix)
                btn.clicked.connect(self._makeOpenCB(shmName))

        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.Update)

    # ------------------------------------------------------------------
    def _makeOpenCB(self, shmName):
        def cb():
            self._openChannelCtrl(shmName)
        return cb

    def _openChannelCtrl(self, shmName):
        script = os.path.join(_here, 'ekarusDmChannelCtrl.py')
        cmd = [sys.executable, script,
               '-i', str(self.dmId),
               '-s', shmName,
               '-m', self.shmMapName,
               '-z', self.shmM2cName]
        try:
            self._children.append(subprocess.Popen(cmd))
        except Exception as exc:
            print('failed to open %s: %s' % (script, exc))

    # ------------------------------------------------------------------
    def Start(self):
        self.timer.start()
        self.Update()

    def Stop(self):
        self.timer.stop()

    @QtCore.pyqtSlot()
    def Update(self):
        mask = self.shmMap.get_data()
        for suffix, panel in self.panels.items():
            cmd = panel['shm'].get_data()
            panel['view'].update_shape(cmd, mask)
            panel['minmax'].setText('min %.3f   max %.3f'
                                    % (np.min(cmd[:, 0]), np.max(cmd[:, 0])))


def parse_args(argv=None):
    """Parse the command line.

    All arguments are optional and default to DM1 / the shm names from
    daoEkarusShmNames.py, so the GUI starts with no arguments:

        ekarusDmCtrl.py
    """
    p = argparse.ArgumentParser(
        prog="ekarusDmCtrl.py",
        description=(
            "Ekarus DM control GUI. Shows the DM command map for every DM1 "
            "command channel (same rendering as the 'DM Channels' panel of "
            "EkarusCtrl): the combined command (dm1Cmd), channels 0-3, and "
            "the static DM offset (dm1CmdOffset), each drawn in 2D through "
            "the DM map. One button per channel opens ekarusDmChannelCtrl.py "
            "on that channel for modal poking."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("-i", "--dmId", default="1",
                   help="DM identifier (window title, and passed on to "
                        "ekarusDmChannelCtrl.py)")
    p.add_argument("-m", "--shmMap", default=shm_names.SHM_DM1_468_MASK,
                   metavar="SHM",
                   help="DM actuator map shm: binary mask of the controlled "
                        "actuators")
    p.add_argument("-z", "--shmM2c", default=shm_names.SHM_DM1_M2C,
                   metavar="SHM",
                   help="modes-to-command (M2C) matrix shm, forwarded to "
                        "ekarusDmChannelCtrl.py")
    return p.parse_args(argv)


if __name__ == '__main__':
    args = parse_args()

    app = QApplication([])
    main = Main(args.dmId, args.shmMap, args.shmM2c)
    main.setWindowTitle('Ekarus DM%s Control' % args.dmId)
    main.show()
    main.Start()
    sys.exit(app.exec_())
