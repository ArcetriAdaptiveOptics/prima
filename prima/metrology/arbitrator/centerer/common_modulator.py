import time
import numpy as np

__version__="$Id$"


class CommonModulator(object):

    def __init__(self, modulatorClient, timeModule=time):
        self._modulatorClient= modulatorClient
        self._timeModule= timeModule


    @staticmethod
    def delta(axis0, axis1):
        return np.array([axis0, axis1])


    def _offsetModulatorCenter(self, offsetInMilliRad):
        self._modulatorClient.offsetCenterByMilliRad(offsetInMilliRad)
