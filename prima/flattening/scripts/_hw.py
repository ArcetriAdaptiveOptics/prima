"""Open live HW stack for flattening scripts (DAO DM + Aravis + E-518)."""
from __future__ import annotations

import time
from dataclasses import dataclass

from prima.drop1_defaults import (
    DEFAULT_E518_HOST, DEFAULT_E518_PORT, DEFAULT_EXPOSURE_MS,
    DEFAULT_MANTA_IP, DEFAULT_MOD_FREQ_HZ, DEFAULT_MOD_RADIUS_MRAD)
from prima.flattening.devices.aravis_camera import AravisCamera
from prima.flattening.devices.bmc_dm import BmcMultiDm
from prima.flattening.devices.live_pyramid import LivePyramid
from prima.hardware.pi_e518_modulator import PiE518Modulator


@dataclass
class LiveStack:
    dm: BmcMultiDm
    camera: AravisCamera
    modulator: PiE518Modulator
    wfs: LivePyramid

    def close(self, park_dm: bool = True, leave_modulating: bool = True):
        if park_dm:
            try:
                self.dm.park()
            except Exception as exc:
                print('DM park warning:', exc)
        try:
            self.dm.close()
        except Exception:
            pass
        if not leave_modulating:
            try:
                self.modulator.close()
            except Exception:
                pass
        else:
            # Release GCS TCP without parking wavegen to 0 — keep 4 mrad if up.
            try:
                if getattr(self.modulator, '_gcs', None) is not None:
                    self.modulator._gcs.close()
                    self.modulator._setup_done = False
            except Exception:
                pass
        try:
            self.camera.close()
        except Exception:
            pass


def open_live_stack(
        prefer: str = 'dao',
        park_dm: bool = True,
        radius_mrad: float = DEFAULT_MOD_RADIUS_MRAD,
        freq_hz: float = DEFAULT_MOD_FREQ_HZ,
        exposure_ms: float = DEFAULT_EXPOSURE_MS,
        geometry_dir=None,
) -> LiveStack:
    """Connect DM (DAO/USB), Aravis Mono12, E-518 @ work defaults, LivePyramid."""
    dm = BmcMultiDm(prefer=prefer, dry_run=False)
    if park_dm:
        dm.park()
    mod = PiE518Modulator(
        host=DEFAULT_E518_HOST, port=DEFAULT_E518_PORT, connect=True)
    mod.setFrequencyInHz(float(freq_hz))
    mod.setRadiusInMilliRad(float(radius_mrad))
    time.sleep(0.8)
    cam = AravisCamera(ip_address=DEFAULT_MANTA_IP, exposure_ms=exposure_ms)
    time.sleep(0.3)
    wfs = LivePyramid(cam, modulator=mod, nframes=2, detect_threshold=400.0)
    if geometry_dir is not None and wfs.load_geometry(geometry_dir):
        mode = wfs.mode
    else:
        mode = wfs.ensure_pupils(detect=True)
    print('live stack: dm=%s wfs=%s R=%.1f f=%.1f exp=%.1fms' % (
        dm, mode, radius_mrad, freq_hz, exposure_ms))
    return LiveStack(dm=dm, camera=cam, modulator=mod, wfs=wfs)
