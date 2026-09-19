"""Pseudo-open-loop modal coefficients for Ekarus telemetry."""

import numpy as np
from astropy import units as u
from arte.dataelab.base_timeseries import BaseTimeSeries
from arte.dataelab.data_loader import OnTheFlyLoader


def delay_in_frames(frame_rate_hz, fixed_delay_seconds=1.1e-3):
    """Return the AO-loop delay in frames including one camera exposure."""
    if frame_rate_hz <= 0:
        raise ValueError('frame_rate_hz must be positive.')
    return fixed_delay_seconds * frame_rate_hz + 1


class PseudoOpenLoopModes(BaseTimeSeries):
    def __init__(self, residual_modes, integrated_modes, delay_seconds):
        def aligned_data():
            residual_times = np.asarray(residual_modes.get_time_vector())
            integrated_times = np.asarray(integrated_modes.get_time_vector())
            valid = residual_times - delay_seconds >= integrated_times[0]
            target_times = residual_times[valid] - delay_seconds
            residual_data = residual_modes.get_data().to_value(u.nm)[valid]
            integrated_data = integrated_modes.get_data().to_value(u.nm)
            delayed_integrated_data = np.column_stack([
                np.interp(target_times, integrated_times, integrated_data[:, mode])
                for mode in range(integrated_data.shape[1])
            ])
            return residual_data + delayed_integrated_data

        def aligned_timestamps():
            residual_times = np.asarray(residual_modes.get_time_vector())
            integrated_times = np.asarray(integrated_modes.get_time_vector())
            return residual_times[residual_times - delay_seconds >= integrated_times[0]]

        data = OnTheFlyLoader(aligned_data)
        timestamps = OnTheFlyLoader(aligned_timestamps)
        super().__init__(data, time_vector=timestamps, astropy_unit=u.nm,
                         axes=('time', 'modes'),
                         data_label='Pseudo-open-loop modal coefficients')