import dao 
import logging
import os
import daoLaunch
import numpy as np
import subprocess
import re
import socket
import struct
import fcntl

def get_device_ip(device_name):
    # Run the arv-tool-0.8 command and get its output
    result = subprocess.run(['arv-tool-0.8'], stdout=subprocess.PIPE)
    lines = result.stdout.decode('utf-8').split('\n')
    device_name = device_name.strip("'")

    for line in lines:
        # Check if the device name is in this line
        print(line)
        print(device_name)
        if device_name in line:
            # Extract the IP address using a regular expression
            match = re.search(r'\((.*?)\)', line)
            if match:
                return match.group(1)

    return None

def get_nic(ip_address):
    try:
        # Run the command to get the route information
        result = subprocess.run(['ip', 'route', 'get', ip_address], stdout=subprocess.PIPE, check=True)
        output = result.stdout.decode()

        # The output should contain the interface name after 'dev'
        parts = output.split()
        if 'dev' in parts:
            dev_index = parts.index('dev')
            if dev_index < len(parts) - 1:
                return parts[dev_index + 1]

    except subprocess.CalledProcessError:
        print(f"Failed to get route to {ip_address}")

    return None

def get_ip_address(ifname):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return socket.inet_ntoa(fcntl.ioctl(
        s.fileno(),
        0x8915,  # SIOCGIFADDR
        struct.pack('256s', ifname[:15].encode('utf-8'))
    )[20:24])

def get_packet_size(device_name):
    # Run the command and get the output
    cmd = f"arv-tool-0.8 -n {device_name} control GevSCPSPacketSize"
    output = subprocess.check_output(cmd, shell=True).decode('utf-8')
    # output = subprocess.run([cmd], stdout=subprocess.PIPE)
    print(output)

    # Use regex to find the packet size
    match = re.search(r'GevSCPSPacketSize = (\d+)', output)
    if match:
        packet_size = int(match.group(1))
        return packet_size

    return None

