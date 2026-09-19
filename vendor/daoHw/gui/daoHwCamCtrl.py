#!/usr/bin/env python3
#

from PyQt5.uic import loadUiType
import sys, getopt
from PyQt5 import QtCore
from PyQt5.QtWidgets import QApplication, QVBoxLayout, QHBoxLayout, QWidget
from PyQt5.QtCore import QRunnable, QThreadPool, pyqtSlot, QObject, pyqtSignal
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
import numpy as np
import time
import os
import re
import subprocess
import dao 


class SubprocessWorker(QRunnable):
    """
    Worker thread that runs a subprocess in the background.
    """
    def __init__(self, command):
        super(SubprocessWorker, self).__init__()
        self.command = command
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self):
        """Run the subprocess."""
        try:
            result = subprocess.run(self.command, check=True, capture_output=True, text=True)
            self.signals.finished.emit(result.stdout)  # Emit success signal with output
            # Try to extract the "xxx" from the line that contains "saving on xxx"
            match = re.search(r'saving in (.+)', result.stdout)
            if match:
                saving_path = match.group(1)  # This is the "xxx" part after "saving on"
                self.signals.path_extracted.emit(saving_path)  # Emit extracted path
        except subprocess.CalledProcessError as e:
            self.signals.error.emit(e.stderr)  # Emit error signal with error message

# Define signals to communicate between the thread and the main GUI thread
class WorkerSignals(QObject):
    """
    Defines the signals available from a running worker thread.
    """
    finished = pyqtSignal(str)  # Signal to emit when finished
    error = pyqtSignal(str)  # Signal to emit if an error occurs
    path_extracted = pyqtSignal(str)  # Signal to emit the extracted path (saving_path)

# get the directory of ui files
path = os.getenv('DAOROOT') + '/data/'
Ui_MainWindow, QMainWindow = loadUiType(os.path.join(path, 'daoHwCamCtrl.ui'))


class MplCanvas(FigureCanvas):
    """Matplotlib Canvas class to replace pyqtgraph"""
    def __init__(self, parent=None, width=5, height=4, dpi=100, im=np.zeros((128,128))):
        self.fig, self.ax = plt.subplots(figsize=(width, height), dpi=dpi)
        super(MplCanvas, self).__init__(self.fig)
        self.ax.set_aspect('equal')
        """Clear the axes and plot a new image with colorbar."""
        self.ax.clear()  # Clear the previous plot
        self.cax = self.ax.imshow(im, cmap='gray', origin='lower')
        self.fig.colorbar(self.cax)  # Initialize colorbar

    def plot_image(self, image, neg=False):
        dmax=image[10:].max()
        dmin=image[10:].min()
        self.cax.set_data(image)
        if neg==True:
            self.cax.set_clim(dmin,dmax)
        else:
            self.cax.set_clim(0,dmax)
        # Redraw the canvas
        self.draw()

