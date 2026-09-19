## Simulated mode
SHM_OOPAO_MODE = "/tmp/oopao_mode.im.shm"

## First stage dm
SHM_WFS1_RECONSTRUCTED_MODES = "/tmp/wfs1Modes.im.shm" # reconstructed modes based on the current reconstructor
SHM_WFS1_RECONSTRUCTED_MODES_GAIN = "/tmp/wfs1ModesGain.im.shm" # gain applied to the reconstructed modes based on the current reconstructor
SHM_WFS1_RECONSTRUCTED_MODES_WITH_GAIN = "/tmp/wfs1ModesWithGain.im.shm" # reconstructed modes based on the current reconstructor with the gain applied
SHM_DM1_468_MASK = "/tmp/dm1Map.im.shm" # binary mask of the valid (controlled actuators)
SHM_DM1_M2C = "/tmp/dm1m2c.im.shm" # Modes to Command Matrix for DM1
SHM_DM1_C2M = "/tmp/dm1c2m.im.shm" # Command to Modes Matrix for DM1
SHM_DM1_RESIDUAL_ZONAL_COMMANDS = "/tmp/dm1resWf.im.shm" # output of the product of the modal reconstructor with the M2C providing zonal command to be sent to the DM1
SHM_DM1_CMD_OFFSET = "/tmp/dm1CmdOffset.im.shm" # Static offset applied to DM1 commands (e.g., focus offset)
SHM_DM1_CHANNEL_0 = "/tmp/dm1Cmd00.im.shm" # DM flat
SHM_DM1_CHANNEL_1 = "/tmp/dm1Cmd01.im.shm" # Output of the Leaky integrator
SHM_DM1_CHANNEL_2 = "/tmp/dm1Cmd02.im.shm" # Additional control channel for DM1
SHM_DM1_CHANNEL_3 = "/tmp/dm1Cmd03.im.shm" # Additional control channel for DM1
SHM_DM1_CMD = "/tmp/dm1Cmd.im.shm"  # Command actually sent to DM1 after that all channels are combined

## OCAM Camera
SHM_OCAM_RAW_FRAME = "/tmp/ocam2raw.im.shm" # raw OCAM frames before descrambling
SHM_OCAM_RAW_ACQ = "/tmp/ocam2rawAcq.im.shm"  # OCAM to Acquire: set to 1 to stream and 0 to stop streaming
SHM_OCAM_FRAME = "/tmp/ocam2.im.shm" # descrambled ocam frames
SHM_OCAM_BACKGROUND = "/tmp/ocam2Bg.im.shm" # OCAM background map (descrambled)
SHM_OCAM_FLAT_FIELD = "/tmp/ocam2Ff.im.shm" # OCAM flat field map (descrambled)
SHM_OCAM_REFERENCE = "/tmp/ocam2Ref.im.shm" # OCAM Reference Image to be used in the pupil extraction
SHM_OCAM_REDUCED_FRAME = "/tmp/ocam2Cal.im.shm" # OCAM Descrambled Image + Bg substracted + flat fielded
SHM_OCAM_CMD = "/tmp/ocam2rawSCmd.im.shm" # OCAM command to be sent via virtual Serial command
SHM_OCAM_RSP = "/tmp/ocam2rawSRsp.im.shm" # OCAM response to the command sent via virtual Serial command
SHM_OCAM_DESCRAMBLE_TIME = "/tmp/ocam2DescrTime.im.shm" # Time taken for last frame descrambling operation
SHM_OCAM_DESCRAMBLE_TIME_AVG = "/tmp/ocam2DescrTimeAvg.im.shm" # Average descrambling time
SHM_OCAM_DESCRAMBLE_TIME_RMS = "/tmp/ocam2DescrTimeRms.im.shm" # RMS of descrambling time
SHM_OCAM_TEMPERATURE = "/tmp/ocam2temp.im.shm" # OCAM temperature
SHM_OCAM_FPS = "/tmp/ocam2fps.im.shm"  # OCAM FPS 
SHM_OCAM_GAIN = "/tmp/ocam2gain.im.shm" # OCAM gain, should not be set higher than 299
SHM_OCAM_FRAME_ID = "/tmp/frameId.im.shm" # ID of the OCAM frame
SHM_OCAM_DARK_MAP_PERCENT = "/tmp/ocam_dark_mapPercent.im.shm" # used to show the progress bar when taking a dark
SHM_OCAM_REFERENCE_FLUX = "/tmp/ocam_reference_flux.im.shm" 
SHM_OCAM_REFERENCE_BEFORE_NCPA_OFFSET = "/tmp/ocam_reference_before_ncpa_offset.im.shm" # Used to return to previous reference after removing NCPA offset

