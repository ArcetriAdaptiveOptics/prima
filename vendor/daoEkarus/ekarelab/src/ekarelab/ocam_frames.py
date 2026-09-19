"""OCAM camera frames from Ekarus telemetry."""

from arte.dataelab.base_timeseries import BaseTimeSeries

from ekarus_telemetry_keys import EkarusTelemetryKeys
from ekarelab.numpy_loader import NumpyDataLoader


class OcamFrames(BaseTimeSeries):
    def __init__(self, filename):
        super().__init__(
            NumpyDataLoader(filename, key=EkarusTelemetryKeys.OCAM_CUBE),
            time_vector=NumpyDataLoader(filename, key=EkarusTelemetryKeys.OCAM_TIMESTAMP_CUBE),
            axes=('time', 'y', 'x'), data_label='OCAM frames')