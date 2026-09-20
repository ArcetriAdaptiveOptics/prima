"""Matrix–vector multiply for DaoPrima RTC stages.

Mirrors daoEkarus / daoTools:

* C path: ``daoMvMGPU`` (CUDA / cuBLAS) for slopes→modes
* Python path: ``daoTools/apps/daoMvM.py`` (``-g`` → CuPy, else NumPy)

Backend selection
-----------------
1. If ``prefer_gpu`` and CuPy + a CUDA device are available → **gpu** (CuPy).
2. Else → **cpu** (NumPy). Documented in ``backend`` / ``gpu_status()``.

To enable real GPU on this host::

    # NVIDIA driver + nvcc already present (RTX 4060 observed)
    pip install cupy-cuda12x   # match installed CUDA major
"""
from __future__ import annotations

from typing import Optional, Tuple

import numpy as np

_CUPY = None
_CUPY_ERR = None
_GPU_OK = False

try:
    import cupy as _cp  # type: ignore
    _CUPY = _cp
    try:
        n = int(_cp.cuda.runtime.getDeviceCount())
        _GPU_OK = n > 0
        if not _GPU_OK:
            _CUPY_ERR = 'CuPy imported but getDeviceCount()==0'
    except Exception as exc:  # noqa: BLE001
        _CUPY_ERR = 'CuPy CUDA init failed: %s' % exc
        _GPU_OK = False
except Exception as exc:  # noqa: BLE001
    _CUPY_ERR = 'CuPy not importable: %s' % exc
    _GPU_OK = False


def gpu_available() -> bool:
    return bool(_GPU_OK and _CUPY is not None)


def gpu_status() -> dict:
    """Human-readable GPU / CuPy readiness for smoke + docs."""
    info = {
        'cupy_importable': _CUPY is not None,
        'gpu_ok': gpu_available(),
        'error': _CUPY_ERR,
        'needed_to_enable': None,
    }
    if gpu_available():
        try:
            props = _CUPY.cuda.runtime.getDeviceProperties(0)
            name = props['name']
            if isinstance(name, bytes):
                name = name.decode('utf-8', errors='replace')
            info['device0'] = name
            info['cupy_version'] = getattr(_CUPY, '__version__', '?')
        except Exception as exc:  # noqa: BLE001
            info['device0_err'] = str(exc)
    else:
        info['needed_to_enable'] = (
            'Install CuPy matching host CUDA (e.g. `pip install cupy-cuda12x` '
            'with NVIDIA driver + CUDA toolkit). daoBase `daoMvMGPU` binary '
            'also requires a built daoTools/CUDA stack.')
    return info


class MatrixVectorMultiply:
    """Reusable MVM: ``y = M @ x`` with optional GPU residency for ``M``.

    Pattern adapted from ``daoMvM.py``: keep matrix on device, upload vector
    each call, download result.
    """

    def __init__(self, matrix: Optional[np.ndarray] = None,
                 prefer_gpu: bool = True):
        self.prefer_gpu = bool(prefer_gpu)
        self._backend = 'cpu'
        self._m_host: Optional[np.ndarray] = None
        self._m_dev = None
        if matrix is not None:
            self.set_matrix(matrix)

    @property
    def backend(self) -> str:
        return self._backend

    def set_matrix(self, matrix: np.ndarray) -> str:
        m = np.ascontiguousarray(np.asarray(matrix, dtype=np.float32))
        self._m_host = m
        use_gpu = self.prefer_gpu and gpu_available()
        if use_gpu:
            self._m_dev = _CUPY.asarray(m)
            self._backend = 'gpu'
        else:
            self._m_dev = None
            self._backend = 'cpu'
        return self._backend

    def __call__(self, vector: np.ndarray) -> np.ndarray:
        return self.multiply(vector)

    def multiply(self, vector: np.ndarray) -> np.ndarray:
        if self._m_host is None:
            raise RuntimeError('MatrixVectorMultiply: matrix not set')
        v = np.ascontiguousarray(np.asarray(vector, dtype=np.float32)).ravel()
        n_in = self._m_host.shape[1]
        if v.size < n_in:
            v = np.resize(v, n_in)
        elif v.size > n_in:
            v = v[:n_in]
        if self._backend == 'gpu' and self._m_dev is not None:
            vd = _CUPY.asarray(v)
            out = _CUPY.matmul(self._m_dev, vd)
            return _CUPY.asnumpy(out).astype(np.float32, copy=False)
        return np.matmul(self._m_host, v).astype(np.float32, copy=False)


def select_backend(prefer_gpu: bool = True) -> Tuple[str, dict]:
    status = gpu_status()
    if prefer_gpu and status['gpu_ok']:
        return 'gpu', status
    return 'cpu', status
