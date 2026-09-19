import pyqtgraph as pg
from pyqtgraph import PlotWidget
from pyqtgraph import ImageView
from PyQt5.uic import loadUiType
from PyQt5 import QtCore
from PyQt5.QtWidgets import QApplication, QVBoxLayout, QHBoxLayout, QWidget
from PyQt5.QtCore import QRunnable, QThreadPool, pyqtSlot, QObject, pyqtSignal
from PyQt5.QtGui import QIcon

import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.colors import LinearSegmentedColormap
import pyqtgraph as pg
import numpy as np
import re
import subprocess
import dao
import platform
import shutil
import os
import sys, getopt
import time
from astropy.io import fits
# ---------------------------------------------------------------------------
# GUI theme
# ---------------------------------------------------------------------------
THEME_BG = "#0b1740"
THEME_FG = "white"

# "viridis-like, with more contrast":
VIRIDIS_HC = LinearSegmentedColormap.from_list(
    "viridis_hc",
    [
        "#000000",
        "#05041a",
        "#2a1a6b",
        "#1e5fa8",
        "#12a89a",
        "#34c46a",
        "#b6e02a",
        "#fdfdb0",
    ],
    N=256,
)

def _style_mpl_axes(ax):
    """Dark-blue background + white ticks/labels/spines for a matplotlib axes."""
    ax.set_facecolor(THEME_BG)
    ax.tick_params(colors=THEME_FG, which="both")
    ax.xaxis.label.set_color(THEME_FG)
    ax.yaxis.label.set_color(THEME_FG)
    ax.title.set_color(THEME_FG)
    for spine in ax.spines.values():
        spine.set_color(THEME_FG)


def _style_mpl_colorbar(cbar):
    """White ticks/labels/outline for a matplotlib colorbar."""
    cbar.ax.tick_params(colors=THEME_FG)
    cbar.ax.yaxis.label.set_color(THEME_FG)
    cbar.outline.set_edgecolor(THEME_FG)


def style_messagebox(msg_box):
    """Apply GUI theme to a QMessageBox."""
    msg_box.setStyleSheet(f"""
        QMessageBox {{
            background-color: {THEME_BG};
        }}
        QMessageBox QLabel {{
            color: {THEME_FG};
        }}
        QMessageBox QPushButton {{
            color: {THEME_FG};
            background-color: #1a2d5c;
            border: 1px solid {THEME_FG};
            border-radius: 3px;
            padding: 4px 16px;
            min-width: 50px;
        }}
        QMessageBox QPushButton:hover {{
            background-color: #2a3d7c;
        }}
        QMessageBox QPushButton:pressed {{
            background-color: #0f1a40;
        }}
    """)

def style_messagebox_alert(msg_box):
    """Apply GUI theme with red alert border to a QMessageBox."""
    msg_box.setStyleSheet(f"""
        QMessageBox {{
            background-color: {THEME_BG};
            border: 5px solid red;
            border-radius: 8px;
        }}
        QMessageBox QLabel {{
            color: {THEME_FG};
        }}
        QMessageBox QPushButton {{
            color: {THEME_FG};
            background-color: #8B0000;
            border: 2px solid red;
            border-radius: 3px;
            padding: 4px 16px;
            min-width: 50px;
            font-weight: bold;
        }}
        QMessageBox QPushButton:hover {{
            background-color: #BB0000;
        }}
        QMessageBox QPushButton:pressed {{
            background-color: #660000;
        }}
    """)

def mount_mpl_canvas(placeholder, canvas, parent=None, toolbar=True, toolbar_bg=THEME_BG):
    """Drop a matplotlib canvas (optionally with its nav toolbar) into a .ui
    placeholder widget. Returns the toolbar (or None) so the caller can keep a reference if needed.
    """
    layout = QVBoxLayout()
    tb = None
    if toolbar:
        tb = NavigationToolbar(canvas, parent)
        tb.setStyleSheet(f"background-color:{toolbar_bg}")
        layout.addWidget(tb)
    layout.addWidget(canvas)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    placeholder.setLayout(layout)
    return tb


