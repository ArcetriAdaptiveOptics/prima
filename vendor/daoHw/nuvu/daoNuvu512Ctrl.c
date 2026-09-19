/*****************************************************************************
  DAO project
  s.cetre

  daoNuvu512Ctrl.c

  Multi-ROI acquisition (up to 3) + control for Nüvü cameras (nc_driver).

  Command line:
      daoNuvu512MultiCtrl -S imgName nbRoiName roi0Img roi1Img roi2Img extTrigName -L

  Control SHMs created (DAO naming convention, same pattern as EDT ctrl code):
      <imgName>Dit         FLOAT[1]
      <imgName>Fps         FLOAT[1]
      <imgName>Gain        FLOAT[1]    (Analog gain)
      <imgName>EmGain      FLOAT[1]    (EM gain)
      <imgName>TargetTemp  FLOAT[1]
      <imgName>CurrentTemp FLOAT[1]
      <roi0Img>Pos         UIINT32[2]  (posX,posY)
      <roi1Img>Pos         UIINT32[2]
      <roi2Img>Pos         UIINT32[2]
      <imgName>NbRoi       UIINT32[1]
      extTrigName          UIINT32[1]

  Rules:
    - ROI sizes are defined by ROI image SHM sizes.
    - ROI positions are defined by Pos SHMs (2 values only).
    - NcImage is typedef const unsigned short => acquisition buffer is uint16*.
    - Multi-ROI buffer layout assumed concatenated: [ROI0][ROI1][ROI2]
    - daoInfo() lines end with '\n'
 *****************************************************************************/

/*==========================================================================*/
#include <stdio.h>
#include <stdarg.h>
#include <stdlib.h>
#include <unistd.h>
#include <string.h>
#include <sched.h>
#include <signal.h>
#include <errno.h>
#include <stdint.h>
#include <pthread.h>
#include <time.h>

/* DAO headers */
#include "dao.h"
#include "daoTools.h"

/* Nüvü SDK */
#include "nc_driver.h"
//#include "utility.h"

//#define DM
#ifdef DM
IMAGE *shmDm;
#endif
#define ENABLE_PULSE

#define PORT1 0x6010

#define DPIN0 0
#define DPIN1 1
#define DPIN2 2

#ifdef ENABLE_PULSE

#include <sys/io.h>

/* Initialize access to a port */
#define PULSE_INIT(PORT_)                  \
    do {                                   \
        ioperm((PORT_), 1, 1);             \
    } while (0)

/* Generate pulse on bit DPIN_ */
#define PULSE(PORT_, DPIN_)                                \
    do {                                                    \
        unsigned char __mask = (unsigned char)(1u << (DPIN_)); \
        unsigned char __v = inb((PORT_));                   \
        outb((unsigned char)(__v | __mask), (PORT_));       \
        outb((unsigned char)(__v & (unsigned char)~__mask), \
             (PORT_));                                      \
    } while (0)

#else

#define PULSE_INIT(PORT_)        do {} while (0)
#define PULSE(PORT_, DPIN_)      do {} while (0)

#endif
/*==========================================================================*/
#define MAX_NB_ROI 3

/* Camera handle */
static NcCam gCam = NULL;

static IMAGE *imgShm = NULL;
static char   imgName[128] = {0};

static IMAGE *nbRoiShm = NULL;
static char   nbRoiName[128] = {0};

/* ROI image SHMs */
static IMAGE *gRoiImgShm[MAX_NB_ROI] = {NULL, NULL, NULL};
static char   gRoiImgName[MAX_NB_ROI][128] = {{0},{0},{0}};
static int    gRoiNew[MAX_NB_ROI] = {0, 0, 0};   /* Flag set by camReaderThread when new ROI image data is available */
/* Control SHMs (created in camCtrlLoop) */
static IMAGE *gDitShm          = NULL;
static IMAGE *gFpsShm          = NULL;
static IMAGE *gAnalogGainShm   = NULL;   /* <imgName>Gain.im.shm */
static IMAGE *gEmGainShm       = NULL;   /* <imgName>EmGain.im.shm */
static IMAGE *gTargetTempShm   = NULL;
static IMAGE *gCurrentTempShm  = NULL;
static IMAGE *gPosShm[MAX_NB_ROI]       = {NULL, NULL, NULL};

/* Control SHM names */
static char gDitShmName[200]         = {0};
static char gFpsShmName[200]         = {0};
static char gAnalogGainShmName[200]  = {0};
static char gEmGainShmName[200]      = {0};
static char gTargetTempShmName[200]  = {0};
static char gCurrentTempShmName[200] = {0};
static char gPosShmName[MAX_NB_ROI][200]      = {{0},{0},{0}};

static IMAGE *extTrigShm = NULL;
static char   extTrigName[128] = {0};

int board_number;
int channel_number;

/* Threads */
static pthread_t camReaderThread;
static int threadIdCamReader = 0;
static pthread_t camCtrlThread;
static int threadIdCamCtrl = 0;

/* Termination flag */
static int end = 0;

/* Acquisition state lock */
static int gAcqRunning = 0;

/* Executable name */
static char *sArgv0 = NULL;

/*--------------------------------------------------------------------------*/
/**
 * @brief SIGINT callback: set termination flag.
 */
static void endme()
{
    end = 1;
}

/*--------------------------------------------------------------------------*/
/**
 * @brief Display command line help.
 */
static void ShowHelp(void)
{
    printf("%s of " __DATE__ " at " __TIME__ "\n", sArgv0);
    printf("   arguments:\n");
    printf("   -h                 display this message and exit\n");
    printf("   -d n               set daoLogLevel\n");
    printf("   -l str             display str in output\n");
    printf("   -u usec            sleep for usec\n");
    printf("   -S roi0 roi1 roi2  set ROI image SHM names\n");
    printf("   -L                 start loop\n");
    printf("   example:\n");
    printf("     daoNuvu512Ctrl -S /tmp/img.im.shm /tmp/roi0.im.shm /tmp/roi1.im.shm /tmp/roi2.im.shm /tmp/extTrig.im.shm -L\n");
    printf("\n");
}

