"""Commands-to-modes reconstructor for Ekarus."""

import numpy as np
from astropy import units as u
from arte.dataelab.base_data import BaseData


class CommandsToModesReconstructor(BaseData):
    def __init__(self, modes_to_commands):
        commands_to_modes = np.linalg.pinv(modes_to_commands.get_data())
        super().__init__(commands_to_modes,
                         astropy_unit=u.dimensionless_unscaled / u.volt,
                         axes=('modes', 'actuators'))