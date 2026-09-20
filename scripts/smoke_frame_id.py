#!/usr/bin/env python
"""Smoke: dedicated frame_id SHM propagation camera→recon→RTC→DM."""
from __future__ import annotations

import argparse
import runpy
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / 'smoke_drop2_daoprima.py'


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--frames', type=int, default=60)
    p.add_argument('--fps', type=float, default=80.0)
    p.add_argument('--cpu-only', action='store_true')
    p.add_argument('--plot', type=Path,
                   default=Path('media/frame-id-pipeline.png'))
    p.add_argument('--log', type=Path,
                   default=Path('media/frame-id-pipeline.json'))
    args = p.parse_args(argv)
    argv2 = [
        '--frames', str(args.frames),
        '--fps', str(args.fps),
        '--plot', str(args.plot),
        '--log', str(args.log),
    ]
    if args.cpu_only:
        argv2.append('--cpu-only')
    sys.argv = [str(SCRIPT)] + argv2
    try:
        runpy.run_path(str(SCRIPT), run_name='__main__')
    except SystemExit as e:
        rc = int(e.code or 0)
        if rc == 0:
            print('FRAME_ID_SMOKE_PASS log=%s plot=%s' % (args.log, args.plot))
        return rc
    print('FRAME_ID_SMOKE_PASS log=%s plot=%s' % (args.log, args.plot))
    return 0


if __name__ == '__main__':
    sys.exit(main())