def get_dmV2nm_conversion(m2c):
    SF2WF = 2 # surface to wavefront conversion factor
    IFs = fits.getdata(os.path.join(os.getenv('DAODATA'), "inputs", 'dm468', 'reordered_DM468_ifunc.fits')).T*SF2WF
    mode_amps = np.std(IFs @ m2c,axis=0) 
    return mode_amps*1e+9

class SubprocessWorker(QRunnable):
    """
    Worker thread that runs a subprocess in the background.
    """
    def __init__(self, command):
        super(SubprocessWorker, self).__init__()
        self.command = command
        self.signals = WorkerSignals()
        self.process = None  # Initialize process attribute

    def stop(self):
        """Terminate the subprocess."""
        if hasattr(self, 'process') and self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()

    @pyqtSlot()
    def run(self):
        """Run the subprocess."""
        try:
            # Use Popen instead of run() so we can store and control the process
            self.process = subprocess.Popen(
                self.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Wait for the process to complete
            stdout, stderr = self.process.communicate()
            
            if self.process.returncode == 0:
                self.signals.finished.emit(stdout)  # Emit success signal with output
                # Try to extract the "xxx" from the line that contains "saving on xxx"
                match = re.search(r"Saving in (.+)", stdout)
                if match:
                    saving_path = match.group(1)
                    self.signals.path_extracted.emit(saving_path)
            else:
                self.signals.error.emit(stderr)  # Emit error signal with error message
                
        except Exception as e:
            self.signals.error.emit(str(e))


# Define signals to communicate between the thread and the main GUI thread
class WorkerSignals(QObject):
    """
    Defines the signals available from a running worker thread.
    """

    finished = pyqtSignal(str)  # Signal to emit when finished
    error = pyqtSignal(str)  # Signal to emit if an error occurs
    path_extracted = pyqtSignal(str)  # Signal to emit the extracted path (saving_path)


class MplCanvas(FigureCanvas):
    """Matplotlib Canvas class to support imshow"""

    def __init__(
        self,
        parent=None,
        width=5,
        height=4,
        dpi=100,
        im=np.zeros((128, 128)),
        pup=np.zeros((128, 128)),
    ):
        self.fig, self.ax = plt.subplots(figsize=(width, height), dpi=dpi)
        super(MplCanvas, self).__init__(self.fig)
        # Theme: figure + axes background to match the GUI panels.
        self.fig.patch.set_facecolor(THEME_BG)
        self.ax.set_facecolor(THEME_BG)
        self.ax.set_aspect("equal")
        """Clear the axes and plot a new image with colorbar."""
        self.ax.clear()  # Clear the previous plot
        self.cax = self.ax.imshow(im, cmap=VIRIDIS_HC, origin="lower")
        self.cbar = self.fig.colorbar(self.cax)  # Initialize colorbar
        # Theme: white ticks/labels/spines on both the image axes and colorbar.
        _style_mpl_axes(self.ax)
        _style_mpl_colorbar(self.cbar)

    def plot_image(self, image, pup, neg=False):
        dmax = image[10:].max()
        dmin = image[10:].min()
        self.cax.set_data(image)
        if neg == True:
            self.cax.set_clim(dmin, dmax)
        else:
            self.cax.set_clim(0, dmax)
        # # Create the alpha channel: 1.0 where mask is True, 0.6 elsewhere
        alpha = np.where(pup, 1.0, 0.6)
        self.cax.set_alpha(alpha)
        # Redraw the canvas
        self.draw()

    def plot_image_general(self, image):
        dmax = image.max()
        self.cax.set_data(image)
        self.cax.set_clim(0, dmax)
        # Redraw the canvas
        self.draw()


class MplHistCanvas(FigureCanvas):
    """Matplotlib Canvas class to support histograms"""

    def __init__(self, parent=None, width=5, height=4, dpi=100):
        self.fig = plt.Figure(figsize=(width, height), dpi=dpi)
        self.axes = self.fig.add_subplot(111)
        super(MplHistCanvas, self).__init__(self.fig)
        # Theme: figure + axes background and white text.
        self.fig.patch.set_facecolor(THEME_BG)
        _style_mpl_axes(self.axes)

class ModeHistCanvas(MplHistCanvas):
    """Themed bar plot for the reconstructed modes. Feed it a 1-D array via update_hist()`.
    """
    def __init__(self, parent=None, data=None, ylim=(-50,50),#(-0.1, 0.1),
                 width=5, height=4, dpi=100, ylabel=''):
        super().__init__(parent, width, height, dpi)
        if data is None:
            data = np.zeros(1)
        n = len(data)
        self.bars = self.axes.bar(np.arange(n), data, width=1.0, color=THEME_FG)
        self.axes.set_xlim(-0.5, n - 0.5)
        self.axes.set_ylim(list(ylim))
        self.axes.set_ylabel(ylabel)
        self.axes.margins(x=0)
        self.axes.tick_params(labelsize=8, pad=2)
        self.fig.subplots_adjust(left=0.05, right=0.98, top=0.95, bottom=0.22)
    def update_hist(self, data):
        for bar, h in zip(self.bars, data):
            bar.set_height(h)
        self.axes.autoscale_view(scalex=False)   # keep x pinned
        self.draw()


class DmShapeView:
    """Fills a pyqtgraph GraphicsView placeholder (e.g. the .ui `dmView`) with
    the DM command map.

    Construction and per-frame refresh in one place. `update_shape()` takes
    plain arrays (the DM command column and the 468 mask) — no shm access
    here — so the controller keeps ownership of `dao.shm` reads and label text.
    """

    def __init__(self, graphics_view, mask, colormap="viridis"):
        # Start by showing the raw mask; the first update_shape() replaces it
        # with actual DM values.
        self.dmM = np.copy(mask).astype(np.float32)
        self.vb = pg.ViewBox()
        graphics_view.setCentralItem(self.vb)
        self.img = pg.ImageItem(border=None)
        if colormap is not None:
            self.img.setColorMap(colormap)
        self.vb.addItem(self.img)
        self.vb.setAspectLocked(True)
        self.img.setImage(self.dmM)

    def update_shape(self, dm_cmd, mask):
        self.dmM[mask == 1] = dm_cmd[:, 0]
        self.dmM[mask == 0] = np.nan
        # Rotate by 180° for consistency with OCAM frame
        self.dmM = np.fliplr(np.flipud(self.dmM))
        self.img.setImage(self.dmM)


class TtScatterView:
    """Fills a pyqtgraph GraphicsView placeholder (e.g. the .ui `ttView`) with
    a fixed-range tip-tilt position marker and crosshairs.

    `update_position(x, y)` moves the marker; the caller does the shm read and
    any offset arithmetic.
    """

    def __init__(self, graphics_view, extent=50):
        self.vb = pg.ViewBox()
        graphics_view.setCentralItem(self.vb)
        self.vb.setAspectLocked(True)
        self.vb.setRange(xRange=(-extent, extent), yRange=(-extent, extent), padding=0)
        self.vb.setMouseEnabled(x=False, y=False)
        self.vb.setLimits(xMin=-extent, xMax=extent, yMin=-extent, yMax=extent)
        self.vb.addItem(pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen('w', width=1)))
        self.vb.addItem(pg.InfiniteLine(pos=0, angle=90, pen=pg.mkPen('w', width=1)))
        self.scatter = pg.ScatterPlotItem(
            size=10, brush=pg.mkBrush('r'), pen=pg.mkPen('w')
        )
        self.vb.addItem(self.scatter)
        self.scatter.setData([0], [0])

    def update_position(self, x, y):
        self.scatter.setData([x], [y])



