#!/usr/bin/env python3
"""Unit smoke for direct PI E-518 modulator (requires lab hardware)."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main():
    from prima.hardware import PiGcsError, connect_pi_modulator

    host = os.environ.get('PRIMA_E518_HOST', '192.168.30.190')
    port = int(os.environ.get('PRIMA_E518_PORT', '50000'))
    try:
        mod = connect_pi_modulator(host=host, port=port)
    except PiGcsError as e:
        print('ABORT: %s' % e)
        return 2

    try:
        mod.setFrequencyInHz(20.0)
        mod.setCenterInMilliRad([0.0, 0.0])
        mod.setRadiusInMilliRad(1.0)
        time.sleep(0.4)
        assert mod.wavegen_running(), 'wavegen not running'
        st = mod.getStatus()
        assert abs(st.modulatorRadiusInMilliRad - 1.0) < 1e-9
        print('status', st)

        # POS peak-to-peak should be near 2*radius in mrad (calib SN 110032051)
        from prima.hardware.gcs_tcp import GcsTcp
        # reuse internal socket carefully — query via fresh short session would
        # fight the open connection; use modulator's locked gcs.
        g = mod._gcs
        pos = []
        for _ in range(40):
            raw = g.query('POS?', wait_s=0.12)
            vals = {}
            for part in raw.replace('\n', ' ').split():
                if '=' in part:
                    k, v = part.split('=', 1)
                    try:
                        vals[k] = float(v)
                    except ValueError:
                        pass
            if 'A' in vals and 'B' in vals:
                pos.append((vals['A'], vals['B']))
            time.sleep(0.005)
        pos = np.asarray(pos)
        lin, off = 0.87, -43.5
        mrad = lin * pos + off
        ptp_a = float(np.ptp(mrad[:, 0]))
        ptp_b = float(np.ptp(mrad[:, 1]))
        print('mrad_ptp_A=%.3f B=%.3f' % (ptp_a, ptp_b))
        # Expect roughly ~2 mrad ptp for 1 mrad radius (allow loose bench tolerance)
        if ptp_a < 0.5 or ptp_b < 0.5:
            print('FAIL: modulation amplitude too small')
            return 1
        mod.setRadiusInMilliRad(0.0)
        print('ALL_OK')
        return 0
    finally:
        try:
            mod.close()
        except Exception:
            pass


if __name__ == '__main__':
    sys.exit(main())
