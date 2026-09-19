"""DataElab quantities stored in Ekarus ``cblue_data`` files."""

from arte.dataelab.base_timeseries import BaseTimeSeries

from ekarus_telemetry_keys import EkarusTelemetryKeys
from ekarelab.numpy_loader import NumpyDataLoader


class CblueFrames(BaseTimeSeries):
    def __init__(self, filename):
        super().__init__(
            NumpyDataLoader(filename, key=EkarusTelemetryKeys.CBLUE_CUBE),
            time_vector=NumpyDataLoader(filename, key=EkarusTelemetryKeys.CBLUE_TIMESTAMP),
            axes=('time', 'y', 'x'), data_label='CBLUE frames')