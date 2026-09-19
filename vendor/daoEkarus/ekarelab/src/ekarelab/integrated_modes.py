"""Modal coefficients reconstructed from Ekarus DM commands."""

from astropy import units as u
from arte.dataelab.base_timeseries import BaseTimeSeries
from arte.dataelab.data_loader import OnTheFlyLoader

from ekarelab.modes_timeseries import timestamps_to_seconds


class IntegratedModes(BaseTimeSeries):
    def __init__(self, dm_commands, commands_to_modes, mode_volts_to_nm):
        def integrated_modes_in_nanometers():
            modes = dm_commands.get_data() @ commands_to_modes.get_data().T
            return modes.value * mode_volts_to_nm

        data = OnTheFlyLoader(
            integrated_modes_in_nanometers)
        timestamps = OnTheFlyLoader(
            lambda: timestamps_to_seconds(dm_commands.get_time_vector()))
        super().__init__(data, time_vector=timestamps,
                         astropy_unit=u.nm,
                         axes=('time', 'modes'),
                         data_label='Integrated modal coefficients')