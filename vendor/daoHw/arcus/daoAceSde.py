'''
 # @ Author: Thomas N. Davies
 # @ Company: Centre for Advanced Instrumentation, Durham University
 # @ Contact: thomas.n.davies@durham.ac.uk
 # @ Create Time: 2025-11-11 14:36:51
 # @ Description: Control library for Arcus ACE-SDE motor controller (Windows USB & Serial interfaces supported).
 '''
 
from ctypes import wintypes
from serial import Serial
import platform
import ctypes

class ACE_SDE:
    DEVICE_BAUDRATE: int = 9600 # from device docs.
    BUFFER_SIZE: int = 64 # Device expects 64 character buffers for read/write.

    def __init__(self, serialPort: str = None):
        self.device = None
        if serialPort:
            try:
                self.device = Serial(serialPort, self.DEVICE_BAUDRATE, write_timeout=1, timeout=1)
                self.send = self.send_serial_
                self.cleanup = lambda: self.device.close()
                self.commsType = f"Serial ({serialPort})"
            except Exception as e:
                raise RuntimeError(f"Failed to open connection to device: {e}")
        elif platform.system() == "Windows":
            self.load_usb_symbols_()
            self.device = wintypes.HANDLE()
            if not self.devOpen(0, ctypes.byref(self.device)):
                raise RuntimeError("Failed to open connection to device")
            self.commsType = "USB"
        else:
            raise RuntimeError("USB interface only supported on Windows - use serial instead!")

        devName = self.send("DN")
        devVer = self.send("VER")
        print(f"Connection: {self.commsType}")
        print(f"Device: {devName} ({devVer})")

    def __del__(self):
        if self.device:
            self.send("STOP")
            self.send("EO=0")
            self.cleanup()

    def load_usb_symbols_(self):
        ''' Windows USB support '''
        
        # attempt to load Performax DLL.
        try:
            lib = ctypes.WinDLL("./PerformaxCom.dll")
        except Exception as e:
            raise RuntimeError(f"Failed to load PerformaxCom DLL: {e}")
    
        # attempt to load required symbols from the DLL.
        try:
            self.devOpen = getattr(lib, "_fnPerformaxComOpen@8")
            self.devClose = getattr(lib, "_fnPerformaxComClose@4")
            self.devFlush = getattr(lib, "_fnPerformaxComFlush@4")
            self.devSend = getattr(lib, "_fnPerformaxComSendRecv@20")

            self.devOpen.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
            self.devOpen.restype = wintypes.BOOL
            
            self.devClose.argtypes = [wintypes.HANDLE]
            self.devClose.restype = wintypes.BOOL

            self.devFlush.argtypes = [wintypes.HANDLE]
            self.devFlush.restype = wintypes.BOOL

            self.devSend.argtypes = [
                wintypes.HANDLE,
                wintypes.LPVOID,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.LPVOID,
            ]
            self.devSend.restype = wintypes.BOOL
            
            self.cleanup = lambda: self.devClose(self.device)
            self.send = self.send_usb_
        except Exception as e:
            raise RuntimeError(f"Failed to import DLL symbols: {e}")
    
    def send_serial_(self, command: str, tx_prefix: str = "01") -> str:
        ''' Sends command to device over serial port and returns response '''
        
        # send command to device over serial port.
        data_send = bytes(f"@{tx_prefix}{command}\r", "ascii")
        if self.device.write(data_send) != len(data_send):
            raise RuntimeError(f"Failed to send command '{command}' to device")
        
        # read response back and handle potential errors.
        response: str = self.device.read(self.BUFFER_SIZE).decode("ascii").rstrip()
        if not len(response):
            raise RuntimeError(f"Device failed to respond to command '{command}'")
        elif response[0] == '?':
            raise RuntimeError(f"Device responded with error to command '{command}': '{response}'")
        
        return response
    
    def send_usb_(self, command: str) -> str:
        ''' Sends command to device over USB and returns response '''
        
        recv = ctypes.create_string_buffer(self.BUFFER_SIZE)
        data = ctypes.c_char_p(bytes(command, "ascii"))
        status = self.devSend(self.device, data, self.BUFFER_SIZE, self.BUFFER_SIZE, recv)
        response = recv.value.decode("ascii")

        if not status:
            raise RuntimeError(f"Failed to send command '{command}' to device")
        elif response[0] == '?':
            raise RuntimeError(f"Bad response to command '{command}': {response}")
        else:
            return response
        
