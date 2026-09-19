/*****************************************************************************
  DAO project
  s.cetre
 *****************************************************************************/

/*==========================================================================*/

#define _GNU_SOURCE
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
#include <errno.h>
#include <sys/mman.h>
#include <sched.h>
#include <semaphore.h>
#include <sys/time.h>
#include <termios.h>
#include <netinet/in.h>//struct ip_mreq
#include <inttypes.h> 

#include <pthread.h>

#include "dao.h" 
#include "daoTools.h" 
#include "daoIportControl.h"


/* SDK Header */
#include <arv.h>

// termination flag
static int end     = 0;

// termination function for SIGINT callback
static void endme() 
{
    end = 1;
}

// ARV specific
// ArvStream *stream;
ArvDevice *device;
ArvGc *genicam;

// Add some constants for comands
const char* GigeFrameRateCommand = "AcquisitionFrameRate";
const char* GigeExposureCommand  = "ExposureTime";
const char* GigeOffsetXCommand  = "OffsetX";
const char* GigeOffsetYCommand  = "OffsetY";
const char* GigeGainCommand      = "Gain";
const char* GigePixelFormatCommand     = "PixelFormat";
const char* GigeCoolingEnableCommand   = "DeviceCoolingEnable";
const char* GigeCoolingSetpointCommand = "DeviceCoolingSetpoint";
const char* GigeAcqusitionStart  = "AcquisitionStart";
const char* GigeAcqusitionStop   = "AcquisitionStop";

// Re-reads every camera-controlled parameter and pushes the confirmed values
// into their SHMs via daoShmImage2Shm (write + Finalize: bumps cnt0 and posts
// semaphores), so any other process (the GUI included) is properly notified
// of the true current configuration -- not just the parameter that was
// directly changed, since e.g. a PixelFormat change can shift ExposureTime/
// AcquisitionFrameRate/Gain under the hood.
void refreshAllCameraParams(IMAGE *ditShm, IMAGE *fpsShm, IMAGE *gainShm,
                             IMAGE *pixelFormatShm, IMAGE *setTempShm, IMAGE *posShm)
{
    ArvGcNode *node;
    double v_double;
    float v_float;
    int v_int;
    const char *v_string;
    uint8_t v_uint8;
    uint32_t posArray[2];

    node = arv_gc_get_node(genicam, GigeExposureCommand);
    if (ARV_IS_GC_NODE(node))
    {
        v_double = arv_gc_float_get_value(ARV_GC_FLOAT(node), NULL);
        v_float = (float) v_double;
        daoShmImage2Shm(&v_float, 1, ditShm);
        daoInfo("refresh: exposure = %g\n", v_double);
    }

    node = arv_gc_get_node(genicam, GigeFrameRateCommand);
    if (ARV_IS_GC_NODE(node))
    {
        v_double = arv_gc_float_get_value(ARV_GC_FLOAT(node), NULL);
        v_float = (float) v_double;
        daoShmImage2Shm(&v_float, 1, fpsShm);
        daoInfo("refresh: fps = %g\n", v_double);
    }

    node = arv_gc_get_node(genicam, GigeGainCommand);
    if (ARV_IS_GC_NODE(node))
    {
        v_double = arv_gc_float_get_value(ARV_GC_FLOAT(node), NULL);
        v_float = (float) v_double;
        daoShmImage2Shm(&v_float, 1, gainShm);
        daoInfo("refresh: gain = %g\n", v_double);
    }

    node = arv_gc_get_node(genicam, GigePixelFormatCommand);
    if (ARV_IS_GC_NODE(node))
    {
        v_string = arv_gc_enumeration_get_string_value(ARV_GC_ENUMERATION(node), NULL);
        v_uint8 = (strcmp(v_string, "Mono14") == 0) ? 1 : 0;
        daoShmImage2Shm(&v_uint8, 1, pixelFormatShm);
        daoInfo("refresh: pixel format = %s\n", v_string);
    }

    node = arv_gc_get_node(genicam, GigeCoolingSetpointCommand);
    if (ARV_IS_GC_NODE(node))
    {
        v_double = arv_gc_float_get_value(ARV_GC_FLOAT(node), NULL);
        v_float = (float) v_double;
        daoShmImage2Shm(&v_float, 1, setTempShm);
        daoInfo("refresh: cooling setpoint = %g\n", v_double);
    }

    posArray[0] = posShm[0].array.UI32[0];
    posArray[1] = posShm[0].array.UI32[1];
    node = arv_gc_get_node(genicam, GigeOffsetXCommand);
    if (ARV_IS_GC_NODE(node))
    {
        v_int = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
        posArray[0] = (uint32_t) v_int;
    }
    node = arv_gc_get_node(genicam, GigeOffsetYCommand);
    if (ARV_IS_GC_NODE(node))
    {
        v_int = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
        posArray[1] = (uint32_t) v_int;
    }
    daoShmImage2Shm(posArray, 2, posShm);
    daoInfo("refresh: pos = %d,%d\n", posArray[0], posArray[1]);
}