int initialize(NcCam* camera, int board, int channel)
{
	int error = NC_SUCCESS; //We initialize an error flag variable
	if (*camera == NULL) {
		// Opens the acquisition channel using the automatic detection
		// A negative buffer count uses the recommended number of buffers appropriate
		// for the connected camera's model
		//error = ncCamOpen(NC_AUTO_UNIT, NC_AUTO_CHANNEL, -1, camera);
		error = ncCamOpen(board, channel, -1, camera);
		if (error != NC_SUCCESS) {
			return error;
		}
	}

    enum Ampli ncAmpliNo;
	char ncAmpliString[32];
	int vertFreq;
	int horizFreq;
	error = ncCamGetReadoutMode(*camera, 2, &ncAmpliNo, ncAmpliString, &vertFreq, &horizFreq);
	if (error != NC_SUCCESS) {
		return error;
	}
    printf("mode 2 : Ampli No %d (%s), vert freq %d Hz, horiz freq %d Hz\n", ncAmpliNo, ncAmpliString, vertFreq, horizFreq);
	// For this example we will not bother checking for the available readout modes on the
	// camera and simply select the first one as it is the prefered mode and always valid
	error = ncCamSetReadoutMode(*camera, 2);
	if (error != NC_SUCCESS) {
		return error;
	}

	//Recover the readout time for use later
	double readoutTime;
	error = ncCamGetReadoutTime(*camera, &readoutTime);
    daoInfo("Readout time: %.2f ms\n", readoutTime);
	if (error != NC_SUCCESS) {
		return error;
	}

	//The exposure time is set to the same value as the readout time
	double exposureTime = readoutTime;
	error = ncCamSetExposureTime(*camera, exposureTime);
    daoInfo("Exposure time: %.2f ms\n", exposureTime);
	if (error != NC_SUCCESS) {
		return error;
	}

	//We set a reasonable waiting time
	//double waitingTime = 0.1 * exposureTime;
	double waitingTime = 0. * exposureTime;
	error = ncCamSetWaitingTime(*camera, waitingTime);
    daoInfo("Waiting time: %.2f ms\n", waitingTime);
	if (error == NC_ERROR_CAM_NO_FEATURE) {
		// Some readout modes do not support waiting time and will return
		//	NC_ERROR_CAM_NO_FEATURE in which case this step can be skipped
		error = NC_SUCCESS;
		waitingTime = 0.0;
	}
	else if (error != NC_SUCCESS) {
		return error;
	}

	//We set a long enough timeout
	error = ncCamSetTimeout(*camera, (int)(waitingTime + readoutTime + exposureTime) + 1000);
	if (error != NC_SUCCESS) {
		return error;
	}

    // Retrieves the number of frames that must be returned before valid frames enter the processing or read queues.
	int frameLatency;
	error = ncCamGetFrameLatency(*camera, &frameLatency);
    daoInfo("Frame Latency: %d\n", frameLatency);
	if (error != NC_SUCCESS) {
		return error;
	}

    error = ncCamSilenceFunctionLogging(*camera, "ncCamGetImageParams", 1);
    daoInfo("Silence ncCamGetImageParams logging: %s\n", (error == NC_SUCCESS) ? "success" : "failure");
	if (error != NC_SUCCESS) {
		return error;
	}
	return error;
}


//This function closes the shutter and calls the destructor
void cleanUp(NcCam camera)
{
	int error = ncCamClose(camera); //Closes and free NcCam structure
	if (error != NC_SUCCESS) {
		printf("\nThe error %d happened while closing the Nuvu Camera driver. For more information about this error, the file nc_error.h can be used\n", error);
	}
}

/*--------------------------------------------------------------------------*/
/**
 * @brief Apply DIT to camera.
 * @param dit Exposure time value.
 * @return Nüvü error code (NC_SUCCESS if no error).
 */
static int camCtrlApplyDit(float dit)
{
    int err = ncCamSetExposureTime(gCam, (double)dit);
    if (err != NC_SUCCESS)
    {
        daoWarning("ncCamSetExposureTime(%.6f) error=%d\n", dit, err);
    }
    //err = ncCamSetWaitingTime(gCam, 0);
    //if (err != NC_SUCCESS)
    //{
    //    daoWarning("ncCamSetWaitingTime(0) error=%d\n", err);
    //}

    return err;
}

/*--------------------------------------------------------------------------*/
/**
 * @brief Apply Analog Gain to camera (range checked every change).
 * @param gain Gain value (SHM float; will be clamped + cast to int).
 * @return Nüvü error code (NC_SUCCESS if no error).
 */
static int camCtrlApplyAnalogGain(float gain)
{
    int err;
    int gmin = 0;
    int gmax = 0;

    err = ncCamGetAnalogGainRange(gCam, &gmin, &gmax);
    if (err != NC_SUCCESS)
    {
        daoWarning("ncCamGetAnalogGainRange error=%d\n", err);
        return err;
    }

    int g = (int)(gain + 0.5f);
    if (g < gmin) g = gmin;
    if (g > gmax) g = gmax;

    err = ncCamSetAnalogGain(gCam, g);
    if (err != NC_SUCCESS)
    {
        daoWarning("ncCamSetAnalogGain(%d) error=%d\n", g, err);
    }

    return err;
}

/*--------------------------------------------------------------------------*/
/**
 * @brief Apply EM Gain to camera (calibrated if available AND current temp in range; else raw).
 *
 * At every change:
 *   - poll current detector temperature
 *   - check calibrated EM availability + calibrated temperature range + gain range
 *   - else check raw EM availability + gain range
 *
 * @param gain Gain value (SHM float; will be clamped + cast to int).
 * @return Nüvü error code (NC_SUCCESS if no error).
 */
static int camCtrlApplyEmGain(float gain)
{
    int err;

    /* Poll current temperature (required for calibrated EM availability) */
    double tAct = 0.0;
    err = ncCamGetDetectorTemp(gCam, &tAct);
    if (err != NC_SUCCESS)
    {
        daoWarning("ncCamGetDetectorTemp error=%d\n", err);
        return err;
    }

    /* ---- Try calibrated EM gain ---- */
    err = ncCamParamAvailable(gCam, CALIBRATED_EM_GAIN, 0);
    if (err == NC_SUCCESS)
    {
        double tMin = 0.0, tMax = 0.0;
        int gmin = 0, gmax = 0;

        err = ncCamGetCalibratedEmGainTempRange(gCam, &tMin, &tMax);
        daoInfo("Cal EM gain temp range: %.2f .. %.2f\n", tMin, tMax);
        if (err != NC_SUCCESS)
        {
            daoWarning("ncCamGetCalibratedEmGainTempRange error=%d\n", err);
        }
        else
        {
            if (tAct >= tMin && tAct <= tMax)
            {
                err = ncCamGetCalibratedEmGainRange(gCam, &gmin, &gmax);
                daoInfo("Cal EM gain range: %d .. %d\n", gmin, gmax);
                if (err != NC_SUCCESS)
                {
                    daoWarning("ncCamGetCalibratedEmGainRange error=%d\n", err);
                }
                else
                {
                    int g = (int)(gain + 0.5f);
                    if (g < gmin) g = gmin;
                    if (g > gmax) g = gmax;

                    err = ncCamSetCalibratedEmGain(gCam, g);
                    if (err != NC_SUCCESS)
                    {
                        daoWarning("ncCamSetCalibratedEmGain(%d) error=%d\n", g, err);
                    }
                    return err;
                }
            }
            else
            {
                daoInfo("Cal EM gain not available at current temp %.2f (range %.2f..%.2f)\n",
                        tAct, tMin, tMax);
            }
        }
    }
    else if (err != NC_ERROR_CAM_NO_FEATURE)
    {
        daoWarning("ncCamParamAvailable(CALIBRATED_EM_GAIN) error=%d\n", err);
    }

    /* ---- Fallback: raw EM gain ---- */
    err = ncCamParamAvailable(gCam, RAW_EM_GAIN, 0);
    if (err == NC_SUCCESS)
    {
        int gmin = 0, gmax = 0;

        err = ncCamGetRawEmGainRange(gCam, &gmin, &gmax);
        if (err != NC_SUCCESS)
        {
            daoWarning("ncCamGetRawEmGainRange error=%d\n", err);
            return err;
        }

        int g = (int)(gain + 0.5f);
        if (g < gmin) g = gmin;
        if (g > gmax) g = gmax;

        err = ncCamSetRawEmGain(gCam, g);
        if (err != NC_SUCCESS)
        {
            daoWarning("ncCamSetRawEmGain(%d) error=%d\n", g, err);
        }
        return err;
    }
    else if (err != NC_ERROR_CAM_NO_FEATURE)
    {
        daoWarning("ncCamParamAvailable(RAW_EM_GAIN) error=%d\n", err);
    }

    daoWarning("No EM gain feature available at current temp %.2f\n", tAct);
    return NC_ERROR_CAM_NO_FEATURE;
}

