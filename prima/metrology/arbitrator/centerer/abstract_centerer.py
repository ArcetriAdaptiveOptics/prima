from prima.metrology.utils.convergeable import Convergeable

_version__= "$Id$"


class AbstractCenterer(Convergeable):

    def __init__(self):
        Convergeable.__init__(self)
