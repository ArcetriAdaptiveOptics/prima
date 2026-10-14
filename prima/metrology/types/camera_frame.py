import numpy as np

__version__= "$Id$"


class CameraFrame(object):

    def __init__(self,
                 rawArray,
                 counter=0):
        self._array= rawArray.astype(np.float64)
        self._counter = counter


    def __eq__(self, o):
        if self._counter != o.counter():
            return False
        if not np.array_equal(self._array, o.toNumpyArray()):
            return False
        return True


    def __ne__(self, o):
        return not self.__eq__(o)


    def __str__(self):
        return "frame-%d" % self._counter


    @staticmethod
    def fromNumpyArray(frameAsNumpyArray,
                       counter=0):
        return CameraFrame(
            frameAsNumpyArray,
            counter)


    def toNumpyArray(self):
        return self._array


    def counter(self):
        return self._counter


    def setCounter(self, counter):
        self._counter = counter
