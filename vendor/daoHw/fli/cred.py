#!/usr/bin/env -S ipython3 -i
#

"""CRED-3 camera daemon minimum example.
"""
import sys, os
import ctypes
import numpy as np
sys.path.append(os.getenv('FLISDK_DIR')+'/Python/lib')
import FliSdk_V2 as FliSdk
import time
import dao
import threading

def get_roi() -> tuple[int, int, int, int]:
    """Get current region-of-interest on the camera.
    """
    res, isenabled, roi = FliSdk.GetCroppingState(fli_obj)
    w, h = FliSdk.GetCurrentImageDimension(fli_obj)
    if isenabled:
        return [roi.col1, roi.row1, roi.col2-roi.col1 + 1, roi.row2-roi.row1 + 1]
    else:
        return  [0,0,w,h]

def getImage(context):
    currentfilling = FliSdk.GetBufferFilling(fli_obj)
    n=0
    while n<1:
        if FliSdk.GetBufferFilling(fli_obj) != currentfilling:
            buffer=FliSdk.GetRawImageAsNumpyArray(context, -1)
            n=n+1
    return buffer

def setFps(context, fps):
    FliSdk.FliSerialCamera.SetFps(context, fps)

def setFps(context, fps):
    FliSdk.FliSerialCamera.SetFps(context, fps)
    time.sleep(0.05)
    getFps(context)
    
def getFps(context):
    fps = FliSdk.FliSerialCamera.GetFps(context)[-1]
    print('Current FPS %.1f'%fps)
    return fps

def setTint(context, tInt):
    if 'C-RED 3' in FliSdk.GetDetectedCameras(context)[0]:
        FliSdk.FliCredThree.SetTint(context, tInt)
    elif 'C-RED 2' in FliSdk.GetDetectedCameras(context)[0]:
        FliSdk.FliCredTwo.SetTint(context, tInt)
    else:
        print("Unsupported camera")
    time.sleep(0.05)
    getTint(context)
    
def getTint(context):
    tIntMin = 0
    tIntMax = 0
    tInt = 0
    if 'C-RED 3' in FliSdk.GetDetectedCameras(context)[0]:
        Tint = FliSdk.FliCredThree.GetTint(context)[-1]
        _, tIntMin, tIntMax = FliSdk.FliCredThree.GetTintRange(context)
    elif 'C-RED 2' in FliSdk.GetDetectedCameras(context)[0]:
        Tint = FliSdk.FliCredTwo.GetTint(context)[-1]
        _, tIntMin, tIntMax = FliSdk.FliCredTwo.GetTintRange(context)
    else:
        print("Unsupported camera")
    print('Intergration time range [%.2e, %.2e] s'%(tIntMin,tIntMax))
    print('Intergation time set to %.2e s'%Tint)
    return Tint

def setTemp(context, temp):
    if 'C-RED 3' in FliSdk.GetDetectedCameras(context)[0]:
        FliSdk.FliCredThree.SetSensorTemp(context, temp)
    elif 'C-RED 2' in FliSdk.GetDetectedCameras(context)[0]:
        FliSdk.FliCredTwo.SetSensorTemp(context, temp)
    else:
        print("Unsupported camera")
    time.sleep(0.05)
    getTemp(context)
   

def getTemp(context,disp=True):
    if 'C-RED 3' in FliSdk.GetDetectedCameras(context)[0]:
        temp = FliSdk.FliCredThree.GetAllTemp(context)[4]
    elif 'C-RED 2' in FliSdk.GetDetectedCameras(context)[0]:
        temp = FliSdk.FliCredTwo.GetAllTemp(context)[4]
    else:
        print("Unsupported camera")
    if disp:
    	print('Current sensor temperature %.2f°C'%temp)
    else:
    	return temp

def getGain(context):
    if 'C-RED 3' in FliSdk.GetDetectedCameras(context)[0]:
        gain = FliSdk.FliCredThree.GetConversionGain(context)[1]
        print('Conversion gain is %s'%gain)
    elif 'C-RED 2' in FliSdk.GetDetectedCameras(context)[0]:
        gain = FliSdk.FliCredTwo.GetConversionGain(context)[1]
        print('Conversion gain is %s'%gain)
    else:
        print('unsupported camera')

