"""DM influence functions measured with the calibration interferometer."""

import numpy as np
from arte.dataelab.base_data import BaseData

from ekarelab.numpy_loader import NumpyDataLoader


class InfluenceFunctions(BaseData):
    def __init__(self, filename):
        super().__init__(NumpyDataLoader(filename),
                         axes=('actuators', 'y', 'x'),
                         data_label='DM influence functions')

    def valid_pixels(self):
        """Return pixels illuminated by at least one actuator influence function."""
        return self.get_data().sum(axis=0) != 0

    def matrix(self):
        """Return influence functions as a matrix of shape (actuators, valid_pixels)."""
        influence_functions = self.get_data()
        return influence_functions[:, self.valid_pixels()]