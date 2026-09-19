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
#include "daoIportControl.h"

/* SDK Header */
#include <arv.h>


typedef struct _ArvGvStreamThreadData ArvGvStreamThreadData;

typedef struct {
	GThread *thread;
	ArvGvStreamThreadData *thread_data;
} ArvGvStreamPrivate;

struct _ArvGvStream {
	ArvStream	stream;
};

struct _ArvGvStreamClass {
	ArvStreamClass parent_class;
};

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
int multicastMaster;
char multicastAddr[32];
char cameraName[32];

// Thread
pthread_t camReaderThread;
int threadIdCamReader = 0;
pthread_t camCtrlThread;
int threadIdCamCtrl = 0;
pthread_t eventThread;
int threadIdEventHandle = 0;


// termination flag
static int end     = 0;

// termination function for SIGINT callback
static void endme() 
{
    end = 1;
}

static char	*sArgv0=NULL;					/* name of executable */


// TODO: hardcoded for now, need a better solution in the future (especally IP)
guint32 mc_port         = 49495;
// char mc_ip[]            = "192.168.60.1";
guint32 mc_timeout      = 400;
guint32 mc_retry_count  = 3;

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
    printf(" .                  example: daoHwAravisDeviceCtrl -L wfsImage 1 224.1.1.1 \"First Light Imaging-01-00001cdab9df\"\n");
    printf("                    multicastMaster: 1=Master/single 2=listener\n");
    printf("                    multicastAddr: IP\n");
    /*
     **	Timing tests
     */
    printf("   -t nloops        test timing for i/o\n");
    printf("\n");
}

void * camCtrlLoop(void *thread_data)
{
    int threadId;
    memcpy(&threadId, thread_data, sizeof(int));
    daoDebug("camCtrlLoop thread id %d\n", threadId);
    daoInfo("Creating control SHM\n");

    IMAGE *ditShm = (IMAGE*) malloc(sizeof(IMAGE));
    IMAGE *fpsShm = (IMAGE*) malloc(sizeof(IMAGE));
    IMAGE *gainShm = (IMAGE*) malloc(sizeof(IMAGE));
    IMAGE *serialCmdShm = (IMAGE*) malloc(sizeof(IMAGE));
    IMAGE *serialRspShm = (IMAGE*) malloc(sizeof(IMAGE));

    char ditShmFname[200]; 
    char fpsShmFname[200]; 
    char gainShmFname[200]; 
    char serialCmdShmFname[200];
    char serialRspShmFname[200];

    daoToolsInsertShmNamePrefix(shmName, "Dit", ditShmFname);
    daoToolsInsertShmNamePrefix(shmName, "Fps", fpsShmFname);
    daoToolsInsertShmNamePrefix(shmName, "Gain", gainShmFname);
    daoToolsInsertShmNamePrefix(shmName, "SCmd", serialCmdShmFname);
    daoToolsInsertShmNamePrefix(shmName, "SRsp", serialRspShmFname);
//    sprintf(ditShmFname, "%s%s", shmName, "Dit");
//    sprintf(fpsShmFname, "%s%s", shmName, "Fps");
//    sprintf(gainShmFname, "%s%s", shmName, "Gain");

    // Create size array, using 2D of 1x1... can be change to 1D
    uint32_t size[2];
    size[0] = 1;
    size[1] = 1;
    // Create SHM
    daoShmImageCreate(ditShm, ditShmFname, 2, size, _DATATYPE_FLOAT, 1, 0);
    daoShmImageCreate(fpsShm, fpsShmFname, 2, size, _DATATYPE_FLOAT, 1, 0);
    daoShmImageCreate(gainShm, gainShmFname, 2, size, _DATATYPE_FLOAT, 1, 0);
    size[0] = 1024;
    daoShmImageCreate(serialCmdShm, serialCmdShmFname, 2, size, _DATATYPE_UINT8, 1, 0);
    daoShmImageCreate(serialRspShm, serialRspShmFname, 2, size, _DATATYPE_UINT8, 1, 0);

    // get initial counter, will be used to check if there is a change 
    unsigned long cnt0DIT = ditShm[0].md[0].cnt0;
    unsigned long cnt0FPS = fpsShm[0].md[0].cnt0;
    unsigned long cnt0GAIN = gainShm[0].md[0].cnt0;
    unsigned long cnt0SCMD = serialCmdShm[0].md[0].cnt0;
    // unsigned long cnt0SRSP = serialRspShm[0].md[0].cnt0;

    // Node pointer to control
    ArvGcNode *node;

    float v_double;
    float v_double_min;
    float v_double_max;

    // pthread_t eventThread; 
    struct eventThreadArgs eta;
    eta.port = mc_port;
    eta.ip = g_inet_socket_address_get_address(G_INET_SOCKET_ADDRESS(arv_gv_device_get_interface_address(device)));
    eta.exit = end;

    if (pthread_create(&eventThread, NULL, eventHandleThread, (void *)&eta) != 0)
    {
        daoError("Cannot create camera controller thead\n");
    }
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
        
        if(cnt0SCMD != serialCmdShm[0].md[0].cnt0)
        {
            cnt0SCMD = serialCmdShm[0].md[0].cnt0;
            daoInfo("New Serial Command provided %s, setting up camera\n", (char *)serialCmdShm[0].array.V);

            // start event 
            setMC_EVENTS_CHANNEL(device);
            guint32 length;
            char * buffer = buffer2Send((char *)serialCmdShm[0].array.V, &length);

            if(!arv_device_write_memory(device, SERIAL_REGISTER,  length, buffer, NULL))
            {
                daoError("Serial command failed\n");
            }
            daoInfo("Serial command successful\n");
            free(buffer);
        }

        if(eta.awaiting !=0)
        {

            // unsetMC_EVENTS_CHANNEL(device);
            // daoInfo("Serial Respinse:  %s\n", eta.response);
            eta.awaiting = 0;
            daoShmImage2Shm((void *) eta.response,
                            1024,
                            serialRspShm);
        }
        usleep(100);// pause 
    }
    eta.exit=end;
    pthread_join(eventThread, NULL);
    daoInfo("EXITING CONTROL LOOP\n");

    int exit_code = DAO_SUCCESS;
    pthread_exit(&exit_code);
}

