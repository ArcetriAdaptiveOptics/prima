/*****************************************************************************
  DAO project
  s.cetre
  this program is a fake camera for aravis using shared memory
  It connects to an exisitng SHM and convert it to a camera
  you can use the daoNoisyPsf.py script to generate a PSF image in SHM (see daoTools)
  and then you can connect to the /tmp/psf.im.shm
  daoHwAravisFakeCamera -L /tmp/psf.im.shm testCam
  the "testCam" GIGE camera will be available in arv-viewer for example
 *****************************************************************************/

/*==========================================================================*/
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#include <signal.h>
#include <time.h>
#include <pthread.h>
#include <sched.h>

#include <arv.h>

#include "dao.h"
#include "daoTools.h"

#define _GNU_SOURCE

IMAGE *shm;
char shmName[32];
char cameraName[32];
char itfName[32];
int camWidth;
int camHeight;
ArvPixelFormat pixelFormat;

uid_t euid_real;
uid_t euid_called;
uid_t suid;

pthread_t shmReaderThread;
int threadIdShmReader = 0;
static int end = 0;
static char *sArgv0 = NULL;

static double arv_option_gvsp_lost_ratio = 0.0;
static char *arv_option_genicam_file = NULL;

// Signal handler to terminate loop
static void endme() {
    end = 1;
}

static void ShowHelp(void) {
    printf("%s of " __DATE__ " at " __TIME__ "\n", sArgv0);
    printf("   arguments:\n");
    printf("   -h               display this message and exit\n");
    printf("   -d               display program debug output\n");
    printf("   -l str           display str in output\n");
    printf("   -L shm camName itfName\n");
    printf("                    example: daoHwAravisFakeCamera -L /tmp/psf.im.shm testCam eth0\n");
}

// This is your custom fill pattern that reads from SHM
static void arv_fake_camera_load_image(ArvBuffer *buffer, void *fill_pattern_data,
                                       guint32 exposure_time_us,
                                       guint32 gain,
                                       ArvPixelFormat pixel_format) {
    if (!buffer) return;

    struct timespec timeout;
    clock_gettime(CLOCK_REALTIME, &timeout);
    timeout.tv_sec += 1;

    uint8_t atype = shm->md[0].atype;

    if (daoShmWaitForSemaphoreTimeout(shm, 3, &timeout) != -1) {
        void *dst = arv_buffer_get_data(buffer, NULL);
        if (atype == _DATATYPE_UINT8) {
            memcpy(dst, shm[0].array.UI8, camWidth * camHeight * sizeof(uint8_t));
        } else if (atype == _DATATYPE_UINT16) {
            memcpy(dst, shm[0].array.UI16, camWidth * camHeight * sizeof(uint16_t));
        }
    } else {
        daoError("Timeout waiting for new image\n");
    }
}

void *shmReadRealTimeLoop(void *thread_data) {
    daoInfo("ThreadId=%p\n", thread_data);
    daoInfo("ENTERING LOOP\n");

    ArvGvFakeCamera *gv_camera = arv_gv_fake_camera_new_full(itfName, cameraName, arv_option_genicam_file);
    g_object_set(gv_camera, "gvsp-lost-ratio", arv_option_gvsp_lost_ratio / 1000.0, NULL);

    // ✅ Register your SHM image loader
    ArvFakeCamera *fake_cam = ARV_FAKE_CAMERA(arv_gv_fake_camera_get_fake_camera(gv_camera));
	// Set resolution and format based on SHM
	arv_fake_camera_write_register(fake_cam, ARV_FAKE_CAMERA_REGISTER_WIDTH, camWidth);
	arv_fake_camera_write_register(fake_cam, ARV_FAKE_CAMERA_REGISTER_HEIGHT, camHeight);
	arv_fake_camera_write_register(fake_cam, ARV_FAKE_CAMERA_REGISTER_PIXEL_FORMAT, pixelFormat);

    arv_fake_camera_set_fill_pattern(fake_cam, arv_fake_camera_load_image, NULL);

    struct timespec t[2], timeout;
    clock_gettime(CLOCK_REALTIME, &t[1]);
    usleep(2000000);

    while (!end) {
        t[0] = t[1];
        clock_gettime(CLOCK_REALTIME, &timeout);
        timeout.tv_sec += 1;

        if (daoShmWaitForSemaphoreTimeout(shm, 2, &timeout) != -1) {
            clock_gettime(CLOCK_REALTIME, &t[1]);
            double elapsedTime = (t[1].tv_sec - t[0].tv_sec) * 1e3 +
                                 (t[1].tv_nsec - t[0].tv_nsec) / 1e6;
            printf("\rFrame received. %.3f ms, FPS: %.2f", elapsedTime, 1e3 / elapsedTime);
            fflush(stdout);
        }
    }

    daoInfo("EXITING MAIN LOOP\n");
    return DAO_SUCCESS;
}

static int realTimeLoop() {
    signal(SIGINT, endme);

    shm = (IMAGE *)malloc(sizeof(IMAGE));
    daoShmShm2Img(shmName, &shm[0]);

    camWidth = shm[0].md[0].size[0];
    camHeight = shm[0].md[0].size[1];

	// Determine pixel format based on SHM atype
	pixelFormat = ARV_PIXEL_FORMAT_MONO_8; // default
	if (shm[0].md[0].atype == _DATATYPE_UINT16)
	{
		pixelFormat = ARV_PIXEL_FORMAT_MONO_16;
	}

    daoInfo("Opening connection to CAM SHM\n");

    if (pthread_create(&shmReaderThread, NULL, shmReadRealTimeLoop, &threadIdShmReader) != 0) {
        daoError("Cannot create camera reader thread\n");
        return DAO_ERROR;
    }

    pthread_join(shmReaderThread, NULL);
    return DAO_SUCCESS;
}

static void DecodeArgs(int argc, char **argv) {
    argv++; argc--;

    while (argc-- > 0) {
        char *str = *argv++;
        if (str[0] != '-') {
            daoError("Do not know arg '%s'\n", str);
            ShowHelp();
            exit(1);
        }

        switch (str[1]) {
            case 'h':
                ShowHelp();
                exit(0);
            case 'd':
                daoLogLevel = atoi(*argv++);
                argc--;
                break;
            case 'l':
                daoInfo("%s\n", *argv++);
                argc--;
                break;
            case 'u':
                usleep(atoi(*argv++));
                argc--;
                break;
            case 'L':
                strncpy(shmName, *argv++, sizeof(shmName) - 1);
                strncpy(cameraName, *argv++, sizeof(cameraName) - 1);
                strncpy(itfName, *argv++, sizeof(itfName) - 1);
                daoInfo("camera SHM = %s\n", shmName);
                daoInfo("cameraName = %s\n", cameraName);
                daoInfo("itfName    = %s\n", itfName);
                realTimeLoop();
                return;
            default:
                daoError("Do not know arg '%s'\n", str);
                ShowHelp();
                exit(2);
        }
    }
}

int main(int argc, char **argv) {
    struct sched_param schedpar;
    schedpar.sched_priority = 93;
    sched_setscheduler(0, SCHED_FIFO, &schedpar);

    sArgv0 = *argv;
    DecodeArgs(argc, argv);
    return DAO_SUCCESS;
}


