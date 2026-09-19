/*****************************************************************************
  DAO project
  s.cetre
 *****************************************************************************/

/*==========================================================================*/
#include <stdio.h>
#include <stdarg.h>
#include <stdlib.h>
#include <unistd.h>
#include <string.h>
#include <math.h>
#include <semaphore.h>
#include <sched.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <ctype.h>
#include <time.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <limits.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <sys/time.h>
#include <termios.h>
#include <pthread.h>
#include <inttypes.h>

/* DAO headers */
extern "C" {
    #include "dao.h"
    #include "daoTools.h"
    }

/* Prevent DLL_EXPORT conflict between dao.h and EVT SDK */
#ifdef DLL_EXPORT
#undef DLL_EXPORT
#endif
/* EVT SDK headers */
#include <EmergentCameraAPIs.h>
#include <emergentframe.h>
#include <EvtParamAttribute.h>
#include <gigevisiondeviceinfo.h>

using namespace Emergent;

/*==========================================================================*/
#define MAX_CAMERAS     10
#define ACQ_BUFFERS     10
#define EVT_SDK_ROOT    "/opt/EVT/eSDK"

/*==========================================================================*/
/* Globals */

static char    *sArgv0 = NULL;
static int      end    = 0;

IMAGE  *shm;
char    shmName[64];
char    cameraName[64];   /* e.g. "EVT-HB-500SM-620015" or empty for first found */

CEmergentCamera camera;
unsigned int    width_max, height_max;

pthread_t camReaderThread;
int       threadIdCamReader = 0;
pthread_t camCtrlThread;
int       threadIdCamCtrl   = 0;

/*==========================================================================*/
static void endme(int sig) { (void)sig; end = 1; }

/*==========================================================================*/
static void ShowHelp(void)
{
    printf("%s of " __DATE__ " at " __TIME__ "\n", sArgv0);
    printf("   arguments:\n");
    printf("   -h                      display this message and exit\n");
    printf("   -d <level>              debug log level\n");
    printf("   -S <shmName> <camName>  set SHM name and camera name\n");
    printf("   -L                      start real-time loop (must follow -S)\n");
    printf("   example: daoEvtCtrl -S pyrIm EVT-HB-500SM-620015 -L\n");
    printf("\n");
}

/*==========================================================================*/
/* Configure camera defaults - mirrors configure_defaults from EVT examples  */
static void configure_defaults(CEmergentCamera *cam)
{
    unsigned int w_max, h_max, param_max;

    /* Pixel format: Mono12 */
    EVT_CameraSetEnumParam(cam, "PixelFormat", "Mono12");

    EVT_CameraSetUInt32Param(cam, "OffsetX", 0);
    EVT_CameraSetUInt32Param(cam, "OffsetY", 0);

    EVT_CameraGetUInt32ParamMax(cam, "Width",  &w_max);
    EVT_CameraSetUInt32Param   (cam, "Width",   w_max);
    EVT_CameraGetUInt32ParamMax(cam, "Height", &h_max);
    EVT_CameraSetUInt32Param   (cam, "Height",  h_max);

    EVT_CameraSetEnumParam  (cam, "AcquisitionMode",       "Continuous");
    EVT_CameraSetUInt32Param(cam, "AcquisitionFrameCount",  1);
    EVT_CameraSetEnumParam  (cam, "TriggerSelector",        "AcquisitionStart");
    EVT_CameraSetEnumParam  (cam, "TriggerMode",            "Off");
    EVT_CameraSetEnumParam  (cam, "TriggerSource",          "Software");
    EVT_CameraSetEnumParam  (cam, "BufferMode",             "Off");
    EVT_CameraSetUInt32Param(cam, "BufferNum",               0);

    EVT_CameraGetUInt32ParamMax(cam, "GevSCPSPacketSize", &param_max);
    EVT_CameraSetUInt32Param   (cam, "GevSCPSPacketSize",   param_max);

    EVT_CameraSetUInt32Param(cam, "Gain",   256);
    EVT_CameraSetUInt32Param(cam, "Offset",   0);
    EVT_CameraSetBoolParam  (cam, "LUTEnable", false);
    EVT_CameraSetBoolParam  (cam, "AutoGain",  false);
}

