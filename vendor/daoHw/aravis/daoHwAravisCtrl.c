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

// DAO header
#include "dao.h" 
#include "daoTools.h"

/* SDK Header */
#include <arv.h>

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

typedef struct {
    GMainLoop *main_loop;

    int buffer_count;
    int error_count;
    size_t transferred;

    ArvChunkParser *chunk_parser;
    char **chunks;

        gint64 start_time;
} ApplicationData;

typedef struct {
	GMainLoop *main_loop;
	guint32 counter;
} AppData;

AppData appData;
ArvCamera *camera;
ArvStream *stream;
GOptionContext *context;
ArvDevice *device;
ArvGvDevice *gv_device;
GInetAddress *device_address;
GInetAddress *interface_address;

struct timespec t[2];
void
new_buffer_cb (ArvStream *stream, void *user_data)
{
    double elapsedTime;
    ArvBuffer *buffer;
	AppData *app_data = user_data;

    t[0] = t[1];
    /* This code is called from the stream receiving thread, which means all the time spent there is less time
	 * available for the reception of incoming packets */

	buffer = arv_stream_pop_buffer (stream);

	/* Display some informations about the retrieved buffer */
	printf ("\rAcquired %d×%d buffer",
		arv_buffer_get_image_width (buffer),
		arv_buffer_get_image_height (buffer));

    guint32 frameId = arv_buffer_get_frame_id(buffer);
    size_t bufSize;
    const unsigned short *data = arv_buffer_get_data(buffer, &bufSize);
    clock_gettime(CLOCK_REALTIME, &t[1]);
    elapsedTime = (t[1].tv_sec - t[0].tv_sec) * 1e3;
    elapsedTime += (t[1].tv_nsec - t[0].tv_nsec) / 1e6;
    printf(" @ fps = %.3f Hz - new_buffer_cb iframeId=%d data=%d bufSize=%ld", 1e6/(1000*elapsedTime), frameId, data[10], bufSize);
    fflush(stdout);

    /* Image processing here */
    daoShmImage2Shm((unsigned char *)data, bufSize, &shm[0]);

	/* Don't destroy the buffer, but put it back into the buffer pool */
	arv_stream_push_buffer (stream, buffer);

	app_data->counter++;

    if (end == 1)
    {
		g_main_loop_quit (app_data->main_loop);
    }
	//if (app_data->counter == 10)
	//	g_main_loop_quit (app_data->main_loop);
}

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
    printf("   -L Nb            real time control loop: example daoHwAravisCtrl -L shmName cameraName\n");
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
    daoInfo("ThreadId=%p\n", thread_data);
    IMAGE *ditShm = (IMAGE*) malloc(sizeof(IMAGE));
    IMAGE *fpsShm = (IMAGE*) malloc(sizeof(IMAGE));
    IMAGE *gainShm = (IMAGE*) malloc(sizeof(IMAGE));
    //IMAGE *binShm = (IMAGE*) malloc(sizeof(IMAGE));
    char shmDitName[256];
    char shmFpsName[256];
    char shmGainName[256];
    //char shmBinName[256];
    daoToolsInsertShmNamePrefix(shmName, "Dit", shmDitName);
    daoToolsInsertShmNamePrefix(shmName, "Fps", shmFpsName);
    daoToolsInsertShmNamePrefix(shmName, "Gain", shmGainName);
    //daoToolsInsertShmNamePrefix(shmName, "Bin", shmGainName);
    daoShmShm2Img(shmDitName, &ditShm[0]);
    daoShmShm2Img(shmFpsName, &fpsShm[0]);
    daoShmShm2Img(shmGainName, &gainShm[0]);
    //daoShmShm2Img(shmBinName, &binShm[0]);
    unsigned long cnt0DIT = ditShm[0].md[0].cnt0;
    unsigned long cnt0FPS = fpsShm[0].md[0].cnt0;
    unsigned long cnt0GAIN = gainShm[0].md[0].cnt0;
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
	    arv_camera_set_frame_rate (camera, fpsShm[0].array.F[0], NULL);
        }
        // If cnt of DIT SHM change, update DIT in aravis lib
        if (cnt0DIT != ditShm[0].md[0].cnt0)
        {
            cnt0DIT = ditShm[0].md[0].cnt0;
            daoInfo("New DIT %.3f, setting up camera\n", ditShm[0].array.F[0]);
    	    arv_camera_set_exposure_time (camera, ditShm[0].array.F[0], NULL);
        }
        // If cnt of GAIN SHM change, update GAIN in aravis lib
        if (cnt0GAIN != gainShm[0].md[0].cnt0)
        {
            cnt0GAIN = gainShm[0].md[0].cnt0;
            daoInfo("New GAIN %.3f, setting up camera\n", gainShm[0].array.F[0]);
            arv_camera_set_gain(camera, gainShm[0].array.F[0], NULL);
        }
        // If cnt of BIN SHM change, update BIN in aravis lib
        //if (cnt0BIN != binShm[0].md[0].cnt0)
        //{
        //    cnt0BIN = binShm[0].md[0].cnt0;
        //    daoInfo("New BIN %.3f, setting up camera\n", binShm[0].array.F[0]);
        //}
        usleep(1000000);// pause 
    }
    daoInfo("EXITING CONTROL LOOP\n");

    return DAO_SUCCESS;
}

