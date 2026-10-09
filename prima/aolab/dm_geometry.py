"""BMC Multi-DM 140 geometry and modal bases.

Actuator order (BMC user order, MULTI140.map): 12x12 grid, row-major,
without the 4 corners -> A0..A139.  Pitch 400 um, active area ~4.4 mm.

The bench pupil (~4.5 mm diameter) is centred on the grid, so the outer
ring of actuators is only partially illuminated and the corners of the
grid are outside: those actuators are *not seen* by the WFS.  Modal bases
are therefore defined on the actuators inside (or close to) the pupil and
the others are "slaved" (kept at the flat).
"""
from __future__ import annotations

import math

import numpy as np

GRID = 12
N_ACT = 140
PITCH_MM = 0.400


def actuator_rc() -> tuple[np.ndarray, np.ndarray]:
    rows, cols = [], []
    for r in range(GRID):
        for c in range(GRID):
            if r in (0, GRID - 1) and c in (0, GRID - 1):
                continue
            rows.append(r)
            cols.append(c)
    return np.asarray(rows), np.asarray(cols)


def actuator_xy_mm() -> tuple[np.ndarray, np.ndarray]:
    """Actuator centres in mm, origin at grid centre (x=cols, y=rows)."""
    r, c = actuator_rc()
    x = (c - (GRID - 1) / 2.0) * PITCH_MM
    y = (r - (GRID - 1) / 2.0) * PITCH_MM
    return x.astype(float), y.astype(float)


def to_grid(vec: np.ndarray, fill=np.nan) -> np.ndarray:
    """140-vector -> 12x12 image (corners = fill) for display."""
    g = np.full((GRID, GRID), fill, dtype=float)
    r, c = actuator_rc()
    g[r, c] = np.asarray(vec, dtype=float).ravel()[:N_ACT]
    return g


def from_grid(grid: np.ndarray) -> np.ndarray:
    r, c = actuator_rc()
    return np.asarray(grid, dtype=float)[r, c]


def pupil_actuators(pupil_diam_mm: float = 4.5, margin: float = 0.0
                    ) -> np.ndarray:
    """Boolean mask of actuators whose centre is inside the pupil
    (+ margin in pitch units).  Default 4.5 mm pupil -> ~ 96 actuators."""
    x, y = actuator_xy_mm()
    rad = 0.5 * pupil_diam_mm + margin * PITCH_MM
    return np.hypot(x, y) <= rad + 1e-9


# --------------------------------------------------------------- Zernike

def _noll_to_nm(j: int) -> tuple[int, int]:
    n = 0
    j1 = j - 1
    while j1 > n:
        n += 1
        j1 -= n
    m = (-1) ** j * ((n % 2) + 2 * int((j1 + ((n + 1) % 2)) / 2.0))
    return n, m


