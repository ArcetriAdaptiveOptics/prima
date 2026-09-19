
import abc
from prima.metrology.types.pyramid_pupils import PyramidPupils
from prima.metrology._compat import returns


__version__= "$Id$"


class AbstractPupilFinderAlgo(object):

    @abc.abstractmethod
    @returns(PyramidPupils)
    def findPupils(self, image):
        assert False
