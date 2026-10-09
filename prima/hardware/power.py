"""Bench power switch — Meross smart plug **mss210 only**.

===========================================================================
 RULE (binding, do not relax):
   * The PRIMA bench is powered by the Meross plug of type ``mss210``.
   * The account also holds a ``mss425e`` power strip that feeds ANOTHER
     bench.  This module must NEVER send a command to it, nor to any device
     whose type is not exactly ``mss210``.
   * If the account shows zero or more than one ``mss210`` the command is
     refused (ambiguous target).
   * The laptop (alienware) is NOT on the plug: power-cycling the bench
     never kills this PC.
===========================================================================

Credentials are read from (first found):
  1. env ``PRIMA_MEROSS_EMAIL`` / ``PRIMA_MEROSS_PASSWORD``
  2. ``~/git/.secrets/meross.json``  {"email": ..., "password": ...}
They are never stored in the repository.

CLI::

    python -m prima.hardware.power status
    python -m prima.hardware.power on
    python -m prima.hardware.power off
    python -m prima.hardware.power cycle --off-s 10

Before switching OFF the bench, park the DM (flat → HV off) and stop the
modulator: :func:`safe_bench_off` does that when the drivers are importable.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ALLOWED_TYPE = 'mss210'            # the ONLY device this code may switch
FORBIDDEN_TYPES = ('mss425e',)     # other bench — never touched
SECRETS = Path.home() / 'git' / '.secrets' / 'meross.json'
API_URL = os.environ.get('PRIMA_MEROSS_API', 'https://iotx-eu.meross.com')


class PowerError(RuntimeError):
    pass


def _credentials() -> tuple[str, str]:
    email = os.environ.get('PRIMA_MEROSS_EMAIL')
    pwd = os.environ.get('PRIMA_MEROSS_PASSWORD')
    if email and pwd:
        return email, pwd
    if SECRETS.is_file():
        d = json.loads(SECRETS.read_text())
        return d['email'], d['password']
    raise PowerError('Meross credentials not found (env or %s)' % SECRETS)


def _select_bench_plug(devices) -> object:
    """Return the single mss210; refuse anything ambiguous."""
    cands = [d for d in devices
             if str(getattr(d, 'type', '')).strip().lower() == ALLOWED_TYPE]
    if len(cands) != 1:
        raise PowerError(
            'Expected exactly one %s on the account, found %d: %s — refusing.'
            % (ALLOWED_TYPE, len(cands),
               [(getattr(d, 'name', '?'), getattr(d, 'type', '?'))
                for d in devices]))
    dev = cands[0]
    dtype = str(getattr(dev, 'type', '')).lower()
    if dtype in FORBIDDEN_TYPES or dtype != ALLOWED_TYPE:  # belt and braces
        raise PowerError('Refusing device type %r' % dtype)
    return dev


async def _run(action: str, off_s: float = 10.0) -> dict:
    from meross_iot.http_api import MerossHttpClient
    from meross_iot.manager import MerossManager

    email, pwd = _credentials()
    http = await MerossHttpClient.async_from_user_password(
        api_base_url=API_URL, email=email, password=pwd)
    manager = MerossManager(http_client=http)
    try:
        await manager.async_init()
        await manager.async_device_discovery()
        devices = manager.find_devices()
        dev = _select_bench_plug(devices)
        await dev.async_update()
        before = bool(dev.is_on())
        if action == 'on':
            await dev.async_turn_on(channel=0)
        elif action == 'off':
            await dev.async_turn_off(channel=0)
        elif action == 'cycle':
            await dev.async_turn_off(channel=0)
            await asyncio.sleep(float(off_s))
            await dev.async_turn_on(channel=0)
        elif action != 'status':
            raise PowerError('unknown action %r' % action)
        await asyncio.sleep(1.0)
        await dev.async_update()
        return {'device': dev.name, 'type': dev.type,
                'online': str(dev.online_status),
                'before_on': before, 'now_on': bool(dev.is_on()),
                'action': action}
    finally:
        manager.close()
        await http.async_logout()


def bench_power(action: str, off_s: float = 10.0) -> dict:
    """Synchronous entry point: ``status`` | ``on`` | ``off`` | ``cycle``."""
    return asyncio.run(_run(action, off_s))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='PRIMA bench plug (mss210 ONLY)')
    p.add_argument('action', choices=('status', 'on', 'off', 'cycle'))
    p.add_argument('--off-s', type=float, default=10.0)
    a = p.parse_args(argv)
    t0 = time.time()
    try:
        res = bench_power(a.action, a.off_s)
    except PowerError as exc:
        print('POWER REFUSED/FAILED:', exc)
        return 2
    res['elapsed_s'] = round(time.time() - t0, 1)
    print(json.dumps(res, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