static int acquireReadoutModes(NcCam camera, int* nbrReadoutModes)
{
	//Investigates about the readout modes available on the camera
	int error = ncCamGetNbrReadoutModes(camera, nbrReadoutModes);
	if (error != NC_SUCCESS) {
		return error;
	}

	printf("READOUT MODES AVAILABLE\n\n");

	for (int i = 1; i <= *nbrReadoutModes; ++i) {
		enum Ampli ncAmpliType;
		int vertFreq;
		int horizFreq;
		char ncAmpliString[32];
		error = ncCamGetReadoutMode(camera, i, &ncAmpliType, ncAmpliString, &vertFreq, &horizFreq);
		//If there is an error, we exit the function to prevent unncessary looping
		if (error) {
			return error;
		}

		//Print out the readout mode
		printf("Readout mode : %d\n", i);
		printf("Ampli Type : %d (%s)\n", ncAmpliType, ncAmpliString);
		printf("Vertical frequency : %d Hz\n", vertFreq);
		printf("Horizontal frequency : %d Hz\n\n", horizFreq);
	}

	return error;
}

/*--------------------------------------------------------------------------*/
/**
 * @brief Apply CCD target temperature to camera (range checked every change).
 * @param tempC Temperature setpoint in Celsius.
 * @return Nüvü error code (NC_SUCCESS if no error).
 */
static int camCtrlApplyTargetTemp(float tempC)
{
    int err;
    double tMin = 0.0, tMax = 0.0;

    err = ncCamGetTargetDetectorTempRange(gCam, &tMin, &tMax);
    if (err != NC_SUCCESS)
    {
        daoWarning("ncCamGetTargetDetectorTempRange error=%d\n", err);
        tMin = -100.0;
        tMax =  100.0;
    }

    double t = (double)tempC;
    if (t < tMin) t = tMin;
    if (t > tMax) t = tMax;

    err = ncCamSetTargetDetectorTemp(gCam, t);
    if (err != NC_SUCCESS)
    {
        daoWarning("ncCamSetTargetDetectorTemp(%.2f) error=%d\n", t, err);
    }

    return err;
}

/*--------------------------------------------------------------------------*/
/**
 * @brief Clamp ROI rectangle inside camera bounds.
 */
static void clampRoi(int maxW, int maxH, int *x, int *y, int *w, int *h)
{
    if (*w < 1) *w = 1;
    if (*h < 1) *h = 1;

    if (*w > maxW) *w = maxW;
    if (*h > maxH) *h = maxH;

    if (*x < 0) *x = 0;
    if (*y < 0) *y = 0;

    if (*x + *w > maxW) *x = maxW - *w;
    if (*y + *h > maxH) *y = maxH - *h;

    if (*x < 0) *x = 0;
    if (*y < 0) *y = 0;
}

/*--------------------------------------------------------------------------*/
/**
 * @brief Read ROI position (posX,posY) from Pos SHM.
 */
static int roiGetPosFromShm(int roiIndex, int *x, int *y)
{
    if (!gPosShm[roiIndex] || !x || !y)
    {
        return DAO_ERROR;
    }
    *x = (int)(gPosShm[roiIndex]->array.UI32[0]);
    *y = (int)(gPosShm[roiIndex]->array.UI32[1]);

    return DAO_SUCCESS;
}

/*--------------------------------------------------------------------------*/
/**
 * @brief Copy a ROI block into a full-frame uint16 image at (x,y), with clipping.
 *
 * dst: full-frame buffer (dstW x dstH)
 * src: ROI buffer (roiW x roiH)
 */
static void blitRoiU16(uint16_t *dst, int dstW, int dstH,
                       const uint16_t *src, int roiW, int roiH,
                       int x, int y)
{
    if (!dst || !src) return;
    if (dstW <= 0 || dstH <= 0 || roiW <= 0 || roiH <= 0) return;

    /* Clip ROI against dst bounds */
    int srcX0 = 0;
    int srcY0 = 0;
    int copyW = roiW;
    int copyH = roiH;

    if (x < 0) { srcX0 = -x; copyW -= srcX0; x = 0; }
    if (y < 0) { srcY0 = -y; copyH -= srcY0; y = 0; }

    if (x + copyW > dstW) copyW = dstW - x;
    if (y + copyH > dstH) copyH = dstH - y;

    if (copyW <= 0 || copyH <= 0) return;

    for (int row = 0; row < copyH; ++row)
    {
        uint16_t *d = dst + (y + row) * dstW + x;
        const uint16_t *s = src + (srcY0 + row) * roiW + srcX0;
        memcpy(d, s, (size_t)copyW * sizeof(uint16_t));
    }
}

/*--------------------------------------------------------------------------*/
/**
 * @brief Apply ROI size (from ROI image SHM) and position (posX,posY).
 *
 * Conservative apply: if pending changes exist, abort + apply + restart.
 */
static int camApplyRoi(int roiIndex, int posX, int posY)
{
    int err;
    int maxW = 0;
    int maxH = 0;

    err = ncCamGetMaxSize(gCam, &maxW, &maxH);
    if (err != NC_SUCCESS)
    {
        daoError("ncCamGetMaxSize error=%d\n", err);
        return err;
    }

    int w = (int)gRoiImgShm[roiIndex]->md[0].size[1];
    int h = (int)gRoiImgShm[roiIndex]->md[0].size[0];

    clampRoi(maxW, maxH, &posX, &posY, &w, &h);

    err = ncCamSetMRoiSize(gCam, roiIndex, w, h);
    if (err != NC_SUCCESS)
    {
        daoError("ncCamSetMRoiSize(%d) error=%d\n", roiIndex, err);
        return err;
    }

    err = ncCamSetMRoiPosition(gCam, roiIndex, posX, posY);
    if (err != NC_SUCCESS)
    {
        daoError("ncCamSetMRoiPosition(%d) error=%d\n", roiIndex, err);
        return err;
    }

    int pending = 0;
    err = ncCamMRoiHasChanges(gCam, &pending);
    if (err != NC_SUCCESS)
    {
        daoError("ncCamMRoiHasChanges error=%d\n", err);
        return err;
    }

    if (pending)
    {
        //While we are acquiring we can't modify, for example,
        //the size of the acquired image.
        //By modifying only the position, we should be able to make changes 
        //without generating an error.
        //However, we must verify that before applying the changes
        int nonStopFlag;
        err = ncCamMRoiCanApplyWithoutStop(gCam, &nonStopFlag);
        if (err)
        {
            daoError("ncCamMRoiCanApplyWithoutStop error=%d\n", err);
            return err;
        }

        if (nonStopFlag == 1)
        {
            //We are clear to make the modification without having to stop the acquisition
            err = ncCamMRoiApply(gCam);
            if (err != NC_SUCCESS)
            {
                daoError("ncCamMRoiApply error=%d\n", err);
                return err;
            }
        }
        else
        {
            printf("changes ignored as they would require a restart.\n");
            err = ncCamMRoiRollback(gCam);
            if (err != NC_SUCCESS)
            {
                daoWarning("ncCamMRoiRollback error=%d\n", err);
            }
        }
    }
    else
    {
        if (gAcqRunning)
        {
            int e2 = ncCamAbort(gCam);
            if (e2 != NC_SUCCESS)
            {
                daoWarning("ncCamAbort error=%d\n", e2);
            }
            gAcqRunning = 0;
            usleep(2000000);
        }

        err = ncCamMRoiApply(gCam);
        if (err != NC_SUCCESS)
        {
            daoError("ncCamMRoiApply error=%d\n", err);
            return err;
        }

        err = ncCamStart(gCam, 0);
        if (err != NC_SUCCESS)
        {
            daoError("ncCamStart (after apply) error=%d\n", err);
            return err;
        }

        gAcqRunning = 1;
    }

    return NC_SUCCESS;
}

/*--------------------------------------------------------------------------*/
/**
 * @brief Set ROI size (from ROI image SHM) and position (posX,posY) without apply/start.
 */