/*--------------------------------------------------------------------------*/
void  * camRealTimeLoop(void *thread_data)
{
    // MAIN LOOP
    // Acquiring pixels and putting them in the SHM
    daoInfo("ENTERING LOOP\n");
    ArvBuffer *buffer;
    struct timespec t[2];
    double elapsedTime;
	unsigned buffer_count = 0;
	guint64 start_time, time;
    int threadId;
    memcpy(&threadId, thread_data, sizeof(int));
    daoDebug("CamRealTimeLoop thread id %d\n", threadId);
    ArvGcNode *node;
    guint32 value;
    node = arv_gc_get_node(genicam, "PayloadSize");
    value = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
    daoInfo("payload size  = %d (0x%x)\n", value, value);
    daoInfo("Setting the Event Channel configuration\n");

    GInetAddress *interfaceAddress = g_inet_socket_address_get_address(G_INET_SOCKET_ADDRESS(arv_gv_device_get_interface_address(device)));
    unsigned interfaceAddressInt = daoToolsIp2Int(g_inet_address_to_string(interfaceAddress));
    daoInfo("interfaceAddress = %s (%ld)\n", g_inet_address_to_string(interfaceAddress), interfaceAddressInt);
    setMC_DESTINATION_PORT(device, mc_port);
    setMC_DESTINATION_ADDRESS(device, interfaceAddress);
    setMC_TIMEOUT(device, mc_timeout);
    setMC_RETRY_COUNT(device, mc_retry_count);
    start_time = g_get_real_time();
    do
    {
        clock_gettime(CLOCK_REALTIME, &t[1]);
        do
        {
            printf("\r");
            buffer = arv_stream_try_pop_buffer(stream);
            if (buffer != NULL)
            {
                size_t sz;
                const unsigned short *data = arv_buffer_get_data(buffer, &sz);
                printf("cnt = %04d, sz=%08ld", buffer_count, sz);
                if (data)
                {
                    daoShmImage2Shm((unsigned short *)data,
                                 // sz,
                                 shm[0].md[0].size[0] * shm[0].md[0].size[1],
                                 &shm[0]);
                }
                //arv_stream_push_buffer(stream, arv_buffer_new(value, NULL));
                arv_stream_push_buffer(stream, buffer);
                buffer_count++;
            }
        } while (buffer != NULL);

        time = g_get_real_time();
        if (time - start_time > 1000000)
        {
            printf("\t\t\t  Frame rate = %4d Hz", buffer_count);
            buffer_count = 0;
            start_time = time;
        }

        t[0] = t[1];
        clock_gettime(CLOCK_REALTIME, &t[1]);
        elapsedTime = (t[1].tv_sec - t[0].tv_sec) * 1e3;    // sec to ms
        elapsedTime += (t[1].tv_nsec - t[0].tv_nsec) / 1e6; // us to ms
        elapsedTime = elapsedTime;                          // in sec... :-)
        //printf("\r fps = %.3f Hz", 1e6 / (1000 * elapsedTime));
        fflush(stdout);
    } while (!end);

    fflush(stdout);
    //ArvGcNode *node;
    guint64 n_processed_buffers;
    guint64 n_failures;
    guint64 n_underruns;
//    gettimeofday(&t[1],NULL);  

    arv_stream_get_statistics(stream, &n_processed_buffers, &n_failures, &n_underruns);

    daoInfo("Processed buffers = %llu\n", (unsigned long long)n_processed_buffers);
    daoInfo("Failures          = %llu\n", (unsigned long long)n_failures);
    daoInfo("Underruns         = %llu\n", (unsigned long long)n_underruns);

    node = arv_gc_get_node(genicam, "AcquisitionStop");
    arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);

    unsetMC_DESTINATION_PORT(device);
    unsetMC_DESTINATION_ADDRESS(device);
    unsetMC_TIMEOUT(device);
    unsetMC_RETRY_COUNT(device);

    g_object_unref(stream); 
    g_object_unref(device);

    daoInfo("EXITING MAIN LOOP\n");
    fflush(stdout);
    int exit_code = DAO_SUCCESS;
    pthread_exit(&exit_code);
}
    
