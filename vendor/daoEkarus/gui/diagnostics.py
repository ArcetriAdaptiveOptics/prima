#!/usr/bin/env python3

from GUIUtils import *
from daoEkarusShmNames import *

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
Ui_MainWindow, QMainWindow = loadUiType(os.path.join(path, "diagnostics.ui"))


class Diagnostics(QMainWindow, Ui_MainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setupUi(self)
        self.threadpool = QThreadPool()

        self.setWindowModality(QtCore.Qt.NonModal)
        self.setWindowTitle("Diagnostics")
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.WindowStaysOnTopHint)

        # Create QT timer to update display
        self.timer = QtCore.QTimer(self)
        # Throw event timeout with an interval of 50 milliseconds
        self.timer.setInterval(50)
        # each time timer counts done call self.Update
        self.timer.timeout.connect(self.Update)

        self.acqDMDataButton.clicked.connect(self.acqDMData)
        self.block_acqDMDataButton = False

        self.map = dao.shm("/tmp/dm241Map.im.shm")
        self.residual_wavefront_shm = dao.shm("/tmp/papyrus_res_wf.im.shm")
        self.current_dm_shape_shm = dao.shm("/tmp/dmCmd.im.shm")
        self.current_dm_flat_shm = dao.shm("/tmp/dmCmd00.im.shm")
        self.current_dm_closedloop_shm = dao.shm("/tmp/dmCmd01.im.shm")
        self.current_dm_NCPA_shm = dao.shm("/tmp/dmCmdOffset.im.shm")
        self.papyrus_modes_shm = dao.shm("/tmp/papyrus_modes.im.shm")
        self.dm_coherence_shm = dao.shm(
            "/tmp/dm_coherences.im.shm", np.zeros((1, 1)).astype(np.float32)
        )
        self.dm_r0_estimation_shm = dao.shm(
            "/tmp/dm_r0_estimation.im.shm", np.zeros((1, 1)).astype(np.float32)
        )
        self.diagnostics_progress_shm = dao.shm(
            "/tmp/diagnostics_Percent.im.shm", np.zeros((1, 1)).astype(np.uint32)
        )

        self.papyrus_modes_buffer = np.zeros(
            (50, self.papyrus_modes_shm.get_data().shape[0])
        )

        self.dmM = np.copy(self.map.get_data()).astype(np.float32)
        self.dmFlat = np.copy(self.map.get_data()).astype(np.float32)
        self.dmClosedLoop = np.copy(self.map.get_data()).astype(np.float32)
        self.dmNCPA = np.copy(self.map.get_data()).astype(np.float32)
        self.res_wfs = np.copy(self.map.get_data()).astype(np.float32)

        self.vb1 = pg.ViewBox()
        self.residualWavefrontView.setCentralItem(self.vb1)
        self.img_res_wfs = pg.ImageItem(border=None)
        self.vb1.addItem(self.img_res_wfs)
        self.vb1.setAspectLocked(True)
        self.img_res_wfs.setImage(self.res_wfs)

        self.vb2 = pg.ViewBox()
        self.dmView.setCentralItem(self.vb2)
        self.img_dmView = pg.ImageItem(border=None)
        self.vb2.addItem(self.img_dmView)
        self.vb2.setAspectLocked(True)
        self.img_dmView.setImage(self.dmM)

        self.vb3 = pg.ViewBox()
        self.dmViewFlat.setCentralItem(self.vb3)
        self.img_dmViewFlat = pg.ImageItem(border=None)
        self.vb3.addItem(self.img_dmViewFlat)
        self.vb3.setAspectLocked(True)
        self.img_dmViewFlat.setImage(self.dmM)

        self.vb4 = pg.ViewBox()
        self.dmViewClosedLoop.setCentralItem(self.vb4)
        self.img_dmViewClosedLoop = pg.ImageItem(border=None)
        self.vb4.addItem(self.img_dmViewClosedLoop)
        self.vb4.setAspectLocked(True)
        self.img_dmViewClosedLoop.setImage(self.dmM)

        self.vb5 = pg.ViewBox()
        self.dmViewNCPA.setCentralItem(self.vb5)
        self.img_dmViewNCPA = pg.ImageItem(border=None)
        self.vb5.addItem(self.img_dmViewNCPA)
        self.vb5.setAspectLocked(True)
        self.img_dmViewNCPA.setImage(self.dmM)

        self.modeHistLayout = QVBoxLayout(
            self.modeHist
        )  # Assuming modeHist is QWidget now
        self.modeHistCanvas = MplHistCanvas(self, width=5, height=4, dpi=100)
        self.modeHistLayout.addWidget(self.modeHistCanvas)
        self.modeHistLayout.setContentsMargins(0, 0, 0, 0)
        self.modeHistLayout.setSpacing(0)
        self.bars = self.modeHistCanvas.axes.bar(
            np.arange(self.papyrus_modes_shm.get_data().shape[0]),
            self.papyrus_modes_shm.get_data().flatten(),
            color="blue",
        )
        self.modeHistCanvas.axes.set_ylim([-0.1, 0.1])

    def Start(self):
        """Start timer"""
        self.timer.start()

    def Stop(self):
        """Stop timer"""
        self.timer.stop()

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

    @QtCore.pyqtSlot()
    def Update(self):
        """Update the GUI"""
        self.res_wfs[self.map.get_data() == 1] = self.residual_wavefront_shm.get_data()[
            :, 0
        ]
        self.img_res_wfs.setImage(self.res_wfs)
        wavefrontRMSResidual = (
            np.std(self.residual_wavefront_shm.get_data()[:, 0].flatten()) * 7591.0
        )
        self.residualWavefrontRMSLabel.setText(f"{wavefrontRMSResidual:.1f} nm")

        dm_shape_no_flat = np.clip(
            self.current_dm_shape_shm.get_data()[:, 0]
            - self.current_dm_flat_shm.get_data()[:, 0],
            -1.0,
            1.0,
        )
        self.dmM[self.map.get_data() == 1] = dm_shape_no_flat
        self.img_dmView.setImage(self.dmM)

        dmShapeRMS = np.std(dm_shape_no_flat) * 7591.0
        self.dmShapeRMSLabel.setText(f"{dmShapeRMS:.1f} nm")

        self.dmFlat[self.map.get_data() == 1] = self.current_dm_flat_shm.get_data()[
            :, 0
        ]
        self.img_dmViewFlat.setImage(self.dmFlat)

        self.dmClosedLoop[self.map.get_data() == 1] = (
            self.current_dm_closedloop_shm.get_data()[:, 0]
        )
        self.img_dmViewClosedLoop.setImage(self.dmClosedLoop)

        self.dmNCPA[self.map.get_data() == 1] = self.current_dm_NCPA_shm.get_data()[
            :, 0
        ]
        self.img_dmViewNCPA.setImage(self.dmNCPA)

        np.roll(self.papyrus_modes_buffer, 1, axis=0)
        current_modes = self.papyrus_modes_shm.get_data().flatten()
        self.papyrus_modes_buffer[0] = current_modes
        if self.modesRollingCheckBox.isChecked():
            data = self.papyrus_modes_buffer.mean(axis=0)
        else:
            data = current_modes

        for bar, h in zip(self.bars, data):
            bar.set_height(h)
        self.modeHistCanvas.axes.relim()
        self.modeHistCanvas.axes.autoscale_view()
        self.modeHistCanvas.draw()

        self.progressDiagBar.setValue(self.diagnostics_progress_shm.get_data()[0, 0])

    def closeEvent(self, event):
        # Inform the parent that this window is closing
        self.Stop()
        if self.parent:
            self.parent.diagnosticsWindow = None
        super().closeEvent(event)

    def acqDMData(self):
        if not self.block_acqDMDataButton:
            self.block_acqDMDataButton = True
            """Call an external script to close the loop"""
            # Command to call the external script
            command = [
                "python3",
                os.getenv("DAOROOT") + "/bin/atm_params_estimation.py",
            ]
            # Create a worker for the subprocess
            worker = SubprocessWorker(command)
            # Connect signals to update the GUI
            worker.signals.finished.connect(self.on_acq_dm_done)
            worker.signals.error.connect(self.on_acq_dm_error)
            # Execute the worker in the background
            self.threadpool.start(worker)

    @pyqtSlot(str)
    def on_acq_dm_done(self, output):
        """Update the GUI when the DM data acquisition is done."""
        self.block_acqDMDataButton = False
        estimated_tau = self.dm_coherence_shm.get_data()[:, 0]
        estimated_r0 = self.dm_r0_estimation_shm.get_data()[0, 0]
        estimated_windspeed = (
            0.314 * estimated_r0 / estimated_tau if estimated_tau > 1e-6 else 0
        )
        self.avgCoherenceTimeLabel.setText(f"{estimated_tau * 1000:.1f} ms")
        self.estimatedr0Label.setText(f"{estimated_r0 * 100:.1f} cm")
        self.avgWindSpeedLabel.setText(f"{estimated_windspeed:.1f} m/s")

        self.progressDiagBar.setValue(100)
        print(f"Script output: {output}")

    @pyqtSlot(str)
    def on_acq_dm_error(self, error):
        """Handle any errors from the background task."""
        self.block_acqDMDataButton = False
        print(f"Error: {error}")


if __name__ == "__main__":
    app = QApplication([])
    app.setApplicationDisplayName("Diagnostics")
    main = Diagnostics()
    main.setWindowTitle("Diagnostics")
    main.show()
    main.Start()
    sys.exit(app.exec_())
