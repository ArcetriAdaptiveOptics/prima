
from prima.metrology.arbitrator.centerer.abstract_centerer import AbstractCenterer
from prima.metrology._compat import Logger
from prima.metrology._compat import override, returns

_version__= "$Id$"


class Centerer(AbstractCenterer):

    def __init__(self, centeringAlgo):
        AbstractCenterer.__init__(self)
        self._algo= centeringAlgo

        self._cycleCounter= 0
        self._gain= 0.0
        self._logger= Logger.of("Centerer")



    @override
    @returns(bool)
    def hasConverged(self):
        return self._algo.isOnTarget()


    @override
    def performOneConvergenceStep(self):
        self._algo.step()
        self._cycleCounter += 1


    @override
    def measureConvergence(self):
        self._logger.debug("skipping convergence measurement")
        return False
