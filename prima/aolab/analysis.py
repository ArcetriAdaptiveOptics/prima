"""Offline analysis of PRIMA telemetry recordings (``arte.dataelab``).

    from prima.aolab.analysis import PrimaAnalyzer, list_tags
    list_tags()                                  # recordings on disk
    an = PrimaAnalyzer.get('20261010_180600-sim-guitest')
    an.summary()
    an.loop.residual_modes.get_data()            # (time, mode) in nm
    an.loop.residual_modes.time_std()            # per-mode rms
    an.loop.residual_modes.plot_spectra()        # PSD (arte TimeSeries)
    an.modalplot()                               # residual vs open loop

Sign conventions (everything is the wavefront produced by the DM, modal
coefficients of the reconstructor basis, unit rms on the active actuators,
converted to *nominal* nm with ``meta['nm_per_unit']``):

    residual_modes     m_k = R s_k     what the WFS measures at frame k
    integrated_modes   c_k             integrator state after frame k;
                                       the loop channel on the DM is M2C c_k
    disturbance_modes  d_k             turb + static channels after frame k,
                                       projected on the modes
    pseudo_open_loop   m_k - c_{k-D}   residual minus the correction that
                                       was on the DM during exposure k

Both DM channels reach the WFS with the same delay D (``delay_frames``):
m_k = d_{k-D} + c_{k-D} + noise, so POL_k estimates d_{k-D} and in closed
loop c ~ -d.  The disturbance applied by the DM is *known* on this bench:
``disturbance_modes`` is the ground truth for the pseudo-open-loop
reconstruction (up to WFS noise, aliasing and the static bench aberration,
a constant offset).  Simulator: D = 1.  Bench (free-running camera, frame
k+1 already exposing when the command of frame k arrives): to be measured.
"""
from __future__ import annotations

import json
from functools import cached_property
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from astropy import units as u
from astropy.io import fits

from arte.dataelab.analyzer_plots import modalplot
from arte.dataelab.base_analyzer import BaseAnalyzer
from arte.dataelab.base_file_walker import AbstractFileNameWalker
from arte.dataelab.base_timeseries import BaseTimeSeries
from arte.dataelab.data_loader import FitsDataLoader, OnTheFlyLoader

from prima.aolab.wfs import valid_mask

REC_DIR = Path.home() / 'git' / 'prima_data' / 'telemetry'


class PrimaFileWalker(AbstractFileNameWalker):
    """``<root>/<tag>/<product>.fits``"""

    def __init__(self, root: Path | str | None = None):
        self._root = Path(root) if root is not None else REC_DIR

    def walker_root_dir(self) -> Path:
        return self._root

    def snapshot_dir(self, tag) -> Path:
        return self._root / str(tag)

    def file(self, tag, product: str) -> Path:
        return self.snapshot_dir(tag) / (product + '.fits')

    def meta_file(self, tag) -> Path:
        return self.snapshot_dir(tag) / 'meta.json'

    def tags(self, pattern: str = '*') -> list[str]:
        if not self._root.is_dir():
            return []
        return sorted(p.name for p in self._root.glob(pattern)
                      if (p / 'meta.json').exists())


def list_tags(pattern: str = '*', root=None) -> list[str]:
    """Recording tags under ``root`` (default ~/git/prima_data/telemetry)."""
    return PrimaFileWalker(root).tags(pattern)


# ------------------------------------------------------------ time series
class _Series(BaseTimeSeries):
    def __init__(self, filename, time_vector, scale=1.0, unit=None,
                 label=None, axes=None, postprocess=None):
        def post(a):
            a = np.asarray(a, float)
            if postprocess is not None:
                a = postprocess(a)
            return a * scale
        super().__init__(FitsDataLoader(filename, postprocess=post),
                         time_vector=time_vector, astropy_unit=unit,
                         data_label=label, axes=axes)


class ModalSeries(_Series):
    """(time, mode) coefficients in nominal nm of wavefront."""

    def __init__(self, filename, time_vector, nm_per_unit, label):
        super().__init__(filename, time_vector, nm_per_unit, u.nm, label,
                         axes=('time', 'mode'))


