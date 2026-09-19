import dao
import daoHw
import numpy as np
import daoLaunch


class cameraControllerBob(daoHw.cameraController):
    def __init__(self, filename, device, controller="daoHwCBlueDeviceCtrl", tmuxname=None, width=1104, height=1104, multicast='224.1.1.1',datatype=np.uint16, offset=[0,0], clockShm='', clockSemNb=0):
        super().__init__(filename, device, controller=controller, tmuxname=tmuxname, width=width, height=height, multicast=multicast,datatype=datatype)
        self.offset = np.zeros((2,1)).astype(np.uint32)
        self.offset[0] = offset[0]
        self.offset[1] = offset[1]

        self.clockShm = clockShm     
        self.clockSemNb = clockSemNb
        
    def createShm(self,):
        """
        Creates shared memory segments for various camera parameters.
        """
        super().createShm()
        self.wfsOffset	= dao.shm(self.path + '/' + self.filename + "Pos"  + self.ext, self.offset)
    
    def loadShm(self,):
        super().loadShm()
        self.wfsOffset = dao.shm(self.path + '/' + self.filename + "Pos"  + self.ext, self.offset)
        
    def launch(self, ):
        args = f'-L {self.shm_file} {self.clockShm} {self.clockSemNb} 1 {self.multicast} {self.device}'
        daoLaunch.manage_process(action='launch', tmuxname=self.tmuxname, processExe=self.controller, processArgs=args)


    def setOffset(self, offset):
        self.offset = np.asarray(offset).astype(np.uint32)
        # self.offset[0] = offset[0]
        # self.offset[1] = offset[1]
        self.wfsOffset.set_data(self.offset)
    
    def getOffset(self,):
        self.offset = self.wfsOffset.get_data()
        return self.offset