import pickle

__version__ = "$Id$"


class Constants:
    n_zernikes = 21
    PICKLE_PROTOCOL= pickle.HIGHEST_PROTOCOL
    METER_2_NANOMETER= 1e9


class ZmqPorts(object):

    def __init__(self, configuration):
        self._conf= configuration


    @property
    def WFS_CAMERA_PUBLISHER_PORT(self):
        return self._conf.publisherPort('serverWfsCamera')


    @property
    def WFS_CAMERA_REPLY_PORT(self):
        return self._conf.replyPort('serverWfsCamera')


    @property
    def WFS_CAMERA_STATUS_PORT(self):
        return self._conf.statusPort('serverWfsCamera')


    @property
    def AUX_CAMERA_PUBLISHER_PORT(self):
        return self._conf.publisherPort('serverAuxCamera')


    @property
    def AUX_CAMERA_REPLY_PORT(self):
        return self._conf.replyPort('serverAuxCamera')


    @property
    def AUX_CAMERA_STATUS_PORT(self):
        return self._conf.statusPort('serverAuxCamera')


    @property
    def PUPILS_FINDER_REPLY_PORT(self):
        return self._conf.replyPort('pupilFinder')


    @property
    def PUPILS_FINDER_PUBLISHER_PORT(self):
        return self._conf.publisherPort('pupilFinder')


    @property
    def PUPILS_FINDER_STATUS_PORT(self):
        return self._conf.statusPort('pupilFinder')


    @property
    def HW_PUBLISHER_PORT(self):
        return self._conf.publisherPort('serverHw')


    @property
    def HW_REPLY_PORT(self):
        return self._conf.replyPort('serverHw')


    @property
    def HW_STATUS_PORT(self):
        return self._conf.statusPort('serverHw')


    @property
    def ARBITRATOR_REPLY_PORT(self):
        return self._conf.replyPort('arbitrator')


    @property
    def ARBITRATOR_STATUS_PORT(self):
        return self._conf.statusPort('arbitrator')
