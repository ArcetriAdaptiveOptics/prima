"""opticalib ``BaseCamera`` over Prima Aravis Mono12."""
from __future__ import annotations

import time

import numpy as np

from opticalib.devices._API.base_devices import BaseCamera

from prima.drop1_defaults import DEFAULT_MANTA_IP, DEFAULT_EXPOSURE_MS
from prima.gui.aravis_camera import AravisLiveCamera


class AravisCamera(BaseCamera):
    """Thin BaseCamera wrapper around ``AravisLiveCamera`` (Mono12 ADU)."""

    def __init__(
            self,
            ip_address: str = DEFAULT_MANTA_IP,
            exposure_ms: float | None = None,
            camera: AravisLiveCamera | None = None,
    ):
        self._ip = str(ip_address)
        self._owns = camera is None
        self._cam = camera or AravisLiveCamera(ip_address=self._ip)
        self._exptime_us = None
        exp = float(DEFAULT_EXPOSURE_MS if exposure_ms is None else exposure_ms)
        self.set_exptime(exp * 1000.0)

    def reconnect(self, *args) -> None:
        try:
            if self._cam is not None:
                self._cam.close()
        except Exception:
            pass
        self._cam = AravisLiveCamera(ip_address=self._ip)
        if self._exptime_us is not None:
            self.set_exptime(self._exptime_us)

    def set_exptime(self, exptime_us: float) -> None:
        """Set exposure in **microseconds** (opticalib camera convention)."""
        self._exptime_us = float(exptime_us)
        self._cam.setExposureTime(self._exptime_us / 1000.0)

    def get_exptime(self) -> float:
        """Exposure in microseconds."""
        if self._exptime_us is not None:
            return float(self._exptime_us)
        try:
            return float(self._cam.exposureTime()) * 1000.0
        except Exception:
            return float('nan')

    def acquire_frames(
            self,
            nframes: int | None = None,
            multiframe_out_mode: str = 'mean',
    ) -> np.ndarray:
        n = 1 if nframes is None else max(1, int(nframes))
        frames = []
        for _ in range(n):
            frames.append(np.asarray(self._cam.getFrame(), dtype=np.float64))
            time.sleep(0.01)
        stack = np.stack(frames, axis=0)
        if n == 1 or multiframe_out_mode == 'mean':
            return np.mean(stack, axis=0)
        return stack

    def close(self) -> None:
        if self._owns and self._cam is not None:
            try:
                self._cam.close()
            except Exception:
                pass
            self._cam = None
