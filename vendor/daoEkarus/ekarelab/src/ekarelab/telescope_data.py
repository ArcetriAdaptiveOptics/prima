"""Telescope telemetry from Ekarus loop data."""

import numpy as np
from arte.dataelab.base_timeseries import BaseTimeSeries

from ekarus_telemetry_keys import EkarusTelemetryKeys
from ekarelab.modes_timeseries import timestamps_to_seconds
from ekarelab.numpy_loader import NumpyDataLoader


class TelescopeData(BaseTimeSeries):
    def __init__(self, filename, key, data_label):
        data = NumpyDataLoader(filename, key=key)
        data._postprocess = np.squeeze
        timestamps = NumpyDataLoader(
            filename, key=EkarusTelemetryKeys.DM_TIMESTAMP_CUBE)
        timestamps._postprocess = timestamps_to_seconds
        super().__init__(data, time_vector=timestamps,
                         axes=('time', 'values'), data_label=data_label)