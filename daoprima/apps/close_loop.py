#!/usr/bin/env python3
"""daoEkarus-compatible closeLoop helper for DaoPrima SHM."""
import sys
import numpy as np
from daoprima import shm as shm_mod
from daoprima import shm_names as N
from daoprima.create_shm import create_default_graph


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    create_default_graph()
    path = argv[0] if argv else N.SHM_DM1_LOOP_CL_SWITCH
    lp = shm_mod.shm(path)
    lp.set_data(np.ones((1, 1), dtype=np.uint32))
    print('Loop Closed (%s)' % path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
