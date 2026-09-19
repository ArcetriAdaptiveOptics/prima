import numpy as np
from prima.metrology._compat import returns
from prima.metrology.types.wavefront import Wavefront
from prima.metrology.surface_reconstructor import SurfaceReconstructor
from scipy import ndimage
from prima.metrology.types.mask import CircularMask
from prima.metrology.utils.zernike_generator import ZernikeGenerator

__version__= "$Id: wavefront.py 186 2017-01-12 13:20:00Z lbusoni $"


class WavefrontComputer(object):

    NOT_INITIALIZED= None

    def __init__(self):
        self._surfaceRecSmoothingFactor= 1
        self._modalDecomposer= self.NOT_INITIALIZED


    def setModalDecomposer(self, modalDecomposer):
        self._modalDecomposer= modalDecomposer


    def getModalDecomposer(self):
        return self._modalDecomposer


    def _computeWavefrontFromGradient(self,
                                      slopes,
                                      mask,
                                      scaleInMeterPerPixel):
        roi= mask.regionOfInterest()
        dx= roi.cutOut(slopes.mapX())
        dy= roi.cutOut(slopes.mapY())
        dx= np.ma.masked_array(dx.filled(dx.mean()))
        dy= np.ma.masked_array(dy.filled(dy.mean()))
        surfRec= SurfaceReconstructor()
        wfNotScaled= surfRec.fromGradient(dx, dy).toNumpyArray()
        wf= wfNotScaled* scaleInMeterPerPixel
        wfLowPass= ndimage.gaussian_filter(
            wf, self._surfaceRecSmoothingFactor)
        return wfLowPass- wfLowPass.mean()


    @returns(Wavefront)
    def fromSlopes(self, slopes, mask, scaleInMeterPerPixel):
        wf= self._computeWavefrontFromGradient(slopes,
                                               mask,
                                               scaleInMeterPerPixel)
        roiMask= CircularMask(np.ones(2) *2* mask.radius())
        wfMasked= np.ma.masked_array(wf, mask=roiMask.mask())
        return Wavefront.fromNumpyArray(wfMasked)



    def _computeZernikeCoefficientsFromWavefront(self, wavefront):
        circularMask= CircularMask.fromMaskedArray(wavefront.toNumpyArray())
        return \
            self._modalDecomposer.measureZernikeCoefficientsFromWavefront(
                wavefront, circularMask)


    def _removeZernikeModesFromMaskedArray(self,
                                           wfMasked,
                                           removeZernikes):
        zc= self._computeZernikeCoefficientsFromWavefront(
            Wavefront.fromNumpyArray(wfMasked))
        circularMask= CircularMask.fromMaskedArray(wfMasked)
        zg= ZernikeGenerator(circularMask.radius() * 2)
        wf= 0.* zg.getZernike(1)
        for y in removeZernikes:
            wf+= zc.getZ([y])* zg.getZernike(y)
        wfZernRemoved= wfMasked- wf
        return wfZernRemoved- wfZernRemoved.mean()


    @returns(Wavefront)
    def removeZernikes(self, wavefront, circularMask, zernikesToRemove):
        wfModesRemoved= self._removeZernikeModesFromMaskedArray(
            wavefront.toNumpyArray(),
            zernikesToRemove)
        return Wavefront.fromNumpyArray(wfModesRemoved)


    def zernikeCoefficientsFromWavefront(self, wavefront):
        return self._computeZernikeCoefficientsFromWavefront(wavefront)


    @returns(Wavefront)
    def fromZernikes(self, zernikeCoefficients, circularMask):
        zg= ZernikeGenerator(circularMask.radius() * 2)
        wf= 0.* zg.getZernike(1)
        for y in zernikeCoefficients.zernikeIndexes():
            wf+= zernikeCoefficients.getZ([y])* zg.getZernike(y)
        return Wavefront.fromNumpyArray(wf- wf.mean())
