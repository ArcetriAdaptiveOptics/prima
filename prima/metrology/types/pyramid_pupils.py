import numpy as np
from prima.metrology.types.mask import CircularMask
from prima.metrology.types.region_of_interest import RegionOfInterest
from prima.metrology._compat import Logger


class CircularPupil(object):

    def __init__(self, centerYX, radius):
        self.centerX= int(centerYX[1])
        self.centerY= int(centerYX[0])
        self.radius= int(radius)
        self.roi= RegionOfInterest(self.centerX - radius,
                                   self.centerX + radius,
                                   self.centerY - radius,
                                   self.centerY + radius)


    def extractMaskedRoiFrom(self, frame):
        mask= CircularMask((2* self.radius, 2* self.radius)).mask()
        return np.ma.masked_array(self.roi.cutOut(frame), mask=mask)


    def __str__(self):
        return "center=(%d, %d), radius=%d" % (
            self.centerY, self.centerX, self.radius)


    def __eq__(self, o):
        if self.centerX != o.centerX:
            return False
        if self.centerY != o.centerY:
            return False
        if self.radius != o.radius:
            return False
        return True


    def __ne__(self, o):
        return not self.__eq__(o)


class PyramidPupilsNames():
    A= 'A'
    B= 'B'
    C= 'C'
    D= 'D'
    ALL_PUPILS= [A, B, C, D]
    NUMBER_OF_PUPILS= 4


class PyramidPupilsException(Exception):
        pass


