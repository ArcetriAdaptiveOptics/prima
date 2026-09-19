#!/usr/bin/env python3
#
# Ekarus telescope control display + hand paddle.
#
#   - telemetry panel: everything telescopeCtrl.py publishes from the TCS
#     (RA/Dec/Alt/Az/HA, tracking / slewing / power / limits, airmass, M2 focus,
#     dome shutter);
#   - offload conversion panel: the fast-TT -> telescope conversion parameters
#     from computeTelescopeOffload.py (theta0, Sx, Sy, theta) and the resulting
#     [dRA, dDec] offload vector (telTtOffload);
#   - a TELESCOPE CONTROL button (SHM_TELESCOPE_CONTROL_ENABLE): telescopeCtrl.py
#     only forwards corrections to the TCS while this is on (default OFF);
#   - an AUTO OFFLOAD button + Period / Gain spin boxes driving the
#     telescopeOffload.py control SHMs (enable / period / gain);
#   - guiding hand paddle: the +RA/-RA/+Dec/-Dec buttons write a [dRA, dDec]
#     nudge (arcsec, scaled by the Step box) into telGuiding; "0" clears it and
#     the running total;
#   - telescope offset hand paddle: same idea into telOffset (set_offset), but
#     the buttons are disabled while the telescope is slewing.
#
# Same theme / look as the other Ekarus GUIs (ekarusDmCtrl.py, EkarusCtrl.py).

from PyQt5.uic import loadUiType
import sys
import argparse
import os
import shutil
import subprocess

from PyQt5.QtWidgets import QApplication
from pyqtgraph.Qt import QtCore
import numpy as np
import dao

import daoEkarusShmNames as shm_names
from daoEkarusShmNames import (
    SHM_TELESCOPE_GUIDING,
    SHM_TELESCOPE_OFFSET,
    SHM_TELESCOPE_RADEC,
    SHM_TELESCOPE_ALTAZ,
    SHM_TELESCOPE_STATUS,
    SHM_TELESCOPE_AIRMASS,
    SHM_TELESCOPE_FOCUS,
    SHM_TELESCOPE_DOME,
    SHM_TELESCOPE_THETA0,
    SHM_TELESCOPE_SCALE,
    SHM_TELESCOPE_THETA,
    SHM_TELESCOPE_TT_OFFLOAD,
    SHM_TELESCOPE_CONTROL_ENABLE,
    SHM_TELESCOPE_OFFLOAD_ENABLE,
    SHM_TELESCOPE_OFFLOAD_PERIOD,
    SHM_TELESCOPE_OFFLOAD_GAIN,
    SHM_FASTTT_LOOP_CL_SWITCH,
)

_GOOD = "#30c0a8"
_WARN = "#e8b84b"
_BAD = "#ff6b6b"

