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
#include <edtinc.h>

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
    printf("   -L shm serial\n");
    printf(" .                  example: daoHwAravisDeviceCtrl -L wfsImage mycam\n");
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

    // MAIN LOOP
    daoInfo("ENTERING CONTROL LOOP\n");
    while (end==0) 
    {
        // If cnt of FPS SHM change, update FPS in aravis lib
        if (cnt0FPS != fpsShm[0].md[0].cnt0)
        {
            cnt0FPS = fpsShm[0].md[0].cnt0;
            daoInfo("New FPS %.3f, setting up camera\n", fpsShm[0].array.F[0]);
            // INSERT COED HERE
        }
        // If cnt of DIT SHM change, update DIT in aravis lib
        if (cnt0DIT != ditShm[0].md[0].cnt0)
        {
            cnt0DIT = ditShm[0].md[0].cnt0;
            daoInfo("New DIT %.3f, setting up camera\n", ditShm[0].array.F[0]);
            // INSERT COED HERE
        }
        // If cnt of GAIN SHM change, update GAIN in aravis lib
        if (cnt0GAIN != gainShm[0].md[0].cnt0)
        {
            cnt0GAIN = gainShm[0].md[0].cnt0;
            daoInfo("New GAIN %.3f, setting up camera\n", gainShm[0].array.F[0]);
            // INSERT COED HERE
        }
        
        if(cnt0SCMD != serialCmdShm[0].md[0].cnt0)
        {
            cnt0SCMD = serialCmdShm[0].md[0].cnt0;
            daoInfo("New Serial Command provided %s, setting up camera\n", (char *)serialCmdShm[0].array.V);
            // INSERT COED HERE
            daoInfo("Serial command successful\n");
        }
        usleep(100);// pause 
    }
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
    struct timespec t[2];
    double elapsedTime;
    int threadId;
    memcpy(&threadId, thread_data, sizeof(int));
    daoDebug("CamRealTimeLoop thread id %d\n", threadId);
    do
    {
        clock_gettime(CLOCK_REALTIME, &t[1]);
        // INSERT CODE HERE
        t[0] = t[1];
        clock_gettime(CLOCK_REALTIME, &t[1]);
        elapsedTime = (t[1].tv_sec - t[0].tv_sec) * 1e3;    // sec to ms
        elapsedTime += (t[1].tv_nsec - t[0].tv_nsec) / 1e6; // us to ms
        elapsedTime = elapsedTime;                          // in sec... :-)
        //printf("\r fps = %.3f Hz", 1e6 / (1000 * elapsedTime));
        fflush(stdout);
    } while (!end);

    fflush(stdout);

    daoInfo("EXITING MAIN LOOP\n");
    fflush(stdout);
    int exit_code = DAO_SUCCESS;
    pthread_exit(&exit_code);
}
    
#define IMAGE_WIDTH  320
#define IMAGE_HEIGHT 256
#define IMAGE_SIZE   (IMAGE_WIDTH * IMAGE_HEIGHT)

/*--------------------------------------------------------------------------*/
static int realTimeLoop()
{
    int stat;
    // register interrupt signal to terminate the main loop
    signal(SIGINT, endme);

    shm = (IMAGE*) malloc(sizeof(IMAGE));
    daoShmShm2Img(shmName, &shm[0]);
    clock_t launch, done;
    double diff;
    daoInfo("Opening connection to CAM\n");
    launch=clock();

    PdvDev *pdv_p;         // EDT device pointer
    char cmd[] = "fps\n";    // Command to send
    char response[256];    // Buffer for the response
    int response_len;

    // Open the first available EDT frame grabber device
    pdv_p = pdv_open(EDT_INTERFACE, 0);
    if (pdv_p == NULL) {
        fprintf(stderr, "Error: could not open EDT device.\n");
        return DAO_ERROR;
    }

    // Send the command to the camera
    if (pdv_serial_write(pdv_p, cmd, (int)strlen(cmd)) != 0) {
        fprintf(stderr, "Error: failed to send command '%s'.\n", cmd);
        pdv_close(pdv_p);
        return DAO_ERROR;
    }

    printf("Command '%s' sent to camera.\n", cmd);

    // Read the response from the camera
    float fps;
    response_len = pdv_serial_read(pdv_p, response, sizeof(response) - 1);
    if (response_len > 0) {
        response[response_len] = '\0'; // Null-terminate the response
        printf("Camera response: \n'%s'\n", response);
        // Extract the FPS value using sscanf
        if (sscanf(response, "Frames per second: %f", &fps) == 1) {
            printf("Extracted FPS: %.3f\n", fps);
        } else {
            fprintf(stderr, "Error: could not parse FPS value from response.\n");
        }
    } 
    else
    {
        fprintf(stderr, "Error: no response from camera.\n");
    }

    // Close the EDT device
    pdv_close(pdv_p);

    stat = 1;
    done = clock();
    diff = (double)(done - launch) / CLOCKS_PER_SEC;
    daoInfo("%ld, %ld, %ld\n", done, launch, CLOCKS_PER_SEC);
    daoInfo("camera init stat = %d, init time=%.3f\n", stat, diff);
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
    void * status;
    int ret = pthread_join(camReaderThread, &status);
    daoError("Camera Control return: %d - %d\n",ret,  *(int*) status );

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
                        daoInfo("camera SHM =   %s \n", shmName);
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
    daoLogLevel=1;
    sArgv0 = *argv;

    DecodeArgs(argc,argv);

    return DAO_SUCCESS;
}
/*==========================================================================*/