class PyramidPupils(object):

    sidesMaxFractionalVariance= 0.2
    anglesMaxVarianceInDegree= 20

    def __init__(self, pupil1, pupil2, pupil3, pupil4):
        self._angles= None
        self._sides= None
        self._pupils= {}
        self._pupils[PyramidPupilsNames.A]= pupil1
        self._pupils[PyramidPupilsNames.B]= pupil2
        self._pupils[PyramidPupilsNames.C]= pupil3
        self._pupils[PyramidPupilsNames.D]= pupil4
        self._checkRadiiAreEqual()
        self._reorderAccordingToGeometry()
        self._checkCentersAreVerticesOfASquare()
        self._checkRadiusIsNotTooBig()


    def _resetCachedValues(self):
        self._angles= None
        self._sides= None


    def _checkRadiusIsNotTooBig(self):
        if 2* self.radius() >= np.min(self.sides()):
            raise PyramidPupilsException(
                "Radius is too big. (radius %f, sides %s)" % (
                    self.radius(), str(self.sides())))


    def _checkCentersAreVerticesOfASquare(self):
        sides= self.sides()
        if np.ptp(sides) >= self.sidesMaxFractionalVariance * np.mean(sides):
            raise PyramidPupilsException(
                "Sides variance exceeds max permitted "
                "value of %f (sides: %s)" % (self.sidesMaxFractionalVariance,
                                             str(sides)))

        if np.any(np.abs(self.angles()- 90) > self.anglesMaxVarianceInDegree):
            raise PyramidPupilsException(
                "Angle variance exceeds max permitted "
                "value of %f (sides: %s)" % (self.anglesMaxVarianceInDegree,
                                             str(self.angles())))


    def _reorderAccordingToGeometry(self):
        circPupilsObj= [
            self[PyramidPupilsNames.A],
            self[PyramidPupilsNames.B],
            self[PyramidPupilsNames.C],
            self[PyramidPupilsNames.D]]
        cc= self.centersAsNumpyArray()
        orig= np.mean(cc, axis=0)
        vertices= cc- orig
        theta= np.degrees(np.arctan2(vertices[:, 0], vertices[:, 1]))
        try:
            reordered= [
                circPupilsObj[np.nonzero((90<theta) & (theta<=180))[0][0]],
                circPupilsObj[np.nonzero((0<theta) & (theta<=90))[0][0]],
                circPupilsObj[np.nonzero((-180<theta) & (theta<=-90))[0][0]],
                circPupilsObj[np.nonzero((-90<theta) & (theta<=0))[0][0]]]
        except IndexError:
            raise PyramidPupilsException(
                "Centers identify a crooked quadrilateral. "
                "(Theta %s)" % str(theta))
        self._pupils[PyramidPupilsNames.A]= reordered[0]
        self._pupils[PyramidPupilsNames.B]= reordered[1]
        self._pupils[PyramidPupilsNames.C]= reordered[2]
        self._pupils[PyramidPupilsNames.D]= reordered[3]
        self._resetCachedValues()


    def _checkRadiiAreEqual(self):
        radii= np.array([pup.radius for pup in self.pupils()])
        if np.ptp(radii) != 0:
            raise PyramidPupilsException("Pupils radii are unequal: %s"
                                         % str(radii))


    def __str__(self):
        ret= ""
        for pupil in PyramidPupilsNames.ALL_PUPILS:
            ret+= "%s: %s; " % (pupil, str(self._pupils[pupil]))
        return ret


    def __eq__(self, o):
        for pupil in PyramidPupilsNames.ALL_PUPILS:
            if self._pupils[pupil] != o._pupils[pupil]:
                return False
        return True


    def __ne__(self, o):
        return not self.__eq__(o)


    def __getitem__(self, item):
        return self._pupils[item]


    def radius(self):
        return self._pupils[PyramidPupilsNames.A].radius


    def pupils(self):
        for pupil in PyramidPupilsNames.ALL_PUPILS:
            yield self._pupils[pupil]

    def pupilsDict(self):
        '''
        Generator iterating on the pupil dictionary.
        Use it with:
          for p,k in pyramidpupils.pupilsDict(): ...
        '''
        for pupil in PyramidPupilsNames.ALL_PUPILS:
            yield pupil, self._pupils[pupil]


    @staticmethod
    def fromNumpyArray(centersYX, radius):
        assert centersYX.shape== (PyramidPupilsNames.NUMBER_OF_PUPILS, 2)
        pup= {}
        for i in range(PyramidPupilsNames.NUMBER_OF_PUPILS):
            pup[i]= CircularPupil(centersYX[i], radius)
        return PyramidPupils(pup[0], pup[1], pup[2], pup[3])


    def centersAsNumpyArray(self):
        ret= np.zeros((PyramidPupilsNames.NUMBER_OF_PUPILS, 2))
        i= 0
        for pup in self.pupils():
            ret[i, :]= np.array([pup.centerY, pup.centerX])
            i+= 1
        return ret


    def _sidesVectors(self):
        cc= self.centersAsNumpyArray()
        vBA= cc[1]- cc[0]
        vDB= cc[3]- cc[1]
        vCD= cc[2]- cc[3]
        vAC= cc[0]- cc[2]
        return np.array([vBA, vDB, vCD, vAC])


    def sides(self):
        if self._sides is None:
            sidesV= self._sidesVectors()
            self._sides= np.linalg.norm(sidesV, axis=1)
        return self._sides


    def _angleBetweenVectorInDegree(self, a, b):
        return np.degrees(np.arctan2(np.linalg.det([a, b]), np.dot(a, b)))


    def angles(self):
        if self._angles is None:
            dd= self._sidesVectors()
            ang= np.zeros(4)
            ang[0]= self._angleBetweenVectorInDegree(dd[0], dd[1])
            ang[0]= np.degrees(np.arctan2(np.linalg.det([dd[0], dd[1]]),
                                          np.dot(dd[0], dd[1])))
            ang[1]= np.degrees(np.arctan2(np.linalg.det([dd[1], dd[2]]),
                                          np.dot(dd[1], dd[2])))
            ang[2]= np.degrees(np.arctan2(np.linalg.det([dd[2], dd[3]]),
                                          np.dot(dd[2], dd[3])))
            ang[3]= np.degrees(np.arctan2(np.linalg.det([dd[3], dd[0]]),
                                          np.dot(dd[3], dd[0])))
            self._angles= ang
        return self._angles
