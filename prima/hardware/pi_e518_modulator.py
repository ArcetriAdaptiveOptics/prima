"""Prisma-style PI S-334 modulator via direct E-518 GCS TCP.

Uses ASCII GCS (WAV SIN_P + WSL + WGO) on ``host:50000`` so Drop 1 does not
depend on ``libpi_pi_gcs2.so`` / ``plico_dm_server``. Optional plico path remains
available separately.
"""
from __future__ import annotations

import math
import os
import threading
import time
from types import SimpleNamespace

import numpy as np

from prima.hardware.gcs_tcp import GcsTcp, GcsTcpError


DEFAULT_E518_HOST = '192.168.30.190'
DEFAULT_E518_PORT = 50000
DEFAULT_SERIAL = '110032051'

# Prisma pygo_gui gain presets go to 40 mrad; SN 110032051 calib maps
# R=40 → ~4–96 V (inside soft 0–100 V). Override with PRIMA_MOD_MAX_MRAD.
MAX_SAFE_RADIUS_MRAD = float(os.environ.get('PRIMA_MOD_MAX_MRAD', '40'))

# Mid-travel park (V). All mrad swings are centered here so pupils stay put.
PARK_MID_VOLTAGE_V = float(os.environ.get('PRIMA_MOD_PARK_V', '50'))

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
        self._wave_n_pts = 0
        self._wave_freq_hz = 0.0
        self._table_vpp_a = 0.0
        self._table_vpp_b = 0.0
        self._last_vol = {1: float('nan'), 2: float('nan'), 3: float('nan')}
        self._parked = False
        self._park_sva = [55.0, 55.0]
        # Mid-travel park target is always +50 V (0–100 soft range), not calib pivot.
        self._park_v = float(PARK_MID_VOLTAGE_V)
        if connect:
            self.connect()

    # --- lifecycle ---

    def connect(self) -> None:
        with self._lock:
            try:
                self._gcs.connect()
                # E-518 often keeps a single TCP client; a stale peer can
                # leave the first replies empty until we reconnect.
                idn = ''
                for attempt in range(3):
                    idn = self._gcs.idn()
                    if idn and ('E-518' in idn or 'PI' in idn.upper()):
                        break
                    self._gcs.close()
                    time.sleep(0.35 * (attempt + 1))
                    self._gcs.connect()
            except (OSError, GcsTcpError) as exc:
                raise PiGcsError(
                    'Cannot open E-518 GCS at %s:%s: %s'
                    % (self._host, self._port, exc)) from exc
            if not idn or ('E-518' not in idn and 'PI' not in idn.upper()):
                raise PiGcsError(
                    'Unexpected *IDN? reply: %r '
                    '(close other Drop1/GCS sessions and retry)' % idn)
            try:
                self._set_up_controller()
                self.park_midscale()
            except (GcsTcpError, PiGcsError) as exc:
                self._gcs.close()
                raise PiGcsError('E-518 setUp failed: %s' % exc) from exc
            self._setup_done = True

    def close(self) -> None:
        with self._lock:
            try:
                if self._gcs.connected:
                    try:
                        self.park_midscale()
                    except Exception:
                        try:
                            self.stop_modulation()
                        except Exception:
                            pass
            finally:
                self._gcs.close()
                self._setup_done = False
                self._modulating = False
                self._parked = False

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

    def _read_vol_ab(self):
        raw = self._gcs.query('VOL?', wait_s=0.3)
        vals = self._parse_vol(raw)
        if vals:
            self._last_vol.update(vals)
        return float(vals.get(1, float('nan'))), float(vals.get(2, float('nan')))

    def park_midscale(self, target_v=None, tol_v=0.8, max_iter=10) -> None:
        """Stop wavegen and hold both tip-tilt axes at mid-travel (~50 V).

        Binding: idle / R=0 must sit at +50 VDC so modulation swings around mid
        scale and PWFS pupil centering is preserved. Uses ``SVA`` with servo
        off (``SVO`` on blocks SVA with GCS 303 on this E-518).
        """
        if not self._gcs.connected:
            return
        target = float(self._park_v if target_v is None else target_v)
        g = self._gcs
        g.set('WGO 1 0 2 0 3 0', check_err=False)
        g.set('WSL 1 0 2 0 3 0', check_err=False)
        g.set('SVO A 0 B 0 C 0', check_err=False)
        time.sleep(0.15)
        # Seed near mid: on this E-518, SVA≈55 → VOL≈50 (≈0.9 V/V).
        cmd_a = 55.0
        cmd_b = 55.0
        g.set('SVA A %.4f B %.4f' % (cmd_a, cmd_b), check_err=False)
        time.sleep(0.45)
        for _ in range(int(max_iter)):
            a, b = self._read_vol_ab()
            if not (math.isfinite(a) and math.isfinite(b)):
                time.sleep(0.2)
                continue
            if abs(a - target) <= tol_v and abs(b - target) <= tol_v:
                break
            # Limited step — avoid winding SVA to the rail on a bad sample.
            step_a = max(-3.0, min(3.0, -0.9 * (a - target)))
            step_b = max(-3.0, min(3.0, -0.9 * (b - target)))
            cmd_a = min(70.0, max(40.0, cmd_a + step_a))
            cmd_b = min(70.0, max(40.0, cmd_b + step_b))
            g.set('SVA A %.4f B %.4f' % (cmd_a, cmd_b), check_err=False)
            time.sleep(0.3)
        self._park_sva = [cmd_a, cmd_b]
        # Leave SVO off so VOL holds the parked mid-scale voltage.
        self._modulating = False
        self._parked = True
        self._wave_n_pts = 0
        self._wave_freq_hz = 0.0
        self._table_vpp_a = 0.0
        self._table_vpp_b = 0.0

    def _ensure_servo_for_wavegen(self) -> None:
        """Enable tip/tilt servos before starting wavegen output."""
        self._gcs.set('SVO A 1 B 1 C 0', check_err=False)
        self._parked = False

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

    def _check_radius(self, radius_mrad: float) -> float:
        r = float(radius_mrad)
        if r < 0:
            raise PiGcsError('Radius must be >= 0')
        if r > self._max_radius:
            raise PiGcsError(
                'Refusing radius %.3f mrad > safe max %.3f mrad'
                % (r, self._max_radius))
        return r

    def _apply(self) -> None:
        if not self._setup_done:
            raise PiGcsError('E-518 not set up')
        r = self._check_radius(self._radius)
        f = float(self._freq)
        if f <= 0:
            raise PiGcsError('Frequency must be > 0')
        cx, cy = float(self._center[0]), float(self._center[1])
        if r == 0.0:
            # No mrad bias when idle — park both axes at mid-travel (+50 V).
            self.park_midscale()
            return
        dt = float(self._servo_dt) * float(self._wtr)
        n_pts = int(round((1.0 / f) / dt))
        n_pts = max(32, min(n_pts, 8000))
        self._gcs.set('WGO 1 0 2 0 3 0', check_err=False)
        self._gcs.set('WCL 1 2 3', check_err=False)
        self._ensure_servo_for_wavegen()
        # Circular: A ≈ cos (SIN phase π/2), B ≈ sin (phase 0).
        # Tables are centered at calib mid (~50 V); Vpp grows with |R|.
        vpp_a = self._load_sin_p(1, r, cx, phase_rad=math.pi / 2.0, n_pts=n_pts)
        vpp_b = self._load_sin_p(2, r, cy, phase_rad=0.0, n_pts=n_pts)
        self._gcs.set('WSL 1 1 2 2')
        self._gcs.set('WGO 1 1 2 1 3 0')
        self._modulating = True
        self._parked = False
        self._wave_n_pts = int(n_pts)
        self._wave_freq_hz = 1.0 / (float(n_pts) * dt)
        self._table_vpp_a = float(vpp_a)
        self._table_vpp_b = float(vpp_b)

    def _load_sin_p(self, table_id, amp_mrad, cen_mrad, phase_rad, n_pts):
        axis = 'A' if int(table_id) == 1 else 'B'
        peak = self._mrad_to_gcs(cen_mrad + amp_mrad, axis)
        valley = self._mrad_to_gcs(cen_mrad - amp_mrad, axis)
        amp = peak - valley  # GCS SIN_P amplitude = peak-to-peak volts
        offset = valley
        start = int(round(phase_rad / (2.0 * math.pi) * n_pts)) % n_pts
        center_pt = n_pts // 2
        # Verified on E-518.I3: WAV <id> X SIN_P <len> <amp> <off> <wl> <start> <ctr>
        cmd = 'WAV %d X SIN_P %d %.6f %.6f %d %d %d' % (
            int(table_id), int(n_pts), float(amp), float(offset),
            int(n_pts), int(start), int(center_pt))
        self._gcs.set(cmd)
        return float(amp)

    def stop_modulation(self) -> None:
        """Stop wavegen and park both axes at mid-travel (+50 V)."""
        if not self._gcs.connected:
            return
        self.park_midscale()

    # --- public modulator API (plico / Prisma shaped) ---

    def name(self):
        return self._name

    def setRadiusInMilliRad(self, radiusInMilliRad):
        with self._lock:
            # Validate before mutating so a refuse cannot stick and block
            # later frequency / center applies.
            new_r = self._check_radius(radiusInMilliRad)
            self._radius = new_r
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
            parked=self._parked,
            park_voltage_v=self._park_v,
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

    def _parse_vol(self, raw: str) -> dict:
        vals = {}
        for part in raw.replace('\n', ' ').split():
            if '=' not in part:
                continue
            k, v = part.split('=', 1)
            try:
                vals[int(k)] = float(v)
            except ValueError:
                pass
        return vals

    def read_vol(self) -> dict:
        """Instantaneous axis voltages from ``VOL?`` (GCS channels 1/2/3)."""
        with self._lock:
            if not self._gcs.connected:
                return dict(self._last_vol)
            raw = self._gcs.query('VOL?', wait_s=0.25)
            vals = self._parse_vol(raw)
            if vals:
                self._last_vol.update(vals)
            return dict(self._last_vol)

    def refresh_wave_table_readback(self) -> None:
        """Measure Vpp + freq from controller wave table via ``GWD?``.

        E-518 returns the full recorder buffer (~0.5 s); call from a worker
        thread / slow timer, not the GUI frame tick.
        """
        with self._lock:
            if not self._gcs.connected or self._wave_n_pts <= 0:
                return
            n_want = int(self._wave_n_pts)
            raw = self._gcs.query('GWD? 1', wait_s=3.0)
        sample_time = None
        for line in raw.splitlines():
            if 'SAMPLE_TIME' in line and '=' in line:
                try:
                    sample_time = float(line.split('=', 1)[1].strip())
                except ValueError:
                    pass
        body = raw.split('# END_HEADER', 1)[-1]
        a_vals = []
        b_vals = []
        for line in body.splitlines():
            parts = line.strip().split()
            if len(parts) < 2:
                continue
            try:
                a_vals.append(float(parts[0]))
                b_vals.append(float(parts[1]))
            except ValueError:
                continue
            if len(a_vals) >= n_want:
                break
        if len(a_vals) < 8:
            return
        a = np.asarray(a_vals[:n_want], dtype=float)
        b = np.asarray(b_vals[:n_want], dtype=float)
        with self._lock:
            self._table_vpp_a = float(np.ptp(a))
            self._table_vpp_b = float(np.ptp(b))
            if sample_time and sample_time > 0 and n_want > 0:
                self._wave_freq_hz = 1.0 / (float(n_want) * float(sample_time))

    def getControllerReadback(self):
        """Live E-518 readback: Vpp (wave table), freq, VOL, WGO."""
        with self._lock:
            vol = dict(self._last_vol)
            try:
                if self._gcs.connected:
                    vol = self._parse_vol(self._gcs.query('VOL?', wait_s=0.25))
                    if vol:
                        self._last_vol.update(vol)
            except Exception:
                pass
            running = False
            try:
                running = self.wavegen_running() if self._gcs.connected else False
            except Exception:
                running = bool(self._modulating)
            return SimpleNamespace(
                vpp_a=float(self._table_vpp_a),
                vpp_b=float(self._table_vpp_b),
                freq_hz=float(self._wave_freq_hz),
                vol_a=float(vol.get(1, float('nan'))),
                vol_b=float(vol.get(2, float('nan'))),
                wavegen_running=bool(running),
                parked=bool(self._parked),
                mode=('PARKED@%.0fV' % self._park_v) if self._parked else (
                    'MODULATING' if running or self._modulating else 'IDLE'),
                n_pts=int(self._wave_n_pts),
                radius_mrad=float(self._radius),
                cmd_freq_hz=float(self._freq),
            )


def connect_pi_modulator(
        host=DEFAULT_E518_HOST,
        port=DEFAULT_E518_PORT,
        serial_number=DEFAULT_SERIAL,
        **kwargs):
    """Connect and setUp E-518; raises ``PiGcsError`` on failure."""
    return PiE518Modulator(
        host=host, port=port, serial_number=serial_number,
        connect=True, **kwargs)
