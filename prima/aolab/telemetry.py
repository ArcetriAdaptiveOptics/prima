"""Ring-buffer telemetry with running means, for live plots."""
from __future__ import annotations

import threading

import numpy as np


class Telemetry:
    SCALARS = ('t', 'frame', 'slope_rms', 'mode_rms', 'loop_cmd_rms',
               'dist_rms', 'flux', 'sat_frac', 'loop_closed')

    def __init__(self, length: int = 3000, n_modes: int = 0):
        self.length = int(length)
        self.lock = threading.Lock()
        self.reset(n_modes)

    def reset(self, n_modes: int | None = None):
        with self.lock:
            if n_modes is not None:
                self.n_modes = int(n_modes)
            self.n = 0
            self.i = 0
            self.s = {k: np.full(self.length, np.nan) for k in self.SCALARS}
            self.modes = np.full((self.length, max(self.n_modes, 1)), np.nan)
            self.dist_modes = np.full((self.length, max(self.n_modes, 1)),
                                      np.nan)

    def push(self, scal: dict, modes: np.ndarray | None = None,
             dist_modes: np.ndarray | None = None):
        with self.lock:
            i = self.i
            for k in self.SCALARS:
                self.s[k][i] = scal.get(k, np.nan)
            if modes is not None and modes.size == self.modes.shape[1]:
                self.modes[i] = modes
            else:
                self.modes[i] = np.nan
            if dist_modes is not None and dist_modes.size == self.modes.shape[1]:
                self.dist_modes[i] = dist_modes
            else:
                self.dist_modes[i] = np.nan
            self.i = (i + 1) % self.length
            self.n = min(self.n + 1, self.length)

    def _order(self):
        if self.n < self.length:
            return np.arange(self.n)
        return (np.arange(self.length) + self.i) % self.length

    def series(self, key: str, last: int | None = None) -> np.ndarray:
        with self.lock:
            o = self._order()
            if last:
                o = o[-int(last):]
            return self.s[key][o].copy()

    def running_mean(self, key: str, window: int) -> np.ndarray:
        x = self.series(key)
        if x.size == 0:
            return x
        w = max(1, int(window))
        x = np.nan_to_num(x)
        c = np.cumsum(np.insert(x, 0, 0.0))
        out = np.empty_like(x)
        for k in range(x.size):                  # O(n), small arrays
            a = max(0, k + 1 - w)
            out[k] = (c[k + 1] - c[a]) / (k + 1 - a)
        return out

    def modal_rms(self, window: int, which: str = 'res') -> np.ndarray:
        """sqrt(mean(m^2)) per mode over the last ``window`` frames."""
        with self.lock:
            o = self._order()[-max(1, int(window)):]
            arr = (self.modes if which == 'res' else self.dist_modes)[o]
        if arr.size == 0:
            return np.zeros(self.modes.shape[1])
        with np.errstate(invalid='ignore'):
            return np.sqrt(np.nanmean(arr ** 2, axis=0))

    def last_modes(self) -> np.ndarray | None:
        with self.lock:
            if self.n == 0:
                return None
            return self.modes[(self.i - 1) % self.length].copy()

    def dump(self) -> dict:
        with self.lock:
            o = self._order()
            d = {k: v[o].copy() for k, v in self.s.items()}
            d['modes'] = self.modes[o].copy()
            d['dist_modes'] = self.dist_modes[o].copy()
        return d
