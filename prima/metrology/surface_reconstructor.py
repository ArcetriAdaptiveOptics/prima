import numpy as np
import scipy.linalg
from scipy import fftpack

from prima.metrology.types.wavefront import Wavefront
from prima.metrology._compat import returns


__version__ = "$Id$"


class SurfaceReconstructor(object):


    @returns(Wavefront)
    def fromGradient(self, gradientX2DMap, gradientY2DMap):
        '''
        From Harker, M., 2008,
        "Least Squares Surface Reconstruction from Measured Gradient Fields"
        and Harker, M., 2011,
        "Regularized Reconstruction of a Surface from its Measured
        Gradient Field"

        See MATLAB g2s.m
        '''
        assert gradientX2DMap.shape == gradientY2DMap.shape
        #assert not isinstance(gradientX2DMap, np.ma.MaskedArray)
        m, n= gradientX2DMap.shape
        Dx= self._getDifferentationMatrix(n)
        Dy= self._getDifferentationMatrix(m)
        Z= self._sylvester(Dy, Dx, gradientY2DMap, gradientX2DMap,
                           np.ones(m), np.ones(n))
        return Wavefront(Z)


    def getTemp(self):
        return self._temp


    def _getDifferentationMatrix(self, size):
        ide= np.identity(size)
        ret= 0.5 * (np.roll(ide, 1, axis=1) - np.roll(ide, 1, axis=0))
        ret[-1, 0]= 0
        ret[0, -1]= 0
        ret[0, 0:3]= [-1.5, 2, -0.5]
        ret[-1, -3:]= [0.5, -2, 1.5]
        return ret


    def _sylvester(self, A, B, F, G, u, v):
        '''
        Solves the semi-definite Sylvester Equation of the form
        A'*A * Phi + Phi * B'*B - A'*F - G*B = 0,
        Where the null vectors of A and B are known to be
        A * u = 0
        B * v = 0
        '''
        assert u.ndim == 1
        assert v.ndim == 1
        m = u.size
        n = v.size

        uVect= u.copy()
        vVect= v.copy()
        uVect[0] += scipy.linalg.norm(uVect)
        uVect= np.sqrt(2) / scipy.linalg.norm(uVect) * uVect
        vVect[0] += scipy.linalg.norm(vVect)
        vVect= np.sqrt(2) / scipy.linalg.norm(vVect) * vVect

        Amat= A- np.dot(np.expand_dims(np.dot(A, uVect), axis=1),
                        np.expand_dims(uVect, axis=0))
        Bmat= B- np.dot(np.expand_dims(np.dot(B, vVect), axis=1),
                        np.expand_dims(vVect, axis=0))
        Fmat= F- np.dot(np.expand_dims(np.dot(F, vVect), axis=1),
                        np.expand_dims(vVect, axis=0))
        Gmat= G- np.dot(np.expand_dims(uVect, axis=1),
                        np.expand_dims(np.dot(uVect.T, G), axis=0))

        phi= np.zeros((m, n))
        phi[0, 1:]= (np.linalg.lstsq(Bmat[:, 1:], Gmat[0, :].T)[0]).T
        phi[1:, 0]= np.linalg.lstsq(Amat[:, 1:], Fmat[:, 0])[0]
        lyaA= np.dot(Amat[:, 1:].T, Amat[:, 1:])
        lyaB= np.dot(Bmat[:, 1:].T, Bmat[:, 1:])
        lyaC= np.dot(Amat[:, 1:].T, Fmat[:, 1:]) + \
            np.dot(Gmat[1:, :], Bmat[:, 1:])
        phi[1:, 1:]= scipy.linalg.solve_sylvester(lyaA, lyaB, lyaC)

        dum= phi - np.dot(np.expand_dims(uVect, axis=1),
                          np.expand_dims(np.dot(uVect.T, phi), axis=0))
        res= dum - np.dot(np.expand_dims(np.dot(dum, vVect), axis=1),
                          np.expand_dims(vVect, axis=0))
#        self._temp= (uVect, vVect, Amat, Bmat, Fmat,
#                      Gmat, phi, lyaA, lyaB, lyaC)
        return res - np.mean(res)


    @returns(Wavefront)
    def _usingFFT(self, gradientX2DMap, gradientY2DMap):
        # ix= griddata(points, val[:, 0], (gry, grx), method= 'linear')
        # iy= griddata(points, val[:, 1], (gry, grx), method= 'linear')
        phaseSecond= np.gradient(gradientX2DMap)[1] + \
            np.gradient(gradientY2DMap)[0]
        # xx=np.hstack((np.diff(ix, axis=1), np.zeros((1, 264)).T))
        # yy=np.vstack((np.diff(iy, axis=0), np.zeros(264)))
        # phaseSecond= xx + yy
        phaseSecond[np.isnan(phaseSecond)]= 0
        F1= fftpack.fft2(np.ma.masked_array(phaseSecond, phaseSecond==0))
        F2= fftpack.fftshift(F1)
        freq= fftpack.fftshift(fftpack.fftfreq(phaseSecond.shape[0]))
        fx, fy= np.meshgrid(freq, freq)
        f= fx**2 + fy**2
        fphase= F2 / (np.ma.masked_array(f, f==0))
        Z= np.ma.masked_array(
            abs(fftpack.fftshift(fftpack.ifft2(fphase))), phaseSecond==0)
        return Wavefront(Z)


    def _iterationHudginStep(self, phaseMap, gradientX2DMap, gradientY2DMap):
        phaseMap.set_fill_value(0.0)
        phaseMapRollUp= np.roll(phaseMap, 1, 0)
        phaseMapRollDown= np.roll(phaseMap, -1, 0)
        phaseMapRollRight= np.roll(phaseMap, 1, 1)
        phaseMapRollLeft= np.roll(phaseMap, -1, 1)
        mapYRollUp= np.roll(gradientY2DMap, 1, 0)
        mapYRollDown= np.roll(gradientY2DMap, -1, 0)
        mapXRollRight= np.roll(gradientX2DMap, 1, 1)
        mapXRollLeft= np.roll(gradientX2DMap, -1, 1)
        res= 0.25 * (phaseMapRollUp + phaseMapRollDown +
                     phaseMapRollLeft + phaseMapRollRight) + \
             0.25 * (mapXRollRight-mapXRollLeft) + \
             0.25 * (mapYRollUp-mapYRollDown)
        return res


    @staticmethod
    def _getWfAndGradient(zc, diameterInPixel=32):
        from prima.metrology.utils.zernike_generator import ZernikeGenerator
        from _functools import reduce
        zg= ZernikeGenerator(diameterInPixel)
        wf= reduce((lambda x, y: x+ zc.getZ([y])* zg.getZernike(y)),
                   zc.zernikeIndexes())
        mapX= reduce((lambda x, y: x+ zc.getZ([y])* zg.getDerivativeX(y)),
                   zc.zernikeIndexes())
        mapY= reduce((lambda x, y: x+ zc.getZ([y])* zg.getDerivativeY(y)),
                   zc.zernikeIndexes())
        return (wf, mapX, mapY)


    @returns(Wavefront)
    def _useingIterativeHudgin(self, gradientX2DMap, gradientY2DMap):
        phaseMap= gradientX2DMap* 0.0
        phaseMapNow= self._iterationHudginStep(phaseMap, gradientX2DMap, gradientY2DMap)
        