## Pyramid
SHM_PYRAMID_SIGNAL = "/tmp/ocam2Centroids.im.shm" # DBARR - OCAM Centroids of the pyramid after extraction and normalisation
# SHM_PYRAMID_SIGNAL_OFFSET = "/tmp/ocam_signal_offset.im.shm" # MME - OCAM slope offsets for NCPA
SHM_PYRAMID_VALID_PIXELS = "/tmp/papyrus_valid_mask.im.shm"  # Mask of valid pixels for pyramid wavefront sensor
SHM_PYRAMID_PUPIL_FLUX = "/tmp/pupil_flux.im.shm" # Total flux in the pupil from pyramid sensor
SHM_PYRAMID_PUPIL_CENTERS = "/tmp/pupil_centers.im.shm" # Computed centers of each pyramid subpupil
SHM_PYRAMID_VALID_PIXELS_STD = "/tmp/papyrus_valid_mask_std.im.shm"  # std of the valid pixels computation saved to avoid re-acquiring it all the time


## CBLUE Camera
SHM_CBLUE_FRAME = "/tmp/cblue.im.shm" # CBLUE science camera frame
SHM_CBLUE_TEMP = "/tmp/cblueTemp.im.shm" # CBLUE detector temperature
SHM_CBLUE_ACQ = "/tmp/cblueAcq.im.shm" # CBLUE acquisition trigger (1 to stream, 0 to stop)
SHM_CBLUE_DIT = "/tmp/cblueDit.im.shm" # CBLUE Detector Integration Time
SHM_CBLUE_FPS = "/tmp/cblueFps.im.shm" # CBLUE Frames Per Second
SHM_CBLUE_GAIN = "/tmp/cblueGain.im.shm" # CBLUE detector gain
SHM_CBLUE_BACKGROUND = "/tmp/cblueBg.im.shm" # CBLUE background calibration map
SHM_CBLUE_FLAT_FIELD = "/tmp/cblueFf.im.shm" # CBLUE flat field calibration map
SHM_CBLUE_REFERENCE = "/tmp/cblueCal.im.shm" # CBLUE reference frame for calibration
SHM_CBLUE_OG_CMD = "/tmp/ogCmd.im.shm" # Output Gain command for CBLUE camera
SHM_CBLUE_REFERENCE_SIM = "/tmp/FrameCalibSimu.im.shm" # Simulated calibration frame for testing
SHM_CBLUE_CONV_EFFICIENCY = "/tmp/cblueConvEfficiency.im.shm" # ORCA conversion efficiency (electrons per ADU)

## ORCA Camera
SHM_ORCA_FRAME = "/tmp/orca.im.shm" # ORCA science camera frame
SHM_ORCA_DIT = "/tmp/orcaDit.im.shm" # ORCA Detector Integration Time
SHM_ORCA_FPS = "/tmp/orcaFps.im.shm" # ORCA Frames Per Second
SHM_ORCA_ROI = "/tmp/orcaRoi.im.shm" # ORCA ROI
SHM_ORCA_TEMP = "/tmp/orcaTemp.im.shm" # ORCA detector temperature
SHM_ORCA_BACKGROUND = "/tmp/orcaBg.im.shm" # ORCA background calibration map

## 1st stage loop control
SHM_DM1_LOOP_CL_SWITCH = "/tmp/dm1_lpCmd.im.shm" # switch between open or closed-loop for DM1
SHM_DM1_LOOP_LEAK = "/tmp/dm1_lpLeak.im.shm" # leak factor for DM1 command
SHM_DM1_LOOP_GAIN = "/tmp/dm1_lpGain.im.shm" # integrator gain for DM1 control

## Fast TT 
SHM_FASTTT_LOOP_CL_SWITCH = "/tmp/fast_tt_lpCmd.im.shm" # switch between open or closed-loop for fast TT
SHM_FASTTT_LOOP_LEAK = "/tmp/fast_tt_lpLeak.im.shm" # leak factor for fast TT command
SHM_FASTTT_LOOP_GAIN = "/tmp/fast_tt_lpGain.im.shm" # integrator gain for fast TT control
SHM_FASTTT_RESIDUAL_TT_OFFLOAD = "/tmp/fasttt_residual_OL.im.shm" # Tip/Tilt residuals for offload to DM1
SHM_FASTTT_RESIDUAL_TT = "/tmp/fasttt_residual.im.shm" # Computed TT residuals from wavefront sensor
SHM_FASTTT_CMD = "/tmp/fasttt.im.shm" # Command sent to the fast TT mirror
SHM_FASTTT_CMD_AVG = "/tmp/fastttAvg.im.shm" # rolling mean of SHM_FASTTT_CMD (daoAvgShm), created at runtime
SHM_FASTTT_CHANNEL_0 = "/tmp/fasttt00.im.shm" # Fast TT channel 0 (X or tip component)
SHM_FASTTT_CHANNEL_1 = "/tmp/fasttt01.im.shm" # Fast TT channel 1 (Y or tilt component)
SHM_FASTTT_CHANNEL_2 = "/tmp/fasttt02.im.shm" # Fast TT channel 2 (Z focus or focus component)
SHM_FASTTT_OFFSET="/tmp/fasttt_offset.im.shm" # Offset to the fast TT mirror
SHM_DM_2_FASTTT_OFFLOAD_TOGGLE = "/tmp/dm1_2_fasttt_offload.im.shm" # toggle flag to activate the offload of the DM1 to the fast TT