/*==========================================================================*/
/* Unpack Mono12 buffer (2 bytes/pixel, lower 12 bits used) into uint16 SHM  */
static void unpackMono12(const unsigned char *src, uint32_t npix, IMAGE *image)
{
    /* EVT Mono12: each pixel is a uint16_t (little-endian),
     * but only every other pixel is valid (tap0); tap1 outputs garbage/offset.
     * We interpolate the dead tap1 columns from their neighbours.            */
    uint16_t *unpacked = (uint16_t *)malloc(npix * sizeof(uint16_t));
    if (!unpacked)
    {
        daoError("unpackMono12: malloc failed\n");
        return;
    }

    const uint16_t *s   = (const uint16_t *)src;
    uint32_t        w   = image->md[0].size[0];
    uint32_t        h   = image->md[0].size[1];

    for (uint32_t y = 0; y < h; y++)
    {
        for (uint32_t x = 0; x < w; x++)
        {
            if (x % 2 == 0)
            {
                /* tap0 - valid pixel */
                unpacked[y * w + x] = s[y * w + x] & 0x0FFF;
            }
            else
            {
                /* tap1 - dead: interpolate from left and right neighbours */
                uint16_t left  = s[y * w + x - 1] & 0x0FFF;
                uint16_t right = (x + 1 < w) ? (s[y * w + x + 1] & 0x0FFF) : left;
                unpacked[y * w + x] = (uint16_t)((left + right) / 2);
            }
        }
    }

    daoShmImage2Shm(unpacked, npix, image);
    free(unpacked);
}

/*==========================================================================*/
/* Acquisition thread                                                         */
void *camRealTimeLoop(void *thread_data)
{
    (void)thread_data;
    daoInfo("camRealTimeLoop: starting\n");

    EVT_ERROR        err;
    CEmergentFrame   evtFrame;
    unsigned int     frames_recd = 0;
    uint32_t         npix = shm[0].md[0].size[0] * shm[0].md[0].size[1];

    struct timeval   t[2];
    gettimeofday(&t[0], NULL);

    daoInfo("ENTERING ACQUISITION LOOP\n");

    while (end == 0)
    {
        /* Allocate frame buffer (zero-copy) */
        evtFrame.size_x     = width_max;
        evtFrame.size_y     = height_max;
        evtFrame.pixel_type = GVSP_PIX_MONO12; /* Mono12 is stored in 16-bit container */

        err = EVT_AllocateFrameBuffer(&camera, &evtFrame, EVT_FRAME_BUFFER_ZERO_COPY);
        if (err)
        {
            daoError("EVT_AllocateFrameBuffer error %d\n", err);
            continue;
        }

        err = EVT_CameraQueueFrame(&camera, &evtFrame);
        if (err)
        {
            daoError("EVT_CameraQueueFrame error %d\n", err);
            EVT_ReleaseFrameBuffer(&camera, &evtFrame);
            continue;
        }

        /* 1000 ms timeout */
        err = EVT_CameraGetFrame(&camera, &evtFrame, 1000);
        if (err)
        {
            daoWarning("EVT_CameraGetFrame timeout/error %d\n", err);
            EVT_ReleaseFrameBuffer(&camera, &evtFrame);
            continue;
        }

        frames_recd++;

        /* Unpack and write to SHM */
        unpackMono12((const unsigned char *)evtFrame.imagePtr, npix, &shm[0]);

        EVT_ReleaseFrameBuffer(&camera, &evtFrame);

        /* Frame rate display */
        gettimeofday(&t[1], NULL);
        double elapsed = (t[1].tv_sec  - t[0].tv_sec)  * 1e6
                       + (t[1].tv_usec - t[0].tv_usec);
        if (elapsed >= 1e6)
        {
            printf("\r  Frame rate = %4u Hz   ", frames_recd);
            fflush(stdout);
            frames_recd = 0;
            t[0] = t[1];
        }
    }

    daoInfo("EXITING ACQUISITION LOOP\n");

    EVT_CameraExecuteCommand(&camera, "AcquisitionStop");
    EVT_CameraCloseStream(&camera);
    configure_defaults(&camera);
    EVT_CameraClose(&camera);
    daoInfo("Camera closed\n");

    return DAO_SUCCESS;
}

