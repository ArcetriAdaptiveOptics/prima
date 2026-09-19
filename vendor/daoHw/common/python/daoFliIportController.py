import dao
import daoHw
import numpy as np
import subprocess
import os
import time
import multiprocessing
import functools
import signal
import queue
import threading
import re

class TimeoutError(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutError("Function timed out")

signal.signal(signal.SIGALRM, timeout_handler)

def with_timeout(timeout):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            signal.alarm(timeout)  # Set alarm
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                signal.alarm(0)  # Cancel alarm after function execution
        return wrapper
    return decorator

def shm_get_data(shm):
    return shm.get_data(check=True)
    
# Wrap the function with a timeout of 1 seconds
@with_timeout(1)
def shm_wrap_function(*args, **kwargs):
    return shm_get_data(*args, **kwargs)


class FliIportController(daoHw.IportController):
    def __init__(self, filename, device, controller="daoHwCBlueDeviceCtrl", tmuxname=None, width=1104, height=1104, multicast='224.1.1.1',datatype=np.uint16):
        super().__init__(filename, device, controller=controller, tmuxname=tmuxname, width=width, height=height, multicast=multicast,datatype=datatype)
        
    def kill(self,cameraOff=False):
        self.SetSensorTemp(15, block=True)
        #turn off camera
        if cameraOff:
            self.SerialCommand("")
        
        return super().kill()
    
    
    def SetSensorTemp(self,temp, block=False, tol = 1, sleep_time=1):
        if temp < -40 or temp >20:
            return "Error"
        else:
            string = self.SerialCommand(f"set temp sensor {temp}")
            if string == 'Result:OK\r\n':
                print("Temperature set successfully")
        
        if block:
            currnet_temp = self.GetSensorTemp()
            while abs(currnet_temp-temp) > tol:
                print(f"current temp: {currnet_temp}, target temp: {temp}, diff: {abs(currnet_temp-temp):.2f} (tol: {tol})", end="\r")
                time.sleep(sleep_time)
                currnet_temp = self.GetSensorTemp()
            
            print(f"Sensor now within temp tolerance: {currnet_temp}")

        else:
            return
    
    def GetSensorTemp(self,):
        string = self.SerialCommand("temp sensor")
        match = re.search(r'T\(°C\) sensor: (-?\d+\.\d+)', string)
        if match:
            return float(match.group(1))
        else:
            return None
        
    def SetFPS(self, fps):
        string = self.SerialCommand(f"set fps {fps}")
        if string == 'Result:OK\r\n':
            print(f"FPS set successfully to: {fps}")
            print(f"FPS now: {self.GetFPS()}")
        else:
            print(f"Setting FPS to {fps} failed.")
            
        
    def GetFPS(self,):
        string = self.SerialCommand("fps")
        match = re.search(r'Frames per second: (-?\d+\.\d+)', string)
        if match:
            return float(match.group(1))
        else:
            return None
    
    def SetTint(self,tint):
        string = self.SerialCommand(f"set tint {tint}")
        if string == 'Result:OK\r\n':
            print(f"Tint set successfully to: {tint}")
            print(f"Tint now: {self.GetTint()}")
        else:
            print(f"Setting Tint to {tint} failed.")
    
    def GetTint(self,):
        string = self.SerialCommand("tint")
        print(string)
        match= re.search(r'integration time for current configuration: (-?\d+\.\d+)', string)
        if match:
            return float(match.group(1))
        else:
            return None


    def SerialCommand(self, command, terminator="fli-cli>"):
        self.terminator = terminator #"fli-cli>"
        resp_counter = self.wfsSerialRsp.get_counter()
        resp_string = ""
        command+="\0" + "000000000000000000000000000000000000"
            
        self.wfsSerialCmd.set_data(np.frombuffer(command.encode('utf8'), dtype=np.uint8))
        running = True
        while(running):
            #time.sleep(0.1)
            try:
                fullResponse = shm_wrap_function(self.wfsSerialRsp)
            except TimeoutError as e:
                print(e)
                return "ERROR: Command unsucessfull, timeout"
            #fullResponse = self.wfsSerialRsp.get_data(check=True)
            null_index = np.where(fullResponse == 0)[0]
            print(fullResponse[:null_index[0]])
            new=fullResponse[:null_index[0]].tobytes().decode('utf-8')
            # print(new, end="")
            resp_string+=new
            if self.terminator in resp_string:
                index = resp_string.index(self.terminator)
                resp_string = resp_string[:index]
                running=False

        return resp_string
