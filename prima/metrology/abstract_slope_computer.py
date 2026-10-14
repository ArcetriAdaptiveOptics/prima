import abc
from prima.metrology._compat import returns
from prima.metrology.types.slopes import Slopes


__version__= "$Id$"


class AbstractSlopeComputer(object, metaclass=abc.ABCMeta):
    @abc.abstractmethod
    @returns(Slopes)
    def computeSlopes(self):
        assert False