/*--------------------------------------------------------------------------*/
static int realTimeLoop()
{
    int status;
    // register interrupt signal to terminate the main loop
    signal(SIGINT, endme);

    shm = (IMAGE*) malloc(sizeof(IMAGE));
    daoShmShm2Img(shmName, &shm[0]);
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

        node = arv_gc_get_node(genicam, "ExposureTime");
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

        GError *error=NULL;

        // If master = 1. either multicast controller of simple client
        if (multicastMaster == 1)
        {
            daoInfo("Multicast Master\n");
            daoInfo("creating stream...\n");
            stream = arv_device_create_stream(device, NULL, NULL, &error);
            daoInfo("creating stream done...\n");
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
                for (i = 0; i < 10; i++)
                {
                    arv_stream_push_buffer(stream, arv_buffer_new(value, NULL));
                }

                // If multicastAddr is not 0, enable multicast on this address
                if (strcmp(multicastAddr, "0.0.0.0") !=0)
                {
                    daoInfo("Writing multicast address to device register... disabled for now\n");

                    //GInetAddress *interfaceAddress = g_inet_socket_address_get_address(G_INET_SOCKET_ADDRESS(arv_gv_device_get_interface_address(device)));
                    //GInetAddress *deviceAddress = g_inet_socket_address_get_address(G_INET_SOCKET_ADDRESS(arv_gv_device_get_device_address(device)));
                    //GInetAddress *multicastAddress = g_inet_address_new_from_string(multicastAddr);

                    //unsigned interfaceAddressInt = daoToolsIp2Int(g_inet_address_to_string(interfaceAddress));
                    //unsigned deviceAddressInt = daoToolsIp2Int(g_inet_address_to_string(deviceAddress));
                    //unsigned multicastAddressInt = daoToolsIp2Int(g_inet_address_to_string(multicastAddress));

                    //daoInfo("interfaceAddress = %s (%ld)\n", g_inet_address_to_string(interfaceAddress), interfaceAddressInt);
                    //daoInfo("deviceAddress = %s (%ld)\n", g_inet_address_to_string(deviceAddress), deviceAddressInt);
                    //daoInfo("multicastAddress = %s (%ld)\n", g_inet_address_to_string(multicastAddress), multicastAddressInt);
                    // address_bytes = g_inet_address_to_bytes (multicastAddress);
                    // arv_device_set_integer_feature_value(ARV_DEVICE(device), "GevSCDA", g_htonl(*((guint64 *)address_bytes)), NULL);
                    //arv_device_write_register (device, 0x00000d18, g_htonl(*((guint32 *)multicastAddress)), NULL);
//                    node = arv_gc_get_node(genicam, "GevSCDA");
//                    //arv_gc_integer_set_value(ARV_GC_INTEGER(node), multicastAddressInt, NULL);
//                    //arv_gc_integer_set_value(ARV_GC_INTEGER(node), g_htonl(*((guint32 *)multicastAddress)), NULL);
//                    value = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
//                    daoInfo("GevSCDA = %ld (%ld wanted)\n", value, multicastAddressInt);
//                    // arv_device_write_register (device,
//                    //                            ARV_GVBS_STREAM_CHANNEL_0_IP_ADDRESS_OFFSET,
//                    //                            multicastAddr, NULL);
//                    // and also subscribe self...
//                    // int nval=g_htonl(multicastAddr);
//                    daoInfo("Joining multicast group (ip %ld)\n", multicastAddressInt);
//                    node = arv_gc_get_node(genicam, "GevPrimaryApplicationSocket");
//                    value = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
//                    daoInfo("socket = %d (0x%x)\n", value, value);
//                    struct ip_mreq mreq;
//                    mreq.imr_multiaddr.s_addr = multicastAddressInt;
//                    mreq.imr_interface.s_addr = 0; // any
                    //setsockopt(value, IPPROTO_IP, IP_ADD_MEMBERSHIP, &mreq, sizeof(mreq));
                    daoInfo("End of multicast part... disabled for now\n");
                }

                daoInfo("Starting Acquisition...\n");
                /* Start the acquisition */
                node = arv_gc_get_node(genicam, "AcquisitionStart");
                arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
            }
            else
            {
                daoError("Not a stream\n");
                return DAO_ERROR;
            }
        }
        else
        {
            daoInfo("Multicast Client\n");
        }

        status = 1;
        done = clock();
        diff = (double)(done - launch) / CLOCKS_PER_SEC;
        daoInfo("%ld, %ld, %ld\n", done, launch, CLOCKS_PER_SEC);
        daoInfo("camera init status = %d, init time=%.3f\n", status, diff);
        fflush(stdout);

        if (pthread_create(&camReaderThread, NULL, camRealTimeLoop, (void *)&threadIdCamReader) != 0)
        {
            daoError("Cannot create camera reader thead\n");
            return DAO_ERROR;
        }
        // Start control thread only if master
        if (multicastMaster == 1)
        {
            if (pthread_create(&camCtrlThread, NULL, camCtrlLoop, (void *)&threadIdCamCtrl) != 0)
            {
                daoError("Cannot create camera controller thead\n");
                return DAO_ERROR;
            }
        }
        void * status;
        int ret = pthread_join(camReaderThread, &status);
        daoError("Camera Control return: %d - %d\n",ret,  *(int*) status );
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
                        (void)sscanf(*argv++,"%d", &multicastMaster);
                        (void)sscanf(*argv++,"%s", multicastAddr);
                        (void)sscanf(*argv++,"%[^\n]", cameraName); // scan all
                        daoInfo("camera SHM                 =		%s \n", shmName);
                        daoInfo("multicast Master/Single    =		%d \n", multicastMaster);
                        daoInfo("multicast IP               =		%s \n", multicastAddr);
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
    daoLogLevel=2;
    sArgv0 = *argv;

    DecodeArgs(argc,argv);

    return DAO_SUCCESS;
}
/*==========================================================================*/



