"""
daoEkarusShmMap
===============
Resolves ICD parameter names (used in Get/Set commands) to SHM file paths.

Flow
----
  param name  ->  (YAML config)  ->  SHM_HANDLE  ->  (daoEkarusShmNames)  ->  path

The YAML is the only place that couples ICD param names to SHM handles.
Actual file paths remain the single source of truth in daoEkarusShmNames.py.
"""

import logging
import os
from typing import Optional

import numpy as np
import yaml

import dao
import daoEkarusShmNames as _shm

LOG = logging.getLogger("ekarus.shmmap")

# Get DAOROOT from environment; fall back to the current directory if not set
try:
    dao_root = os.environ.get("DAOROOT", os.path.dirname(__file__))
except Exception as e:
    LOG.error("Error occurred while fetching DAOROOT: %s", e)
    raise RuntimeError("Failed to initialize DAOROOT")

_DEFAULT_CONFIG = os.path.join(
    dao_root, "config", "daoEkarusServerConfig.yaml"
)


class ShmParamMap:
    """Load the YAML config and resolve parameter names to SHM paths."""

    def __init__(self, config_path: str = _DEFAULT_CONFIG) -> None:
        with open(config_path) as fh:
            cfg = yaml.safe_load(fh)
        self._params: dict = cfg.get("parameters", {})
        self._shm_cache: dict[str, dao.shm] = {}
        LOG.info("Loaded %d parameter mappings from %s", len(self._params), config_path)

    # ------------------------------------------------------------------
    # Path resolution
    # ------------------------------------------------------------------

    def get_shm_path(self, param: str) -> Optional[str]:
        """Return the SHM file path for *param*, or None if not found."""
        entry = self._params.get(param)
        if entry is None:
            LOG.warning("Unknown parameter %r", param)
            return None
        handle = entry.get("shm")
        path = getattr(_shm, handle, None)
        if path is None:
            LOG.error("SHM handle %r not found in daoEkarusShmNames", handle)
        return path

    # ------------------------------------------------------------------
    # Access helpers
    # ------------------------------------------------------------------

    def get_access(self, param: str) -> Optional[str]:
        """Return the access mode ('read' | 'write' | 'readwrite') for *param*."""
        entry = self._params.get(param)
        return entry.get("access", "readwrite") if entry else None

    def is_readable(self, param: str) -> bool:
        return self.get_access(param) in ("read", "readwrite")

    def is_writable(self, param: str) -> bool:
        return self.get_access(param) in ("write", "readwrite")

    # ------------------------------------------------------------------
    # SHM I/O
    # ------------------------------------------------------------------

    def open_shm(self, param: str) -> "dao.shm":
        """Return a cached dao.shm handle for *param*, opening it on first call."""
        if param not in self._shm_cache:
            path = self.get_shm_path(param)
            if path is None:
                raise ValueError(f"No SHM mapping for parameter {param!r}")
            LOG.debug("Opening SHM %s -> %s", param, path)
            self._shm_cache[param] = dao.shm(path)
        return self._shm_cache[param]

    def read_shm(self, param: str) -> np.ndarray:
        """Read and return the current SHM data for *param*."""
        return self.open_shm(param).get_data()

    def write_shm(self, param: str, data: np.ndarray) -> None:
        """Write *data* to the SHM for *param*, casting to the SHM's native dtype and shape."""
        handle = self.open_shm(param)
        current = handle.get_data()
        data = np.asarray(data, dtype=current.dtype).reshape(current.shape)
        handle.set_data(data)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def list_params(self) -> list[str]:
        """Return all known parameter names."""
        return list(self._params.keys())
