import dao 
import logging
import os
import daoLaunch
import numpy as np
import subprocess


class cameraController:
    """
    A class that controls a camera device and manages shared memory (SHM) communication for various camera parameters.

    Args:
        filename (str): The base filename used for creating SHM segments.
        device (str): The camera device identifier.
        controller (str, optional): The controller type for the camera. Default is "daoHwAravisDeviceCtrl".
        tmuxname (str, optional): The name used for the TMUX session. If None, it defaults to the value of 'filename'.
        width (int, optional): The width of the camera frame. Default is 1104.
        height (int, optional): The height of the camera frame. Default is 1104.
        multicast (str, optional): The multicast address for communication. Default is '224.1.1.1'.

    Attributes:
        log: An instance of a logger for debugging purposes.
        shm_file (str): The path to the SHM file.
        path (str): The directory path of the SHM file.
        filename (str): The base filename without extension.
        ext (str): The file extension.
        controller (str): The camera controller type.
        tmuxname (str): The TMUX session name.
        width (int): The width of the camera frame.
        height (int): The height of the camera frame.
        device (str): The camera device identifier.
        multicast (str): The multicast address.

    Methods:
        createShm():
            Creates shared memory segments for various camera parameters.
            
        loadShm():
            Loads existing shared memory segments for camera parameters.
            
        launch():
            Launches the camera controller process using TMUX.
            
        kill():
            Terminates the camera controller process associated with the TMUX session.
            
        setExposureTime(dit):
            Sets the exposure time (DIT) in the camera's shared memory.
  
        getExposureTime(dit):
            Gets the exposure time (DIT) in the camera's shared memory.
            
        setFPS(fps):
            Sets the frames per second (FPS) in the camera's shared memory.

        getFPS():
            Gets the frames per second (FPS) in the camera's shared memory.

        setGain(fps):
            Sets the Gsin in the camera's shared memory.

        getGain():
            Gets the Gain in the camera's shared memory.
            
        getCamShm():
            Retrieves the shared memory segment for the camera frame.
    """
    def __init__(self, filename, device, controller="daoHwCBlueDeviceCtrl", tmuxname=None, width=1104, height=1104, multicast='224.1.1.1',datatype=np.uint16):
        """
        Initialize a cameraController instance.
        """
        self.log = logging.getLogger(__name__)
        self.shm_file = filename
        self.path, fullname = os.path.split(self.shm_file)
        filenameparts = fullname.split(".")
        self.filename = filenameparts[0]
        self.ext ="." + ".".join(filenameparts[1:])
        self.controller= controller

        if tmuxname is None:
            self.tmuxname = self.filename
        else:
            self.tmuxname = tmuxname

        self.log.debug(f"self.filename: {self.shm_file}")
        self.log.debug(f"path: {self.path}")
        self.log.debug(f"filename: {self.filename}")
        self.log.debug(f"ext: {self.ext}")
        self.log.debug(f"controller: {self.controller}")
        self.log.debug(f"tmuxname: {self.tmuxname}")
        
        self.datatype=datatype
        self.width=width
        self.height=height
        self.device = device
        self.multicast = multicast

    def createShm(self,):
        """
        Creates shared memory segments for various camera parameters.
        """
        print(self.filename)
        self.wfsCamName = self.path + '/' + self.filename + self.ext
        self.wfsCam 	= dao.shm(self.path + '/' + self.filename + self.ext, np.zeros((self.height,self.width)).astype(self.datatype))
        self.wfsCamDit 	= dao.shm(self.path + '/' + self.filename + "Dit"  + self.ext, np.zeros((1, 1)).astype(np.float32))
        self.wfsCamFps 	= dao.shm(self.path + '/' + self.filename + "Fps"  + self.ext, np.zeros((1, 1)).astype(np.float32))
        self.wfsCamGain = dao.shm(self.path + '/' + self.filename + "Gain" + self.ext, np.zeros((1, 1)).astype(np.float32))
        self.wfsCamBin 	= dao.shm(self.path + '/' + self.filename + "Bin"  + self.ext, np.zeros((1, 1)).astype(np.float32))

    def loadShm(self,):
        """
        Loads existing shared memory segments for camera parameters.
        """
        self.wfsCamName = self.path + '/' + self.filename + self.ext
        self.wfsCam 	= dao.shm(self.path + '/' + self.filename + self.ext)
        self.wfsCamDit 	= dao.shm(self.path + '/' + self.filename + "Dit"  + self.ext)
        self.wfsCamFps 	= dao.shm(self.path + '/' + self.filename + "Fps"  + self.ext)
        self.wfsCamGain = dao.shm(self.path + '/' + self.filename + "Gain" + self.ext)
        self.wfsCamBin 	= dao.shm(self.path + '/' + self.filename + "Bin"  + self.ext)

    def launch(self):
        """
        Launches the camera controller process using TMUX.
        """
        args = f'-L {self.shm_file} 1 {self.multicast} {self.device}'
        daoLaunch.manage_process(action='launch', tmuxname=self.tmuxname, processExe=self.controller, processArgs=args)

    def kill(self):
        """
        Terminates the camera controller process associated with the TMUX session.
        """
        daoLaunch.manage_process(action='kill', tmuxname=self.tmuxname)

    def setExposureTime(self, dit):
        """
        Sets the exposure time (DIT) in the camera's shared memory.
        
        Args:
            dit (float): The exposure time value to be set.
        """
        self.wfsCamDit.set_data((self.wfsCamDit.get_data()*0+dit).astype(np.float32))

    def getExposureTime(self):
        """
        Gets the exposure time (DIT) in the camera's shared memory.
        
        Returns:
            dit (float): The exposure time value in shared memory.
        """
        return self.wfsCamDit.get_data()

    def setFPS(self,fps):
        """
        Sets the frames per second (FPS) in the camera's shared memory.
        
        Args:
            fps (float): The frames per second value to be set.
        """
        self.wfsCamFps.set_data((self.wfsCamFps.get_data()*0+fps).astype(np.float32))

    def getFPS(self, shm=True):
        """
        Sets the frames per second (FPS) in the camera's shared memory.
        
        Returns:
            fps (float): The frames per second value from SHM
        """
        return self.wfsCamFps.get_data()
    
    def setGain(self,gain):
        """
        Sets the frames per second (FPS) in the camera's shared memory.
        
        Args:
            fps (float): The frames per second value to be set.
        """
        self.wfsCamGain.set_data((self.wfsCamFps.get_data()*0+gain).astype(np.float32))

    def getGain(self, shm=True):
        """
        Sets the frames per second (FPS) in the camera's shared memory.
        
        Returns:
            fps (float): The frames per second value from SHM
        """
        return self.wfsCamGain.get_data()
 
    def getCamShm(self):
        """
        Retrieves the shared memory segment for the camera frame.
        
        Returns:
            dao.shm: The shared memory segment containing camera frame data.
        """
        return self.wfsCam
    
    def launchImageViewer(self, RTD='daoImageRTD'):
        daoroot = os.getenv('DAOROOT')
        string = f"python {daoroot}/bin/daoImageRTD.py -s {self.wfsCamName}"
        try:
            subprocess.Popen([string], shell=True)
            print("GUI script launched successfully.")
        except Exception as e:
            print(f"Error launching GUI script: {e}")
            
if __name__=="__main__":
    log = logging.getLogger(__name__)
    log.setLevel(logging.DEBUG)
    shm = "/tmp/wfsImage.im.shm"
    a = "First Light Imaging-C-BLUE ONE 1.7 MP-01-00001cdab9df"
    # device ="\'First Light Imaging-C-BLUE ONE 1.7 MP-01-00001ee7a6e1\'"
    device = f"\'{a}\'"

    cblue = daoCblue(shm, device)

    # cblue.createShm()
    # cblue.launch()
    # cblue.setFPS(10)