/*==========================================================================*/
/* Control thread: monitors SHM for FPS / DIT / Gain / Pos changes           */
void *camCtrlLoop(void *thread_data)
{
    (void)thread_data;
    daoInfo("camCtrlLoop: starting\n");

    IMAGE *ditShm  = (IMAGE *)malloc(sizeof(IMAGE));
    IMAGE *fpsShm  = (IMAGE *)malloc(sizeof(IMAGE));
    IMAGE *gainShm = (IMAGE *)malloc(sizeof(IMAGE));
    IMAGE *posShm  = (IMAGE *)malloc(sizeof(IMAGE));

    char ditShmFname[200];
    char fpsShmFname[200];
    char gainShmFname[200];
    char posShmFname[200];

    daoToolsInsertShmNamePrefix(shmName, "Dit",  ditShmFname);
    daoToolsInsertShmNamePrefix(shmName, "Fps",  fpsShmFname);
    daoToolsInsertShmNamePrefix(shmName, "Gain", gainShmFname);
    daoToolsInsertShmNamePrefix(shmName, "Pos",  posShmFname);

    uint32_t size[2];
    size[0] = 1; size[1] = 1;
    daoShmImageCreate(ditShm,  ditShmFname,  2, size, _DATATYPE_INT32, 1, 0);
    daoShmImageCreate(fpsShm,  fpsShmFname,  2, size, _DATATYPE_INT32, 1, 0);
    daoShmImageCreate(gainShm, gainShmFname, 2, size, _DATATYPE_INT32, 1, 0);
    size[0] = 2;
    daoShmImageCreate(posShm,  posShmFname,  2, size, _DATATYPE_INT32, 1, 0);

    unsigned long cnt0DIT  = ditShm[0].md[0].cnt0;
    unsigned long cnt0FPS  = fpsShm[0].md[0].cnt0;
    unsigned long cnt0GAIN = gainShm[0].md[0].cnt0;
    unsigned long cnt0POS  = posShm[0].md[0].cnt0;

    unsigned int v, vmin, vmax;

    daoInfo("ENTERING CONTROL LOOP\n");

    while (end == 0)
    {
        /* --- FPS --------------------------------------------------------- */
        if (cnt0FPS != fpsShm[0].md[0].cnt0)
        {
            cnt0FPS = fpsShm[0].md[0].cnt0;
            int fps = fpsShm[0].array.SI32[0];
            daoInfo("New FPS %d\n", fps);

            EVT_CameraExecuteCommand(&camera, "AcquisitionStop");

            EVT_CameraGetUInt32ParamMin(&camera, "FrameRate", &vmin);
            EVT_CameraGetUInt32ParamMax(&camera, "FrameRate", &vmax);
            if (fps >= (int)vmin && fps <= (int)vmax)
                EVT_CameraSetUInt32Param(&camera, "FrameRate", (unsigned int)fps);
            else
                daoWarning("FPS %d out of range [%u, %u]\n", fps, vmin, vmax);

            EVT_CameraGetUInt32Param(&camera, "FrameRate", &v);
            daoInfo("FrameRate is now %u\n", v);

            EVT_CameraExecuteCommand(&camera, "AcquisitionStart");
        }

        /* --- DIT (Exposure) ---------------------------------------------- */
        if (cnt0DIT != ditShm[0].md[0].cnt0)
        {
            cnt0DIT = ditShm[0].md[0].cnt0;
            int dit = ditShm[0].array.SI32[0];
            daoInfo("New DIT %d\n", dit);

            EVT_CameraExecuteCommand(&camera, "AcquisitionStop");

            EVT_CameraGetUInt32ParamMin(&camera, "Exposure", &vmin);
            EVT_CameraGetUInt32ParamMax(&camera, "Exposure", &vmax);
            if (dit >= (int)vmin && dit <= (int)vmax)
                EVT_CameraSetUInt32Param(&camera, "Exposure", (unsigned int)dit);
            else
                daoWarning("DIT %d out of range [%u, %u]\n", dit, vmin, vmax);

            EVT_CameraGetUInt32Param(&camera, "Exposure", &v);
            daoInfo("Exposure is now %u\n", v);

            EVT_CameraExecuteCommand(&camera, "AcquisitionStart");
        }

        /* --- Gain -------------------------------------------------------- */
        if (cnt0GAIN != gainShm[0].md[0].cnt0)
        {
            cnt0GAIN = gainShm[0].md[0].cnt0;
            int gain = gainShm[0].array.SI32[0];
            daoInfo("New Gain %d\n", gain);

            EVT_CameraExecuteCommand(&camera, "AcquisitionStop");

            EVT_CameraGetUInt32ParamMin(&camera, "Gain", &vmin);
            EVT_CameraGetUInt32ParamMax(&camera, "Gain", &vmax);
            if (gain >= (int)vmin && gain <= (int)vmax)
                EVT_CameraSetUInt32Param(&camera, "Gain", (unsigned int)gain);
            else
                daoWarning("Gain %d out of range [%u, %u]\n", gain, vmin, vmax);

            EVT_CameraGetUInt32Param(&camera, "Gain", &v);
            daoInfo("Gain is now %u\n", v);

            EVT_CameraExecuteCommand(&camera, "AcquisitionStart");
        }

        /* --- Position (OffsetX / OffsetY) -------------------------------- */
        if (cnt0POS != posShm[0].md[0].cnt0)
        {
            cnt0POS = posShm[0].md[0].cnt0;
            int posX = posShm[0].array.SI32[0];
            int posY = posShm[0].array.SI32[1];
            daoInfo("New POS %d, %d\n", posX, posY);

            EVT_CameraExecuteCommand(&camera, "AcquisitionStop");

            /* OffsetX */
            EVT_CameraGetUInt32ParamMin(&camera, "OffsetX", &vmin);
            EVT_CameraGetUInt32ParamMax(&camera, "OffsetX", &vmax);
            if (posX >= (int)vmin && posX <= (int)vmax)
                EVT_CameraSetUInt32Param(&camera, "OffsetX", (unsigned int)posX);
            else
                daoWarning("OffsetX %d out of range [%u, %u]\n", posX, vmin, vmax);

            /* OffsetY */
            EVT_CameraGetUInt32ParamMin(&camera, "OffsetY", &vmin);
            EVT_CameraGetUInt32ParamMax(&camera, "OffsetY", &vmax);
            if (posY >= (int)vmin && posY <= (int)vmax)
                EVT_CameraSetUInt32Param(&camera, "OffsetY", (unsigned int)posY);
            else
                daoWarning("OffsetY %d out of range [%u, %u]\n", posY, vmin, vmax);

            EVT_CameraGetUInt32Param(&camera, "OffsetX", &v);
            daoInfo("OffsetX is now %u\n", v);
            EVT_CameraGetUInt32Param(&camera, "OffsetY", &v);
            daoInfo("OffsetY is now %u\n", v);

            EVT_CameraExecuteCommand(&camera, "AcquisitionStart");
        }

        usleep(1000);
    }

    daoInfo("EXITING CONTROL LOOP\n");
    return DAO_SUCCESS;
}