void printHelp()
{
    daoError("Usage: daoHwStandaloneCtrl [options]\n");
    daoError("Options:\n");
    daoError("  --DeviceName, -d <name>         Set the device name\n");
    daoError("  --shmName, -f <file>            Set the share memory filename\n");
    daoError("  --receivePort, -R <port>        Set the receive port (default: 39433)\n");
    daoError("  --packetSize, -s <size>         Set the packet size (default: 8976)\n");
    daoError("  --help, -h                      Display this help message\n");
}


void parseArguments(int argc, char *argv[], char **deviceName, char **shmName, uint32_t *receivePort, uint32_t *packetSize)
{
    // Set default values
    *deviceName = NULL;
    *shmName = NULL;
    *receivePort = 39433;
    *packetSize = 8976;

    // Parse command-line arguments
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--help") == 0 || strcmp(argv[i], "-h") == 0) {
            printHelp();
            exit(0);
        } else if ((strcmp(argv[i], "--DeviceName") == 0 || strcmp(argv[i], "-d") == 0) && i + 1 < argc) {
            *deviceName = argv[++i];
        } else if ((strcmp(argv[i], "--shmName") == 0 || strcmp(argv[i], "-f") == 0) && i + 1 < argc) {
            *shmName = argv[++i];
        } else if ((strcmp(argv[i], "--receivePort") == 0 || strcmp(argv[i], "-r") == 0) && i + 1 < argc) {
            *receivePort = (uint32_t)atoi(argv[++i]);
        } else if ((strcmp(argv[i], "--packetSize") == 0 || strcmp(argv[i], "-s") == 0) && i + 1 < argc) {
            *packetSize = (uint32_t)atoi(argv[++i]);
        }
    }
}