## TT modulator
SHM_MODULATOR = "/tmp/modulator.im.shm" # SHM with all the data from the modulator

## Telescope control (TCS / ICS interface)
# Inputs (written by a GUI / the RTC, consumed by telescopeCtrl.py)
SHM_TELESCOPE_OFFSET = "/tmp/telOffset.im.shm" # [x, y] pointing offset to send to the telescope [arcsec]
SHM_TELESCOPE_GUIDING = "/tmp/telGuiding.im.shm" # [x, y] guiding correction to send to the telescope [arcsec]
SHM_TELESCOPE_CONTROL_ENABLE = "/tmp/telControlEnable.im.shm" # 0/1 master switch - telescopeCtrl.py only commands the TCS (guiding + offset) when this is 1
# Outputs (published by telescopeCtrl.py from the TCS telemetry)
SHM_TELESCOPE_RADEC = "/tmp/telRaDec.im.shm" # [RA, Dec] current telescope position [deg]
SHM_TELESCOPE_ALTAZ = "/tmp/telAltAz.im.shm" # [Alt, Az, HA] current telescope pointing [deg]
SHM_TELESCOPE_STATUS = "/tmp/telStatus.im.shm" # [power_on, tracking_on, is_slewing, ha_limit_reached, alt_limit_reached] (0/1)
SHM_TELESCOPE_AIRMASS = "/tmp/telAirmass.im.shm" # [airmass] at the current pointing
SHM_TELESCOPE_FOCUS = "/tmp/telFocus.im.shm" # [M2 Z focus position] [mm]
SHM_TELESCOPE_DOME = "/tmp/telDome.im.shm" # [dome shutter state] 0 = closed, 1 = partial, 2 = open
# Fast-TT -> telescope offload (computeTelescopeOffload.py):
#   theta = theta0 + HA - Dec
#   rotMat = [[cos t, -sin t],[sin t, cos t]] . diag(Sx, Sy)     (2x2)
#   [dAlpha, dDelta] = rotMat . fastttAvg
SHM_TELESCOPE_THETA0 = "/tmp/telTheta0.im.shm" # [theta0] calibration constant [deg], default -100
SHM_TELESCOPE_SCALE = "/tmp/telScale.im.shm" # [Sx, Sy] calibration scales, default [0.58, 0.43]
SHM_TELESCOPE_THETA = "/tmp/telThetaAngle.im.shm" # [theta] = theta0 + HA - Dec [deg]
SHM_TELESCOPE_ROTMAT = "/tmp/telRotMat.im.shm" # 2x2 rotation*scale matrix mapping [vx, vy] -> [dAlpha, dDelta]
SHM_TELESCOPE_TT_OFFLOAD = "/tmp/telTtOffload.im.shm" # [dAlpha, dDelta] = rotMat . fastttAvg  (averaged TT projected on sky)
# Automatic fast-TT -> telescope offload loop (telescopeOffload.py)
SHM_TELESCOPE_OFFLOAD_ENABLE = "/tmp/telOffloadEnable.im.shm" # 0/1 - auto offload active (default 0)
SHM_TELESCOPE_OFFLOAD_PERIOD = "/tmp/telOffloadPeriod.im.shm" # [s] between two offload pushes (default 20)
SHM_TELESCOPE_OFFLOAD_GAIN = "/tmp/telOffloadGain.im.shm" # gain applied to telTtOffload before it is sent as guiding (default 0.5)

## CALIBRATION MATRICES
SHM_PYRAMID_2_DM1_REC = "/tmp/papyrus_CM.im.shm" # Pyramid to DM1 reconstructor calibration matrix
SHM_PYRAMID_FLUX_2_FASTTT_REC = "/tmp/pupil_2_fastTT_rec.im.shm" # Pyramid flux to Fast TT reconstructor matrix
SHM_PYRAMID_FLUX_2_DM1_REC = "/tmp/pupil_2_dm1_rec.im.shm" # Pyramid flux to DM1 reconstructor matrix
SHM_DM1_2_FASTTT_REC = "/tmp/dm1_2_fastTT_rec.im.shm" # DM1 to Fast TT offload reconstructor matrix

## Atmosphere simulator
SHM_DM1_ATM_STOP = "/tmp/dm1atmStop.im.shm" # Flag to start/stop atmospheric turbulence simulation
SHM_DM1_ATM_SEEING = "/tmp/dm1atmSeeing.im.shm"  # Atmospheric seeing parameter (Value is multiplied by 10)
SHM_DM1_ATM_WINDSPEED = "/tmp/dm1atmSpeed.im.shm"  # Atmospheric wind speed parameter (Value is multiplied by 5 / 1000)