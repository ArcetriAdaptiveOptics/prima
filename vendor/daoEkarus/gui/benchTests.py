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
Ui_MainWindow, QMainWindow = loadUiType(os.path.join(path, "benchTests.ui"))


class BenchTest(QMainWindow, Ui_MainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setupUi(self)
        self.threadpool = QThreadPool()  # Create a thread pool

        self.atmStop = dao.shm(SHM_DM1_ATM_STOP)
        self.atmSeeing = dao.shm(SHM_DM1_ATM_SEEING)
        self.atmSpeed = dao.shm(SHM_DM1_ATM_WINDSPEED)

        self.setWindowModality(QtCore.Qt.NonModal)
        self.setWindowTitle("Bench Tests")
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.WindowStaysOnTopHint)

        # Create QT timer to update display
        self.timer = QtCore.QTimer(self)
        # Throw event timeout with an interval of 50 milliseconds
        self.timer.setInterval(50)
        # each time timer counts done call self.Update
        self.timer.timeout.connect(self.Update)

        self.applyDmOffsetButton.clicked.connect(self.applyDmOffset)
        self.resetDmOffsetButton.clicked.connect(self.resetDmOffset)
        self.applyKolmoTurbButton.clicked.connect(self.applyKolmoTurb)
        self.stopKolmoTurbButton.clicked.connect(self.stopKolmoTurb)
        self.seeingSlider.valueChanged.connect(self.setSeeing)
        self.windspeedSlider.valueChanged.connect(self.setWindSpeed)
        self.rtfMeasurementButton.clicked.connect(self.measureEtf)

    def Start(self):
        """Start timer"""
        self.timer.start()

    def Stop(self):
        """Stop timer"""
        self.timer.stop()

    @QtCore.pyqtSlot()
    def Update(self):
        """Update the GUI"""
        self.atmSeeingLabel.setText(f'{self.atmSeeing.get_data()[0,0]:.1f} "')
        self.atmWindSpeedLabel.setText(
            f"{self.atmSpeed.get_data()[0,0]:.1f} m/s"
        )

    def closeEvent(self, event):
        # Inform the parent that this window is closing
        self.atmStop.set_data(self.atmStop.get_data() * 0 + 1)
        if self.parent:
            self.parent.benchTestsWindow = None
        self.Stop
        super().closeEvent(event)

    def applyDmOffset(self):
        """Call an external script to apply dm offset"""
        # Command to call the external script
        command = [
            "python3",
            os.getenv("DAOROOT") + "/bin/applyDmOffset.py",
            str(self.numberModeOffsetBox.value()),
            str(self.amplitudeModeOffsetBox.value()),
            self.basisComboBox.currentText(),
        ]
        # Create a worker for the subprocess
        worker = SubprocessWorker(command)
        # Execute the worker in the background
        self.threadpool.start(worker)

    def measureEtf(self):
        """Call an external script to measure the RTF of the system"""
        # Command to call the external script
        loop_frequency = dao.shm(SHM_OCAM_FPS).get_data()[0][0]

        command = [
                "python3",
                os.getenv("DAOROOT") + "/bin/ekarusEtf.py",
                str(self.numberModeOffsetBox.value()),
                str(self.amplitudeModeOffsetBox.value()),
                str(loop_frequency)
                    ]
        # Create a worker for the subprocess
        worker = SubprocessWorker(command)
        # Execute the worker in the background
        self.threadpool.start(worker)

    def resetDmOffset(self):
        """Call an external script to apply dm offset"""
        # Command to call the external script
        command = ["python3", os.getenv("DAOROOT") + "/bin/resetDmOffset.py"]
        # Create a worker for the subprocess
        worker = SubprocessWorker(command)
        # Execute the worker in the background
        self.threadpool.start(worker)
        # print("resetDmOffset")

    def applyKolmoTurb(self):
        """Call an external script to apply dm offset"""
        # Command to call the external script
        command = ["python3", os.getenv("DAOROOT") + "/bin/applyKolmoTurb.py"]
        # Create a worker for the subprocess
        worker = SubprocessWorker(command)
        # Execute the worker in the background
        self.threadpool.start(worker)

    def stopKolmoTurb(self):
        self.atmStop.set_data(self.atmStop.get_data() * 0 + 1)

    def setSeeing(self, value):
        self.atmSeeing.set_data(self.atmSeeing.get_data() * 0 + value / 10.0)

    def setWindSpeed(self, value):
        self.atmSpeed.set_data(self.atmSpeed.get_data() * 0 + value / 1000 * 5.)

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


if __name__ == "__main__":
    app = QApplication([])
    app.setApplicationDisplayName("Bench Tests")
    main = BenchTest()
    main.setWindowTitle("Bench Tests")
    main.show()
    main.Start()
    sys.exit(app.exec_())
