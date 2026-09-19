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
const char* GigeFrameRateCommand = "FrameRate";
const char* GigeExposureCommand  = "ExposureTime";
const char* GigeOffsetXCommand  = "OffsetX";
const char* GigeOffsetYCommand  = "OffsetY";
const char* GigeGainCommand      = "Gain";
const char* GigeAcqusitionStart  = "AcquisitionStart";
const char* GigeAcqusitionStop   = "AcquisitionStop";

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

        node = arv_gc_get_node(genicam, GigeExposureCommand);
        if (ARV_IS_GC_NODE(node))
        {
            v_double = arv_gc_float_get_value(ARV_GC_FLOAT(node), NULL);
            v_double_min = arv_gc_float_get_min(ARV_GC_FLOAT(node), NULL);
            v_double_max = arv_gc_float_get_max(ARV_GC_FLOAT(node), NULL);
            daoInfo("exposure       = %g (min:%g - max:%g)\n", v_double, v_double_min, v_double_max);
        }

        node = arv_gc_get_node(genicam, "PixelFormat");
        v_string = arv_gc_enumeration_get_string_value(ARV_GC_ENUMERATION(node), NULL);
        daoInfo("pixel format    = %s\n", v_string);
        value = arv_gc_enumeration_get_int_value(ARV_GC_ENUMERATION(node), NULL);
        daoInfo("pixel format  = %d (0x%x)\n", value, value);

        node = arv_gc_get_node(genicam, "PayloadSize");
        value = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
        daoInfo("payload size  = %d (0x%x)\n", value, value);

        daoInfo("Creating control SHM\n");
        IMAGE *acqShm = (IMAGE*) malloc(sizeof(IMAGE));
        IMAGE *ditShm = (IMAGE*) malloc(sizeof(IMAGE));
        IMAGE *fpsShm = (IMAGE*) malloc(sizeof(IMAGE));
        IMAGE *gainShm = (IMAGE*) malloc(sizeof(IMAGE));
        IMAGE *posShm = (IMAGE*) malloc(sizeof(IMAGE));

        char acqShmFname[200];
        char ditShmFName[200]; 
        char fpsShmFName[200]; 
        char gainShmFName[200]; 
        char posShmFName[200]; 
        daoToolsInsertShmNamePrefix(shmName, "Acq", acqShmFname);
        daoToolsInsertShmNamePrefix(shmName, "Dit", ditShmFName);
        daoToolsInsertShmNamePrefix(shmName, "Fps", fpsShmFName);
        daoToolsInsertShmNamePrefix(shmName, "Gain", gainShmFName);
        daoToolsInsertShmNamePrefix(shmName, "Pos", posShmFName);

        // Create size array, using 2D of 1x1... can be change to 1D
        uint32_t size[2];
        size[0] = 1;
        size[1] = 1;
        daoShmImageCreate(acqShm, acqShmFname, 2, size, _DATATYPE_UINT8, 1, 0); 
        daoShmImageCreate(ditShm, ditShmFName, 2, size, _DATATYPE_FLOAT, 1, 0);
        daoShmImageCreate(fpsShm, fpsShmFName, 2, size, _DATATYPE_FLOAT, 1, 0);
        daoShmImageCreate(gainShm, gainShmFName, 2, size, _DATATYPE_FLOAT, 1, 0);   

        size[0] = 2;
        size[1] = 1;
        daoShmImageCreate(posShm, posShmFName, 2, size, _DATATYPE_UINT32, 1, 0);  

        // get initial counter, will be used to check if there is a change 
        unsigned long cnt0Acq = acqShm[0].md[0].cnt0;
        unsigned long cnt0DIT = ditShm[0].md[0].cnt0;
        unsigned long cnt0FPS = fpsShm[0].md[0].cnt0;
        unsigned long cnt0GAIN = gainShm[0].md[0].cnt0;
        unsigned long cnt0POS = posShm[0].md[0].cnt0;

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
        while (end==0)
        {
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
            }
            // If cnt of GAIN SHM change, update GAIN in aravis lib
            if (cnt0GAIN != gainShm[0].md[0].cnt0)
            {
                cnt0GAIN = gainShm[0].md[0].cnt0;
                daoInfo("New GAIN %.3f, setting up camera\n", gainShm[0].array.F[0]);
            //    arv_camera_set_gain(camera, gainShm[0].array.F[0], NULL);
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