/*==========================================================================*/
static int realTimeLoop(void)
{
    signal(SIGINT, endme);

    /* Open SHM */
    shm = (IMAGE *)malloc(sizeof(IMAGE));
    daoShmShm2Img(shmName, &shm[0]);

    int width  = shm[0].md[0].size[0];
    int height = shm[0].md[0].size[1];
    daoInfo("SHM size: %d x %d, atype=%d\n", width, height, shm[0].md[0].atype);

    /* Find cameras */
    struct GigEVisionDeviceInfo deviceInfo[MAX_CAMERAS];
    unsigned int count = MAX_CAMERAS;
    EVT_ListDevices(deviceInfo, &count, &count);
    if (count == 0)
    {
        daoError("No EVT cameras found\n");
        return DAO_ERROR;
    }
    daoInfo("Found %u camera(s)\n", count);

    /* Find camera by name or use first */
    int camIdx = -1;
    for (unsigned int i = 0; i < count; i++)
    {
        daoInfo("  [%u] %s  (%s)\n", i,
                deviceInfo[i].modelName,
                deviceInfo[i].serialNumber);
        if (strlen(cameraName) == 0 && camIdx < 0)
            camIdx = (int)i;
        if (strstr(deviceInfo[i].serialNumber, cameraName) ||
            strstr(deviceInfo[i].modelName,    cameraName))
            camIdx = (int)i;
    }
    if (camIdx < 0)
    {
        daoError("Camera '%s' not found\n", cameraName);
        return DAO_ERROR;
    }
    daoInfo("Using camera index %d: %s\n", camIdx, deviceInfo[camIdx].modelName);

    int ret = EVT_CameraOpen(&camera, &deviceInfo[camIdx]);
    /* Open camera */
    if (ret != EVT_SUCCESS)
    {
        daoError("EVT_CameraOpen failed, ret=%d\n", ret);
        return DAO_ERROR;
    }
    daoInfo("Camera opened\n");

    /* Apply defaults then configure for our use */
    configure_defaults(&camera);

    /* Set resolution to match SHM */
    EVT_CameraSetUInt32Param(&camera, "Width",  (unsigned int)width);
    EVT_CameraSetUInt32Param(&camera, "Height", (unsigned int)height);

    /* Store max resolution for frame buffer allocation */
    EVT_CameraGetUInt32ParamMax(&camera, "Width",  &width_max);
    EVT_CameraGetUInt32ParamMax(&camera, "Height", &height_max);

    /* Log current settings */
    unsigned int v;
    char strbuf[64];
    unsigned long strLen = 0;
    EVT_CameraGetEnumParam(&camera, "PixelFormat", strbuf, sizeof(strbuf), &strLen);    daoInfo("PixelFormat  = %s\n", strbuf);
    EVT_CameraGetUInt32Param(&camera, "Width",    &v); daoInfo("Width        = %u\n", v);
    EVT_CameraGetUInt32Param(&camera, "Height",   &v); daoInfo("Height       = %u\n", v);
    EVT_CameraGetUInt32Param(&camera, "Exposure", &v); daoInfo("Exposure     = %u\n", v);
    EVT_CameraGetUInt32Param(&camera, "FrameRate",&v); daoInfo("FrameRate    = %u\n", v);
    EVT_CameraGetUInt32Param(&camera, "Gain",     &v); daoInfo("Gain         = %u\n", v);
    EVT_CameraGetUInt32Param(&camera, "Offset",   &v); daoInfo("Offset       = %u\n", v);

    /* Open stream and start acquisition */
    EVT_CameraOpenStream(&camera);
    EVT_CameraExecuteCommand(&camera, "AcquisitionStart");
    daoInfo("Acquisition started\n");

    /* Launch threads */
    if (pthread_create(&camReaderThread, NULL, camRealTimeLoop, (void *)&threadIdCamReader) != 0)
    {
        daoError("Cannot create camera reader thread\n");
        return DAO_ERROR;
    }
    if (pthread_create(&camCtrlThread, NULL, camCtrlLoop, (void *)&threadIdCamCtrl) != 0)
    {
        daoError("Cannot create camera control thread\n");
        return DAO_ERROR;
    }

    pthread_join(camReaderThread, NULL);
    pthread_join(camCtrlThread,   NULL);

    return DAO_SUCCESS;
}