def zernike(j: int, rho: np.ndarray, theta: np.ndarray) -> np.ndarray:
    """Noll-normalised Zernike j (1=piston) on (rho, theta)."""
    n, m = _noll_to_nm(j)
    R = np.zeros_like(rho, dtype=float)
    for k in range((n - abs(m)) // 2 + 1):
        R += ((-1) ** k * math.factorial(n - k)
              / (math.factorial(k) * math.factorial((n + abs(m)) // 2 - k)
                 * math.factorial((n - abs(m)) // 2 - k))) * rho ** (n - 2 * k)
    if m == 0:
        return math.sqrt(n + 1) * R
    if m > 0:
        return math.sqrt(2 * (n + 1)) * R * np.cos(m * theta)
    return math.sqrt(2 * (n + 1)) * R * np.sin(-m * theta)


ZERNIKE_NAMES = {
    1: 'piston', 2: 'tip', 3: 'tilt', 4: 'focus', 5: 'astig 45',
    6: 'astig 0', 7: 'coma y', 8: 'coma x', 9: 'trefoil y',
    10: 'trefoil x', 11: 'spherical'}


# --------------------------------------------------------------- bases

def _orthonormalise(B: np.ndarray, w: np.ndarray | None = None
                    ) -> np.ndarray:
    """Gram-Schmidt (via QR) columns of B on the active actuators."""
    q, r = np.linalg.qr(B)
    # keep sign convention of the original columns
    s = np.sign(np.diag(r))
    s[s == 0] = 1
    return q * s


def zernike_basis(active: np.ndarray, n_modes: int,
                  pupil_diam_mm: float = 4.5) -> np.ndarray:
    """(140, n_modes) Zernike modes from tip (j=2), sampled on actuators,
    zero on slaved actuators, orthonormal on the active set and scaled to
    unit RMS over the active actuators."""
    x, y = actuator_xy_mm()
    R = 0.5 * pupil_diam_mm
    rho = np.hypot(x, y) / R
    th = np.arctan2(y, x)
    na = int(active.sum())
    n_modes = int(min(n_modes, na - 1))
    Z = np.stack([zernike(j, rho[active], th[active])
                  for j in range(2, n_modes + 2)], axis=1)
    Z = Z - Z.mean(axis=0, keepdims=True)
    Q = _orthonormalise(Z) * math.sqrt(na)  # unit RMS
    out = np.zeros((N_ACT, n_modes))
    out[active] = Q
    return out


def kl_basis(active: np.ndarray, n_modes: int | None = None,
             r0_mm: float = 0.5, L0_mm: float = 50.0) -> np.ndarray:
    """Karhunen-Loeve modes of von Karman turbulence on the active
    actuators (diagonalised phase covariance, piston removed).  Ordered by
    decreasing variance -> natural 'low order first' modal basis.
    Unit RMS over active actuators."""
    x, y = actuator_xy_mm()
    xa, ya = x[active], y[active]
    na = xa.size
    d = np.hypot(xa[:, None] - xa[None, :], ya[:, None] - ya[None, :])
    # von Karman phase covariance, up to a constant factor:
    #   C(r) ~ (k0 r)^(5/6) K_{5/6}(k0 r),  C(0) = 2^(-1/6) Gamma(5/6)
    from scipy.special import kv, gamma
    k0 = 2 * np.pi / L0_mm
    rr = np.where(d == 0, 1.0, d)
    cov = (k0 * rr) ** (5 / 6) * kv(5 / 6, k0 * rr)
    cov[d == 0] = 2 ** (-1 / 6) * gamma(5 / 6)
    # remove piston: P cov P
    P = np.eye(na) - np.ones((na, na)) / na
    cov = P @ cov @ P
    cov = 0.5 * (cov + cov.T)
    w, V = np.linalg.eigh(cov)
    order = np.argsort(w)[::-1]
    V = V[:, order]
    n = na - 1 if n_modes is None else int(min(n_modes, na - 1))
    V = V[:, :n] * math.sqrt(na)
    # sign convention: make the largest |value| positive
    for k in range(n):
        if V[np.argmax(np.abs(V[:, k])), k] < 0:
            V[:, k] *= -1
    out = np.zeros((N_ACT, n))
    out[active] = V
    return out


def zonal_basis(active: np.ndarray) -> np.ndarray:
    idx = np.flatnonzero(active)
    out = np.zeros((N_ACT, idx.size))
    out[idx, np.arange(idx.size)] = 1.0
    return out


def hadamard_basis(active: np.ndarray) -> np.ndarray:
    """Hadamard patterns on the active actuators (good SNR for IM)."""
    from scipy.linalg import hadamard
    idx = np.flatnonzero(active)
    n = idx.size
    H = hadamard(2 ** int(math.ceil(math.log2(n))))[:n, :n].astype(float)
    out = np.zeros((N_ACT, n))
    out[idx] = H
    return out


def make_basis(kind: str, active: np.ndarray, n_modes: int | None = None,
               pupil_diam_mm: float = 4.5) -> np.ndarray:
    kind = (kind or 'kl').lower()
    na = int(active.sum())
    if kind == 'zonal':
        B = zonal_basis(active)
    elif kind == 'hadamard':
        B = hadamard_basis(active)
    elif kind in ('zernike', 'zern'):
        B = zernike_basis(active, n_modes or na - 1, pupil_diam_mm)
    elif kind == 'kl':
        B = kl_basis(active, n_modes)
    else:
        raise ValueError('unknown basis %r (kl|zernike|zonal|hadamard)' % kind)
    if n_modes is not None:
        B = B[:, :int(n_modes)]
    return B