static int camSetRoiNoApply(int roiIndex, int posX, int posY)
{
    int err;
    int maxW = 0;
    int maxH = 0;

    err = ncCamGetMaxSize(gCam, &maxW, &maxH);
    if (err != NC_SUCCESS)
    {
        daoError("ncCamGetMaxSize error=%d\n", err);
        return err;
    }

    int w = (int)gRoiImgShm[roiIndex]->md[0].size[1];
    int h = (int)gRoiImgShm[roiIndex]->md[0].size[0];

    clampRoi(maxW, maxH, &posX, &posY, &w, &h);

    err = ncCamSetMRoiSize(gCam, roiIndex, w, h);
    if (err != NC_SUCCESS)
    {
        daoError("ncCamSetMRoiSize(%d) error=%d\n", roiIndex, err);
        return err;
    }

    err = ncCamSetMRoiPosition(gCam, roiIndex, posX, posY);
    if (err != NC_SUCCESS)
    {
        daoError("ncCamSetMRoiPosition(%d) error=%d\n", roiIndex, err);
        return err;
    }

    return NC_SUCCESS;
}

/*--------------------------------------------------------------------------*/
/**
 * @brief Initial ROI configuration: set ROI0, add ROI1/ROI2, apply once.
 */
static int camConfigureRoisInitial(int nbRoi)
{
    int err;

    int roiCountMax = -1;
    err = ncCamGetMRoiCountMax(gCam, &roiCountMax);
    if (err != NC_SUCCESS)
    {
        daoError("ncCamGetMRoiCountMax error=%d\n", err);
        return err;
    }

    if (roiCountMax < MAX_NB_ROI)
    {
        daoError("Readout mode supports only %d ROI(s)\n", roiCountMax);
        return DAO_ERROR;
    }

    int x0=0,y0=0,x1=0,y1=0,x2=0,y2=0;
    if (roiGetPosFromShm(0, &x0, &y0) != DAO_SUCCESS) return DAO_ERROR;
    if (roiGetPosFromShm(1, &x1, &y1) != DAO_SUCCESS) return DAO_ERROR;
    if (roiGetPosFromShm(2, &x2, &y2) != DAO_SUCCESS) return DAO_ERROR;

    daoInfo("ROI0 pos %d, %d\n", x0, y0);
    daoInfo("ROI1 pos %d, %d\n", x1, y1);
    daoInfo("ROI2 pos %d, %d\n", x2, y2);

    int maxW=0, maxH=0;
    err = ncCamGetMaxSize(gCam, &maxW, &maxH);
    if (err != NC_SUCCESS)
    {
        daoError("ncCamGetMaxSize error=%d\n", err);
        return err;
    }

    int w0 = (int)gRoiImgShm[0]->md[0].size[1];
    int h0 = (int)gRoiImgShm[0]->md[0].size[0];
    int w1 = (int)gRoiImgShm[1]->md[0].size[1];
    int h1 = (int)gRoiImgShm[1]->md[0].size[0];
    int w2 = (int)gRoiImgShm[2]->md[0].size[1];
    int h2 = (int)gRoiImgShm[2]->md[0].size[0];

    clampRoi(maxW, maxH, &x0, &y0, &w0, &h0);
    clampRoi(maxW, maxH, &x1, &y1, &w1, &h1);
    clampRoi(maxW, maxH, &x2, &y2, &w2, &h2);

    if (gAcqRunning)
    {
        int eAbort = ncCamAbort(gCam);
        if (eAbort != NC_SUCCESS)
        {
            daoError("ncCamAbort error=%d\n", eAbort);
            return eAbort;
        }
        gAcqRunning = 0;
        usleep(2000000);
    }

    daoInfo("camSetRoiNoApply\n");
    err = camSetRoiNoApply(0, x0, y0);
    if (err != NC_SUCCESS)
    {
        daoError("camSetRoiNoApply ROI0 error=%d\n", err);
        return err;
    }

    if (nbRoi > 1)
    {
        daoInfo("n>1 ncCamAddMRoi\n");
        err = ncCamAddMRoi(gCam, x1, y1, w1, h1);
        if (err != NC_SUCCESS)
        {
            daoError("ncCamAddMRoi ROI1 error=%d\n", err);
            return err;
        }
    }

    if (nbRoi > 2)
    {
        daoInfo("n>2 ncCamAddMRoi\n");
        err = ncCamAddMRoi(gCam, x2, y2, w2, h2);
        if (err != NC_SUCCESS)
        {
            daoError("ncCamAddMRoi ROI2 error=%d\n", err);
            return err;
        }
    }

    err = ncCamMRoiApply(gCam);
    if (err != NC_SUCCESS)
    {
        daoError("ncCamMRoiApply (MAX_NB_ROI ROI) error=%d\n", err);
        return err;
    }

    return NC_SUCCESS;
}

/*--------------------------------------------------------------------------*/
/**
 * @brief Configure camera to "full frame" using MRoi API:
 *        keep ROI0 only, set ROI0 to (0,0,maxW,maxH), apply once.
 */
static int camConfigureFullFrameFromMRoi(void)
{
    int err;
    int maxW = 0;
    int maxH = 0;

    err = ncCamGetMaxSize(gCam, &maxW, &maxH);
    if (err != NC_SUCCESS)
    {
        daoError("ncCamGetMaxSize error=%d\n", err);
        return err;
    }

    /* Ensure only ROI0 exists */
    int roiCount = 0;
    err = ncCamGetMRoiCount(gCam, &roiCount);
    if (err != NC_SUCCESS)
    {
        daoError("ncCamGetMRoiCount error=%d\n", err);
        return err;
    }

    while (roiCount > 1)
    {
        err = ncCamDeleteMRoi(gCam, 1);
        if (err != NC_SUCCESS)
        {
            daoError("ncCamDeleteMRoi(1) error=%d\n", err);
            return err;
        }
        roiCount--;
    }

    /* Set ROI0 = full sensor */
    err = ncCamSetMRoiPosition(gCam, 0, 0, 0);
    if (err != NC_SUCCESS)
    {
        daoError("ncCamSetMRoiPosition(0) error=%d\n", err);
        return err;
    }

    err = ncCamSetMRoiSize(gCam, 0, maxW, maxH);
    if (err != NC_SUCCESS)
    {
        daoError("ncCamSetMRoiSize(0) error=%d\n", err);
        return err;
    }

    err = ncCamMRoiApply(gCam);
    if (err != NC_SUCCESS)
    {
        daoError("ncCamMRoiApply (full frame) error=%d\n", err);
        return err;
    }

    return NC_SUCCESS;
}

/*--------------------------------------------------------------------------*/
/**
 * @brief Publish initial control values to SHMs (placeholders).
 */
static void camCtrlPublishInitialValues(void)
{
    float dit         = 0.0f;
    float fps         = 0.0f;
    float ag          = 0.0f;
    float emg         = 0.0f;
    float targetTemp  = 0.0f;
    float currentTemp = 0.0f;

    daoShmImage2Shm((float*)&dit,         1, &gDitShm[0]);
    daoShmImage2Shm((float*)&fps,         1, &gFpsShm[0]);
    daoShmImage2Shm((float*)&ag,          1, &gAnalogGainShm[0]);
    daoShmImage2Shm((float*)&emg,         1, &gEmGainShm[0]);
    daoShmImage2Shm((float*)&targetTemp,  1, &gTargetTempShm[0]);
    daoShmImage2Shm((float*)&currentTemp, 1, &gCurrentTempShm[0]);
}

/*--------------------------------------------------------------------------*/
/**
 * @brief Control thread.
 */
