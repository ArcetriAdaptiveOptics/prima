"""WFS intensity signals from Ekarus telemetry."""

from arte.dataelab.base_timeseries import BaseTimeSeries

from ekarus_telemetry_keys import EkarusTelemetryKeys
from ekarelab.numpy_loader import NumpyDataLoader


class WfsSignals(BaseTimeSeries):
    def __init__(self, filename):
        super().__init__(
            NumpyDataLoader(filename, key=EkarusTelemetryKeys.WFS1_SIGNALS_CUBE),
            axes=('time', 'signals'), data_label='WFS intensity signals')