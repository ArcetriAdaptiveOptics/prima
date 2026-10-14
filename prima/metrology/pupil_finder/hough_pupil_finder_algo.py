import numpy as np
import scipy.ndimage
import skimage.feature
import skimage.transform
from prima.metrology.types.pyramid_pupils import PyramidPupils, PyramidPupilsNames
from prima.metrology.utils import image_moments
from prima.metrology.types.region_of_interest import RegionOfInterest
from prima.metrology._compat import returns, override
from prima.metrology._compat import Logger
from prima.metrology.pupil_finder.abstract_pupil_finder_algo import \
    AbstractPupilFinderAlgo


__version__= "$Id$"


class PupilFinderException(Exception):
    pass


class HoughPupilFinderAlgo(AbstractPupilFinderAlgo):

    def __init__(self, imageAnalyzer):
        self._imageAnalyzer= imageAnalyzer
        self._logger= Logger.of('Pupil Finder')


    @returns(PyramidPupils)
    @override
    def findPupils(self, image):
        return self._houghIterative(image)


    def _houghIterative(self, image):
        fimage= image.astype('float')
        roi= self._getRoiUsingHough(fimage)
        cropped= roi.cutOut(fimage)
        radiiVector= np.arange(64, np.max(cropped.shape) / 2, 16)
        for rebinFactor in [16, 8, 4, 2, 1]:
            centers, radius= self._rebinAndHough(cropped, rebinFactor,
                                                 radiiVector)
            radiiVector= np.arange(radius - rebinFactor,
                                   radius + rebinFactor + 1,
                                   np.maximum(rebinFactor/ 2, 1))
        centers += np.array([roi.ymin, roi.xmin])
        return PyramidPupils.fromNumpyArray(centers, radius)


    def _roiAndCentroid(self, image):
        roi= self._getRoiUsingHough(image)
        cropped= roi.cutOut(image)
        clean= self._imageAnalyzer.removeBadPixels(cropped)
        imageToUse= self._imageAnalyzer.highPass(clean, clean.shape[0]/ 50.)
        binary= self._imageAnalyzer.convertToBinary(imageToUse)
        closingDiskRadius= binary.shape[0]/ 30.
        closed= self._imageAnalyzer.closeBinaryImage(binary, closingDiskRadius)
        centers, radii= self._findPupilsCentersFromCroppedBinaryImage(closed)
        centers += np.array([roi.ymin, roi.xmin])
        average_radius= np.round(np.mean(radii))
        return PyramidPupils.fromNumpyArray(centers, average_radius)


    def _makeQuadrantMask(self, shape, quadrant):
        mask= np.zeros(shape).astype(int)
        sz= mask.shape
        if quadrant == 0:
            mask[0:sz[0] / 2, 0:sz[1] / 2]= 1
        elif quadrant == 1:
            mask[-sz[0] / 2:, 0:sz[1] / 2]= 1
        elif quadrant == 2:
            mask[0:sz[0] / 2, -sz[1] / 2:]= 1
        elif quadrant == 3:
            mask[-sz[0] / 2:, -sz[1] / 2:]= 1
        else:
            raise ValueError("quadrant must be between 0 and 3")
        return mask


    def _findPupilsCentersFromCroppedBinaryImage(self, image):
        sz= image.shape
        m0= image_moments.ImageMoments(image * self._makeQuadrantMask(sz, 0))
        m1= image_moments.ImageMoments(image * self._makeQuadrantMask(sz, 1))
        m2= image_moments.ImageMoments(image * self._makeQuadrantMask(sz, 2))
        m3= image_moments.ImageMoments(image * self._makeQuadrantMask(sz, 3))
        centers= np.vstack((m0.centroid(), m1.centroid(),
                            m2.centroid(), m3.centroid()))
        radii= np.array([m0.effectiveRadius(), m1.effectiveRadius(),
                         m2.effectiveRadius(), m3.effectiveRadius()])
        self._logger.notice("From centroid: center:%s" % str(centers))
        self._logger.notice("From centroid: radii:%s" % str(radii))
        return centers, radii


    def _rebinAndHough(self, image, rebinFactor, radiiVector):
        highPassFilterSize= int(50/ rebinFactor)
        radiiVectorBinned= radiiVector / rebinFactor

        imaz= scipy.ndimage.zoom(image, 1./ rebinFactor, order=1)
        ima1z= self._imageAnalyzer.removeBadPixels(imaz)
        ima2z= self._imageAnalyzer.highPass(ima1z, highPassFilterSize)
        ima2zr= self._imageAnalyzer.rescaleBetween0And1(ima2z)

        centersRebin, radiusRebin= self._getBestRadiusFromHough(
            ima2zr, radiiVectorBinned)
        centers= centersRebin* rebinFactor
        radius= radiusRebin* rebinFactor
        self._logger.notice("From Hough: radius:%d center:%s" % (radius,
                                                                 str(centers)))
        return centers, radius


    @returns(RegionOfInterest)
    def _getRoiUsingHough(self, image):
        rebinFactor= 16
        radiiVector= np.arange(64, 1024, rebinFactor)
        centers, radius= self._rebinAndHough(image, rebinFactor, radiiVector)
        xmin= np.maximum(np.min(centers[:, 1]) - 1.5 * radius, 0)
        ymin= np.maximum(np.min(centers[:, 0]) - 1.5 * radius, 0)
        xmax= np.minimum(np.max(centers[:, 1]) + 1.5 * radius, image.shape[1])
        ymax= np.minimum(np.max(centers[:, 0]) + 1.5 * radius, image.shape[0])
        return RegionOfInterest(xmin, xmax, ymin, ymax)



    def _getBestRadiusFromHough(self, image, radiiVector):
        edges= skimage.feature.canny(image, sigma=1)
        htAllRadii= skimage.transform.hough_circle(edges, radiiVector)
        maxht= np.max(htAllRadii, axis=(1, 2))
        idxBestRadius= np.where(maxht == np.max(htAllRadii))[0][0]
        bestRadius= radiiVector[idxBestRadius]
        htBestRadius= htAllRadii[idxBestRadius]
        dum= htBestRadius.copy()
        maxCoords= np.zeros((PyramidPupilsNames.NUMBER_OF_PUPILS, 2))
        for idx in range(PyramidPupilsNames.NUMBER_OF_PUPILS):
            maxCoord= np.array(np.where(dum == np.max(dum)))[:, 0]
            dum[int(maxCoord[0] - bestRadius): int(maxCoord[0] + bestRadius),
                int(maxCoord[1] - bestRadius): int(maxCoord[1] + bestRadius)]=\
                np.min(dum)
            maxCoords[idx, :]= maxCoord
        return maxCoords, bestRadius


    def __findPupilsOLD(self, image):
        closingDiskRadius= 13
        binary= self._imageAnalyzer.convertToBinary(image)
        closed= self._imageAnalyzer.closeBinaryImage(binary, closingDiskRadius)

        centers, radii, meanRadius= self._imageAnalyzer.\
            _findPupilsCentersFromCroppedBinaryImage(closed)
        return {'centers': centers, 'radius': meanRadius, 'radii': radii,
                'binary': binary, 'closed': closed, 'image': image}



