"""Zonal IFF acquire → process → flatten command (opticalib-compatible flow).

Uses in-memory arrays so fake tests do not need opticalib TN folders.
HW scripts can persist cubes to disk and feed ``opticalib.dmutils.flattening``
when a tracking number is available.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class IffResult:
    amplitudes: np.ndarray          # (n_acts,) poke amp used
    plus: np.ndarray                # (n_slopes, n_acts)
    minus: np.ndarray               # (n_slopes, n_acts)
    im: np.ndarray                  # (n_slopes, n_acts) = (plus-minus)/(2 amp)


@dataclass
class FlattenResult:
    cmd_delta: np.ndarray           # differential about bias
    cmd_abs: np.ndarray             # absolute drive
    rms_before: float
    rms_after: float
    singular_values: np.ndarray
    n_modes: int


def acquire_zonal_iff(
        dm,
        wfs,
        amplitude: float = 0.05,
        act_list: np.ndarray | None = None,
        settle_s: float = 0.0,
) -> IffResult:
    """Push–pull zonal IFF about current bias."""
    import time
    n = int(dm.n_acts)
    acts = (np.arange(n) if act_list is None
            else np.asarray(act_list, dtype=int).ravel())
    amp = float(amplitude)
    # Probe slope size
    s0 = np.asarray(wfs.acquire_map(output_type='slopes1d'), dtype=float).ravel()
    n_s = s0.size
    plus = np.zeros((n_s, n), dtype=float)
    minus = np.zeros((n_s, n), dtype=float)
    amps = np.zeros(n, dtype=float)
    start = dm.get_shape().copy()
    for a in acts:
        amps[a] = amp
        poke = np.zeros(n)
        poke[a] = amp
        dm.set_shape(poke, differential=True)
        if settle_s:
            time.sleep(settle_s)
        plus[:, a] = np.asarray(
            wfs.acquire_map(output_type='slopes1d'), dtype=float).ravel()
        dm.set_shape(-poke, differential=True)
        if settle_s:
            time.sleep(settle_s)
        minus[:, a] = np.asarray(
            wfs.acquire_map(output_type='slopes1d'), dtype=float).ravel()
        dm.set_shape(start, differential=False)
    im = (plus - minus) / (2.0 * np.maximum(amps, 1e-12))
    # Zero unused actuators
    unused = np.setdiff1d(np.arange(n), acts)
    im[:, unused] = 0.0
    return IffResult(amplitudes=amps, plus=plus, minus=minus, im=im)


def process_iff(iff: IffResult, svd_threshold: float = 1e-3) -> tuple[np.ndarray, np.ndarray]:
    """Return (reconstructor R, singular values) from IM via SVD.

    ``cmd = -R @ slopes`` reduces measured slopes.
    """
    im = np.asarray(iff.im, dtype=float)
    u, s, vt = np.linalg.svd(im, full_matrices=False)
    s_max = float(s[0]) if s.size else 1.0
    keep = s > (svd_threshold * s_max)
    s_inv = np.zeros_like(s)
    s_inv[keep] = 1.0 / s[keep]
    # R maps slopes → cmd: V Σ⁺ Uᵀ
    r = (vt.T * s_inv) @ u.T
    return r, s


def compute_flat_cmd(
        dm,
        wfs,
        reconstructor: np.ndarray,
        gain: float = 0.5,
) -> tuple[np.ndarray, float]:
    """One-shot flattening delta about bias: ``δ = -gain · R · slopes``."""
    slopes = np.asarray(wfs.acquire_map(output_type='slopes1d'), dtype=float).ravel()
    rms = float(np.sqrt(np.mean(slopes ** 2)))
    delta = -float(gain) * (reconstructor @ slopes)
    return delta, rms


def apply_flatten(
        dm,
        wfs,
        reconstructor: np.ndarray,
        gain: float = 0.5,
        n_iter: int = 1,
        singular_values: np.ndarray | None = None,
) -> FlattenResult:
    """Apply flattening iterations; return before/after RMS and command."""
    s0 = np.asarray(wfs.acquire_map(output_type='slopes1d'), dtype=float).ravel()
    rms0 = float(np.sqrt(np.mean(s0 ** 2)))
    total_delta = np.zeros(dm.n_acts, dtype=float)
    for _ in range(max(1, int(n_iter))):
        delta, _ = compute_flat_cmd(dm, wfs, reconstructor, gain=gain)
        total_delta = total_delta + delta
        dm.set_shape(delta, differential=True)
    s1 = np.asarray(wfs.acquire_map(output_type='slopes1d'), dtype=float).ravel()
    rms1 = float(np.sqrt(np.mean(s1 ** 2)))
    svals = (np.asarray(singular_values, dtype=float)
             if singular_values is not None else np.array([]))
    return FlattenResult(
        cmd_delta=total_delta,
        cmd_abs=dm.get_shape().copy(),
        rms_before=rms0,
        rms_after=rms1,
        singular_values=svals,
        n_modes=int(np.count_nonzero(np.any(reconstructor, axis=0))),
    )


def flatten_from_iff(
        dm,
        wfs,
        amplitude: float = 0.05,
        gain: float = 0.5,
        svd_threshold: float = 1e-3,
        n_iter: int = 1,
) -> tuple[IffResult, np.ndarray, FlattenResult]:
    """Full fake/HW pipeline: IFF → R → apply flatten."""
    iff = acquire_zonal_iff(dm, wfs, amplitude=amplitude)
    r, svals = process_iff(iff, svd_threshold=svd_threshold)
    # Measure before; differential cmds are about bias (replace, don't stack).
    s0 = np.asarray(wfs.acquire_map(output_type='slopes1d'), dtype=float).ravel()
    rms0 = float(np.sqrt(np.mean(s0 ** 2)))
    total = np.zeros(dm.n_acts, dtype=float)
    for _ in range(max(1, int(n_iter))):
        delta, _ = compute_flat_cmd(dm, wfs, r, gain=gain)
        total = total + delta
        # Apply cumulative correction about bias
        dm.set_shape(total, differential=True)
    s1 = np.asarray(wfs.acquire_map(output_type='slopes1d'), dtype=float).ravel()
    rms1 = float(np.sqrt(np.mean(s1 ** 2)))
    result = FlattenResult(
        cmd_delta=total,
        cmd_abs=dm.get_shape().copy(),
        rms_before=rms0,
        rms_after=rms1,
        singular_values=svals,
        n_modes=int(np.sum(svals > svd_threshold * (svals[0] if svals.size else 1.0))),
    )
    return iff, r, result
