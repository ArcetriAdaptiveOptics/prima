"""Offline analyzer for Ekarus loop and CBLUE telemetry."""

from pathlib import Path
from types import SimpleNamespace

from arte.dataelab.base_analyzer import BaseAnalyzer
from arte.dataelab.analyzer_plots import modalplot

from ekarelab.cblue_data import CblueFrames
from ekarelab.commands_to_modes_reconstructor import CommandsToModesReconstructor
from ekarelab.dm_commands import DMCommands
from ekarelab.ekarus_file_walker import EkarusFileWalker
from ekarus_telemetry_keys import EkarusTelemetryKeys
from ekarelab.loop_data import FastTTCommands, FastTTReconstructor
from ekarelab.integrated_modes import IntegratedModes
from ekarelab.influence_functions import InfluenceFunctions
from ekarelab.modes_timeseries import ResidualModes, mode_volts_to_nanometers
from ekarelab.modes_to_commands_reconstructor import ModesToCommandsReconstructor
from ekarelab.orca_data import OrcaFrames
from ekarelab.pseudo_open_loop_modes import PseudoOpenLoopModes, delay_in_frames
from ekarelab.signal_to_modes_reconstructor import SignalToModesReconstructor
from ekarelab.telemetry_data import EkarusDataField, load_scalar
from ekarelab.telescope_data import TelescopeData
from ekarelab.wfs_signals import WfsSignals


class CblueTelemetry(SimpleNamespace):
    @property
    def long_exposure(self):
        return self.frames.time_mean.value - self.background.get_data()


class OrcaTelemetry(SimpleNamespace):
    @property
    def long_exposure(self):
        return self.frames.time_mean.value - self.background.get_data()


class FastTTTelemetry(SimpleNamespace):
    pass


class OcamTelemetry(SimpleNamespace):
    pass


class ModulatorTelemetry(SimpleNamespace):
    pass


class DMTelemetry(SimpleNamespace):
    pass


class LoopTelemetry(SimpleNamespace):
    pass


class TelescopeTelemetry(SimpleNamespace):
    pass


