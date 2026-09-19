#!/usr/bin/env python3


from PyQt5.uic import loadUiType
import sys, getopt
from PyQt5 import QtCore
from PyQt5.QtWidgets import QApplication, QVBoxLayout, QHBoxLayout, QWidget, QPushButton
from PyQt5.QtCore import QRunnable, QThreadPool, pyqtSlot, QObject, pyqtSignal
from PyQt5.QtGui import QLinearGradient, QColor, QBrush, QIcon

import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
import numpy as np
import time
import os
import re
import subprocess
import dao 


from numpy.fft import fft2, fftshift
from maoppy.instrument import papyrus
from maoppy.psfmodel import Psfao, Turbulent
from maoppy.psffit import psffit
from scipy.ndimage import gaussian_filter
# Issues while trying to import TELESCOPE and DM from papylib.constant
# also imported clean_data from papylib.image

class dotdict(dict):
    """dot.notation access to dictionary attributes"""
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__

TELESCOPE = {'DIAMETER':1.52, # [m]
             'OBSTRUCTION':0.27 # ratio
             }

TELESCOPE = dotdict(TELESCOPE)

DM = {'D_CALIB':37.5, # [mm]
      'D_SKY':35.5, # [mm]
      'PITCH':2.5, # [mm]
      'NACT':241 # number of actuators
      }

