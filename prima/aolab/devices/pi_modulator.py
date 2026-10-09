"""PI S-334 tip-tilt modulator on E-518, ASCII GCS over TCP.

Same semantics as the reference Arcetri driver (``pi_gcs.TipTilt2Axis`` +
``plico_dm_server.PIS334Modulator``), re-implemented on the plain TCP
client so that ``libpi_pi_gcs2.so`` is not needed:

setUp
    ONL 1 1 2 1 3 1          remote (online) control of the 3 channels
    WGO 1 0 2 0 3 0          wave generators stopped
    VMI/VMA 0..100 V         voltage limits on all channels
    SVO A 0 B 0              servo off while configuring
    SVO C 0 ; SVA C 100      3rd axis = PIVOT, open loop at 100 V
    SVO A 1 B 1              closed loop on tip/tilt
    MOV A c B c              centre = 0 mrad -> mid travel

R = 0  ->  wave generators stopped, axes in CLOSED LOOP at the centre
           position (DC, mid travel).  Outputs are never switched off.
R > 0  ->  sinusoidal wave tables (SIN_P) centred on the same position,
           so the circle is centred on mid travel of the piezo axes.

Calibration SN 110032051: mrad = 0.87 * gcs - 43.5  (0 mrad = 50 gcs).
"""
from __future__ import annotations

import math
import os
import threading
import time

import numpy as np

from prima.hardware.gcs_tcp import GcsTcp, GcsTcpError

CALIB = {
    '110032051': dict(lin_a=0.87, off_a=-43.5, lin_b=0.87, off_b=-43.5),
    'ideal': dict(lin_a=0.5, off_a=-25.0, lin_b=0.5, off_b=-25.0),
}
PIVOT_V = 100.0
V_LO, V_HI = 0.0, 100.0
MAX_RADIUS_MRAD = float(os.environ.get('PRIMA_MOD_MAX_MRAD', '40'))


