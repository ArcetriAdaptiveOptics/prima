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

// KRTC header
#include "dao.h" 
#include "daoTools.h" 
#include "daoIportControl.h"


/* SDK Header */
#include <arv.h>

// // TODO: hardcoded for now, need a better solution in the future (especally IP)
// guint32 mc_port         = 49495;
// guint32 mc_timeout      = 400;
// guint32 mc_retry_count  = 3;

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
const char* GigeFrameRateCommand = "AcquisitionFrameRateAbs";
const char* GigeExposureCommand  = "ExposureTimeAbs";
const char* GigeGainCommand      = "Gain";

char cameraName[] = "Allied Vision Technologies-GT1920 (02-2610A)-02-2610A-07672";
char shmName[] = "/tmp/avt.im.shm";
guint32 port = 39433;

int main()
{
    daoLogLevel=2;
    // register interrupt signal to terminate the main loop
    signal(SIGINT, endme);

    IMAGE * shm = (IMAGE*) malloc(sizeof(IMAGE));
    daoShmShm2Img(shmName, &shm[0]);
    // inverted height/width
    // int width = shm[0].md[0].size[1];
    // int height = shm[0].md[0].size[0];
    // clock_t launch, done;
    daoInfo("Opening connection to CAM\n");
    // launch=clock();


    // Init Camera
    GError *error = NULL;
    device = arv_open_device(cameraName, &error);
    ArvGcNode *node;
    // If master = 1. either multicast controller of simple client
    if (device != NULL)
    {
        daoInfo("Device Created\n");
        guint32 value;
        guint32 maximum;
        double v_double;
        double v_double_min;
        double v_double_max;
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
        //node = arv_gc_get_node(genicam, "SensorWidth");
        //value = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
        //daoInfo("sensor width  = %d\n", value);
        //node = arv_gc_get_node(genicam, "SensorHeight");
        //value = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
        //daoInfo("sensor height = %d\n", value);
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

        char acqShmFname[200];
        daoToolsInsertShmNamePrefix(shmName, "Acq", acqShmFname);

        // Create size array, using 2D of 1x1... can be change to 1D
        uint32_t size[2];
        size[0] = 1;
        size[1] = 1;
        daoShmImageCreate(acqShm, acqShmFname, 2, size, _DATATYPE_UINT8, 1, 0);      
        // get initial counter, will be used to check if there is a change 
        unsigned long cnt0Acq = acqShm[0].md[0].cnt0;

        configureStream(device, port, 8976, TRUE, FALSE,FALSE);
        // MAIN LOOP
        if(acqShm[0].array.UI8[0] == 1)
        {
            daoInfo("Starting Acquisition...\n");
            /* Start the acquisition */
            node = arv_gc_get_node(genicam, "AcquisitionStart");
            arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
        }
        else
        {
            daoInfo("Entering Main loop without Acq started\n");
        }
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
                    node = arv_gc_get_node(genicam, "AcquisitionStop");
                    arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
                    daoInfo("Stopping Acquisition\n");
                }
                else
                {
                    node = arv_gc_get_node(genicam, "AcquisitionStart");
                    arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
                    daoInfo("Starting Acquisition\n");
                }
            }
            usleep(100);// pause 
        }

        daoInfo("Stopping Acquisition\n");
        node = arv_gc_get_node(genicam, "AcquisitionStop");
        arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);

        daoInfo("EXITING MAIN LOOP\n");
        daoInfo("EXITING CONTROL LOOP\n");
    }

    return 0;
}