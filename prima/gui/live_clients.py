"""Connect Drop 1 camera / modulator backends (no plico servers).

Today's stack (binding):
  - Camera: Aravis GigE Manta (single owner)
  - Modulator: direct PI E-518 GCS TCP
  - pysilico_server / plico_dm_server: deferred
"""
from __future__ import annotations

import os

import numpy as np

from prima.demo.backends import DemoCamera, DemoModulator


DEFAULT_E518_HOST = os.environ.get('PRIMA_E518_HOST', '192.168.30.190')
DEFAULT_E518_PORT = int(os.environ.get('PRIMA_E518_PORT', '50000'))
DEFAULT_ARAVIS_IP = os.environ.get('PRIMA_ARAVIS_IP', '192.168.30.189')


class LiveCameraWrapper:
    """Unused stub kept for import compatibility; Drop1 uses AravisLiveCamera."""

    def __init__(self, client, name='LiveCamera'):
        self._c = client
        self._name = name

    def name(self):
        return self._name


def connect_aravis(ip_address=None):
    from prima.gui.aravis_camera import connect_aravis as _connect
    return _connect(ip_address or DEFAULT_ARAVIS_IP)


def connect_pi_direct(host=None, port=None):
    from prima.hardware import connect_pi_modulator
    return connect_pi_modulator(
        host=host or DEFAULT_E518_HOST,
        port=port or DEFAULT_E518_PORT,
    )


def try_connect_live(aravis_ip=None,
                     e518_host=None,
                     e518_port=None,
                     **_ignored):
    """Return (camera, modulator, errors) for Drop1 live stack.

    Extra kwargs ignored for backward compatibility with older launchers.
    """
    aravis_ip = aravis_ip or DEFAULT_ARAVIS_IP
    e518_host = e518_host or DEFAULT_E518_HOST
    e518_port = DEFAULT_E518_PORT if e518_port is None else int(e518_port)

    cam, mod, errors = None, None, []
    try:
        cam = connect_aravis(aravis_ip)
    except Exception as e:
        errors.append('camera(Aravis): %s' % e)

    try:
        mod = connect_pi_direct(e518_host, e518_port)
    except Exception as e:
        errors.append('modulator(direct PI GCS): %s' % e)
        mod = None

    return cam, mod, errors


def demo_pair(rows=512, cols=512):
    return DemoCamera(rows=rows, cols=cols), DemoModulator()


# Back-compat aliases (unused by Drop1 GUI now)
def connect_camera(*_a, **_k):
    raise RuntimeError('pysilico camera path deferred — use Aravis')


def connect_modulator(*_a, **_k):
    raise RuntimeError('plico_dm modulator path deferred — use direct PI GCS')


def try_connect_aravis(ip_address=None):
    return connect_aravis(ip_address)
