"""DataElab quantities stored in Ekarus ``loop_data`` files."""

import numpy as np
from astropy import units as u
from arte.dataelab.base_timeseries import BaseTimeSeries

from ekarus_telemetry_keys import EkarusTelemetryKeys
from ekarelab.numpy_loader import NumpyDataLoader
from ekarelab.telemetry_data import EkarusDataField


class FastTTCommands(BaseTimeSeries):
    def __init__(self, filename):
        data = NumpyDataLoader(filename, key=EkarusTelemetryKeys.FAST_TT_COMMANDS_CUBE)
        data._postprocess = np.squeeze
        super().__init__(data, astropy_unit=u.dimensionless_unscaled,
                         axes=('time', 'fast_tt_commands'), data_label='Fast tip-tilt commands')


class FastTTReconstructor(EkarusDataField):
    def __init__(self, filename):
        super().__init__(filename, EkarusTelemetryKeys.FAST_TT_RECONSTRUCTOR,
                         'Fast tip-tilt reconstructor', axes=('fast_tt_commands', 'signals'))