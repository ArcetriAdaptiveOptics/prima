#!/usr/bin/env python
"""Headless smoke: engine measure + GUI take-once (offscreen)."""
from __future__ import annotations

import os
import sys


def smoke_engine():
    from prima.metrology.engine import MetrologyEngine, MODULATION_GAIN_PRESETS_MRAD
    e = MetrologyEngine()
    centers, r = e.find_pupils_from_frame()
    assert len(centers) == 4, centers
    assert r > 0
    e.set_modulation_radius_mrad(MODULATION_GAIN_PRESETS_MRAD[2])
    m = e.take_measurement(frames_to_average=2)
    products = e.measurement_products(remove_zernikes=[2, 3])
    assert products['slopes'].shape[0] > 10
    assert products['wavefront_nm'].size > 10
    assert len(products['zernike_nm']) >= 5
    new, tt = e.auto_align_step()
    assert len(new) == 2
    print('engine_ok pupils_r=%.1f rms_nm=%.2f slopes=%s wf=%s' % (
        r, products['rms_nm'], products['slopes'].shape,
        products['wavefront_nm'].shape))
    return True


def smoke_gui():
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from prima.gui.main_window import build_app
    app, win = build_app(['smoke'], demo=True)
    for _ in range(3):
        win._on_tick()
        app.processEvents()
    win._on_find_pupils()
    win._on_take_once()
    app.processEvents()
    assert win._engine.last_measure() is not None
    products = win._engine.measurement_products()
    assert products['rms_nm'] == products['rms_nm']  # finite check via display
    # gain preset
    btn = win._gain_group.button(3)
    btn.click()
    app.processEvents()
    assert abs(win._radius_spin.value() - 4.0) < 1e-6
    win.close()
    print('gui_ok rms_nm=%.2f' % products['rms_nm'])
    return True


if __name__ == '__main__':
    smoke_engine()
    smoke_gui()
    print('SMOKE_OK')
    sys.exit(0)
