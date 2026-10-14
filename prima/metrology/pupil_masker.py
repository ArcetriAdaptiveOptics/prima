import numpy as np
from prima.metrology._compat import returns, logEnterAndExit
from prima.metrology.types.mask import CircularMask
from prima.metrology._compat import Logger
from prima.metrology.image_analyzer import ImageAnalyzer


__version__= "$Id$"


class PupilMasker(object):

    PUPIL_RADIUS_FRACTION= 0.9
    ACCURACY= 4

    def __init__(self):
        self._imageAnalyzer= ImageAnalyzer()
        self._logger= Logger.of('Pupil Masker')


    @returns(CircularMask)
    @logEnterAndExit("Enter createCircularMask",
                     "createCircularMask completed")
    def createCircularMask(self, pupilImage):
        masks= self._imageAnalyzer.findCircles(
            pupilImage, 1, accuracyInPixels=self.ACCURACY)
        return self._reduceRadiusOfMask(masks[0], self.PUPIL_RADIUS_FRACTION)


    def _reduceRadiusOfMask(self, mask, radiusFraction):
        return CircularMask(mask.shape(),
                            int(mask.radius()* radiusFraction),
                            mask.center())
