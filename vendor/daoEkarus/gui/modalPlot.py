#!/usr/bin/env python3
"""Modal plot window: temporal RMS per mode, read from dao shared memory.

The DM command channel is projected onto the modal basis with c2m and
compared against the reconstructed modal coefficients.

Acquisition runs in a background QThread that blocks on the shm semaphore at
the RTC loop rate; the GUI refreshes at 1 Hz from a ring buffer snapshot.
"""

from GUIUtils import *
from daoEkarusShmNames import *
from astropy.io import fits

# Semaphore index to wait on. Pick one no other consumer is using; the
# telemetry script uses 8, so use a different one to avoid stealing posts.
SEM_NB = 5

# Ring buffer depth in frames. At ~1 kHz this is ~8 s of history; the RMS is
# computed over the most recent `window` frames of it.
NSAMPLES = 8192

path = os.getenv("DAOROOT") + "/data/"
Ui_MainWindow, QMainWindow = loadUiType(os.path.join(path, "modalPlot.ui"))


class ShmReader(QtCore.QThread):
    """Blocks on the DM command shm and accumulates full frame vectors.

    Buffers are 2-D, (nsamples, nelements), so the GUI can take a temporal
    std per actuator / per mode. Buffers are allocated on the first frame,
    once the shm shapes are known.
    """

    error = QtCore.pyqtSignal(str)

    def __init__(self, nsamples=NSAMPLES, parent=None):
        super().__init__(parent)
        self.nsamples = nsamples
        self._running = False

        # Ring buffers + write index, guarded by a mutex because the GUI
        # thread snapshots them.
        self._mutex = QtCore.QMutex()
        self._dm_buf = None
        self._mode_buf = None
        self._idx = 0
        self._filled = 0

        self.dmCmd = None
        self.modes = None
        self.fpsShm = None

        self.diameter = 1.82/0.95 # ALPAO on-sky diameter, for seeing estimation

    def stop(self):
        self._running = False
        self.wait(2000)

    def snapshot(self, window=None):
        """Return (dm, modes, n) with the most recent `window` frames.

        Each array is (n, nelements) in chronological order.
        """
        self._mutex.lock()
        try:
            n = self._filled
            if n == 0 or self._dm_buf is None:
                return None, None, 0

            if n < self.nsamples:
                dm = self._dm_buf[:n]
                md = self._mode_buf[:n]
            else:
                dm = np.concatenate((self._dm_buf[self._idx:],
                                     self._dm_buf[:self._idx]))
                md = np.concatenate((self._mode_buf[self._idx:],
                                     self._mode_buf[:self._idx]))

            if window is not None and window < n:
                dm = dm[-window:]
                md = md[-window:]
                n = window

            return dm.copy(), md.copy(), n
        finally:
            self._mutex.unlock()

    def sampling_rate(self, default=1000.0):
        """Loop rate in Hz, read from the OCAM fps shm."""
        try:
            fps = float(self.fpsShm.get_data()[0, 0])
            return fps if fps > 0 else default
        except Exception:
            return default

    def _allocate(self, n_dm, n_mode):
        self._dm_buf = np.zeros((self.nsamples, n_dm), dtype=np.float64)
        self._mode_buf = np.zeros((self.nsamples, n_mode), dtype=np.float64)
        self._idx = 0
        self._filled = 0

    def run(self):
        try:
            self.dmCmd = dao.shm(SHM_DM1_CHANNEL_1)
            self.modes = dao.shm(SHM_WFS1_RECONSTRUCTED_MODES_WITH_GAIN)
            self.fpsShm = dao.shm(SHM_OCAM_FPS)
        except Exception as e:
            self.error.emit(f"Could not open shared memory: {e}")
            return

        self._running = True
        while self._running:
            try:
                # Blocks until the RTC posts a new DM command.
                dm = self.dmCmd.get_data(check=True, semNb=SEM_NB)
                md = self.modes.get_data()
            except Exception as e:
                self.error.emit(str(e))
                return

            # Both shm are (n, 1) column vectors; flatten to 1-D.
            dm = np.asarray(dm, dtype=np.float64).ravel()
            md = np.asarray(md, dtype=np.float64).ravel()

            self._mutex.lock()
            try:
                if self._dm_buf is None:
                    self._allocate(dm.size, md.size)
                self._dm_buf[self._idx] = dm
                self._mode_buf[self._idx] = md
                self._idx = (self._idx + 1) % self.nsamples
                self._filled = min(self._filled + 1, self.nsamples)
            finally:
                self._mutex.unlock()


