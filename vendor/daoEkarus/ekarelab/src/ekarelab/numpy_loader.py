import numpy as np

from arte.dataelab.data_loader import NumpyDataLoader as ArteNumpyDataLoader


class NumpyDataLoader(ArteNumpyDataLoader):
    """Load NumPy telemetry files, including dictionaries saved in ``.npy``."""

    def load(self):
        arr = np.load(self._filename, allow_pickle=True)
        if not self._key:
            data = arr
        elif isinstance(arr, np.lib.npyio.NpzFile) or hasattr(arr, 'files'):
            data = arr[self._key]
        elif isinstance(arr, dict):
            data = arr[self._key]
        elif isinstance(arr, np.ndarray) and arr.dtype == object and arr.shape == ():
            data = arr.item()[self._key]
        else:
            try:
                data = arr[self._key]
            except Exception as error:
                raise IndexError(
                    f"Unable to extract key '{self._key}' from '{self._filename}'") from error

        transpose_axes = getattr(self, '_transpose_axes', None)
        if transpose_axes is not None:
            data = data.transpose(*transpose_axes)
        postprocess = getattr(self, '_postprocess', None)
        return postprocess(data) if postprocess else data