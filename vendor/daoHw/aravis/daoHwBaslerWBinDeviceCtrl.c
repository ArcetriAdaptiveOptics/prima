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
#include <errno.h>
#include <sys/mman.h>
#include <sched.h>
#include <semaphore.h>
#include <sys/time.h>
#include <termios.h>
#include <netinet/in.h>//struct ip_mreq

#include <pthread.h>

// KRTC header
#include "dao.h" 
#include "daoTools.h" 

/* SDK Header */
#include <arv.h>

typedef struct _ArvGvStreamThreadData ArvGvStreamThreadData;

typedef struct {
	GThread *thread;
	ArvGvStreamThreadData *thread_data;
} ArvGvStreamPrivate;

#define ARV_GVBS_STREAM_CHANNEL_0_IP_ADDRESS_OFFSET 0x00000d18

typedef int bool_t;
#ifndef TRUE
#define TRUE	1
#endif
#ifndef FALSE
#define FALSE	0
#endif

#define NBUF 50

/*==========================================================================*/

//Need to install process with setuid.  Then, so you aren't running privileged all the time do this:
uid_t euid_real;
uid_t euid_called;
uid_t suid;


struct timespec tnow;
double tlastupdatedouble;

IMAGE *shm;
char shmName[32];
char cameraName[32];

// Thread
pthread_t camReaderThread;
int threadIdCamReader = 0;
pthread_t camCtrlThread;
int threadIdCamCtrl = 0;


// termination flag
static int end     = 0;

// termination function for SIGINT callback
static void endme() 
{
    end = 1;
}

static char	*sArgv0=NULL;					/* name of executable */

// ARV specific
ArvStream *stream;
ArvDevice *device;
ArvGc *genicam;

static void ShowHelp(void)
{
    printf("%s of " __DATE__ " at " __TIME__ "\n",sArgv0);
    printf("   arguments:\n");
    printf("   -h               display this message and exit\n");
    printf("   -d               display program debug output\n");
    printf("   -l str           display str in output\n");
    /*
     **	Post init tests
     */
    printf("   -L shm  multicastMaster multicastAddr serial\n");
    printf(" .                  example: daoHwBaslerDeviceCtrl -L wfsImage  \"XXX\"\n");
    /*
     **	Timing tests
     */
    printf("   -t nloops        test timing for i/o\n");
    printf("\n");
}