_here = os.path.dirname(os.path.abspath(__file__))
_uiPath = os.path.join(_here, 'telescopeCtrlDisp.ui')
if not os.path.exists(_uiPath):
    _uiPath = os.path.join(os.getenv('DAOROOT', ''), 'data', 'telescopeCtrlDisp.ui')
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
    QPushButton:hover    { background-color: rgba(48, 192, 168, 0.30); }
    QPushButton:pressed  { background-color: rgba(48, 192, 168, 0.50); }
    QPushButton:disabled { background-color: rgba(24, 72, 120, 0.25);
                           color: #5a6b85; border: 1px solid #24506f; }
    QDoubleSpinBox { background-color: rgba(5, 12, 34, 0.6); color: #e8eef7;
                     border: 1px solid #1860a8; }
    QGroupBox {
        border: 1px solid #30c0a8;
        border-radius: 6px;
        margin-top: 10px;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 12px;
        padding: 0 5px;
        color: #7fe0d0;
        font-weight: bold;
    }
"""


class Main(QMainWindow, Ui_MainWindow):
    def __init__(self, shmGuidingName, shmRaDecName):
        super(Main, self).__init__()
        self.setupUi(self)
        self.setStyleSheet(DARK_STYLESHEET)

        self.shmGuidingName = shmGuidingName
        self.shmRaDecName = shmRaDecName

        self.guidingShm = self._openShm(shmGuidingName)
        self.offsetShm = self._openShm(shm_names.SHM_TELESCOPE_OFFSET)
        self.raDecShm = self._openShm(shmRaDecName)
        self.enableShm = self._openShm(shm_names.SHM_TELESCOPE_CONTROL_ENABLE)
        self.offloadEnableShm = self._openShm(shm_names.SHM_TELESCOPE_OFFLOAD_ENABLE)
        self.offloadPeriodShm = self._openShm(shm_names.SHM_TELESCOPE_OFFLOAD_PERIOD)
        self.offloadGainShm = self._openShm(shm_names.SHM_TELESCOPE_OFFLOAD_GAIN)

        # read-only telemetry / conversion params published by the RTC apps
        self.roShm = {
            'telRaDec': self.raDecShm,
            'telAltAz': self._openShm(shm_names.SHM_TELESCOPE_ALTAZ),
            'telStatus': self._openShm(shm_names.SHM_TELESCOPE_STATUS),
            'telAirmass': self._openShm(shm_names.SHM_TELESCOPE_AIRMASS),
            'telFocus': self._openShm(shm_names.SHM_TELESCOPE_FOCUS),
            'telDome': self._openShm(shm_names.SHM_TELESCOPE_DOME),
            'telTheta0': self._openShm(shm_names.SHM_TELESCOPE_THETA0),
            'telScale': self._openShm(shm_names.SHM_TELESCOPE_SCALE),
            'telTheta': self._openShm(shm_names.SHM_TELESCOPE_THETA),
            'telTtOffload': self._openShm(shm_names.SHM_TELESCOPE_TT_OFFLOAD),
            'fastttLoop': self._openShm(shm_names.SHM_FASTTT_LOOP_CL_SWITCH),
        }

        # running total of what has been sent, since the last "0"
        self.sentRa = 0.0
        self.sentDec = 0.0
        self._refreshTotals()

        # (dRA, dDec) unit vector per button
        self.btn_raP.clicked.connect(lambda: self._nudge(+1.0, 0.0))
        self.btn_raM.clicked.connect(lambda: self._nudge(-1.0, 0.0))
        self.btn_decP.clicked.connect(lambda: self._nudge(0.0, +1.0))
        self.btn_decM.clicked.connect(lambda: self._nudge(0.0, -1.0))
        self.btn_zero.clicked.connect(self._zero)
        self.controlEnableButton.toggled.connect(self._setEnable)
        self.openCompassButton.clicked.connect(self._openCompass)
        self._compass = None

        # auto fast-TT -> telescope offload loop (telescopeOffload.py)
        self.offloadEnableButton.toggled.connect(self._setOffloadEnable)
        self.offPeriodSpinBox.valueChanged.connect(self._setOffloadPeriod)
        self.offGainSpinBox.valueChanged.connect(self._setOffloadGain)
        self._seedFromShm(self.offPeriodSpinBox, self.offloadPeriodShm, 20.0)
        self._seedFromShm(self.offGainSpinBox, self.offloadGainShm, 0.5)

        # offset hand paddle (writes telOffset; disabled while slewing)
        self.btn_off_raP.clicked.connect(lambda: self._offsetNudge(+1.0, 0.0))
        self.btn_off_raM.clicked.connect(lambda: self._offsetNudge(-1.0, 0.0))
        self.btn_off_decP.clicked.connect(lambda: self._offsetNudge(0.0, +1.0))
        self.btn_off_decM.clicked.connect(lambda: self._offsetNudge(0.0, -1.0))
        self.btn_off_zero.clicked.connect(lambda: self._sendOffset(0.0, 0.0))
        self._offsetButtons = (self.btn_off_raP, self.btn_off_raM,
                               self.btn_off_decP, self.btn_off_decM,
                               self.btn_off_zero)

        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(300)
        self.timer.timeout.connect(self.Update)

    # ------------------------------------------------------------------
    @staticmethod
    def _openShm(name):
        # dao.shm() does not raise on a missing shm (it logs and hands back a
        # handle that segfaults on use), so check the backing file first.
        if not os.path.exists(name):
            print('shm not found, run daoEkarusCreateShm.py first: %s' % name)
            return None
        try:
            return dao.shm(name)
        except Exception as exc:
            print('could not open %s: %s' % (name, exc))
            return None

    # ------------------------------------------------------------------
    # hand paddle -> telGuiding
    # ------------------------------------------------------------------
    def _nudge(self, dRa, dDec):
        step = float(self.stepSpinBox.value())
        if self._send(dRa * step, dDec * step):
            self.sentRa += dRa * step
            self.sentDec += dDec * step
            self._refreshTotals()

    def _zero(self):
        self._send(0.0, 0.0)
        self.sentRa = 0.0
        self.sentDec = 0.0
        self._refreshTotals()

    def _refreshTotals(self):
        self.guidingTotalLabel.setText(
            'Σ  RA %+.2f  Dec %+.2f' % (self.sentRa, self.sentDec))

    def _send(self, dRa, dDec):
        if self.guidingShm is None:
            self.lastSentLabel.setText('last sent: FAILED (%s not available)'
                                       % self.shmGuidingName)
            return False
        self.guidingShm.set_data(np.array([[dRa], [dDec]], dtype=np.float32))
        self.lastSentLabel.setText(
            'last sent to telGuiding:  dRA=%+.2f  dDec=%+.2f arcsec' % (dRa, dDec))
        self.shmLabel.setText('shm: %s' % self.shmGuidingName)
        return True

    # ------------------------------------------------------------------
    # offset hand paddle -> telOffset  (only when not slewing)
    # ------------------------------------------------------------------
    def _offsetNudge(self, dRa, dDec):
        step = float(self.offStepSpinBox.value())
        self._sendOffset(dRa * step, dDec * step)

    def _sendOffset(self, dRa, dDec):
        if self.offsetShm is None:
            self.lastSentLabel.setText('last sent: FAILED (telOffset not available)')
            return
        self.offsetShm.set_data(np.array([[dRa], [dDec]], dtype=np.float32))
        self.lastSentLabel.setText(
            'last sent to telOffset:  dRA=%+.2f  dDec=%+.2f arcsec' % (dRa, dDec))
        self.shmLabel.setText('shm: %s' % shm_names.SHM_TELESCOPE_OFFSET)

    # ------------------------------------------------------------------
    # telescope-control master enable  (SHM_TELESCOPE_CONTROL_ENABLE)
    # ------------------------------------------------------------------
    def _setEnable(self, on):
        if self.enableShm is not None:
            self.enableShm.set_data(np.array([[1 if on else 0]], dtype=np.uint32))
        self._paintEnable(on)

    def _paintEnable(self, on):
        self.controlEnableButton.setText(
            'TELESCOPE CONTROL: ENABLED' if on else 'TELESCOPE CONTROL: DISABLED')
        self.controlEnableButton.setStyleSheet(
            'background-color: %s; color: #06121f; font-weight: bold;'
            % (_GOOD if on else _BAD))

    # ------------------------------------------------------------------
    # auto offload loop  (telescopeOffload.py control SHMs)
    # ------------------------------------------------------------------
    @staticmethod
    def _seedFromShm(spin, shm, default):
        v = default
        if shm is not None:
            try:
                v = float(np.asarray(shm.get_data(), dtype=float).ravel()[0])
            except Exception:
                pass
        spin.blockSignals(True)
        spin.setValue(v)
        spin.blockSignals(False)

    def _setOffloadEnable(self, on):
        if self.offloadEnableShm is not None:
            self.offloadEnableShm.set_data(
                np.array([[1 if on else 0]], dtype=np.uint32))
        self._paintOffloadEnable(on)

    def _paintOffloadEnable(self, on):
        self.offloadEnableButton.setText(
            'AUTO OFFLOAD: ACTIVE' if on else 'AUTO OFFLOAD: INACTIVE')
        self.offloadEnableButton.setStyleSheet(
            'background-color: %s; color: #06121f; font-weight: bold;'
            % (_GOOD if on else _BAD))

    def _setOffloadPeriod(self, v):
        if self.offloadPeriodShm is not None:
            self.offloadPeriodShm.set_data(np.array([[v]], dtype=np.float32))

    def _setOffloadGain(self, v):
        if self.offloadGainShm is not None:
            self.offloadGainShm.set_data(np.array([[v]], dtype=np.float32))

    # ------------------------------------------------------------------
    def _openCompass(self):
        """Launch compassRose.py (once); a second click re-runs it if it died."""
        if self._compass is not None and self._compass.poll() is None:
            return  # still running
        script = os.path.join(_here, 'compassRose.py')
        if not os.path.exists(script):
            script = shutil.which('compassRose.py') or 'compassRose.py'
        try:
            self._compass = subprocess.Popen([sys.executable, script])
        except Exception as exc:
            print('failed to open compassRose.py: %s' % exc)

    # ------------------------------------------------------------------
    def Start(self):
        self.timer.start()
        self.Update()

    def Stop(self):
        self.timer.stop()

    @staticmethod
    def _readShm(shm):
        if shm is None:
            return None
        try:
            return np.asarray(shm.get_data(), dtype=float).ravel()
        except Exception:
            return None

    @staticmethod
    def _fmt(v, prec=4):
        return '--' if v is None or not np.isfinite(v) else ('%.*f' % (prec, v))

    def _setValue(self, label, text, colour=None):
        label.setText(text)
        label.setStyleSheet('color: %s' % colour if colour else '')

    def _scalar(self, key, prec):
        d = self._readShm(self.roShm[key])
        return self._fmt(d[0] if d is not None and d.size else None, prec)

    @QtCore.pyqtSlot()
    def Update(self):
        # --- telescope status ---
        pos = self._readShm(self.raDecShm)
        self.raValueLabel.setText(self._fmt(pos[0] if pos is not None and pos.size else None, 5))
        self.decValueLabel.setText(self._fmt(pos[1] if pos is not None and pos.size > 1 else None, 5))

        aa = self._readShm(self.roShm['telAltAz'])
        for i, lbl in enumerate((self.altValueLabel, self.azValueLabel, self.haValueLabel)):
            lbl.setText(self._fmt(aa[i] if aa is not None and aa.size > i else None, 4))

        st = self._readShm(self.roShm['telStatus'])
        slew = None
        if st is not None and st.size >= 5:
            power, track, slew, halim, altlim = (st[k] > 0.5 for k in range(5))
            self._setValue(self.powerValueLabel, 'on' if power else 'OFF',
                           _GOOD if power else _BAD)
            self._setValue(self.trackingValueLabel, 'yes' if track else 'no',
                           _GOOD if track else _WARN)
            self._setValue(self.slewingValueLabel, 'yes' if slew else 'no',
                           _WARN if slew else None)
            lim = [n for n, f in (('HA', halim), ('ALT', altlim)) if f]
            self._setValue(self.limitsValueLabel, ', '.join(lim) if lim else 'clear',
                           _BAD if lim else _GOOD)
        else:
            for lbl in (self.powerValueLabel, self.trackingValueLabel,
                        self.slewingValueLabel, self.limitsValueLabel):
                self._setValue(lbl, '--')

        # offset paddle is only valid when the telescope is known not to be slewing
        if slew is None:
            offOk, hint, colour = False, 'status unknown', _WARN
        elif slew:
            offOk, hint, colour = False, 'SLEWING - disabled', _BAD
        else:
            offOk, hint, colour = True, '', None
        for b in self._offsetButtons:
            b.setEnabled(offOk)
        self._setValue(self.offsetSlewLabel, hint, colour)

        self.airmassValueLabel.setText(self._scalar('telAirmass', 3))
        self.focusValueLabel.setText(self._scalar('telFocus', 3))
        do = self._readShm(self.roShm['telDome'])
        if do is not None and do.size:
            self.domeValueLabel.setText(
                {0: 'closed', 1: 'partial', 2: 'open'}.get(int(round(do[0])), self._fmt(do[0], 0)))
        else:
            self.domeValueLabel.setText('--')

        # --- offload conversion ---
        self.theta0ValueLabel.setText(self._scalar('telTheta0', 2))
        self.thetaValueLabel.setText(self._scalar('telTheta', 3))
        sc = self._readShm(self.roShm['telScale'])
        self.sxValueLabel.setText(self._fmt(sc[0] if sc is not None and sc.size else None, 3))
        self.syValueLabel.setText(self._fmt(sc[1] if sc is not None and sc.size > 1 else None, 3))
        off = self._readShm(self.roShm['telTtOffload'])
        if off is not None and off.size >= 2:
            self.offloadValueLabel.setText('%+.3f , %+.3f' % (off[0], off[1]))
        else:
            self.offloadValueLabel.setText('--')

        # --- enable buttons reflect their shm (may be driven elsewhere) ---
        for shm, btn, paint in (
                (self.enableShm, self.controlEnableButton, self._paintEnable),
                (self.offloadEnableShm, self.offloadEnableButton, self._paintOffloadEnable)):
            v = self._readShm(shm)
            on = bool(v is not None and v.size and v[0] > 0.5)
            if on != btn.isChecked():
                btn.blockSignals(True)
                btn.setChecked(on)
                btn.blockSignals(False)
            paint(on)

        # period / gain spin boxes track the shm unless the user is editing them
        for spin, key in ((self.offPeriodSpinBox, self.offloadPeriodShm),
                          (self.offGainSpinBox, self.offloadGainShm)):
            if not spin.hasFocus():
                d = self._readShm(key)
                if d is not None and d.size and abs(d[0] - spin.value()) > 1e-6:
                    spin.blockSignals(True)
                    spin.setValue(float(d[0]))
                    spin.blockSignals(False)

        # --- auto offload status line ---
        oOn = bool(self.offloadEnableButton.isChecked())
        lp = self._readShm(self.roShm['fastttLoop'])
        loop = ('closed' if lp is not None and lp.size and lp[0] > 0.5 else
                ('OPEN' if lp is not None and lp.size else '--'))
        gain = self.offGainSpinBox.value()
        per = self.offPeriodSpinBox.value()
        if oOn and loop != 'closed':
            self._setValue(self.offloadStatusLabel,
                           'auto offload ACTIVE but fast-TT loop %s - not offloading' % loop,
                           _WARN)
        elif oOn:
            self._setValue(self.offloadStatusLabel,
                           'auto offload ACTIVE - gain %.2f, every %.0f s (loop closed)' % (gain, per),
                           _GOOD)
        else:
            self._setValue(self.offloadStatusLabel,
                           'auto offload inactive   (loop %s)' % loop, None)

        missing = [n for n, s in self.roShm.items() if s is None]
        self.telemetryStatusLabel.setText(
            'telemetry OK' if not missing else 'telemetry: missing ' + ', '.join(missing))


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="telescopeCtrlDisp.py",
        description=(
            "Ekarus telescope control display + hand paddle. Shows the TCS "
            "telemetry and the fast-TT offload conversion, an Enable button for "
            "SHM_TELESCOPE_CONTROL_ENABLE, and RA/Dec nudge buttons that write "
            "telGuiding."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--shmGuiding", default=shm_names.SHM_TELESCOPE_GUIDING,
                   metavar="SHM",
                   help="telescope guiding-correction shm ([x, y] arcsec)")
    p.add_argument("--shmRaDec", default=shm_names.SHM_TELESCOPE_RADEC,
                   metavar="SHM",
                   help="telescope RA/Dec readback shm ([RA, Dec] deg)")
    return p.parse_args(argv)


if __name__ == '__main__':
    args = parse_args()

    app = QApplication([])
    main = Main(args.shmGuiding, args.shmRaDec)
    main.setWindowTitle('Ekarus Telescope Control Display')
    main.show()
    main.Start()
    sys.exit(app.exec_())
