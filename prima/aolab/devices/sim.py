"""Numerical twin of the PRIMA bench: modulated pyramid WFS + Multi-DM 140.

Physics (simple but faithful enough to teach and to test the software):

* DM surface: Gaussian influence functions on the 12x12 (-corners) grid,
  pitch 400 um, inter-actuator coupling ~15 %.  Electrostatic MEMS:
  deflection ~ stroke * u**2 (u = normalised command in [0, 1]); the
  shipped flat ``u_flat`` gives a flat mirror by definition.
* Pupil of 4.5 mm on the DM -> outer actuators only partly seen.
* Static bench aberration (low-order Zernike, ~80 nm rms) so that the
  "flat" is not perfect and the loop has something to correct.
* PWFS: Fraunhofer propagation pupil -> focal plane, 4-faces pyramid
  phase mask, back to pupil plane; tip-tilt modulation sampled with
  ``n_mod`` points on a circle of radius ``r_mod`` (lambda/D).
* Camera: 4 pupils on a square frame, photon + read noise, Mono12.
"""
from __future__ import annotations

import math
import threading
import time

import numpy as np

from prima.aolab import dm_geometry as G
from prima.aolab.devices.base import Camera, DeformableMirror, Modulator


class BenchModel:
    def __init__(self, npup: int = 40, nfft: int = 128,
                 wavelength_nm: float = 633.0,
                 pupil_diam_mm: float = 4.5,
                 stroke_um: float = 5.5,
                 coupling: float = 0.15,
                 static_rms_nm: float = 80.0,
                 lod_per_mrad: float = 0.75,
                 flat: np.ndarray | None = None,
                 seed: int = 1):
        self.npup = int(npup)
        self.nfft = int(nfft)
        self.lam = float(wavelength_nm)
        self.D = float(pupil_diam_mm)
        self.stroke_nm = float(stroke_um) * 1e3
        self.lod_per_mrad = float(lod_per_mrad)
        self.lock = threading.RLock()
        rng = np.random.default_rng(seed)

        n = self.npup
        c = (np.arange(n) - (n - 1) / 2.0) * (self.D / n)   # mm
        self.X, self.Y = np.meshgrid(c, c)
        self.pupil = (np.hypot(self.X, self.Y) <= self.D / 2).astype(float)
        self.pmask = self.pupil > 0

        # influence functions (n_act, npup, npup)
        ax, ay = G.actuator_xy_mm()
        w = G.PITCH_MM / math.sqrt(-math.log(coupling))
        d2 = (self.X[None] - ax[:, None, None]) ** 2 + \
             (self.Y[None] - ay[:, None, None]) ** 2
        self.IF = np.exp(-d2 / w ** 2)                      # peak 1
        self.IFm = self.IF[:, self.pmask]                   # (140, npix)

        if flat is None:
            flat = np.full(G.N_ACT, 0.8)
        self.flat = np.clip(np.asarray(flat, float), 0, 1)
        self.u = self.flat.copy()

        # static aberration: random Zernike 4..11 with 1/j weighting
        rho = np.hypot(self.X, self.Y) / (self.D / 2)
        th = np.arctan2(self.Y, self.X)
        ab = np.zeros_like(rho)
        for j in range(4, 12):
            ab += rng.normal() / j * G.zernike(j, rho, th)
        ab -= ab[self.pmask].mean()
        ab *= static_rms_nm / max(ab[self.pmask].std(), 1e-9)
        self.static_nm = ab * self.pupil

        # pyramid mask: 4 faces, pupils centred at +-nfft/4
        N = self.nfft
        f = np.fft.fftfreq(N) * N           # pixel units of focal plane
        FX, FY = np.meshgrid(f, f)
        s = N / 4.0
        self.pyr = np.exp(1j * 2 * np.pi * s * (np.abs(FX) + np.abs(FY)) / N)

        # modulation
        self.r_mod_lod = 3.0
        self.center_lod = np.zeros(2)
        self.n_mod = 16
        self.flux = 6.0e6          # photons / frame at 10 ms (whole pupil)
        self.read_noise = 3.0
        self.exposure_ms = 10.0
        self.full_well = 4095.0

    # ---------------------------------------------------------------- DM
    def dm_surface_nm(self, u: np.ndarray | None = None) -> np.ndarray:
        u = self.u if u is None else u
        a = self.stroke_nm * (np.asarray(u) ** 2 - self.flat ** 2)
        surf = np.zeros_like(self.pupil)
        surf[self.pmask] = a @ self.IFm
        return surf

    def wavefront_nm(self) -> np.ndarray:
        """Reflected wavefront (2 x surface) + static bench aberration."""
        with self.lock:
            wf = 2.0 * self.dm_surface_nm() + self.static_nm
        wf = wf - wf[self.pmask].mean()
        return wf * self.pupil

    # ---------------------------------------------------------------- WFS
    def pwfs_image(self) -> np.ndarray:
        N, n = self.nfft, self.npup
        wf = self.wavefront_nm()
        phase = 2 * np.pi * wf / self.lam
        E0 = np.zeros((N, N), complex)
        o = (N - n) // 2
        E0[o:o + n, o:o + n] = self.pupil * np.exp(1j * phase)
        # tilt grid in lambda/D (pupil spans n pixels -> 1 lambda/D = N/n px)
        yy, xx = np.mgrid[0:N, 0:N]
        xx = (xx - o - (n - 1) / 2) / n
        yy = (yy - o - (n - 1) / 2) / n
        with self.lock:
            r = float(self.r_mod_lod)
            cx, cy = self.center_lod
        nm = max(1, self.n_mod if r > 0 else 1)
        img = np.zeros((N, N))
        for k in range(nm):
            a = 2 * np.pi * k / nm
            tx = cx + r * math.cos(a)
            ty = cy + r * math.sin(a)
            E = E0 * np.exp(1j * 2 * np.pi * (tx * xx + ty * yy))
            F = np.fft.fft2(np.fft.fftshift(E))
            P = np.fft.ifft2(F * self.pyr)
            img += np.abs(np.fft.ifftshift(P)) ** 2
        img /= img.sum()
        return img

    def camera_frame(self, rng) -> np.ndarray:
        img = self.pwfs_image()
        photons = img * self.flux * (self.exposure_ms / 10.0)
        frame = rng.poisson(np.clip(photons, 0, None)).astype(float)
        frame += rng.normal(0, self.read_noise, frame.shape) + 20.0
        return np.clip(frame, 0, self.full_well).astype(np.float32)