void * camCtrlLoop(void *thread_data)
{
    daoInfo("ThreadId=%p\n", thread_data);
    daoInfo("Creating control SHM\n");
    IMAGE *ditShm = (IMAGE*) malloc(sizeof(IMAGE));
    IMAGE *fpsShm = (IMAGE*) malloc(sizeof(IMAGE));
    IMAGE *gainShm = (IMAGE*) malloc(sizeof(IMAGE));
    IMAGE *posShm = (IMAGE*) malloc(sizeof(IMAGE));
    //IMAGE *binShm = (IMAGE*) malloc(sizeof(IMAGE));
    char ditShmFName[200]; 
    char fpsShmFName[200]; 
    char gainShmFName[200]; 
    char posShmFName[200]; 

    daoToolsInsertShmNamePrefix(shmName, "Dit", ditShmFName);
    daoToolsInsertShmNamePrefix(shmName, "Fps", fpsShmFName);
    daoToolsInsertShmNamePrefix(shmName, "Gain", gainShmFName);
    daoToolsInsertShmNamePrefix(shmName, "Pos", posShmFName);

    // Create size array, using 2D of 1x1... can be change to 1D
    uint32_t size[2];
    size[0] = 1;
    size[1] = 1;
    // Create SHM
    daoShmImageCreate(ditShm, ditShmFName, 2, size, _DATATYPE_FLOAT, 1, 0);
    daoShmImageCreate(fpsShm, fpsShmFName, 2, size, _DATATYPE_FLOAT, 1, 0);
    daoShmImageCreate(gainShm, gainShmFName, 2, size, _DATATYPE_FLOAT, 1, 0);
    size[0] = 2;
    size[1] = 1;
    daoShmImageCreate(posShm, posShmFName, 2, size, _DATATYPE_UINT32, 1, 0);

    // get initial counter, will be used to check if there is a change 
    unsigned long cnt0DIT = ditShm[0].md[0].cnt0;
    unsigned long cnt0FPS = fpsShm[0].md[0].cnt0;
    unsigned long cnt0GAIN = gainShm[0].md[0].cnt0;
    unsigned long cnt0POS = posShm[0].md[0].cnt0;

    // Node pointer to control
    ArvGcNode *node;

    double v_double;
    double v_double_min;
    double v_double_max;
    int v_int;
    int v_int_max;
    //unsigned long cnt0BIN = binShm[0].md[0].cnt0;
    // MAIN LOOP
    daoInfo("ENTERING CONTROL LOOP\n");
    while (end==0) 
    {
        // If cnt of FPS SHM change, update FPS in aravis lib
        if (cnt0FPS != fpsShm[0].md[0].cnt0)
        {
            cnt0FPS = fpsShm[0].md[0].cnt0;
            daoInfo("New FPS %.3f, setting up camera\n", fpsShm[0].array.F[0]);
            node = arv_gc_get_node(genicam, "AcquisitionStop");
            arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
            node = arv_gc_get_node(genicam, "AcquisitionFrameRateEnable");
            arv_gc_boolean_set_value(ARV_GC_BOOLEAN(node), TRUE, NULL);
            node = arv_gc_get_node(genicam, "AcquisitionFrameRate");
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

            node = arv_gc_get_node(genicam, "AcquisitionStart");
            arv_gc_command_execute(ARV_GC_COMMAND(node), NULL); 

        }
        // If cnt of DIT SHM change, update DIT in aravis lib
        if (cnt0DIT != ditShm[0].md[0].cnt0)
        {
            cnt0DIT = ditShm[0].md[0].cnt0;
            daoInfo("New DIT %.3f, setting up camera\n", ditShm[0].array.F[0]);
            node = arv_gc_get_node(genicam, "AcquisitionStop");
            arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
            node = arv_gc_get_node (genicam, "ExposureTime");
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
            node = arv_gc_get_node(genicam, "AcquisitionStart");
            arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
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
            daoInfo("New POS (%d,%d), setting up camera\n", posShm[0].array.UI32[0], posShm[0].array.UI32[1]);
            node = arv_gc_get_node(genicam, "AcquisitionStop");
            arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
            if (ARV_IS_GC_NODE(node))
            {
                node = arv_gc_get_node(genicam, "OffsetX");
                arv_gc_integer_set_value(ARV_GC_INTEGER(node), posShm[0].array.UI32[0], NULL);
                v_int = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
                v_int_max = arv_gc_integer_get_max(ARV_GC_INTEGER(node), NULL);
                daoInfo("offset x   = %d (max:%d, wanted:%d)\n", v_int, v_int_max, posShm[0].array.UI32[0]);
                node = arv_gc_get_node(genicam, "OffsetY");
                arv_gc_integer_set_value(ARV_GC_INTEGER(node), posShm[0].array.UI32[1], NULL);
                v_int = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
                v_int_max = arv_gc_integer_get_max(ARV_GC_INTEGER(node), NULL);
                daoInfo("offset y   = %d (max:%d, wanted:%d)\n", v_int, v_int_max, posShm[0].array.UI32[1]); 
            }
            node = arv_gc_get_node(genicam, "AcquisitionStart");
            arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
        }
        //usleep(1000000);// pause 
    }
    daoInfo("EXITING CONTROL LOOP\n");

    return DAO_SUCCESS;
}