void *camCtrlLoop(void *thread_data)
{
    int threadId;
    memcpy(&threadId, thread_data, sizeof(int));
    daoDebug("camCtrlLoop thread id %d\n", threadId);
    daoInfo("Creating control SHMs\n");

    uint32_t size1[2];
    size1[0] = 1;
    size1[1] = 1;

    gDitShm         = (IMAGE*)malloc(sizeof(IMAGE));
    gFpsShm         = (IMAGE*)malloc(sizeof(IMAGE));
    gAnalogGainShm  = (IMAGE*)malloc(sizeof(IMAGE));
    gEmGainShm      = (IMAGE*)malloc(sizeof(IMAGE));
    gTargetTempShm  = (IMAGE*)malloc(sizeof(IMAGE));
    gCurrentTempShm = (IMAGE*)malloc(sizeof(IMAGE));

    if (!gDitShm || !gFpsShm || !gAnalogGainShm || !gEmGainShm || !gTargetTempShm || !gCurrentTempShm)
    {
        daoError("malloc control SHM objects failed\n");
        pthread_exit((void*)(intptr_t)DAO_ERROR);
    }

    daoToolsInsertShmNamePrefix(imgName, "Dit",         gDitShmName);
    daoToolsInsertShmNamePrefix(imgName, "Fps",         gFpsShmName);
    daoToolsInsertShmNamePrefix(imgName, "Gain",        gAnalogGainShmName);   /* <name>Gain.im.shm */
    daoToolsInsertShmNamePrefix(imgName, "EmGain",      gEmGainShmName);       /* <name>EmGain.im.shm */
    daoToolsInsertShmNamePrefix(imgName, "TargetTemp",  gTargetTempShmName);
    daoToolsInsertShmNamePrefix(imgName, "CurrentTemp", gCurrentTempShmName);

    daoShmImageCreate(gDitShm,         gDitShmName,         2, size1, _DATATYPE_FLOAT,  1, 0);
    daoShmImageCreate(gFpsShm,         gFpsShmName,         2, size1, _DATATYPE_FLOAT,  1, 0);
    daoShmImageCreate(gAnalogGainShm,  gAnalogGainShmName,  2, size1, _DATATYPE_FLOAT,  1, 0);
    daoShmImageCreate(gEmGainShm,      gEmGainShmName,      2, size1, _DATATYPE_FLOAT,  1, 0);
    daoShmImageCreate(gTargetTempShm,  gTargetTempShmName,  2, size1, _DATATYPE_FLOAT,  1, 0);
    daoShmImageCreate(gCurrentTempShm, gCurrentTempShmName, 2, size1, _DATATYPE_FLOAT,  1, 0);

    unsigned long cnt0DIT        = gDitShm[0].md[0].cnt0;
    unsigned long cnt0FPS        = gFpsShm[0].md[0].cnt0;
    unsigned long cnt0ANALOGGAIN = gAnalogGainShm[0].md[0].cnt0;
    unsigned long cnt0EMGAIN     = gEmGainShm[0].md[0].cnt0;
    unsigned long cnt0TARGETTEMP = gTargetTempShm[0].md[0].cnt0;

    unsigned long cnt0POS[MAX_NB_ROI];
    cnt0POS[0] = gPosShm[0][0].md[0].cnt0;
    cnt0POS[1] = gPosShm[1][0].md[0].cnt0;
    cnt0POS[2] = gPosShm[2][0].md[0].cnt0;

    unsigned long cnt0NBROI = nbRoiShm[0].md[0].cnt0;

    extTrigShm = (IMAGE *)malloc(sizeof(IMAGE));
    if (!extTrigShm)
    {
        daoError("malloc extTrigShm failed\n");
        pthread_exit((void*)(intptr_t)DAO_ERROR);
    }
    daoShmShm2Img(extTrigName, &extTrigShm[0]);

    unsigned long cnt0EXTTRIG = extTrigShm[0].md[0].cnt0;
    int err = NC_SUCCESS;

    camCtrlPublishInitialValues();

    /* Initialize CurrentTemp once */
    {
        double tAct = 0.0;
        int e2 = ncCamGetDetectorTemp(gCam, &tAct);
        if (e2 == NC_SUCCESS)
        {
            float f = (float)tAct;
            daoShmImage2Shm((float*)&f, 1, &gCurrentTempShm[0]);
        }
        else
        {
            daoWarning("ncCamGetDetectorTemp error=%d\n", e2);
        }
    }

    struct timespec tLastTempPoll;
    clock_gettime(CLOCK_MONOTONIC, &tLastTempPoll);

    daoInfo("ENTERING CONTROL LOOP\n");
    while (!end)
    {
        if (cnt0FPS != gFpsShm[0].md[0].cnt0)
        {
            cnt0FPS = gFpsShm[0].md[0].cnt0;
            printf("\n"); fflush(stdout);
            daoInfo("New FPS %.3f\n", gFpsShm[0].array.F[0]);
        }

        if (cnt0DIT != gDitShm[0].md[0].cnt0)
        {
            cnt0DIT = gDitShm[0].md[0].cnt0;
            float dit = gDitShm[0].array.F[0];

            printf("\n"); fflush(stdout);
            daoInfo("New DIT %.3f\n", dit);

            int e2 = camCtrlApplyDit(dit);
            if (e2 != NC_SUCCESS)
            {
                daoWarning("DIT apply error=%d\n", e2);
            }
        }

        if (cnt0ANALOGGAIN != gAnalogGainShm[0].md[0].cnt0)
        {
            cnt0ANALOGGAIN = gAnalogGainShm[0].md[0].cnt0;
            float gain = gAnalogGainShm[0].array.F[0];

            printf("\n"); fflush(stdout);
            daoInfo("New ANALOG GAIN %.3f\n", gain);

            int e2 = camCtrlApplyAnalogGain(gain);
            if (e2 != NC_SUCCESS)
            {
                daoWarning("ANALOG GAIN apply error=%d\n", e2);
            }
        }

        if (cnt0EMGAIN != gEmGainShm[0].md[0].cnt0)
        {
            cnt0EMGAIN = gEmGainShm[0].md[0].cnt0;
            float gain = gEmGainShm[0].array.F[0];

            printf("\n"); fflush(stdout);
            daoInfo("New EM GAIN %.3f\n", gain);

            int e2 = camCtrlApplyEmGain(gain);
            if (e2 != NC_SUCCESS)
            {
                daoWarning("EM GAIN apply error=%d\n", e2);
            }
        }

        if (cnt0TARGETTEMP != gTargetTempShm[0].md[0].cnt0)
        {
            cnt0TARGETTEMP = gTargetTempShm[0].md[0].cnt0;
            float targetTemp = gTargetTempShm[0].array.F[0];

            printf("\n"); fflush(stdout);
            daoInfo("New TARGET TEMP %.3f\n", targetTemp);

            int e2 = camCtrlApplyTargetTemp(targetTemp);
            if (e2 != NC_SUCCESS)
            {
                daoWarning("TARGET TEMP apply error=%d\n", e2);
            }
        }

        /* Poll CurrentTemp every second */
        {
            struct timespec tNow;
            clock_gettime(CLOCK_MONOTONIC, &tNow);

            double dt = (double)(tNow.tv_sec - tLastTempPoll.tv_sec);
            dt += (double)(tNow.tv_nsec - tLastTempPoll.tv_nsec) / 1e9;

            if (dt >= 1.0)
            {
                tLastTempPoll = tNow;

                double tAct = 0.0;
                int e2 = ncCamGetDetectorTemp(gCam, &tAct);
                if (e2 == NC_SUCCESS)
                {
                    float f = (float)tAct;
                    daoShmImage2Shm((float*)&f, 1, &gCurrentTempShm[0]);
                }
                else
                {
                    daoWarning("ncCamGetDetectorTemp error=%d\n", e2);
                }
            }
        }

        if (cnt0EXTTRIG != extTrigShm[0].md[0].cnt0)
        {
            cnt0EXTTRIG = extTrigShm[0].md[0].cnt0;

            if (gAcqRunning)
            {
                err = ncCamAbort(gCam);
                if (err != NC_SUCCESS)
                {
                    daoError("ncCamAbort error=%d\n", err);
                }
                gAcqRunning = 0;
                usleep(2000000);
            }

            if (extTrigShm[0].array.UI32[0] != 0)
            {
                err = ncCamSetTriggerMode(gCam, CONT_LOW_HIGH, 1);
                if (err != NC_SUCCESS)
                {
                    daoError("ncCamSetTriggerMode(CONT_LOW_HIGH) error=%d\n", err);
                }
            }
            else
            {
                err = ncCamSetTriggerMode(gCam, INTERNAL, 1);
                if (err != NC_SUCCESS)
                {
                    daoError("ncCamSetTriggerMode(INTERNAL) error=%d\n", err);
                }
            }

            err = ncCamStart(gCam, 0);
            if (err != NC_SUCCESS)
            {
                daoError("ncCamStart (after trig change) error=%d\n", err);
                gAcqRunning = 0;
            }
            else
            {
                gAcqRunning = 1;
            }

            printf("\n"); fflush(stdout);
            daoInfo("New EXTTRIG %d\n", extTrigShm[0].array.UI32[0]);
        }

        if (cnt0NBROI != nbRoiShm[0].md[0].cnt0)
        {
            cnt0NBROI = nbRoiShm[0].md[0].cnt0;

            if (gAcqRunning)
            {
                int e2 = ncCamAbort(gCam);
                if (e2 != NC_SUCCESS)
                {
                    daoError("ncCamAbort error=%d\n", e2);
                }
                gAcqRunning = 0;
                usleep(2000000);
            }

            int roiCount = 0;
            err = ncCamGetMRoiCount(gCam, &roiCount);
            if (err != NC_SUCCESS)
            {
                daoError("ncCamGetMRoiCount error=%d\n", err);
            }
            daoInfo("Current config: %d ROI\n", roiCount);

            /* Keep ROI0, delete ROI1..ROI(n-1) */
            while (roiCount > 1)
            {
                err = ncCamDeleteMRoi(gCam, 1);
                if (err != NC_SUCCESS)
                {
                    daoError("ncCamDeleteMRoi(1) error=%d\n", err);
                    break;
                }
                roiCount--;
            }

            uint32_t newNbRoi = nbRoiShm[0].array.UI32[0];

            daoInfo("Configuring ROIs for newNbRoi=%u\n", newNbRoi);

            if (newNbRoi == 0)
            {
                err = camConfigureFullFrameFromMRoi();
            }
            else
            {
                err = camConfigureRoisInitial((int)newNbRoi);
            }

            if (err != NC_SUCCESS)
            {
                daoError("ROI reconfigure error=%d\n", err);
                gAcqRunning = 0;
            }
            else
            {
                err = ncCamStart(gCam, 0);
                if (err != NC_SUCCESS)
                {
                    daoError("ncCamStart (after ROI apply) error=%d\n", err);
                    gAcqRunning = 0;
                }
                else
                {
                    gAcqRunning = 1;
                }
                int nbrReadoutModes;
                acquireReadoutModes(gCam, &nbrReadoutModes); // just to display readout modes
            }

            printf("\n"); fflush(stdout);
            daoInfo("New Nb of Roi %d\n", nbRoiShm[0].array.UI32[0]);
        }

        // Change in ROI position, only if multi-ROI enabled
        if (nbRoiShm[0].array.UI32[0] > 0)
        {
            for (int i = 0; i < (int)nbRoiShm[0].array.UI32[0]; ++i)
            {
                if (cnt0POS[i] != gPosShm[i][0].md[0].cnt0)
                {
                    cnt0POS[i] = gPosShm[i][0].md[0].cnt0;

                    int x = 0;
                    int y = 0;
                    if (roiGetPosFromShm(i, &x, &y) == DAO_SUCCESS)
                    {
                        printf("\n"); fflush(stdout);
                        daoInfo("ROI%d new Pos x=%d y=%d\n", i, x, y);

                        err = camApplyRoi(i, x, y);
                        if (err != NC_SUCCESS)
                        {
                            daoWarning("ROI%d apply error=%d\n", i, err);
                        }
                        gRoiNew[i] = 1;
                    }
                }
            }
        }

        usleep(100);
    }

    printf("\n"); fflush(stdout);
    daoInfo("EXITING CONTROL LOOP\n");

    pthread_exit((void*)(intptr_t)DAO_SUCCESS);
}

