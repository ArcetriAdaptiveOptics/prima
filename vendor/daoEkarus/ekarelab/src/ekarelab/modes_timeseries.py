"""Residual modal coefficients from Ekarus loop telemetry."""

import datetime
import numpy as np
from astropy import units as u
from arte.dataelab.base_timeseries import BaseTimeSeries

from ekarus_telemetry_keys import EkarusTelemetryKeys
from ekarelab.numpy_loader import NumpyDataLoader


def mode_volts_to_nanometers(m2c, influence_functions):
    """Return the wavefront RMS amplitude of each mode in nanometers per volt."""
    surface_to_wavefront = 2
    m2c = np.asarray(getattr(m2c, 'value', m2c))
    influence_functions = np.asarray(influence_functions)
    if influence_functions.shape[0] != m2c.shape[0]:
        raise ValueError(
            'Influence functions must have shape (actuators, pixels): '
            f'IF shape is {influence_functions.shape}, M2C shape is {m2c.shape}.')
    mode_amplitudes = np.std(
        surface_to_wavefront * influence_functions.T @ m2c, axis=0)
    return mode_amplitudes * 1e9


def timestamps_to_seconds(values):
    """Convert absolute timestamps to seconds relative to the first sample."""
    values = np.asarray(values)
    if values.dtype.kind == 'M':
        seconds = values.astype('datetime64[ns]').astype('int64') / 1e9
        return seconds - seconds[0]
    if values.dtype == object and values.size and isinstance(values.flat[0], datetime.datetime):
        return np.array([(value - values.flat[0]).total_seconds() for value in values])
    return values.astype(float)


class ResidualModes(BaseTimeSeries):
    def __init__(self, filename, mode_volts_to_nm):
        data = NumpyDataLoader(filename, key=EkarusTelemetryKeys.MODE_CUBE)
        data._postprocess = lambda values: np.squeeze(values) * mode_volts_to_nm
        time = NumpyDataLoader(filename, key=EkarusTelemetryKeys.DM_TIMESTAMP_CUBE)
        time._postprocess = timestamps_to_seconds
        super().__init__(data, time_vector=time, astropy_unit=u.nm,
                 axes=('time', 'modes'), data_label='Residual modal coefficients')