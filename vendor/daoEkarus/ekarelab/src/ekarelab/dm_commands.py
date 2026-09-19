"""Deformable-mirror commands from Ekarus loop telemetry."""

import numpy as np
from astropy import units as u
from arte.dataelab.base_timeseries import BaseTimeSeries

from ekarus_telemetry_keys import EkarusTelemetryKeys
from ekarelab.numpy_loader import NumpyDataLoader


class DMCommands(BaseTimeSeries):
    def __init__(self, filename):
        data = NumpyDataLoader(filename, key=EkarusTelemetryKeys.DM_CMD_CUBE)
        data._postprocess = np.squeeze
        time = NumpyDataLoader(filename, key=EkarusTelemetryKeys.DM_TIMESTAMP_CUBE)
        super().__init__(data, time_vector=time, astropy_unit=u.volt,
                         axes=('time', 'actuators'), data_label='DM commands')