# ======================================================================

class SimCamera(Camera):
    def __init__(self, model: BenchModel, fps: float = 30.0, seed: int = 2):
        self.m = model
        self.name = 'SimCamera (PWFS twin)'
        self._fps = float(fps)
        self._rng = np.random.default_rng(seed)
        self._count = 0
        self._last_t = 0.0
        self._lock = threading.Lock()

    def start(self):
        pass

    def get_frame(self, wait_new=True, timeout_s=2.0):
        with self._lock:
            period = 1.0 / self._fps
            dt = time.time() - self._last_t
            if wait_new and dt < period:
                time.sleep(period - dt)
            self._last_t = time.time()
            self._count += 1
            return self._count, self.m.camera_frame(self._rng)

    def set_exposure_ms(self, ms):
        self.m.exposure_ms = float(ms)

    def get_exposure_ms(self):
        return float(self.m.exposure_ms)

    def get_fps(self):
        return self._fps

    def set_fps(self, fps):
        self._fps = float(fps)

    def get_roi(self):
        return (0, 0, self.m.nfft, self.m.nfft)

    def full_well(self):
        return self.m.full_well


class SimDM(DeformableMirror):
    def __init__(self, model: BenchModel):
        self.m = model
        self.name = 'SimDM (Multi-DM 140 twin)'

    def send(self, cmd):
        cmd = np.clip(np.asarray(cmd, float).ravel(), 0.0, 1.0)
        if cmd.size != G.N_ACT:
            raise ValueError('need 140 actuators')
        with self.m.lock:
            self.m.u = cmd

    def last(self):
        with self.m.lock:
            return self.m.u.copy()


class SimModulator(Modulator):
    def __init__(self, model: BenchModel):
        self.m = model
        self.name = 'SimModulator'
        self._radius = 4.0
        self._freq = 20.0
        self._center = (0.0, 0.0)
        self.set_modulation(self._radius, self._freq)

    def set_modulation(self, radius_mrad, freq_hz):
        self._radius, self._freq = float(radius_mrad), float(freq_hz)
        with self.m.lock:
            self.m.r_mod_lod = self._radius * self.m.lod_per_mrad
            self.m.n_mod = max(8, int(4 * math.ceil(self.m.r_mod_lod * 2)))

    def set_center(self, cx_mrad, cy_mrad):
        self._center = (float(cx_mrad), float(cy_mrad))
        with self.m.lock:
            self.m.center_lod = np.array(self._center) * self.m.lod_per_mrad

    def state(self):
        return {'radius_mrad': self._radius, 'freq_hz': self._freq,
                'center': self._center}


def make_sim_bench(flat: np.ndarray | None = None, fps: float = 30.0, **kw):
    m = BenchModel(flat=flat, **kw)
    return SimCamera(m, fps=fps), SimDM(m), SimModulator(m), m