int main(int argc, char *argv[])
{
    daoLogLevel=2;
    // register interrupt signal to terminate the main loop
    signal(SIGINT, endme);


    char *deviceName;
    char *shmName;
    uint32_t receivePort;
    uint32_t packetSize;

    parseArguments(argc, argv, &deviceName, &shmName, &receivePort, &packetSize);

    // Print the values to verify
    daoDebug("DeviceName: %s\n", deviceName ? deviceName : "NULL");
    daoDebug("shmName: %s\n", shmName ? shmName : "NULL");
    daoDebug("receivePort: %u\n", receivePort);
    daoDebug("packetSize: %u\n", packetSize);

    if(deviceName == NULL || shmName == NULL)
    {
        printHelp();
        exit(EXIT_FAILURE);
    }


    IMAGE * shm = (IMAGE*) malloc(sizeof(IMAGE));
    daoShmShm2Img(shmName, &shm[0]);
    daoInfo("Opening connection to CAM\n");

    // Init Camera
    GError *error = NULL;
    device = arv_open_device(deviceName, &error);
    ArvGcNode *node;

    if (device != NULL)
    {
        daoInfo("Device Created\n");
        guint32 value;
        guint32 maximum;
        double v_double;
        double v_double_min;
        double v_double_max;
        int v_int;
        int v_int_min;
        int v_int_max;
        const char *v_string;
        genicam = arv_device_get_genicam(device);

        node = arv_gc_get_node(genicam, "DeviceVendorName");
        v_string = arv_gc_string_get_value(ARV_GC_STRING(node), NULL);
        daoInfo("vendor        = %s\n", v_string);
        node = arv_gc_get_node(genicam, "DeviceModelName");
        v_string = arv_gc_string_get_value(ARV_GC_STRING(node), NULL);
        daoInfo("model         = %s\n", v_string);
        node = arv_gc_get_node(genicam, "DeviceID");
        v_string = arv_gc_string_get_value(ARV_GC_STRING(node), NULL);
        daoInfo("device id     = %s\n", v_string); 
        node = arv_gc_get_node(genicam, "SensorWidth");
        value = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
        daoInfo("sensor width  = %d\n", value);
        node = arv_gc_get_node(genicam, "SensorHeight");
        value = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
        daoInfo("sensor height = %d\n", value);
        node = arv_gc_get_node(genicam, "Width");
        //arv_gc_integer_set_value(ARV_GC_INTEGER(node), width, NULL);
        value = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
        maximum = arv_gc_integer_get_max(ARV_GC_INTEGER(node), NULL);
        daoInfo("image width   = %d (max:%d)\n", value, maximum);
        node = arv_gc_get_node(genicam, "Height");
        //arv_gc_integer_set_value(ARV_GC_INTEGER(node), height, NULL);
        value = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
        maximum = arv_gc_integer_get_max(ARV_GC_INTEGER(node), NULL);
        daoInfo("image height  = %d (max:%d)\n", value, maximum);

        // Values read here are used both for the startup log below and to
        // seed the control SHMs further down, so the GUI/clients see the
        // camera's real current settings instead of zeroed-out defaults.
        double initExposure = 0.0;
        double initFps = 0.0;
        double initGain = 0.0;
        double initSetTemp = 0.0;
        int initOffsetX = 0;
        int initOffsetY = 0;
        uint8_t initPixelFormat = 0; // 0 = Mono12, 1 = Mono14

        node = arv_gc_get_node(genicam, GigeExposureCommand);
        if (ARV_IS_GC_NODE(node))
        {
            v_double = arv_gc_float_get_value(ARV_GC_FLOAT(node), NULL);
            v_double_min = arv_gc_float_get_min(ARV_GC_FLOAT(node), NULL);
            v_double_max = arv_gc_float_get_max(ARV_GC_FLOAT(node), NULL);
            daoInfo("exposure       = %g (min:%g - max:%g)\n", v_double, v_double_min, v_double_max);
            initExposure = v_double;
        }

        node = arv_gc_get_node(genicam, GigeFrameRateCommand);
        if (ARV_IS_GC_NODE(node))
        {
            v_double = arv_gc_float_get_value(ARV_GC_FLOAT(node), NULL);
            v_double_min = arv_gc_float_get_min(ARV_GC_FLOAT(node), NULL);
            v_double_max = arv_gc_float_get_max(ARV_GC_FLOAT(node), NULL);
            daoInfo("fps            = %g (min:%g - max:%g)\n", v_double, v_double_min, v_double_max);
            initFps = v_double;
        }

        node = arv_gc_get_node(genicam, GigeGainCommand);
        if (ARV_IS_GC_NODE(node))
        {
            v_double = arv_gc_float_get_value(ARV_GC_FLOAT(node), NULL);
            v_double_min = arv_gc_float_get_min(ARV_GC_FLOAT(node), NULL);
            v_double_max = arv_gc_float_get_max(ARV_GC_FLOAT(node), NULL);
            daoInfo("gain           = %g (min:%g - max:%g)\n", v_double, v_double_min, v_double_max);
            initGain = v_double;
        }

        node = arv_gc_get_node(genicam, GigeOffsetXCommand);
        if (ARV_IS_GC_NODE(node))
        {
            initOffsetX = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
            daoInfo("offsetX        = %d\n", initOffsetX);
        }

        node = arv_gc_get_node(genicam, GigeOffsetYCommand);
        if (ARV_IS_GC_NODE(node))
        {
            initOffsetY = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
            daoInfo("offsetY        = %d\n", initOffsetY);
        }

        node = arv_gc_get_node(genicam, "PixelFormat");
        v_string = arv_gc_enumeration_get_string_value(ARV_GC_ENUMERATION(node), NULL);
        daoInfo("pixel format    = %s\n", v_string);
        value = arv_gc_enumeration_get_int_value(ARV_GC_ENUMERATION(node), NULL);
        daoInfo("pixel format  = %d (0x%x)\n", value, value);
        if (strcmp(v_string, "Mono14") == 0)
        {
            initPixelFormat = 1;
        }
        else if (strcmp(v_string, "Mono12") == 0)
        {
            initPixelFormat = 0;
        }
        else
        {
            daoWarning("Camera PixelFormat '%s' is neither Mono12 nor Mono14\n", v_string);
        }

        node = arv_gc_get_node(genicam, "DeviceTemperature");
        if (ARV_IS_GC_NODE(node))
        {
            v_double = arv_gc_float_get_value(ARV_GC_FLOAT(node), NULL);
            daoInfo("temperature    = %g C\n", v_double);
        }

        node = arv_gc_get_node(genicam, GigeCoolingSetpointCommand);
        if (ARV_IS_GC_NODE(node))
        {
            v_double = arv_gc_float_get_value(ARV_GC_FLOAT(node), NULL);
            v_double_min = arv_gc_float_get_min(ARV_GC_FLOAT(node), NULL);
            v_double_max = arv_gc_float_get_max(ARV_GC_FLOAT(node), NULL);
            daoInfo("cooling setpoint = %g C (min:%g - max:%g)\n", v_double, v_double_min, v_double_max);
            initSetTemp = v_double;
        }

        node = arv_gc_get_node(genicam, "PayloadSize");
        value = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
        daoInfo("payload size  = %d (0x%x)\n", value, value);

        daoInfo("Creating control SHM\n");
        IMAGE *acqShm = (IMAGE*) malloc(sizeof(IMAGE));
        IMAGE *ditShm = (IMAGE*) malloc(sizeof(IMAGE));
        IMAGE *fpsShm = (IMAGE*) malloc(sizeof(IMAGE));
        IMAGE *gainShm = (IMAGE*) malloc(sizeof(IMAGE));
        IMAGE *posShm = (IMAGE*) malloc(sizeof(IMAGE));
        IMAGE *pixelFormatShm = (IMAGE*) malloc(sizeof(IMAGE));
        IMAGE *setTempShm = (IMAGE*) malloc(sizeof(IMAGE));

        char acqShmFname[200];
        char ditShmFName[200];
        char fpsShmFName[200];
        char gainShmFName[200];
        char posShmFName[200];
        char pixelFormatShmFName[200];
        char setTempShmFName[200];
        daoToolsInsertShmNamePrefix(shmName, "Acq", acqShmFname);
        daoToolsInsertShmNamePrefix(shmName, "Dit", ditShmFName);
        daoToolsInsertShmNamePrefix(shmName, "Fps", fpsShmFName);
        daoToolsInsertShmNamePrefix(shmName, "Gain", gainShmFName);
        daoToolsInsertShmNamePrefix(shmName, "Pos", posShmFName);
        daoToolsInsertShmNamePrefix(shmName, "PixelFormat", pixelFormatShmFName);
        daoToolsInsertShmNamePrefix(shmName, "SetTemp", setTempShmFName);

        // Create size array, using 2D of 1x1... can be change to 1D
        uint32_t size[2];
        size[0] = 1;
        size[1] = 1;
        daoShmImageCreate(acqShm, acqShmFname, 2, size, _DATATYPE_UINT8, 1, 0);
        daoShmImageCreate(ditShm, ditShmFName, 2, size, _DATATYPE_FLOAT, 1, 0);
        daoShmImageCreate(fpsShm, fpsShmFName, 2, size, _DATATYPE_FLOAT, 1, 0);
        daoShmImageCreate(gainShm, gainShmFName, 2, size, _DATATYPE_FLOAT, 1, 0);
        daoShmImageCreate(pixelFormatShm, pixelFormatShmFName, 2, size, _DATATYPE_UINT8, 1, 0);
        daoShmImageCreate(setTempShm, setTempShmFName, 2, size, _DATATYPE_FLOAT, 1, 0);

        size[0] = 2;
        size[1] = 1;
        daoShmImageCreate(posShm, posShmFName, 2, size, _DATATYPE_UINT32, 1, 0);

        // Seed the control SHMs with the camera's actual current settings
        // (read above) so a freshly-started GUI/client reflects reality
        // instead of the zeroed-out defaults daoShmImageCreate() leaves.
        // Written directly into the array (not through a "set" that bumps
        // cnt0), so this does not trigger the apply-to-camera logic below.
        ditShm[0].array.F[0] = (float) initExposure;
        fpsShm[0].array.F[0] = (float) initFps;
        gainShm[0].array.F[0] = (float) initGain;
        pixelFormatShm[0].array.UI8[0] = initPixelFormat;
        setTempShm[0].array.F[0] = (float) initSetTemp;
        posShm[0].array.UI32[0] = (uint32_t) initOffsetX;
        posShm[0].array.UI32[1] = (uint32_t) initOffsetY;

        // get initial counter, will be used to check if there is a change
        unsigned long cnt0Acq = acqShm[0].md[0].cnt0;
        unsigned long cnt0DIT = ditShm[0].md[0].cnt0;
        unsigned long cnt0FPS = fpsShm[0].md[0].cnt0;
        unsigned long cnt0GAIN = gainShm[0].md[0].cnt0;
        unsigned long cnt0POS = posShm[0].md[0].cnt0;
        unsigned long cnt0PIXFMT = pixelFormatShm[0].md[0].cnt0;
        unsigned long cnt0SETTEMP = setTempShm[0].md[0].cnt0;

        configureStream(device, receivePort, packetSize, TRUE, FALSE, FALSE);
        // MAIN LOOP
        // if(acqShm[0].array.UI8[0] == 1)
        // {
        //     daoInfo("Starting Acquisition...\n");
        //     /* Start the acquisition */
        //     node = arv_gc_get_node(genicam, GigeAcqusitionStart);
        //     arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
        // }
        // else
        // {
        //     daoInfo("Entering Main loop without Acq started\n");
        // }
        daoInfo("ENTERING CONTROL LOOP\n");
        int paramsChanged;
        while (end==0)
        {
            paramsChanged = 0;
            if (cnt0Acq != acqShm[0].md[0].cnt0)
            {
                cnt0Acq = acqShm[0].md[0].cnt0;
                uint8_t acqMode = acqShm[0].array.UI8[0];
                daoInfo("Change in ACQ %" PRIu8 ", setting up camera\n", acqMode);
                if(acqMode == 0)
                {
                    node = arv_gc_get_node(genicam, GigeAcqusitionStop);
                    arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
                    daoInfo("Stopping Acquisition\n");
                }
                else
                {
                    node = arv_gc_get_node(genicam, GigeAcqusitionStart);
                    arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
                    daoInfo("Starting Acquisition\n");
                }
            }

            if (cnt0FPS != fpsShm[0].md[0].cnt0)
            {
                cnt0FPS = fpsShm[0].md[0].cnt0;
                daoInfo("New FPS %.3f, setting up camera\n", fpsShm[0].array.F[0]);

                if(acqShm[0].array.UI8[0] == 1)
                {
                    node = arv_gc_get_node(genicam, GigeAcqusitionStop);
                    arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
                }

                node = arv_gc_get_node(genicam, GigeFrameRateCommand);
                if (ARV_IS_GC_NODE(node))
                {
                    v_double = arv_gc_float_get_value(ARV_GC_FLOAT(node), NULL);
                    v_double_min = arv_gc_float_get_min(ARV_GC_FLOAT(node), NULL);
                    v_double_max = arv_gc_float_get_max(ARV_GC_FLOAT(node), NULL);
                    daoInfo("\nfps (%lf) was          = %g (min:%g - max:%g)\n", 
                            fpsShm[0].array.F[0], v_double, v_double_min, v_double_max);
                    if ((fpsShm[0].array.F[0] < v_double_min) && (fpsShm[0].array.F[0] > v_double_max))
                    {
                        daoWarning("\nCannot set fps, not in the range\n");   
                    }
                    else
                    {
                        arv_gc_float_set_value(ARV_GC_FLOAT(node), fpsShm[0].array.F[0], NULL);
                    }
                    v_double = arv_gc_float_get_value(ARV_GC_FLOAT(node), NULL);
                    daoInfo("fps (%lf) is now           = %g (min:%g - max:%g)\n",
                            fpsShm[0].array.F[0], v_double, v_double_min, v_double_max);
                }
                // restart aqusistion
                if(acqShm[0].array.UI8[0] == 1)
                {
                    node = arv_gc_get_node(genicam, GigeAcqusitionStart);
                    arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
                }
                paramsChanged = 1;
            }
            // If cnt of DIT SHM change, update DIT in aravis lib
            if (cnt0DIT != ditShm[0].md[0].cnt0)
            {
                cnt0DIT = ditShm[0].md[0].cnt0;
                daoInfo("New DIT %.3f, setting up camera\n", ditShm[0].array.F[0]);
                if(acqShm[0].array.UI8[0] == 1)
                {
                    node = arv_gc_get_node(genicam, GigeAcqusitionStop);
                    arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
                }
                node = arv_gc_get_node (genicam, GigeExposureCommand);
                if (ARV_IS_GC_NODE(node))
                {
                    v_double = arv_gc_float_get_value(ARV_GC_FLOAT(node), NULL);
                    v_double_min = arv_gc_float_get_min(ARV_GC_FLOAT(node), NULL);
                    v_double_max = arv_gc_float_get_max(ARV_GC_FLOAT(node), NULL);
                    daoInfo("\nexposure (%lf) was          = %g (min:%g - max:%g)\n", 
                            ditShm[0].array.F[0], v_double, v_double_min, v_double_max);
                    if ((ditShm[0].array.F[0] < v_double_min) && (ditShm[0].array.F[0] > v_double_max))
                    {
                        daoWarning("\nCannot set dit, not in the range\n");
                    }
                    else
                    {
                        arv_gc_float_set_value(ARV_GC_FLOAT(node), ditShm[0].array.F[0], NULL);
                    }
                    v_double = arv_gc_float_get_value(ARV_GC_FLOAT(node), NULL);
                    daoInfo("exposure (%lf) is now           = %g (min:%g - max:%g)\n",
                            ditShm[0].array.F[0], v_double, v_double_min, v_double_max);
                }
                // restart aqusistion
                if(acqShm[0].array.UI8[0] == 1)
                {
                    node = arv_gc_get_node(genicam, GigeAcqusitionStart);
                    arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
                }
                paramsChanged = 1;
            }
            // If cnt of GAIN SHM change, update GAIN in aravis lib
            if (cnt0GAIN != gainShm[0].md[0].cnt0)
            {
                cnt0GAIN = gainShm[0].md[0].cnt0;
                daoInfo("New GAIN %.3f, setting up camera\n", gainShm[0].array.F[0]);
                if(acqShm[0].array.UI8[0] == 1)
                {
                    node = arv_gc_get_node(genicam, GigeAcqusitionStop);
                    arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
                }
                node = arv_gc_get_node(genicam, GigeGainCommand);
                if (ARV_IS_GC_NODE(node))
                {
                    v_double = arv_gc_float_get_value(ARV_GC_FLOAT(node), NULL);
                    v_double_min = arv_gc_float_get_min(ARV_GC_FLOAT(node), NULL);
                    v_double_max = arv_gc_float_get_max(ARV_GC_FLOAT(node), NULL);
                    daoInfo("\ngain (%lf) was          = %g (min:%g - max:%g)\n",
                            gainShm[0].array.F[0], v_double, v_double_min, v_double_max);
                    if ((gainShm[0].array.F[0] < v_double_min) || (gainShm[0].array.F[0] > v_double_max))
                    {
                        daoWarning("\nCannot set gain, not in the range\n");
                    }
                    else
                    {
                        arv_gc_float_set_value(ARV_GC_FLOAT(node), gainShm[0].array.F[0], NULL);
                    }
                    v_double = arv_gc_float_get_value(ARV_GC_FLOAT(node), NULL);
                    daoInfo("gain (%lf) is now           = %g (min:%g - max:%g)\n",
                            gainShm[0].array.F[0], v_double, v_double_min, v_double_max);
                }
                if(acqShm[0].array.UI8[0] == 1)
                {
                    node = arv_gc_get_node(genicam, GigeAcqusitionStart);
                    arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
                }
                paramsChanged = 1;
            }
            // If cnt of PIXELFORMAT SHM change, update PixelFormat in aravis lib
            if (cnt0PIXFMT != pixelFormatShm[0].md[0].cnt0)
            {
                cnt0PIXFMT = pixelFormatShm[0].md[0].cnt0;
                const char *pixFmtStr = (pixelFormatShm[0].array.UI8[0] == 1) ? "Mono14" : "Mono12";
                daoInfo("New PixelFormat %s, setting up camera\n", pixFmtStr);
                if(acqShm[0].array.UI8[0] == 1)
                {
                    node = arv_gc_get_node(genicam, GigeAcqusitionStop);
                    arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
                }
                node = arv_gc_get_node(genicam, GigePixelFormatCommand);
                if (ARV_IS_GC_NODE(node))
                {
                    arv_gc_enumeration_set_string_value(ARV_GC_ENUMERATION(node), pixFmtStr, NULL);
                    v_string = arv_gc_enumeration_get_string_value(ARV_GC_ENUMERATION(node), NULL);
                    daoInfo("pixel format is now = %s\n", v_string);
                }
                if(acqShm[0].array.UI8[0] == 1)
                {
                    node = arv_gc_get_node(genicam, GigeAcqusitionStart);
                    arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
                }
                // Changing bit depth can shift the camera's readout timing,
                // which clamps/rescales ExposureTime, AcquisitionFrameRate
                // and Gain under the hood -- the paramsChanged refresh below
                // re-reads all of them so the GUI reflects reality.
                paramsChanged = 1;
            }
            // If cnt of SETTEMP SHM change, update the cooling setpoint in aravis lib
            // (DeviceTemperature itself is read-only telemetry; the way to control
            // it is via DeviceCoolingEnable + DeviceCoolingSetpoint)
            if (cnt0SETTEMP != setTempShm[0].md[0].cnt0)
            {
                cnt0SETTEMP = setTempShm[0].md[0].cnt0;
                daoInfo("New SetTemp %.3f, setting up camera\n", setTempShm[0].array.F[0]);
                node = arv_gc_get_node(genicam, GigeCoolingEnableCommand);
                if (ARV_IS_GC_NODE(node))
                {
                    arv_gc_boolean_set_value(ARV_GC_BOOLEAN(node), TRUE, NULL);
                }
                node = arv_gc_get_node(genicam, GigeCoolingSetpointCommand);
                if (ARV_IS_GC_NODE(node))
                {
                    v_double = arv_gc_float_get_value(ARV_GC_FLOAT(node), NULL);
                    v_double_min = arv_gc_float_get_min(ARV_GC_FLOAT(node), NULL);
                    v_double_max = arv_gc_float_get_max(ARV_GC_FLOAT(node), NULL);
                    daoInfo("\ncooling setpoint (%lf) was          = %g (min:%g - max:%g)\n",
                            setTempShm[0].array.F[0], v_double, v_double_min, v_double_max);
                    if ((setTempShm[0].array.F[0] < v_double_min) || (setTempShm[0].array.F[0] > v_double_max))
                    {
                        daoWarning("\nCannot set cooling setpoint, not in the range\n");
                    }
                    else
                    {
                        arv_gc_float_set_value(ARV_GC_FLOAT(node), setTempShm[0].array.F[0], NULL);
                    }
                    v_double = arv_gc_float_get_value(ARV_GC_FLOAT(node), NULL);
                    daoInfo("cooling setpoint (%lf) is now           = %g (min:%g - max:%g)\n",
                            setTempShm[0].array.F[0], v_double, v_double_min, v_double_max);
                }
                paramsChanged = 1;
            }
            // If cnt of POS SHM change, update POS in aravis lib
            if (cnt0POS != posShm[0].md[0].cnt0)
            {
                cnt0POS = posShm[0].md[0].cnt0;
                daoInfo("New POS %d,%d , setting up camera\n", posShm[0].array.UI32[0], posShm[0].array.UI32[0]);
                if(acqShm[0].array.UI8[0] == 1)
                {
                    node = arv_gc_get_node(genicam, GigeAcqusitionStop);
                    arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
                }
                node = arv_gc_get_node (genicam, GigeOffsetXCommand);
                if (ARV_IS_GC_NODE(node))
                {
                    v_int = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
                    v_int_min = arv_gc_integer_get_min(ARV_GC_INTEGER(node), NULL);
                    v_int_max = arv_gc_integer_get_max(ARV_GC_INTEGER(node), NULL);
                    daoInfo("\nOffsetX (%d) was          = %d (min:%d - max:%d)\n", 
                            posShm[0].array.UI32[0], v_int, v_int_min, v_int_max);
                    if (((int)posShm[0].array.UI32[0] < v_int_min) && ((int)posShm[0].array.UI32[0] > v_int_max))
                    {
                        daoWarning("\nCannot set offsetX, not in the range\n");
                    }
                    else
                    {
                        arv_gc_integer_set_value(ARV_GC_INTEGER(node), posShm[0].array.UI32[0], NULL);
                    }
                    v_int = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
                    daoInfo("offsetX (%d) is now           = %d (min:%d - max:%d)\n",
                            posShm[0].array.UI32[0], v_int, v_int_min, v_int_max);
                }
                node = arv_gc_get_node (genicam, GigeOffsetYCommand);
                if (ARV_IS_GC_NODE(node))
                {
                    v_int = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
                    v_int_min = arv_gc_integer_get_min(ARV_GC_INTEGER(node), NULL);
                    v_int_max = arv_gc_integer_get_max(ARV_GC_INTEGER(node), NULL);
                    daoInfo("\nOffsetY (%d) was          = %d (min:%d - max:%d)\n", 
                            posShm[0].array.UI32[1], v_int, v_int_min, v_int_max);
                    if (((int)posShm[0].array.UI32[0] < v_int_min) && ((int)posShm[0].array.UI32[1] > v_int_max))
                    {
                        daoWarning("\nCannot set offsetY, not in the range\n");
                    }
                    else
                    {
                        arv_gc_integer_set_value(ARV_GC_INTEGER(node), posShm[0].array.UI32[1], NULL);
                    }
                    v_int = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
                    daoInfo("offsetX (%d) is now           = %d (min:%d - max:%d)\n",
                            posShm[0].array.UI32[1], v_int, v_int_min, v_int_max);
                }
                // restart aqusistion
                if(acqShm[0].array.UI8[0] == 1)
                {
                    node = arv_gc_get_node(genicam, GigeAcqusitionStart);
                    arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
                }
                paramsChanged = 1;
            }

            if (paramsChanged)
            {
                refreshAllCameraParams(ditShm, fpsShm, gainShm, pixelFormatShm, setTempShm, posShm);
                // Re-sync our own change-tracking counters to the values
                // Finalize just bumped, so this refresh doesn't re-trigger
                // itself on the next loop iteration.
                cnt0DIT = ditShm[0].md[0].cnt0;
                cnt0FPS = fpsShm[0].md[0].cnt0;
                cnt0GAIN = gainShm[0].md[0].cnt0;
                cnt0PIXFMT = pixelFormatShm[0].md[0].cnt0;
                cnt0SETTEMP = setTempShm[0].md[0].cnt0;
                cnt0POS = posShm[0].md[0].cnt0;
            }
            usleep(100);// pause
        }

        daoInfo("Stopping Acquisition\n");
        node = arv_gc_get_node(genicam, GigeAcqusitionStop);
        arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);

        daoInfo("EXITING MAIN LOOP\n");
        daoInfo("EXITING CONTROL LOOP\n");
    }
    else
    {
        daoError("Could not connect to device\n");
        if (error != NULL)
        {
            // Print the error message
            g_print("Error: %s\n", error->message);

            // Free the error
            g_error_free(error);
        }
        exit(EXIT_FAILURE);
    }

    // add any cleanup required.

    return 0;
}