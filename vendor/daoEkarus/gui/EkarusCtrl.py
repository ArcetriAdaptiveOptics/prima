#!/usr/bin/env python3
#

from GUIUtils import *
from daoEkarusShmNames import *
from PyQt5.QtWidgets import QMessageBox, QFileDialog

## WIDGETS and POP UP WINDOWS
from benchTests import BenchTest
from calibrationParameters import calibrationParameters
from calibrationDisplay import CalibrationDisplay
from diagnostics import Diagnostics
# from dummyPlot import LogLogPlotWindow
from modalPlot import ModalPlot
from modePSD import ModePSD

if platform.system() == "Darwin":
    # macOS: launch via osascript in Terminal
    console = [
        "osascript",
        "-e",
        f'tell application "Terminal" to do script \\"{sys.executable} \\"',
    ]
    console_wrap = True  # We'll need to wrap the full command in quotes
else:
    # Linux: find available terminal
    if shutil.which("terminator"):
        console = ["terminator", "-x"]
    elif shutil.which("gnome-terminal"):
        console = ["gnome-terminal", "--"]
    elif shutil.which("xterm"):
        console = ["xterm", "-e"]
    elif shutil.which("konsole"):
        console = ["konsole", "-e"]
    else:
        raise RuntimeError(
            "No supported terminal found (gnome-terminal, xterm, konsole)"
        )

    console_wrap = False


path = os.getenv("DAOROOT") + "/data/"
Ui_MainWindow, QMainWindow = loadUiType(os.path.join(path, "EkarusCtrl.ui"))


