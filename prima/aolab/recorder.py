"""Telemetry recorder: N consecutive RTC frames -> FITS files + meta.json.

One directory per recording, named as an ``arte.dataelab`` tag
(exactly one underscore)::

    ~/git/prima_data/telemetry/YYYYMMDD_HHMMSS[-label]/
        meta.json        loop / calibration / camera / modulator / disturbance
        scalars.fits     binary table, one row per frame (t, frame, flux, ...)
        slopes.fits      (N, n_slopes)  slopes minus reference
        modes.fits       (N, n_modes)   reconstructed residual modes  R @ s
        int_modes.fits   (N, n_modes)   integrator state c (loop command, modal)
        dist_modes.fits  (N, n_modes)   disturbance (turb + static) projected
        dm_cmd.fits      (N, 140)       total command sent to the DM [0, 1]
        loop_cmd.fits    (N, 140)       'loop' channel (DM units about flat)
        dist_cmd.fits    (N, 140)       'turb' + 'static' channels
        frames.fits      (K, h, w)      first K camera frames (optional)
        calib.fits       primary: IM, extensions: REC, M2C, REF, FLAT, ACTIVE

Modal coefficients are in DM units (modes have unit rms on the active
actuators); multiply by ``nm_per_unit`` in meta.json for nominal nm of WF.
Frame k of every array is the same RTC iteration: slopes/modes measured on
that frame, commands as they were *after* the update of that iteration.
"""
from __future__ import annotations

import json
import re
import subprocess
import threading
import time
from pathlib import Path

import numpy as np
from astropy.io import fits

SCALAR_KEYS = ('t', 'frame', 'loop_closed', 'slope_rms', 'mode_rms',
               'loop_cmd_rms', 'dist_rms', 'dm_res_rms', 'flux', 'dark',
               'sat_frac')
MAX_BYTES = 2_000_000_000       # refuse recordings above ~2 GB in RAM


def make_tag(label: str = '', when: float | None = None) -> str:
    tag = time.strftime('%Y%m%d_%H%M%S', time.localtime(when))
    label = re.sub(r'[^A-Za-z0-9.+-]+', '-', label.strip()).strip('-')
    return tag + ('-' + label if label else '')


def git_version() -> str:
    try:
        return subprocess.run(
            ['git', 'describe', '--always', '--dirty'], capture_output=True,
            text=True, timeout=2,
            cwd=Path(__file__).resolve().parent).stdout.strip()
    except Exception:
        return ''


