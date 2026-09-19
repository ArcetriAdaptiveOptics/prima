import dao
import daoHw
import numpy as np
import subprocess
import os

class IportController(daoHw.cameraController):

    def createShm(self,):
        """
        Creates shared memory segments for various camera parameters.
        """
        super().createShm()
        self.wfsSerialCmdName = self.path + '/' + self.filename + "SCmd"  + self.ext
        self.wfsSerialRspName = self.path + '/' + self.filename + "SRsp"  + self.ext
        self.acqName        = self.path + '/' + self.filename + "Acq"  + self.ext
        self.wfsSerialCmd	= dao.shm(self.path + '/' + self.filename + "SCmd"  + self.ext, np.zeros((1024, 1)).astype(np.uint8))
        self.wfsSerialRsp   = dao.shm(self.path + '/' + self.filename + "SRsp"  + self.ext, np.zeros((1024, 1)).astype(np.uint8))
        self.acqShm         = dao.shm(self.path + '/' + self.filename + "Acq"  + self.ext, np.zeros((1, 1)).astype(np.uint8))

    def loadShm(self,):
        """
        Loads existing shared memory segments for camera parameters.
        """
        super().loadShm()
        self.wfsSerialCmdName = self.path + '/' + self.filename + "SCmd"  + self.ext
        self.wfsSerialRspName = self.path + '/' + self.filename + "SRsp"  + self.ext
        self.acqName        = self.path + '/' + self.filename + "Acq"  + self.ext
        self.wfsSerialCmd	= dao.shm(self.wfsSerialCmdName)
        self.wfsSerialRsp   = dao.shm(self.wfsSerialRspName)
        self.acqShm         = dao.shm(self.acqName)
        
    def SerialCommand(self, command):
        resp_counter = self.wfsSerialRsp.get_counter()   
        command+="\0" + "000000000000000000000000000000000000"
        self.wfsSerialCmd.set_data(np.frombuffer(command.encode('utf8'), dtype=np.uint8))
        fullResponse = self.wfsSerialRsp.get_data(check=True)
        newCounter = self.wfsSerialRsp.get_counter()
        if resp_counter == newCounter:
            fullResponse = self.wfsSerialRsp.get_data(check=True)
        null_index = np.where(fullResponse == 0)[0]
        return fullResponse[:null_index[0]].tobytes().decode('utf-8')
    
    def launchSerialControlGui(self):
        daoroot = os.getenv('DAOROOT')
        string = f"python {daoroot}/bin/daoIportSerialControl.py -c {self.wfsSerialCmdName} -r {self.wfsSerialRspName}"
        try:
            subprocess.Popen([string], shell=True)
            print("GUI script launched successfully.")
        except Exception as e:
            print(f"Error launching GUI script: {e}")

    def launchImageViewer(self):
        daoroot = os.getenv('DAOROOT')
        string = f"python {daoroot}/bin/daoImageRTD.py -s {self.wfsCamName}"
        try:
            subprocess.Popen([string], shell=True)
            print("GUI script launched successfully.")
        except Exception as e:
            print(f"Error launching GUI script: {e}")
            
    def startAcq(self):
        self.acqShm.set_data(self.acqShm.get_data()*0 + 1)
    
    def stopAcq(self):
        self.acqShm.set_data(self.acqShm.get_data()*0)