class EkarusCtrlApp(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super(EkarusCtrlApp, self).__init__()
        self.setupUi(self)
        self.threadpool = QThreadPool()  # Create a thread pool
        self.shmim = dao.shm(SHM_OCAM_FRAME)

        # Extract 'baseName'
        self.shmBgPercentName = f"/tmp/papyrus_dark_mapPercent.im.shm"
        self.shmBg = dao.shm(SHM_OCAM_BACKGROUND)
        self.shmOcamRef = dao.shm(SHM_OCAM_REFERENCE)
        self.shmOcamOldRef = dao.shm(SHM_OCAM_REFERENCE_BEFORE_NCPA_OFFSET)
        self.shmOcamRefFlux = dao.shm(SHM_OCAM_REFERENCE_FLUX)
        self.shmPup = dao.shm(SHM_PYRAMID_VALID_PIXELS)
        self.shmBgP = dao.shm(SHM_OCAM_DARK_MAP_PERCENT, np.zeros((1, 1)).astype(np.uint32))
        self.shmLpLeak = dao.shm(SHM_DM1_LOOP_LEAK)
        self.shmLpGain = dao.shm(SHM_DM1_LOOP_GAIN)
        self.shmLpCmd = dao.shm(SHM_DM1_LOOP_CL_SWITCH)
        self.pwfs_modulator = dao.shm(SHM_MODULATOR)
        self.fast_tt_pos = dao.shm(SHM_FASTTT_CMD)

        self.shmdm = dao.shm(SHM_DM1_CMD)
        self.shmdm_0 = dao.shm(SHM_DM1_CHANNEL_0)
        self.shmdm_1 = dao.shm(SHM_DM1_CHANNEL_1)
        self.shmdm_2 = dao.shm(SHM_DM1_CHANNEL_2)
        self.shmdm_3 = dao.shm(SHM_DM1_CHANNEL_3)
        self.shmdm_offset = dao.shm(SHM_DM1_CMD_OFFSET)

        self.shmm2c = dao.shm(SHM_DM1_M2C)

        self.map = dao.shm(SHM_DM1_468_MASK)
        self.atmStop = dao.shm(SHM_DM1_ATM_STOP, np.zeros((1, 1)).astype(np.uint32))

        ## OCAM STATS INITIALIZATION
        self.shmOcam2gain = dao.shm(SHM_OCAM_GAIN)
        self.shmOcam2fps = dao.shm(SHM_OCAM_FPS)
        self.shmOcam2temp = dao.shm(SHM_OCAM_TEMPERATURE)

        ## OFFLOAD SHMs
        self.shm_TTlp = dao.shm(SHM_FASTTT_LOOP_CL_SWITCH)
        self.shm_TTlp_gain = dao.shm(SHM_FASTTT_LOOP_GAIN)
        self.shm_TTlp_leak = dao.shm(SHM_FASTTT_LOOP_LEAK)
        self.shm_offload_TT = dao.shm(SHM_DM_2_FASTTT_OFFLOAD_TOGGLE)
        # self.shm_offload_TTlp_gain = dao.shm(SHM_OFFLOAD_DM_TT_GAIN)
        # self.shm_FIMlp = dao.shm(SHM_FIM_STATE)

        # DM shape view (was: manual vb/img/setColorMap/setAspectLocked/setImage)
        self.dmShape = DmShapeView(self.dmView, self.map.get_data(), colormap="viridis")
        self.dmShape_0 = DmShapeView(self.dmView_0, self.map.get_data(), colormap="viridis")
        self.dmShape_1 = DmShapeView(self.dmView_1, self.map.get_data(), colormap="viridis")
        self.dmShape_2 = DmShapeView(self.dmView_2, self.map.get_data(), colormap="viridis")
        self.dmShape_3 = DmShapeView(self.dmView_3, self.map.get_data(), colormap="viridis")
        self.dmRecShape = DmShapeView(self.dmView_4, self.map.get_data(), colormap="viridis")

        self.imageSizeX = self.shmim.get_data().shape[0]
        self.imageSizeY = self.shmim.get_data().shape[1]
        im = self.shmim.get_data().astype(np.float32)
        im = im.flatten().reshape((self.imageSizeX, self.imageSizeY))

        # Tip-tilt scatter view (was: manual ttVB + InfiniteLines + ScatterPlotItem)
        self.ttScatterView = TtScatterView(self.ttView, extent=50)

        self.original_style = ""
        # OCAM canvas + nav toolbar (was: hand-rolled QVBoxLayout wiring)
        self.canvas = MplCanvas(self, width=5, height=4.5, dpi=100, im=im)
        self.toolbar = mount_mpl_canvas(self.imageView, self.canvas, parent=self)

        # Get first image
        im = self.shmim.get_data().astype(np.float32)
        im = im.flatten().reshape((self.imageSizeX, self.imageSizeY))
        pup = self.shmPup.get_data()
        # Plot the first image
        # self.canvas.plot_image(im, im * 0 + True)
        self.canvas.plot_image(im, pup.astype(np.bool))
        # save first counter
        self.imCnt1 = self.shmim.get_meta_data()["cnt0"]

        # Create QT timer to update display
        self.timer = QtCore.QTimer(self)
        # Throw event timeout with an interval of 50 milliseconds
        self.timer.setInterval(50)
        # each time timer counts done call self.Update
        self.timer.timeout.connect(self.Update)
        # save initial time for frequency display purpose
        self.t1 = time.time()

        # Connect buttons to their respective methods
        self.fpsButton.clicked.connect(self.updateFps)
        self.gainButton.clicked.connect(self.updateGain)
        self.protectionResetButton.clicked.connect(self.protectionReset)
        self.temperatureButton.clicked.connect(self.updateTemp)
        self.modulationButton.clicked.connect(self.setModulation)
        self.acqBgButton.clicked.connect(self.acqBgData)
        self.computePupilButton.clicked.connect(self.computePupil)
        self.computePixelButton.clicked.connect(self.reComputePupil)
        self.computeIMButton.clicked.connect(self.computeIM)
        self.stopComputeIMButton.clicked.connect(self.stopCalibration)  # ADD THIS LINE
        self.computeCMButton.clicked.connect(self.computeCM)
        self.calibrateFastTTButton.clicked.connect(self.calibrateFastTT)
        self.calibrateSelectedButton.clicked.connect(self.CalibrateSelected)
        self.loadM2CButton.clicked.connect(self.loadM2C)
        self.currentM2CLabel = ""
        try:
            with open(os.getenv("DAODATA") + "/inputs/dm468/current_m2c.txt") as f:
                last_path = f.read().strip()
                f.close()
            self.currentM2CLabel = os.path.splitext(os.path.basename(last_path))[0]
            self.dmV2nm = get_dmV2nm_conversion(self.shmm2c.get_data())
        except FileNotFoundError:
            self.currentM2CLabel = ""
            self.dmV2nm = 1 # initialize at 1, update on M2C load
        self.m2cStatusLabel.setText(self.currentM2CLabel or "No M2C loaded")
        self.currentInteractionMatrixLabel = ""
        self.interactionMatrixLabel.setText("No Int. Matrix loaded")
        self.loadIMButton.clicked.connect(self.loadInteractionMatrix)
        self.lpLeakButton.clicked.connect(self.updateLpLeak)
        self.lpGainButton.clicked.connect(self.updateLpGain)
        # self._gainTimer = QtCore.QTimer(self)
        # self._gainTimer.setSingleShot(True)
        # self._gainTimer.setInterval(600)
        # self._gainTimer.timeout.connect(self.updateLpGain)
        # self.lpGainBox.valueChanged.connect(lambda _: self._gainTimer.start())
        # self._gainTimer.timeout.connect(self.updateLpLeak)
        # self.lpLeakBox.valueChanged.connect(lambda _: self._gainTimer.start())
        # self.lpGainBox.valueChanged.connect(self.updateLpGain)
        # self.lpLeakBox.valueChanged.connect(self.updateLpLeak)
        self.closeLoopButton.clicked.connect(self.closeLoop)
        self.openLoopButton.clicked.connect(self.openLoop)
        self.saveFlatButton.clicked.connect(self.saveFlat)
        self.loadFlatButton.clicked.connect(self.loadFlat)
        self.resetFlatButton.clicked.connect(self.resetFlat)
        self.filterTTButton.clicked.connect(self.filterTT)
        self.acqTelemButton.clicked.connect(self.acqTelem)
        self.openBenchTestsButton.clicked.connect(self.openBenchTestsWindow)
        self.calibrationParametersButton.clicked.connect(self.openCalibrationParametersWindow)
        self.tt_centering_gain.editingFinished.connect(self.disp_tt_centering_gain)
        self.tt_centering_leak.editingFinished.connect(self.disp_tt_centering_leak)
        # self.TTOffloadCheckBox.toggled.connect(self.onTTOffloadToggled)
        self.set_tt_offload.clicked.connect(self.tt_offload)
        self.set_tt_centering.clicked.connect(self.tt_centering)
        self.saveTTButton.clicked.connect(self.saveTT)
        self.loadTTButton.clicked.connect(self.loadTT)
        self.resetTTButton.clicked.connect(self.resetTT)
        self.acquireRefFrameButton.clicked.connect(self.takeRef)
        self.resetRefFrameButton.clicked.connect(self.resetRef)
        self.acquireNCPAButton.clicked.connect(self.takeNcpa)
        self.loadNCPAButton.clicked.connect(self.loadNcpa)
        self.resetNCPAButton.clicked.connect(self.resetNcpa)
        if np.sum(self.shmOcamRef.get_data()) > 0:
            self.resetRefFrameButton.setStyleSheet("background-color: green")
            if np.sum(self.shmOcamOldRef.get_data()) > 0:
                self.resetNCPAButton.setStyleSheet("background-color: green")
                self.resetRefFrameButton.setStyleSheet("background-color: grey")

        self.loadPupilsButton.clicked.connect(self.loadValidPixels)
        self.modalPlotWindow = None
        self.showModalPlot.clicked.connect(self.modalPlot)
        self.modePSDWindow = None
        self.showModePSD.clicked.connect(self.modePSD)
        self.calibrationCheckWindow = None
        self.displayCalibButton.clicked.connect(self.displayCalibration)
        self.openDmCtrlButton.clicked.connect(self.openDmCtrl)
        # self.tt_centering_flag = False
        self.activeCalibrationWorker = None  # Track active calibration process to allow killing it
        self.acqPercent = 0
        self.acqBgPercent = 0
        self.nbAcq = 1000
        self.nbBgAcq = 1000

        self.shmmode = dao.shm(SHM_WFS1_RECONSTRUCTED_MODES)
        self.modeHistCanvas = ModeHistCanvas(
            self,
            data=self.shmmode.get_data().flatten()[:405] * self.dmV2nm[:405],
            ylim=(-25,25), #(-0.1, 0.1),
            width=5, height=4, dpi=100, ylabel='[nm]',
        )
        mount_mpl_canvas(self.modeHist, self.modeHistCanvas, parent=self, toolbar=False)

        self.openLoopButton.setStyleSheet("background-color: green")

        self.benchTestsWindow = None
        self.diagnosticsWindow = None
        self.calibrationParametersWindow = calibrationParameters(self)
        self.is_simulation = dao.shm(SHM_OOPAO_MODE).get_data()[0, 0]

    def Start(self):
        """Start timer."""
        self.timer.start()

    def Stop(self):
        """Stop timer."""
        self.timer.stop()

    def _clear_active_worker(self):
        """Clear the active worker reference when done."""
        self.activeCalibrationWorker = None

    def resetDMOffsets(self):
        """Reset DM offsets (channel 2 and 3) to zero."""
        try:
            # Reset DM channels
            self.shmdm_2.set_data(self.shmdm_2.get_data() * 0)
            self.shmdm_3.set_data(self.shmdm_3.get_data() * 0)
            self.logBgLabel.setText("DM offsets reset to zero")
        except Exception as e:
            self.logBgLabel.setText(f"Error resetting DM: {str(e)}")

    def stopCalibration(self):
        """Stop the running computeIM process."""
        if self.activeCalibrationWorker is not None:
            try:
                self.activeCalibrationWorker.stop()
                self.logBgLabel.setText("Calibration Process stopped")
                self.activeCalibrationWorker = None
                # Reset DM commands
                self.resetDMOffsets()
            except Exception as e:
                self.logBgLabel.setText(f"Error stopping process: {str(e)}")
        else:
            self.logBgLabel.setText("No active calibration to stop")

    def display_calibration(self):
        """ """

    @QtCore.pyqtSlot()
    def Update(self):
        """Update the GUI."""
        # Update the displayed image with the data of the SHM
        im = self.shmim.get_data().astype(np.float32)
        im = im.flatten().reshape((self.imageSizeX, self.imageSizeY))
        pup = self.shmPup.get_data()
        neg = False
        if self.bgCheckBox.isChecked():
            im = im - self.shmBg.get_data().flatten().reshape(
                (self.imageSizeX, self.imageSizeY)
            )
            neg = True
        pup = self.shmPup.get_data() * 0 + True
        pupMask = self.shmPup.get_data().astype(np.float32)
        impup = im.copy()
        if self.pupCheckBox.isChecked() == True:
            impup /= im.max()
            impup -= pupMask/2
            neg = True
        else:
            neg = False
        if self.maskCheckBox.isChecked() == True:
            impup *=  pupMask
        self.canvas.plot_image(impup, pup, neg=neg)

        # Get the counter
        self.imCnt2 = self.shmim.get_counter()
        self.t2 = time.time()
        ellapsedTime = self.t2 - self.t1
        nbImage = self.imCnt2 - self.imCnt1
        fluxInPupil = np.sum(im*pupMask)/np.sum(pupMask)*self.shmOcam2fps.get_data()[0, 0]
        # Display frequency
        self.freqLabel.setText(f"{nbImage/ellapsedTime:.2f} Hz")
        self.fluxLabel.setText(f"{fluxInPupil/1000.0:1.1f} e-/pix/ms")
        self.t1 = self.t2
        self.imCnt1 = self.imCnt2
        self.progressBgBar.setValue(self.shmBgP.get_data()[0, 0])
        # convert to ms
        self.lpLeakStatusLabel.setText(str(self.shmLpLeak.get_data()[0, 0]))
        self.lpGainStatusLabel.setText(str(self.shmLpGain.get_data()[0, 0]))
        if self.shmLpCmd.get_data()[0, 0] == 0:
            self.loopStatusLabel.setText("Open")
            self.closeLoopButton.setStyleSheet("")
            self.openLoopButton.setStyleSheet("background-color: green")
        else:
            self.loopStatusLabel.setText("Closed")
            self.closeLoopButton.setStyleSheet("background-color: green")
            self.openLoopButton.setStyleSheet("")

        # DM shape + min/max labels. One shm read (was three), then hand the
        # array to the view; labels stay in the controller.
        dm_mask = self.map.get_data()
        dm_cmd = self.shmdm.get_data()
        self.dmShape.update_shape(dm_cmd, dm_mask)
        self.dmMinStatusLabel.setText(f"{np.min(dm_cmd[:, 0]):.2f}")
        self.dmMaxStatusLabel.setText(f"{np.max(dm_cmd[:, 0]):.2f}")
        self.dmRMSStatusLabel.setText(f"{np.sqrt(np.mean(dm_cmd[:, 0]**2)):.2f}")

        dm_cmd_0 = self.shmdm_0.get_data()
        self.dmShape_0.update_shape(dm_cmd_0, dm_mask)

        dm_cmd_1 = self.shmdm_1.get_data()
        self.dmShape_1.update_shape(dm_cmd_1, dm_mask)

        dm_cmd_2 = self.shmdm_2.get_data()
        dm_cmd_3 = self.shmdm_3.get_data()
        self.dmShape_2.update_shape(dm_cmd_2+dm_cmd_3, dm_mask)

        dm_cmd_offset = self.shmdm_offset.get_data()
        self.dmShape_3.update_shape(dm_cmd_offset, dm_mask)

        # Modes histogram
        dm_modes = self.shmmode.get_data().flatten()
        self.modeHistCanvas.update_hist(dm_modes * self.dmV2nm[:len(dm_modes)])

        dm_rec_cmds = self.shmm2c.get_data() @ dm_modes
        self.dmRecShape.update_shape(dm_rec_cmds.reshape([len(dm_rec_cmds),1]), dm_mask)
        self.dmRecModesMinLabel.setText(f"Min: {np.min(dm_rec_cmds[:]):.3f}")
        self.dmRecModesMaxLabel.setText(f"Max: {np.max(dm_rec_cmds[:]):.3f}")

        self.OcamFPSStatusLabel.setText(str(self.shmOcam2fps.get_data()[0, 0]) + " Hz")
        self.OcamGainStatusLabel.setText(str(self.shmOcam2gain.get_data()[0, 0]))
        self.OcamTemperatureStatusLabel.setText(
            str(self.shmOcam2temp.get_data()[0, 0]) + " C"
        )
        self.modLabelDynamic.setText(str(self.pwfs_modulator.get_data()[1, 0]))

        fast_tt_pos = self.fast_tt_pos.get_data() - 50.
        self.ttScatterView.update_position(fast_tt_pos[0, 0], fast_tt_pos[1, 0])


    def updateFps(self):
        """Call an external script to set the Camera FPS"""
        # Command to call the external script
        command = [
            "python3",
            os.getenv("DAOROOT") + "/bin/setOcamFps.py",
            str(self.fpsBox.value()),
        ]
        # Create a worker for the subprocess
        worker = SubprocessWorker(command)
        # Execute the worker in the background
        self.threadpool.start(worker)

        ## Also set the modulation
        self.setModulation(ocam_fps=self.fpsBox.value())

    def updateGain(self):
        """Call an external script to set the Camera FPS"""
        # Command to call the external script
        command = [
            "python3",
            os.getenv("DAOROOT") + "/bin/setOcamGain.py",
            str(self.gainBox.value()),
        ]
        # Create a worker for the subprocess
        worker = SubprocessWorker(command)
        # Execute the worker in the background
        self.threadpool.start(worker)


    def protectionReset(self):
        self.protectionResetButton.setStyleSheet("background-color: green")
        QtCore.QTimer.singleShot(
            10000,
            lambda: self.reset_button_color(
                self.protectionResetButton, self.original_style
            ),
        )
        """Call an external script to set the Camera Gain protectionReset"""
        # Command to call the external script
        command = ["python3", os.getenv("DAOROOT") + "/bin/protectionReset.py"]
        # Create a worker for the subprocess
        worker = SubprocessWorker(command)
        # Execute
        self.threadpool.start(worker)

    def updateTemp(self):
        """Call an external script to set the Camera FPS"""
        # Command to call the external script
        command = [
            "python3",
            os.getenv("DAOROOT") + "/bin/setOcamTemp.py",
            str(self.temperatureBox.value()),
        ]
        # Create a worker for the subprocess
        worker = SubprocessWorker(command)
        # Execute the worker in the background
        self.threadpool.start(worker)


    def setModulation(self, check=False, ocam_fps=None):
        if ocam_fps is None:
            ocam_fps = self.shmOcam2fps.get_data()[0, 0]
        """Call an external script to set the modulation radius"""
        # Command to call the external script
        command = [
            "python3",
            os.getenv("DAOROOT") + "/bin/setModulation.py",
            str(ocam_fps),
            str(self.modRadiusBox.value()),
        ]
        # Create a worker for the subprocess
        worker = SubprocessWorker(command)
        # Execute the worker in the background
        self.threadpool.start(worker)

    def acqBgData(self, finished_callback=None):
        """Call an external script to acquire background data."""
        # Command to call the external script
        command = [
            "python3",
            os.getenv("DAOROOT") + "/bin/takeBG.py",
            str(self.nbFrameBgBox.value()),
        ]
        self.runCalibrationCommand(command, finished_callback)

    def computePupil(self, finished_callback=None):
        """Call an external script to acquire new valid pixels."""
        # Command to call the external script
        command = [
            "python3",
            os.getenv("DAOROOT") + "/bin/select_valid_pixels.py",
            str(self.nbFramePupilBox.value()),
        ]
        # self.runCalibrationCommand(command, finished_callback)
        self.runCalibrationCommand(command, self.on_change_pupils_done)

    def reComputePupil(self, finished_callback=None):
        """Call an external script to acquire new valid pixels."""
        # Command to call the external script
        command = [
            "python3",
            os.getenv("DAOROOT") + "/bin/select_valid_pixels.py",
            str("skip_measurement"),
        ]
        # self.runCalibrationCommand(command, finished_callback) 
        self.runCalibrationCommand(command, self.on_change_pupils_done)

    def loadValidPixels(self):
        """Call an external script to load the pupils"""
        pupil_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select valid pixels file",
            "/home/daouser/DAODATA/calibration/pupils",
            "FITS Files (*.fits);;All Files (*)",
        )
        if not pupil_path:
            return
        command = [
            "python3",
            os.getenv("DAOROOT") + "/bin/loadPupils.py",
            SHM_PYRAMID_VALID_PIXELS,
            pupil_path,
        ]
        # worker = SubprocessWorker(command)
        # self.threadpool.start(worker)
        self.runCalibrationCommand(command, self.on_change_pupils_done)

    def computeIM(self, finished_callback=None):
        """Call an external script to acquire an interaction matrix."""
        p = self.calibrationParametersWindow.get_parameters()
        command = [
            "python3",
            os.getenv("DAOROOT") + "/bin/computeInteractionMatrix.py",
            str(self.nbModeBox.value()),
            str(self.currentM2CLabel),
            "--amplitude", str(p["amplitude"]),
            "--nFrameAverage", str(p["nFrameAverage"]),
            "--nRepetition", str(p["nRepetition"]),
            "--modalScaling", str(int(p["modalScaling"])),
        ]
        self.runCalibrationCommand(command, finished_callback)

    def computeCM(self, finished_callback=None):
        """Call an external script to compute a new reconstruction matrix."""
        # Command to call the external script
        command = [
            "python3",
            os.getenv("DAOROOT") + "/bin/computeReconstructionMatrix.py",
            str(self.nbModeBox.value()),
            str(self.currentM2CLabel),
        ]
        self.runCalibrationCommand(command, finished_callback)

    def calibrateFastTT(self, finished_callback=None):
        """Call an external script to calibrate the fast TT mirror."""
        # Command to call the external script
        command = [
            "python3",
            os.getenv("DAOROOT") + "/bin/calibrateFastTT.py",
        ]
        self.runCalibrationCommand(command, finished_callback)

    def loadM2C(self):
        """Open a file picker to select and load an M2C file."""
        m2c_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select M2C file",
            "/home/daouser/DAODATA/inputs/dm468/M2C",
            "NumPy Files (*.npy);;All Files (*)",
        )
        if not m2c_path:          # user cancelled
            return
        self.currentM2CLabel = os.path.splitext(os.path.basename(m2c_path))[0]
        self.m2cStatusLabel.setText(self.currentM2CLabel)
        with open(os.getenv("DAODATA") + "/inputs/dm468/current_m2c.txt", "w") as f:
            f.write(m2c_path)
            f.close()

        command = [
            "python3",
            os.getenv("DAOROOT") + "/bin/selectBasis.py",
            m2c_path,
        ]
        self.runCalibrationCommand(command, self.on_change_m2c_done)

    def loadInteractionMatrix(self):
        """Open a file picker to select and load an interaction matrix file."""
        im_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Interaction Matrix file",
            "/home/daouser/DAODATA/inputs/calibration/interactionMatrix/",
            "NumPy Files (*.npy);;All Files (*)",
        )
        if not im_path:          # user cancelled
            return
        self.currentInteractionMatrixLabel = os.path.splitext(os.path.basename(im_path))[0]
        self.interactionMatrixLabel.setText(self.currentInteractionMatrixLabel)
        with open(os.getenv("DAODATA") + "/inputs/calibration/interactionMatrix/current_imat.txt", "w") as f:
            f.write(im_path)
            f.close()

    def runCalibrationCommand(self, command, finished_callback=None):
        worker = SubprocessWorker(command)
        self.activeCalibrationWorker = worker  # STORE REFERENCE
        
        worker.signals.finished.connect(self.on_acq_bg_done)
        worker.signals.error.connect(self.on_acq_bg_error)
        
        # Clear reference when done
        worker.signals.finished.connect(lambda: self._clear_active_worker())
        worker.signals.error.connect(lambda: self._clear_active_worker())
        
        if finished_callback:
            worker.signals.finished.connect(finished_callback)
        
        self.threadpool.start(worker)
        self.logBgLabel.setText("Acquisition in Progress...")
    
    def CalibrateSelected(self):
        self.calibrationQueue = []

        # if self.backgroundCheckBox.isChecked():
        #     self.calibrationQueue.append(
        #         lambda: self.acqBgData(self.on_calib_bg_done)
        #         )
        #     msg_box = QMessageBox(self)
        #     msg_box.setWindowTitle("Background Acquisition")
        #     msg_box.setText("Please turn OFF the laser before acquiring the background.\n\n"
        #                     "Click OK when the laser is OFF.")
        #     msg_box.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        #     msg_box.setDefaultButton(QMessageBox.Ok)

        #     style_messagebox(msg_box)
        #     reply = msg_box.exec_()

        if self.pupilCheckBox.isChecked():
            self.calibrationQueue.append(
                lambda: self.computePupil(self.on_calib_step_done)
                )

        if self.iMatCheckBox.isChecked():
            self.calibrationQueue.append(
                lambda: self.computeIM(self.on_calib_step_done)
                )

        if self.reconCheckBox.isChecked():
            self.calibrationQueue.append(
                lambda: self.computeCM(self.on_calib_step_done)
                )

        # if self.fastTTCheckBox.isChecked():
        #     self.calibrationQueue.append(
        #         lambda: self.calibrateFastTT(self.on_calib_step_done)
        #         )

        self.runNextCalibration()


    def runNextCalibration(self):
        """Run the next calibration in the queue."""

        if not self.calibrationQueue:
            self.logBgLabel.setText("Calibration finished.")
            return

        calibration = self.calibrationQueue.pop(0)
        calibration()

    def updateLpLeak(self):
        """Call an external script to set the Loop Leak"""
        # Command to call the external script
        command = [
            "python3",
            os.getenv("DAOROOT") + "/bin/setLoopLeak.py",
            SHM_DM1_LOOP_LEAK,
            str(self.lpLeakBox.value()),
        ]
        # Create a worker for the subprocess
        worker = SubprocessWorker(command)
        # Execute the worker in the background
        self.threadpool.start(worker)

    def updateLpGain(self):
        """Call an external script to set the Loop Gain"""
        # Command to call the external script
        command = [
            "python3",
            os.getenv("DAOROOT") + "/bin/setLoopGain.py",
            SHM_DM1_LOOP_GAIN,
            str(self.lpGainBox.value()),
        ]
        # Create a worker for the subprocess
        worker = SubprocessWorker(command)
        # Execute the worker in the background
        self.threadpool.start(worker)

    def closeLoop(self):
        self.closeLoopButton.setStyleSheet("background-color: green")
        self.openLoopButton.setStyleSheet("")
        """Call an external script to close the loop"""
        # Command to call the external script
        command = ["python3", os.getenv("DAOROOT") + "/bin/closeLoop.py", SHM_DM1_LOOP_CL_SWITCH]
        # Create a worker for the subprocess
        worker = SubprocessWorker(command)
        # Execute the worker in the background
        self.threadpool.start(worker)

    def openLoop(self):
        self.openLoopButton.setStyleSheet("background-color: green")
        self.closeLoopButton.setStyleSheet("")
        """Call an external script to open the loop"""
        # Command to call the external script
        command = ["python3", os.getenv("DAOROOT") + "/bin/openLoop.py", SHM_DM1_LOOP_CL_SWITCH]
        # Create a worker for the subprocess
        worker = SubprocessWorker(command)
        # Execute the worker in the background
        self.threadpool.start(worker)

        # # Open the TT loop
        # self.tt_centering_flag = True
        # self.tt_centering()

    def saveFlat(self):
        """Call an external script to save the flat"""
        # Command to call the external script
        command = [
            "python3",
            os.getenv("DAOROOT") + "/bin/saveFlat.py",
            SHM_DM1_CMD,
            "dm468"
        ]
        # Create a worker for the subprocess
        worker = SubprocessWorker(command)
        # Execute the worker in the background
        self.threadpool.start(worker)

    def loadFlat(self):
        """Call an external script to load the flat"""
        # flat_path, _ = QFileDialog.getOpenFileName(
        #     self,
        #     "Select flat file",
        #     "/home/daouser/DAODATA/inputs/dm468/flats",
        #     "FITS Files (*.fits);;NumPy Files (*.npy);;All Files (*)",
        # )
        # if not flat_path:
        #     return
        # Command to call the external script
        command = [
            "python3",
            os.getenv("DAOROOT") + "/bin/loadFlat.py",
            SHM_DM1_CHANNEL_0,
            "dm468",
            # flat_path,
        ]
        worker = SubprocessWorker(command)
        self.threadpool.start(worker)

    def resetFlat(self):
        """Call an external script to reset the flat"""
        # Command to call the external script
        command = [
            "python3",
            os.getenv("DAOROOT") + "/bin/resetFlat.py",
            SHM_DM1_CHANNEL_0
        ]
        # Create a worker for the subprocess
        worker = SubprocessWorker(command)
        # Execute the worker in the background
        self.threadpool.start(worker)


    def takeRef(self, finished_callback=None):
        """Call an external script to acquire the ref frame"""
        # Command to call the external script
        command = [
            "python3",
            os.getenv("DAOROOT") + "/bin/takeRef.py",
            str(self.nbFrameRefBox.value()),
        ]
        self.resetRefFrameButton.setStyleSheet("background-color: green")
        self.runCalibrationCommand(command, finished_callback=finished_callback)

    def saveRef(self, finished_callback=None):
        """Call an external script to save the (un-normalized) ref frame"""
        # Command to call the external script
        tn = time.strftime("%Y%m%d_%H%M%S", time.localtime())
        command = [
            "python3",
            os.getenv("DAOROOT") + "/bin/saveRef.py",
            tn,
        ]
        self.runCalibrationCommand(command, finished_callback=finished_callback)

    def loadRef(self):
        """Call an external script to load the (un-normalized) ref frame"""
        ref_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select ref file",
            "/home/daouser/DAODATA/inputs/referenceFrames",
            "FITS Files (*.fits);;NumPy Files (*.npy);;All Files (*)",
        )
        if not ref_path:
            return
        command = [
            "python3",
            os.getenv("DAOROOT") + "/bin/loadRef.py",
            SHM_OCAM_REFERENCE,
            ref_path,
        ]
        self.resetRefFrameButton.setStyleSheet("background-color: green")
        self.runCalibrationCommand(command)

    def resetRef(self):
        """Call an external script to reset the ref frame"""
        # Command to call the external script
        command = [
            "python3",
            os.getenv("DAOROOT") + "/bin/resetRef.py",
        ]
        self.resetRefFrameButton.setStyleSheet("background-color: grey")
        self.runCalibrationCommand(command)

    def takeNcpa(self, finished_callback=None):
        """ Call an external script to acquire ncpa """
        # Command to call the external script
        command = [
            "python3",
            os.getenv("DAOROOT") + "/bin/ncpaCompensation.py",
        ]
        self.runCalibrationCommand(command, finished_callback=finished_callback)
        self.resetNCPAButton.setStyleSheet("background-color: green")
        self.resetRefFrameButton.setStyleSheet("background-color: grey")

    def loadNcpa(self):
        ncpa_dir = os.path.join(
            os.getenv("DAODATA"),
            "calibration",
            "ncpa",
        )
        ncpa_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select NCPA file",
            ncpa_dir,
            "NCPA files (*.npz)",
        )
        if not ncpa_path:
            return
        try:
            with np.load(ncpa_path) as ncpa_data:
                frame_offset = np.asarray(
                    ncpa_data["frame_offset"],
                    dtype=np.float32,
                )
            current_ref = self.shmOcamRef.get_data()
            if current_ref.shape != frame_offset.shape:
                raise ValueError(
                    f"Shape mismatch: {current_ref.shape} != {frame_offset.shape}"
                )
            self.shmOcamOldRef.set_data(current_ref)
            self.shmOcamRef.set_data(frame_offset)
            self.resetNCPAButton.setStyleSheet("background-color: green")
            self.resetRefFrameButton.setStyleSheet("background-color: grey")
        except (KeyError, OSError, ValueError) as error:
            QMessageBox.critical(
                self,
                "NCPA Load Error",
                f"Could not load NCPA file:\n{error}",
            )


    def resetNcpa(self):
        """ Remove the NCPA reference frame """
        oldRef = self.shmOcamOldRef.get_data()
        self.shmOcamRef.set_data(oldRef)
        self.shmOcamOldRef.set_data(oldRef*0)
        self.resetNCPAButton.setStyleSheet("background-color: grey")
        if np.sum(oldRef) > 0:
            self.resetRefFrameButton.setStyleSheet("background-color: green")


    def displayCalibration(self):
        if self.calibrationCheckWindow is None:
            self.calibrationCheckWindow = CalibrationDisplay(self)
        self.calibrationCheckWindow.show()
        self.calibrationCheckWindow.raise_()
        self.calibrationCheckWindow.activateWindow()
        self.calibrationCheckWindow.Start()


    def modalPlot(self):
        """Spawns the modal plot window or brings it to the front if it exists."""
        if self.modalPlotWindow is None:
            self.modalPlotWindow = ModalPlot(parent=self)
            self.modalPlotWindow.show()
            self.modalPlotWindow.Start()
        else:
            self.modalPlotWindow.raise_()
            self.modalPlotWindow.activateWindow()

    def modePSD(self):
        """Open the modal PSD display window."""
        if self.modePSDWindow is None:
            self.modePSDWindow = ModePSD(parent=self)
        self.modePSDWindow.show()
        self.modePSDWindow.raise_()
        self.modePSDWindow.activateWindow()
        self.modePSDWindow.Start()

    def openDmCtrl(self):
        """Open the standalone DM channels GUI (ekarusDmCtrl.py) in its own
        process. Launches the installed script directly -- nothing imported."""
        script_path = os.path.join(os.getenv("DAOROOT"), "bin", "ekarusDmCtrl.py")
        try:
            subprocess.Popen([sys.executable, script_path])
        except Exception as e:
            self.logBgLabel.setText(f"Error opening DM ctrl: {e}")

    def _run_script(self, script_name, args):
        """Helper to run external script in terminal"""
        script_path = os.path.join(os.getenv("DAOROOT"), "bin", script_name)
        if console_wrap:
            script = f'{sys.executable} {script_path} {" ".join(args)}'
            command = [
                "osascript",
                "-e",
                f'tell application "Terminal" to do script "{script}"\nactivate',
            ]
        else:
            command = console + [sys.executable, script_path] + args

        worker = SubprocessWorker(command)
        self.threadpool.start(worker)

    def reset_button_color(self, button, original_style):
        button.setStyleSheet(original_style)




    def filterTT(self):
        """Call an external script to filter the TT from the flat"""
        # Command to call the external script
        command = ["python3", os.getenv("DAOROOT") + "/bin/FilterTTFromFlat.py"]
        # Create a worker for the subprocess
        worker = SubprocessWorker(command)
        # Execute the worker in the background
        self.threadpool.start(worker)


    def acqTelem(self):
        """Call an external script to acquire AO telemetry"""
        # Command to call the external script
        # command = ["xterm ", "--", "python3", os.getenv("DAOROOT")+"/bin/telemetry.py",  str(self.nbFrameTelemBox.value()), str(self.frameIdTelemBox.value())]
        self.data_list = []

        # save the regular telemetry
        if self.AoLoopDataCheckBox.isChecked():
            self.data_list.append('loop_data')
        # add the ocam frames
        if self.OcamFrameCheckBox.isChecked():
            self.data_list.append('ocam_frames')
        # add the DM channels
        if self.DmChannelsCheckBox.isChecked():
            self.data_list.append('dm_channels')
        # add the WFS intensity
        if self.WfsIntensityCheckBox.isChecked():
            self.data_list.append('wfs_intensity')
                # add the WFS intensity
        if self.CblueFrameCheckBox.isChecked():
            self.data_list.append('cblue_data')

        if self.OrcaFrameCheckBox.isChecked():
            self.data_list.append('orca_data')
        # if self.TelescopeOffsetCheckBox.isChecked():
        #     self.data_list.append('telescope_offset')

        tracking_number = time.strftime("%Y%m%d_%H%M%S", time.localtime())
        print(tracking_number)
        command = [
            "python3",
            os.getenv("DAOROOT") + "/bin/telemetry.py",
            str(self.nbFrameTelemBox.value()),
            str(self.nbFrameCblueBox.value()),
            ",".join(self.data_list),  # Convert list to comma-separated string
            tracking_number,
            ]
        # Create a worker for the subprocess
        worker = SubprocessWorker(command)

        # Connect signals to update the GUI
        worker.signals.finished.connect(self.on_acq_done)
        worker.signals.error.connect(self.on_acq_error)
        worker.signals.path_extracted.connect(
            self.on_path_extracted
        )  # Connect to the slot to handle saving_path

        # Execute
        self.threadpool.start(worker)

        # Optionally update the label to show progress
        self.logTelemLabel.setText('TN: ' +tracking_number)
        # self.frameIdTelemBox.setValue(self.frameIdTelemBox.value() + 1)


    def openBenchTestsWindow(self):
        if self.benchTestsWindow is None:
            self.benchTestsWindow = BenchTest(self)
        self.benchTestsWindow.show()
        self.benchTestsWindow.raise_()
        self.benchTestsWindow.activateWindow()
        self.benchTestsWindow.Start()

    def openCalibrationParametersWindow(self):
        self.calibrationParametersWindow.show()
        self.calibrationParametersWindow.raise_()
        self.calibrationParametersWindow.activateWindow()


    def disp_tt_centering_gain(self):
        value = np.float32(self.tt_centering_gain.value())
        self.shm_TTlp_gain.set_data(self.shm_TTlp_gain.get_data() * 0 + value)
        value = self.shm_TTlp_gain.get_data()[0, 0]
        text = f"TT gain: {value:.2f}"
        display_box_value(self.label_tt_centering_gain, text)

    def disp_tt_centering_leak(self):
        value = np.float32(self.tt_centering_leak.value())
        self.shm_TTlp_leak.set_data(self.shm_TTlp_leak.get_data() * 0 + value)
        value = self.shm_TTlp_leak.get_data()[0, 0]
        text = f"TT leak: {value:.2f}"
        display_box_value(self.label_tt_centering_leak, text)

    # def onTTOffloadToggled(self, checked):
    #     if checked:
    #         self.shm_offload_TT.set_data(self.shm_offload_TT.get_data() * 0 + 1)
    #     else:
    #         self.shm_offload_TT.set_data(self.shm_offload_TT.get_data() * 0)

    # def tt_centering(self):
    #     if self.tt_centering_flag is False:
    #         self.set_tt_centering.setText("Disable TT centering")
    #         self.set_tt_centering.setStyleSheet("background-color: green")
    #         self.tt_centering_flag = True
    #         self.shm_TTlp.set_data(self.shm_TTlp.get_data() * 0 + 1)
    #     else:
    #         self.set_tt_centering.setText("Enable TT centering")
    #         reset_button_color(self.set_tt_centering, self.original_style)
    #         self.tt_centering_flag = False
    #         self.shm_TTlp.set_data(self.shm_TTlp.get_data() * 0)

    def tt_centering(self):
        if self.shm_TTlp.get_data()[0,0] == 0:
            if self.shm_offload_TT.get_data()[0,0] == 1: # disable offload if centering is on
                self.tt_offload()
            self.set_tt_centering.setText("TT centering: ON")
            self.set_tt_centering.setStyleSheet("background-color: green")
            self.shm_TTlp.set_data(self.shm_TTlp.get_data() * 0 + 1)
        else:
            self.set_tt_centering.setText("TT centering: OFF")
            reset_button_color(self.set_tt_centering, self.original_style)
            self.shm_TTlp.set_data(self.shm_TTlp.get_data() * 0)


    def tt_offload(self):
        if self.shm_offload_TT.get_data()[0,0] == 0:
            if self.shm_TTlp.get_data()[0,0] == 1: # disable centering if offload is on
                self.tt_centering()
            self.set_tt_offload.setText("TT offload: ON")
            self.set_tt_offload.setStyleSheet("background-color: green")
            self.shm_offload_TT.set_data(self.shm_offload_TT.get_data() * 0 + 1)
        else:
            self.set_tt_offload.setText("TT offload: OFF")
            reset_button_color(self.set_tt_offload, self.original_style)
            self.shm_offload_TT.set_data(self.shm_offload_TT.get_data() * 0)

    def saveTT(self):
        """Call an external script to save the flat"""
        # Command to call the external script
        command = [
            "python3",
            os.getenv("DAOROOT") + "/bin/saveTTFlat.py"
        ]
        # Create a worker for the subprocess
        worker = SubprocessWorker(command)
        # Execute the worker in the background
        self.threadpool.start(worker)

    def loadTT(self):
        """Call an external script to save the flat"""
        # Command to call the external script
        command = [
            "python3",
            os.getenv("DAOROOT") + "/bin/loadTTFlat.py"
        ]
        # Create a worker for the subprocess
        worker = SubprocessWorker(command)
        # Execute the worker in the background
        self.threadpool.start(worker)

    def resetTT(self):
        """Call an external script to save the flat"""
        # Command to call the external script
        command = [
            "python3",
            os.getenv("DAOROOT") + "/bin/resetTTFlat.py",
            SHM_DM1_CMD,
            "dm468"
        ]
        # Create a worker for the subprocess
        worker = SubprocessWorker(command)
        # Execute the worker in the background
        self.threadpool.start(worker)

    @pyqtSlot(str)
    def on_path_extracted(self, saving_path):
        """Handle the extracted saving path."""
        # Update the label or take any action with the extracted path
        print(f"Data saved in: {saving_path}")
        self.logTelemLabel.setText(f"Data saved in: {saving_path}")

    @pyqtSlot(str)
    def on_acq_bg_done(self, output):
        """Update the GUI when the background acquisition is done."""
        self.logBgLabel.setText("Acquisition Done")
        self.acqBgPercent = 100
        self.progressBgBar.setValue(self.acqBgPercent)
        print(f"Script output: {output}")
        with open(os.getenv("DAODATA") + "/inputs/calibration/interactionMatrix/current_imat.txt") as f:
            im_path = f.read()
            f.close()
        self.currentInteractionMatrixLabel = os.path.splitext(os.path.basename(im_path))[0]
        self.interactionMatrixLabel.setText(self.currentInteractionMatrixLabel)

    @pyqtSlot(str)
    def on_acq_bg_error(self, error):
        """Handle any errors from the background task."""
        self.logBgLabel.setText("Error in Acquisition")
        print(f"Error: {error}")

    def on_change_m2c_done(self, output):
        self.shmLpCmd.set_data(self.shmLpCmd.get_data()*0)
        self.dmV2nm = get_dmV2nm_conversion(self.shmm2c.get_data())

    def on_change_pupils_done(self, output):
        # 1. Save new pupils
        command = [
            "python3",
            os.getenv("DAOROOT") + "/bin/savePupils.py",
            SHM_PYRAMID_VALID_PIXELS,
        ]
        worker = SubprocessWorker(command)
        self.threadpool.start(worker)
        # 2. Renormalize ref frame
        unorm_ref = self.shmOcamRef.get_data() * self.shmOcamRefFlux.get_data()
        flux = np.sum(unorm_ref * self.shmPup.get_data())  
        if flux > 0:
            norm_ref = unorm_ref/flux
        else:
            norm_ref = unorm_ref
        self.shmOcamRef.set_data(self.shmOcamRef.get_data() * 0 + norm_ref.astype(np.float32))
        self.shmOcamRefFlux.set_data(self.shmOcamRefFlux.get_data() * 0 + flux.astype(np.float32))
        # 3. Recompute Rec, where applicable
        if self.currentInteractionMatrixLabel != "": # Recompute Rec
            self.computeCM()

    def on_calib_step_done(self, output):
        self.runNextCalibration()

    def on_calib_bg_done(self, output):
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Background Acquisition Completed")
        msg_box.setText("Please turn ON the laser before proceeding.\n\n"
                        "Click OK when the laser is ON.")
        msg_box.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        msg_box.setDefaultButton(QMessageBox.Ok)

        style_messagebox(msg_box)
        reply = msg_box.exec_()

        self.runNextCalibration()

    def resetBg(self):
        self.shmBg.set_data(self.shmBg.get_data() * 0)

    @pyqtSlot(str)
    def on_acq_done(self, output):
        """Update the GUI when the dataCube acquisition is done."""
        self.logTelemLabel.setText("Telemetry Acquisition Done")
        print(f"Script output: {output}")

    @pyqtSlot(str)
    def on_acq_error(self, error):
        """Handle any errors from the acq task."""
        self.logTelemLabel.setText("Error in telemetry Acquisition")
        print(f"Error: {error}")


def display_box_value(label_id, string_value):
    label_id.setText(string_value)


def reset_button_color(button, original_style):
    button.setStyleSheet(original_style)


if __name__ == "__main__":
    try:
        opts, args = getopt.getopt(sys.argv[1:], "h", ["help"])
    except getopt.GetoptError:
        print("err, usage: EkarusCtrl.py")
        sys.exit(2)
    print(opts)
    print(args)
    for opt, arg in opts:
        if opt == "-h":
            print("EkarusCtrl.py")
            sys.exit()

    app = QApplication([])

    app.setApplicationDisplayName("Ekarus Control")

    # Set application icon if available
    dao_root = os.getenv("DAOROOT")
    if dao_root:
        icon_path = os.path.join(dao_root, "data/Ekarus_Logo_dark.png")
        if os.path.exists(icon_path):
            app.setWindowIcon(QIcon(icon_path))

    papyCtrl = EkarusCtrlApp()
    papyCtrl.setWindowTitle("Ekarus Control")
    papyCtrl.show()
    papyCtrl.Start()
    sys.exit(app.exec_())