"""IFF acquire → process → flatten (zonal or Hadamard modal base).

Uses in-memory arrays so fake tests do not need opticalib TN folders.
Hadamard modal base matches ``opticalib.dmutils.iff_preparation``
(``modal_base: hadamard``): truncated Walsh–Hadamard without piston row/col.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


@dataclass
class IffResult:
    amplitudes: np.ndarray          # (n_modes,) poke amp used
    plus: np.ndarray                # (n_slopes, n_modes)
    minus: np.ndarray               # (n_slopes, n_modes)
    im: np.ndarray                  # (n_slopes, n_modes) modal IM
    modal_base: np.ndarray | None = None   # (n_acts, n_modes)
    modal_base_id: str = 'zonal'
    # Actuator-space IM when modal: im @ pinv(H)  (n_slopes, n_acts)
    im_actuator: np.ndarray | None = None


@dataclass
class FlattenResult:
    cmd_delta: np.ndarray           # differential about bias
    cmd_abs: np.ndarray             # absolute drive
    rms_before: float
    rms_after: float
    singular_values: np.ndarray
    n_modes: int


def make_hadamard_base(n_acts: int) -> np.ndarray:
    """opticalib-compatible Hadamard modal base (n_acts, n_acts), no piston."""
    from scipy.linalg import hadamard
    numb = int(math.ceil(math.log(n_acts, 2)))
    hadm = hadamard(2 ** numb)
    return np.asarray(hadm[1:n_acts + 1, 1:n_acts + 1], dtype=float)


def make_zonal_base(n_acts: int) -> np.ndarray:
    return np.eye(int(n_acts), dtype=float)


def make_modal_base(n_acts: int, modal_base: str = 'hadamard') -> np.ndarray:
    mid = (modal_base or 'hadamard').lower()
    if mid in ('hadamard', 'had'):
        return make_hadamard_base(n_acts)
    if mid in ('zonal', 'mirror', 'eye'):
        return make_zonal_base(n_acts)
    raise ValueError('unknown modal_base %r (use hadamard|zonal)' % modal_base)


def acquire_modal_iff(
        dm,
        wfs,
        amplitude: float = 0.04,
        modal_base: str | np.ndarray = 'hadamard',
        mode_list: np.ndarray | None = None,
        settle_s: float = 0.0,
        progress_every: int = 10,
) -> IffResult:
    """Push–pull modal IFF: poke columns of the modal base about bias."""
    import time
    n = int(dm.n_acts)
    if isinstance(modal_base, str):
        mid = modal_base.lower()
        H = make_modal_base(n, mid)
    else:
        H = np.asarray(modal_base, dtype=float)
        mid = 'custom'
        if H.ndim != 2 or H.shape[0] != n:
            raise ValueError('modal_base shape %s incompatible with n_acts=%d'
                             % (H.shape, n))
    n_modes = H.shape[1]
    modes = (np.arange(n_modes) if mode_list is None
             else np.asarray(mode_list, dtype=int).ravel())
    amp = float(amplitude)
    s0 = np.asarray(wfs.acquire_map(output_type='slopes1d'), dtype=float).ravel()
    n_s = s0.size
    plus = np.zeros((n_s, n_modes), dtype=float)
    minus = np.zeros((n_s, n_modes), dtype=float)
    amps = np.zeros(n_modes, dtype=float)
    start = dm.get_shape().copy()
    for i, m in enumerate(modes):
        amps[m] = amp
        poke = amp * H[:, m]
        dm.set_shape(poke, differential=True)
        if settle_s:
            time.sleep(settle_s)
        plus[:, m] = np.asarray(
            wfs.acquire_map(output_type='slopes1d'), dtype=float).ravel()
        dm.set_shape(-poke, differential=True)
        if settle_s:
            time.sleep(settle_s)
        minus[:, m] = np.asarray(
            wfs.acquire_map(output_type='slopes1d'), dtype=float).ravel()
        dm.set_shape(start, differential=False)
        if progress_every and (i + 1) % int(progress_every) == 0:
            print('  IFF mode %d/%d' % (i + 1, modes.size), flush=True)
    im = (plus - minus) / (2.0 * np.maximum(amps, 1e-12))
    unused = np.setdiff1d(np.arange(n_modes), modes)
    im[:, unused] = 0.0
    # Actuator-space IM: slopes ≈ im_act @ Δcmd, Δcmd = H @ modal
    # → im_act = im_modal @ pinv(H)
    im_act = im @ np.linalg.pinv(H)
    return IffResult(
        amplitudes=amps, plus=plus, minus=minus, im=im,
        modal_base=H, modal_base_id=mid, im_actuator=im_act)


def acquire_zonal_iff(
        dm,
        wfs,
        amplitude: float = 0.05,
        act_list: np.ndarray | None = None,
        settle_s: float = 0.0,
) -> IffResult:
    """Push–pull zonal IFF (identity modal base)."""
    return acquire_modal_iff(
        dm, wfs, amplitude=amplitude, modal_base='zonal',
        mode_list=act_list, settle_s=settle_s)


def process_iff(
        iff: IffResult,
        svd_threshold: float = 1e-3,
        actuator_space: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (reconstructor R, singular values).

    By default ``R`` maps slopes → **actuator** differential command
    (``δ = -R @ slopes``), converting Hadamard modal IM through ``H``.
    """
    im = np.asarray(iff.im, dtype=float)
    u, s, vt = np.linalg.svd(im, full_matrices=False)
    s_max = float(s[0]) if s.size else 1.0
    keep = s > (svd_threshold * s_max)
    s_inv = np.zeros_like(s)
    s_inv[keep] = 1.0 / s[keep]
    r_modal = (vt.T * s_inv) @ u.T  # (n_modes, n_slopes)
    if (actuator_space and iff.modal_base is not None
            and iff.modal_base_id not in ('zonal', 'mirror', 'eye')):
        r = iff.modal_base @ r_modal  # (n_acts, n_slopes)
    else:
        r = r_modal
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
        # Cumulative correction about bias; allow full step for flatten apply
        try:
            dm.set_shape(total_delta, differential=True, max_step=1.0)
        except TypeError:
            dm.set_shape(total_delta, differential=True)
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
        modal_base: str = 'zonal',
) -> tuple[IffResult, np.ndarray, FlattenResult]:
    """Full fake/HW pipeline: IFF → R → apply flatten."""
    iff = acquire_modal_iff(
        dm, wfs, amplitude=amplitude, modal_base=modal_base)
    r, svals = process_iff(iff, svd_threshold=svd_threshold)
    s0 = np.asarray(wfs.acquire_map(output_type='slopes1d'), dtype=float).ravel()
    rms0 = float(np.sqrt(np.mean(s0 ** 2)))
    total = np.zeros(dm.n_acts, dtype=float)
    for _ in range(max(1, int(n_iter))):
        delta, _ = compute_flat_cmd(dm, wfs, r, gain=gain)
        total = total + delta
        try:
            dm.set_shape(total, differential=True, max_step=1.0)
        except TypeError:
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
