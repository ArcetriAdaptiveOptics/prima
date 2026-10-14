import pickle
from prima.metrology.aoProcess import aoUtils
from prima.metrology._compat import Logger
from prima.metrology.utils.stepable import Stepable
from prima.metrology._compat import override, logEnterAndExit, logFailureAndContinue
from prima.metrology.constants import Constants
from prima.metrology._compat import Snapshotable
from prima.metrology.utils.executor import Task, logTaskFailure, MultiThreadExecutor


__version__= "$Id$"


class SnapshotEntry(object):
    IS_ENABLED= "IS_ENABLED"


class PupilUpdateTask(Task):

    def __init__(self,
                 wfsCamera,
                 imageAnalyzer,
                 pupilFinderAlgo,
                 publisherSocket):
        Task.__init__(self)
        self._camera= wfsCamera
        self._imageAnalyzer= imageAnalyzer
        self._pupilFinderAlgo= pupilFinderAlgo
        self._publisherSocket= publisherSocket
        self._logger= Logger.of("Pupil Update Task")
        self._timekeep = aoUtils.timeKeeper()



    @logTaskFailure
    @override
    def perform(self):
        cameraFrame = self._camera.getLastFrame()

        refinedFrame= self._imageAnalyzer.removeBadPixels(
            cameraFrame.toNumpyArray())
        pupils= self._pupilFinderAlgo.findPupils(refinedFrame)
        self._publisherSocket.send(
            pickle.dumps(pupils, Constants.PICKLE_PROTOCOL))

        if self._timekeep.inc():
            self._logger.notice(
                'Processed %d frames (%5.2f Hz) -'
                ' Average calc time: %5.2f ms' % (
                    self._timekeep.count, self._timekeep.rate,
                    self._timekeep.ms))





class PupilFinder(Stepable, Snapshotable):

    def __init__(self,
                 cameraClient,
                 imageAnalyzer,
                 pupilFinderAlgo,
                 replySocket,
                 publisherSocket,
                 rpcHandler):
        self._camera= cameraClient
        self._imageAnalyzer= imageAnalyzer
        self._pupilFinderAlgo= pupilFinderAlgo
        self._replySocket= replySocket
        self._publisherSocket= publisherSocket
        self._rpcHandler= rpcHandler
        self._logger= Logger.of('PupilFinder')
        self._isTerminated= False
        self._stepCounter= 0
        self._enabled= False
        self._executor= MultiThreadExecutor(maxThreads=2, logger=self._logger)
        self._pupilUpdateTask= PupilUpdateTask(self._camera,
                                               self._imageAnalyzer,
                                               self._pupilFinderAlgo,
                                               self._publisherSocket)
        self._pupilUpdateTaskCtrl= None





    def setExecutor(self, executor):
        self._executor= executor


    def setPupilUpdateTask(self, task):
        self._pupilUpdateTask= task



    def _publishPupils(self):
        if self._pupilUpdateTaskCtrl is None or (
                self._pupilUpdateTaskCtrl.isDone()):
            self._pupilUpdateTaskCtrl= \
                self._executor.execute(self._pupilUpdateTask)


    @logFailureAndContinue
    def _waitUntilPupilUpdateTaskIsDone(self):
        if self._pupilUpdateTaskCtrl is not None:
            self._pupilUpdateTaskCtrl.waitForCompletion(timeoutSec=10)
            self._pupilUpdateTaskCtrl = None


    @override
    def step(self):
        self._rpcHandler.handleRequest(self, self._replySocket, multi=True)
        if self.isEnabled():
            self._publishPupils()
        self._stepCounter+= 1


    def getStepCounter(self):
        return self._stepCounter


    def terminate(self):
        self._logger.notice("Got request to terminate")
        self._isTerminated= True


    @override
    def isTerminated(self):
        return self._isTerminated


    def enable(self):
        self._logger.notice('Enabling pupil finding')
        self._enabled= True


    def disable(self):
        self._logger.notice('Disabling pupil finding')
        self._enabled= False


    def isEnabled(self):
        return self._enabled


    @logEnterAndExit('Entering getSnapshot', 'Executed getSnapshot')
    def getSnapshot(self, prefix):
        snapshot= {}
        snapshot[SnapshotEntry.IS_ENABLED]= self.isEnabled()
        return Snapshotable.prepend(prefix, snapshot)
