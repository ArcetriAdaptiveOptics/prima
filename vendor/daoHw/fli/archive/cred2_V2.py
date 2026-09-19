"""CRED-2 camera daemon.
"""
import sys, os
import ctypes
import numpy as np
sys.path.append(os.getenv('FLISDK_DIR')+'/Python/lib')
import FliSdk_V2 as FliSdk
import time
import dao

def get_roi(context) -> tuple[int, int, int, int]:
    """Get current region-of-interest on the camera.
    """
    res, isenabled, roi = FliSdk.GetCroppingState(context)
    w, h = FliSdk.GetCurrentImageDimension(context)
    if isenabled:
        return [roi.col1, roi.row1, roi.col2-roi.col1 + 1, roi.row2-roi.row1 + 1]
    else:
        return  [0,0,w,h]

def getImage(context):
    currentfilling = FliSdk.GetBufferFilling(context)
    n=0
    while n<1:
        if FliSdk.GetBufferFilling(context) != currentfilling:
            buffer=FliSdk.GetRawImageAsNumpyArray(context, -1)
            n=n+1
    return buffer
    
def setFps(context, fps):
    FliSdk.FliSerialCamera.SetFps(context, fps)
    time.sleep(0.05)
    getFps()
    
def getFps(context):
    fps = FliSdk.FliSerialCamera.GetFps(context)[-1]
    print('Current FPS %.1f'%fps)

def setTint(context, tInt):
    FliSdk.FliCredTwo.SetTint(context, tInt)
    time.sleep(0.05)
    getTint(fli_obj)
    
def getTint(context):
    Tint = FliSdk.FliCredTwo.GetTint(context)[-1]
    _, tIntMin, tIntMax = FliSdk.FliCredTwo.GetTintRange(context)
    print('Intergration time range [%.2e, %.2e] s'%(tIntMin,tIntMax))
    print('Intergation time set to %.2e s'%Tint)

def setTemp(context, temp):
    FliSdk.FliCredTwo.SetSensorTemp(context, temp)
    time.sleep(0.05)
    getTemp(context)
    
def getTemp(context):
    temp = FliSdk.FliCredTwo.GetAllTemp(context)[4]
    print('Current sensor temperature %.2f°C'%temp)
    
    
if __name__ == '__main__':
    fli_obj = FliSdk.Init()
    # call before DetectCameras or it fails for some reason ...
    grabbers_list = FliSdk.DetectGrabbers(fli_obj)
    cameras_list = FliSdk.DetectCameras(fli_obj)

    # if camera is available
    if cameras_list[0]!='Usb#' and len(cameras_list)>=1:
        res = FliSdk.SetCamera(fli_obj, cameras_list[0])
        FliSdk.Update(fli_obj)
    else:
        raise ConnectionError("No camera found...")
    FliSdk.Start(fli_obj)
    buffer=FliSdk.GetRawImageAsNumpyArray(fli_obj, -1)
    shm=dao.shm('/tmp/cred2.im.shm',buffer)
    '''
    currentfilling = FliSdk.GetBufferFilling(fli_obj)
    buffer=FliSdk.GetRawImageAsNumpyArray(fli_obj, -1)
    
    FliSdk.Stop(fli_obj)
    FliSdk.Exit(fli_obj)
    '''
    #capture_n_imgs(100)
