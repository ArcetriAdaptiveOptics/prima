#!/usr/bin/env python3
"""
TTM Controller - Tip-Tilt Mirror control via PI E-518
Reads commands from shared memory and sends them to the controller.

Usage: ttmController.py <shmName> <ip> <ctrlModel> [options]

Arguments:
  shmName     Shared memory path
  ip          Controller IP address
  ctrlModel   Controller model

Options:
  --center    Center position as 'A,B' in controller units (default: 50.0,50.0)
  --help      Show this help message

Example:
  ttmController.py /tmp/ttm1Cmd.im.shm 192.168.68.47 E-518
  ttmController.py /tmp/ttm1Cmd.im.shm 192.168.68.47 E-518 --center 55.0,45.0
"""

import dao
import numpy as np
import sys
import argparse
from pipython import GCSDevice
import time


def parse_args():
    parser = argparse.ArgumentParser(
        description='TTM Controller - Tip-Tilt Mirror control via PI E-518',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s /tmp/ttm1Cmd.im.shm 192.168.68.47 E-518
  %(prog)s /tmp/ttm1Cmd.im.shm 192.168.68.47 E-518 --center 55.0,45.0

  # Second TTM unit
  %(prog)s /tmp/ttm2Cmd.im.shm 192.168.68.48 E-518

  # Custom center
  %(prog)s /tmp/ttm1Cmd.im.shm 192.168.68.47 E-518 --center 55.0,45.0
        """
    )
    parser.add_argument('shmName',
                        help='Shared memory path (e.g. /tmp/ttm1Cmd.im.shm)')
    parser.add_argument('ip',
                        help='Controller IP address (e.g. 192.168.68.47)')
    parser.add_argument('ctrlModel',
                        help='Controller model (e.g. E-518)')
    parser.add_argument('--center', default='50.0,50.0',
                        help='Center position as A,B in controller units 0-100 (default: 50.0,50.0)')
    return parser.parse_args()


def main():
    args = parse_args()

    # Parse center
    try:
        center_a, center_b = map(float, args.center.split(','))
    except ValueError:
        print("ERROR: --center must be two comma-separated floats e.g. 50.0,50.0")
        sys.exit(1)

    print(f"TTM controller {args.ip} | model={args.ctrlModel} | shm={args.shmName} | center=({center_a},{center_b})")

    ttm = dao.shm(args.shmName)
    ttmAXES = ['A', 'B']

    # Connect
    device = GCSDevice(args.ctrlModel)
    device.ConnectTCPIP(ipaddress=args.ip)
    device.ONL([1, 2], [1, 1])
    time.sleep(0.2)

    # Open loop
    device.SVO(ttmAXES, [0, 0])
    time.sleep(0.2)
    print("servo:", device.qSVO(ttmAXES))

    # Start at center
    device.SVA(ttmAXES, [center_a, center_b])
    time.sleep(0.1)
    print("initial POS:", device.qPOS(ttmAXES))
    print("error:", device.qERR())

    print("Running... Ctrl+C to stop")
    try:
        while True:
            cmd = ttm.get_data(check=True)  # blocks until new data, shape (2,1)
            a = np.clip(float(cmd[0, 0]), 0.0, 100.0)
            b = np.clip(float(cmd[1, 0]), 0.0, 100.0)
            device.SVA(ttmAXES, [a, b])

    except KeyboardInterrupt:
        print("\nStopped, returning to center...")
        device.SVA(ttmAXES, [center_a, center_b])
        print("final POS:", device.qPOS(ttmAXES))
        print("Done")


if __name__ == '__main__':
    main()