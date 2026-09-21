#!/usr/bin/env python3
"""Drop 1 UI: exposure ↔ f_mod lock (unit / offscreen integration).

Rules under test:
  - Lock on → exposure spin disabled; t_exp = 1000/f_mod
  - Radius / center / gain never change exposure
  - Unlock → exposure spin editable again
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main():
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    from prima.gui.main_window import build_app

    app, win = build_app(['prima-gui'], demo=True)

    # Default: lock on, exposure spin disabled
    assert win._lock_exp.isChecked(), 'lock should default on'
    assert not win._exp_spin.isEnabled(), 'exposure spin must be disabled when locked'
    win._freq_spin.setValue(20.0)
    app.processEvents()
    assert abs(win._exp_spin.value() - 50.0) < 1e-6, win._exp_spin.value()
    assert abs(win._camera.exposureTime() - 50.0) < 1e-6
    print('lock_default_and_freq20_ok')

    # Radius must not touch exposure
    win._camera.setExposureTime(50.0)
    win._exp_spin.blockSignals(True)
    win._exp_spin.setValue(50.0)
    win._exp_spin.blockSignals(False)
    win._radius_spin.setValue(2.5)
    app.processEvents()
    win._mod_apply_timer.stop()
    win._apply_modulator()
    assert abs(win._exp_spin.value() - 50.0) < 1e-6, win._exp_spin.value()
    assert abs(win._camera.exposureTime() - 50.0) < 1e-6
    print('radius_keeps_exposure_ok')

    # Center must not touch exposure
    win._cx_spin.setValue(0.25)
    app.processEvents()
    win._mod_apply_timer.stop()
    assert abs(win._exp_spin.value() - 50.0) < 1e-6
    print('center_keeps_exposure_ok')

    # Frequency drives exposure while locked
    win._freq_spin.setValue(25.0)
    app.processEvents()
    assert abs(win._exp_spin.value() - 40.0) < 1e-6, win._exp_spin.value()
    assert abs(win._camera.exposureTime() - 40.0) < 1e-6
    assert not win._exp_spin.isEnabled()
    print('freq_lock_sets_exposure_ok')

    # Unlock enables spin; manual exposure sticks until lock again
    win._lock_exp.setChecked(False)
    app.processEvents()
    assert win._exp_spin.isEnabled()
    win._exp_spin.setValue(12.0)
    win._on_exposure_changed()
    assert abs(win._camera.exposureTime() - 12.0) < 1e-6
    win._radius_spin.setValue(1.0)
    app.processEvents()
    win._mod_apply_timer.stop()
    assert abs(win._exp_spin.value() - 12.0) < 1e-6
    print('unlock_allows_independent_exposure_ok')

    # Re-lock snaps exposure to 1/f and disables spin
    win._freq_spin.setValue(20.0)
    win._lock_exp.setChecked(True)
    app.processEvents()
    assert not win._exp_spin.isEnabled()
    assert abs(win._exp_spin.value() - 50.0) < 1e-6
    print('relock_snaps_exposure_ok')

    # Gain preset is radius-only
    for btn in win._gain_group.buttons():
        if abs(float(btn.property('gain_mrad')) - 4.0) < 1e-9:
            btn.click()
            break
    app.processEvents()
    win._mod_apply_timer.stop()
    assert abs(win._radius_spin.value() - 4.0) < 1e-6
    assert abs(win._exp_spin.value() - 50.0) < 1e-6
    print('gain_preset_keeps_exposure_ok')

    print('ALL_OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