/*--------------------------------------------------------------------------*/
void  * camRealTimeLoop(void *thread_data)
{
    daoInfo("ThreadId=%p\n", thread_data);
    //int status;
    // MAIN LOOP
    daoInfo("ENTERING LOOP\n");
    fflush(stdout);
    struct timeval t[2];

    guint64 n_completed_buffers;
    guint64 n_failures;
    guint64 n_underruns;
    gettimeofday(&t[1],NULL);  

    g_main_loop_run (appData.main_loop);
    g_main_loop_unref (appData.main_loop);
    arv_stream_get_statistics (stream, &n_completed_buffers, &n_failures, &n_underruns);

    arv_camera_stop_acquisition (camera, NULL);
    arv_stream_set_emit_signals (stream, FALSE);
    g_object_unref (stream);

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
    
    int imSizeX = shm[0].md[0].size[0]; 
    int imSizeY = shm[0].md[0].size[1]; 

    clock_t launch, done;
    double diff;
    daoInfo("Opening connection to CAM\n");
    launch=clock();

    // Init Camera
    GError *error = NULL;
    appData.main_loop = g_main_loop_new (NULL, FALSE);
	appData.counter = 0;
    //arv_g_thread_init (NULL);
    //arv_g_type_init ();
    
    camera = arv_camera_new(cameraName, &error);
    // If master = 1. either multicast controller of simple client
    if (camera != NULL) 
    {
        daoInfo("Camera Created\n");
	    gint payload;
	    gint x, y, width, height;
	    double exposure;
	    int gain;
        //arv_camera_set_binning (camera, 1, 1, &error);
        //if (error != NULL)
        //{
        //    daoError("%s\n", error->message);
        //    return DAO_ERROR;
        //}
	    arv_camera_set_region (camera, 0, 0, imSizeX, imSizeY, &error);
	    arv_camera_get_region (camera, &x, &y, &width, &height, &error);
	    //arv_camera_get_binning (camera, &dx, &dy, &error);
	    exposure = arv_camera_get_exposure_time (camera, &error);
	    payload = arv_camera_get_payload (camera, &error);
	    gain = arv_camera_get_gain (camera, &error);
	    daoInfo ("vendor name           = %s\n", arv_camera_get_vendor_name (camera, &error));
	    daoInfo ("model name            = %s\n", arv_camera_get_model_name (camera, &error));
	    daoInfo ("device id             = %s\n", arv_camera_get_device_id (camera, &error));
	    daoInfo ("image width           = %d\n", width);
	    daoInfo ("image height          = %d\n", height);
	    daoInfo ("image x .             = %d\n", x);
	    daoInfo ("image y               = %d\n", y);
	    //daoInfo ("horizontal binning    = %d\n", dx);
	    //daoInfo ("vertical binning      = %d\n", dy);
	    daoInfo ("payload               = %d bytes\n", payload);
	    daoInfo ("exposure              = %g µs\n", exposure);
	    daoInfo ("gain                  = %d dB\n", gain);

	    stream = arv_camera_create_stream (camera, NULL, NULL, &error);
	    if (ARV_IS_STREAM (stream)) 
        {
            daoInfo("is stream\n");
			int i;
			size_t payload;

			/* Retrieve the payload size for buffer creation */
			payload = arv_camera_get_payload (camera, &error);
			if (error == NULL) {
				/* Insert some buffers in the stream buffer pool */
				for (i = 0; i < 5; i++)
					arv_stream_push_buffer (stream, arv_buffer_new (payload, NULL));
			}

			g_signal_connect (stream, "new-buffer", G_CALLBACK (new_buffer_cb), &appData);
			arv_stream_set_emit_signals (stream, TRUE);

			if (error == NULL)
            {
                daoInfo("Starting Acquisition...\n");
				/* Start the acquisition */
                arv_camera_set_string (camera, "TriggerMode", "On", &error);
                arv_camera_set_string (camera, "AcquisitionMode", "Continuous", &error);
                arv_camera_set_string (camera, "TriggerSelector", "AcquisitionStart", &error);
                arv_camera_execute_command (camera, "AcquisitionStart", &error);
				//arv_camera_start_acquisition (camera, NULL);

                //arv_camera_execute_command (camera, "TriggerSoftware", &error);
                //arv_camera_set_string (camera, "TriggerActivation", "RisingEdge", &error);
                //arv_camera_set_string (camera, "TriggerDelay", "0", &error);
            }   
            status=1; 
            done=clock();
            diff = (double)(done - launch) / CLOCKS_PER_SEC;
            daoInfo("%ld, %ld, %ld\n",done, launch, CLOCKS_PER_SEC);
            daoInfo("camera init status = %d, init time=%.3f\n", status, diff);
            fflush(stdout);

            if (pthread_create(&camReaderThread, NULL, camRealTimeLoop, (void *)&threadIdCamReader) != 0)
            {
                daoError("Cannot create camera reader thead\n");
                return DAO_ERROR;
            }
            if (pthread_create(&camCtrlThread, NULL, camCtrlLoop, (void *)&threadIdCamCtrl) != 0)
            {
                daoError("Cannot create camera controller thead\n");
                return DAO_ERROR;
            }

            pthread_join(camReaderThread, NULL);
        }
        else
        {
            daoError("Not a stream\n");
            return DAO_ERROR;
        } 
    }
    else
    {
        daoError("Not a Camera\n");
        return DAO_ERROR;
    } 
    return 0;
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
                        daoInfo("camera SHM =		%s \n", shmName);
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



