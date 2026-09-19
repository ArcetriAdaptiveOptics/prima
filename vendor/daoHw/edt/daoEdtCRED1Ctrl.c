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

PdvDev *pdv_p;         // EDT device pointer

//Need to install process with setuid.  Then, so you aren't running privileged all the time do this:
uid_t euid_real;
uid_t euid_called;
uid_t suid;


struct timespec tnow;
double tlastupdatedouble;

IMAGE *shm;
char shmName[32];
char configFile[128];

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
    printf("   -S shm config    shared memory name + config file\n");
    printf("   -L               start loop\n");
    printf("        example: daoEdtCRED1Ctrl -S wfsImage configCRED1 -L\n");
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

    // Read current configuration
    char fpsCmd[] = "fps\n";    // Command to send
    char fpsRsp[256];    // Buffer for the fpsRsp
    int fpsRspLen;
    char gainCmd[] = "gain\n";    // Command to send
    char gainRsp[256];    // Buffer for the fpsRsp
    int gainRspLen;

    // FPS
    // Send the command to the camera
    if (pdv_serial_write(pdv_p, fpsCmd, (int)strlen(fpsCmd)) != 0) 
    {
        daoError("failed to send command '%s'.\n", fpsCmd);
        pdv_close(pdv_p);
        pthread_exit((void*)(intptr_t)DAO_ERROR);
    }
    daoInfo("Command '%s' sent to camera.\n", fpsCmd);
    usleep(100000);
    // Read the fpsRsp from the camera
    float fps;
    fpsRspLen = pdv_serial_read(pdv_p, fpsRsp, sizeof(fpsRsp) - 1);
    if (fpsRspLen > 0) 
    {
        fpsRsp[fpsRspLen] = '\0'; // Null-terminate the fpsRsp
        daoInfo("Camera response: \n%s\n", fpsRsp);
        // Extract the FPS value using sscanf
        if (sscanf(fpsRsp, "Frames per second: %f", &fps) == 1) 
        {
            daoInfo("Extracted FPS: %.2f\n", fps);
            daoShmImage2Shm((float*)&fps, 1, &fpsShm[0]);
        }
        else
        {
            daoError("could not parse FPS value from response.\n");
        }
    } 
    else
    {
        daoError("no response from camera.\n");
    } 
    // GAIN
    // Send the command to the camera
    if (pdv_serial_write(pdv_p, gainCmd, (int)strlen(gainCmd)) != 0) 
    {
        daoError("failed to send command '%s'.\n", gainCmd);
        pdv_close(pdv_p);
        pthread_exit((void*)(intptr_t)DAO_ERROR);
    }
    daoInfo("Command '%s' sent to camera.\n", gainCmd);
    usleep(100000);
    // Read the response from the camera
    float gain;
    gainRspLen = pdv_serial_read(pdv_p, gainRsp, sizeof(gainRsp) - 1);
    if (gainRspLen > 0) 
    {
        gainRsp[gainRspLen] = '\0'; // Null-terminate the gainRsp
        daoInfo("Camera response: \n%s\n", gainRsp);
        // Extract the gain value using sscanf
        if (sscanf(gainRsp, "Gain: %f", &gain) == 1) 
        {
            daoInfo("Extracted gain: %.2f\n", gain);
            daoShmImage2Shm((float*)&gain, 1, &gainShm[0]);
        }
        else
        {
            daoError("could not parse FPS value from response.\n");
        }
    } 
    else
    {
        daoError("no response from camera.\n");
    } 

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
            // Create a 'set fps XXX' command
            char cmd[256]; // Buffer to store the command
            char rsp[256];    // Buffer for the fpsRsp
            int rspLen;
            // Format the command string
            snprintf(cmd, sizeof(cmd), "set fps %.3f\n", fpsShm[0].array.F[0]);
            if (pdv_serial_write(pdv_p, cmd, (int)strlen(cmd)) != 0) 
            {
                daoError("failed to send command '%s'.\n", cmd);
                pdv_close(pdv_p);
                pthread_exit((void*)(intptr_t)DAO_ERROR);
            }
            daoInfo("Command '%s' sent to camera.\n", cmd);
            usleep(100000);
            // Readback status of the command to clean the console
            rspLen = pdv_serial_read(pdv_p, rsp, sizeof(rsp) - 1);
            if (rspLen <= 0)
            {
                daoError("no response from camera.\n");
            }
            usleep(100000);

            // readback FPS
            // Send the command to the camera
            if (pdv_serial_write(pdv_p, fpsCmd, (int)strlen(fpsCmd)) != 0) 
            {
                daoError("failed to send command '%s'.\n", fpsCmd);
                pdv_close(pdv_p);
                pthread_exit((void*)(intptr_t)DAO_ERROR);
            }
            daoInfo("Command '%s' sent to camera.\n", fpsCmd);
            usleep(100000);
            // Read the fpsRsp from the camera
            float fps;
            fpsRspLen = pdv_serial_read(pdv_p, fpsRsp, sizeof(fpsRsp) - 1);
            if (fpsRspLen > 0) 
            {
                fpsRsp[fpsRspLen] = '\0'; // Null-terminate the fpsRsp
                daoInfo("Camera response: \n%s\n", fpsRsp);
                // Extract the FPS value using sscanf
                if (sscanf(fpsRsp, "Frames per second: %f", &fps) == 1) 
                {
                    daoInfo("Extracted FPS: %.2f\n", fps);
                    daoShmImage2Shm((float*)&fps, 1, &fpsShm[0]);
                }
                else
                {
                    daoError("could not parse FPS value from response.\n");
                }
            } 
            else
            {
                daoError("no response from camera.\n");
            } 
            // Finished
            cnt0FPS = fpsShm[0].md[0].cnt0;
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
            
            // Cast void* to char*
            char *char_ptr = (char *)serialCmdShm[0].array.V;
            // Find the length of the string (up to '\0')
            size_t len = strlen(char_ptr);
            // Copy the string into a new buffer
            char *result = (char *)malloc(len + 1);
            strncpy(result, char_ptr, len);
            result[len] = '\n';  // Ensure null-termination

            daoInfo("Extracted String: %s\n", result);


            // Send the command to the camera
            //if (pdv_serial_write(pdv_p, (char *)serialCmdShm[0].array.V,
            //                     (int)strlen((char *)serialCmdShm[0].array.V)) != 0) 
            //{
            //    daoError("failed to send command '%s'.\n", (char *)serialCmdShm[0].array.V);
            if (pdv_serial_write(pdv_p, (char *)result,
                                 (int)strlen((char *)result)) != 0) 
            {
                daoError("failed to send command '%s'.\n", (char *)result);
                free(result);
                pdv_close(pdv_p);
                pthread_exit((void*)(intptr_t)DAO_ERROR);
            }

            daoInfo("Command '%s' sent to camera.\n", (char *)result);
            usleep(100000);

            // Read the response from the camera
            int rspLen = pdv_serial_read(pdv_p, (char *)serialRspShm[0].array.V, 1024);
            if (rspLen > 0)
            {
                ((char *)serialRspShm[0].array.V)[rspLen] = '\0'; // Null-terminate the response
                printf("Camera response: \n'%s'\n", (char *)serialRspShm[0].array.V);
            } 
            else
            {
                daoError("no response from camera.\n");
            }
            free(result);

            daoInfo("Serial command successful\n");
        }
        usleep(100);// pause 
    }
    daoInfo("EXITING CONTROL LOOP\n");

    int exit_code = DAO_SUCCESS;
    pthread_exit(&exit_code);
}

