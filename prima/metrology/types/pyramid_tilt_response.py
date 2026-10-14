import numpy as np


class PyramidTiltResponse(object):


    def __init__(self,
                 tiltVectorInMilliRad,
                 signalVector,
                 modulationRadiusInMilliRad,
                 fiberSizeInMeter):
        self.tiltVectorInMilliRad= tiltVectorInMilliRad
        self.signalVector= signalVector
        self.modulationRadiusInMilliRad= modulationRadiusInMilliRad
        self.fiberSizeInMeter= fiberSizeInMeter
        assert tiltVectorInMilliRad.shape == signalVector.shape, \
            "Tilt and signal vector shape must be equal but are %s and %s" % (
                str(tiltVectorInMilliRad.shape), str(signalVector.shape))


    @staticmethod
    def createTheoreticalFor(modulationRadiusInMilliRad, fiberSize):
        signals= np.linspace(-1.0, 1.0, 100)
        gradient= modulationRadiusInMilliRad * np.sin(np.pi/ 2 * signals)
        return PyramidTiltResponse(gradient, signals,
                                   modulationRadiusInMilliRad, fiberSize)
