"""
Lightweight SHM for DaoPrima demos without daoBase.

Backend preference:
  1. Real ``dao.shm`` when ``import dao`` works.
  2. Else **file-backed** ``numpy.memmap`` at the same ``/tmp/….im.shm`` paths
     used by ``daoprima.shm_names`` (cross-process read/write).
  3. Optional in-process registry (``force_inprocess=True``) for unit tests.

Does not modify vendor dao* trees.
"""
from __future__ import annotations

import os
from typing import Dict, Optional, Tuple

import numpy as np

_REGISTRY: Dict[str, "ShmImage"] = {}
_FILE_CACHE: Dict[str, "FileShmImage"] = {}

try:
    import dao as _dao  # type: ignore
    _HAS_DAO = True
except Exception:
    _dao = None
    _HAS_DAO = False

# Default: file-backed when dao missing (true write→read across processes)
_FORCE_INPROCESS = os.environ.get('DAOPRIMA_SHM_INPROCESS', '').lower() in (
    '1', 'true', 'yes')


class ShmImage:
    """Minimal get_data / set_data surface matching dao.shm usage in GUIs."""

    def __init__(self, name: str, data: Optional[np.ndarray] = None):
        self.name = name
        if data is None:
            data = np.zeros((1, 1), dtype=np.float32)
        self._data = np.asarray(data).copy()

    def get_data(self) -> np.ndarray:
        return self._data.copy()

    def set_data(self, data) -> None:
        self._data = np.asarray(data).copy()

    def shape(self):
        return self._data.shape

    @property
    def backend(self) -> str:
        return 'inprocess'


class FileShmImage:
    """File-backed IMAGE stand-in at path ``name`` (daoEkarus-style path).

    Layout: little-endian header ``ndim:u32, dtype_code:u32, dims…:u32`` then
    raw C-order payload. ``dtype_code`` 0=float32, 1=float64, 2=uint8, 3=uint32.
    """

    _DTYPE_TO_CODE = {
        np.dtype('float32'): 0,
        np.dtype('float64'): 1,
        np.dtype('uint8'): 2,
        np.dtype('uint32'): 3,
    }
    _CODE_TO_DTYPE = {v: k for k, v in _DTYPE_TO_CODE.items()}

    def __init__(self, name: str, data: Optional[np.ndarray] = None):
        self.name = name
        self._mm = None
        self._shape: Tuple[int, ...] = (1, 1)
        self._dtype = np.dtype(np.float32)
        os.makedirs(os.path.dirname(name) or '.', exist_ok=True)
        if data is not None:
            self._create_or_replace(np.asarray(data))
        elif os.path.exists(name) and os.path.getsize(name) > 0:
            self._open_existing()
        else:
            self._create_or_replace(np.zeros((1, 1), dtype=np.float32))

    def _header_nbytes(self, ndim: int) -> int:
        return 4 + 4 + 4 * ndim  # ndim, dtype_code, dims

    def _create_or_replace(self, arr: np.ndarray) -> None:
        arr = np.ascontiguousarray(arr)
        if arr.dtype not in self._DTYPE_TO_CODE:
            arr = arr.astype(np.float32)
        self._dtype = arr.dtype
        self._shape = tuple(int(x) for x in arr.shape)
        ndim = len(self._shape)
        header = self._header_nbytes(ndim)
        total = header + arr.nbytes
        # truncate / rewrite
        with open(self.name, 'wb') as f:
            f.write(np.array([ndim], dtype='<u4').tobytes())
            f.write(np.array(
                [self._DTYPE_TO_CODE[self._dtype]], dtype='<u4').tobytes())
            f.write(np.array(self._shape, dtype='<u4').tobytes())
            f.write(arr.tobytes(order='C'))
            if f.tell() < total:
                f.truncate(total)
        self._open_existing()

    def _open_existing(self) -> None:
        with open(self.name, 'rb') as f:
            ndim = int(np.frombuffer(f.read(4), dtype='<u4')[0])
            code = int(np.frombuffer(f.read(4), dtype='<u4')[0])
            dims = tuple(
                int(x) for x in np.frombuffer(f.read(4 * ndim), dtype='<u4'))
        self._dtype = self._CODE_TO_DTYPE.get(code, np.dtype('float32'))
        self._shape = dims
        header = self._header_nbytes(ndim)
        self._mm = np.memmap(
            self.name, dtype=self._dtype, mode='r+',
            offset=header, shape=self._shape, order='C')

    def get_data(self) -> np.ndarray:
        if self._mm is None:
            self._open_existing()
        return np.array(self._mm, copy=True)

    def set_data(self, data) -> None:
        arr = np.ascontiguousarray(data)
        if arr.dtype != self._dtype or tuple(arr.shape) != self._shape:
            # reshape / recreate file (consumer may have opened old shape)
            self._create_or_replace(arr)
            # refresh any other cached handles by rewriting; caller re-opens
            return
        self._mm[:] = arr
        self._mm.flush()

    def shape(self):
        return self._shape

    @property
    def backend(self) -> str:
        return 'file'


def shm(name: str, data: Optional[np.ndarray] = None,
        force_inprocess: Optional[bool] = None):
    """Open or create a named SHM image (dao.shm-compatible call pattern)."""
    use_inprocess = (
        _FORCE_INPROCESS if force_inprocess is None else force_inprocess)

    if _HAS_DAO and not use_inprocess:
        if data is None:
            return _dao.shm(name)
        return _dao.shm(name, np.asarray(data))

    if use_inprocess:
        if name not in _REGISTRY:
            _REGISTRY[name] = ShmImage(name, data)
        elif data is not None:
            _REGISTRY[name].set_data(data)
        return _REGISTRY[name]

    # File-backed (default without dao)
    if name in _FILE_CACHE and data is None:
        return _FILE_CACHE[name]
    img = FileShmImage(name, data)
    _FILE_CACHE[name] = img
    return img


def reset_registry() -> None:
    """Clear in-process + file handle caches (does not delete /tmp files)."""
    _REGISTRY.clear()
    _FILE_CACHE.clear()


def has_dao() -> bool:
    return _HAS_DAO


def backend_name() -> str:
    if _HAS_DAO and not _FORCE_INPROCESS:
        return 'dao'
    if _FORCE_INPROCESS:
        return 'inprocess'
    return 'file'
