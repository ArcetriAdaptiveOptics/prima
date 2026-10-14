"""Live alignment viewer: 4 pyramid pupils + flux balance.

Used to centre the PSF on the pyramid apex with the manual tip-tilt of
the mount.  Goal: the 4 pupils equally bright (25 % each) with the
modulation OFF (R = 0) -> then also with small R.

    python scripts/aolab/align_viewer.py
"""
from __future__ import annotations

import sys
import time

import numpy as np
import pyqtgraph as pg
from PyQt5 import QtCore, QtWidgets

from prima.aolab.devices.camera_aravis import AravisCamera
from prima.aolab.wfs import find_pupils, PyramidProcessor
from prima.aolab.devices.pi_modulator import PiTipTiltModulator


def main():
    app = QtWidgets.QApplication(sys.argv[:1])
    cam = AravisCamera(exposure_ms=50.0)
    cam.set_binning(2)
    cam.start()
    mod = PiTipTiltModulator()
    mod.set_modulation(10.0, 20.0)
    time.sleep(1.0)
    frames = [cam.get_frame()[1] for _ in range(4)]
    try:
        geom = find_pupils(np.mean(frames, axis=0))
    except Exception as exc:
        # fall back to the geometry measured on 2026-10-09 (full frame / 2)
        print('find_pupils failed (%s): using stored geometry' % exc)
        from prima.aolab.wfs import PupilGeometry
        c = np.array([[514, 475], [549, 1640], [1686, 443], [1718, 1603]]) / 2.0
        geom = PupilGeometry(c, 195 / 2.0, frames[0].shape, 'stored 2026-10-09')
    proc = PyramidProcessor(geom, 32)
    mod.set_modulation(0.0)

    w = QtWidgets.QWidget()
    w.setWindowTitle('PRIMA - allineamento piramide (tip-tilt manuale)')
    w.setStyleSheet('QWidget{background:#0f1923;color:#dfe8f1;font-size:16px}'
                    'QPushButton{background:#1d3446;padding:6px}')
    lay = QtWidgets.QHBoxLayout(w)
    glw = pg.GraphicsLayoutWidget()
    vb = glw.addViewBox(lockAspect=True)
    img = pg.ImageItem()
    img.setColorMap(pg.colormap.get('inferno'))
    vb.addItem(img)
    ds = 2
    for k, (cy, cx) in enumerate(geom.centers):
        r = geom.radius / ds
        e = QtWidgets.QGraphicsEllipseItem(cx / ds - r, cy / ds - r, 2 * r, 2 * r)
        e.setPen(pg.mkPen('#40ff80'))
        vb.addItem(e)
        t = pg.TextItem(str(k), color='#40ff80')
        t.setPos(cx / ds, cy / ds)
        vb.addItem(t)
    lay.addWidget(glw, 3)
    side = QtWidgets.QVBoxLayout()
    lab = QtWidgets.QLabel()
    lab.setTextFormat(QtCore.Qt.RichText)
    side.addWidget(lab)
    bars = pg.PlotWidget(title='flux per pupil [%]')
    bars.setYRange(0, 60)
    bars.addLine(y=25, pen=pg.mkPen('#40ff80', style=QtCore.Qt.DashLine))
    bg = pg.BarGraphItem(x=[0, 1, 2, 3], height=[0] * 4, width=0.6,
                         brush='#2f8f9d')
    bars.addItem(bg)
    side.addWidget(bars, 1)
    hb = QtWidgets.QHBoxLayout()
    for r in (0, 2, 5, 10, 20):
        b = QtWidgets.QPushButton('R=%d' % r)
        b.clicked.connect(lambda _, r=r: mod.set_modulation(float(r)))
        hb.addWidget(b)
    side.addLayout(hb)
    lay.addLayout(side, 2)

    def refresh():
        try:
            _, f = cam.get_frame(wait_new=False)
        except Exception:
            return
        img.setImage(np.sqrt(np.clip(f[::ds, ::ds], 0, None)), autoLevels=True)
        I = proc.pupil_intensities(f).sum(axis=1)
        p = 100 * I / max(I.sum(), 1e-9)
        bg.setOpts(height=p)
        lr = (p[0] + p[2]) - (p[1] + p[3])
        bt = (p[0] + p[1]) - (p[2] + p[3])
        ok = max(abs(lr), abs(bt)) < 5
        col = '#40ff80' if ok else '#ffb060'
        lab.setText(
            '<b>R mod = %.1f mrad</b><br>'
            'pupille 0..3: %s %%<br>'
            '<span style="color:%s;font-size:22px">sinistra-destra %+.1f %%'
            '<br>basso-alto %+.1f %%</span><br>'
            'obiettivo: entrambi ~0 (4 x 25%%)<br>max %.0f ADU, %.1f fps'
            % (mod.radius, ' / '.join('%.1f' % v for v in p),
               col, lr, bt, f.max(), cam.get_fps()))

    tm = QtCore.QTimer()
    tm.timeout.connect(refresh)
    tm.start(150)
    w.resize(1500, 800)
    w.show()
    rc = app.exec_()
    mod.set_modulation(10.0)
    mod.close()
    cam.close()
    return rc


if __name__ == '__main__':
    sys.exit(main())