class EkarusAnalyzer(BaseAnalyzer):
    def __init__(self, tag, recalc=False, file_walker=None,
                 fixed_delay_seconds=1.1e-3):
        super().__init__(str(tag), recalc)
        walker = file_walker or EkarusFileWalker(Path.cwd())
        loop_file = str(walker.telemetry_file(tag))
        wfs_intensity_file = str(walker.wfs_intensity_file(tag))
        cblue_file = str(walker.cblue_file(tag))
        orca_file = str(walker.orca_file(tag))

        self.dm = DMTelemetry(
            commands=DMCommands(loop_file),
            offset=EkarusDataField(loop_file, EkarusTelemetryKeys.DM_OFFSET, 'DM offset'),
            timestamps=EkarusDataField(loop_file, EkarusTelemetryKeys.DM_TIMESTAMP_CUBE, 'DM command timestamps'),
            influence_functions=InfluenceFunctions(
                walker.dm468_influence_functions_file()),
        )
        modes_to_commands = ModesToCommandsReconstructor(loop_file)
        self.loop = LoopTelemetry(
            s2m=SignalToModesReconstructor(loop_file),
            m2c=modes_to_commands,
            c2m=CommandsToModesReconstructor(modes_to_commands),
            gain=load_scalar(loop_file, EkarusTelemetryKeys.LP_GAIN, 'Loop gain'),
            leak=load_scalar(loop_file, EkarusTelemetryKeys.LP_LEAK, 'Loop leak'),
            closed_loop_status=bool(load_scalar(loop_file, EkarusTelemetryKeys.CLOSED_LOOP_STATUS, 'Closed-loop status')),
        )
        self.mode_volts_to_nm = mode_volts_to_nanometers(
            self.loop.m2c.get_data(),
            self.dm.influence_functions.matrix())
        self.loop.residual_modes = ResidualModes(
            loop_file, self.mode_volts_to_nm)
        self.loop.integrated_modes = IntegratedModes(
            self.dm.commands, self.loop.c2m, self.mode_volts_to_nm)
        self.wfs_signals = WfsSignals(wfs_intensity_file)
        self.fast_tt = FastTTTelemetry(
            commands=FastTTCommands(loop_file),
            reconstructor=FastTTReconstructor(loop_file),
            closed_loop_status=bool(load_scalar(loop_file, EkarusTelemetryKeys.FAST_TT_CLOSED_LOOP, 'Fast tip-tilt closed-loop status')),
            loop_gain=load_scalar(loop_file, EkarusTelemetryKeys.FAST_TT_LOOP_GAIN, 'Fast tip-tilt loop gain'),
            loop_leak=load_scalar(loop_file, EkarusTelemetryKeys.FAST_TT_LOOP_LEAK, 'Fast tip-tilt loop leak'),
        )
        self.ocam = OcamTelemetry(
            dark=EkarusDataField(loop_file, EkarusTelemetryKeys.OCAM_DARK, 'OCAM dark frame', axes=('y', 'x')),
            gain=load_scalar(loop_file, EkarusTelemetryKeys.OCAM_GAIN, 'OCAM gain'),
            fps=load_scalar(loop_file, EkarusTelemetryKeys.OCAM_FPS, 'OCAM frame rate'),
            temperature=load_scalar(loop_file, EkarusTelemetryKeys.OCAM_TEMPERATURE, 'OCAM temperature'),
            mean_frame=EkarusDataField(loop_file, EkarusTelemetryKeys.MEAN_OCAM_FRAME, 'Mean OCAM frame', axes=('y', 'x')),
            reference_frame=EkarusDataField(loop_file, EkarusTelemetryKeys.REF, 'OCAM reference frame', axes=('y', 'x')),
            flat_field=EkarusDataField(loop_file, EkarusTelemetryKeys.OCAM_FLAT, 'OCAM flat field'),
        )
        self.loop.pseudo_open_loop_delay_frames = delay_in_frames(
            self.ocam.fps, fixed_delay_seconds)
        self.loop.pseudo_open_loop_modes = PseudoOpenLoopModes(
            self.loop.residual_modes,
            self.loop.integrated_modes,
            self.loop.pseudo_open_loop_delay_frames / self.ocam.fps)
        self.modulator = ModulatorTelemetry(
            frequency=load_scalar(loop_file, EkarusTelemetryKeys.MODULATOR_FREQUENCY, 'Modulator frequency'),
            radius=load_scalar(loop_file, EkarusTelemetryKeys.MODULATOR_RADIUS, 'Modulator radius'),
            enabled=bool(load_scalar(loop_file, EkarusTelemetryKeys.MODULATOR_ON_OFF, 'Modulator enabled flag')),
        )
        self.telescope = TelescopeTelemetry(
            offset=TelescopeData(loop_file, EkarusTelemetryKeys.TELESCOPE_OFFSET_CUBE, 'Telescope offset'),
            guiding=TelescopeData(loop_file, EkarusTelemetryKeys.TELESCOPE_GUIDING_CUBE, 'Telescope guiding'),
            ra_dec=TelescopeData(loop_file, EkarusTelemetryKeys.TELESCOPE_RADEC_CUBE, 'Telescope RA/DEC'),
        )
        self.valid_pixels = EkarusDataField(loop_file, EkarusTelemetryKeys.VALID_PIXELS, 'Valid pixel map')

        self.cblue = CblueTelemetry(
            frames=CblueFrames(cblue_file),
            background=EkarusDataField(cblue_file, EkarusTelemetryKeys.CBLUE_BACKGROUND, 'CBLUE background', axes=('y', 'x')),
            full_background=EkarusDataField(cblue_file, EkarusTelemetryKeys.CBLUE_FULL_BACKGROUND, 'CBLUE full-frame background', axes=('y', 'x')),
            timestamps=EkarusDataField(cblue_file, EkarusTelemetryKeys.CBLUE_TIMESTAMP, 'CBLUE timestamps'),
            fps=load_scalar(cblue_file, EkarusTelemetryKeys.CBLUE_FPS, 'CBLUE frame rate'),
            dit=load_scalar(cblue_file, EkarusTelemetryKeys.CBLUE_DIT, 'CBLUE exposure time'),
            gain=load_scalar(cblue_file, EkarusTelemetryKeys.CBLUE_GAIN, 'CBLUE gain'),
            temperature=load_scalar(cblue_file, EkarusTelemetryKeys.CBLUE_TEMPERATURE, 'CBLUE temperature'),
            conversion_efficiency=load_scalar(cblue_file, EkarusTelemetryKeys.CBLUE_CONVERSION_EFFICIENCY, 'CBLUE conversion efficiency'),
            loop_status=load_scalar(cblue_file, EkarusTelemetryKeys.LOOP_STATUS, 'CBLUE loop status'),
            roi=EkarusDataField(cblue_file, EkarusTelemetryKeys.CBLUE_ROI_VECTOR, 'CBLUE ROI vector', axes=('roi_values',)),
        )
        self.orca = OrcaTelemetry(
            frames=OrcaFrames(orca_file),
            pixelscale=0.035,  # arcsec/pixel
            background=EkarusDataField(orca_file, EkarusTelemetryKeys.ORCA_BACKGROUND, 'ORCA background', axes=('y', 'x')),
            full_background=EkarusDataField(orca_file, EkarusTelemetryKeys.ORCA_FULL_BACKGROUND, 'ORCA full-frame background', axes=('y', 'x')),
            timestamps=EkarusDataField(orca_file, EkarusTelemetryKeys.ORCA_TIMESTAMP, 'ORCA timestamps'),
            fps=load_scalar(orca_file, EkarusTelemetryKeys.ORCA_FPS, 'ORCA frame rate'),
            dit=load_scalar(orca_file, EkarusTelemetryKeys.ORCA_DIT, 'ORCA exposure time'),
            temperature=load_scalar(orca_file, EkarusTelemetryKeys.ORCA_TEMPERATURE, 'ORCA temperature'),
            loop_status=load_scalar(orca_file, EkarusTelemetryKeys.LOOP_STATUS, 'ORCA loop status'),
        )

    def modalplot(self, title=None, **kwargs):
        """Plot residual and pseudo-open-loop modal standard deviations."""
        return modalplot(
            self.loop.residual_modes.time_std.value,
            self.loop.pseudo_open_loop_modes.time_std.value,
            title=self._snapshot_tag if title is None else title,
            res_label='Residual',
            pol_label='Pseudo-open-loop',
            **kwargs)

    def _info(self):
        info = super()._info()
        for name, data in [('nframes_fast_tt', self.fast_tt.commands), ('nframes_residual_modes', self.loop.residual_modes), ('nframes_wfs_signals', self.wfs_signals), ('nframes_dm', self.dm.commands), ('nframes_telescope', self.telescope.offset), ('nframes_cblue', self.cblue.frames), ('nframes_orca', self.orca.frames)]:
            try:
                info[name] = len(data.get_data())
            except Exception:
                info[name] = 'N/A'
        for name in ('gain', 'leak', 'closed_loop_status'):
            info[f'loop_{name}'] = getattr(self.loop, name)
        for name in ('frequency', 'radius', 'enabled'):
            info[f'modulator_{name}'] = getattr(self.modulator, name)
        for name in ('gain', 'fps', 'temperature'):
            info[f'ocam_{name}'] = getattr(self.ocam, name)
        for name in ('closed_loop_status', 'loop_gain', 'loop_leak'):
            info[f'fast_tt_{name}'] = getattr(self.fast_tt, name)
        for name in ('fps', 'dit', 'gain', 'temperature', 'conversion_efficiency', 'loop_status'):
            info[f'cblue_{name}'] = getattr(self.cblue, name)
        for name in ('fps', 'dit', 'temperature', 'loop_status'):
            info[f'orca_{name}'] = getattr(self.orca, name)
        return info