# ----- old GUIUtil functions not used anymore --


# def _style_pg_plot(widget):
#     """Dark-blue background + white axes/labels for a pyqtgraph PlotWidget."""
#     widget.setBackground(THEME_BG)
#     for name in ("left", "bottom", "right", "top"):
#         axis = widget.getAxis(name)
#         axis.setPen(pg.mkPen(THEME_FG))        # axis line + ticks
#         axis.setTextPen(pg.mkPen(THEME_FG))    # tick labels (pyqtgraph >= 0.11)


# class PgImageCanvas(QWidget):
#     """PyQtGraph-based canvas to replace Matplotlib for image display with optional alpha mask."""

#     def __init__(self, parent=None, im=np.zeros((128, 128)), pup=np.ones((128, 128))):
#         super().__init__(parent)
#         self.view = pg.ImageView(view=pg.PlotItem())
#         layout = pg.QtWidgets.QVBoxLayout(self)
#         layout.setContentsMargins(0, 0, 0, 0)
#         layout.addWidget(self.view)

#         # Theme: match the GUI panel background.
#         self.view.ui.graphicsView.setBackground(THEME_BG)

#         # Hide unused buttons and resize colorbar
#         self.view.ui.roiBtn.hide()
#         self.view.ui.menuBtn.hide()
#         self.view.ui.histogram.gradient.loadPreset("viridis")
#         self.view.ui.histogram.hide()

