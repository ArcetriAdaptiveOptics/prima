"""Prima main control launcher — open Drop 1 (PWFS) and Drop 2 (DM) sub-GUIs."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QStatusBar, QGroupBox, QMessageBox,
)

from prima.gui.branding import build_brand_row, install_watermark


STYLESHEET = """
QMainWindow, QWidget { background-color: #0b1015; color: #e8eef7; }
QLabel#brand { font-size: 28px; font-weight: 700; color: #7ec8e3; }
QLabel#tagline { color: #8a9bb0; font-size: 13px; }
QLabel#body { color: #c5d0dc; font-size: 13px; }
QGroupBox {
  border: 1px solid #2a3441; border-radius: 4px; margin-top: 12px;
  font-weight: 600; color: #c5d0dc;
}
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
QPushButton {
  background: #1a2836; border: 1px solid #3a5168; border-radius: 3px;
  padding: 14px 18px; color: #e8eef7; font-size: 15px; font-weight: 600;
  min-height: 28px;
}
QPushButton:hover { background: #243446; border-color: #7ec8e3; }
QPushButton#primary { background: #1e4a5c; border-color: #7ec8e3; }
QStatusBar { color: #8a9bb0; }
"""


class ControlLauncher(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Prima — control')
        self.resize(720, 420)
        self.setStyleSheet(STYLESHEET)
        self._children = []

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(12)

        brand_row, _, _ = build_brand_row(
            'Main control · open Drop 1 / Drop 2',
            logo_height=36, variant='light')
        root.addLayout(brand_row)

        blurb = QLabel(
            'Launch the PWFS absolute-metrology GUI (Drop 1) or the BMC '
            'Multi-DM open-loop GUI (Drop 2). Each opens in its own window.')
        blurb.setObjectName('body')
        blurb.setWordWrap(True)
        root.addWidget(blurb)

        row = QHBoxLayout()
        row.setSpacing(14)

        drop1 = QGroupBox('Drop 1 · PWFS')
        d1 = QVBoxLayout(drop1)
        d1.addWidget(QLabel(
            'Aravis Manta + PI E-518 direct GCS\n'
            'Absolute optical metrology'))
        b1 = QPushButton('Open PWFS / Drop 1')
        b1.setObjectName('primary')
        b1.clicked.connect(self._open_drop1)
        d1.addWidget(b1)
        row.addWidget(drop1)

        drop2 = QGroupBox('Drop 2 · Science DM')
        d2 = QVBoxLayout(drop2)
        d2.addWidget(QLabel(
            'BMC Multi-DM 5.5 µm via DAO SHM\n'
            'daodm_bmc_ctrl → USB / sim'))
        b2 = QPushButton('Open DM / Drop 2')
        b2.setObjectName('primary')
        b2.clicked.connect(self._open_drop2)
        d2.addWidget(b2)
        row.addWidget(drop2)

        root.addLayout(row)
        root.addStretch(1)
        install_watermark(
            central, variant='light', opacity=0.08,
            anchor='bottom-right', height_hint=140)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage('Ready')

    def _spawn(self, args, label: str):
        try:
            proc = subprocess.Popen(args)
        except Exception as exc:
            QMessageBox.warning(self, 'Launch failed', str(exc))
            return
        self._children.append(proc)
        self.statusBar().showMessage('Started %s (pid %s)' % (label, proc.pid))

    def _open_drop1(self):
        self._spawn(
            [sys.executable, '-m', 'prima.gui.app', '--live'],
            'Drop1 PWFS')

    def _open_drop2(self):
        self._spawn(
            [sys.executable, '-m', 'prima.gui.dm_panel'],
            'Drop2 DM')

    def closeEvent(self, event):
        # Do not kill child GUIs — user may keep them open
        super().closeEvent(event)


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    parser = argparse.ArgumentParser(description='Prima main control launcher')
    parser.add_argument('--screenshot', metavar='PATH')
    parser.add_argument('--platform', default=None)
    args, qt_args = parser.parse_known_args(argv)
    if args.platform:
        os.environ['QT_QPA_PLATFORM'] = args.platform
    elif args.screenshot:
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

    app = QApplication(['prima-control'] + qt_args)
    win = ControlLauncher()
    win.show()
    if args.screenshot:
        QTimer.singleShot(350, lambda: (win.grab().save(args.screenshot), app.quit()))
    return app.exec_()


if __name__ == '__main__':
    sys.exit(main())