//serial = FliSdk.FliSerialCamera
//res, msg = serial.SendCommand(context, 'set gain 1')
//#res, msg = serial.SendCommand(context, 'set mode globalresetsingle')
//#res, msg = serial.SendCommand(context, 'set mode globalresetcds')
//res, msg = serial.SendCommand(context, 'set mode globalresetbursts')
//res, msg = serial.SendCommand(context, 'set nbreadworeset 30')
//
//#res, msg = serial.SendCommand(context, 'set mode rollingresetnro')
//#res, msg = serial.SendCommand(context, 'set nbreadworeset 50') # Number non-destructive readout of the FRAME
//
//#res, msg = serial.SendCommand(context, 'set mode rollingresetiota')
//#res, msg = serial.SendCommand(context, 'set nbreadworeset 1') # Number non-destructive readout of the FRAME
//#res, msg = serial.SendCommand(context, 'set nloop 10') # Number of times a LINE is read in IOTA mode
//#res, msg = serial.SendCommand(context, 'set nsample 1') # Number of times a PIXEL is read in IOTA mode
//
//res, msg = serial.SendCommand(context, 'set rawimages on')
//res, msg = serial.SendCommand(context, 'set cropping on')
//res, msg = serial.SendCommand(context, 'set cropping columns 4-8')
//res, msg = serial.SendCommand(context, 'set cropping rows 50-180')
//res, msg = serial.SendCommand(context, 'set imagetags on')
//res, msg = serial.SendCommand(context, 'set fowlerreadout on')
//
//res, msg = serial.SendCommand(context, 'set overillumination acknowledge')
//
//
//FliSdk.SetBufferSizeInImages(context, 1000)

