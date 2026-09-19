"""
@Author:    Thomas Davies
@Date:      23-06-2025
@Brief:     RTC latency monitoring GUI.
"""

# ============================================================ #

from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
)
from PyQt5.QtGui import QBrush, QKeySequence
from PyQt5.QtCore import pyqtSignal, QThread, pyqtSlot
import pyqtgraph as pg
import yaml as yml
import numpy as np
import dao

# ============================================================ #


class dao_latency_acc(QThread):
    sig_redraw = pyqtSignal(np.ndarray, tuple)

    def __init__(self, shm_path: str, buffer_cap: int, retention_fct: float = 0.8):
        super().__init__()
        self.buf = np.zeros((2, buffer_cap))
        self.shm = dao.shm(shm_path)
        self.buf_cap = buffer_cap
        self.buf_retention_size = int(buffer_cap * retention_fct)
        self.buf_size = 0
        self.accumulated = 0
        self.missed = 0

    def run(self):
        """
        Accumulates new frames from shm, discarding an initial proportion
        of the buffer when full to make room for upcoming frames, and
        signal gui to reflect new buffer state.
        """
        cnt0 = self.shm.get_counter()
        while True:
            cnt0_ = self.shm.get_counter()
            dcnt0 = cnt0_ - cnt0
            cnt0 = cnt0_
            if not dcnt0:
                continue  # frame not ready.

            # grab ready frame
            latency = self.shm.get_data()[0][0]
            self.buf[0][self.buf_size] = self.accumulated
            self.buf[1][self.buf_size] = latency
            self.missed += dcnt0 - 1
            self.accumulated += 1
            self.buf_size += 1

            # shuffle data around to make room for the future.
            if self.buf_size == self.buf_cap:
                self.buf[:,:self.buf_retention_size] = self.buf[:,-self.buf_retention_size:]
                self.buf_size = self.buf_retention_size

            # signal gui to update
            self.sig_redraw.emit(
                self.buf[:,:self.buf_size], (self.buf_size, self.accumulated, self.missed)
            )

# ============================================================ #