/*--------------------------------------------------------------------------*/
/**
 * @brief Reader thread: acquire multi-ROI buffer and write ROI0/1/2 SHMs.
 *
 * Prints fps as EDT style:
 *    "\r fps = .... Hz"
 */
void *camRealTimeLoop(void *thread_data)
{
    int threadId;
    memcpy(&threadId, thread_data, sizeof(int));
    daoDebug("camRealTimeLoop thread id %d\n", threadId);
    PULSE_INIT(PORT1);
#ifdef DM
    shmDm = (IMAGE *)malloc(sizeof(IMAGE));
    daoShmShm2Img("/tmp/dmTt.im.shm", &shmDm[0]);
    float cmd[822];
    float sign=1.0;
    for(int k=0; k<822; k++) {
        cmd[k] = 0.1;
    }
#endif
    daoInfo("ENTERING ACQ LOOP\n");

    struct timespec t[2];
    double elapsedTime;

    clock_gettime(CLOCK_REALTIME, &t[0]);
    t[1] = t[0];

    // Open the shutter for the acquisition 
    int error = ncCamSetShutterMode(gCam, OPEN);
    if (error != NC_SUCCESS)
    {
        daoError("ncCamSetShutterMode(OPEN), error %d\n", error);
        pthread_exit((void*)(intptr_t)DAO_ERROR);
    }

    error = ncCamStart(gCam, 0);
    if (error != NC_SUCCESS)
    {
        daoError("ncCamStart, error %d\n", error);
        pthread_exit((void*)(intptr_t)DAO_ERROR);
    }
    gAcqRunning = 1;
    //error = ncCamSetReadoutMode(gCam, 2);
    //if (error != NC_SUCCESS)
    //{
    //    daoError("ncCamSetShutterMode(OPEN), error %d\n", error);
    //    pthread_exit((void*)(intptr_t)DAO_ERROR);
    //}
    uint64_t n=0;
    uint64_t n0=0;
    uint64_t n1=0;
    uint64_t n2=0;
    int waitCounter=0;
    ImageParams imageParams=NULL;

    int offsetX0=0, offsetY0=0, width0=0, height0=0;
    int offsetX0Orig=0, offsetY0Orig=0, width0Orig=0, height0Orig=0;

    int offsetX1=0, offsetY1=0, width1=0, height1=0;
    int offsetX1Orig=0, offsetY1Orig=0, width1Orig=0, height1Orig=0;

    int offsetX2=0, offsetY2=0, width2=0, height2=0;
    int offsetX2Orig=0, offsetY2Orig=0, width2Orig=0, height2Orig=0;

    while (!end)
    {
        t[0] = t[1];

        NcImage *img = NULL;

        if (gAcqRunning)
        {
            error = ncCamRead(gCam, &img);
            if (error != NC_SUCCESS)
            {
                daoWarning("ncCamRead error=%d\n", error);
                clock_gettime(CLOCK_REALTIME, &t[1]);
                continue;
            }
            PULSE(PORT1, DPIN0);

            // If ROI has changed, get teh ImageParams until it matches the wanted ROI. The goal is to ensure the ROI positon match.
            if (gRoiNew[0] == 1)
            {
                // Open only once the image parameters object at the beginning (i.e. ==NULL)
                if (imageParams == NULL)
                {
                    error = ncCamOpenImageParams(&imageParams);
                    if (error != NC_SUCCESS)
                    {
                        daoWarning("ncCamOpenImageParams error=%d\n", error);
                    }
                }

                //Get the image parameters for this acquisition
                error = ncCamGetImageParams(gCam, img, imageParams);
                if (error != NC_SUCCESS)
                {
                    daoWarning("ncCamGetImageParams error=%d\n", error);
                }

                // Retrieve the ROI position for this acquisition
                error = ncCamGetMRoiInputRegion(imageParams, 0, &offsetX0, &offsetY0, &width0, &height0);
                if (error != NC_SUCCESS)
                {
                    daoWarning("ncCamGetMRoiInputRegion error=%d\n", error);
                }
                if (offsetX0 != offsetX0Orig || offsetY0 != offsetY0Orig || width0 != width0Orig || height0 != height0Orig)
                {
                    offsetX0Orig = offsetX0;
                    offsetY0Orig = offsetY0;
                    width0Orig   = width0;
                    height0Orig  = height0;
                    daoInfo("Acquisition ROI0 changed to (%d,%d) size (%d x %d)\n", offsetX0, offsetY0, width0, height0);
                }
                // If the positon match, we can consider that the ROI is correctly applied and we can clear the flag to avoid doing this verification for each acquisition
                if (offsetX0 == (int)gPosShm[0][0].array.UI32[0] && offsetY0 == (int)gPosShm[0][0].array.UI32[1])
                {
                    gRoiNew[0] = 0;
                }
            }

            if (nbRoiShm[0].array.UI32[0] == 0)
            {
                n = (uint64_t)imgShm[0].md[0].size[0] * (uint64_t)imgShm[0].md[0].size[1];
                daoShmImage2Shm((unsigned short*)img, n, &imgShm[0]);
            }
            else
            {
                const unsigned short *base = (const unsigned short *)img;

                gRoiImgShm[0]->md[0].cnt1 = offsetX0;
                gRoiImgShm[0]->md[0].cnt2 = offsetY0;
                n0 = (uint64_t)gRoiImgShm[0]->md[0].size[0] * (uint64_t)gRoiImgShm[0]->md[0].size[1];
                daoShmImage2Shm((unsigned short*)base, n0, &gRoiImgShm[0][0]);

            PULSE(PORT1, DPIN0);
                if (nbRoiShm[0].array.UI32[0] > 1)
                {
                    error = ncCamGetMRoiInputRegion(imageParams, 1, &offsetX1, &offsetY1, &width1, &height1);
                    if (error != NC_SUCCESS)
                    {
                        daoWarning("ncCamGetMRoiInputRegion error=%d\n", error);
                    }
                    if (offsetX1 != offsetX1Orig || offsetY1 != offsetY1Orig || width1 != width1Orig || height1 != height1Orig)
                    {
                        offsetX1Orig = offsetX1;
                        offsetY1Orig = offsetY1;
                        width1Orig   = width1;
                        height1Orig  = height1;
                        daoInfo("Acquisition ROI1 changed to (%d,%d) size (%d x %d)\n", offsetX1, offsetY1, width1, height1);
                    }

                    gRoiImgShm[1]->md[0].cnt1 = offsetX1;
                    gRoiImgShm[1]->md[0].cnt2 = offsetY1;

                    n1 = (uint64_t)gRoiImgShm[1]->md[0].size[0] * (uint64_t)gRoiImgShm[1]->md[0].size[1];
                    daoShmImage2Shm((unsigned short*)(base + n0), n1, &gRoiImgShm[1][0]);
                }

                if (nbRoiShm[0].array.UI32[0] > 2)
                {
                    error = ncCamGetMRoiInputRegion(imageParams, 2, &offsetX2, &offsetY2, &width2, &height2);
                    if (error != NC_SUCCESS)
                    {
                        daoWarning("ncCamGetMRoiInputRegion error=%d\n", error);
                    }
                    if (offsetX2 != offsetX2Orig || offsetY2 != offsetY2Orig || width2 != width2Orig || height2 != height2Orig)
                    {
                        offsetX2Orig = offsetX2;
                        offsetY2Orig = offsetY2;
                        width2Orig   = width2;
                        height2Orig  = height2;
                        daoInfo("Acquisition ROI2 changed to (%d,%d) size (%d x %d)\n", offsetX2, offsetY2, width2, height2);
                    }

                    gRoiImgShm[2]->md[0].cnt1 = offsetX2;
                    gRoiImgShm[2]->md[0].cnt2 = offsetY2;

                    n2 = (uint64_t)gRoiImgShm[2]->md[0].size[0] * (uint64_t)gRoiImgShm[2]->md[0].size[1];
                    daoShmImage2Shm((unsigned short*)(base + n0 + n1), n2, &gRoiImgShm[2][0]);
                }

                /* --- Optional: compose full-frame SHM (zeros + ROIs pasted) --- */
                {
                    int ffW = (int)imgShm[0].md[0].size[1];
                    int ffH = (int)imgShm[0].md[0].size[0];
                    uint16_t *ff = (uint16_t*)imgShm[0].array.UI16;   /* adjust field name if needed */

                    memset(ff, 0, (size_t)ffW * (size_t)ffH * sizeof(uint16_t));

                    int x0=0,y0=0;
                    (void)roiGetPosFromShm(0, &x0, &y0);
                    {
                        int roi0W = (int)gRoiImgShm[0]->md[0].size[1];
                        int roi0H = (int)gRoiImgShm[0]->md[0].size[0];
                        blitRoiU16(ff, ffW, ffH, (const uint16_t*)(base), roi0W, roi0H, x0, y0);
                    }

                    if (nbRoiShm[0].array.UI32[0] > 1)
                    {
                        int x1=0,y1=0;
                        (void)roiGetPosFromShm(1, &x1, &y1);
                        int roi1W = (int)gRoiImgShm[1]->md[0].size[1];
                        int roi1H = (int)gRoiImgShm[1]->md[0].size[0];
                        blitRoiU16(ff, ffW, ffH, (const uint16_t*)(base + n0), roi1W, roi1H, x1, y1);
                    }

                    if (nbRoiShm[0].array.UI32[0] > 2)
                    {
                        int x2=0,y2=0;
                        (void)roiGetPosFromShm(2, &x2, &y2);
                        int roi2W = (int)gRoiImgShm[2]->md[0].size[1];
                        int roi2H = (int)gRoiImgShm[2]->md[0].size[0];
                        blitRoiU16(ff, ffW, ffH, (const uint16_t*)(base + n0 + n1), roi2W, roi2H, x2, y2);
                    }

                    daoShmImagePart2ShmFinalize(&imgShm[0]);
#ifdef DM
                    for(int k=0; k<822; k++) {
                        shmDm[0].array.F[k] = cmd[k] * sign;
                    }
                    daoShmImagePart2ShmFinalize(&shmDm[0]);
#endif
                }
            }

            clock_gettime(CLOCK_REALTIME, &t[1]);

            elapsedTime  = (t[1].tv_sec  - t[0].tv_sec)  * 1e3;
            elapsedTime += (t[1].tv_nsec - t[0].tv_nsec) / 1e6;

            if (elapsedTime > 0.0)
            {
                printf("\r fps = %.3f Hz", 1e6 / (1000.0 * elapsedTime));
            }
            else
            {
                printf("\r fps = inf Hz");
            }
        }
        else
        {
            usleep(1000000);
            waitCounter += 1;
            printf("\rWAIT %d", waitCounter);
        }
        fflush(stdout);
    }

    //close the image parameters for this acquisition
    error = ncCamCloseImageParams(imageParams);
    if (error != NC_SUCCESS)
    {
        daoWarning("ncCamCloseImageParams error=%d\n", error);
    }

    error = ncCamSetShutterMode(gCam, CLOSE);
    if (error != NC_SUCCESS)
    {
        daoError("ncCamSetShutterMode(CLOSE), error %d\n", error);
        pthread_exit((void*)(intptr_t)DAO_ERROR);
    }

    printf("\n");
    daoInfo("EXITING ACQ LOOP\n");
    pthread_exit((void*)(intptr_t)DAO_SUCCESS);
}

