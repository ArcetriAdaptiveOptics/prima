from prima.metrology.arbitrator.centerer.algo import Algo
from prima.metrology._compat import override


_version__= "$Id$"


class CommonAlgo(Algo):

    def __init__(self):
        self._interactionMatrix= None
        self._reconstructionMatrix= None
        self._gain= 0.5


    def getReconstructionMatrix(self):
        return self._reconstructionMatrix


    def setReconstructionMatrix(self, recMatrix):
        self._reconstructionMatrix= recMatrix


    def getInteractionMatrix(self):
        return self._interactionMatrix


    def setInteractionMatrix(self, interactionMatrix):
        self._interactionMatrix= interactionMatrix


    @override
    def setGain(self, gain):
        if gain < 0:
            raise ValueError("gain must be positive")
        self._gain= gain


    @override
    def getGain(self):
        return self._gain
