#!/usr/bin/env python3
"""Display an interaction-matrix column and reconstructor noise."""

from GUIUtils import *
from GUIUtils import _style_mpl_axes, _style_mpl_colorbar
from PyQt5.QtWidgets import QFileDialog


path = os.getenv("DAOROOT") + "/data/"
Ui_MainWindow, QMainWindow = loadUiType(
    os.path.join(path, "calibrationDisplay.ui")
)

IM_DIRECTORY = "/home/daouser/DAODATA/inputs/calibration/interactionMatrix/"


class CalibrationDisplay(QMainWindow, Ui_MainWindow):
    """Interactive display for an interaction matrix and its reconstructor."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setupUi(self)
        self.setWindowTitle("Calibration Display")
        self.setWindowModality(QtCore.Qt.NonModal)
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.WindowStaysOnTopHint)

        self.im_canvas = MplCanvas(self, width=5, height=4, dpi=100)
        self.im_canvas.fig.clear()
        self.im_ax = self.im_canvas.fig.add_axes([0.13, 0.08, 0.70, 0.82])
        self.im_colorbar_ax = self.im_canvas.fig.add_axes([0.86, 0.08, 0.035, 0.82])
        self.im_colorbar = None
        self.im_artist = None
        mount_mpl_canvas(self.imView, self.im_canvas, parent=self, toolbar=False)

        self.noise_canvas = MplCanvas(self, width=5, height=4, dpi=100)
        self.noise_canvas.fig.clear()
        self.noise_ax = self.noise_canvas.fig.add_subplot(111)
        mount_mpl_canvas(self.noiseView, self.noise_canvas, parent=self, toolbar=False)

        self._current_im_path = self._read_current_im_path()
        self._selected_im_path = self._current_im_path
        self._interaction_matrix = None
        self._noise_cache = {}
        self._valid_pixel_mask = self._load_valid_pixel_mask()

        self.mode_update_timer = QtCore.QTimer(self)
        self.mode_update_timer.setSingleShot(True)
        self.mode_update_timer.setInterval(300)
        self.mode_update_timer.timeout.connect(self.update_display)

        self.columnBox.valueChanged.connect(self.update_display)
        self.modeBox.valueChanged.connect(self._schedule_mode_update)
        self.selectIMButton.clicked.connect(self.select_interaction_matrix)

        self._load_selected_matrix()

    def Start(self):
        """Compatibility hook used by the main controller."""
        self.update_display()

    def Stop(self):
        """Compatibility hook used by the main controller."""
        self.mode_update_timer.stop()

    def _read_current_im_path(self):
        current_path_file = os.path.join(
            os.getenv("DAODATA"),
            "inputs",
            "calibration",
            "interactionMatrix",
            "current_imat.txt",
        )
        try:
            with open(current_path_file) as handle:
                return handle.read().strip()
        except (FileNotFoundError, OSError):
            return ""

    def _load_selected_matrix(self):
        if not self._selected_im_path:
            self._set_status("No current interaction matrix selected")
            return

        try:
            matrix = np.asarray(np.load(self._selected_im_path), dtype=np.float64)
            if matrix.ndim != 2:
                raise ValueError("interaction matrix must be two-dimensional")
            if matrix.shape[0] != 240 * 240:
                raise ValueError(
                    f"expected 57600 rows, got {matrix.shape[0]}"
                )
        except (OSError, ValueError, TypeError) as exc:
            self._interaction_matrix = None
            self._set_status(f"Could not load interaction matrix: {exc}")
            return

        self._interaction_matrix = matrix
        self._noise_cache.clear()
        self.columnBox.setRange(1, matrix.shape[1])
        self.modeBox.setRange(1, matrix.shape[1])
        self.modeBox.setValue(matrix.shape[1])
        self._set_status(
            f"Current IM: {os.path.basename(self._current_im_path) or 'unknown'}"
        )
        self.update_display()

    def _set_status(self, text):
        self.currentIMLabel.setText(text)

    def _load_valid_pixel_mask(self):
        mask_path = os.path.join(
            os.getenv("DAODATA"), "inputs", "calibration", "valid_pix_map.npy"
        )
        try:
            mask = np.asarray(np.load(mask_path), dtype=bool)
            if mask.size != 240 * 240:
                raise ValueError(f"expected 57600 pixels, got {mask.size}")
            return mask.reshape(-1)
        except (OSError, ValueError, TypeError):
            return None

    def _schedule_mode_update(self):
        self.mode_update_timer.start()

    def select_interaction_matrix(self):
        selected_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select interaction matrix",
            IM_DIRECTORY,
            "NumPy files (*.npy);;All files (*)",
        )
        if not selected_path:
            return
        self._selected_im_path = selected_path
        self._load_selected_matrix()

    def update_display(self):
        if self._interaction_matrix is None:
            return

        column_index = self.columnBox.value() - 1
        mode_count = min(self.modeBox.value(), self._interaction_matrix.shape[1])
        column = self._interaction_matrix[:, column_index]

        image_data = column.reshape(240, 240)
        if self.im_artist is None:
            self.im_artist = self.im_ax.imshow(
                image_data,
                origin="lower",
                cmap=VIRIDIS_HC,
                aspect="equal",
            )
            self.im_colorbar = self.im_canvas.fig.colorbar(
                self.im_artist,
                cax=self.im_colorbar_ax,
            )
            _style_mpl_colorbar(self.im_colorbar)
        else:
            self.im_artist.set_data(image_data)
            self.im_artist.set_clim(
                float(np.min(image_data)), float(np.max(image_data))
            )
        matrix_name = os.path.basename(self._selected_im_path) or "unknown"
        self.im_ax.set_title(
            f"{matrix_name}\nIM column {column_index + 1}",
            pad=10,
        )
        _style_mpl_axes(self.im_ax)
        self.im_canvas.draw()

        cache_key = mode_count
        rec_noise_full, rec_noise_valid, condition_full, condition_valid = (
            self._noise_cache.get(cache_key, (None, None, None, None))
        )
        selected_matrix = self._interaction_matrix[:, :mode_count]
        if rec_noise_full is None:
            reconstructor, singular_values = self._compute_reconstructor(selected_matrix)
            condition_full = (
                singular_values[0] / singular_values[-1]
                if singular_values[-1] > 0
                else np.inf
            )
            rec_noise_full = self._reconstructor_noise(reconstructor)

        if rec_noise_valid is None and self._valid_pixel_mask is not None:
            valid_matrix = selected_matrix[self._valid_pixel_mask, :]
            valid_reconstructor, singular_values = self._compute_reconstructor(valid_matrix)
            condition_valid = (
                singular_values[0] / singular_values[-1]
                if singular_values[-1] > 0
                else np.inf
            )
            rec_noise_valid = self._reconstructor_noise(valid_reconstructor)

        self._noise_cache[cache_key] = (
            rec_noise_full,
            rec_noise_valid,
            condition_full,
            condition_valid,
        )
        mode_indices = np.arange(1, mode_count + 1)

        self.noise_ax.clear()
        self.noise_ax.loglog(
            mode_indices,
            rec_noise_full,
            color=THEME_FG,
            label=f"{condition_full:.6f} (full frame)",
        )
        if rec_noise_valid is not None:
            self.noise_ax.loglog(
                mode_indices,
                rec_noise_valid,
                color="c",
                label=f"{condition_valid:.6f} (valid pixels)",
            )
        self.noise_ax.set_xlabel("Mode #")              
        self.noise_ax.set_title(f"Reconstructor noise ({mode_count} modes)")
        self.noise_ax.grid(which='both',alpha=0.4)
        self.noise_ax.legend()
        self.conditionLabelValue.setText(f"{condition_full:.6f}")
        self.validConditionLabelValue.setText(
            f"{condition_valid:.6f}" if condition_valid is not None else "N/A"
        )
        _style_mpl_axes(self.noise_ax)
        self.noise_canvas.fig.tight_layout()
        self.noise_canvas.draw()

    @staticmethod
    def _compute_reconstructor(matrix):
        U, singular_values, Vt = np.linalg.svd(matrix, full_matrices=False)
        if singular_values.size == 0:
            return np.zeros((matrix.shape[1], matrix.shape[0])), singular_values
        tolerance = np.finfo(matrix.dtype).eps * max(matrix.shape) * singular_values[0]
        inverse = np.zeros_like(singular_values)
        nonzero = singular_values > tolerance
        inverse[nonzero] = 1.0 / singular_values[nonzero]
        return (Vt.T * inverse) @ U.T, singular_values

    @staticmethod
    def _reconstructor_noise(reconstructor):
        noise = np.diag(reconstructor @ reconstructor.T)
        return np.maximum(noise, np.finfo(float).tiny)

    def closeEvent(self, event):
        self.Stop()
        if self.parent:
            self.parent.calibrationCheckWindow = None
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication([])
    app.setApplicationDisplayName("Calibration Display")
    window = CalibrationDisplay()
    window.show()
    window.Start()
    sys.exit(app.exec_())
