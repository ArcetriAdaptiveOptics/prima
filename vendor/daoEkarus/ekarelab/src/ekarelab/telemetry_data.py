"""Generic DataElab quantities stored in Ekarus telemetry files."""

import numpy as np
from arte.dataelab.base_data import BaseData

from ekarelab.numpy_loader import NumpyDataLoader


class EkarusDataField(BaseData):
    def __init__(self, filename, key, data_label, axes=None):
        super().__init__(NumpyDataLoader(filename, key=key), data_label=data_label, axes=axes)


def load_scalar(filename, key, data_label):
    value = EkarusDataField(filename, key, data_label).get_data()
    if isinstance(value, np.ndarray):
        return value.squeeze().item()
    if isinstance(value, np.generic):
        return value.item()
    return value