def setIGain(context, gain):
    print(f"Setting gain to {gain}")
    if gain == 0:
        setGain(context, 'low')
    elif gain == 1:
        setGain(context, 'medium')
    elif gain == 2:
        setGain(context, 'high')
    else:
        print("Gain is not valid, it should be 0, 1 or 2

def setGain(context, gain):
    if 'C-RED 3' in FliSdk.GetDetectedCameras(context)[0]:
        if gain in ['low','medium','high']:
            FliSdk.FliCredThree.SetConversionGain(context,gain)
            print('Conversion gain set to %s'%FliSdk.FliCredThree.GetConversionGain(context)[1])
        else:
            print("Gain is not valid, it should be 'low', 'medium' or 'high'")
    if 'C-RED 2' in FliSdk.GetDetectedCameras(context)[0]:
        if gain in ['low','medium','high']:
            FliSdk.FliCredTwo.SetConversionGain(context,gain)
            print('Conversion gain set to %s'%FliSdk.FliCredTwo.GetConversionGain(context)[1])
        else:
            print("Gain is not valid, it should be 'low', 'medium' or 'high'")
    else:
        print('Unsupported camera')

#def ROI(context, cx, cy, w, h):
#	col1 = int(cx - w//2) 
#	col2 = int(cx + w//2)
#	row1 = int(cy - h//2)
#	row2 = int(cy + h//2)
#	if 'C-RED 3' in FliSdk.GetDetectedCameras(context)[0]:
#        FliSdk.FliCredThree.SetAgcRoi(context, col1, col2, row1, row2)
#    elif 'C-RED 2' in FliSdk.GetDetectedCameras(context)[0]:
#        FliSdk.FliCredTwo.SetAgcRoi(context, col1, col2, row1, row2)
#    else:
#        print("Unsupported camera")
    
def imAcq(obj, shm):
    try:
        while 1:
            frame = getImage(obj)
            # frame = np.abs(frame - np.median(frame))
            shm.set_data(frame)
            # temp = getTemp(fli_obj, disp=False)
            #print("  Buffer: %5u/%5u, fps: %.1f, median: %.1f, maximum: %.1f, temp: %.1f"%(FliSdk.GetBufferFilling(fli_obj),FliSdk.GetImagesCapacity(fli_obj),FliSdk.GetImageReceivedRate(fli_obj),np.median(frame[1:,:]),np.max(frame[1:,:]),temp),end='\r')
            #print("  Buffer: %5u/%5u, fps: %.1f, median: %.1f, maximum: %.1f"%(FliSdk.GetBufferFilling(fli_obj),FliSdk.GetImagesCapacity(fli_obj),FliSdk.GetImageReceivedRate(fli_obj),np.median(frame[1:,:]),np.max(frame[10:-10,10:-10])),end='\r')
    except KeyboardInterrupt:
        print()
        print('End of acquisition')
    		
def fpsCtrl(obj, shm):
    while 1:
        fps = shm.get_data(check=True)[0,0]
        print(f"detection of new FPS : {fps} Hz, applying.")
        setFps(obj, fps)
	
def ditCtrl(obj, shm):
    while 1:
        dit = shm.get_data(check=True)[0,0]
        print(f"detection of new DIT : {dit} s, applying.")
        setTint(obj, dit)
	
def gainCtrl(obj, shm):
    while 1:
        gain = shm.get_data(check=True)[0,0]
        print(f"detection of new GAIN : {gain}, applying.")
        setIGain(obj, gain)
	
if __name__ == '__main__':
    fli_obj = FliSdk.Init()
    # call before DetectCameras or it fails for some reason ...
    grabbers_list = FliSdk.DetectGrabbers(fli_obj)
    cameras_list = FliSdk.DetectCameras(fli_obj)
    print(f"{len(cameras_list)} cameras detected")
    print("Select the camera")
    for k in range(len(cameras_list)):
        print(f"{k} : {cameras_list[k]}")
    print("select camera #:")
    camId = int(input())
    print(f"camera {camId} selected: {cameras_list[camId]}")
    print("select name for the shared memory: ")
    shmName = input()
    # if camera is available
    if cameras_list[0]!='Usb#' and len(cameras_list)>=1:
        res = FliSdk.SetCamera(fli_obj, cameras_list[camId])
        FliSdk.Update(fli_obj)
    else:
        raise ConnectionError("No camera found...")
    FliSdk.Start(fli_obj)
    buffer=FliSdk.GetRawImageAsNumpyArray(fli_obj, -1)
    shm=dao.shm(f"/tmp/{shmName}.im.shm",buffer)
    shmBg=dao.shm(f"/tmp/{shmName}Bg.im.shm",buffer.astype(np.float32)*0)
    shmDit=dao.shm(f"/tmp/{shmName}Dit.im.shm", 1000*getTint(fli_obj) * np.ones((1,1)).astype(np.float32))
    shmFps=dao.shm(f"/tmp/{shmName}Fps.im.shm", getFps(fli_obj) * np.ones((1,1)).astype(np.float32))
    shmGain=dao.shm(f"/tmp/{shmName}Gain.im.shm",np.zeros((1,1)).astype(np.float32))
    
    #FliSdk.FliSerialCamera.SendCommand(fli_obj, 'set led off')
    FliSdk.FliCred.EnableLed(fli_obj, False)

    acqThread = threading.Thread(target = imAcq, args = (fli_obj, shm))
    fpsCtrlThread = threading.Thread(target = fpsCtrl, args = (fli_obj, shmFps))
    ditCtrlThread = threading.Thread(target = ditCtrl, args = (fli_obj, shmDit))
    gainCtrlThread = threading.Thread(target = gainCtrl, args = (fli_obj, shmGain))
    fpsCtrlThread.start()
    ditCtrlThread.start()
    gainCtrlThread.start()
    acqThread.start()
