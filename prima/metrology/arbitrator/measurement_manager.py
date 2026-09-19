import numpy as np
from prima.metrology.types.measure import Measure
from prima.metrology._compat import Logger
from prima.metrology._compat import logTime, logEnterAndExit, returns, override
from prima.metrology.types.pyramid_pupils_geometry import PyramidPupilsGeometry
from prima.metrology.modal_decomposer import ModalDecomposer
from prima.metrology.arbitrator.abstract_measurement_manager import \
    AbstractMeasurementManager
from prima.metrology.types.camera_frame import CameraFrame

__version__= "$Id$"


class MeasurementManager(AbstractMeasurementManager):

    def __init__(self, cameraClient, modulatorClient):
        self._cameraClient= cameraClient
        self._modulatorClient= modulatorClient
        self._logger= Logger.of("Measurement Manager")
        self._measurementDict= {}
        self._pyramidGeometry= None
        self._slopesNormalization= 0.005
        self._pupilScaleInMeterPerPx= 1.0
        self._nextTag= 0
        self._modalDecomposer= ModalDecomposer()
        self._darkFrame= None
        self._pyramidTiltResponse= None


    @override
    def setPyramidGeometry(self, pyramidGeometry):
        assert isinstance(pyramidGeometry, PyramidPupilsGeometry)
        self._pyramidGeometry= pyramidGeometry


    @override
    def getPyramidGeometry(self):
        return self._pyramidGeometry


    @override
    def setSlopesNormalizationInRadians(self, slopesNormalizationInRadians):
        assert False, "Should not use this"
        self._logger.notice("Setting slopes normalizaton %g rad" %
                            slopesNormalizationInRadians)
        self._slopesNormalization= slopesNormalizationInRadians


    @override
    def setPupilScaleInMeterPerPx(self, pupilScaleInMeterPerUnbinnedPixel):
        self._logger.notice("Setting pupil scale of %g meter per bin1 px" %
                            pupilScaleInMeterPerUnbinnedPixel)
        self._pupilScaleInMeterPerPx= pupilScaleInMeterPerUnbinnedPixel


    @override
    def getPupilScaleInMeterPerPx(self):
        return self._pupilScaleInMeterPerPx


    @override
    def addMeasurement(self, measurement):
        assert isinstance(measurement, Measure)
        self._measurementDict[self._nextTag]= measurement
        self._nextTag+= 1


    @override
    def getMeasurementTags(self):
        return list(self._measurementDict.keys())


    @override
    def getMeasurementFromTag(self, tag):
        return self._measurementDict[tag]


    @override
    def getLastTag(self):
        return self._nextTag- 1


    def _computePupilScaleInMeterPerBinnedPixel(self):
        return self._pupilScaleInMeterPerPx * self._cameraClient.getBinning()


    def _computeSlopesNormalization(self):
        SPOT_SIZE_IN_MILLI_RAD= 0.0
        MILLIRAD_TO_RAD= 1e-3
        return MILLIRAD_TO_RAD * (
            self._modulatorClient.getRadiusInMilliRad() +
            SPOT_SIZE_IN_MILLI_RAD)


    def _getPyramidTiltResponseCalibrationArray(self):
        modRad= self._modulatorClient.getRadiusInMilliRad()
        assert modRad == self._pyramidTiltResponse.modulationRadiusInMilliRad,\
            ('The pyramid tilt response in use corresponds to a'
             ' modulation radius of %g mrad while the current'
             ' modulation radius is %g mrad' %
             (self._pyramidTiltResponse.modulationRadiusInMilliRad, modRad))
        # assert on Fiber Size
        return np.vstack((self._pyramidTiltResponse.tiltVectorInMilliRad* 1e-3,
                          self._pyramidTiltResponse.signalVector))


    def _correctDarkFrame(self, cameraFrame):
        if self._darkFrame is not None:
            return CameraFrame(cameraFrame.toNumpyArray() -
                               self._darkFrame.toNumpyArray())
        else:
            return cameraFrame


    def _averageCameraFrame(self, cameraFrame):
        aa= cameraFrame.toNumpyArray().squeeze()
        if aa.ndim == 3:
            aa= np.average(aa, axis=2)
        return CameraFrame(aa)


    def _processCameraFrame(self, cameraFrame):
        return self._correctDarkFrame(self._averageCameraFrame(cameraFrame))



    def setDarkFrame(self, darkFrame):
        assert isinstance(darkFrame, CameraFrame)
        self._darkFrame= darkFrame


    @logTime
    @logEnterAndExit('Entering takeAMeasurement', 'Executed takeAMeasurement')
    @returns(Measure)
    def takeAMeasurement(self,
                         framesToAverage,
                         snapshot={},
                         storeMeasurement=False):
        if not snapshot:
            from prima.metrology.arbitrator.snapshot_entry import (
                SnapshotEntry, SnapshotPrefix)
            snapshot = {
                SnapshotEntry.SIGNAL_TO_GRADIENT: 'default',
            }
            mod_snap = self._modulatorClient.getSnapshot(
                SnapshotPrefix.MODULATOR)
            # Prefix with PYGO. as Prisma arbitrator does
            for k, v in mod_snap.items():
                snapshot['%s.%s' % (SnapshotPrefix.PYGO, k)] = v
        cameraFrame= self._processCameraFrame(
            self._cameraClient.getFutureFrames(
                1, numberOfFramesToAverageForEachImage=framesToAverage))
        measurement= Measure.create(
            cameraFrame,
            self._pyramidGeometry,
            self._getPyramidTiltResponseCalibrationArray(),
            self._computePupilScaleInMeterPerBinnedPixel(),
            snapshot)
        measurement.setModalDecomposer(self._modalDecomposer)
        if storeMeasurement:
            self.addMeasurement(measurement)
        return measurement


    @override
    def setPyramidTiltResponse(self, pyramidTiltResponse):
        self._pyramidTiltResponse= pyramidTiltResponse


    @override
    def getPyramidTiltResponse(self):
        return self._pyramidTiltResponse

