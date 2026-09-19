#!/usr/bin/env python3
#
# compassRose.py
#
# RA/Dec orientation compass for the Ekarus fast-TT -> telescope offload.
#
# Draws, in the fast-TT command frame (vx = right, vy = up), where +RA (East)
# and +Dec (North) point, given the field-rotation angle theta published by
# computeTelescopeOffload.py:
#
#     (dAlpha, dDelta) = R(theta) . diag(Sx, Sy) . (vx, vy)
#     =>  (vx, vy) = diag(1/Sx, 1/Sy) . R(-theta) . (dAlpha, dDelta)
#
# so the +RA and +Dec sky axes map into the command frame through R(-theta) and
# the Sx/Sy scaling (unequal scales -> the N and E arrows are not exactly 90
# apart, which is correct and shown).
#
# Two checkboxes optionally overlay the current averaged TT command
# (fastttAvg - centre) and the offload vector (telTtOffload, converted from the
# TCS guiding convention back to sky via OFFLOAD_SKY_SIGN); both off by default
# (only the RA/Dec orientation is shown). With the offload on, its arrow is
# exactly opposite the TT-command arrow.
#
# Reads (all optional, shown as -- when absent):
#     SHM_TELESCOPE_THETA      theta [deg]
#     SHM_TELESCOPE_SCALE      [Sx, Sy]
#     SHM_TELESCOPE_RADEC      [RA, Dec]
#     SHM_TELESCOPE_ALTAZ      [Alt, Az, HA]
#     SHM_FASTTT_CMD_AVG       [vx, vy]
#     SHM_TELESCOPE_TT_OFFLOAD [dAlpha, dDelta]

import sys
import os
import math

import numpy as np
import dao

from PyQt5.uic import loadUiType
from PyQt5.QtCore import Qt, QTimer, QPointF
from PyQt5.QtGui import QPainter, QPen, QColor, QFont, QPolygonF
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout

import daoEkarusShmNames as shm_names

_here = os.path.dirname(os.path.abspath(__file__))
_uiPath = os.path.join(_here, 'compassRose.ui')
if not os.path.exists(_uiPath):
    _uiPath = os.path.join(os.getenv('DAOROOT', ''), 'data', 'compassRose.ui')
Ui_MainWindow, QMainWindow = loadUiType(_uiPath)

# Flip East/West if your instrument train has an odd number of reflections
# (sky-as-seen-on-detector is mirrored).
FLIP_EW = False

# PI tip-tilt stage mid-range: (0, 0) tip-tilt corresponds to command (50, 50),
# so the actual TT excursion drawn on the rose is fastttAvg - TT_CENTER.
# (matches the "- 50" in computeTelescopeOffload.py)
TT_CENTER = 50.0

# telTtOffload is stored in the TCS guiding convention, whose Dec axis is
# inverted w.r.t. sky (the "dAlphaDelta[1,0] = -dAlphaDelta[1,0]" line in
# computeTelescopeOffload.py). Undo it here so the compass shows the *sky*
# offload, which then comes out exactly opposite the TT-command arrow.
OFFLOAD_SKY_SIGN = (1.0, -1.0)   # (RA, Dec)

BG = QColor("#0b1740")
FG = QColor("#e8eef7")
GRID = QColor("#1c3a6e")
NCOL = QColor("#30c0a8")   # +Dec / North
ECOL = QColor("#5aa9ff")   # +RA / East
VCOL = QColor("#e8b84b")   # current TT command
OCOL = QColor("#ff6b6b")   # offload vector


def _open(name):
    return dao.shm(name) if os.path.exists(name) else None


def _read(shm):
    try:
        return np.asarray(shm.get_data(), dtype=float).ravel() if shm else None
    except Exception:
        return None


def _sky_to_cmd(dalpha, ddelta, t_rad, sx, sy):
    """(dAlpha, dDelta) sky vector -> (vx, vy) command-frame vector."""
    c, s = math.cos(t_rad), math.sin(t_rad)
    vx = (c * dalpha + s * ddelta) / (sx or 1.0)
    vy = (-s * dalpha + c * ddelta) / (sy or 1.0)
    return vx, vy


class CompassWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(340, 340)
        self.theta = 0.0
        self.sx = self.sy = 1.0
        self.v = np.zeros(2)
        self.off = np.zeros(2)
        self.show_v = False
        self.show_off = False

    def set_state(self, theta, sx, sy, v, off):
        self.theta, self.sx, self.sy = theta, sx, sy
        self.v, self.off = np.asarray(v, float), np.asarray(off, float)
        self.update()

    # -- helpers ------------------------------------------------------------
    def _screen(self, vx, vy):
        """command-frame (vx right, vy up) -> screen unit vector (y down)."""
        mx = -1.0 if FLIP_EW else 1.0
        n = math.hypot(vx, vy)
        if n < 1e-12:
            return 0.0, 0.0
        return mx * vx / n, -vy / n

    def _arrow(self, p, ux, uy, L, col, label, dashed=False):
        if ux == 0.0 and uy == 0.0:
            return
        tip = QPointF(L * ux, L * uy)
        pen = QPen(col, 2.4)
        if dashed:
            pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(0, 0), tip)

        ah, spread = 11.0, 0.5
        bx, by = -ux, -uy

        def rot(a):
            c, s = math.cos(a), math.sin(a)
            return QPointF(tip.x() + ah * (bx * c - by * s),
                           tip.y() + ah * (bx * s + by * c))

        p.setPen(QPen(col, 1))
        p.setBrush(col)
        p.drawPolygon(QPolygonF([tip, rot(spread), rot(-spread)]))

        p.setFont(QFont("Sans", 9, QFont.Bold))
        p.setPen(QPen(col))
        p.drawText(QPointF((L + 10) * ux - 14, (L + 10) * uy + 5), label)

    # -- paint ------------------------------------------------------------
    def paintEvent(self, _ev):
        w, h = self.width(), self.height()
        R = 0.40 * min(w, h)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), BG)
        p.translate(w / 2.0, h / 2.0)

        # ring + ticks
        p.setPen(QPen(GRID, 1))
        p.drawEllipse(QPointF(0, 0), R, R)
        for deg in range(0, 360, 15):
            a = math.radians(deg)
            r0 = R * (0.88 if deg % 45 == 0 else 0.93)
            p.drawLine(QPointF(r0 * math.cos(a), -r0 * math.sin(a)),
                       QPointF(R * math.cos(a), -R * math.sin(a)))

        # fixed command axes
        p.setPen(QPen(GRID, 1, Qt.DashLine))
        p.drawLine(QPointF(-R, 0), QPointF(R, 0))
        p.drawLine(QPointF(0, R), QPointF(0, -R))
        p.setPen(QPen(FG.darker(140)))
        p.setFont(QFont("Sans", 8))
        p.drawText(QPointF(R - 18, 13), "+vx")
        p.drawText(QPointF(7, -R + 12), "+vy")

        t = math.radians(self.theta)
        # +RA (East) and +Dec (North) directions in the command frame
        self._arrow(p, *self._screen(*_sky_to_cmd(1.0, 0.0, t, self.sx, self.sy)),
                    L=R * 0.86, col=ECOL, label="E +RA")
        self._arrow(p, *self._screen(*_sky_to_cmd(0.0, 1.0, t, self.sx, self.sy)),
                    L=R * 0.86, col=NCOL, label="N +Dec")

        # live vectors (toggleable)
        if self.show_v:
            vc = self.v - TT_CENTER            # excursion from the PI mid-range
            self._arrow(p, *self._screen(vc[0], vc[1]),
                        L=R * 0.6, col=VCOL, label="TT cmd", dashed=True)
        if self.show_off:
            offSky0 = self.off[0] * OFFLOAD_SKY_SIGN[0]
            offSky1 = self.off[1] * OFFLOAD_SKY_SIGN[1]
            ox, oy = _sky_to_cmd(offSky0, offSky1, t, self.sx, self.sy)
            self._arrow(p, *self._screen(ox, oy),
                        L=R * 0.5, col=OCOL, label="offload", dashed=True)

        p.end()


class Main(QMainWindow, Ui_MainWindow):
    _SHM = {
        'theta': 'SHM_TELESCOPE_THETA',
        'scale': 'SHM_TELESCOPE_SCALE',
        'radec': 'SHM_TELESCOPE_RADEC',
        'altaz': 'SHM_TELESCOPE_ALTAZ',
        'v': 'SHM_FASTTT_CMD_AVG',
        'off': 'SHM_TELESCOPE_TT_OFFLOAD',
    }

    def __init__(self):
        super(Main, self).__init__()
        self.setupUi(self)

        # the painted rose lives inside the 'compassFrame' placeholder from the .ui
        self.compass = CompassWidget()
        lay = QVBoxLayout(self.compassFrame)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.compass)

        self.cbTtCmd.toggled.connect(self._toggleArrows)
        self.cbOffload.toggled.connect(self._toggleArrows)
        self._toggleArrows(False)

        self.shm = {k: _open(getattr(shm_names, n)) for k, n in self._SHM.items()}
        for k, opened in self.shm.items():
            if opened is None:
                print("shm not found: %s (%s)" % (getattr(shm_names, self._SHM[k]), k))

        self.timer = QTimer(self)
        self.timer.setInterval(300)
        self.timer.timeout.connect(self.tick)

    def start(self):
        self.timer.start()
        self.tick()

    def _toggleArrows(self, _checked):
        self.compass.show_v = self.cbTtCmd.isChecked()
        self.compass.show_off = self.cbOffload.isChecked()
        self.compass.update()

    @staticmethod
    def _vec(d, n):
        return d[:n] if d is not None and d.size >= n else np.full(n, np.nan)

    def tick(self):
        th = self._vec(_read(self.shm['theta']), 1)
        theta = 0.0 if not np.isfinite(th[0]) else float(th[0])
        sc = self._vec(_read(self.shm['scale']), 2)
        sx = 1.0 if not np.isfinite(sc[0]) else float(sc[0])
        sy = 1.0 if not np.isfinite(sc[1]) else float(sc[1])
        ra, dec = self._vec(_read(self.shm['radec']), 2)
        ha = self._vec(_read(self.shm['altaz']), 3)[2]
        v = np.nan_to_num(self._vec(_read(self.shm['v']), 2))
        off = np.nan_to_num(self._vec(_read(self.shm['off']), 2))

        self.compass.set_state(theta, sx, sy, v, off)
        vc = v - TT_CENTER
        offSky = off * np.array(OFFLOAD_SKY_SIGN)
        self.infoLabel.setText(
            " RA  {:10.4f}    Dec {:10.4f}    HA {:9.3f}\n"
            " theta {:9.3f} deg     Sx {:.3f}   Sy {:.3f}\n"
            " TT cmd  ({:+8.3f}, {:+8.3f}) - center = ({:+8.3f}, {:+8.3f})\n"
            " offload shm ({:+8.3f}, {:+8.3f})   sky ({:+8.3f}, {:+8.3f}) arcsec"
            .format(ra, dec, ha, theta, sx, sy,
                    v[0], v[1], vc[0], vc[1],
                    off[0], off[1], offSky[0], offSky[1]))


if __name__ == '__main__':
    app = QApplication(sys.argv)
    main = Main()
    main.setWindowTitle('Ekarus RA/Dec Compass')
    main.show()
    main.start()
    sys.exit(app.exec_())