/*==========================================================================*/
static void DecodeArgs(int argc, char **argv)
{
    char *str;
    int   a1;

    argv++; argc--;

    while (argc-- > 0)
    {
        str = *argv++;
        if (str[0] != '-')
        {
            daoError("Unknown argument '%s'\n", str);
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
                argc--;
                break;
            case 'l':
                daoInfo("%s\n", *argv);
                argv++; argc--;
                break;
            case 'u':
                (void)sscanf(*argv++, "%d", &a1);
                argc--;
                usleep(a1);
                break;
            case 'S':
                (void)sscanf(*argv++, "%s", shmName);
                (void)sscanf(*argv++, "%[^\n]", cameraName);
                argc -= 2;
                daoInfo("shmName    = %s\n", shmName);
                daoInfo("cameraName = %s\n", cameraName);
                break;
            case 'L':
                realTimeLoop();
                break;
            default:
                daoError("Unknown argument '%s'\n", str);
                ShowHelp();
                exit(2);
        }
    }
}

/*==========================================================================*/
int main(int argc, char **argv)
{
    int               RT_priority = 93;
    struct sched_param schedpar;

    schedpar.sched_priority = RT_priority;
    sched_setscheduler(0, SCHED_FIFO, &schedpar);

    sArgv0 = *argv;
    DecodeArgs(argc, argv);

    return DAO_SUCCESS;
}
/*==========================================================================*/