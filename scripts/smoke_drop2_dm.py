#!/usr/bin/env python
"""Smoke open-loop shapes via DAO SHM + daodm_bmc_ctrl (sim by default)."""
from __future__ import annotations

import argparse
import sys

import numpy as np

from daoprima.bridges import ShmCommandWriter
from daoprima.create_shm import create_default_graph
from daoprima.hw.bmc_dm import open_bmc_dm
from daoprima import shm_names as N


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--prefer', default='sim',
                   choices=['auto', 'usb', 'vendor', 'sim'])
    args = p.parse_args(argv)

    create_default_graph()
    dm = open_bmc_dm(prefer=args.prefer)
    writer = ShmCommandWriter()
    n = dm.num_actuators()
    print('backend=%s serial=%s n=%d shm=%s' % (
        dm.backend, dm.serial, n, N.SHM_DM1_CMD))

    flat = np.full(n, 0.5, dtype=np.float32)
    writer.set_shape(flat)
    dm.send_data(writer.get_shape())
    poke = flat.copy()
    poke[10] = 0.6
    writer.set_shape(poke)
    dm.send_data(writer.get_shape())
    rb = dm.get_actuator_data()
    print('poke_act10=%.3f readback=%.3f' % (poke[10], float(rb[10])))
    dm.send_data(flat)
    dm.close()
    print('smoke_drop2_dao_ok')
    return 0


if __name__ == '__main__':
    sys.exit(main())