class cameraControllerSplit:
    """
    A class that controls a camera device and manages shared memory (SHM) communication for various camera parameters.

    Args:
        filename (str): The base filename used for creating SHM segments.
        device (str): The camera device identifier.
        controller (str, optional): The controller type for the camera. Default is "daoHwAravisDeviceCtrl".
        tmuxname (str, optional): The name used for the TMUX session. If None, it defaults to the value of 'filename'.
        width (int, optional): The width of the camera frame. Default is 1104.
        height (int, optional): The height of the camera frame. Default is 1104.
        port (str, optional): The port address for communication. Default is '224.1.1.1'.

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
        port (str): The port address.

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
            
        getCamShm():
            Retrieves the shared memory segment for the camera frame.
    """
    def __init__(self, filename, device, controller="daoHwCblueDeviceMain", receiver="daoGigeReaderV2", ip=None, tmuxname_controller=None, tmuxname_reader=None, width=1104, height=1104, port='30000', PayloadSize=None, datatype=np.uint16, rec_as_root=False):
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
        self.receiver  = receiver
        
        self.datatype=datatype
        self.width=width
        self.height=height
        self.device = device
        self.port = port
        self.RecAsRoot = rec_as_root

        if tmuxname_controller is None:
            self.tmuxname_controller = self.filename + "_controller"
        else:
            self.tmuxname_controller = tmuxname_controller
            
        if tmuxname_reader is None:
            self.tmuxname_reader = self.filename + "_reader"
        else:
            self.tmuxname_reader = tmuxname_controller
        
            
        if ip is None:
            camIp = get_device_ip(device)
            if camIp is None:
                print(f"Cannot find device: {self.device}")
                exit(-1)
            nic = get_nic(camIp)
            if nic is None:
                print(f"Cannot find nic associated with ip: {camIp}")
                exit(-1)
            
            ip = get_ip_address(nic)
            if ip is None:
                print(f"Cannot find nic associated with nic: {nic}")
                exit(-1)
            self.ip = ip
            
        else:
            print(f'ip: {ip}')
            self.ip = ip
        if PayloadSize is None:
            PayloadSize = get_packet_size(self.device)
        print(PayloadSize)
        self.PacketSize = PayloadSize
        
        if "V2" in receiver:
            self.payload = PayloadSize - 48 ## check size?
        else:
            self.payload = PayloadSize - 36 ## check size?
    
    
        print(f"device: {device}")
        print(f"self.filename: {self.shm_file}")
        print(f"path: {self.path}")
        print(f"filename: {self.filename}")
        print(f"ext: {self.ext}")
        print(f"controller: {self.controller}")
        print(f"reciver: {self.receiver}")
        print(f"tmuxname_controller: {self.tmuxname_controller}")
        print(f"tmuxname_reader: {self.tmuxname_reader}")
        print(f"ip: {self.ip}")
        print(f"payload: {self.payload}")
        

    def createShm(self,):
        """
        Creates shared memory segments for various camera parameters.
        """
        print(self.filename)
        self.CamName    = self.path + '/' + self.filename + self.ext
        self.Cam            = dao.shm(self.path + '/' + self.filename + self.ext, np.zeros((self.width,self.height)).astype(self.datatype))
        self.CamDit     = dao.shm(self.path + '/' + self.filename + "Dit"  + self.ext, np.zeros((1, 1)).astype(np.float32))
        self.CamFps     = dao.shm(self.path + '/' + self.filename + "Fps"  + self.ext, np.zeros((1, 1)).astype(np.float32))
        self.CamGain    = dao.shm(self.path + '/' + self.filename + "Gain" + self.ext, np.zeros((1, 1)).astype(np.float32))
        self.CamBin     = dao.shm(self.path + '/' + self.filename + "Bin"  + self.ext, np.zeros((1, 1)).astype(np.float32))
        self.CamAcq     = dao.shm(self.path + '/' + self.filename + "Acq"  + self.ext, np.zeros((1, 1)).astype(np.uint8))

    def loadShm(self,):
        """
        Loads existing shared memory segments for camera parameters.
        """
        self.CamName    = self.path + '/' + self.filename + self.ext
        self.Cam            = dao.shm(self.path + '/' + self.filename + self.ext)
        self.CamDit     = dao.shm(self.path + '/' + self.filename + "Dit"  + self.ext)
        self.CamFps     = dao.shm(self.path + '/' + self.filename + "Fps"  + self.ext)
        self.CamGain    = dao.shm(self.path + '/' + self.filename + "Gain" + self.ext)
        self.CamBin     = dao.shm(self.path + '/' + self.filename + "Bin"  + self.ext)
        self.CamAcq     = dao.shm(self.path + '/' + self.filename + "Acq"  + self.ext)

    def launchCamController(self):
        """
        Launches the camera controller process using TMUX.
        """
        device = '\\"' + self.device + '\\"'
        print(f"Device: {device}")
        args = f"-d {device} -f {self.shm_file} -r {self.port} -s {self.PacketSize}"
        print(args)
        daoLaunch.manage_process(action='launch', tmuxname=self.tmuxname_controller, processExe=self.controller, processArgs=args)
        
    def launchCamReader(self):
        """
        Launches the camera controller process using TMUX.
        """
        args = f"{self.ip} {self.port} {self.shm_file} {self.width} {self.height} {self.payload}"
        # daoLaunch.manage_process(action='launch', tmuxname=self.tmuxname_reader, processExe=self.receiver, processArgs=args)
        hostname = socket.gethostname()
        if self.RecAsRoot:
            daoLaunch.manage_process(action='launch', tmuxname=self.tmuxname_reader, processExe=self.receiver, processArgs=args, user='root' ,machine=hostname)
        else:
            daoLaunch.manage_process(action='launch', tmuxname=self.tmuxname_reader, processExe=self.receiver, processArgs=args)


    def launch(self):
        """
        Launches the camera controller and pixel reader process using TMUX sessions.
        """
        self.launchCamController()
        self.launchCamReader()

    def kill(self):
        """
        Launches the camera controller and pixel reader process using TMUX sessions.
        """
        self.killCamController()
        self.killPixelReader()     
        

    def killCamController(self):
        """
        Terminates the camera controller process associated with the TMUX session.
        """
        daoLaunch.manage_process(action='kill', tmuxname=self.tmuxname_controller)
        
    def killPixelReader(self):
        """
        Terminates the camera controller process associated with the TMUX session.
        """
        hostname = socket.gethostname()
        if self.RecAsRoot:
            daoLaunch.manage_process(action='kill', tmuxname=self.tmuxname_reader, machine=hostname, user='root')
        else:
            daoLaunch.manage_process(action='kill', tmuxname=self.tmuxname_reader)

            
    
    def restartCamController(self):
        self.killCamContoller()
        self.launchCamReader()

    def restartCamReader(self):
        self.killPixelReader()
        self.startCamReader()

    def restart(self):
        self.kill()
        self.launch()

    def setExposureTime(self, dit):
        """
        Sets the exposure time (DIT) in the camera's shared memory.
        
        Args:
            dit (float): The exposure time value to be set.
        """
        self.CamDit.set_data((self.CamDit.get_data()*0+dit).astype(np.float32))
        
    def startAcq(self):
        """
        sets a 1 in the acq shm to start the pixel acq
        
        Args:
            dit (uint8): The exposure time value to be set.
        """
        self.CamAcq.set_data((self.CamAcq.get_data()*0+1).astype(np.uint8))
        
    def stopAcq(self):
        """
        sets a 1 in the acq shm to start the pixel acq
        
        Args:
            dit (uint8): The exposure time value to be set.
        """
        self.CamAcq.set_data((self.CamAcq.get_data()*0).astype(np.uint8))

    def getExposureTime(self):
        """
        Gets the exposure time (DIT) in the camera's shared memory.
        
        Returns:
            dit (float): The exposure time value in shared memory.
        """
        return self.CamDit.get_data()

    def setFPS(self,fps):
        """
        Sets the frames per second (FPS) in the camera's shared memory.
        
        Args:
            fps (float): The frames per second value to be set.
        """
        self.CamFps.set_data((self.CamFps.get_data()*0+fps).astype(np.float32))

    def getFPS(self, shm=True):
        """
        Sets the frames per second (FPS) in the camera's shared memory.
        
        Returns:
            fps (float): The frames per second value from SHM
        """
        return self.CamFps.get_data()
 
    def getCamShm(self):
        """
        Retrieves the shared memory segment for the camera frame.
        
        Returns:
            dao.shm: The shared memory segment containing camera frame data.
        """
        return self.Cam

if __name__=="__main__":
    log = logging.getLogger(__name__)
    log.setLevel(logging.DEBUG)
    shm = "/tmp/cblue.im.shm"
    a = "First Light Imaging-C-BLUE ONE 1.7 MP-01-00001ee7a6e1"
    # device ="\'First Light Imaging-C-BLUE ONE 1.7 MP-01-00001ee7a6e1\'"
    device = f"\'{a}\'"

    cblue = cameraControllerSplit(shm,device)

    # cblue.createShm()
    # cblue.launch()
    # cblue.setFPS(10)