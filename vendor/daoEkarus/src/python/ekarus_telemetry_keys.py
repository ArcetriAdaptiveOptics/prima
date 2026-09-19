class EkarusTelemetryKeys:
    """Keys saved by the Ekarus telemetry acquisition program."""

    DM_CHANNEL_0_CUBE = 'dmCh0Cube'  # flat DM command
    DM_CHANNEL_1_CUBE = 'dmCh1Cube'  # command sent to the DM by the closed loop
    DM_CHANNEL_2_CUBE = 'dmCh2Cube'  # DM turbulence
    DM_CHANNEL_3_CUBE = 'dmCh3Cube'  # DM command offset
    WFS1_SIGNALS_CUBE = 'WFS1_signalsCube'  # Reduced intensities from WFS 1 (Bg substracted, flux normalized)
    OCAM_CUBE = 'ocamCube'  # Full cube of OCAM frames
    OCAM_TIMESTAMP_CUBE = 'timeStampOcamCube'  # timestamps of the ocam frames

    FAST_TT_COMMANDS_CUBE = 'fastTTcmdsCube'
    FAST_TT_RECONSTRUCTOR = 'fastTTRec'
    FAST_TT_CLOSED_LOOP = 'fastTTisClosedLoop'
    FAST_TT_LOOP_GAIN = 'fastTTlpGain'
    FAST_TT_LOOP_LEAK = 'fastTTlpLeak'

    OCAM_DARK = 'ocamDark'
    OCAM_GAIN = 'ocamGain'
    OCAM_FPS = 'ocamFps'
    OCAM_TEMPERATURE = 'ocamTemp'
    MEAN_OCAM_FRAME = 'meanOcamFrame'
    DM_OFFSET = 'dmOffset'
    DM_CMD_CUBE = 'dmCmdCube'  # sum of DM command channels
    DM_TIMESTAMP_CUBE = 'timeStampDmCube'  # timestamps of the DM commands
    MODULATOR_FREQUENCY = 'modulatorFrequency'
    MODULATOR_RADIUS = 'modulatorRadius'
    MODULATOR_ON_OFF = 'modulatorOn-Off'
    LP_GAIN = 'lpGain'  # loop gain
    LP_LEAK = 'lpLeak'  # leak value
    MODE_CUBE = 'modeCube'  # modal coefficients
    CLOSED_LOOP_STATUS = 'closedLoopStatus'  # flag for open/closed loop
    OCAM_FLAT = 'ocamFlat'  # flat map of the OCAM
    VALID_PIXELS = 'validPixels'  # map of valid pixels
    REF = 'ref'  # reference substracted to the OCAM frames
    S2M = 's2m'  # pyramid signals-to-modes reconstruction matrix
    M2C = 'm2c'  # modes-to-command matrix
    TELESCOPE_OFFSET_CUBE = 'telescope_offset_cube'
    TELESCOPE_GUIDING_CUBE = 'telescope_guiding_cube'
    TELESCOPE_RADEC_CUBE = 'telescope_radec_cube'

    CBLUE_CUBE = 'cblueCube'  # data_cube of the CBLUE cropped to the current ROI
    CBLUE_BACKGROUND = 'cblueBg'  # CBLUE background cropped to ROI
    CBLUE_FULL_BACKGROUND = 'cblueBg_no_ROI'  # CBLUE background (full frame)
    CBLUE_FPS = 'cblueFps'  # CBLUE framerate
    CBLUE_DIT = 'cblueDIT'  # CBLUE exposure time (s)
    CBLUE_GAIN = 'cblueGain'  # CBLUE Gain
    CBLUE_TEMPERATURE = 'cblueTemp'  # CBLUE temperature
    CBLUE_CONVERSION_EFFICIENCY = 'cblueConvEfficiency'  # CBLUE conversion efficiency factor
    CBLUE_TIMESTAMP = 'timeStampCblue'  # CBLUE timestamps
    CBLUE_ROI_VECTOR = 'cblue_roi_vector'  # values of the CBLUE ROI [width, cy, cx]

    ORCA_CUBE = 'orcaCube'  # data_cube of the ORCA cropped to the current ROI
    ORCA_BACKGROUND = 'orcaBg'  # ORCA background cropped to ROI
    ORCA_FULL_BACKGROUND = 'orcaBg_no_ROI'  # ORCA background (full frame)
    ORCA_FPS = 'orcaFps'  # ORCA framerate
    ORCA_DIT = 'orcaDIT'  # ORCA exposure time (s)
    ORCA_TEMPERATURE = 'orcaTemp'  # ORCA temperature
    ORCA_TIMESTAMP = 'timeStampOrca'  # ORCA timestamps
    ORCA_ROI_VECTOR = 'orca_roi_vector'  # values of the ORCA ROI [width, cy, cx]

    LOOP_STATUS = 'LoopStatus'  # Closed-loop flag