/*--------------------------------------------------------------------------*/
void  * camRealTimeLoop(void *thread_data)
{
    daoInfo("ThreadId=%p\n", thread_data);


    // MAIN LOOP
    // Acquiring pixels and putting them in the SHM
    daoInfo("ENTERING LOOP\n");
    ArvGcNode *node;
    guint64 n_processed_buffers;
    guint64 n_failures;
    guint64 n_underruns;
    ArvBuffer *buffer;
	unsigned buffer_count = 0;
	guint64 start_time, time;
    start_time = g_get_real_time();
    gint nIn, nOut;
    long long sysTimestamp = 0;
    long long sysTimestamp0 = 0;
    long long camTimestamp = 0;
    long long camTimestamp0 = 0;
    const short int *data; 
    daoInfo("Starting Acquisition...\n");
    /* Start the acquisition */
    node = arv_gc_get_node(genicam, "AcquisitionStart");
    arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
    // Get Buffer original config
    arv_stream_get_n_buffers(stream, &nIn, &nOut);
    printf("nInInit=%d, nOutInit=%d, \n", nIn, nOut);
    gint n_input_buffers, n_output_buffers;
    do
    {
        data = NULL;
//        buffer = arv_stream_pop_buffer(stream);
        buffer = arv_stream_try_pop_buffer(stream);  // non-blocking

        arv_stream_get_n_buffers(stream, &n_input_buffers, &n_output_buffers);
        if (buffer)
        {
            printf("\r");
            printf("buffer: %d/%d", n_input_buffers, n_output_buffers);
            size_t sz;
            data = arv_buffer_get_data(buffer, &sz);
            camTimestamp0=camTimestamp;
            sysTimestamp0=sysTimestamp;
            camTimestamp = arv_buffer_get_timestamp(buffer);
            sysTimestamp = arv_buffer_get_system_timestamp(buffer);
            printf("cnt = %04d, sz=%08ld, ts=%17lld, delta=%8lld, systs=%17lld, deltasysts=%10lld ",
                   buffer_count, sz, camTimestamp, camTimestamp-camTimestamp0, 
                   sysTimestamp, sysTimestamp-sysTimestamp0);
            arv_stream_push_buffer(stream, buffer);
            buffer_count++;
            if (data)
            {
                if (sz != 0)
                {
                    daoShmImage2Shm((unsigned short *)data,
                                    //sz,
                                    shm[0].md[0].size[0] * shm[0].md[0].size[1],
                                    &shm[0]);
                }
            }
            time = g_get_real_time();
            if (time - start_time > 1000000)
            {
                printf(" Frame rate = %4d Hz", buffer_count);
                buffer_count = 0;
                start_time = time;
            }
            fflush(stdout);
        }
        if (buffer == NULL)
        {
            usleep(1);
            //printf("NULL buffer\n");
        }
    } while (!end);

    arv_stream_get_statistics(stream, &n_processed_buffers, &n_failures, &n_underruns);

    daoInfo("Processed buffers = %llu\n", (unsigned long long)n_processed_buffers);
    daoInfo("Failures          = %llu\n", (unsigned long long)n_failures);
    daoInfo("Underruns         = %llu\n", (unsigned long long)n_underruns);

    node = arv_gc_get_node(genicam, "AcquisitionStop");
    arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);

    g_object_unref(stream);
    g_object_unref(device);

    daoInfo("EXITING MAIN LOOP\n");
    fflush(stdout);
    return DAO_SUCCESS;
}
    