class CamCtrlApp(QMainWindow, Ui_MainWindow):
    def __init__(self, shmName):
        super(CamCtrlApp, self).__init__()
        self.setupUi(self)
        self.threadpool = QThreadPool()  # Create a thread pool

        self.shmName = shmName
        # Create SHM object
        self.shmim = dao.shm(shmName)

        # Extract 'baseName'
        self.baseName = shmName.split('/')[-1].split('.')[0]
        self.shmDitName = f"/tmp/{self.baseName}Dit.im.shm"
        self.shmFpsName = f"/tmp/{self.baseName}Fps.im.shm"
        self.shmBgName = f"/tmp/{self.baseName}Bg.im.shm"
        self.shmBgPercentName = f"/tmp/{self.baseName}BgPercent.im.shm"
        self.shmPercentName = f"/tmp/{self.baseName}Percent.im.shm"
        self.shmDit = dao.shm(self.shmDitName)
        self.shmFps = dao.shm(self.shmFpsName)
        self.shmBg = dao.shm(self.shmBgName)
        self.shmBgP = dao.shm(self.shmBgPercentName, np.zeros((1,1)).astype(np.uint32))
        self.shmImP = dao.shm(self.shmPercentName, np.zeros((1,1)).astype(np.uint32))

        self.imageSizeX = self.shmim.get_data().shape[0]
        self.imageSizeY = self.shmim.get_data().shape[1]
        im=self.shmim.get_data().astype(np.float32)
        im=im.flatten().reshape((self.imageSizeX,self.imageSizeY))
        # Create matplotlib canvas and add to layout
        self.canvas = MplCanvas(self, width=5, height=4, dpi=100, im=im)

        # Add Matplotlib toolbar
        self.toolbar = NavigationToolbar(self.canvas, self)
        self.toolbar.setStyleSheet("background-color:White;")

        # Create layout for the image and toolbar
        layout = QVBoxLayout()
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)
        self.imageView.setLayout(layout)

        #  Update dit and Fps box with current value
        print(f"{self.shmFps.get_data()[0,0]}")
        self.ditBox.setValue(float(1000*self.shmDit.get_data()[0,0]))
        self.fpsBox.setValue(float(self.shmFps.get_data()[0,0]))

        # Get first image
        im = self.shmim.get_data().astype(np.float32)
        im=im.flatten().reshape((self.imageSizeX,self.imageSizeY))
        self.canvas.plot_image(im)

        # save first counter
        self.imCnt1 = self.shmim.get_meta_data()['cnt0']

        # Create QT timer to update display
        self.timer = QtCore.QTimer(self)
        # Throw event timeout with an interval of 50 milliseconds
        self.timer.setInterval(50)
        # each time timer counts done call self.Update
        self.timer.timeout.connect(self.Update)
        # save initial time for frequency display purpose
        self.t1 = time.time()

        # Connect buttons to their respective methods
        self.ditButton.clicked.connect(self.updateDit)
        self.fpsButton.clicked.connect(self.updateFps)
        self.acqButton.clicked.connect(self.acqData)
        self.acqAvgButton.clicked.connect(self.acqAvgData)
        self.acqBgButton.clicked.connect(self.acqBgData)
        self.resetBgButton.clicked.connect(self.resetBg)
        self.acqPercent = 0
        self.acqBgPercent = 0
        self.nbAcq = 1000
        self.nbBgAcq = 1000


    def Start(self):
        """Start timer."""
        self.timer.start()

    def Stop(self):
        """Stop timer."""
        self.timer.stop()

    @QtCore.pyqtSlot()
    def Update(self):
        """Update the GUI."""
        # Update the displayed image with the data of the SHM
        im = self.shmim.get_data().astype(np.float32)
        im=im.flatten().reshape((self.imageSizeX,self.imageSizeY))
        neg=False
        if self.bgCheckBox.isChecked():
            im = im - self.shmBg.get_data().flatten().reshape((self.imageSizeX,self.imageSizeY))
            neg=True
        self.canvas.plot_image(im, neg=neg)

        # Get the counter
        self.imCnt2 = self.shmim.get_counter()
        self.t2 = time.time()
        ellapsedTime = self.t2 - self.t1
        nbImage = self.imCnt2 - self.imCnt1
        # Display frequency
        self.freqLabel.setText(f'{nbImage/ellapsedTime:.2f} Hz')
        self.t1 = self.t2
        self.imCnt1 = self.imCnt2
        self.progressBar.setValue(self.shmImP.get_data()[0, 0])
        self.progressBgBar.setValue(self.shmBgP.get_data()[0, 0])
        # convert to ms
        self.ditStatusLabel.setText(str(1000*self.shmDit.get_data()[0,0]))
        self.fpsStatusLabel.setText(str(self.shmFps.get_data()[0,0]))

    def updateDit(self):
        """Call an external script to set the FPS"""
        # Command to call the external script
        command = ["python3", os.getenv("DAOROOT")+"/bin/daoHwSetDit.py", self.baseName, str(self.ditBox.value())]
        # Create a worker for the subprocess
        worker = SubprocessWorker(command)
        # Execute the worker in the background
        self.threadpool.start(worker)

    def updateFps(self):
        """Call an external script to set the FPS"""
        # Command to call the external script
        command = ["python3", os.getenv("DAOROOT")+"/bin/daoHwSetFps.py", self.baseName, str(self.fpsBox.value())]
        # Create a worker for the subprocess
        worker = SubprocessWorker(command)
        # Execute the worker in the background
        self.threadpool.start(worker)

    def acqData(self):
        """Call an external script to acquire background data."""
        # Command to call the external script
        command = ["python3", os.getenv("DAOROOT")+"/bin/daoTakeDataCubeNPY.py", self.shmName, str(self.nbFrameBox.value()), str(self.frameIdBox.value())]

        # Create a worker for the subprocess
        worker = SubprocessWorker(command)

        # Connect signals to update the GUI
        worker.signals.finished.connect(self.on_acq_done)
        worker.signals.error.connect(self.on_acq_error)
        worker.signals.path_extracted.connect(self.on_path_extracted)  # Connect to the slot to handle saving_path

        # Execute the worker in the background
        self.threadpool.start(worker)

        # Optionally update the label to show progress
        self.logLabel.setText("dataCube Acquisition in Progress...")
        self.frameIdBox.setValue(self.frameIdBox.value()+1)
    
    def acqAvgData(self):
        """Call an external script to acquire background data."""
        # Command to call the external script
        command = ["python3", os.getenv("DAOROOT")+"/bin/daoTakeAverageDataNPY.py", self.shmName, str(self.nbFrameBox.value()), str(self.frameIdBox.value())]

        # Create a worker for the subprocess
        worker = SubprocessWorker(command)

        # Connect signals to update the GUI
        worker.signals.finished.connect(self.on_acq_done)
        worker.signals.error.connect(self.on_acq_error)
        worker.signals.path_extracted.connect(self.on_path_extracted)  # Connect to the slot to handle saving_path

        # Execute the worker in the background
        self.threadpool.start(worker)

        # Optionally update the label to show progress
        self.logLabel.setText("dataAvg Acquisition in Progress...")
        self.frameIdBox.setValue(self.frameIdBox.value()+1)

    @pyqtSlot(str)
    def on_path_extracted(self, saving_path):
        """Handle the extracted saving path."""
        # Update the label or take any action with the extracted path
        print(f"Data saved at: {saving_path}")
        self.logLabel.setText(f"Data saved at: {saving_path}")

    @pyqtSlot(str)
    def on_acq_done(self, output):
        """Update the GUI when the dataCube acquisition is done."""
        self.logLabel.setText("Background Acquisition Done")
        self.acqPercent = 100
        self.progressBar.setValue(self.acqPercent)
        print(f"Script output: {output}")

    @pyqtSlot(str)
    def on_acq_error(self, error):
        """Handle any errors from the acq task."""
        self.logLabel.setText("Error in dataCube Acquisition")
        print(f"Error: {error}")

    def acqBgData(self):
        """Call an external script to acquire background data."""
        # Command to call the external script
        command = ["python3", os.getenv("DAOROOT")+"/bin/daoTakeBg.py", self.shmName, str(self.nbFrameBgBox.value())]

        # Create a worker for the subprocess
        worker = SubprocessWorker(command)

        # Connect signals to update the GUI
        worker.signals.finished.connect(self.on_acq_bg_done)
        worker.signals.error.connect(self.on_acq_bg_error)

        # Execute the worker in the background
        self.threadpool.start(worker)

        # Optionally update the label to show progress
        self.logBgLabel.setText("Background Acquisition in Progress...")

    @pyqtSlot(str)
    def on_acq_bg_done(self, output):
        """Update the GUI when the background acquisition is done."""
        self.logBgLabel.setText("Background Acquisition Done")
        self.acqBgPercent = 100
        self.progressBgBar.setValue(self.acqBgPercent)
        print(f"Script output: {output}")

    @pyqtSlot(str)
    def on_acq_bg_error(self, error):
        """Handle any errors from the background task."""
        self.logBgLabel.setText("Error in Background Acquisition")
        print(f"Error: {error}")

    def resetBg(self):
        self.shmBg.set_data(self.shmBg.get_data()*0)

if __name__ == '__main__':
    shmimName = '/tmp/image.im.shm'
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hs:", ["help", "shmimName="])
    except getopt.GetoptError:
        print('err, usage: daoHwCamCtrl.py -s <shmimName>')
        sys.exit(2)
    print(opts)
    print(args)
    for opt, arg in opts:
        if opt == '-h':
            print('daoHwCamCtrl.py -s <shmimName>')
            sys.exit()
        elif opt in ("-s", "--shm"):
            shmimName = str(arg)

    app = QApplication([])
    camCtrl = CamCtrlApp(shmimName)
    camCtrl.setWindowTitle(shmimName)
    camCtrl.show()
    camCtrl.Start()
    sys.exit(app.exec_())