//#define IMAGE_WIDTH  128
//#define IMAGE_HEIGHT 128
//#define IMAGE_SIZE   (IMAGE_WIDTH * IMAGE_HEIGHT * 2) // Each pixel is 2 bytes (uint16)
#define IMAGE_WIDTH  320
#define IMAGE_HEIGHT 256
#define IMAGE_SIZE   (IMAGE_WIDTH * IMAGE_HEIGHT * 2) // Each pixel is 2 bytes (uint16)

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

    void *captured_image=NULL;
    // Configure timeout to avoid indefinite waits
    pdv_set_timeout(pdv_p, 1000); // 1000 milliseconds timeout
    //pdv_multibuf(pdv_p, 4);
    //pdv_start_images(pdv_p, 1);
    do
    {
        t[0] = t[1];

        captured_image = pdv_image(pdv_p);
        pdv_flush_fifo(pdv_p);
        //pdv_start_image(pdv_p);
        if (captured_image != NULL)
        {
            daoShmImage2Shm((unsigned short *)captured_image, IMAGE_WIDTH*IMAGE_HEIGHT, &shm[0]);
        }
        else
        {
            daoWarning("MIssed frame\n"); 
        }
        clock_gettime(CLOCK_REALTIME, &t[1]);
        elapsedTime = (t[1].tv_sec - t[0].tv_sec) * 1e3;    // sec to ms
        elapsedTime += (t[1].tv_nsec - t[0].tv_nsec) / 1e6; // us to ms
        elapsedTime = elapsedTime;                          // in sec... :-)
        printf("\r fps = %.3f Hz", 1e6 / (1000 * elapsedTime));
        fflush(stdout);
    } while (!end);

    fflush(stdout);

    daoInfo("EXITING MAIN LOOP\n");
    fflush(stdout);
    int exit_code = DAO_SUCCESS;
    pthread_exit(&exit_code);
}
    
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

    PdvDependent *dd_p;
    Edtinfo edtinfo;

    // Allocate memory for camera configuration
    dd_p = pdv_alloc_dependent();
    if (dd_p == NULL)
    {
        daoError("Could not allocate memory for camera configuration.\n");
        pthread_exit((void*)(intptr_t)DAO_ERROR);
    }

    // Read the configuration file
    if (pdv_readcfg(configFile, dd_p, &edtinfo) != 0) 
    {
        daoError("Failed to load configuration file: %s\n", configFile);
        free(dd_p);
        pthread_exit((void*)(intptr_t)DAO_ERROR);
    }

    daoInfo("Successfully loaded configuration file: %s\n", configFile);

    // Open the first available EDT frame grabber device
    pdv_p = pdv_open(EDT_INTERFACE, 0);
    if (pdv_p == NULL) 
    {
        daoInfo("could not open EDT device.\n");
        pthread_exit((void*)(intptr_t)DAO_ERROR);    
    }

    // Initialize the camera
    if (pdv_initcam(pdv_p, dd_p, 0, &edtinfo, configFile, NULL, 0) != 0) 
    {
        daoError("Could not initialize camera.\n");
        pdv_close(pdv_p);
        free(dd_p);
        pthread_exit((void*)(intptr_t)DAO_ERROR);
    }

    daoInfo("Camera successfully initialized.\n");

    // Manually configure serial settings after loading the config
    pdv_set_baud(pdv_p, 115200); // Match your camera's baud rate
    //pdv_set_serial_parity(pdv_p, 0);
    //pdv_set_stopbits(pdv_p, 1);
    //pdv_set_databits(pdv_p, 8);

    stat = 1;
    done = clock();
    diff = (double)(done - launch) / CLOCKS_PER_SEC;
    daoInfo("%ld, %ld, %ld\n", done, launch, CLOCKS_PER_SEC);
    daoInfo("camera init stat = %d, init time=%.3f\n", stat, diff);
    fflush(stdout);

    if (pthread_create(&camReaderThread, NULL, camRealTimeLoop, (void *)&threadIdCamReader) != 0)
    {
        daoError("Cannot create camera reader thead\n");
        pthread_exit((void*)(intptr_t)DAO_ERROR);
    }
    if (pthread_create(&camCtrlThread, NULL, camCtrlLoop, (void *)&threadIdCamCtrl) != 0)
    {
        daoError("Cannot create camera controller thead\n");
        pthread_exit((void*)(intptr_t)DAO_ERROR);
    }
    void * status;
    int ret = pthread_join(camReaderThread, &status);
    daoError("Camera Control return: %d - %d\n",ret,  *(int*) status );

    // Close the EDT device
    pdv_close(pdv_p);
    free(dd_p);


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
            case 'S':
                        daoInfo("CAM real time control\n");
                        (void)sscanf(*argv++,"%s", shmName);
                        (void)sscanf(*argv++,"%[^\n]", configFile); // scan all
                        daoInfo("camera SHM =   %s \n", shmName);
                        daoInfo("configFile = 	%s \n", configFile);
                        break;
            case 'L':
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



