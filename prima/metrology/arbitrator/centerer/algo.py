import abc
from prima.metrology._compat import returnsNone, returns

_version__= "$Id$"


class Algo(object, metaclass=abc.ABCMeta):

    @abc.abstractmethod
    @returnsNone
    def step(self):
        assert False


    @abc.abstractmethod
    @returns(bool)
    def isOnTarget(self):
        assert False


    @abc.abstractmethod
    @returnsNone
    def calibrate(self):
        assert False


    @abc.abstractmethod
    @returnsNone
    def storeCalibration(self, tag):
        assert False


    @abc.abstractmethod
    @returnsNone
    def restoreCalibration(self, tag):
        assert False


    @abc.abstractmethod
    @returnsNone
    def setGain(self, gain):
        assert False


    @abc.abstractmethod
    @returns(float)
    def getGain(self):
        return self._gain
