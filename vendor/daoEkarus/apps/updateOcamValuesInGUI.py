import dao
import numpy as np
import re

from time import sleep
from daoEkarusShmNames import *


def GetResponseFromOcam(input):
    resp_counter = wfsSerialRsp.get_counter()
    command = input
    command += "\0" + "000000000000000000000000000000000000"
    wfsSerialCmd.set_data(np.frombuffer(command.encode("utf8"), dtype=np.uint8))
    fullResponse = wfsSerialRsp.get_data(check=True)
    newCounter = wfsSerialRsp.get_counter()
    if resp_counter == newCounter:
        fullResponse = wfsSerialRsp.get_data(check=True)
    null_index = np.where(fullResponse == 0)[0]

    return fullResponse[: null_index[0]].tobytes().decode("utf-8")


def SortResponse(response):

    if "Gain" in response:
        match = re.search(r"Gain set to (\d+)", decoded_response)
        if match:
            current_gain = int(match.group(1))
            ocam2gainShm.set_data(ocam2gainShm.get_data() * 0 + current_gain)

    elif "Camera rate" in response:
        match = re.search(r"\[(\d+)\]", decoded_response)
        if match:
            current_fps = int(match.group(1))
            ocam2fpsShm.set_data(ocam2fpsShm.get_data() * 0 + current_fps)

    elif "Temperatures" in response:
        values = re.findall(r"\[(-?[\d.]+)\]", decoded_response)
        if values:
            current_temp = float(values[0])
            ocam2tempShm.set_data(ocam2tempShm.get_data() * 0 + current_temp)


wfsSerialCmd = dao.shm(SHM_OCAM_CMD)
wfsSerialRsp = dao.shm(SHM_OCAM_RSP)

ocam2gainShm = dao.shm(SHM_OCAM_GAIN)
ocam2fpsShm = dao.shm(SHM_OCAM_FPS)
ocam2tempShm = dao.shm(SHM_OCAM_TEMPERATURE)

sleep(15)

## Get current gain
while True:
    decoded_response = GetResponseFromOcam(input="gain")
    SortResponse(decoded_response)
    sleep(0.8)

    ## Get current fps
    decoded_response = GetResponseFromOcam(input="fps")
    SortResponse(decoded_response)
    sleep(0.8)

    ## Get current temp
    decoded_response = GetResponseFromOcam(input="temp")
    SortResponse(decoded_response)
    sleep(0.8)

    sleep(1)