class dao_latency_widget(QWidget):
    # GUI cosmetic parameters..
    base_pen = pg.mkPen(color="#000000")
    plot_pen = pg.mkPen(color="#5AA5E2", width=1.5)
    lat_unit = "\u03bcs"
    plot_padding = 5
    n_hist_bins = 30

    def __init__(self, config_path: str, buffer_cap: int = 250):
        # init..
        super().__init__()
        self.buffer_cap = buffer_cap
        self.inspecting = False
        self.bar_p = None
        self.line_p = None

        # stats panel init..
        self.lbl_mt = QLabel("<b>Latency Metrics</b>")
        self.lbl_buf = QLabel(f"Buffer: -")
        self.lbl_acc = QLabel(f"Acc: -")
        self.lbl_msd = QLabel(f"Missed: -")
        self.lbl_avg = QLabel(f"Mean: -")
        self.lbl_min = QLabel(f"Min: -")
        self.lbl_max = QLabel(f"Max: -")
        self.lbl_stdev = QLabel(f"Stdev: -")
        self.btn_insp = QPushButton("Inspect")
        self.btn_insp.clicked.connect(self.toggle_inspect_mode)
        self.btn_insp.setShortcut(QKeySequence("Esc"))
        self.lbl_ct = QLabel("<hr/><b>Configuration</b>")

        try:
            with open(config_path, "rt") as file:
                config = yml.safe_load(file)
                ifce = config["Session"]["Interface"]
                dur = config["Session"]["Duration"]
                cam_po = config["Network"]["Camera"]["Port"]
                cam_pr = config["Network"]["Camera"]["Protocol"]
                cmd_po = config["Network"]["Command"]["Port"]
                cmd_pr = config["Network"]["Command"]["Protocol"]
                sesh = f'Interface: {ifce} ({f"{dur}s" if dur else "inf"})'
                cam = f"Camera: port {cam_po} ({cam_pr})"
                cmd = f"Command: port {cmd_po} ({cmd_pr})"
                cfg_txt = f"{sesh}\n{cam}\n{cmd}"
        except Exception as e:
            cfg_txt = f"Failed to load configuration: {e}"
        finally:
            self.lbl_cfg = QLabel(cfg_txt)

        # line-plot init..
        self.series = pg.PlotWidget()
        self.series.setBackground("#FFFFFF")
        self.series.getAxis("bottom").setLabel("RTC Frame")
        self.series.getAxis("left").setLabel("Latency", units=self.lat_unit)
        self.series.getAxis("left").setPen(self.base_pen)
        self.series.getAxis("bottom").setPen(self.base_pen)
        self.series.getAxis("left").setTextPen(self.base_pen)
        self.series.getAxis("bottom").setTextPen(self.base_pen)
        self.series.getPlotItem().layout.setContentsMargins(
            self.plot_padding, self.plot_padding, self.plot_padding, self.plot_padding
        )

        # histogram init..
        self.histogram = pg.PlotWidget()
        self.histogram.setBackground("#FFFFFF")
        self.histogram.getAxis("bottom").setLabel("Latency", units=self.lat_unit)
        self.histogram.getAxis("left").setLabel("Counts")
        self.histogram.getAxis("left").setPen(self.base_pen)
        self.histogram.getAxis("bottom").setPen(self.base_pen)
        self.histogram.getAxis("left").setTextPen(self.base_pen)
        self.histogram.getAxis("bottom").setTextPen(self.base_pen)
        self.histogram.getPlotItem().layout.setContentsMargins(
            self.plot_padding, self.plot_padding, self.plot_padding, self.plot_padding
        )

        # layout plots..
        plt_layout = QVBoxLayout()
        plt_layout.addWidget(self.series)
        plt_layout.addWidget(self.histogram)

        # layout stats panel..
        pnl_layout = QVBoxLayout()
        pnl_layout.addWidget(self.lbl_mt)
        pnl_layout.addWidget(self.lbl_buf)
        pnl_layout.addWidget(self.lbl_acc)
        pnl_layout.addWidget(self.lbl_msd)
        pnl_layout.addWidget(self.lbl_avg)
        pnl_layout.addWidget(self.lbl_min)
        pnl_layout.addWidget(self.lbl_max)
        pnl_layout.addWidget(self.lbl_stdev)
        pnl_layout.addWidget(self.btn_insp)
        pnl_layout.addWidget(self.lbl_ct)
        pnl_layout.addWidget(self.lbl_cfg)
        pnl_layout.addStretch()

        # layout gui..
        layout = QHBoxLayout()
        layout.addLayout(plt_layout)
        layout.addLayout(pnl_layout)
        self.setLayout(layout)

        # launch acc thread
        self.acc_t = dao_latency_acc("/tmp/tom.im.shm", buffer_cap)
        self.acc_t.sig_redraw.connect(self.redraw)
        self.acc_t.start()

    @pyqtSlot(np.ndarray, tuple)
    def redraw(self, buffer, metrics):
        if self.inspecting:
            return
        
        frame_nums, lats = buffer[0], buffer[1]
        buf_size, acc, msd = metrics

        # draw latency buffer..
        if not self.line_p:
            self.line_p = self.series.plot(
                frame_nums, lats, pen=self.plot_pen, antialias=True
            )
        else:
            self.line_p.setData(frame_nums, lats)

        # draw histogram of latency buffer..
        if self.bar_p:
            self.histogram.removeItem(self.bar_p)

        counts, bins = np.histogram(lats, bins=self.n_hist_bins)
        self.bar_p = pg.BarGraphItem(
            x=(bins[1:] + bins[:-1]) / 2,  # calc bin midpoints from edges.
            height=counts,
            width=bins[1] - bins[0],
            brush=QBrush(self.plot_pen.color()),
            pen=pg.mkPen(color="w"),
        )
        self.histogram.addItem(self.bar_p)

        # draw info panel..
        mean = np.mean(lats)
        min = np.min(lats)
        max = np.max(lats)
        stdev = np.std(lats)

        self.lbl_buf.setText(f"Buffer: {buf_size} / {self.buffer_cap}")
        self.lbl_acc.setText(f"Acc: {acc}")
        self.lbl_msd.setText(f"Missed: {msd}")
        self.lbl_avg.setText(f"Mean: {mean:.3f}{self.lat_unit}")
        self.lbl_min.setText(f"Min: {min:.3f}{self.lat_unit}")
        self.lbl_max.setText(f"Max: {max:.3f}{self.lat_unit}")
        self.lbl_stdev.setText(f"Stdev: {stdev:.3f}{self.lat_unit}")

    def toggle_inspect_mode(self):
        self.inspecting = not self.inspecting

# ============================================================ #

if __name__ == "__main__":
    app = QApplication([])
    gui = dao_latency_widget("../Cisco/config.yaml")
    gui.show()
    app.exec_()