class Recorder:
    """Preallocated buffers filled from the RTC thread (``push`` is just
    array copies); ``save`` writes the files."""

    def __init__(self, out_dir: Path, n_frames: int, n_slopes: int,
                 n_modes: int, n_act: int, frame_shape=None,
                 n_cam_frames: int = 0, meta: dict | None = None,
                 calib: dict | None = None):
        self.dir = Path(out_dir)
        self.n_frames = int(n_frames)
        n = self.n_frames
        n_cam = min(int(n_cam_frames), n) if frame_shape else 0
        nbytes = 4 * n * (n_slopes + 3 * max(n_modes, 1) + 3 * n_act) \
            + (2 * n_cam * int(np.prod(frame_shape)) if n_cam else 0)
        if nbytes > MAX_BYTES:
            raise ValueError('recording too large (%.1f GB): fewer frames'
                             % (nbytes / 1e9))
        f32 = np.float32
        self.scal = {k: np.full(n, np.nan) for k in SCALAR_KEYS}
        self.slopes = np.full((n, n_slopes), np.nan, f32)
        self.modes = np.full((n, max(n_modes, 1)), np.nan, f32)
        self.int_modes = np.full_like(self.modes, np.nan)
        self.dist_modes = np.full_like(self.modes, np.nan)
        self.dm_cmd = np.full((n, n_act), np.nan, f32)
        self.loop_cmd = np.full_like(self.dm_cmd, np.nan)
        self.dist_cmd = np.full_like(self.dm_cmd, np.nan)
        self.frames = (np.zeros((n_cam,) + tuple(frame_shape), np.uint16)
                       if n_cam else None)
        self.meta = dict(meta or {})
        self.calib = dict(calib or {})
        self.n = 0
        self.t_start = time.time()
        self.done = threading.Event()
        self.path: Path | None = None
        self.error: str | None = None

    @property
    def full(self) -> bool:
        return self.n >= self.n_frames

    @property
    def progress(self) -> float:
        return self.n / self.n_frames

    def push(self, scal: dict, slopes=None, modes=None, int_modes=None,
             dist_modes=None, dm_cmd=None, loop_cmd=None, dist_cmd=None,
             frame=None) -> bool:
        """Store one RTC iteration; returns True when the buffer is full."""
        i = self.n
        if i >= self.n_frames:
            return True
        for k in SCALAR_KEYS:
            v = scal.get(k)
            self.scal[k][i] = np.nan if v is None else v
        for buf, v in ((self.slopes, slopes), (self.modes, modes),
                       (self.int_modes, int_modes),
                       (self.dist_modes, dist_modes), (self.dm_cmd, dm_cmd),
                       (self.loop_cmd, loop_cmd), (self.dist_cmd, dist_cmd)):
            if v is not None and np.size(v) == buf.shape[1]:
                buf[i] = v
        if self.frames is not None and i < len(self.frames) \
                and frame is not None and frame.shape == self.frames.shape[1:]:
            self.frames[i] = frame
        self.n = i + 1
        return self.n >= self.n_frames

    # ------------------------------------------------------------ save
    def save(self) -> Path:
        n = self.n
        d = self.dir
        d.mkdir(parents=True, exist_ok=False)
        t = self.scal['t'][:n]
        dt = np.diff(t[np.isfinite(t)])
        self.meta.update({
            'n_frames': int(n), 'n_frames_requested': self.n_frames,
            't_start': float(t[0]) if n else self.t_start,
            'duration_s': float(t[-1] - t[0]) if n > 1 else 0.0,
            'loop_rate_hz': float(1 / np.median(dt)) if dt.size else 0.0,
            'dropped_frames': int(np.sum(np.diff(self.scal['frame'][:n]) > 1))
            if n > 1 else 0,
            'files': {}})
        cols = [fits.Column(name=k, format='D', array=self.scal[k][:n])
                for k in SCALAR_KEYS]
        self._write('scalars', fits.BinTableHDU.from_columns(cols),
                    'per-frame scalars')
        arrays = [
            ('slopes', self.slopes, 'slopes - reference (normalised)'),
            ('modes', self.modes, 'residual modes R@s [DM units]'),
            ('int_modes', self.int_modes, 'integrator state [DM units]'),
            ('dist_modes', self.dist_modes, 'disturbance modes [DM units]'),
            ('dm_cmd', self.dm_cmd, 'total DM command [0..1]'),
            ('loop_cmd', self.loop_cmd, 'loop channel [DM units]'),
            ('dist_cmd', self.dist_cmd, 'turb+static channels [DM units]')]
        for name, a, what in arrays:
            if np.all(np.isnan(a[:n])):
                continue             # e.g. no reconstructor -> no modes
            self._write(name, fits.PrimaryHDU(a[:n]), what)
        if self.frames is not None:
            k = min(n, len(self.frames))
            self._write('frames', fits.PrimaryHDU(self.frames[:k]),
                        'raw camera frames [ADU]')
        if self.calib:
            hdus = []
            for name, a in self.calib.items():
                a = np.asarray(a)
                if a.dtype == bool:
                    a = a.astype(np.uint8)
                h = (fits.PrimaryHDU(a) if not hdus
                     else fits.ImageHDU(a, name=name.upper()))
                h.header['CONTENT'] = name
                hdus.append(h)
            fits.HDUList(hdus).writeto(d / 'calib.fits')
            self.meta['files']['calib'] = {
                'file': 'calib.fits', 'hdus': list(self.calib)}
        (d / 'meta.json').write_text(json.dumps(self.meta, indent=1,
                                                default=_json_default))
        self.path = d
        return d

    def _write(self, name, hdu, what):
        hdu.header['CONTENT'] = what
        hdu.writeto(self.dir / (name + '.fits'))
        self.meta['files'][name] = {
            'file': name + '.fits', 'what': what,
            'shape': list(hdu.data.shape) if hdu.data is not None else None}


def _json_default(o):
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, np.generic):
        return o.item()
    return str(o)