class Slopes(_Series):
    """(time, 2 n_valid) slopes: first half Sx, second half Sy."""

    def __init__(self, filename, time_vector, mask):
        self.valid2d = mask
        super().__init__(filename, time_vector, 1.0,
                         u.dimensionless_unscaled, 'WFS slopes',
                         axes=('time', 'slope'))

    def to_maps(self, vec) -> tuple[np.ndarray, np.ndarray]:
        """slope vector -> (Sx, Sy) maps with NaN outside the pupil."""
        vec = np.asarray(getattr(vec, 'value', vec))
        n = int(self.valid2d.sum())
        mx = np.full(self.valid2d.shape, np.nan)
        my = np.full(self.valid2d.shape, np.nan)
        mx[self.valid2d] = vec[:n]
        my[self.valid2d] = vec[n:]
        return mx, my


class _Derived(BaseTimeSeries):
    def __init__(self, func, time_vector, unit, label, axes):
        super().__init__(OnTheFlyLoader(func), time_vector=time_vector,
                         astropy_unit=unit, data_label=label, axes=axes)


# ------------------------------------------------------------ analyzer
class PrimaAnalyzer(BaseAnalyzer):
    """One telemetry recording.  ``tag`` is the directory name under
    ``root`` (or a full path to the recording directory)."""

    def __init__(self, tag, recalc=False, root=None, delay_frames=1):
        p = Path(str(tag)).expanduser()
        if p.is_dir() and (p / 'meta.json').exists():
            tag, root = p.name, p.parent
        super().__init__(str(tag), recalc)
        self._walker = w = PrimaFileWalker(root)
        mf = w.meta_file(tag)
        if not mf.exists():
            raise FileNotFoundError('no recording %s in %s'
                                    % (tag, w.walker_root_dir()))
        self.meta = json.loads(mf.read_text())
        self.dir = w.snapshot_dir(tag)
        self.nm_per_unit = float(self.meta['nm_per_unit'])
        self.delay_frames = int(delay_frames)
        sc = fits.getdata(w.file(tag, 'scalars'))
        self._scalars = {k: np.asarray(sc[k], float) for k in sc.names}
        t = self._scalars['t']
        self.time = t - t[0]
        tv = self.time
        f = lambda name: w.file(tag, name)      # noqa: E731
        k = self.nm_per_unit
        lp = self.meta['loop']

        npix = self.meta.get('wfs', {}).get('npix_across', 32)
        self.wfs = SimpleNamespace(
            slopes=Slopes(f('slopes'), tv, valid_mask(npix)),
            frames=BaseTimeSeries(FitsDataLoader(f('frames')),
                                  data_label='camera frames',
                                  axes=('time', 'y', 'x')),
            flux=self.scalar('flux'), dark=self.scalar('dark'),
            exposure_ms=self.meta['camera']['exposure_ms'],
            camera=self.meta['camera'])
        self.loop = SimpleNamespace(
            residual_modes=ModalSeries(f('modes'), tv, k,
                                       'residual modes'),
            integrated_modes=ModalSeries(f('int_modes'), tv, k,
                                         'integrated modes'),
            disturbance_modes=ModalSeries(f('dist_modes'), tv, k,
                                          'disturbance modes'),
            gain=lp['gain'], leak=lp['leak'],
            n_modes=self.meta.get('n_modes', 0),
            closed=bool(np.nanmean(self._scalars['loop_closed']) > 0.5),
            rate_hz=self.meta.get('loop_rate_hz', 0.0),
            delay_frames=self.delay_frames)
        self.loop.pseudo_open_loop_modes = _Derived(
            lambda: self.pseudo_open_loop(self.delay_frames),
            tv[self.delay_frames:], u.nm, 'pseudo open-loop modes',
            ('time', 'mode'))
        self.dm = SimpleNamespace(
            commands=_Series(f('dm_cmd'), tv, 1.0, None,
                             'DM command [0..1]', ('time', 'actuator')),
            loop_commands=_Series(f('loop_cmd'), tv, k, u.nm,
                                  'loop channel', ('time', 'actuator')),
            disturbance_commands=_Series(f('dist_cmd'), tv, k, u.nm,
                                         'disturbance channels',
                                         ('time', 'actuator')))
        self.dm.residual_commands = _Derived(
            self._dm_residual, tv, u.nm,
            'disturbance + correction on the DM', ('time', 'actuator'))
        self.modulator = SimpleNamespace(**self.meta.get('modulator', {}))

    # -------------------------------------------------------- helpers
    def scalar(self, name: str) -> BaseTimeSeries:
        """Per-frame scalar (t, frame, flux, dark, slope_rms, ...)."""
        v = self._scalars[name]
        return BaseTimeSeries(v, time_vector=self.time, data_label=name)

    @property
    def scalar_names(self) -> list[str]:
        return list(self._scalars)

    @cached_property
    def calib(self) -> SimpleNamespace:
        """Calibration in use during the recording: im, rec, m2c, sv
        (singular values), ref (reference slopes), flat, active."""
        out = {}
        fn = self._walker.file(self._snapshot_tag, 'calib')
        if fn.exists():
            with fits.open(fn) as h:
                for hdu in h:
                    out[hdu.header.get('CONTENT', hdu.name).lower()] = \
                        np.array(hdu.data)
        if 'active' in out:
            out['active'] = out['active'].astype(bool)
        return SimpleNamespace(**out)

    def _raw(self, name):
        return np.asarray(fits.getdata(self._walker.file(
            self._snapshot_tag, name)), float)

    def _dm_residual(self):
        return (self._raw('dist_cmd') + self._raw('loop_cmd')) \
            * self.nm_per_unit

    def pseudo_open_loop(self, delay_frames: int) -> np.ndarray:
        """POL modes [nm] for delay D, frames D..N-1 (try several D)."""
        m, c = self._raw('modes'), np.nan_to_num(self._raw('int_modes'))
        D = int(delay_frames)
        return (m[D:] - (c[:-D] if D else c)) * self.nm_per_unit

    # ---------------------------------------------------------- plots
    def modalplot(self, reference: str = 'pol', **kwargs):
        """Residual vs open-loop rms per mode.  ``reference`` = 'pol'
        (pseudo open loop) or 'disturbance' (what the DM injected)."""
        res = np.nanstd(self.loop.residual_modes.get_data().value, axis=0)
        if reference == 'pol':
            ref = np.nanstd(self.loop.pseudo_open_loop_modes.get_data()
                            .value, axis=0)
            lbl = 'pseudo open loop (D=%d)' % self.delay_frames
        else:
            d = self.loop.disturbance_modes.get_data().value
            ref = np.nanstd(d, axis=0)
            lbl = 'disturbance (DM)'
        kwargs.setdefault('title', self._snapshot_tag)
        return modalplot(res * u.nm, ref * u.nm, res_label='residual',
                         pol_label=lbl, **kwargs)

    # ----------------------------------------------------------- info
    def _info(self):
        m = self.meta
        info = super()._info()
        info.update({
            'mode': m.get('mode'), 'label': m.get('label', ''),
            'n_frames': m.get('n_frames'),
            'loop_rate_hz': '%.1f' % m.get('loop_rate_hz', 0),
            'dropped_frames': m.get('dropped_frames'),
            'loop_closed': self.loop.closed,
            'gain': self.loop.gain, 'leak': self.loop.leak,
            'n_modes': self.loop.n_modes,
            'basis': m.get('im', {}).get('basis'),
            'exposure_ms': self.wfs.exposure_ms,
            'modulation': '%s mrad @ %s Hz' % (
                m['modulator'].get('radius_mrad'),
                m['modulator'].get('freq_hz')),
            'turbulence': m.get('turbulence', {}),
            'static': m.get('static', {}),
            'nm_per_unit': m.get('nm_per_unit')})
        return info