/*--------------------------------------------------------------------------*/
/**
 * @brief Main loop: attach SHMs, init camera, start threads.
 */
static int realTimeLoop()
{
    signal(SIGINT, endme);

    imgShm = (IMAGE *)malloc(sizeof(IMAGE));
    daoShmShm2Img(imgName, &imgShm[0]);

    nbRoiShm = (IMAGE *)malloc(sizeof(IMAGE));
    daoToolsInsertShmNamePrefix(imgName, "NbRoi", nbRoiName);
    daoShmShm2Img(nbRoiName, &nbRoiShm[0]);
    daoInfo("Nb ROI = %d\n", nbRoiShm[0].array.UI32[0]);

    for (int i = 0; i < MAX_NB_ROI; ++i)
    {
        gRoiImgShm[i] = (IMAGE*)malloc(sizeof(IMAGE));
        if (!gRoiImgShm[i])
        {
            daoError("malloc ROI IMG object failed (idx=%d)\n", i);
            return DAO_ERROR;
        }

        daoShmShm2Img(gRoiImgName[i], &gRoiImgShm[i][0]);

        daoInfo("ROI%d IMG SHM = %s size=%ux%u atype=%d\n",
                i, gRoiImgName[i],
                gRoiImgShm[i][0].md[0].size[1],
                gRoiImgShm[i][0].md[0].size[0],
                gRoiImgShm[i][0].md[0].atype);
    }

    daoInfo("Opening connection to NUVU CAM\n");
    int err = initialize(&gCam, board_number, channel_number);
    if (err != NC_SUCCESS)
    {
        daoError("initialize error=%d\n", err);
        return DAO_ERROR;
    }

    err = ncCamSetWaitingTime(gCam, 0.0);
    if (err == NC_ERROR_CAM_NO_FEATURE)
    {
        // Some readout modes do not support waiting time and will return
        // NC_ERROR_CAM_NO_FEATURE in which case this step can be skipped
        err = NC_SUCCESS;
    }
    else if (err != NC_SUCCESS)
    {
        daoError("ncCamSetWaitingTime error=%d\n", err);
        return DAO_ERROR;
    }

    for (int i = 0; i < MAX_NB_ROI; ++i)
    {
        gPosShm[i] = (IMAGE*)malloc(sizeof(IMAGE));
        if (!gPosShm[i])
        {
            daoError("malloc Pos SHM object failed (idx=%d)\n", i);
            pthread_exit((void*)(intptr_t)DAO_ERROR);
        }

        daoToolsInsertShmNamePrefix(gRoiImgName[i], "Pos", gPosShmName[i]);
        daoShmShm2Img(gPosShmName[i], &gPosShm[i][0]);
    }

    // If multi ROI enabled, configure ROIs
    if (nbRoiShm[0].array.UI32[0] > 0)
    {
        daoInfo("Configuring initial ROIs\n");
        err = camConfigureRoisInitial(nbRoiShm[0].array.UI32[0]);
        if (err != NC_SUCCESS)
        {
            daoError("camConfigureRoisInitial error=%d\n", err);
            return DAO_ERROR;
        }
    }

    if (pthread_create(&camReaderThread, NULL, camRealTimeLoop, (void *)&threadIdCamReader) != 0)
    {
        daoError("Cannot create camera reader thread\n");
        cleanUp(gCam);
        return DAO_ERROR;
    }

    if (pthread_create(&camCtrlThread, NULL, camCtrlLoop, (void *)&threadIdCamCtrl) != 0)
    {
        daoError("Cannot create camera controller thread\n");
        end = 1;
        void *st = NULL;
        pthread_join(camReaderThread, &st);
        cleanUp(gCam);
        return DAO_ERROR;
    }

    void *statusReader = NULL;
    pthread_join(camReaderThread, &statusReader);

    end = 1;

    void *statusCtrl = NULL;
    pthread_join(camCtrlThread, &statusCtrl);

    cleanUp(gCam);
    gCam = NULL;

    return DAO_SUCCESS;
}

