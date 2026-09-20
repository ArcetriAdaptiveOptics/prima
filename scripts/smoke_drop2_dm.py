#!/usr/bin/env python
"""Smoke open-loop shapes against plico BMC sim (or in-process DemoDm)."""
from __future__ import annotations

import argparse
import sys
import time

import numpy as np


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--host', default='localhost')
    p.add_argument('--port', type=int, default=7050)
    p.add_argument('--demo', action='store_true',
                   help='Skip server; use in-process 140-act DemoDm')
    args = p.parse_args(argv)

    if args.demo:
        from prima.gui.dm_panel import DemoDm
        dm = DemoDm()
        print('backend=demo')

        def n_act():
            return dm.get_number_of_actuators()

        def set_shape(s):
            dm.set_shape(s)

        def get_shape():
            return dm.get_shape()
    else:
        import plico_dm
        time.sleep(0.2)
        dm = plico_dm.deformableMirror(args.host, args.port)
        print('backend=plico %s:%d' % (args.host, args.port))
        n_act = dm.get_number_of_actuators
        set_shape = dm.set_shape
        get_shape = dm.get_shape

    n = int(n_act())
    print('n_actuators=%d' % n)
    assert n == 140, 'expected 140-act BMC Multi-DM path, got %d' % n

    set_shape(np.zeros(n))
    poke = np.zeros(n)
    poke[3] = 0.12
    set_shape(poke)
    got = np.asarray(get_shape()).ravel()
    assert abs(got[3] - 0.12) < 1e-6
    set_shape(np.full(n, 0.5))
    print('smoke_ok poke+flat')
    return 0


if __name__ == '__main__':
    sys.exit(main())
