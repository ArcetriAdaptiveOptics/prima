import abc
from prima.metrology.types.measure import Measure
from prima.metrology._compat import returns

__version__= "$Id: $"


class AbstractMeasurementManager(object):


    @abc.abstractmethod
    def setPyramidGeometry(self, pyramidGeometry):
        assert False


    @abc.abstractmethod
    def getPyramidGeometry(self):
        assert False


    @abc.abstractmethod
    def setSlopesNormalizationInRadians(self, slopesNormalizationInRadians):
        assert False


    @abc.abstractmethod
    def setPupilScaleInMeterPerPx(self, pupilScaleInMeterPerPixel):
        assert False


    @abc.abstractmethod
    def getPupilScaleInMeterPerPx(self):
        assert False


    @abc.abstractmethod
    def addMeasurement(self, measurement):
        assert False


    @abc.abstractmethod
    def getMeasurementTags(self):
        assert False


    @abc.abstractmethod
    def getMeasurementFromTag(self, tag):
        assert False


    @abc.abstractmethod
    def getLastTag(self):
        assert False


    @abc.abstractmethod
    @returns(Measure)
    def takeAMeasurement(self,
                         framesToAverage=1,
                         snapshot={},
                         storeMeasurement=False):
        assert False


    @abc.abstractmethod
    def setPyramidTiltResponse(self, pyramidTiltResponse):
        assert False


    @abc.abstractmethod
    def getPyramidTiltResponse(self):
        assert False

