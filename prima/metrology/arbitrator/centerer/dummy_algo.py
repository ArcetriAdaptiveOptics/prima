from prima.metrology.arbitrator.centerer.algo import Algo
from prima.metrology._compat import returnsNone, returns, override
from prima.metrology._compat import Logger


_version__= "$Id$"


class DummyAlgo(Algo):


    def __init__(self):
        self._logger= Logger.of(self.__class__.__name__)
        self._gain= -1.0


    @override
    @returnsNone
    def step(self):
        self._logger.debug("One guiding step is done.")


    @override
    @returns(bool)
    def isOnTarget(self):
        return False


    @override
    @returnsNone
    def calibrate(self):
        self._logger.debug("Dummy calibration is done.")


    @override
    @returnsNone
    def storeCalibration(self, tag):
        self._logger.debug("Dummy calibration shall be stored at '%s'" % tag)


    @override
    @returnsNone
    def restoreCalibration(self, tag):
        self._logger.debug("Dummy calibration '%s' shall be restored." % tag)


    @override
    @returnsNone
    def setGain(self, gain):
        self._logger.debug("Dummy gain is set to %.1f" % gain)
        self._gain= gain


    @override
    @returns(float)
    def getGain(self):
        return float(self._gain)
