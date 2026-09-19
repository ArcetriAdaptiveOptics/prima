"""DataElab quantities stored in Ekarus ``orca_data`` files."""

from arte.dataelab.base_timeseries import BaseTimeSeries

from ekarus_telemetry_keys import EkarusTelemetryKeys
from ekarelab.numpy_loader import NumpyDataLoader


class OrcaFrames(BaseTimeSeries):
    def __init__(self, filename):
        super().__init__(
            NumpyDataLoader(filename, key=EkarusTelemetryKeys.ORCA_CUBE),
            time_vector=NumpyDataLoader(filename, key=EkarusTelemetryKeys.ORCA_TIMESTAMP),
            axes=('time', 'y', 'x'), data_label='ORCA frames')