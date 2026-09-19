"""Signal-to-modes reconstructor for Ekarus."""

from astropy import units as u
from arte.dataelab.base_data import BaseData

from ekarus_telemetry_keys import EkarusTelemetryKeys
from ekarelab.numpy_loader import NumpyDataLoader


class SignalToModesReconstructor(BaseData):
    def __init__(self, filename):
        super().__init__(NumpyDataLoader(filename, key=EkarusTelemetryKeys.S2M),
                         astropy_unit=u.dimensionless_unscaled, axes=('modes', 'signals'))