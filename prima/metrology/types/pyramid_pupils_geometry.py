import numpy as np


__version__= "$Id$"


class PyramidPupilsGeometry(object):
    pupilCenters= None
    fitsHeader= None


    def __init__(self,
                 pupilCenters=None,
                 fitsHeader=None):
        if pupilCenters is not None:
            assert (4, 2) == pupilCenters.shape, \
                "Pupil Centers shape must be (4, 2) but is %s" % (
                str(pupilCenters.shape))

        self.pupilCenters= pupilCenters
        self.fitsHeader= fitsHeader


    def __eq__(self, other):
        return np.allclose(self.pupilCenters, other.pupilCenters)


    def __ne__(self, o):
        return not self.__eq__(o)
