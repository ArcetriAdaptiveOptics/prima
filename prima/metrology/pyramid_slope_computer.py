import numpy as np
from prima.metrology.types.pyramid_pupils import PyramidPupils, PyramidPupilsNames
from prima.metrology.types.pyramid_pupils import PyramidPupilsNames as pupNames
from prima.metrology.types.slopes import Slopes
from prima.metrology._compat import override, returns
from prima.metrology.abstract_slope_computer import AbstractSlopeComputer
from prima.metrology.types.pyramid_pupils_geometry import PyramidPupilsGeometry
from prima.metrology.types.region_of_interest import RegionOfInterest
from prima.metrology._compat import Logger
from scipy.interpolate import interp1d


__version__ = "$Id$"


class PyramidSlopeComputer(AbstractSlopeComputer):

    def __init__(self):
        self._pupils= None
        self._pupilsGeometry= None
        self._centralPixelCoordinates= None
        self._signalToGradientConversionFunction= \
            self.signalsToGradientConversionFromGeometricalTheory(1)
        self._createLogger()


    def _createLogger(self):
        self._logger= Logger.of('Pyramid Slope Computer')


    def __getstate__(self):
        odict = self.__dict__.copy()
        del odict['_logger']
        return odict


    def __setstate__(self, d):
        self.__dict__.update(d)
        self._createLogger()


    def setPupils(self, pupils):
        assert isinstance(pupils, PyramidPupils)
        self._pupils= pupils


    def setPupilsGeometry(self, pupilsGeometry):
        assert isinstance(pupilsGeometry, PyramidPupilsGeometry)
        self._pupilsGeometry= pupilsGeometry


    def setCentralPixelBetweenPupils(self, centralPixelCoordinates):
        self._centralPixelCoordinates= centralPixelCoordinates


    def signalsToGradientConversionFromGeometricalTheory(
            self,
            maxGradientInRadians):
        sig= np.linspace(-1, 1, 101)
        return interp1d(sig,
                        maxGradientInRadians * np.sin(np.pi/ 2 * sig),
                        kind='cubic')


    def _signalsToGradientInRadians(self, signal):
        clippedSignal= np.clip(
            signal.filled(0),
            self._signalToGradientConversionFunction.x.min(),
            self._signalToGradientConversionFunction.x.max())
        try:
            gradientMap= np.ma.masked_array(
                self._signalToGradientConversionFunction(clippedSignal),
                mask=signal.mask)
        except ValueError as err:
            self._logger.error(
                'Signals outside of interpolation range. Programming Error!')
            raise err
        return gradientMap


    def setSignalToGradientConversionFunction(
            self, signalToGradientConversionFunction):
        self._signalToGradientConversionFunction= \
            signalToGradientConversionFunction


    def signalToGradientConversionFunction(self):
        return self._signalToGradientConversionFunction


    @override
    @returns(Slopes)
    def computeSlopes(self, image):
        return self._computeSlopesUsingPyramidGeometry(image.astype('float'))


    @returns(np.ndarray)
    def computeOverlappedPupilImage(self, image):
        pupilImages= self._extractPupilsfromGeometry(image)
        return (pupilImages[PyramidPupilsNames.A]+
                pupilImages[PyramidPupilsNames.B]+
                pupilImages[PyramidPupilsNames.C]+
                pupilImages[PyramidPupilsNames.D])


    def _computeSlopesUsingPyramidGeometry(self, image):
        pupilImages= self._extractPupilsfromGeometry(image)
        signals2dX, signals2dY= self._computeSignalsFromQuadrantImages(
            pupilImages[PyramidPupilsNames.A],
            pupilImages[PyramidPupilsNames.B],
            pupilImages[PyramidPupilsNames.C],
            pupilImages[PyramidPupilsNames.D])
        slopes2dX= self._signalsToGradientInRadians(signals2dX)
        slopes2dY= self._signalsToGradientInRadians(signals2dY)
        return Slopes(slopes2dX, slopes2dY)


    def _computeSlopesOldWay(self, image):
        signals2dX, signals2dY= self._extractPupilsUsingPupilMasks(image)
        slopes2dX= self._signalsToGradientInRadians(signals2dX)
        slopes2dY= self._signalsToGradientInRadians(signals2dY)
        return Slopes(slopes2dX, slopes2dY)


    def _extractPupilsUsingPupilMasks(self, image):
        imaA= self._pupils[pupNames.A].extractMaskedRoiFrom(image)
        imaB= self._pupils[pupNames.B].extractMaskedRoiFrom(image)
        imaC= self._pupils[pupNames.C].extractMaskedRoiFrom(image)
        imaD= self._pupils[pupNames.D].extractMaskedRoiFrom(image)
        return self._computeSignalsFromQuadrantImages(imaA, imaB, imaC, imaD)


    def _computeSignalsFromQuadrantImages(self, imaA, imaB, imaC, imaD):
        norm= imaA+ imaB+ imaC+ imaD
        sx= ((imaB + imaD) - (imaA + imaC)) / norm
        sy= ((imaA + imaB) - (imaC + imaD)) / norm
        return sx, sy


    def _extractPupilsfromGeometry(self, image):
        assert isinstance(self._pupilsGeometry, PyramidPupilsGeometry), \
            'Pyramid pupils geometry is undefined'
        assert (2,) == self._centralPixelCoordinates.shape, \
            'Central pixel coordinates must be a numpy array(2)'
        quadrantsCenter= self._centralPixelCoordinates
        offset= self._pupilsGeometry.pupilCenters
        assert (4, 2) == offset.shape, \
            'Offset must be a numpy array(4,2)'

        dd= offset - quadrantsCenter
        maximumPupilRadius= int(0.5* np.min([
            np.abs(dd[1]- dd[0])[1],
            np.abs(dd[2]- dd[0])[0],
            image.shape[1]- np.abs(dd[1]- dd[0])[1],
            image.shape[0]- np.abs(dd[2]- dd[0])[0]]))
        afterShiftRoi= RegionOfInterest(
            quadrantsCenter[1]- maximumPupilRadius,
            quadrantsCenter[1]+ maximumPupilRadius,
            quadrantsCenter[0]- maximumPupilRadius,
            quadrantsCenter[0]+ maximumPupilRadius)

        qA= np.roll(np.roll(image, -int(dd[0, 0]), axis=0),
                    -int(dd[0, 1]), axis=1)
        qB= np.roll(np.roll(image, -int(dd[1, 0]), axis=0),
                    -int(dd[1, 1]), axis=1)
        qC= np.roll(np.roll(image, -int(dd[2, 0]), axis=0),
                    -int(dd[2, 1]), axis=1)
        qD= np.roll(np.roll(image, -int(dd[3, 0]), axis=0),
                    -int(dd[3, 1]), axis=1)

        imaA= np.ma.masked_array(afterShiftRoi.cutOut(qA))
        imaB= np.ma.masked_array(afterShiftRoi.cutOut(qB))
        imaC= np.ma.masked_array(afterShiftRoi.cutOut(qC))
        imaD= np.ma.masked_array(afterShiftRoi.cutOut(qD))
        return {PyramidPupilsNames.A: imaA,
                PyramidPupilsNames.B: imaB,
                PyramidPupilsNames.C: imaC,
                PyramidPupilsNames.D: imaD,
                }

