#!/usr/bin/env python3
"""
Resolve a SHM_* handle name to its filepath string, as defined in a
config module (e.g. shm_config.py containing lines like:
    SHM_OCAM_FRAME = "/tmp/ocam2.im.shm"

Usage:
    python3 shm_path.py SHM_OCAM_FRAME
    python3 shm_path.py --config /path/to/daoEkarusShmNames.py SHM_OCAM_FRAME

In bash:
    path=$(python3 shm_path.py SHM_OCAM_FRAME)
    echo "$path"
"""

import argparse
import importlib.util
import os
import sys

import daoEkarusShmNames

def main():
    parser = argparse.ArgumentParser(description="Resolve a SHM handle to its filepath.")
    parser.add_argument("handle", help="Name of the SHM_* variable to resolve")
    args = parser.parse_args()


    if not hasattr(daoEkarusShmNames, args.handle):
        print(f"Error: handle '{args.handle}' not found in daoEkarusShmNames", file=sys.stderr)
        sys.exit(1)

    value = getattr(daoEkarusShmNames, args.handle)
    print(value)


if __name__ == "__main__":
    main()