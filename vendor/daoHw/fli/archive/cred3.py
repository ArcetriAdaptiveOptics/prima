"""CRED-3 camera daemon minimum example.
"""
import sys, os
import ctypes
import numpy as np
sys.path.append(os.getenv('FLISDK_DIR')+'/Python/lib')
import FliSdk_V2 as FliSdk
import time
import dao

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
    shm=dao.shm('/tmp/cred3.im.shm',buffer)
    '''
    currentfilling = FliSdk.GetBufferFilling(fli_obj)
    buffer=FliSdk.GetRawImageAsNumpyArray(fli_obj, -1)
    
    FliSdk.Stop(fli_obj)
    FliSdk.Exit(fli_obj)
    '''
    #capture_n_imgs(100)
