from GUIUtils import *  # QThreadPool, QtCore, pg, np, QApplication, loadUiType, os, sys

from PyQt5.QtCore import QObject, QRunnable, pyqtSignal, pyqtSlot

path = os.getenv("DAOROOT") + "/data/"
Ui_ValidPixelSelector, ValidPixelSelectorBase = loadUiType(
    os.path.join(path, "validPixelSelector.ui")
)


class MaskWorkerSignals(QObject):
    # (mask, threshold, in_radius, out_radius, filtered)
    result = pyqtSignal(object, float, float, float, bool)
    error = pyqtSignal(str)


class MaskWorker(QRunnable):
    """Compute the valid-pixel mask on a background thread.

    Reads `valid_pix_map` (never mutates it) and emits a fresh array, so it is
    safe to run off the GUI thread. Only the emitted result touches Qt/pyqtgraph
    -- and that happens back on the GUI thread via a queued signal connection.
    """

    def __init__(self, valid_pix_map, threshold, in_radius, out_radius, do_filter):
        super().__init__()
        self.valid_pix_map = valid_pix_map
        self.threshold = threshold
        self.in_radius = in_radius
        self.out_radius = out_radius
        self.do_filter = do_filter
        self.signals = MaskWorkerSignals()

    @pyqtSlot()
    def run(self):
        try:
            mask = compute_mask(
                self.valid_pix_map,
                self.threshold,
                self.do_filter,
                self.in_radius,
                self.out_radius,
            )
            self.signals.result.emit(
                mask, self.threshold, self.in_radius, self.out_radius, self.do_filter
            )
        except Exception as exc:  # noqa: BLE001 - report anything back to the GUI
            self.signals.error.emit(str(exc))


def _two_level_thresholding(image, thr1: float = 0.1, thr2: float = 0.25):
    """ Use two level thresholding to define active pixels """
    min_val, max_val = float(np.min(image)), float(np.max(image))
    s1 = min_val + (max_val - min_val) * thr1
    thresh_img = image.copy()
    thresh_img[thresh_img < s1] = 0
    s2 = float(np.mean(thresh_img[thresh_img > 0])) * thr2
    mask = thresh_img >= s2
    return mask

def _get_photocenters(valid_pix_map, xHalf: int = 100, yHalf: int = 120):
    """ Compute photocenters for each pupil """
    mask = _two_level_thresholding(valid_pix_map)
    x = np.arange(240)
    X, Y = np.meshgrid(x, x)
    X = X.astype(float)
    Y = Y.astype(float)
    # data = valid_pix_map * mask
    data = mask.copy()
    
    # Get x,y photocenters
    p1 = data[:xHalf, :yHalf].sum()
    p2 = data[xHalf:, :yHalf].sum()
    p3 = data[:xHalf, yHalf:].sum()
    p4 = data[xHalf:, yHalf:].sum()
    
    cx1 = np.sum(X[:xHalf, :yHalf] * data[:xHalf, :yHalf]) / p1
    cx2 = np.sum(X[xHalf:, :yHalf] * data[xHalf:, :yHalf]) / p2
    cx3 = np.sum(X[:xHalf, yHalf:] * data[:xHalf, yHalf:]) / p3
    cx4 = np.sum(X[xHalf:, yHalf:] * data[xHalf:, yHalf:]) / p4
    
    cy1 = np.sum(Y[:xHalf, :yHalf] * data[:xHalf, :yHalf]) / p1
    cy2 = np.sum(Y[xHalf:, :yHalf] * data[xHalf:, :yHalf]) / p2
    cy3 = np.sum(Y[:xHalf, yHalf:] * data[:xHalf, yHalf:]) / p3
    cy4 = np.sum(Y[xHalf:, yHalf:] * data[xHalf:, yHalf:]) / p4
    
    pupil_centers = np.array([[cx1, cy1], [cx2, cy2], [cx3, cy3], [cx4, cy4]])
    return pupil_centers, X, Y