class ModalPlotView:
    """Fills a .ui placeholder widget with a log-log pyqtgraph plot.

    Same spirit as DmShapeView / TtScatterView in GUIUtils: construction and
    per-frame refresh in one place, taking plain arrays so the controller
    keeps ownership of the shm reads.
    """

    def __init__(self, placeholder, parent=None):
        self.glw = pg.GraphicsLayoutWidget()
        self.glw.setBackground(THEME_BG)
        mount_mpl_canvas(placeholder, self.glw, parent=parent, toolbar=False)

        self.plot = self.glw.addPlot()
        self.plot.setLogMode(x=True, y=True)
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.plot.setLabels(left="RMS [nm]", bottom="Mode index")
        self.plot.addLegend()
        for name in ("left", "bottom"):
            axis = self.plot.getAxis(name)
            axis.setPen(pg.mkPen(THEME_FG))
            axis.setTextPen(pg.mkPen(THEME_FG))

        self.dmCurve = self.plot.plot(pen=pg.mkPen(color="c", width=2),
                                      name="DM commands")
        self.modeCurve = self.plot.plot(pen=pg.mkPen(color="y", width=2),
                                        name="Rec modes")
        self.polModesCurve = self.plot.plot(pen=pg.mkPen(color="g", width=2),
                                        name="POL modes")
        self.plot.getAxis("bottom").setStyle(tickTextOffset=8)

    @staticmethod
    def _set_curve(curve, x, y, visible):
        if not visible or y is None:
            curve.setData([], [])
            return
        # setLogMode takes the log itself, so feed linear values and strip
        # non-positive points that would otherwise vanish.
        good = ~np.isnan(y) # good = y > 0
        curve.setData(x[good], y[good])

    def update_curves(self, dm_rms, md_rms, pol_rms, show_dm=True, show_modes=True, show_pol=True):
        dm_x = np.arange(1, dm_rms.size + 1)
        md_x = np.arange(1, md_rms.size + 1)
        pol_x = np.arange(1, pol_rms.size + 1)
        self._set_curve(self.dmCurve, dm_x, dm_rms, show_dm)
        self._set_curve(self.modeCurve, md_x, md_rms, show_modes)
        self._set_curve(self.polModesCurve, pol_x, pol_rms, show_pol)


