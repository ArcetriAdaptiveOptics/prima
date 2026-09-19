import dao 
import logging
import os
import daoLaunch
import numpy as np
import screeninfo

class slmController:
    def __init__(self, filename, screen, controller="daoSLMOpenCv.py", tmuxname=None, width=None, height=None, imageType=np.uint8, update=100):
        self.log = logging.getLogger(__name__)
        self.shm_file = filename
        self.path, fullname = os.path.split(self.shm_file)
        filenameparts = fullname.split(".")
        self.filename = filenameparts[0]
        self.ext ="." + ".".join(filenameparts[1:])

        self.screen = screen
        self.controller = controller

        if tmuxname is not None:
            self.tmuxname = tmuxname
        else:
            self.tmuxname = f"daoSLM-{self.filename}"

        self.width = width
        self.height = height
        
        self.imageType = imageType

        self.connectShm = False
        self.update=update
    
    def launch(self,):
        """
        Launches the camera controller process using TMUX.
        """
        args = f'-s {self.shm_file}  -m {self.screen} -u {self.update}'
        if self.connectShm:
            daoLaunch.manage_process(action='launch', tmuxname=self.tmuxname, processExe=self.controller, processArgs=args)
        else:
            self.log.error('Not Connected to SHM')

    def kill(self,):
        """
        Terminates the camera controller process associated with the TMUX session.
        """
        daoLaunch.manage_process(action='kill', tmuxname=self.tmuxname)

    def createShm(self,):
        """
        Creates shared memory segments for various camera parameters.
        """
        if self.width is not None and self.height is not None:
            self.displayImage = dao.shm(self.path + '/' + self.filename + self.ext, np.zeros((self.width,self.height)).astype(np.uint8))
            self.connectShm = True
        else:
            screen = screeninfo.get_monitors()[self.screen]
            self.width, self.height = screen.width, screen.height
            self.displayImage = dao.shm(self.path + '/' + self.filename + self.ext, np.zeros((self.width,self.height)).astype(np.uint8))
            self.connectShm = True
    def loadShm(self):
        """
        Loads existing shared memory segments for camera parameters.
        """
        self.displayImage = dao.shm(self.path + '/' + self.filename + self.ext)
        self.connectShm = True