def _add_circular_masks(valid_pix_map, in_radius: float = 0.0, out_radius: float = 40.0):
    """ Compute anular masks with given radii, centered of pupils """
    pupil_centers, X, Y = _get_photocenters(valid_pix_map)
    circ_masks = np.zeros(valid_pix_map.shape)
    
    for j in range(pupil_centers.shape[0]):
        cx, cy = pupil_centers[j, 0], pupil_centers[j, 1]
        rad_distance = np.sqrt((X - cx)**2 + (Y - cy)**2)
        circ_masks += (rad_distance <= out_radius) * (rad_distance >= in_radius)
        
    return circ_masks.astype(bool)

def _apply_filter(valid_pix):
    """Neighbour count filter, identical to the original."""
    hpf = np.ones((3, 3), dtype=np.float32)
    hpf[1, 1] = 0
    padded = np.pad(valid_pix.astype(np.float32), pad_width=1, mode="constant")
    sx, sy = valid_pix.shape
    conv = np.zeros((sx, sy), dtype=np.float32)
    for i in range(hpf.shape[0]):
        for j in range(hpf.shape[1]):
            conv += padded[i:i + sx, j:j + sy] * hpf[i, j]
    return conv > 5


def compute_mask(valid_pix_map, threshold, do_filter, in_radius=0.0, out_radius=25.0):
    """threshold + optional neighbour filter. Same result as the old update_mask."""
    valid_pix = valid_pix_map > threshold
    if do_filter:
        valid_pix = _apply_filter(valid_pix)
    return np.logical_and(
        valid_pix, _add_circular_masks(valid_pix_map, in_radius, out_radius)
    )


