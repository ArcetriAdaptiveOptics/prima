#!/usr/bin/env python3
import os, sys
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication
import numpy as np
from prima.gui.dm_panel import DmPanelWindow

def main():
    app = QApplication(['drop2-live'])
    win = DmPanelWindow(prefer='usb')
    win._mode.setCurrentIndex(1)
    win._on_start_ctrl()
    out = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'media', 'drop2-bmc-usb-live.png'))
    os.makedirs(os.path.dirname(out), exist_ok=True)

    def apply_flat():
        win._apply(np.full(140, 0.5, dtype=np.float32))
    def apply_poke():
        a = np.full(140, 0.5, dtype=np.float32); a[0] = 0.55; win._apply(a)
    def shot():
        win._refresh_status()
        ok = win.grab().save(out)
        print('grab_ok', ok, 'path', out)
        print('status_text:', repr(win._info.text()))
        print('usb:', win._usb_status)
        alive = win._ctrl_proc is not None and win._ctrl_proc.poll() is None
        print('ctrl_alive', alive)
        win._on_stop_ctrl()
        app.quit()
    QTimer.singleShot(800, apply_flat)
    QTimer.singleShot(1100, apply_poke)
    QTimer.singleShot(1600, shot)
    win.show()
    return app.exec_()

if __name__ == '__main__':
    sys.exit(main())