class ModalPlot(QMainWindow, Ui_MainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setupUi(self)

        self.setWindowModality(QtCore.Qt.NonModal)
        self.setWindowTitle("Modal Plot")
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.WindowStaysOnTopHint)

        # Command-to-mode projection matrix, truncated to the number of modes
        # in the current m2c.
        with open(os.getenv("DAODATA") + "/inputs/dm468/current_m2c.txt") as f:
            m2c_path = f.read().strip()
        tmp_m2c = np.load(m2c_path)
        self.c2m = dao.shm(SHM_DM1_C2M).get_data()[:tmp_m2c.shape[1], :]

        # Plot mounted into the .ui placeholder
        self.view = ModalPlotView(self.modalView, parent=self)

        # Create QT timer to update display
        self.timer = QtCore.QTimer(self)
        # Throw event timeout with an interval of 1000 milliseconds
        self.timer.setInterval(1000)
        # each time timer counts done call self.Update
        self.timer.timeout.connect(self.Update)

        self.dmCheckBox.stateChanged.connect(self.Update)
        self.modeCheckBox.stateChanged.connect(self.Update)
        self.polModesCheckBox.stateChanged.connect(self.Update)
        self.windowComboBox.currentTextChanged.connect(self.Update)

        # Acquisition thread
        self.reader = ShmReader(nsamples=NSAMPLES, parent=self)
        self.reader.error.connect(self.onError)
        self.reader.start()
        self.voltage2Nm = get_dmV2nm_conversion(tmp_m2c)
        self.delayInFrames = self._delay_ms_to_frames(self.delayInMsBox.value())
        self.delayInMsBox.valueChanged.connect(self._set_delay)

    def Start(self):
        """Start timer"""
        self.timer.start()

    def Stop(self):
        """Stop timer"""
        self.timer.stop()

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

    @QtCore.pyqtSlot(float)
    def _set_delay(self, delay):
        self.delayInFrames = self._delay_ms_to_frames(delay)
        self.Update()

    def _delay_ms_to_frames(self, delay_ms):
        return float(delay_ms) * self.reader.sampling_rate() / 1000.0

    def _set_mode_ticks(self, mode_count):
        axis = self.view.plot.getAxis("bottom")
        if mode_count <= 1:
            ticks = [(1, "1")]
        else:
            step = max(1, int(np.ceil(mode_count / 8)))
            positions = list(range(1, mode_count + 1, step))
            if positions[-1] != mode_count:
                positions.append(mode_count)
            ticks = [(position, str(position)) for position in positions]
        axis.setTicks([ticks])

    @QtCore.pyqtSlot()
    def Update(self):
        """Update the GUI"""
        window = int(self.windowComboBox.currentText())
        dm, md, n = self.reader.snapshot(window=window)
        if n == 0:
            return
        if n < 2:
            self.statusLabel.setText(f"Buffering... {n} frames")
            return

        # Temporal rms, one value per mode.
        dmmodes = np.matmul(self.c2m, dm.T).T
        delayed_md = self._interpolate(md, self.delayInFrames)
        aligned_dm = dmmodes[:len(delayed_md)]
        pol_modes = aligned_dm + delayed_md[:,:aligned_dm.shape[1]]
        dm_rms = np.sqrt(np.mean(dmmodes**2, axis=0)) # dm_std = np.std(np.matmul(self.c2m, dm.T), axis=1)
        md_rms = np.sqrt(np.mean(md**2, axis=0)) # md_std = np.std(md, axis=0)
        pol_rms = np.sqrt(np.mean(pol_modes**2, axis=0))
        nModes = int(np.sum(md_rms>0))

        dm_rms = dm_rms[:nModes] * self.voltage2Nm[:nModes]
        md_rms = md_rms[:nModes] * self.voltage2Nm[:nModes]
        pol_rms = pol_rms[:nModes] * self.voltage2Nm[:nModes]

        # Total residual estimate
        maxModes = int(200) # max mode to use for the linear fit
        p = np.polyfit(np.arange(np.min((len(pol_rms),maxModes))),pol_rms[:maxModes],deg=1)
        min_res = 1e-2 # minimum residual [nm] to consider in the integral
        max_id = int((min_res-p[1])/p[0])
        ho_pol_rms = p[1]+p[0]*np.arange(len(pol_rms)+1,max_id)
        resInNm = np.sqrt(np.sum(pol_rms**2)+np.sum(ho_pol_rms**2))
        tot_res = 2*np.pi*resInNm/500
        r0 = self.reader.diameter * tot_res**(-6/5)
        seeingInRad = 0.98*500e-9/r0
        seeing = seeingInRad*180/np.pi*3600

        self.view.update_curves(
            dm_rms, md_rms, pol_rms,
            show_dm=self.dmCheckBox.isChecked(),
            show_modes=self.modeCheckBox.isChecked(),
            show_pol=self.polModesCheckBox.isChecked(),
        )
        self._set_mode_ticks(nModes)
        self.view.plot.setTitle(
            f'DM commands: {np.sqrt(np.sum(dm_rms**2)):1.1f}nm | '
            f'Rec modes: {np.sqrt(np.sum(md_rms**2)):1.1f}nm | '
            f'Estimated seeing: {seeing:1.1f}"',
            size='12pt',
        )

        fs = self.reader.sampling_rate()
        self.statusLabel.setText(
            f"fs = {fs:.1f} Hz   |   {n} frames averaged ({n / fs:.2f} s)   |   "
            f"{dm_rms.size} projected modes, {md_rms.size} reconstructed modes")

    @QtCore.pyqtSlot(str)
    def onError(self, msg):
        self.statusLabel.setText(f"Error: {msg}")

    def closeEvent(self, event):
        # Inform the parent that this window is closing
        self.Stop()
        self.reader.stop()
        if self.parent:
            self.parent.modalPlotWindow = None
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication([])
    app.setApplicationDisplayName("Modal Plot")
    main = ModalPlot()
    main.setWindowTitle("Modal Plot")
    main.show()
    main.Start()
    sys.exit(app.exec_())
