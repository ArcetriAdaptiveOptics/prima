#!/usr/bin/env python3
"""
PyQt5 GUI for Rittal CMC III PDU Control.

  - Background QThread polls status at ~1 Hz via rittal_pdu_controller.get_all_outlets()
  - On/Off commands are dispatched via subprocess to rittal_pdu_controller.py CLI
  - Table shows: Socket | Unit | Description | LED | Status | Toggle button

Requires:
    pip install PyQt5
"""

import os
import sys
import asyncio
import subprocess
from pathlib import Path
from datetime import datetime

# Suppress Mesa/libGL driver warnings that flood stderr
os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
os.environ.setdefault("MESA_LOG_LEVEL", "fatal")

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QLabel,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor, QFont

# ── Locate controller ─────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))
from rittal_pdu_controller import get_all_outlets          # status walk only

CONTROLLER = SCRIPT_DIR / "rittal_pdu_controller.py"      # CLI for on/off


# ── Background poller ─────────────────────────────────────────────────────────

class StatusPoller(QThread):
    """Runs get_all_outlets() in its own asyncio loop every second."""
    data_ready = pyqtSignal(list)   # list[dict]
    poll_error = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop = False

    @staticmethod
    def _run_loop(coro):
        """Run coroutine, then cancel any pending tasks pysnmp left behind."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            # Cancel leftover tasks (pysnmp handle_timeout coroutines)
            pending = asyncio.all_tasks(loop)
            if pending:
                for task in pending:
                    task.cancel()
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
            loop.close()

    def run(self):
        while not self._stop:
            try:
                outlets = self._run_loop(get_all_outlets())
                self.data_ready.emit(outlets)
            except Exception as exc:
                self.poll_error.emit(str(exc))
            # Sleep in 100 ms chunks so stop() is responsive
            for _ in range(10):
                if self._stop:
                    return
                self.msleep(100)

    def stop(self):
        self._stop = True
        self.wait()


# ── LED widget ────────────────────────────────────────────────────────────────

class LedLabel(QLabel):
    """Small circular LED rendered via stylesheet."""

    _STYLES = {
        True:  ("background-color:#00cc44; border:2px solid #004d1a; border-radius:10px;",),
        False: ("background-color:#cc2200; border:2px solid #550e00; border-radius:10px;",),
        None:  ("background-color:#888888; border:2px solid #333333; border-radius:10px;",),
    }

    def __init__(self):
        super().__init__()
        self.setFixedSize(20, 20)
        self.set_state(None)

    def set_state(self, on):
        self.setStyleSheet(self._STYLES[on][0])


# ── Main window ───────────────────────────────────────────────────────────────

# Table columns
_C_SOCK   = 0
_C_UNIT   = 1
_C_NAME   = 2
_C_LED    = 3
_C_STATUS = 4
_C_BTN    = 5


class PDUWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Rittal CMC III PDU Control")
        self.resize(760, 750)

        self._leds: dict[tuple, LedLabel]   = {}
        self._btns: dict[tuple, QPushButton] = {}
        self._outlets: list[dict] = []

        self._build_ui()
        self._start_poller()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        vbox = QVBoxLayout(root)
        vbox.setContentsMargins(10, 8, 10, 4)
        vbox.setSpacing(6)

        # Title
        title = QLabel("Rittal CMC III — PDU Socket Control")
        f = QFont()
        f.setPointSize(13)
        f.setBold(True)
        title.setFont(f)
        vbox.addWidget(title)

        # Table
        self._tbl = QTableWidget(0, 6)
        self._tbl.setHorizontalHeaderLabels(
            ["Socket", "Unit", "Description", "", "Status", "Action"]
        )
        hh = self._tbl.horizontalHeader()
        hh.setSectionResizeMode(_C_SOCK,   QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(_C_UNIT,   QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(_C_NAME,   QHeaderView.Stretch)
        hh.setSectionResizeMode(_C_LED,    QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(_C_STATUS, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(_C_BTN,    QHeaderView.ResizeToContents)
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tbl.setSelectionMode(QTableWidget.NoSelection)
        self._tbl.setAlternatingRowColors(True)
        self._tbl.setFocusPolicy(Qt.NoFocus)
        vbox.addWidget(self._tbl)

        # Status bar
        self._status_lbl = QLabel("Connecting…")
        self.statusBar().addWidget(self._status_lbl)

    # ── Poller ────────────────────────────────────────────────────────────────

    def _start_poller(self):
        self._poller = StatusPoller(self)
        self._poller.data_ready.connect(self._on_data)
        self._poller.poll_error.connect(self._on_error)
        self._poller.start()

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_data(self, outlets: list):
        self._outlets = outlets
        ts = datetime.now().strftime("%H:%M:%S")
        self._status_lbl.setText(
            f"Updated: {ts}  |  {len(outlets)} sockets"
        )
        if self._tbl.rowCount() != len(outlets):
            self._rebuild_table(outlets)
        else:
            self._refresh_rows(outlets)

    def _on_error(self, msg: str):
        self._status_lbl.setText(f"Poll error: {msg}")
        for led in self._leds.values():
            led.set_state(None)

    # ── Table helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _key(o: dict) -> tuple:
        return (o["unit"], o["socket"])

    def _rebuild_table(self, outlets: list):
        """Full table rebuild — called when row count changes."""
        self._tbl.setRowCount(0)
        self._leds.clear()
        self._btns.clear()

        for row, o in enumerate(outlets):
            self._tbl.insertRow(row)
            key = self._key(o)
            is_on = o["status"] == "ON"

            # Socket number
            itm = QTableWidgetItem(str(o["socket"]))
            itm.setTextAlignment(Qt.AlignCenter)
            self._tbl.setItem(row, _C_SOCK, itm)

            # Unit
            itm = QTableWidgetItem(o["unit"])
            itm.setTextAlignment(Qt.AlignCenter)
            self._tbl.setItem(row, _C_UNIT, itm)

            # Description
            self._tbl.setItem(row, _C_NAME, QTableWidgetItem(o["name"]))

            # LED (in a centred container)
            led = LedLabel()
            led.set_state(is_on)
            self._leds[key] = led
            led_wrap = self._centred(led)
            self._tbl.setCellWidget(row, _C_LED, led_wrap)

            # Status text
            self._tbl.setItem(row, _C_STATUS, self._status_item(o["status"]))

            # Toggle button (in a centred container)
            btn = QPushButton()
            btn.setFixedWidth(90)
            self._btns[key] = btn
            self._update_btn(btn, o)
            btn.clicked.connect(lambda _checked, outlet=o: self._toggle(outlet))
            self._tbl.setCellWidget(row, _C_BTN, self._centred(btn))

            self._tbl.setRowHeight(row, 34)

    def _refresh_rows(self, outlets: list):
        """Lightweight update — only change values that may have flipped."""
        for row, o in enumerate(outlets):
            key = self._key(o)
            is_on = o["status"] == "ON"

            if key in self._leds:
                self._leds[key].set_state(is_on)

            itm = self._tbl.item(row, _C_STATUS)
            if itm:
                itm.setText(o["status"])
                itm.setForeground(
                    QColor("#006622") if is_on else QColor("#990000")
                )

            if key in self._btns:
                btn = self._btns[key]
                self._update_btn(btn, o)
                try:
                    btn.clicked.disconnect()
                except RuntimeError:
                    pass
                btn.clicked.connect(lambda _checked, outlet=o: self._toggle(outlet))

    # ── Toggle via CLI ────────────────────────────────────────────────────────

    def _toggle(self, outlet: dict):
        action = "off" if outlet["status"] == "ON" else "on"
        unit   = outlet["unit"].lower()
        socket = str(outlet["socket"])
        cmd = [sys.executable, str(CONTROLLER), action, unit, socket]
        subprocess.Popen(cmd)   # fire-and-forget; 1 Hz poll updates the UI

    # ── Widget factories ──────────────────────────────────────────────────────

    @staticmethod
    def _centred(widget: QWidget) -> QWidget:
        wrap = QWidget()
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.addWidget(widget, alignment=Qt.AlignCenter)
        return wrap

    @staticmethod
    def _status_item(status: str) -> QTableWidgetItem:
        itm = QTableWidgetItem(status)
        itm.setTextAlignment(Qt.AlignCenter)
        itm.setForeground(
            QColor("#006622") if status == "ON" else QColor("#990000")
        )
        return itm

    @staticmethod
    def _update_btn(btn: QPushButton, o: dict):
        is_on = o["status"] == "ON"
        btn.setText("Turn OFF" if is_on else "Turn ON")
        if is_on:
            btn.setStyleSheet(
                "QPushButton{background:#cc3333;color:white;border-radius:4px;"
                "padding:4px 8px;font-weight:bold;}"
                "QPushButton:hover{background:#ee4444;}"
                "QPushButton:pressed{background:#aa2222;}"
            )
        else:
            btn.setStyleSheet(
                "QPushButton{background:#2d7a2d;color:white;border-radius:4px;"
                "padding:4px 8px;font-weight:bold;}"
                "QPushButton:hover{background:#3a9e3a;}"
                "QPushButton:pressed{background:#1e5c1e;}"
            )

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        self._poller.stop()
        super().closeEvent(event)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = PDUWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
