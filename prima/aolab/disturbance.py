"""Disturbances generated *with the DM itself* (no external turbulence).

* ``StaticAberration``: sum of Zernike modes (focus, astig, coma ...).
* ``FrozenFlowTurbulence``: a von Karman phase screen much larger than the
  pupil, translated by the "wind" every frame and sampled at the actuator
  positions -> realistic temporal and spatial statistics of turbulence
  as seen through a 140 actuator corrector.

All amplitudes are in DM command units (fraction of full scale);
``nm_per_unit`` converts approximately to nm of wavefront.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

from prima.aolab import dm_geometry as G


def von_karman_screen(n: int, dx_mm: float, r0_mm: float, L0_mm: float,
                      rng: np.random.Generator) -> np.ndarray:
    """FFT phase screen (arbitrary units, rescaled by the caller)."""
    fx = np.fft.fftfreq(n, d=dx_mm)
    FX, FY = np.meshgrid(fx, fx)
    f2 = FX ** 2 + FY ** 2 + (1.0 / L0_mm) ** 2
    psd = 0.023 * r0_mm ** (-5 / 3) * f2 ** (-11 / 6)
    psd[0, 0] = 0.0
    c = (rng.normal(size=(n, n)) + 1j * rng.normal(size=(n, n)))
    scr = np.fft.ifft2(c * np.sqrt(psd)).real
    return scr


class StaticAberration:
    def __init__(self, active: np.ndarray, pupil_diam_mm: float = 4.5):
        self.active = active
        x, y = G.actuator_xy_mm()
        R = pupil_diam_mm / 2
        self._rho = np.hypot(x, y) / R
        self._th = np.arctan2(y, x)
        self.coeffs: dict[int, float] = {}

    def set(self, j: int, amp: float) -> None:
        self.coeffs[int(j)] = float(amp)

    def command(self) -> np.ndarray:
        cmd = np.zeros(G.N_ACT)
        for j, a in self.coeffs.items():
            if a == 0:
                continue
            z = G.zernike(j, self._rho, self._th)
            z = np.where(self.active, z, 0.0)
            z[self.active] -= z[self.active].mean()
            rms = z[self.active].std() or 1.0
            cmd += a * z / rms
        return cmd


class FrozenFlowTurbulence:
    """Screen of ``n`` x ``n`` samples, ``dx`` = pitch/2 mm per sample."""

    def __init__(self, active: np.ndarray, rms: float = 0.01,
                 wind_px_per_frame: float = 0.3, direction_deg: float = 30,
                 r0_mm: float = 1.0, L0_mm: float = 20.0, n: int = 512,
                 seed: int = 0):
        self.active = active
        self.rms = float(rms)
        self.wind = float(wind_px_per_frame)
        self.direction = np.deg2rad(direction_deg)
        self.dx = G.PITCH_MM / 2
        self.rng = np.random.default_rng(seed)
        self.n = int(n)
        self.screen = von_karman_screen(self.n, self.dx, r0_mm, L0_mm,
                                        self.rng)
        x, y = G.actuator_xy_mm()
        self._ax = x / self.dx
        self._ay = y / self.dx
        self.pos = np.array([self.n / 2.0, self.n / 2.0])
        self._norm = self._estimate_norm()

    def _sample(self, pos) -> np.ndarray:
        rows = (pos[0] + self._ay) % self.n
        cols = (pos[1] + self._ax) % self.n
        v = ndimage.map_coordinates(self.screen, [rows, cols], order=1,
                                    mode='grid-wrap')
        v = np.where(self.active, v, 0.0)
        v[self.active] -= v[self.active].mean()
        return v

    def _estimate_norm(self) -> float:
        vals = [self._sample(self.rng.uniform(0, self.n, 2))[self.active].std()
                for _ in range(64)]
        return float(np.mean(vals)) or 1.0

    def step(self) -> np.ndarray:
        self.pos += self.wind * np.array([np.sin(self.direction),
                                          np.cos(self.direction)])
        return self.command()

    def command(self) -> np.ndarray:
        return self.rms * self._sample(self.pos) / self._norm
