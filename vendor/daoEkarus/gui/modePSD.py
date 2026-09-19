#!/usr/bin/env python3
"""Welch PSD and cumulative PSD display for Ekarus modal telemetry."""

from scipy.signal import welch

from GUIUtils import *
from GUIUtils import _style_mpl_axes
from daoEkarusShmNames import *
from modalPlot import NSAMPLES, ShmReader


path = os.getenv("DAOROOT") + "/data/"
Ui_MainWindow, QMainWindow = loadUiType(os.path.join(path, "modePSD.ui"))


class ModePSD(QMainWindow, Ui_MainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setupUi(self)
        self.setWindowTitle("Mode PSD")
        self.setWindowModality(QtCore.Qt.NonModal)
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.WindowStaysOnTopHint)
        self.delayInMs = 1.1
        self.delayInFrames = 1 # Initialized, updated afterwwards

        self.canvas = MplCanvas(self, width=8, height=5, dpi=100)
        self.canvas.fig.clear()
        self.axes = self.canvas.fig.add_subplot(111)
        mount_mpl_canvas(self.plotView, self.canvas, parent=self, toolbar=False)

        with open(os.getenv("DAODATA") + "/inputs/dm468/current_m2c.txt") as handle:
            m2c_path = handle.read().strip()
        tmp_m2c = np.load(m2c_path)
        self.c2m = dao.shm(SHM_DM1_C2M).get_data()[:tmp_m2c.shape[1], :]
        self.voltage2Nm = get_dmV2nm_conversion(tmp_m2c)

        self.reader = ShmReader(nsamples=NSAMPLES, parent=self)
        self.reader.error.connect(self.onError)
        self.reader.start()

        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(2000)
        self.timer.timeout.connect(self.Update)

        self.modeBox.valueChanged.connect(self._schedule_update)
        self.modeListEdit.textChanged.connect(self._schedule_update)
        self.plotModeCombo.currentTextChanged.connect(self._on_plot_mode_changed)
        self.showDmCumulative.toggled.connect(self.Update)
        self.windowComboBox.currentTextChanged.connect(self.Update)

        self._set_mode_range(tmp_m2c.shape[1])
        self._on_plot_mode_changed(self.plotModeCombo.currentText())

    def _set_mode_range(self, mode_count):
        self.modeBox.setRange(0, max(0, mode_count - 1))
        self.modeBox.setValue(0)
        self.modeListEdit.setText("0")

    def Start(self):
        self.timer.start()
        self.Update()

    def Stop(self):
        self.timer.stop()

    def _schedule_update(self):
        self.Update()

    def _on_plot_mode_changed(self, mode):
        cumulative = mode == "Cumulative PSD"
        self.modeLabel.setVisible(not cumulative)
        self.modeBox.setVisible(not cumulative)
        self.modeListLabel.setVisible(cumulative)
        self.modeListEdit.setVisible(cumulative)
        self.showDmCumulative.setVisible(cumulative)
        self.Update()

    def _parse_mode_list(self):
        text = self.modeListEdit.text().strip()
        if not text:
            return [self.modeBox.value()]
        modes = set()
        try:
            for item in text.split(","):
                item = item.strip()
                if not item:
                    continue
                if "-" in item:
                    first, last = (int(value.strip()) for value in item.split("-", 1))
                    modes.update(range(min(first, last), max(first, last) + 1))
                else:
                    modes.add(int(item))
        except ValueError:
            return []
        max_mode = len(self.voltage2Nm) - 1
        return sorted(mode for mode in modes if 0 <= mode <= max_mode)

    def _get_data(self):
        window = int(self.windowComboBox.currentText())
        dm, md, n = self.reader.snapshot(window=window)
        if n < 4:
            return None, None, None, n
        dm_modes = (dm @ self.c2m.T) * self.voltage2Nm[:self.c2m.shape[0]]
        residual_modes = md[:, :len(self.voltage2Nm)] * self.voltage2Nm
        delayed_md = self._interpolate(residual_modes, self.delayInFrames)
        aligned_dm = dm_modes[:len(delayed_md)]
        pol_modes = aligned_dm + delayed_md[:,:aligned_dm.shape[1]]
        return dm_modes, residual_modes, pol_modes, n

    @staticmethod
    def _interpolate(data, shift: float):
        """Return data delayed by a possibly fractional number of frames."""
        if data.shape[0] == 0:
            return data
        shift = min(max(0.0, float(shift)), data.shape[0] - 1)
        lower = int(np.floor(shift))
        fraction = shift - lower
        if lower >= data.shape[0]:
            return data[:0]
        end = data.shape[0] - lower
        current = data[lower:lower + end]
        if fraction == 0.0 or lower == 0:
            return current
        previous = data[lower - 1:lower - 1 + end]
        return (1.0 - fraction) * current + fraction * previous

    @staticmethod
    def _welch(data, fs):
        nperseg = min(1024, data.size)
        return welch(data, fs=fs, nperseg=nperseg, detrend="constant")

    @staticmethod
    def _cumulative(psd, df):
        return np.sqrt(np.maximum(np.cumsum(psd) * df - psd[0] * df, 0.0))

    def Update(self):
        dm_modes, residual_modes, pol_modes, n = self._get_data()
        if dm_modes is None:
            self.statusLabel.setText(f"Buffering... {n} frames")
            return

        fs = self.reader.sampling_rate()
        self.delayInFrames = self.delayInMs*1e-3*fs
        mode = self.modeBox.value()
        if self.plotModeCombo.currentText() == "PSD":
            # dm_freq, dm_psd = self._welch(dm_modes[:, mode], fs)
            dm_freq, dm_psd = self._welch(pol_modes[:, mode], fs)
            residual_freq, residual_psd = self._welch(residual_modes[:, mode], fs)
            self.axes.clear()
            self.axes.loglog(dm_freq[1:], dm_psd[1:], color="c", label="POL commands")
            self.axes.loglog(residual_freq[1:], residual_psd[1:], color="y", label="Residual")
            self.axes.set_ylabel("PSD [nm^2/Hz]")
            self.axes.set_xlabel("Frequency [Hz]")
            tot_dm = np.sqrt(np.sum(dm_psd[1:])*(dm_freq[1]-dm_freq[0]))
            tot_res = np.sqrt(np.sum(residual_psd[1:])*(residual_freq[1]-residual_freq[0]))
            self.axes.set_title(f"Mode {mode} PSD\nPOL commands {tot_dm:1.0f}nm | Measured residual {tot_res:1.0f}nm")
        else:
            modes = self._parse_mode_list()
            self.axes.clear()
            if not modes:
                self.statusLabel.setText("Enter modes such as 0-5,8")
                self.canvas.draw()
                return
            for j,mode_id in enumerate(modes):
                frequency, psd = self._welch(residual_modes[:, mode_id], fs)
                self.axes.semilogx(
                    frequency,
                    self._cumulative(psd, frequency[1] - frequency[0]),
                    label=f"Mode {mode_id}",
                    c = f'C{j}',
                )
                if self.showDmCumulative.isChecked():
                    # frequency, psd = self._welch(dm_modes[:, mode_id], fs)
                    frequency, psd = self._welch(pol_modes[:, mode_id], fs)
                    self.axes.semilogx(
                        frequency,
                        self._cumulative(psd, frequency[1] - frequency[0]),
                        linestyle="--",
                        # label=f"DM mode {mode_id}",
                        c = f'C{j}',
                    )
            self.axes.set_ylabel("Cumulative PSD [nm]")
            self.axes.set_xlabel("Frequency [Hz]")
            self.axes.set_title("Cumulative modal PSD")

        self.axes.grid(True, which="both", alpha=0.3)
        self.axes.legend()
        _style_mpl_axes(self.axes)
        self.canvas.fig.tight_layout()
        self.canvas.draw()
        self.statusLabel.setText(f"fs = {fs:.1f} Hz | {n} frames")

    @QtCore.pyqtSlot(str)
    def onError(self, message):
        self.statusLabel.setText(f"Error: {message}")

    def closeEvent(self, event):
        self.Stop()
        self.reader.stop()
        if self.parent:
            self.parent.modePSDWindow = None
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication([])
    window = ModePSD()
    window.show()
    window.Start()
    sys.exit(app.exec_())