class PiTipTiltModulator:
    def __init__(self, host='192.168.30.190', port=50000,
                 serial='110032051', max_radius_mrad=MAX_RADIUS_MRAD):
        self.host, self.port = host, int(port)
        self.cal = CALIB[serial]
        self.max_radius = float(max_radius_mrad)
        self.g = GcsTcp(host, port)
        self.lock = threading.RLock()
        self.radius = 0.0
        self.freq = 20.0
        self.center = np.zeros(2)
        self.modulating = False
        self.servo_dt = 40e-6
        self.wtr = 1
        self.n_pts = 0
        self.idn = ''
        self.setup()

    # ------------------------------------------------------------ units
    def mrad_to_gcs(self, mrad, axis):
        if axis == 'A':
            return (float(mrad) - self.cal['off_a']) / self.cal['lin_a']
        return (float(mrad) - self.cal['off_b']) / self.cal['lin_b']

    def gcs_to_mrad(self, gcs, axis):
        if axis == 'A':
            return self.cal['lin_a'] * float(gcs) + self.cal['off_a']
        return self.cal['lin_b'] * float(gcs) + self.cal['off_b']

    # ------------------------------------------------------------ setup
    def _set(self, cmd, check=True):
        return self.g.set(cmd, check_err=check)

    def setup(self):
        with self.lock:
            self.g.connect()
            self.idn = self.g.idn()
            if 'E-518' not in self.idn and 'PI' not in self.idn.upper():
                raise GcsTcpError('unexpected IDN %r' % self.idn)
            self.g.query('ERR?', wait_s=0.3)            # clear stale error
            self._set('ONL 1 1 2 1 3 1')
            self._set('WGO 1 0 2 0 3 0')
            self._set('VMI 1 %.1f 2 %.1f 3 %.1f' % (V_LO, V_LO, V_LO))
            self._set('VMA 1 %.1f 2 %.1f 3 %.1f' % (V_HI, V_HI, V_HI))
            self._set('SVO A 0 B 0')
            self._set('SVO C 0')
            # pivot -> 100 V, ramped (it may start from 0 V)
            v0 = self._parse(self.g.query('SVA?', wait_s=0.4)).get('C', 0.0)
            for v in np.linspace(v0, PIVOT_V, 11)[1:]:
                self._set('SVA C %.3f' % v)
                time.sleep(0.05)
            self._set('SVO A 1 B 1')
            self.servo_dt = self._query_float('SPA? 1 0x0E000200', 40e-6)
            self.wtr = self._query_wtr()
            self._goto_center()

    def _query_float(self, q, default):
        raw = self.g.query(q, wait_s=0.6)
        for tok in raw.replace('\n', ' ').split():
            if '=' in tok:
                try:
                    return float(tok.split('=', 1)[1])
                except ValueError:
                    pass
        return default

    def _query_wtr(self):
        raw = self.g.query('WTR?', wait_s=0.5)
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith('1='):
                try:
                    return max(1, int(float(line.split('=', 1)[1].split()[0])))
                except (ValueError, IndexError):
                    pass
        return 1

    def _goto_center(self):
        a = self.mrad_to_gcs(self.center[0], 'A')
        b = self.mrad_to_gcs(self.center[1], 'B')
        self._set('MOV A %.5f B %.5f' % (a, b))

    # ------------------------------------------------------- modulation
    def set_modulation(self, radius_mrad, freq_hz=None):
        r = float(radius_mrad)
        if r < 0 or r > self.max_radius:
            raise ValueError('radius %.2f outside [0, %.1f] mrad'
                             % (r, self.max_radius))
        with self.lock:
            self.radius = r
            if freq_hz is not None:
                if freq_hz <= 0:
                    raise ValueError('frequency must be > 0')
                self.freq = float(freq_hz)
            self._apply()

    def set_center(self, cx, cy):
        with self.lock:
            self.center = np.array([float(cx), float(cy)])
            self._apply()

    def _apply(self):
        g = self.g
        self._set('WGO 1 0 2 0 3 0')
        self.modulating = False
        if self.radius == 0.0:
            self._goto_center()          # DC, closed loop, mid travel
            self.n_pts = 0
            return
        dt = self.servo_dt * self.wtr
        n = int(round(1.0 / self.freq / dt))
        n = max(32, min(n, 8000))
        self._set('WCL 1 2')
        self._load_sin(1, 'A', self.center[0], math.pi / 2, n)   # cos
        self._load_sin(2, 'B', self.center[1], 0.0, n)           # sin
        self._set('WSL 1 1 2 2')
        self._set('WGO 1 1 2 1')
        self.n_pts = n
        self.modulating = True

    def _load_sin(self, table, axis, cen_mrad, phase, n):
        peak = self.mrad_to_gcs(cen_mrad + self.radius, axis)
        valley = self.mrad_to_gcs(cen_mrad - self.radius, axis)
        start = int(round(phase / (2 * math.pi) * n)) % n
        # WAV <t> X SIN_P <len> <amp p-p> <offset=valley> <wavelen> <start> <centre>
        self._set('WAV %d X SIN_P %d %.6f %.6f %d %d %d'
                  % (table, n, peak - valley, valley, n, start, n // 2))

    # ------------------------------------------------------- read back
    def _parse(self, raw):
        out = {}
        for line in raw.replace('\r', '').split('\n'):
            if '=' in line:
                k, v = line.split('=', 1)
                try:
                    out[k.strip()] = float(v.split()[0])
                except (ValueError, IndexError):
                    pass
        return out

    def readback(self, n_samples=40, dt=0.007):
        """Sample POS? and VOL? to estimate centre / amplitude actually
        produced (voltages per channel, positions per axis)."""
        with self.lock:
            pos, vol = [], []
            for _ in range(int(n_samples)):
                p = self._parse(self.g.query('POS?', wait_s=0.15))
                v = self._parse(self.g.query('VOL?', wait_s=0.15))
                pos.append([p.get('A', np.nan), p.get('B', np.nan)])
                vol.append([v.get('1', np.nan), v.get('2', np.nan),
                            v.get('3', np.nan)])
                time.sleep(dt)
        pos, vol = np.array(pos), np.array(vol)
        return {
            'pos_gcs_mid': ((np.nanmax(pos, 0) + np.nanmin(pos, 0)) / 2).round(3).tolist(),
            'pos_gcs_ptp': np.ptp(pos, 0).round(3).tolist(),
            'vol_mid': ((np.nanmax(vol, 0) + np.nanmin(vol, 0)) / 2).round(2).tolist(),
            'vol_ptp': np.ptp(vol, 0).round(2).tolist(),
            'vol_min': np.nanmin(vol, 0).round(2).tolist(),
            'vol_max': np.nanmax(vol, 0).round(2).tolist(),
        }

    def state(self):
        return {'radius_mrad': self.radius, 'freq_hz': self.freq,
                'center': (float(self.center[0]), float(self.center[1])),
                'modulating': self.modulating, 'n_pts': self.n_pts}

    def close(self, keep_state=True):
        """Release TCP.  The controller keeps doing what it was doing
        (modulating or holding the centre in closed loop)."""
        if not keep_state:
            with self.lock:
                self.radius = 0.0
                self._apply()
        self.g.close()