/*--------------------------------------------------------------------------*/
static int realTimeLoop()
{
    int status;
    // register interrupt signal to terminate the main loop
    signal(SIGINT, endme);

    shm = (IMAGE*) malloc(sizeof(IMAGE));
    daoShmShm2Img(shmName, &shm[0]);
    
    IMAGE *binShm = (IMAGE*) malloc(sizeof(IMAGE));
    char binShmFName[200]; 
    daoToolsInsertShmNamePrefix(shmName, "Bin", binShmFName);
    daoShmShm2Img(binShmFName, &binShm[0]);
    int binning = binShm[0].array.UI32[0];
    daoInfo("Setting for binning=%d\n", binning);
    
    // inverted height/width
    int width = shm[0].md[0].size[1];
    int height = shm[0].md[0].size[0];
    clock_t launch, done;
    double diff;
    daoInfo("Opening connection to CAM\n");
    launch=clock();

    // Init Camera
    GError *error = NULL;
    static gboolean arv_option_auto_buffer = FALSE;
    device = arv_open_device(cameraName, &error);
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
        int i;

        ArvGcNode *node;
        genicam = arv_device_get_genicam(device);


        node = arv_gc_get_node(genicam, "AcquisitionStop");
        arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);

        node = arv_gc_get_node(genicam, "DeviceVendorName");
        v_string = arv_gc_string_get_value(ARV_GC_STRING(node), NULL);
        daoInfo("vendor        = %s\n", v_string);
        node = arv_gc_get_node(genicam, "DeviceModelName");
        v_string = arv_gc_string_get_value(ARV_GC_STRING(node), NULL);
        daoInfo("model         = %s\n", v_string);
        node = arv_gc_get_node(genicam, "DeviceID");
        v_string = arv_gc_string_get_value(ARV_GC_STRING(node), NULL);
        daoInfo("device id     = %s\n", v_string);

        node = arv_gc_get_node(genicam, "OffsetX");
        arv_gc_integer_set_value(ARV_GC_INTEGER(node), 0, NULL);
        value = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
        maximum = arv_gc_integer_get_max(ARV_GC_INTEGER(node), NULL);
        daoInfo("offset x   = %d (max:%d, wanted:%d)\n", value, maximum, 0);
        
        node = arv_gc_get_node(genicam, "OffsetY");
        arv_gc_integer_set_value(ARV_GC_INTEGER(node), 0, NULL);
        value = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
        maximum = arv_gc_integer_get_max(ARV_GC_INTEGER(node), NULL);
        daoInfo("offset y   = %d (max:%d, wanted:%d)\n", value, maximum, 0); 
        node = arv_gc_get_node(genicam, "BinningHorizontal");
        arv_gc_integer_set_value(ARV_GC_INTEGER(node), binning, NULL);
        value = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
        maximum = arv_gc_integer_get_max(ARV_GC_INTEGER(node), NULL);
        daoInfo("BinningHorizontal x   = %d (max:%d, wanted:%d)\n", value, maximum, binning);

        node = arv_gc_get_node(genicam, "BinningVertical");
        arv_gc_integer_set_value(ARV_GC_INTEGER(node), binning, NULL);
        value = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
        maximum = arv_gc_integer_get_max(ARV_GC_INTEGER(node), NULL);
        daoInfo("BinningVertical x   = %d (max:%d, wanted:%d)\n", value, maximum, binning);

        node = arv_gc_get_node(genicam, "Width");
        arv_gc_integer_set_value(ARV_GC_INTEGER(node), width, NULL);
        value = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
        maximum = arv_gc_integer_get_max(ARV_GC_INTEGER(node), NULL);
        daoInfo("image width   = %d (max:%d, wanted:%d)\n", value, maximum, width);

        node = arv_gc_get_node(genicam, "Height");
        arv_gc_integer_set_value(ARV_GC_INTEGER(node), height, NULL);
        value = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
        maximum = arv_gc_integer_get_max(ARV_GC_INTEGER(node), NULL);
        daoInfo("image height  = %d (max:%d, wanted:%d)\n", value, maximum, height);

        node = arv_gc_get_node(genicam, "ExposureTime");
        if (ARV_IS_GC_NODE(node))
        {
            v_double = arv_gc_float_get_value(ARV_GC_FLOAT(node), NULL);
            v_double_min = arv_gc_float_get_min(ARV_GC_FLOAT(node), NULL);
            v_double_max = arv_gc_float_get_max(ARV_GC_FLOAT(node), NULL);
            daoInfo("exposure       = %g (min:%g - max:%g)\n", v_double, v_double_min, v_double_max);
        }

        node = arv_gc_get_node(genicam, "PixelFormat");
        arv_gc_enumeration_set_string_value(ARV_GC_ENUMERATION(node), "Mono10", NULL);
        v_string = arv_gc_enumeration_get_string_value(ARV_GC_ENUMERATION(node), NULL);
        daoInfo("pixel format    = %s\n", v_string);
        value = arv_gc_enumeration_get_int_value(ARV_GC_ENUMERATION(node), NULL);
        daoInfo("pixel format  = %d (0x%x)\n", value, value);

        node = arv_gc_get_node(genicam, "PayloadSize");
        value = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
        daoInfo("payload size  = %d (0x%x)\n", value, value);

        GError *error=NULL;
        daoInfo("creating stream...\n");
        stream = arv_device_create_stream(device, NULL, NULL, &error);
        daoInfo("creating stream done...\n");
        gint n_input_buffers, n_output_buffers;
        if (ARV_IS_STREAM(stream))
        {

            daoInfo("setting stream socket buffer...\n");
            if (arv_option_auto_buffer)
            {
                g_object_set(stream,
                             "socket-buffer", ARV_GV_STREAM_SOCKET_BUFFER_AUTO,
                             "socket-buffer-size", 0,
                             NULL);
            }
            daoInfo("pushing buffer...\n");
            for (i = 0; i < 20; i++)
            {
                arv_stream_push_buffer((ArvStream *)stream, arv_buffer_new(value, NULL));
            }
            arv_stream_get_n_buffers(stream, &n_input_buffers, &n_output_buffers);
            daoInfo("After push: input=%d, output=%d\n", n_input_buffers, n_output_buffers);
        }
        else
        {
            daoError("Not a stream\n");
            return DAO_ERROR;
        }

        status = 1;
        done = clock();
        diff = (double)(done - launch) / CLOCKS_PER_SEC;
        daoInfo("%ld, %ld, %ld\n", done, launch, CLOCKS_PER_SEC);
        daoInfo("camera init status = %d, init time=%.3f\n", status, diff);
        fflush(stdout);

        if (pthread_create(&camCtrlThread, NULL, camCtrlLoop, (void *)&threadIdCamCtrl) != 0)
        {
            daoError("Cannot create camera controller thead\n");
            return DAO_ERROR;
        }
        usleep(1000000);

        if (pthread_create(&camReaderThread, NULL, camRealTimeLoop, (void *)&threadIdCamReader) != 0)
        {
            daoError("Cannot create camera reader thead\n");
            return DAO_ERROR;
        }

        pthread_join(camReaderThread, NULL);
    }
    else
    {
        daoError("Not a Device\n");
        return DAO_ERROR;
    }
    return DAO_SUCCESS;
}

