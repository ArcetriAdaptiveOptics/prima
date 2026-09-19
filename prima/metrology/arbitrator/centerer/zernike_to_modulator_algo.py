import numpy as np
import scipy.linalg

from prima.metrology._compat import Logger
from prima.metrology._compat import returnsNone, returns, override, logTime
import time
from prima.metrology.arbitrator.centerer.common_algo import CommonAlgo
from prima.metrology.arbitrator.centerer.common_modulator import CommonModulator
from prima.metrology.calibration.abstract_calibration_manager import \
    ZernikeToModulatorResult


class ZernikeToModulatorAlgo(CommonAlgo,
                             CommonModulator):

    ON_TARGET_THRESHOLD_IN_ZERNIKE_METERS= 10e-9

    def __init__(self,
                 measurementManager,
                 modulatorClient,
                 calibrationManager,
                 timeMod=time):

        self._timeMod= timeMod
        CommonAlgo.__init__(self)
        CommonModulator.__init__(self, modulatorClient)
        self._measMgr= measurementManager
        self._calibMgr= calibrationManager
        self._logger= Logger.of("ZernikeToModulatorAlgo")
        self._gain= 0.5


    @returnsNone
    def storeCalibration(self, tag):
        result= ZernikeToModulatorResult(
            self._interactionMatrix, self._reconstructionMatrix, None)
        self._calibMgr.saveZernikeToModulator(tag, result)


    @returnsNone
    def restoreCalibration(self, tag):
        result= self._calibMgr.loadZernikeToModulator(tag)
        self.setInteractionMatrix(result.interactionMatrix)
        self.setReconstructionMatrix(result.reconstructionMatrix)


    def _offsetModulatorAndMeasureZernikeTipTilt(self, modulatorOffset):
        self._offsetModulatorCenter(modulatorOffset)
        measure= self._measureTipTiltFromZernike()
        return measure


    @override
    @returns(bool)
    def isOnTarget(self):
        error= self._measureTipTiltFromZernike()
        onTarget= bool(
            np.all(abs(error) < self.ON_TARGET_THRESHOLD_IN_ZERNIKE_METERS))

        self._logger.debug(
            "On target %s. Tip tilt error %s (threshold %s)" % (
                onTarget, self.ON_TARGET_THRESHOLD_IN_ZERNIKE_METERS, error))
        return onTarget


    @override
    @returnsNone
    @logTime
    def calibrate(self, header=None):
        NUMBER_OF_ITERATIONS= 3

        offsetInMilliRad= 2.0

        sig= np.ndarray((NUMBER_OF_ITERATIONS, 2, 2))

        for i in np.arange(NUMBER_OF_ITERATIONS):
            self._logger.notice('moving positive axis 0')
            offPosPhi= self._offsetModulatorAndMeasureZernikeTipTilt(
                self.delta(offsetInMilliRad, 0))

            self._logger.notice('moving negative axis 0')
            offNegPhi= self._offsetModulatorAndMeasureZernikeTipTilt(
                self.delta(-2* offsetInMilliRad, 0))

            self._logger.notice('moving positive axis 1')
            offPosTheta= self._offsetModulatorAndMeasureZernikeTipTilt(
                self.delta(offsetInMilliRad, offsetInMilliRad))

            self._logger.notice('moving negative axis 1')
            offNegTheta= self._offsetModulatorAndMeasureZernikeTipTilt(
                self.delta(0, -2* offsetInMilliRad))

            self._offsetModulatorCenter(
                self.delta(0, offsetInMilliRad))

            sig[i]= np.array([offPosPhi- offNegPhi, offPosTheta- offNegTheta]
                             ) / (2* offsetInMilliRad)

        self._interactionMatrix=np.mean(sig, axis=0).T
        self._reconstructionMatrix= scipy.linalg.pinv2(self._interactionMatrix)


    def _measureTipTiltFromZernike(self):
        framesToAverage= 1
        meas= self._measMgr.takeAMeasurement(framesToAverage,
                                             storeMeasurement=False)
        meas.applyAutomaticMask()
        tiptilt= meas.zernikeCoefficients().getZ([2, 3])
        self._logger.notice("Z2, Z3: %s" % str(tiptilt))
        return tiptilt


    def _determineOffsetToBeGivenToModulator(self):
        error= self._measureTipTiltFromZernike()
        offset= -1. * self._gain * np.dot(self._reconstructionMatrix, error)
        return self.delta(offset[0], offset[1])


    @returnsNone
    def step(self):
        offsetDict= self._determineOffsetToBeGivenToModulator()
        self._offsetModulatorCenter(offsetDict)


    def setGain(self, gain):
        self._gain= gain


    @returns(float)
    def getGain(self):
        return float(self._gain)
