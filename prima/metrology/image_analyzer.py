import numpy as np
from scipy.ndimage import median_filter
import skimage.filters
import skimage.morphology
from scipy import ndimage
from skimage.feature._canny import canny
from skimage.transform.hough_transform import hough_circle
from skimage.feature.peak import peak_local_max
from prima.metrology.types.mask import CircularMask
from prima.metrology._compat import Logger
import rebin

__version__ = "$Id$"


class CircleNotFoundException(Exception):
    pass


class ImageAnalyzer(object):

    def __init__(self):
        self._logger= Logger.of("Image Analyzer")

    def removeBadPixels(self, image):
        return median_filter(image, 3)


    def convertToBinary(self, image):
        imageNorm= image / np.max(image)
        binary= imageNorm > skimage.filters.threshold_otsu(imageNorm)
        return binary


    def closeBinaryImage(self, binaryImage, diskRadius):
        return skimage.morphology.binary_closing(
            binaryImage,
            skimage.morphology.disk(diskRadius))


    def findDarkLevel(self, image):
        SIZE_DARK_CORNER= 200
        dark= np.dstack((image[0:SIZE_DARK_CORNER, 0:SIZE_DARK_CORNER],
                         image[-SIZE_DARK_CORNER:, 0:SIZE_DARK_CORNER],
                         image[-SIZE_DARK_CORNER:, -SIZE_DARK_CORNER:],
                         image[0:SIZE_DARK_CORNER, -SIZE_DARK_CORNER:]))
        return dark


    def highPass(self, image, size):
        lowpass= ndimage.gaussian_filter(image, size)
        return image - lowpass


    def rescaleBetween0And1(self, image):
        tmp= image- np.min(image)
        return tmp/ np.max(tmp)



    def findCirclesWithKnownRadius(self, image, radiiVector,
                                   howManyCirclesToFind):
        edges= canny(image, sigma=1)

        hough_res= hough_circle(edges, radiiVector, normalize=False)
        if len(hough_res) == 0 or hough_res.max() == 0:
            raise CircleNotFoundException("Hough transform is zero")

        centers= []
        accums= []
        radii= []
        masks=[]


        for radius, h in zip(radiiVector, hough_res):
            try:
                peaks= peak_local_max(h,
                                      min_distance=1,
                                      num_peaks=howManyCirclesToFind)
                centers.extend(peaks)
                accums.extend(h[peaks[:, 0], peaks[:, 1]])
                radii.extend([radius] * howManyCirclesToFind)
            except Exception as e:
                self._logger.error("peaks %s" % peaks)
                self._logger.error("centers %s" % centers)
                self._logger.error("accums %s" % accums)
                self._logger.error("radii %s" % radii)
                self._logger.error("radius %s" % radius)
                self._logger.error("h.max %s" % h.max())
                self._logger.error("%s" % e)
                continue

        for idx in np.argsort(accums)[::-1][:howManyCirclesToFind]:
            center_y, center_x= centers[idx]
            radius= radii[idx]
            mask= CircularMask(image.shape,
                               radius,
                               np.array([center_y, center_x]))
            masks.append(mask)
            self._logger.debug("Found mask %s [accums %f]" % (mask,
                                                              accums[idx]))
        return masks



    def _rebinAndHough(self, image, howManyCirclesToFind,
                       rebinFactor, radiiVector):
        iRebinFactor= int(rebinFactor)
        radiiVectorBinned= radiiVector // iRebinFactor

        imaz= rebin.rebin(image.astype(np.float64), iRebinFactor)
        ima1z= self.removeBadPixels(imaz)
        ima2zr= self.rescaleBetween0And1(ima1z)

        masks= self.findCirclesWithKnownRadius(ima2zr,
                                               radiiVectorBinned,
                                               howManyCirclesToFind)
        res= []
        for mask in masks:
            res.append(CircularMask(image.shape,
                                    mask.radius()* iRebinFactor,
                                    mask.center()* iRebinFactor))
        return res


    def findCircles(self, image, howManyCirclesToFind, accuracyInPixels=1):
        return self._houghIterative(image,
                                    howManyCirclesToFind,
                                    accuracyInPixels)


    def _determineInitialRadiiVectorAndBinningSeries(self,
                                                     image,
                                                     accuracyInPixels):
        if np.min(image.shape) > 50:
            radiiVector= np.arange(16, np.max(image.shape) / 2, 16)
            rebinFactorVector= np.unique(
                (2**np.arange(5)).clip(min=accuracyInPixels/ 2))[::-1]
        else:
            radiiVector= np.arange(2, np.max(image.shape) / 2, 1)
            rebinFactorVector= [1]
        return radiiVector, rebinFactorVector


    def _houghIterative(self, image, howManyCirclesToFind, accuracyInPixels):
        radiiVector, rebinFactorVector= \
            self._determineInitialRadiiVectorAndBinningSeries(image,
                                                              accuracyInPixels)
        masks= None
        for rebinFactor in rebinFactorVector:
            self._logger.debug('rebinFactor %d radiiVector %s' % (
                               rebinFactor, radiiVector))
            try:
                masks= self._rebinAndHough(image,
                                           howManyCirclesToFind,
                                           rebinFactor,
                                           radiiVector)
                radiiMeas= np.array([x.radius() for x in masks])
                self._logger.debug('masks %s' % masks)
            except CircleNotFoundException:
                radiiMeas= radiiVector.min()
                self._logger.warn('CircleNotFound: setting radiiMeas to %d' %
                                  radiiMeas)

            radiiVector= np.arange(radiiMeas.min() - rebinFactor,
                                   radiiMeas.max() + rebinFactor,
                                   np.maximum(rebinFactor/ 2, 1))
            radiiVector= np.unique(radiiVector.clip(
                min=np.maximum(rebinFactor/ 2, 1)))
        if masks is None:
            raise CircleNotFoundException()
        return masks