static void DecodeArgs(int argc, char **argv)
    /*
     **	Parse the input arguments.
     */
{
    char *str;
    int a1;

    argv += 1;	argc -= 1;					/* skip program name */

    while (argc-- > 0) {
        daoDebug("DecodeArgs: working on '%s'/%d\n",*argv,argc);
        str = *argv++;
        if (str[0] != '-') {
            daoError("Do not know arg '%s'\n",str);
            ShowHelp();
            exit(1);
        }

        switch (str[1]) {
            case 'h':	ShowHelp(); exit(0);
	        case 'd':	
			            (void)sscanf(*argv++,"%d",&daoLogLevel); argc -= 1;
			            break;
            case 'l':
                        daoInfo("%s\n",*argv);
                        argv += 1; argc -= 1;
                        break;

            case 'u':
                        (void)sscanf(*argv++,"%d",&a1); argc -= 1;
                        daoInfo("will sleep for %d usec\n",a1);
                        (void)usleep(a1);
                        break;
            case 'L':
                        daoInfo("CAM real time control\n");
                        (void)sscanf(*argv++,"%s", shmName);
                        (void)sscanf(*argv++,"%[^\n]", cameraName); // scan all
                        daoInfo("camera SHM                 =		%s \n", shmName);
                        daoInfo("cameraName = 	%s \n", cameraName);
                        realTimeLoop();
                        break;
            default:
                        daoError("Do not know arg '%s'\n",str);
                        ShowHelp();
                        exit(2);
        }
    }

    return;
}
/*==========================================================================*/
int main(int argc, char **argv)
    /*
     **	Fetch the arguments and do what is requested
     */
{
    int RT_priority = 93; //any number from 0-99
    struct sched_param schedpar;

    schedpar.sched_priority = RT_priority;
    // r = seteuid(euid_called); //This goes up to maximum privileges
    sched_setscheduler(0, SCHED_FIFO, &schedpar); //other option is SCHED_RR, might be faster
    // r = seteuid(euid_real);//Go back to normal privileges

    sArgv0 = *argv;

    DecodeArgs(argc,argv);

    return DAO_SUCCESS;
}
/*==========================================================================*/



