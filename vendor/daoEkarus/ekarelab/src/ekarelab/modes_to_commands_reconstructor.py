"""Modes-to-commands reconstructor for Ekarus."""

from astropy import units as u
from arte.dataelab.base_data import BaseData

from ekarus_telemetry_keys import EkarusTelemetryKeys
from ekarelab.numpy_loader import NumpyDataLoader


class ModesToCommandsReconstructor(BaseData):
    def __init__(self, filename):
        super().__init__(NumpyDataLoader(filename, key=EkarusTelemetryKeys.M2C),
                         astropy_unit=u.volt / u.dimensionless_unscaled,
                         axes=('actuators', 'modes'))