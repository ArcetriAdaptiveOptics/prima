"""
calibrationParameters.py

Window exposing the Interaction Matrix Acquisition Parameters defined in
$DAOROOT/data/calibrationParameters.ui

Widgets available from the .ui file
-----------------------------------
    amplitudeIntMatBox       QDoubleSpinBox  modes amplitude   [0.000 .. 0.100], step 0.001
    nFrameAverageIntMatBox   QSpinBox        nFrameAverage     [1 .. 500]
    nAverageIntMatBox        QSpinBox        nRepetition       [1 .. 500]
    modalScalingCheckBox     QCheckBox       modal amplitude scaling (bool)

The parent window is expected to read the parameters through get_parameters(),
or to connect to the parametersChanged signal to be notified when the user
explicitly saves changes.
"""

import os
import sys
import shutil
import platform

from GUIUtils import *
from daoEkarusShmNames import *


# ---------------------------------------------------------------------------
# Terminal detection (used by _run_script)
# ---------------------------------------------------------------------------
if platform.system() == "Darwin":
    # macOS: launch via osascript in Terminal
    console = [
        "osascript",
        "-e",
        f'tell application "Terminal" to do script \"{sys.executable} \"',
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
Ui_MainWindow, QMainWindow = loadUiType(os.path.join(path, "calibrationParameters.ui"))


class calibrationParameters(QMainWindow, Ui_MainWindow):
    # Emitted when the user explicitly saves the parameter changes.
    # Payload: dict as returned by get_parameters()
    parametersChanged = QtCore.pyqtSignal(dict)

    # ----------------------------------------------------------------- init
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setupUi(self)
        self.threadpool = QThreadPool()  # Create a thread pool

        self.setWindowModality(QtCore.Qt.NonModal)
        self.setWindowTitle("Calibration Parameters")
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.WindowStaysOnTopHint)

        # ---- widget setup -------------------------------------------------
        # Defaults are already in the .ui, this only makes them explicit and
        # keeps the code working if the .ui is regenerated.
        self.amplitudeIntMatBox.setDecimals(3)
        self.amplitudeIntMatBox.setRange(0.0, 0.1)
        self.amplitudeIntMatBox.setSingleStep(0.001)

        self.nFrameAverageIntMatBox.setRange(1, 500)
        self.nAverageIntMatBox.setRange(1, 500)

        # ---- signals ------------------------------------------------------
        self.amplitudeIntMatBox.valueChanged.connect(self._on_parameter_changed)
        self.nFrameAverageIntMatBox.valueChanged.connect(self._on_parameter_changed)
        self.nAverageIntMatBox.valueChanged.connect(self._on_parameter_changed)
        self.modalScalingCheckBox.stateChanged.connect(self._on_parameter_changed)
        self.saveButton.clicked.connect(self.save_parameters)
        self.cancelButton.clicked.connect(self.cancel_parameters)

        self._saved_parameters = self.get_parameters()

        # Create QT timer to update display
        self.timer = QtCore.QTimer(self)
        # Throw event timeout with an interval of 50 milliseconds
        self.timer.setInterval(50)
        # each time timer counts done call self.Update
        self.timer.timeout.connect(self.Update)

    # ------------------------------------------------------------- timer
    def Start(self):
        """Start timer"""
        self.timer.start()

    def Stop(self):
        """Stop timer"""
        self.timer.stop()

    @QtCore.pyqtSlot()
    def Update(self):
        """Periodic refresh.

        Nothing in this panel is driven by shared memory, so there is no
        display to refresh. Kept for symmetry with the other panels and as a
        hook if a status readout is added later.
        """
        pass

    # -------------------------------------------------------- accessors
    def get_amplitude(self):
        """Modes amplitude [a.u.] -> float"""
        return self.amplitudeIntMatBox.value()

    def get_n_frame_average(self):
        """Number of frames averaged per push/pull -> int"""
        return self.nFrameAverageIntMatBox.value()

    def get_n_repetition(self):
        """Number of repetitions of the full modal sequence -> int"""
        return self.nAverageIntMatBox.value()

    def get_modal_scaling(self):
        """Modal amplitude scaling enabled -> bool"""
        return self.modalScalingCheckBox.isChecked()

    def get_parameters(self):
        """Return every acquisition parameter in a single dict."""
        return {
            "amplitude": self.get_amplitude(),
            "nFrameAverage": self.get_n_frame_average(),
            "nRepetition": self.get_n_repetition(),
            "modalScaling": self.get_modal_scaling(),
        }

    # ---------------------------------------------------------- mutators
    def set_parameters(
        self,
        amplitude=None,
        nFrameAverage=None,
        nRepetition=None,
        modalScaling=None,
    ):
        """Set any subset of the parameters programmatically.

        Signals are blocked while the widgets are updated so the controls can
        be restored without treating each value as a separate user edit.
        """
        widgets = (
            self.amplitudeIntMatBox,
            self.nFrameAverageIntMatBox,
            self.nAverageIntMatBox,
            self.modalScalingCheckBox,
        )
        for w in widgets:
            w.blockSignals(True)

        try:
            if amplitude is not None:
                self.amplitudeIntMatBox.setValue(float(amplitude))
            if nFrameAverage is not None:
                self.nFrameAverageIntMatBox.setValue(int(nFrameAverage))
            if nRepetition is not None:
                self.nAverageIntMatBox.setValue(int(nRepetition))
            if modalScaling is not None:
                self.modalScalingCheckBox.setChecked(bool(modalScaling))
        finally:
            for w in widgets:
                w.blockSignals(False)

        self._on_parameter_changed()

    # ------------------------------------------------------------- slots
    @QtCore.pyqtSlot()
    def _on_parameter_changed(self, *args):
        """Keep widget edits local until the user explicitly saves them.

        The *args swallows the int/float payload sent by valueChanged and
        stateChanged so the same slot can serve all four widgets.
        """
        pass

    @QtCore.pyqtSlot()
    def save_parameters(self):
        """Commit the current widget values and notify the parent."""
        self._saved_parameters = self.get_parameters()
        self.parametersChanged.emit(self._saved_parameters.copy())
        self.hide()

    @QtCore.pyqtSlot()
    def cancel_parameters(self):
        """Restore the values from the last explicit save."""
        self.set_parameters(**self._saved_parameters)
        self.hide()

    # ------------------------------------------------------------- close
    def closeEvent(self, event):
        self.Stop()
        self.cancel_parameters()
        event.ignore()   # keep the widget alive, just hide it
        self.hide()

    # ------------------------------------------------------- subprocess
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

    def run_interaction_matrix(self, script_name="daoIntMatAcquisition.py"):
        """Example launcher passing the current parameters to an external script."""
        p = self.get_parameters()
        args = [
            "--amplitude", str(p["amplitude"]),
            "--nFrameAverage", str(p["nFrameAverage"]),
            "--nRepetition", str(p["nRepetition"]),
        ]
        if p["modalScaling"]:
            args.append("--modalScaling")
        self._run_script(script_name, args)


if __name__ == "__main__":
    app = QApplication([])
    app.setApplicationDisplayName("Calibration Parameters")
    main = calibrationParameters()
    main.setWindowTitle("Calibration Parameters")
    main.parametersChanged.connect(lambda p: print(p))
    main.show()
    main.Start()
    sys.exit(app.exec_())