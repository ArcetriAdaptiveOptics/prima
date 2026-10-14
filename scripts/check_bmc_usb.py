#!/usr/bin/env python3
"""One-shot BMC Multi-DM USB functionality check (DAO path)."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

from daoprima.hw.bmc_dm import open_bmc_dm, probe_bmc_usb
from daoprima.hw.bmc_usb import floats_to_dac, load_map, pack_frame
import numpy as np


def main() -> int:
    ts = datetime.now(timezone.utc).isoformat()
    probe = probe_bmc_usb()
    report = {
        'timestamp_utc': ts,
        'host': 'alienware-m16-R2',
        'probe_present': probe.present,
        'probe_message': probe.message,
        'probe_devices': probe.devices,
        'cypress_bootloader': probe.cypress_bootloader,
        'expected_vid_pid': '1781:0ed8 (Multi)',
        'map': None,
        'open': None,
        'poke': None,
    }

    try:
        m = load_map('MULTI140.map')
        report['map'] = {
            'name': 'MULTI140.map',
            'len': int(m.size),
            'min': int(m.min()),
            'max': int(m.max()),
        }
        # dry-run pack
        frame = pack_frame(np.full(140, 0.5), m)
        report['map']['frame_bytes'] = len(frame)
        report['map']['mid_dac'] = int(floats_to_dac(np.array([0.5]))[0])
    except Exception as exc:
        report['map'] = {'error': str(exc)}

    prefer = 'usb' if probe.present else 'sim'
    try:
        dm = open_bmc_dm(prefer=prefer if probe.present else 'auto')
        report['open'] = {
            'backend': dm.backend,
            'serial': dm.serial,
            'n_actuators': dm.num_actuators(),
            'message': dm.info.message,
        }
        # safe: flat mid + small poke on act 0, then back to mid
        flat = np.full(dm.num_actuators(), 0.5, dtype=float)
        dm.send_data(flat)
        poke = flat.copy()
        poke[0] = 0.55
        dm.send_data(poke)
        rb = dm.get_actuator_data()
        dm.send_data(flat)
        report['poke'] = {
            'ok': True,
            'poke_act0': 0.55,
            'readback_act0': float(rb[0]) if rb.size else None,
            'readback_mean': float(np.mean(rb)) if rb.size else None,
        }
        dm.close()
    except Exception as exc:
        report['open'] = {'error': str(exc)}
        report['poke'] = {'ok': False, 'error': str(exc)}

    print(json.dumps(report, indent=2))
    # Non-zero only on hard failure of sim path; missing USB is reported in JSON
    if report.get('poke') and report['poke'].get('ok'):
        return 0
    return 1


if __name__ == '__main__':
    sys.exit(main())