class ValidPixelSelector(ValidPixelSelectorBase, Ui_ValidPixelSelector):
    """Interactive valid-pixel selection with a live threshold control.

    Layout comes from data/validPixelSelector.ui (same pattern as benchTests).
    """

    def __init__(self, valid_pix_map, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setupUi(self)          # builds glw, thresholdBox, filterCheck, ...
        self.glw.setBackground("#0b1740")   # or 'w', 'k', or a QColor
        # Pre-normalized map from acquisition -- never recomputed here.
        self.valid_pix_map = valid_pix_map
        max_val = np.max(self.valid_pix_map)
        self.norm_pix_map = (
            self.valid_pix_map / max_val if max_val > 0 else self.valid_pix_map
        )
        self.valid_pix = None       # result, filled by the worker / on accept

        # --- worker plumbing (same idea as benchTest's threadpool) ---
        self.threadpool = QThreadPool()
        self._dirty = False         # params changed since last computed frame
        self._busy = False          # a worker is currently in flight
        self._ranged = False        # have we auto-ranged the view yet?

        # --- Side-by-Side Image Display ---
        self.image_title = self.glw.addLabel(row=0, col=0, colspan=2)

        # Left View: Normalized Pupil Frame minus Mask
        self.vb_left = self.glw.addViewBox(row=1, col=0)
        self.vb_left.setAspectLocked(True)
        self.img_left = pg.ImageItem()
        self.vb_left.addItem(self.img_left)

        # Right View: Boolean Mask
        self.vb_right = self.glw.addViewBox(row=1, col=1)
        self.vb_right.setAspectLocked(True)
        self.img_right = pg.ImageItem()
        self.vb_right.addItem(self.img_right)

        # Link zoom/pan between both views
        self.vb_right.setXLink(self.vb_left)
        self.vb_right.setYLink(self.vb_left)

        # Set Colormaps
        cmap_viridis = pg.colormap.get("viridis")
        self.img_left.setLookupTable(cmap_viridis.getLookupTable(0.0, 1.0, 256))
        self.img_right.setLookupTable(cmap_viridis.getLookupTable(0.0, 1.0, 2))

        # --- wiring ---
        # Input handlers are deliberately trivial: they only mark state dirty.
        # The timer (Update) decides when to actually recompute.
        self.thresholdBox.valueChanged.connect(self._mark_dirty)
        self.innerRadiusBox.valueChanged.connect(self._mark_dirty)
        self.outerRadiusBox.valueChanged.connect(self._mark_dirty)
        # self.innerRadiusBox.valueChanged.connect(self.Update) # unnecessary ? 
        # self.outerRadiusBox.valueChanged.connect(self.Update) # unnecessary ? 
        self.filterCheck.toggled.connect(self._mark_dirty)
        self.okButton.clicked.connect(self.accept)
        self.cancelButton.clicked.connect(self.reject)

        # --- refresh timer (identical structure to benchTest) ---
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(50)              # 20 Hz, same as benchTest
        self.timer.timeout.connect(self.Update)

        # Paint the initial frame synchronously so the dialog opens populated,
        # then let the timer/worker handle every interactive change.
        self._compute_and_show(
            self.thresholdBox.value(),
            self.innerRadiusBox.value(),
            self.outerRadiusBox.value(),
            self.filterCheck.isChecked(),
        )
        self.Start()

    # ----- benchTest-style lifecycle -------------------------------------
    def Start(self):
        """Start the refresh timer."""
        self.timer.start()

    def Stop(self):
        """Stop the refresh timer."""
        self.timer.stop()

    def _mark_dirty(self, *args):
        """Slot for every control: cheap, just flags that a recompute is due."""
        self._dirty = True

    @QtCore.pyqtSlot()
    def Update(self):
        """Timer tick: if something changed and no worker is running, dispatch one.

        This is what coalesces a burst of spinbox events into at most one
        recompute per 50 ms, and keeps the numpy work off the GUI thread.
        """
        if not self._dirty or self._busy:
            return

        # Read widget values here (GUI thread) and hand plain data to the worker.
        threshold = self.thresholdBox.value()
        in_radius = self.innerRadiusBox.value()
        out_radius = self.outerRadiusBox.value()
        do_filter = self.filterCheck.isChecked()
        self._dirty = False
        self._busy = True

        worker = MaskWorker(
            self.valid_pix_map, threshold, in_radius, out_radius, do_filter
        )
        worker.signals.result.connect(self._on_mask_ready)
        worker.signals.error.connect(self._on_mask_error)
        self.threadpool.start(worker)

    # ----- worker callbacks (run back on the GUI thread) -----------------
    @pyqtSlot(object, float, float, float, bool)
    def _on_mask_ready(self, mask, threshold, in_radius, out_radius, do_filter):
        self._busy = False
        self._show_both_views(mask) # self._show_mask(mask)
        # If the user kept twiddling while we computed, _dirty is set again and
        # the next timer tick will pick up the latest values.

    @pyqtSlot(str)
    def _on_mask_error(self, message):
        self._busy = False
        self.countLabel.setText(f"error: {message}")

    # ----- display helpers ------------------------------------------------
    # def _show_mask(self, mask):
    #     """Cheap GUI-thread update: fixed levels so pyqtgraph skips autoLevels."""
    #     self.valid_pix = mask
    #     # levels=(0, 1) + autoLevels=False avoids a per-call histogram/level pass.
    #     self.img.setImage(mask.T.astype(np.float32), autoLevels=False, levels=(0, 1))
    #     if not self._ranged:
    #         self.vb.autoRange()     # frame the image once; then leave the view put
    #         self._ranged = True
    #     self.countLabel.setText(f"{int(mask.sum())} valid pixels")

    # def _compute_and_show(self, threshold, in_radius, out_radius, do_filter):
    #     """Synchronous compute+show, used only for the very first frame."""
    #     self._show_mask(
    #         compute_mask(
    #             self.valid_pix_map, threshold, do_filter, in_radius, out_radius
    #         )
    #     )

    def _show_both_views(self, mask):
        """Renders both left (Normalized - Mask) and right (Boolean Mask) side-by-side."""
        self.valid_pix = mask
        mask_float = mask.astype(np.float32)

        # Left View: Pupil Frame with Mask Subtracted
        masked_img = self.norm_pix_map - mask_float
        self.img_left.setImage(masked_img.T, autoLevels=False, levels=(-1, 1))

        # Right View: Pure Boolean Mask
        self.img_right.setImage(mask_float.T, autoLevels=False, levels=(0, 1))

        if not self._ranged:
            self.vb_left.autoRange()
            self.vb_right.autoRange()
            self._ranged = True

        captured_pct = (
            (np.sum(mask * self.norm_pix_map) / np.sum(self.norm_pix_map) * 100.0)
            if np.sum(self.norm_pix_map) > 0
            else 0.0
        )
        valid_pixels = int(mask.sum())
        pixel_text = f"<span style='color:red'>{valid_pixels}</span>" if valid_pixels > 6000 else str(valid_pixels)
        self.image_title.setText(
            f"{pixel_text} valid pixels | {captured_pct:1.1f}% intensity captured"
        )

    def _compute_and_show(self, threshold, in_radius, out_radius, do_filter):
        """Synchronous compute+show, used only for the very first frame."""
        initial_mask = compute_mask(
            self.valid_pix_map, threshold, do_filter, in_radius, out_radius
        )
        self._show_both_views(initial_mask)

    # ----- result contract (unchanged for select_valid_pixels.py) --------
    def accept(self):
        # Guarantee the returned mask matches exactly what the controls show,
        # even if a throttled recompute was still pending.
        self.Stop()
        self.valid_pix = compute_mask(
            self.valid_pix_map,
            self.thresholdBox.value(),
            self.filterCheck.isChecked(),
            self.innerRadiusBox.value(),
            self.outerRadiusBox.value(),
        )
        super().accept()

    def reject(self):
        self.Stop()
        super().reject()

    def closeEvent(self, event):
        self.Stop()
        if self.parent:
            self.parent.validPixelSelectorWindow = None
        super().closeEvent(event)

    def result_mask(self):
        return self.valid_pix


if __name__ == "__main__":
    # Standalone smoke test with a synthetic map (mirrors benchTest's __main__).
    app = QApplication([])
    app.setApplicationDisplayName("Select valid pixels")

    yy, xx = np.mgrid[0:240, 0:240].astype(np.float32)
    r = np.sqrt((xx - 120) ** 2 + (yy - 120) ** 2)
    demo_map = np.clip(1.0 - r / 110.0, 0, 1).astype(np.float32)
    demo_map += 0.05 * np.random.default_rng(0).standard_normal(demo_map.shape).astype(np.float32)

    dlg = ValidPixelSelector(demo_map)
    if dlg.exec_():
        print(f"accepted: {int(dlg.result_mask().sum())} valid pixels")
    else:
        print("cancelled")
    sys.exit(0)
# from GUIUtils import *  # QThreadPool, QtCore, pg, np, QApplication ... (as in benchTests.py)

# from PyQt5.QtCore import QObject, QRunnable, pyqtSignal, pyqtSlot, Qt
# from PyQt5.QtWidgets import (
#     QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
#     QDoubleSpinBox, QCheckBox,
# )

# class MaskWorkerSignals(QObject):
#     # (mask, threshold, filtered) -- params echoed back so the slot can label it
#     result = pyqtSignal(object, float, bool)
#     error = pyqtSignal(str)


# class MaskWorker(QRunnable):
#     """Compute the valid-pixel mask on a background thread.

#     Reads `valid_pix_map` (never mutates it) and emits a fresh array, so it is
#     safe to run off the GUI thread. Only the emitted result touches Qt/pyqtgraph
#     -- and that happens back on the GUI thread via a queued signal connection.
#     """

#     def __init__(self, valid_pix_map, threshold, do_filter):
#         super().__init__()
#         self.valid_pix_map = valid_pix_map
#         self.threshold = threshold
#         self.do_filter = do_filter
#         self.signals = MaskWorkerSignals()

#     @pyqtSlot()
#     def run(self):
#         try:
#             mask = compute_mask(self.valid_pix_map, self.threshold, self.do_filter)
#             self.signals.result.emit(mask, self.threshold, self.do_filter)
#         except Exception as exc:  # noqa: BLE001 - report anything back to the GUI
#             self.signals.error.emit(str(exc))


# def _apply_filter(valid_pix):
#     """Neighbour count filter, identical to the original."""
#     hpf = np.ones((3, 3), dtype=np.float32)
#     hpf[1, 1] = 0
#     padded = np.pad(valid_pix.astype(np.float32), pad_width=1, mode="constant")
#     sx, sy = valid_pix.shape
#     conv = np.zeros((sx, sy), dtype=np.float32)
#     for i in range(hpf.shape[0]):
#         for j in range(hpf.shape[1]):
#             conv += padded[i:i + sx, j:j + sy] * hpf[i, j]
#     return conv > 5


# def compute_mask(valid_pix_map, threshold, do_filter):
#     """threshold + optional neighbour filter. Same result as the old update_mask."""
#     valid_pix = valid_pix_map > threshold
#     if do_filter:
#         valid_pix = _apply_filter(valid_pix)
#     return valid_pix


# class ValidPixelSelector(QDialog):
#     """Interactive valid-pixel selection with a live threshold slider."""

#     def __init__(self, valid_pix_map, parent=None):
#         super().__init__(parent)
#         self.parent = parent
#         self.setWindowTitle("Select valid pixels")
#         self.resize(400,400)

#         # Pre-normalized map from acquisition -- never recomputed here.
#         self.valid_pix_map = valid_pix_map
#         self.valid_pix = None   # result, filled by the worker / on accept

#         # --- worker plumbing (same idea as benchTest's threadpool) ---
#         self.threadpool = QThreadPool()
#         self._dirty = False      # params changed since last computed frame
#         self._busy = False       # a worker is currently in flight
#         self._ranged = False     # have we auto-ranged the view yet?

#         # --- image display ---
#         self.glw = pg.GraphicsLayoutWidget()
#         self.vb = self.glw.addViewBox()
#         self.vb.setAspectLocked(True)
#         self.img = pg.ImageItem()
#         self.vb.addItem(self.img)

#         # --- controls ---
#         self.thresholdBox = QDoubleSpinBox()
#         self.thresholdBox.setRange(0.0, 1.0)
#         self.thresholdBox.setSingleStep(0.01)
#         self.thresholdBox.setValue(0.2)

#         self.filterCheck = QCheckBox("Apply neighbour filter")

#         self.countLabel = QLabel("")

#         self.okButton = QPushButton("Accept")
#         self.cancelButton = QPushButton("Cancel")

#         # --- layout ---
#         controls = QHBoxLayout()
#         controls.addWidget(QLabel("Threshold:"))
#         controls.addWidget(self.thresholdBox)
#         controls.addWidget(self.filterCheck)
#         controls.addWidget(self.countLabel)
#         controls.addStretch()

#         buttons = QHBoxLayout()
#         buttons.addStretch()
#         buttons.addWidget(self.cancelButton)
#         buttons.addWidget(self.okButton)

#         layout = QVBoxLayout(self)
#         layout.addWidget(self.glw)
#         layout.addLayout(controls)
#         layout.addLayout(buttons)

#         # --- wiring ---
#         # Input handlers are deliberately trivial: they only mark state dirty.
#         # The timer (Update) decides when to actually recompute.
#         self.thresholdBox.valueChanged.connect(self._mark_dirty)
#         self.filterCheck.toggled.connect(self._mark_dirty)
#         self.okButton.clicked.connect(self.accept)
#         self.cancelButton.clicked.connect(self.reject)

#         # --- refresh timer (identical structure to benchTest) ---
#         self.timer = QtCore.QTimer(self)
#         self.timer.setInterval(50)                # 20 Hz, same as benchTest
#         self.timer.timeout.connect(self.Update)

#         # Paint the initial frame synchronously so the dialog opens populated,
#         # then let the timer/worker handle every interactive change.
#         self._compute_and_show(self.thresholdBox.value(), self.filterCheck.isChecked())
#         self.Start()

#     # ----- benchTest-style lifecycle -------------------------------------
#     def Start(self):
#         """Start the refresh timer."""
#         self.timer.start()

#     def Stop(self):
#         """Stop the refresh timer."""
#         self.timer.stop()

#     def _mark_dirty(self, *args):
#         """Slot for every control: cheap, just flags that a recompute is due."""
#         self._dirty = True

#     @QtCore.pyqtSlot()
#     def Update(self):
#         """Timer tick: if something changed and no worker is running, dispatch one.

#         This is what coalesces a burst of spinbox events into at most one
#         recompute per 50 ms, and keeps the numpy work off the GUI thread.
#         """
#         if not self._dirty or self._busy:
#             return

#         # Read widget values here (GUI thread) and hand plain data to the worker.
#         threshold = self.thresholdBox.value()
#         do_filter = self.filterCheck.isChecked()
#         self._dirty = False
#         self._busy = True

#         worker = MaskWorker(self.valid_pix_map, threshold, do_filter)
#         worker.signals.result.connect(self._on_mask_ready)
#         worker.signals.error.connect(self._on_mask_error)
#         self.threadpool.start(worker)

#     # ----- worker callbacks (run back on the GUI thread) -----------------
#     @pyqtSlot(object, float, bool)
#     def _on_mask_ready(self, mask, threshold, do_filter):
#         self._busy = False
#         self._show_mask(mask)
#         # If the user kept twiddling while we computed, _dirty is set again and
#         # the next timer tick will pick up the latest values.

#     @pyqtSlot(str)
#     def _on_mask_error(self, message):
#         self._busy = False
#         self.countLabel.setText(f"error: {message}")

#     # ----- display helpers ------------------------------------------------
#     def _show_mask(self, mask):
#         """Cheap GUI-thread update: fixed levels so pyqtgraph skips autoLevels."""
#         self.valid_pix = mask
#         # levels=(0, 1) + autoLevels=False avoids a per-call histogram/level pass.
#         self.img.setImage(mask.T.astype(np.float32), autoLevels=False, levels=(0, 1))
#         if not self._ranged:
#             self.vb.autoRange()      # frame the image once; then leave the view put
#             self._ranged = True
#         self.countLabel.setText(f"{int(mask.sum())} valid pixels")

#     def _compute_and_show(self, threshold, do_filter):
#         """Synchronous compute+show, used only for the very first frame."""
#         self._show_mask(compute_mask(self.valid_pix_map, threshold, do_filter))

#     # ----- result contract (unchanged for select_valid_pixels.py) --------
#     def accept(self):
#         # Guarantee the returned mask matches exactly what the controls show,
#         # even if a throttled recompute was still pending.
#         self.Stop()
#         self.valid_pix = compute_mask(
#             self.valid_pix_map,
#             self.thresholdBox.value(),
#             self.filterCheck.isChecked(),
#         )
#         super().accept()

#     def reject(self):
#         self.Stop()
#         super().reject()

#     def closeEvent(self, event):
#         self.Stop()
#         super().closeEvent(event)

#     def result_mask(self):
#         return self.valid_pix


# if __name__ == "__main__":
#     # Standalone smoke test with a synthetic map (mirrors benchTest's __main__).
#     app = QApplication([])
#     app.setApplicationDisplayName("Select valid pixels")

#     yy, xx = np.mgrid[0:240, 0:240].astype(np.float32)
#     r = np.sqrt((xx - 120) ** 2 + (yy - 120) ** 2)
#     demo_map = np.clip(1.0 - r / 110.0, 0, 1).astype(np.float32)
#     demo_map += 0.05 * np.random.default_rng(0).standard_normal(demo_map.shape).astype(np.float32)

#     dlg = ValidPixelSelector(demo_map)
#     if dlg.exec_():
#         print(f"accepted: {int(dlg.result_mask().sum())} valid pixels")
#     else:
#         print("cancelled")
#     sys.exit(0)