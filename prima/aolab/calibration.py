"""Interaction matrix (push-pull) and modal reconstructor.

    IM[:, k] = ( s(+a B_k) - s(-a B_k) ) / (2 a)        slopes per unit mode
    R        = V diag(1/sigma) U^T   (truncated SVD of IM)
    modes    = R @ slopes      -> estimated modal amplitudes (DM units)
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class InteractionMatrix:
    im: np.ndarray                 # (n_slopes, n_modes)
    m2c: np.ndarray                # (140, n_modes) modes -> DM command
    amplitude: float
    basis: str
    n_avg: int = 1
    meta: dict = field(default_factory=dict)

    @property
    def n_modes(self) -> int:
        return self.im.shape[1]

    def sensitivity(self) -> np.ndarray:
        """Slope response norm per mode (how well each mode is seen)."""
        return np.linalg.norm(self.im, axis=0)


@dataclass
class Reconstructor:
    rec: np.ndarray                # (n_modes, n_slopes)
    m2c: np.ndarray                # (140, n_modes)
    singular_values: np.ndarray    # of the full IM
    n_kept: int                    # SVD modes kept
    n_modes: int


def push_pull_sequence(n_modes: int, amplitude: float):
    """Yields (mode index, sign, amplitude) in push/pull order."""
    for k in range(n_modes):
        for sgn in (+1, -1):
            yield k, sgn, sgn * amplitude


def build_im(plus: np.ndarray, minus: np.ndarray, amplitude: float
             ) -> np.ndarray:
    return (np.asarray(plus) - np.asarray(minus)) / (2.0 * amplitude)


def make_reconstructor(imat: InteractionMatrix, n_modes: int | None = None,
                       n_cut: int = 0, rcond: float | None = None
                       ) -> Reconstructor:
    """Truncated-SVD pseudo-inverse of the first ``n_modes`` columns.

    ``n_cut``: number of smallest singular values discarded (badly seen
    combinations of modes).  ``rcond``: alternatively discard
    sigma < rcond * sigma_max.
    """
    nm = imat.n_modes if n_modes is None else int(min(n_modes, imat.n_modes))
    D = imat.im[:, :nm]
    U, s, Vt = np.linalg.svd(D, full_matrices=False)
    keep = np.ones_like(s, bool)
    if n_cut > 0:
        keep[len(s) - int(n_cut):] = False
    if rcond is not None:
        keep &= s >= rcond * s.max()
    inv = np.where(keep, 1.0 / np.where(s > 0, s, 1), 0.0)
    rec = (Vt.T * inv) @ U.T
    return Reconstructor(rec, imat.m2c[:, :nm], s, int(keep.sum()), nm)
