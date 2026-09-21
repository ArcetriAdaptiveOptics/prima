"""Prisma-style PI S-334 modulator via direct E-518 GCS TCP.

Uses ASCII GCS (WAV SIN_P + WSL + WGO) on ``host:50000`` so Drop 1 does not
depend on ``libpi_pi_gcs2.so`` / ``plico_dm_server``. Optional plico path remains
available separately.
"""
from __future__ import annotations

import math
import threading
from types import SimpleNamespace

import numpy as np

from prima.hardware.gcs_tcp import GcsTcp, GcsTcpError


DEFAULT_E518_HOST = '192.168.30.190'
DEFAULT_E518_PORT = 50000
DEFAULT_SERIAL = '110032051'

# Safe Drop-1 ceiling (mrad). Hardware tests stay well below this.
MAX_SAFE_RADIUS_MRAD = 5.0

# Prisma calib/modulator/pi_calibration.py SN 110032051
_CALIB = {
    '110032051': {
        'lin_a': 0.87, 'off_a': -43.5,
        'lin_b': 0.87, 'off_b': -43.5,
        'v_lo': [0.0, 0.0, 0.0],
        'v_hi': [100.0, 100.0, 100.0],
        'pivot': 100.0,
    },
    'ideal': {
        'lin_a': 0.5, 'off_a': -25.0,
        'lin_b': 0.5, 'off_b': -25.0,
        'v_lo': [0.0, 0.0, 0.0],
        'v_hi': [100.0, 100.0, 100.0],
        'pivot': 100.0,
    },
}


class PiGcsError(RuntimeError):
    """Raised when PI/GCS setup or modulation fails."""


