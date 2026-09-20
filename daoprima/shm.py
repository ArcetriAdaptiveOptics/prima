"""
Lightweight SHM stand-in for DaoPrima demos without daoBase.

When ``dao`` is importable, prefer real ``dao.shm``. Otherwise store arrays
in a process-local registry keyed by the same ``/tmp/….im.shm`` paths used
by ``daoprima.shm_names`` (and daoEkarus). Cross-process file backing can
be added later; for Drop 2 visibility the in-process registry is enough.
"""
from __future__ import annotations

from typing import Dict, Optional

import numpy as np

_REGISTRY: Dict[str, "ShmImage"] = {}

try:
    import dao as _dao  # type: ignore
    _HAS_DAO = True
except Exception:
    _dao = None
    _HAS_DAO = False


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


def shm(name: str, data: Optional[np.ndarray] = None) -> ShmImage:
    """Open or create a named SHM image (dao.shm-compatible call pattern)."""
    if _HAS_DAO:
        if data is None:
            return _dao.shm(name)
        return _dao.shm(name, np.asarray(data))
    if name not in _REGISTRY:
        _REGISTRY[name] = ShmImage(name, data)
    elif data is not None:
        _REGISTRY[name].set_data(data)
    return _REGISTRY[name]


def reset_registry() -> None:
    """Clear in-process SHM (tests / demo restarts). No-op when using dao."""
    _REGISTRY.clear()


def has_dao() -> bool:
    return _HAS_DAO
