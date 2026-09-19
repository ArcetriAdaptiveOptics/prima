import numpy as np
from astropy.io import fits as pyfits
from prima.metrology.types.slopes import Slopes
from prima.metrology._compat import returns, logEnterAndExit
from prima.metrology.types.pyramid_pupils_geometry import PyramidPupilsGeometry
from prima.metrology.types.camera_frame import CameraFrame
from prima.metrology.types.zernike_coefficients import ZernikeCoefficients
from prima.metrology.types.mask import CircularMask
from prima.metrology._compat import Snapshotable
from prima.metrology.pyramid_slope_computer import PyramidSlopeComputer
from prima.metrology.pupil_masker import PupilMasker
from prima.metrology._compat import Logger
from prima.metrology.types.wavefront import Wavefront
from prima.metrology.wavefront_computer import WavefrontComputer
from prima.metrology.arbitrator.snapshot_entry import SnapshotEntry, SnapshotPrefix
from prima.metrology.arbitrator.snapshot_entry import SnapshotEntry as SnapshotEntryModulator
from scipy.interpolate import interp1d


__version__= "$Id$"



class Measure(object):

    NOT_INITIALIZED= None

    def __init__(self,
                 cameraFrame,
                 pyramidGeometry,
                 signalsToGradientCalibrationArray,
                 scaleInMeterPerPixel,
                 pygoSnapshot=dict()):
        assert isinstance(cameraFrame, CameraFrame), \
            'CameraFrame undefined'
        assert isinstance(pyramidGeometry, PyramidPupilsGeometry), \
            'Pyramid Geometry undefined'
        self._cameraFrame= cameraFrame
        self._pyramidGeometry= pyramidGeometry
        self._signalsToGradientCalibrationArray= \
            signalsToGradientCalibrationArray
        self._scaleInMeterPerPixel= scaleInMeterPerPixel
        self._snapshot = pygoSnapshot

        self._resetToUninitialized()
        self._initializeSignalsToGradientConversionFunction()
        self.setSlopeComputer(PyramidSlopeComputer())
        self.setWavefrontComputer(WavefrontComputer())
        self._createLogger()
        self._usedRemoveZernikes= []


    def _initializeSignalsToGradientConversionFunction(self):
        self._signalsToGradientConvFunct= interp1d(
            self._signalsToGradientCalibrationArray[1], # pyr sign
            self._signalsToGradientCalibrationArray[0], # wf gradient [rad]
            kind='cubic')


    def signalsToGradientCalibrationArray(self):
        return self._signalsToGradientCalibrationArray


    def scaleInMeterPerPixel(self):
        return self._scaleInMeterPerPixel


    def _createLogger(self):
        self._logger= Logger.of('Measure')


    def __getstate__(self):
        odict = self.__dict__.copy()
        del odict['_logger']
        del odict['_modalDecomposer']
        del odict['_slopesComputer']
        del odict['_wavefrontComputer']
        del odict['_circularMask']
        return odict


    def __setstate__(self, d):
        self.__dict__.update(d)
        self._modalDecomposer= None
        self._circularMask= None
        self.setSlopeComputer(PyramidSlopeComputer())
        self.setWavefrontComputer(WavefrontComputer())
        self._createLogger()


    def _resetToUninitialized(self):
        self._slopes= self.NOT_INITIALIZED
        self._pupilOverlappedImage= self.NOT_INITIALIZED
        self._circularMask= self.NOT_INITIALIZED
        self._zernikeCoefficients= self.NOT_INITIALIZED
        self._wavefrontFromZernikes= self.NOT_INITIALIZED
        self._modalDecomposer= self.NOT_INITIALIZED
        self._slopesComputer= self.NOT_INITIALIZED
        self._wavefrontComputer= self.NOT_INITIALIZED
        self._wavefrontFromGradient= self.NOT_INITIALIZED


    def _averageFrame(self):
        aa= self._cameraFrame.toNumpyArray().squeeze()
        if aa.ndim == 3:
            return np.average(aa, axis=2)
        return aa


    def _configureSlopeComputer(self):
        self._slopesComputer.setPupilsGeometry(self._pyramidGeometry)
        centralPixel= np.array(self._averageFrame().shape) / 2
        self._slopesComputer.setCentralPixelBetweenPupils(centralPixel)
        self._slopesComputer.setSignalToGradientConversionFunction(
            self._signalsToGradientConvFunct)


    @staticmethod
    def create(cameraFrame, pyramidGeometry,
               slopesNormalizationInRadians,
               scaleInMeterPerPixel, pygoSnapshot=dict()):
        return Measure(cameraFrame,
                       pyramidGeometry,
                       slopesNormalizationInRadians,
                       scaleInMeterPerPixel,
                       pygoSnapshot)


    def setSlopeComputer(self, slopeComputer):
        self._slopesComputer= slopeComputer
        self._configureSlopeComputer()


    def slopeComputer(self):
        return self._slopesComputer


    def setWavefrontComputer(self, wavefrontComputer):
        self._wavefrontComputer= wavefrontComputer


    def setModalDecomposer(self, modalDecomposer):
        self._modalDecomposer = modalDecomposer
        if self._wavefrontComputer is not self.NOT_INITIALIZED:
            self._wavefrontComputer.setModalDecomposer(modalDecomposer)


    def getModalDecomposer(self):
        return self._modalDecomposer


    def saveAsFits(self, fileName):
        try:
            fitsHeader= Snapshotable.asFITSHeader(self._snapshot)
        except:
            fitsHeader= None
        pyfits.writeto(fileName, self._cameraFrame.toNumpyArray(),
                       fitsHeader,
                       clobber=False)
        pyfits.append(fileName, np.array([self._cameraFrame.counter()]))
        pyfits.append(fileName, self._pyramidGeometry.pupilCenters)
        pyfits.append(fileName, self._signalsToGradientCalibrationArray)
        pyfits.append(fileName, np.array([self._scaleInMeterPerPixel]))


    @staticmethod
    def loadFromFits(fileName):
        hdr= pyfits.getheader(fileName)
        signalToGradientKey= SnapshotPrefix.PYGO +"."+\
            SnapshotEntry.SIGNAL_TO_GRADIENT
        if signalToGradientKey in hdr.keys():
            return Measure._loadFromFitsWithSignalToGradient(fileName)
        else:
            return Measure._loadFromFitsWithoutSignalToGradient(fileName)



    @staticmethod
    def _loadFromFitsWithoutSignalToGradient(fileName):
        hdr= pyfits.getheader(fileName)
        hduList= pyfits.open(fileName)
        rawArray= hduList[0].data
        counter= hduList[1].data[0]
        pupilCenters= hduList[2].data
        slopesNorm= hduList[3].data[0]
        scaleInMeterPerPixel= hduList[4].data[0]
        pyramidGeometry= PyramidPupilsGeometry(pupilCenters)
        cameraFrame= CameraFrame(rawArray, counter)
        try:
            snapshot= Snapshotable.fromFITSHeader(hdr)
        except:
            snapshot= dict()

        signalsToGradientCalibrationArray= \
            Measure.createCalibrationArrayFromSlopesNormalization(slopesNorm)

        measure= Measure(cameraFrame,
                         pyramidGeometry,
                         signalsToGradientCalibrationArray,
                         scaleInMeterPerPixel,
                         snapshot)
        return measure


    @staticmethod
    def createCalibrationArrayFromSlopesNormalization(slopesNorm):
        signals= np.linspace(-1.0, 1.0, 100)
        gradient= slopesNorm * np.sin(np.pi/ 2 * signals)
        signalsToGradientCalibrationArray= np.vstack((gradient, signals))
        return signalsToGradientCalibrationArray


    @staticmethod
    def _loadFromFitsWithSignalToGradient(fileName):
        hdr= pyfits.getheader(fileName)
        hduList= pyfits.open(fileName)
        rawArray= hduList[0].data
        counter= hduList[1].data[0]
        pupilCenters= hduList[2].data
        sigToGradCalArray= hduList[3].data
        scaleInMeterPerPixel= hduList[4].data[0]
        pyramidGeometry= PyramidPupilsGeometry(pupilCenters)
        cameraFrame= CameraFrame(rawArray, counter)
        try:
            snapshot= Snapshotable.fromFITSHeader(hdr)
        except Exception:
            snapshot= dict()
        measure= Measure(cameraFrame,
                         pyramidGeometry,
                         sigToGradCalArray,
                         scaleInMeterPerPixel,
                         snapshot)
        return measure




    @returns(CameraFrame)
    def cameraFrame(self):
        return self._cameraFrame


    @returns(PyramidPupilsGeometry)
    def pyramidGeometry(self):
        return self._pyramidGeometry


    def setCircularMask(self, mask):
        assert isinstance(mask, (CircularMask, type(None))), \
            'mask argument should be of type CircularMask or None'
        if mask is None:
            self._circularMask= self.NOT_INITIALIZED
            self._zernikeCoefficients= self.NOT_INITIALIZED
            self._wavefrontFromZernikes= self.NOT_INITIALIZED
            self._wavefrontFromGradient= self.NOT_INITIALIZED
        else:
            self._circularMask= mask
            self._setZernikeCoefficients(
                self._computeZernikeCoefficientsFromSlopes())


    @returns(CircularMask)
    def circularMask(self):
        return self._circularMask


    def _setSlopes(self, slopes):
        assert isinstance(slopes, Slopes), \
            'slopes argument should be of type Slopes'
        self._slopes= slopes


    @returns(Slopes)
    def slopes(self):
        if self._slopes is self.NOT_INITIALIZED:
            self._setSlopes(self._computeSlopes())
        return self._slopes


    @logEnterAndExit("Enter _computeSlopes",
                     "_computeSlopes completed")
    def _computeSlopes(self):
        assert self._slopesComputer is not self.NOT_INITIALIZED
        return self._slopesComputer.computeSlopes(
            self._averageFrame())


    def _setZernikeCoefficients(self, zernikeCoefficients):
        assert isinstance(zernikeCoefficients, ZernikeCoefficients), \
            'setZernikeCoefficients argument is of type %s instead of ' \
            'ZernikeCoefficients' % type(zernikeCoefficients)
        self._zernikeCoefficients= zernikeCoefficients


    @returns(ZernikeCoefficients)
    def zernikeCoefficients(self):
        if self._zernikeCoefficients is self.NOT_INITIALIZED:
            self._setZernikeCoefficients(
                self._computeZernikeCoefficientsFromSlopes())
        return self._zernikeCoefficients


    @logEnterAndExit("Enter _computeZernikeCoefficientsFromSlopes",
                     "_computeZernikeCoefficientsFromSlopes completed")
    def _computeZernikeCoefficientsFromSlopes(self):
        assert self._modalDecomposer is not self.NOT_INITIALIZED
        assert self._circularMask is not self.NOT_INITIALIZED
        zc= self._modalDecomposer.measureZernikeCoefficientsFromSlopes(
            self.slopes(), self.circularMask()).toNumpyArray()
        zernToMeterRms= self._circularMask.radius() * \
            self._scaleInMeterPerPixel
        return ZernikeCoefficients.fromNumpyArray(zc * zernToMeterRms)


    @returns(Wavefront)
    def wavefront(self, removeZernikes=[2, 3]):
        return self.wavefrontFromGradient(removeZernikes=removeZernikes)


    @returns(Wavefront)
    def wavefrontFromZernikes(self, removeZernikes=[2, 3]):
        if self._wavefrontFromZernikes is self.NOT_INITIALIZED or \
           not np.array_equal(removeZernikes, self._usedRemoveZernikes):
            self._wavefrontFromZernikes= \
                self._computeWavefrontFromZernikeCoefficients(
                    removeZernikes)
            self._usedRemoveZernikes= removeZernikes
        return self._wavefrontFromZernikes


    def _computeWavefrontFromZernikeCoefficients(self, removeZernikes):
        zcVector= self.zernikeCoefficients().toNumpyArray().copy()
        toRemove= (np.array(removeZernikes)-
                   ZernikeCoefficients.FIRST_ZERNIKE_MODE).astype(np.int64)
        zcVector[toRemove]= 0
        wfRemoved= self._wavefrontComputer.fromZernikes(
            ZernikeCoefficients.fromNumpyArray(zcVector),
            self.circularMask())
        return wfRemoved


    @returns(Wavefront)
    def wavefrontFromGradient(self, removeZernikes=[2, 3]):
        wfFull= self._wavefrontComputer.fromSlopes(
            self.slopes(), self.circularMask(), self.scaleInMeterPerPixel())
        wfRemoved= self._wavefrontComputer.removeZernikes(wfFull,
                                                          self.circularMask(),
                                                          removeZernikes)
        return wfRemoved


    @returns(dict)
    def snapshot(self):
        return self._snapshot


    def _setPupilImage(self, pupilOverlappedImage):
        self._pupilOverlappedImage= pupilOverlappedImage


    @returns(np.ndarray)
    def pupilImage(self):
        if self._pupilOverlappedImage is self.NOT_INITIALIZED:
            self._setPupilImage(self._computePupilImage())
        return self._pupilOverlappedImage


    def _computePupilImage(self):
        assert self._slopesComputer is not self.NOT_INITIALIZED
        return self._slopesComputer.computeOverlappedPupilImage(
            self._averageFrame())


    def slopesNormalizationInRadians(self):
        key= SnapshotPrefix.PYGO + '.' + SnapshotPrefix.MODULATOR + '.' +\
            SnapshotEntryModulator.MODULATOR_AMPLITUDE
        if key in self._snapshot:
            return float(self._snapshot[key]) / 1000.
        # Fallback when snapshot incomplete: peak of tilt-response calib [rad]
        cal = np.asarray(self._signalsToGradientCalibrationArray)
        return float(np.max(np.abs(cal[0])))


    @logEnterAndExit("Enter applyAutomaticMask",
                     "applyAutomaticMask completed")
    def applyAutomaticMask(self):
        pupilMasker= PupilMasker()
        pupImage= self.pupilImage()
        mask= pupilMasker.createCircularMask(pupImage)
        self.setCircularMask(mask)


    def _areMaskedSlopesSaturated(self):
        HIGH_SIGNAL= 0.9
        LOW_SIGNAL= 0.1
        assert self._circularMask is not self.NOT_INITIALIZED
        mapX= np.ma.MaskedArray(self.slopes().mapX(),
                                self.circularMask().mask()) / \
            self.slopesNormalizationInRadians()
        mapY= np.ma.MaskedArray(self.slopes().mapY(),
                                self.circularMask().mask()) / \
            self.slopesNormalizationInRadians()
        fractionXHigh= (np.abs(mapX) > HIGH_SIGNAL).sum()/ mapX.count()
        fractionYHigh= (np.abs(mapY) > HIGH_SIGNAL).sum()/ mapY.count()
        fractionXLow= (np.abs(mapX) < LOW_SIGNAL).sum()/ mapX.count()
        fractionYLow= (np.abs(mapY) < LOW_SIGNAL).sum()/ mapY.count()
        return (fractionXHigh > 0.1) or (fractionYHigh > 0.1)


