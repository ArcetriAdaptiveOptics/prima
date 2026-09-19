#!/usr/bin/env python3
#
import sys
import argparse
import typing
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QLineEdit, QPushButton, QTextEdit
from PyQt5.QtCore import QObject, QThread, pyqtSignal, Qt, QEvent
import dao
import numpy as np
import time
import datetime


class MonitorThread(QThread):
    valueChanged = pyqtSignal(str)

    def __init__(self, shm, parent=None):
        super().__init__(parent)
        self.shm = shm
        
    valueChanged = pyqtSignal(str)

    def run(self):
        while True:
            fullResponse = self.shm.get_data(check=True, semNb=5)
            null_index = np.where(fullResponse == 0)[0]
            self.valueChanged.emit(fullResponse[:null_index[0]].tobytes().decode('latin-1', errors='replace'))
            time.sleep(0.01)

class MyGUI(QWidget):
    def __init__(self, CmdShm, RspShm):
        super().__init__()
        self.CmdShm = CmdShm
        self.RspShm = RspShm
        
        self.command_shm = dao.shm(self.CmdShm)
        self.response_shm = dao.shm(self.RspShm)
        
        self.command_history = []
        self.history_index = 0
        
        self.initUI()

    def initUI(self):
        self.setWindowTitle('Iport Serial Commands')
        self.setGeometry(300, 300, 400, 300)

        # Widgets
        self.entry = QLineEdit(self)
        self.entry.setPlaceholderText('Enter text...')
        self.entry.installEventFilter(self)
        self.entry.returnPressed.connect(self.on_button_click)

        self.button = QPushButton('Send Command', self)
        self.button.clicked.connect(self.on_button_click)

        self.log_display = QTextEdit(self)
        self.log_display.setReadOnly(True)
        
        # Monitor Thread
        self.monitor_thread = MonitorThread(self.response_shm)
        self.monitor_thread.valueChanged.connect(self.update_display)
        self.monitor_thread.start()

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.entry)
        layout.addWidget(self.button)
        layout.addWidget(self.log_display)

        self.setLayout(layout)
        

    def eventFilter(self, obj, event):
        if obj is self.entry and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Up:
                self.show_previous_command()
                return True
            elif event.key() == Qt.Key_Down:
                self.show_next_command()
                return True
        return super().eventFilter(obj, event)
    
    def update_display(self, text):
        # Append text to the top of the log display
        self.log_display.insertPlainText(text)
        cursor = self.log_display.textCursor()
        cursor.movePosition(cursor.End)
        self.log_display.setTextCursor(cursor)
        self.log_display.ensureCursorVisible()
        # Move cursor to the top of the log display 
        #self.log_display.setTextCursor(cursor)
    
    def send_command(self, command):
        command+="\0" + "000000000000000000000000000000000000"
        self.command_shm.set_data(np.frombuffer(command.encode('utf8'), dtype=np.uint8))

    def on_button_click(self):
        text = self.entry.text()
        timestamp = datetime.datetime.now()
        timestamp = timestamp.strftime("%d-%m-%Y, %H:%M:%S")
        if text:
            if text and (not self.command_history or text != self.command_history[0]):
                self.command_history.insert(0, text)
            self.send_command(text)
            self.log_display.insertPlainText(f'Time: {timestamp}\nCommand: {text}\n')
            self.entry.clear()
            self.history_index = 0

    def show_previous_command(self):
        if self.history_index < len(self.command_history):
            self.entry.setText(self.command_history[self.history_index])
            self.history_index += 1

    def show_next_command(self):
        if self.history_index > 0:
            self.history_index -= 1
            if self.history_index == 0:
                self.entry.clear()
            else:
                self.entry.setText(self.command_history[self.history_index - 1])

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Simple GUI with log')
    parser.add_argument('-c', '--command-shm', help='Command string shm name', required=True)
    parser.add_argument('-r', '--response-shm', help='response string shm name', required=True)
    args = parser.parse_args()
    CmdShm = args.command_shm
    RspShm = args.response_shm
    
    app = QApplication(sys.argv)
    my_gui = MyGUI(CmdShm, RspShm)
    my_gui.show()
    sys.exit(app.exec_())