/*--------------------------------------------------------------------------*/
/**
 * @brief Parse input arguments. Style: -S sets params, -L starts loop.
 */
static void DecodeArgs(int argc, char **argv)
{
    char *str;
    int a1;

    argv += 1;
    argc -= 1;

    while (argc-- > 0)
    {
        daoDebug("DecodeArgs: working on '%s'/%d\n", *argv, argc);
        str = *argv++;

        if (str[0] != '-')
        {
            daoError("Do not know arg '%s'\n", str);
            ShowHelp();
            exit(1);
        }

        switch (str[1])
        {
            case 'h':
                ShowHelp();
                exit(0);

            case 'd':
                (void)sscanf(*argv++, "%d", &daoLogLevel);
                argc -= 1;
                break;

            case 'l':
                daoInfo("%s\n", *argv);
                argv += 1;
                argc -= 1;
                break;

            case 'u':
                (void)sscanf(*argv++, "%d", &a1);
                argc -= 1;
                daoInfo("will sleep for %d usec\n", a1);
                (void)usleep(a1);
                break;

            case 'S':
                (void)sscanf(*argv++, "%127s", imgName);
                argc -= 1;
                (void)sscanf(*argv++, "%127s", gRoiImgName[0]);
                argc -= 1;
                (void)sscanf(*argv++, "%127s", gRoiImgName[1]);
                argc -= 1;
                (void)sscanf(*argv++, "%127s", gRoiImgName[2]);
                argc -= 1;
                (void)sscanf(*argv++, "%127s", extTrigName);
                argc -= 1;
                (void)sscanf(*argv++, "%d", &board_number);
                argc -= 1;
                (void)sscanf(*argv++, "%d", &channel_number);
                argc -= 1;
                daoInfo("img SHM      = %s\n", imgName);
                daoInfo("ROI0 IMG SHM = %s\n", gRoiImgName[0]);
                daoInfo("ROI1 IMG SHM = %s\n", gRoiImgName[1]);
                daoInfo("ROI2 IMG SHM = %s\n", gRoiImgName[2]);
                daoInfo("board number   =   %d \n", board_number);
                daoInfo("channel number =   %d \n", channel_number); 
                daoInfo("extTrig SHM  = %s\n", extTrigName);
                break;

            case 'L':
                daoInfo("CAM real time control\n");
                (void)realTimeLoop();
                break;

            default:
                daoError("Do not know arg '%s'\n", str);
                ShowHelp();
                exit(2);
        }
    }

    return;
}

/*==========================================================================*/
/**
 * @brief Program entry point. Sets RT scheduler then runs DecodeArgs().
 */
int main(int argc, char **argv)
{
    int RT_priority = 93;
    struct sched_param schedpar;

    schedpar.sched_priority = RT_priority;
    sched_setscheduler(0, SCHED_FIFO, &schedpar);

    daoLogLevel = 1;
    sArgv0 = *argv;

    DecodeArgs(argc, argv);

    return DAO_SUCCESS;
}
/*==========================================================================*/