class PiE518Modulator:
    """Direct E-518 client with plico/Prisma modulator surface.

    ``setRadiusInMilliRad`` / ``setFrequencyInHz`` / ``setCenterInMilliRad``
    rebuild a circular SIN_P wavegen trajectory (no adaptive recorder loop).
    """

    def __init__(
            self,
            host=DEFAULT_E518_HOST,
            port=DEFAULT_E518_PORT,
            serial_number=DEFAULT_SERIAL,
            name=None,
            max_radius_mrad=MAX_SAFE_RADIUS_MRAD,
            connect=True,
    ):
        self._host = str(host)
        self._port = int(port)
        self._serial = str(serial_number)
        if self._serial not in _CALIB:
            raise PiGcsError(
                'Unknown PI calib serial %r (known: %s)'
                % (self._serial, sorted(_CALIB)))
        self._cal = dict(_CALIB[self._serial])
        self._name = name or ('PI-E518@%s:%s' % (self._host, self._port))
        self._max_radius = float(max_radius_mrad)
        self._gcs = GcsTcp(self._host, self._port)
        self._lock = threading.RLock()
        self._radius = 1.0
        self._freq = 20.0
        self._center = np.zeros(2, dtype=float)
        self._setup_done = False
        self._modulating = False
        self._servo_dt = None
        self._wtr = 1
        if connect:
            self.connect()

    # --- lifecycle ---

    def connect(self) -> None:
        with self._lock:
            try:
                self._gcs.connect()
                idn = self._gcs.idn()
            except (OSError, GcsTcpError) as exc:
                raise PiGcsError(
                    'Cannot open E-518 GCS at %s:%s: %s'
                    % (self._host, self._port, exc)) from exc
            if 'E-518' not in idn and 'PI' not in idn.upper():
                raise PiGcsError('Unexpected *IDN? reply: %r' % idn)
            try:
                self._set_up_controller()
            except (GcsTcpError, PiGcsError) as exc:
                self._gcs.close()
                raise PiGcsError('E-518 setUp failed: %s' % exc) from exc
            self._setup_done = True

    def close(self) -> None:
        with self._lock:
            try:
                if self._gcs.connected:
                    try:
                        self.stop_modulation()
                    except Exception:
                        pass
                    try:
                        self._gcs.set('SVO A 0 B 0 C 0', check_err=False)
                    except Exception:
                        pass
            finally:
                self._gcs.close()
                self._setup_done = False
                self._modulating = False

    def _set_up_controller(self) -> None:
        g = self._gcs
        # Drain any stale ERR from a prior half-open session.
        try:
            g.query('ERR?', wait_s=0.3)
        except Exception:
            pass
        # Proven Drop-1 sequence on E-518.I3 (ASCII GCS, no pi_pi_gcs2 .so).
        # STP then WGO stop — tolerate soft errors (e.g. 1090) after reclaim.
        try:
            g.set('STP', check_err=False)
        except Exception:
            pass
        try:
            g.set('WGO 1 0 2 0 3 0')
        except GcsTcpError as exc:
            # Reclaim: reconnect once and retry stop.
            if '1090' in str(exc) or 'GCS error' in str(exc):
                g.connect()
                g.query('ERR?', wait_s=0.3)
                g.set('WGO 1 0 2 0 3 0', check_err=False)
            else:
                raise
        g.set('ONL 1 1 2 1 3 1')
        lo = self._cal['v_lo']
        hi = self._cal['v_hi']
        g.set('VMI 1 %.6f 2 %.6f 3 %.6f' % (lo[0], lo[1], lo[2]))
        g.set('VMA 1 %.6f 2 %.6f 3 %.6f' % (hi[0], hi[1], hi[2]))
        g.set('SVO A 1 B 1 C 0')
        g.set('WTR 1 1 0 2 1 0 3 1 0')
        # Clear residual error code so later set() is clean.
        g.query('ERR?', wait_s=0.3)
        self._servo_dt = self._query_servo_dt()
        self._wtr = self._query_wtr()

    def _query_servo_dt(self) -> float:
        raw = self._gcs.query('SPA? 1 0x0E000200', wait_s=0.6)
        # e.g. "1 0X0E000200=3.99999968e-5"
        for tok in raw.replace('\n', ' ').split():
            if '=' in tok:
                try:
                    return float(tok.split('=', 1)[1])
                except ValueError:
                    pass
        # E-518 typical ~40 µs
        return 40e-6

    def _query_wtr(self) -> int:
        raw = self._gcs.query('WTR?', wait_s=0.5)
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith('1='):
                parts = line.split('=', 1)[1].split()
                try:
                    return max(1, int(float(parts[0])))
                except (ValueError, IndexError):
                    pass
        return 1

    # --- unit conversion ---

    def _mrad_to_gcs(self, mrad, axis: str) -> float:
        if axis == 'A':
            return (float(mrad) - self._cal['off_a']) / self._cal['lin_a']
        if axis == 'B':
            return (float(mrad) - self._cal['off_b']) / self._cal['lin_b']
        raise KeyError(axis)

    # --- modulation ---

    def _apply(self) -> None:
        if not self._setup_done:
            raise PiGcsError('E-518 not set up')
        r = float(self._radius)
        if r < 0:
            raise PiGcsError('Radius must be >= 0')
        if r > self._max_radius:
            raise PiGcsError(
                'Refusing radius %.3f mrad > safe max %.3f mrad'
                % (r, self._max_radius))
        f = float(self._freq)
        if f <= 0:
            raise PiGcsError('Frequency must be > 0')
        cx, cy = float(self._center[0]), float(self._center[1])
        if r == 0.0:
            self.stop_modulation()
            return
        dt = float(self._servo_dt) * float(self._wtr)
        n_pts = int(round((1.0 / f) / dt))
        n_pts = max(32, min(n_pts, 8000))
        self._gcs.set('WGO 1 0 2 0 3 0')
        self._gcs.set('WCL 1 2 3')
        # Circular: A ≈ cos (SIN phase π/2), B ≈ sin (phase 0).
        self._load_sin_p(1, r, cx, phase_rad=math.pi / 2.0, n_pts=n_pts)
        self._load_sin_p(2, r, cy, phase_rad=0.0, n_pts=n_pts)
        self._gcs.set('WSL 1 1 2 2')
        self._gcs.set('WGO 1 1 2 1 3 0')
        self._modulating = True

    def _load_sin_p(self, table_id, amp_mrad, cen_mrad, phase_rad, n_pts):
        axis = 'A' if int(table_id) == 1 else 'B'
        peak = self._mrad_to_gcs(cen_mrad + amp_mrad, axis)
        valley = self._mrad_to_gcs(cen_mrad - amp_mrad, axis)
        amp = peak - valley
        offset = valley
        start = int(round(phase_rad / (2.0 * math.pi) * n_pts)) % n_pts
        center_pt = n_pts // 2
        # Verified on E-518.I3: WAV <id> X SIN_P <len> <amp> <off> <wl> <start> <ctr>
        cmd = 'WAV %d X SIN_P %d %.6f %.6f %d %d %d' % (
            int(table_id), int(n_pts), float(amp), float(offset),
            int(n_pts), int(start), int(center_pt))
        self._gcs.set(cmd)

    def stop_modulation(self) -> None:
        if not self._gcs.connected:
            return
        self._gcs.set('WGO 1 0 2 0 3 0')
        self._modulating = False

    # --- public modulator API (plico / Prisma shaped) ---

    def name(self):
        return self._name

    def setRadiusInMilliRad(self, radiusInMilliRad):
        with self._lock:
            self._radius = float(radiusInMilliRad)
            self._apply()

    def getRadiusInMilliRad(self):
        return float(self._radius)

    def setFrequencyInHz(self, frequencyInHz):
        with self._lock:
            self._freq = float(frequencyInHz)
            self._apply()

    def getFrequencyInHz(self):
        return float(self._freq)

    def setCenterInMilliRad(self, center):
        with self._lock:
            c = np.asarray(center, dtype=float).reshape(-1)
            if c.size < 2:
                raise ValueError('center needs 2 components')
            self._center = np.array([c[0], c[1]], dtype=float)
            self._apply()

    def getCenterInMilliRad(self):
        return self._center.copy()

    def getStatus(self):
        return SimpleNamespace(
            name=self._name,
            modulatorRadiusInMilliRad=self.getRadiusInMilliRad(),
            modulatorFrequencyInHz=self.getFrequencyInHz(),
            modulatorCenterInMilliRad=self.getCenterInMilliRad(),
            modulating=self._modulating,
            host=self._host,
            port=self._port,
            serial_number=self._serial,
        )

    def getSnapshot(self, prefix=''):
        from prima.metrology.arbitrator.snapshot_entry import SnapshotEntry
        p = prefix or ''
        return {
            p + 'NAME': SnapshotEntry('Name', self.name()),
            p + 'RADIUS_MRAD': SnapshotEntry(
                'Radius [mrad]', self.getRadiusInMilliRad()),
            p + 'FREQ_HZ': SnapshotEntry(
                'Frequency [Hz]', self.getFrequencyInHz()),
            p + 'CENTER_MRAD': SnapshotEntry(
                'Center [mrad]', self.getCenterInMilliRad()),
        }

    def wavegen_running(self) -> bool:
        with self._lock:
            if not self._gcs.connected:
                return False
            raw = self._gcs.query('WGO?', wait_s=0.4)
            vals = {}
            for part in raw.replace('\n', ' ').split():
                if '=' in part:
                    k, v = part.split('=', 1)
                    try:
                        vals[int(k)] = int(float(v))
                    except ValueError:
                        pass
            return bool(vals.get(1, 0) and vals.get(2, 0))


def connect_pi_modulator(
        host=DEFAULT_E518_HOST,
        port=DEFAULT_E518_PORT,
        serial_number=DEFAULT_SERIAL,
        **kwargs):
    """Connect and setUp E-518; raises ``PiGcsError`` on failure."""
    return PiE518Modulator(
        host=host, port=port, serial_number=serial_number,
        connect=True, **kwargs)