#         vb = self.view.getView().getViewBox()
#         vb.setDefaultPadding(0)
#         # Hide axes
#         self.view.getView().hideAxis("left")
#         self.view.getView().hideAxis("bottom")

#         self.image_item = self.view.imageItem
#         self.plot_image(im, pup)

#     def plot_image(self, image, pup, neg=False, yaxis=None):
#         if yaxis is not None:
#             dmin, dmax = yaxis
#         else:
#             dmax = image[10:].max()
#             dmin = image[10:].min()
#             if not neg:
#                 dmin = 0

#         levels = (dmin, dmax)

#         alpha = np.where(pup, 1.0, 0.6).astype(np.float32)

#         rgba = np.zeros((*image.shape, 4), dtype=np.float32)
#         norm = dmax if dmax != 0 else 1
#         normed_image = image / norm
#         rgba[..., 0] = normed_image
#         rgba[..., 1] = normed_image
#         rgba[..., 2] = normed_image
#         rgba[..., 3] = alpha

#         # Block histogram auto-scaling
#         self.view.ui.histogram.setLevels(*levels)
#         self.view.autoHistogramRange = False  # <--- Important to stop auto-blinking

#         # Set the image with levels in one go
#         self.image_item.setImage(rgba, levels=(0, 1), autoLevels=False)


# class PgHistCanvas(PlotWidget):
#     """PyQtGraph Canvas class to replace matplotlib for histogram plotting."""

#     def __init__(self, parent=None):
#         super().__init__(parent)
#         _style_pg_plot(self)  # dark-blue background + white axes/labels
#         self.plotItem.showGrid(x=True, y=True)
#         self.plotItem.setMouseEnabled(x=False, y=False)
#         self.bar_graph = None

#     def update_histogram(self, data):
#         x = np.arange(len(data))
#         if self.bar_graph is None:
#             self.bar_graph = pg.BarGraphItem(x=x, height=data, width=0.8, brush="b")
#             self.addItem(self.bar_graph)
#         else:
#             self.bar_graph.setOpts(x=x, height=data)


# class PgPlotCanvas(PlotWidget):
#     """PyQtGraph Canvas class for plotting data as a line chart."""

#     def __init__(self, parent=None):
#         super().__init__(parent)
#         _style_pg_plot(self)  # dark-blue background + white axes/labels
#         self.plotItem.showGrid(x=True, y=True)
#         self.plotItem.setMouseEnabled(x=False, y=False)
#         self.line_plot = None

#     def update_plot(self, data, yaxis=None):
#         x = np.arange(len(data))
#         if self.line_plot is None:
#             self.line_plot = self.plot(
#                 x,
#                 data,
#                 pen=pg.mkPen(color="b", width=2),
#                 symbol="o",
#                 symbolBrush="b",
#                 symbolSize=4,
#             )
#         else:
#             self.line_plot.setData(x, data)

#         # Set Y-axis limits if specified
#         if yaxis is not None:
#             ymin, ymax = yaxis
#             self.setYRange(ymin, ymax)