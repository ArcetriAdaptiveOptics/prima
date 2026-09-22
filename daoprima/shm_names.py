"""
DaoPrima shared-memory path names.

Adapted from daoEkarus ``src/daoEkarusShmNames.py`` (Durham / EKARUS).
Prima differences vs Ekarus:
  - Science DM is BMC Multi-DM **140** actuators (not Alpao 468).
  - WFS camera is Manta G-419 or Alvium G1 via pysilico (not OCAM²k).
  - Modulator / tip-tilt is PI S-334 (Drop 2 modulator; Drop 3 TT DM role).

Path strings intentionally keep the daoEkarus *shape* (``/tmp/<name>.im.shm``)
so GUIs and scripts ported from daoEkarus need minimal edits. When daoBase
is available, these paths are real ``dao.shm`` images; the sim backend uses
the same names as keys in ``daoprima.shm``.
"""

# --- Science DM (BMC Multi-DM 5.5 µm, 140 actuators) ---
SHM_DM1_N_ACTUATORS = 140
SHM_DM1_MASK = "/tmp/prima_dm1Map.im.shm"
SHM_DM1_M2C = "/tmp/prima_dm1m2c.im.shm"
SHM_DM1_C2M = "/tmp/prima_dm1c2m.im.shm"
SHM_DM1_RESIDUAL_ZONAL_COMMANDS = "/tmp/prima_dm1resWf.im.shm"
SHM_DM1_CMD_OFFSET = "/tmp/prima_dm1CmdOffset.im.shm"
SHM_DM1_CHANNEL_0 = "/tmp/prima_dm1Cmd00.im.shm"  # flat
SHM_DM1_CHANNEL_1 = "/tmp/prima_dm1Cmd01.im.shm"  # integrator
SHM_DM1_CHANNEL_2 = "/tmp/prima_dm1Cmd02.im.shm"
SHM_DM1_CHANNEL_3 = "/tmp/prima_dm1Cmd03.im.shm"
SHM_DM1_CMD = "/tmp/prima_dm1Cmd.im.shm"  # combined command → daodm_bmc_ctrl → USB

# --- WFS camera (Manta / Alvium via pysilico → SHM bridge) ---
SHM_WFS_FRAME = "/tmp/prima_wfs.im.shm"
SHM_WFS_ACQ = "/tmp/prima_wfsAcq.im.shm"
SHM_WFS_BACKGROUND = "/tmp/prima_wfsBg.im.shm"
SHM_WFS_FLAT_FIELD = "/tmp/prima_wfsFf.im.shm"
SHM_WFS_REFERENCE = "/tmp/prima_wfsRef.im.shm"
SHM_WFS_FPS = "/tmp/prima_wfsFps.im.shm"
SHM_WFS_EXPOSURE_MS = "/tmp/prima_wfsExpMs.im.shm"

# --- Pyramid / PWFS products (names mirror daoEkarus pyramid keys) ---
SHM_PYRAMID_SIGNAL = "/tmp/prima_wfsCentroids.im.shm"
SHM_PYRAMID_VALID_PIXELS = "/tmp/prima_valid_mask.im.shm"
SHM_PYRAMID_PUPIL_FLUX = "/tmp/prima_pupil_flux.im.shm"
SHM_PYRAMID_PUPIL_CENTERS = "/tmp/prima_pupil_centers.im.shm"

# --- Loop control (same semantics as daoEkarus dm1_lp*) ---
SHM_DM1_LOOP_CL_SWITCH = "/tmp/prima_dm1_lpCmd.im.shm"
SHM_DM1_LOOP_LEAK = "/tmp/prima_dm1_lpLeak.im.shm"
SHM_DM1_LOOP_GAIN = "/tmp/prima_dm1_lpGain.im.shm"

# --- Tip-tilt / modulator (S-334: Drop 2 modulator; Drop 3 TT corrector) ---
SHM_MODULATOR = "/tmp/prima_modulator.im.shm"
SHM_FASTTT_CMD = "/tmp/prima_fasttt.im.shm"
SHM_FASTTT_LOOP_CL_SWITCH = "/tmp/prima_fast_tt_lpCmd.im.shm"
SHM_FASTTT_LOOP_GAIN = "/tmp/prima_fast_tt_lpGain.im.shm"
SHM_FASTTT_LOOP_LEAK = "/tmp/prima_fast_tt_lpLeak.im.shm"

# --- Modes / reconstructor telemetry ---
SHM_WFS1_RECONSTRUCTED_MODES = "/tmp/prima_wfs1Modes.im.shm"
SHM_WFS1_RECONSTRUCTED_MODES_GAIN = "/tmp/prima_wfs1ModesGain.im.shm"
SHM_WFS1_RECONSTRUCTED_MODES_WITH_GAIN = "/tmp/prima_wfs1ModesWithGain.im.shm"
SHM_PYRAMID_2_DM1_REC = "/tmp/prima_pwfs_CM.im.shm"

# --- frame_id (DaoPrima divergence from daoEkarus — intentional) ---
# Camera assigns; each stage stamps the ID it processed for E2E smoke.
SHM_FRAME_ID = "/tmp/prima_frame_id.im.shm"
SHM_FRAME_ID_RECON = "/tmp/prima_frame_id_recon.im.shm"
SHM_FRAME_ID_RTC = "/tmp/prima_frame_id_rtc.im.shm"
SHM_FRAME_ID_DM = "/tmp/prima_frame_id_dm.im.shm"

# daoEkarus aliases kept for drop-in script ports (map to Prima paths)
SHM_OCAM_FRAME = SHM_WFS_FRAME
SHM_OCAM_FPS = SHM_WFS_FPS
SHM_DM1_468_MASK = SHM_DM1_MASK  # name kept; size is 140 for Prima