DM = dotdict(DM)
# from papylib.image import clean_data
def center_cog(img, bkg, nx):
    """Center an image on its CoG"""
    cx,cy = compute_cog(img, bkg, integer=True)
    m_center = img[cy-nx//2:cy+nx//2,cx-nx//2:cx+nx//2]
    bkg_center = bkg[cy-nx//2:cy+nx//2,cx-nx//2:cx+nx//2]
    return m_center, bkg_center
def dead_pixel_map(bkg, maxi=0.2):
    """Compute the map of dead pixels"""
    bkg = bkg - np.median(bkg)
    return bkg > (bkg.max()*maxi)

def compute_cog(img, bkg, integer=False, low=0.1):
    """
    Compute the center of gravity of an image.
    Threshold pixels lower than `low*np.max(img)`
    """
    x = np.arange(0,img.shape[1])
    y = np.arange(0,img.shape[0])
    X,Y = np.meshgrid(x,y)
    img_filtered = (img - bkg) - np.median(img - bkg)
    img_filtered = np.clip(img_filtered - low*np.max(img_filtered), 0, None)
    cx = np.sum(img_filtered*X)/np.sum(img_filtered)
    cy = np.sum(img_filtered*Y)/np.sum(img_filtered)
    if integer:
        cx = int(np.round(cx))
        cy = int(np.round(cy))
    return cx, cy
def filter_dead_pixel(img, dead_pix_map):
    """Filter dead pixels"""
    img[np.where(dead_pix_map==1)] = np.median(img)
    return img
def clean_data(img, bkg, nx=None):
    """
    Clean an image: filter dead pixels, remove background.
    Crop the image to (nx,nx) pixels if the `nx` keyword is set.
    """
    dead_pix_map = dead_pixel_map(bkg)
    bkg_dp = filter_dead_pixel(bkg, dead_pix_map)
    img_dp = filter_dead_pixel(img, dead_pix_map)
    if nx is not None:
        img_dp, bkg_dp = center_cog(img_dp, bkg_dp, nx)
    return img_dp - bkg_dp


class SubprocessWorker(QRunnable):
    def __init__(self, command):
        super(SubprocessWorker, self).__init__()
        self.command = command
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self):
        try:
            result = subprocess.run(self.command, check=True, capture_output=True, text=True)
            self.signals.finished.emit(result.stdout)
            match = re.search(r'Saved to (.+)', result.stdout)
            if match:
                self.signals.path_extracted.emit(match.group(1))
        except subprocess.CalledProcessError as e:
            self.signals.error.emit(e.stderr)
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
Ui_MainWindow, QMainWindow = loadUiType(os.path.join(path, 'cblueGUI.ui'))


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
        self.rollingImageBuffer = np.zeros((100, im.shape[0], im.shape[1]))

        # image geometry (rows, cols) -- needed to clamp the ROI
        self.nrows, self.ncols = im.shape
        
        self.nx = 64
        self.sampling = 1.5#2.32
        
        self.onsky = False
        self.sr = np.nan
        self.theoretical_psf()

    def get_zoom_roi(self):
        """
        Return the currently displayed region as integer pixel indices.
        imshow puts pixel centres on integers, so the data edges are at -0.5.
        Returns dict with row/col bounds, half-open (usable directly as a slice).
        """
        xlim = sorted(self.ax.get_xlim())   # columns
        ylim = sorted(self.ax.get_ylim())   # rows (origin='lower')

        col_min = int(np.floor(xlim[0] + 0.5))
        col_max = int(np.ceil(xlim[1] + 0.5))
        row_min = int(np.floor(ylim[0] + 0.5))
        row_max = int(np.ceil(ylim[1] + 0.5))

        # clamp to the actual image
        col_min = max(0, col_min)
        col_max = min(self.ncols, col_max)
        row_min = max(0, row_min)
        row_max = min(self.nrows, row_max)

        self.roi = {'col_min': col_min, 'col_max': col_max,
                    'row_min': row_min, 'row_max': row_max,
                    'width':  col_max - col_min,
                    'height': row_max - row_min,
                    'cx': (col_min + col_max) // 2,
                    'cy': (row_min + row_max) // 2}
        return self.roi

    def reset_zoom(self):
        """Back to the full frame (autoscale is unreliable on images)."""
        self.ax.set_xlim(-0.5, self.ncols - 0.5)
        self.ax.set_ylim(-0.5, self.nrows - 0.5)
        self.draw()
    
    def otf(self,image):
        otf = abs(np.fft.fftshift(np.fft.ifft2(np.fft.fftshift(image))))
        otf = otf/otf.max() #TODO
        return otf
        
    def theoretical_psf(self):
        x  = (np.arange(self.nx)-self.nx/2)*self.sampling/self.nx
        X,Y = np.meshgrid(x,x)
        T = np.where(np.sqrt(X**2+Y**2)<=0.5, 1, 0)
        if self.onsky:
            T_central = np.where(np.sqrt(X**2+Y**2)<=0.3/2, 0, 1)
            T_full = T * T_central
        else:
            T_full = T
        T_tf = np.fft.fftshift(np.fft.fft2(np.fft.fftshift(T_full))) / np.sum(T_full)
        psf_theory = np.abs(T_tf)**2
        self.otf_theory = self.otf(psf_theory)
    
    def strehl_ratio(self, image):
        image_crop = self.cog(image)
        otf_image = self.otf(image_crop)
        SR = np.sum(otf_image) / np.sum(self.otf_theory)
        return SR 
            
    def cog(self, m):
        m = m - np.median(m)
        x = np.arange(0,m.shape[1])
        y = np.arange(0,m.shape[0])
        X,Y = np.meshgrid(x,y)
        cx = int(np.round(np.sum(m*X)/np.sum(m)))
        cy = int(np.round(np.sum(m*Y)/np.sum(m)))    
        m_center = m[cy-self.nx//2:cy+self.nx//2,cx-self.nx//2:cx+self.nx//2]
        return m_center

    def plot_image(self, image, saturation_lim=3500.0, neg=False, scale="Linear", rollingAverage=False):
        # access roi
        roi_file = os.path.join(os.getenv("DAODATA"), "inputs", "cblue_roi.txt")
        roi = {}
        with open(roi_file) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                roi[key.strip()] = int(value.strip())

        """Crop a frame to the ROI. cx is a column index, cy a row index."""
        w = roi['width']
        r0 = roi['cy'] - w // 2
        c0 = roi['cx'] - w // 2
        # select corresponding ROI

        # if image.shape[0] != self.rollingImageBuffer.shape[1] or image.shape[1] != self.rollingImageBuffer.shape[2]:
        #     self.rollingImageBuffer = np.zeros((100, image.shape[0], image.shape[1]))

        # --- Rolling buffer ---
        self.rollingImageBuffer[1:] = self.rollingImageBuffer[:-1]
        self.rollingImageBuffer[0] = image
        read_out_noise = np.mean(np.std(self.rollingImageBuffer, axis=0))

        if rollingAverage:
            temp_image = np.mean(self.rollingImageBuffer[:100], axis=0)
        else:
            temp_image = image.copy()

        # --- Nettoyage des valeurs négatives ---
        temp_image[temp_image < 0] = 0

        suptitle = ''
        if scale == "Linear":
            image_to_show = temp_image
        elif scale == "Sqrt":
            image_to_show = np.sqrt(temp_image)
        elif scale == "Log":
            image_to_show = np.log10(1 + temp_image)
        else:
            print(f"[WARN] Échelle inconnue '{scale}', utilisation de Linear.")
            image_to_show = temp_image

        # --- Mise à jour de l'affichage ---
        self.cax.set_data(image_to_show)
        dmax = image[10:].max()
        # --- Détermination du contraste ---
        dmax_scaled = np.nanmax(image_to_show[10:])
        dmin_scaled = np.nanmin(image_to_show[10:])
        if neg:
            self.cax.set_clim(dmin_scaled, dmax_scaled)
        else:
            self.cax.set_clim(0, dmax_scaled)

        # --- Texte du titre ---
        suptitle = ''
        if dmax > saturation_lim:
            suptitle += ' SATURATION'
        else:
            try:
                # self.sr = self.strehl_ratio(image[50:-50, 50:-50]) * 100
                self.sr = self.strehl_ratio(temp_image[r0:r0 + w, c0:c0 + w]) * 100

                if self.sr > 100:
                    self.sr = np.nan
            except Exception:
                self.sr = np.nan
            suptitle += f' SR={self.sr:.0f} %'

        self.fig.suptitle(suptitle, weight='bold')
        self.draw()

        return temp_image


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
        self.shmGainName = f"/tmp/{self.baseName}Gain.im.shm"
        self.shmTemp = f"/tmp/{self.baseName}Temp.im.shm"
        self.shmConvEfficiencyName = f"/tmp/{self.baseName}ConvEfficiency.im.shm"
        self.shmDit = dao.shm(self.shmDitName)
        self.shmFps = dao.shm(self.shmFpsName)
        self.shmBg = dao.shm(self.shmBgName)
        self.shmBgP = dao.shm(self.shmBgPercentName, np.zeros((1,1)).astype(np.uint32))
        self.shmImP = dao.shm(self.shmPercentName, np.zeros((1,1)).astype(np.uint32))
        self.shmGain = dao.shm(self.shmGainName)
        self.shmConvEfficiency = dao.shm(self.shmConvEfficiencyName, np.array([[0]], dtype=np.int8))
        self.shmTemp = dao.shm(self.shmTemp, np.array([[0]], dtype=np.float32))
        self.extractZoomButton = QPushButton("Extract Zoom as ROI")
        self.extractZoomButton.clicked.connect(self.extract_zoom_roi)

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
        # --- ROI button row ---
        roiRow = QHBoxLayout()
        self.extractZoomButton = QPushButton("Zoom → ROI")
        self.resetZoomButton   = QPushButton("Reset Zoom")
        self.extractZoomButton.clicked.connect(self.extract_zoom_roi)
        self.resetZoomButton.clicked.connect(self.reset_zoom)
        roiRow.addWidget(self.extractZoomButton)
        roiRow.addWidget(self.resetZoomButton)
        layout.addLayout(roiRow)

        self.imageView.setLayout(layout)

        #  Update dit and Fps box with current value
        print(f"{self.shmFps.get_data()[0,0]}")
        self.ditBox.setValue(float(1000*self.shmDit.get_data()[0,0]))
        self.fpsBox.setValue(float(self.shmFps.get_data()[0,0]))

        #Update gain and temperature with currunt value
        self.gainBox.setValue(float(self.shmGain.get_data()[0,0]))
        
       
        
        # Get first image
        im = self.shmim.get_data().astype(np.float32)
        im=im.flatten().reshape((self.imageSizeX,self.imageSizeY))
       
        ConEffstatus = self.convEfficiencyLabel.text()
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
        self.cblue_gain_button.clicked.connect(self.updateGain)
        self.launch_OG_process_button.clicked.connect(self.OG_process_launch)
        self.estimate_radius_button.clicked.connect(self.estimate_radius)
        self.cblue_temperature_button.clicked.connect(self.monitorTemp)
        self.convEfficiencyButton.clicked.connect(self.monitorConvEfficiency)
        self.estimateSeeingButton.clicked.connect(self.estimateSeeing)
        self.ogLoopButton.clicked.connect(self.og_start)
        
        
        self.acqPercent = 0
        self.acqBgPercent = 0
        self.nbAcq = 1000
        self.nbBgAcq = 1000

    def extract_zoom_roi(self):
        """Read the current matplotlib zoom and write it to the ROI spinboxes."""
        roi = self.canvas.get_zoom_roi()

        # square, even-sized ROI centred on the zoom (most cameras want even/aligned)
        width = max(roi['width'], roi['height'])
        width = int(np.clip(width - (width % 4), 
                            self.ImageWidthBox.minimum(),
                            self.ImageWidthBox.maximum()))

        self.ImageWidthBox.setValue(width)
        self.ImageCenterXBox.setValue(int(np.clip(roi['cx'], 0, self.ImageCenterXBox.maximum())))
        self.ImageCenterYBox.setValue(int(np.clip(roi['cy'], 0, self.ImageCenterYBox.maximum())))

        self.save_roi()
        self.logLabel.setText(f"ROI: w={width} cx={roi['cx']} cy={roi['cy']}")
        print(f"[ROI] rows {roi['row_min']}:{roi['row_max']}  cols {roi['col_min']}:{roi['col_max']}")

    def reset_zoom(self):
        self.canvas.reset_zoom()
        self.logLabel.setText("Zoom reset to full frame")

    def save_roi(self):
        """Persist the ROI so acquisition scripts / next startup can read it."""
        roi_file = os.path.join(os.getenv("DAODATA"), "inputs", f"{self.baseName}_roi.txt")
        os.makedirs(os.path.dirname(roi_file), exist_ok=True)
        with open(roi_file, "w") as f:
            f.write(f"width={self.ImageWidthBox.value()}\n")
            f.write(f"cx={self.ImageCenterXBox.value()}\n")
            f.write(f"cy={self.ImageCenterYBox.value()}\n")
        print(f"[ROI] saved to {roi_file}")
   
    def reset_zoom(self):
        """Reset matplotlib zoom"""
        self.canvas.reset_zoom()
        self.logLabel.setText("Zoom reset to full image")

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
            
        ConEffstatus = self.convEfficiencyLabel.text()   
        if ConEffstatus == 'Low':
            saturation_lim = 5000.0
        elif ConEffstatus == 'High':
            saturation_lim = 3500.0  
            
           
        scale_text = self.scaleComboBox.currentText()   
        useRollingAverage = self.rollingCheckBox.isChecked()
        im = self.canvas.plot_image(im, saturation_lim,  neg=neg, scale=scale_text, rollingAverage = useRollingAverage)
        self.saturationProgressBar.setValue(int(min(100, (im[20:-20, 20:-20].max() * 100)/saturation_lim)))
        # self.canvas.plot_image(im, neg=neg)

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
        self.ditStatusLabel.setText(str(self.shmDit.get_data()[0,0]/1000))
        self.fpsStatusLabel.setText(str(self.shmFps.get_data()[0,0]))
        self.gainStatusLabel.setText(str(self.shmGain.get_data()[0,0]))

    def updateDit(self):
        """Call an external script to set the FPS"""
        # Command to call the external script
        command = ["python3", os.getenv("DAOROOT")+"/bin/daoHwSetDit.py", self.baseName, str(self.ditBox.value())]
        # Create a worker for the subprocess
        worker = SubprocessWorker(command)
        # Execute the worker in the background
        self.threadpool.start(worker)
    def handle_finished(self, output):
        print("✔️ Process finished:\n", output)

    def handle_error(self, error):
        print("❌ Process error:\n", error)

    def handle_path(self, path):
        print("📁 Path extracted:", path)

        
    def estimate_radius(self):
        """Launch the modulation radius estimation in a new xterm terminal."""
        script_path = os.path.join(os.getenv("DAOROOT"), "bin", "modulationRadiusEstimation.py")

        subprocess.Popen([
            "xterm",
            "-hold",  # keep the terminal open after the command finishes
            "-e",     # execute the following command
            "python3", script_path
        ])
        
    def updateGain(self):
        """Call an external script to set the Gain"""
        # Command to call the external script
        command = ["python3", os.getenv("DAOROOT")+"/bin/daoHwSetGain.py", self.baseName, str(self.gainBox.value())]
        # Create a worker for the subprocess
        worker = SubprocessWorker(command)
        # Execute the worker in the background
        self.threadpool.start(worker)
    
    def monitorTemp(self):
        """Call arv-tool to get the camera temperature and display it"""
        # Command to get the temperature
        command = ["arv-tool-0.8", "-a", "169.254.123.124", "control", "DeviceTemperature"]

        # Create a worker for the subprocess
        worker = SubprocessWorker(command)

        # Connect the signal to a function to update the QLabel
        worker.signals.finished.connect(self.updateTemperatureLabel)

        # Execute the worker in the background
        self.threadpool.start(worker)
        
    def monitorConvEfficiency(self):
        """Call arv-tool to get the camera conversion efficiency and display it"""
        # Command to get the Conversion Efficiency
        command = ["arv-tool-0.8", "-a", "169.254.123.124", "control", "ConversionEfficiency"]

        # Create a worker for the subprocess
        worker = SubprocessWorker(command)

        # Connect the signal to a function to update the QLabel
        worker.signals.finished.connect(self.updateConversionEfficiencyLabel)

        # Execute the worker in the background
        self.threadpool.start(worker)
        
    def updateConversionEfficiencyLabel(self, output):
        """
        Update the QLabel with the extracted ConversionEfficiency value.
        output : the raw output from the arv-tool command (string).

        """
        output_bool = 1
        if output == "Low":
            output_bool = 0
        else:
            output_bool = 1
        self.shmConvEfficiency.set_data(np.array([[output_bool]], dtype=np.int8))
        if output:
            # Extract the value after '='
            parts = output.split('=')
            if len(parts) == 2:
                value = parts[1].strip()
                # Update the label with the extracted value
                self.convEfficiencyLabel.setText(value)
            else:
                # If the output format is unexpected, set to Unknown
                self.convEfficiencyLabel.setText("Unknown")
        else:
            self.convEfficiencyLabel.setText("No data")

            
    def estimateSeeing(self):
        
        #################################################
        try:
            def psf_metrics(img, bkg, is_sky=True, is_close_loop=True):
    
                nx = 128 # number of pixels for cropping
                nb_mode_control = 195
                elevation_deg = 80 # star elevation
    
              # FIXED PARAMETERS
                sampling_calib = 2.32 # from CRED3 data 05/03/2025
                wvl_sky = 635e-9  # visible vert
                wvl_calib = 635e-9  # calibrage aussi visible ou proche
    
                
    
                # DEFINITIONS
                rad2arcsec = 180/np.pi * 3600
    
                def get_otf(img):
                    return np.abs(fftshift(fft2(fftshift(img))))
    
               # Process PSF
                psf_c = clean_data(img, bkg, nx=nx)
    
                # ADAPT SKY or CALIB
                if is_sky:
                    sampling = sampling_calib * DM.D_CALIB/DM.D_SKY * wvl_sky/wvl_calib
                    papyrus.occ = TELESCOPE.OBSTRUCTION
                    wvl = wvl_sky
                else:
                    sampling = sampling_calib
                    papyrus.occ = 0
                    wvl = wvl_calib
    
                #  FIT with MODEL
                nb_act_lin = 1 + DM.D_CALIB/DM.PITCH
                papyrus.Nact = round(nb_act_lin * DM.D_SKY/DM.D_CALIB * np.sqrt(nb_mode_control/DM.NACT))
                
                ron = 10
                weights = 1/(gaussian_filter(psf_c, 2)+ron**2)
    
                if is_close_loop:
                    psfmodel = Psfao((nx,nx), system=papyrus, samp=sampling)
                    psfparam_guess = [0.09, 1e-4, 0.4, 0.5, 1, 0, 1.5]
                    fixed = [False, ]*7
                else:
                    psfmodel = Turbulent((nx,nx), system=papyrus, samp=sampling)
                    psfparam_guess = [0.09, 30]
                    fixed = [False, ]*2
                
                out = psffit(psf_c, psfmodel, psfparam_guess, weights=weights, fixed=fixed, max_nfev=30)
                
                # COMPUTE METRICS
                r0_zenith = out.x[0]/np.cos(np.pi/2-elevation_deg*np.pi/180)**(3/5)
                seeing = rad2arcsec*wvl/r0_zenith
                seeing_550 = seeing * (550e-9/wvl)**(-1/5)
                sr_psfao = psfmodel.strehlOTF(out.x)
                
                #Quality
                psf_norm = (psf_c-out.flux_bck[1])/out.flux_bck[0]
                error = np.sqrt(np.sum(np.abs(psf_norm-out.psf)**2))
                n1 = np.sqrt(np.sum(np.abs(psf_norm)**2))
                n2 = np.sqrt(np.sum(np.abs(out.psf)**2))
                
                return sr_psfao, seeing_550, 1-error/((n1+n2)/2)
               
            long_exp = np.mean(self.canvas.rollingImageBuffer, axis = 0)
            long_exp = long_exp[10:-10,10:-10]
            bkg = self.shmBg.get_data()[10:-10,10:-10]
            if self.bgCheckBox.isChecked():
                long_exp = long_exp + bkg
            sr,seeing_550,quality = psf_metrics(long_exp, bkg)
            self.seeingLabel.setText('s       : %.2f\"\nSr     : %.1f%%\nqlty : %u%%'%(seeing_550,100*sr,round(quality*100)))
        except Exception as e:
            self.seeingLabel.setText('ERROR!')
            print(f"estimateSeeing error: {e}")
            
        return
        
    
    def updateTemperatureLabel(self, output):
        """
        Uptate the QLabel with the temperature extracted and rounded to 1 decimal place.
        output : raw output from the arv-tool command (string).

        """
        if output:
            # Example output: "DeviceTemperature =  9.98797 C min:-3.40282e+38 max:3.40282e+38"
            try:
                # Extract the value after 'DeviceTemperature'
            
                parts = output.split('=')
                if len(parts) == 2:
                    # Get the part after '='  
                    temp_str = parts[1].strip()
                    # Extract the floating value before 'C'
                    temp_value_str = temp_str.split(' ')[0]  # "9.98797"
                    temp_value = float(temp_value_str)
                    # Round the temperature value
                    # Arrondir à 1 chiffre après la virgule
                    temp_rounded = round(temp_value, 1)
                    self.shmTemp.set_data(np.array([[temp_rounded]], dtype=np.float32))
                    # Update the label
                    self.tempStatusLabel.setText(f"{temp_rounded} °C")
                else:
                    self.tempStatusLabel.setText("Unknown")
            except Exception as e:
                print(f"Erreur parsing température: {e}")
                self.tempStatusLabel.setText("Error")
        else:
            self.tempStatusLabel.setText("No data")


    def updateFps(self):
        """Call an external script to set the FPS"""
        # Command to call the external script
        command = ["python3", os.getenv("DAOROOT")+"/bin/daoHwSetFps.py", self.baseName, str(self.fpsBox.value())]
        # Create a worker for the subprocess
        worker = SubprocessWorker(command)
        # Execute the worker in the background
        self.threadpool.start(worker)

    def acqData(self):
        command = ["python3", os.getenv("DAOROOT")+"/bin/telemetry_cblue.py",
                   str(self.nbFrameBox.value()),
                   "--width", str(self.ImageWidthBox.value()),
                   "--cx",    str(self.ImageCenterXBox.value()),
                   "--cy",    str(self.ImageCenterYBox.value())]
        worker = SubprocessWorker(command)
        worker.signals.finished.connect(self.on_acq_done)
        worker.signals.error.connect(self.on_acq_error)
        worker.signals.path_extracted.connect(self.on_path_extracted)
        self.threadpool.start(worker)
        self.logLabel.setText("dataCube Acquisition in Progress...")
    # def acqData(self):
    #     """Call an external script to acquire background data."""
    #     # Command to call the external script
    #     #daoTakeDataCubeFITS.py
    #     command = ["python3", os.getenv("DAOROOT")+"/bin/telemetry_cblue.py", str(self.nbFrameBox.value())]
    #     #command = ["python3", os.getenv("DAOROOT")+"/bin/daoTakeDataCubeFITS.py", str(self.nbFrameBox.value())]

    #     # Create a worker for the subprocess
    #     worker = SubprocessWorker(command)

    #     # Connect signals to update the GUI
    #     worker.signals.finished.connect(self.on_acq_done)
    #     worker.signals.error.connect(self.on_acq_error)
    #     worker.signals.path_extracted.connect(self.on_path_extracted)  # Connect to the slot to handle saving_path

    #     # Execute the worker in the background
    #     self.threadpool.start(worker)

    #     # Optionally update the label to show progress
    #     self.logLabel.setText("dataCube Acquisition in Progress...")
    #     # self.frameIdBox.setValue(self.frameIdBox.value()+1)
    
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

    @pyqtSlot(str)
    def on_acq_done(self, output):
        """Update the GUI when the dataCube acquisition is done."""
        saving_path = None
        for line in output.splitlines():
            if "Data saved to" in line:
                saving_path = line.split("Data saved to")[-1].strip()
                break

        if saving_path:
            self.logLabel.setText(f"Telemetry saved at: {saving_path}")
            print(f"Data saved at: {saving_path}")
        else:
            self.logLabel.setText("Telemetry saved: path not found")
            print("No saving path found in output")

        self.acqPercent = 100
        self.progressBar.setValue(self.acqPercent)

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

    
        
    def og_reset_calibration(self):
        """Delete the calibration flag to force recalibration next time."""
        flag_path = os.path.join(os.getenv("DAOROOT"), "tmp", "og_calibration_done.flag")
        if os.path.exists(flag_path):
            os.remove(flag_path)
            print("[INFO] Calibration flag removed — next OG start will re-run calibration.")
        else:
            print("[INFO] No calibration flag found.")

    def OG_process_launch(self):
        """Launch the OG calibration process."""
        script_path = os.path.join(os.getenv("DAOROOT"), "bin", "launchOGCalibration.py")
        n_frames = str(self.n_frames_box.value())
        subprocess.Popen(["xterm", "-hold", "-e", "python3", script_path, n_frames])
         # Create calibration flag  after calibration is done
        tmp_dir = os.path.join(os.getenv("DAOROOT"), "tmp")
        os.makedirs(tmp_dir, exist_ok=True)
        flag_path = os.path.join(tmp_dir, "og_calibration_done.flag")
        with open(flag_path, "w") as f:
            f.write("Calibration complete\n")
        print(f"[INFO] Calibration flag created at: {flag_path}")
    
    # def OG_process_launch(self):
    #     """Launch the OG calibration process."""
    #     script_path = os.path.join(os.getenv("DAOROOT"), "bin", "launchOGCalibration.py")
    #     n_frames = str(self.n_frames_box.value())
    #     self.calib_xterm = subprocess.Popen(["xterm", "-e", "python3", script_path, n_frames])
    #     self.flag_timer = QtCore.QTimer(self)
    #     self.flag_timer.timeout.connect(self.check_calibration_flag)
    #     self.flag_timer.start(1000)  # Vérifie toutes les secondes (1000 ms)

    # def check_calibration_flag(self):
    #     """Vérifie si le drapeau est là pour tuer xterm."""
    #     flag_path = os.path.join(os.getenv("DAOROOT"), "tmp", "og_calibration_done.flag")
        
    #     # Si le fichier existe, c'est que launchOGCalibration.py a terminé !
    #     if os.path.exists(flag_path):
    #         print("[INFO] Calibration terminée ! Exécution de xterm...")
    #         self.flag_timer.stop()  # On arrête de surveiller
            
    #         # On détruit la fenêtre xterm de force depuis la GUI
    #         if hasattr(self, 'calib_xterm') and self.calib_xterm.poll() is None:
    #             self.calib_xterm.kill()  # SIGKILL : destruction absolue


    def og_start(self):
            """Launch the OG computations and GUI without spawning a terminal."""
            n_frames = str(self.n_frames_box.value())
            script_path = os.path.join(os.getenv("DAOROOT"), "bin", "OGStartProcess.py")
            
            subprocess.Popen(
                ["xterm", "-hold", "-e", "python3", script_path, n_frames],
               
                stdin=subprocess.DEVNULL,  
                   
            )
            #  stdout=subprocess.DEVNULL,    start_new_session=True              stderr=subprocess.DEVNULL,

        
    def ensure_calibration_done():
        """Check if calibration flag exists; if not, run calibration."""
        tmp_dir = os.path.join(os.getenv("DAOROOT"), "tmp")
        flag_path = os.path.join(tmp_dir, "og_calibration_done.flag")

        if not os.path.exists(flag_path):
            print("[WARNING] Calibration not found. Launching calibration first...")
            script_calib = os.path.join(os.getenv("DAOROOT"), "bin", "launchOGCalibration.py")

            # Take a default number of images for calibration
            n_images = "500"
            subprocess.run(["python3", script_calib, n_images], check=True)

            # Verify that the calibration flag was created
            if not os.path.exists(flag_path):
                raise RuntimeError("Calibration failed or did not create flag file.")
            else:
                print("[INFO] Calibration completed successfully.")
        else:
            print("[INFO] Calibration flag detected — skipping calibration.")



        

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
    shmimName = '/tmp/cblue.im.shm'
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

    dao_root = os.getenv("DAOROOT")
    if dao_root:
        icon_path = os.path.join(dao_root, "data/GSC.png")
        if os.path.exists(icon_path):
            app.setWindowIcon(QIcon(icon_path))

    camCtrl = CamCtrlApp(shmimName)
    camCtrl.setWindowTitle(shmimName)
    camCtrl.show()
    camCtrl.Start()
    sys.exit(app.exec_())

