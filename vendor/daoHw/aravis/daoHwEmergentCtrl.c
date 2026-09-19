/*****************************************************************************
  DAO project - daoHwEmergentCtrl.c
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

// Alignment helpers for GenICam ROI constraints
#define ALIGN_UP(x, inc)   (((x) + (inc) - 1) / (inc) * (inc))
#define ALIGN_DOWN(x, inc) ((x) / (inc) * (inc))

/*==========================================================================*/
// LineTime in nanoseconds (read from camera: 324 ns)
#define LINE_TIME_NS 324

// Default camera parameter values applied at connection time.
// Actual min/max are always queried live from the camera (GenICam nodes);
// these are just the startup targets (documented ranges in comments).
#define GAIN_DEFAULT          1000   // min:0    max:8191
#define PGA_GAIN_DEFAULT      0      // min:0    max:40
#define HCG_DEFAULT           FALSE
#define AUTO_GAIN_DEFAULT     FALSE
#define PIXEL_FORMAT_DEFAULT  "Mono8"   // overridden at runtime by -r (see pixelBits)
#define EXPOSURE_DEFAULT      2340   // min:1    max:2342
#define FRAME_RATE_DEFAULT    400    // min:1    max:405

//Need to install process with setuid.  Then, so you aren't running privileged all the time do this:
uid_t euid_real;
uid_t euid_called;
uid_t suid;


struct timespec tnow;
double tlastupdatedouble;

IMAGE *shm;
char shmName[32];
char cameraName[32];

// Number of lines to acquire per frame.
//   0 (default) = full frame, same behaviour as before, Height taken from SHM
//   N > 0       = partial scan, N rows centred on the sensor
// Latency = nLines * LINE_TIME_NS ns
// Examples:
//   1 line  ->  ~0.3 us
//   10 lines -> ~3.2 us
//   64 lines -> ~20.7 us
//   620 lines (full frame) -> ~200 us
static int nLines = 0;  // 0 = full frame (default, no -n passed)

// Pixel bit depth requested via -r (8 or 12). 8 = Mono8/1 byte per pixel
// (default), 12 = Mono12/2 bytes per pixel (unpacked into a 16-bit word).
// The SHM the caller passes via -S must be sized accordingly (uint8 for 8,
// uint16 for 12) — this control only drives the camera-side PixelFormat and
// the peek thread's byte stride, it does not allocate the SHM itself.
static int pixelBits = 8;

// Mutex protecting nLines and stream buffer changes between ctrl and reader threads
static pthread_mutex_t nLinesMutex = PTHREAD_MUTEX_INITIALIZER;
// Flag set by ctrl thread to ask reader thread to pause while buffers are rebuilt
static volatile int nLinesChangePending = 0;

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
    printf("   -L shm  serial\n");
    printf(" .                  example: daoHwAravisDeviceCtrl -L wfsImage 1 224.1.1.1 \"First Light Imaging-01-00001cdab9df\"\n");
    printf("   -n nlines        number of lines to acquire per frame (default: full frame)\n");
    printf("                    0 or omitted = full frame (original behaviour)\n");
    printf("                    N > 0 = partial scan, latency = N * %d ns\n", LINE_TIME_NS);
    printf("   -r 8|12          pixel bit depth (default: 8)\n");
    printf("                    8  = PixelFormat Mono8,  SHM must be uint8\n");
    printf("                    12 = PixelFormat Mono12, SHM must be uint16\n");
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
    IMAGE *pgaGainShm = (IMAGE*) malloc(sizeof(IMAGE));
    IMAGE *hcgShm = (IMAGE*) malloc(sizeof(IMAGE));
    IMAGE *autoGainShm = (IMAGE*) malloc(sizeof(IMAGE));
    IMAGE *pixelFormatShm = (IMAGE*) malloc(sizeof(IMAGE));
    IMAGE *posShm = (IMAGE*) malloc(sizeof(IMAGE));
    IMAGE *nLinesShm = (IMAGE*) malloc(sizeof(IMAGE));
    char ditShmFname[200];
    char fpsShmFname[200];
    char gainShmFname[200];
    char pgaGainShmFname[200];
    char hcgShmFname[200];
    char autoGainShmFname[200];
    char pixelFormatShmFname[200];
    char posShmFname[200];
    char nLinesShmFname[200];
    daoToolsInsertShmNamePrefix(shmName, "Dit",         ditShmFname);
    daoToolsInsertShmNamePrefix(shmName, "Fps",         fpsShmFname);
    daoToolsInsertShmNamePrefix(shmName, "Gain",        gainShmFname);
    daoToolsInsertShmNamePrefix(shmName, "PgaGain",     pgaGainShmFname);
    daoToolsInsertShmNamePrefix(shmName, "Hcg",         hcgShmFname);
    daoToolsInsertShmNamePrefix(shmName, "AutoGain",    autoGainShmFname);
    daoToolsInsertShmNamePrefix(shmName, "PixelFormat", pixelFormatShmFname);
    daoToolsInsertShmNamePrefix(shmName, "Pos",         posShmFname);
    daoToolsInsertShmNamePrefix(shmName, "NLines",      nLinesShmFname);

    // Create size array, using 2D of 1x1
    uint32_t size[2];
    size[0] = 1;
    size[1] = 1;
    // Create SHMs
    daoShmImageCreate(ditShm,         ditShmFname,         2, size, _DATATYPE_INT32, 1, 0);
    daoShmImageCreate(fpsShm,         fpsShmFname,         2, size, _DATATYPE_INT32, 1, 0);
    daoShmImageCreate(gainShm,        gainShmFname,        2, size, _DATATYPE_INT32, 1, 0);
    daoShmImageCreate(pgaGainShm,     pgaGainShmFname,     2, size, _DATATYPE_INT32, 1, 0);
    daoShmImageCreate(hcgShm,         hcgShmFname,         2, size, _DATATYPE_INT32, 1, 0);
    daoShmImageCreate(autoGainShm,    autoGainShmFname,    2, size, _DATATYPE_INT32, 1, 0);
    daoShmImageCreate(pixelFormatShm, pixelFormatShmFname, 2, size, _DATATYPE_INT32, 1, 0);
    daoShmImageCreate(nLinesShm,      nLinesShmFname,      2, size, _DATATYPE_INT32, 1, 0);
    size[0] = 2;
    daoShmImageCreate(posShm, posShmFname, 2, size, _DATATYPE_INT32, 1, 0);

    // Initialise nLines SHM with current value.
    // Note: if nLines was 0 (full frame default), realTimeLoop() will have
    // resolved it to height before this thread starts — so the SHM always
    // reflects the actual number of lines being acquired.
    nLinesShm[0].array.SI32[0] = nLines;

    // get initial counters — used to detect changes
    unsigned long cnt0DIT         = ditShm[0].md[0].cnt0;
    unsigned long cnt0FPS         = fpsShm[0].md[0].cnt0;
    unsigned long cnt0GAIN        = gainShm[0].md[0].cnt0;
    unsigned long cnt0PGAGAIN     = pgaGainShm[0].md[0].cnt0;
    unsigned long cnt0HCG         = hcgShm[0].md[0].cnt0;
    unsigned long cnt0AUTOGAIN    = autoGainShm[0].md[0].cnt0;
    unsigned long cnt0PIXELFORMAT = pixelFormatShm[0].md[0].cnt0;
    unsigned long cnt0POS         = posShm[0].md[0].cnt0;
    unsigned long cnt0NLINES      = nLinesShm[0].md[0].cnt0;

    // Node pointer to control
    ArvGcNode *node;

    int v_int;
    int v_int_min;
    int v_int_max;

    // MAIN LOOP
    daoInfo("ENTERING CONTROL LOOP\n");
    while (end==0) 
    {
        // ----------------------------------------------------------------
        // FPS change
        // ----------------------------------------------------------------
        if (cnt0FPS != fpsShm[0].md[0].cnt0)
        {
            cnt0FPS = fpsShm[0].md[0].cnt0;
            daoInfo("New FPS %d, setting up camera\n", fpsShm[0].array.SI32[0]);
            node = arv_gc_get_node(genicam, "AcquisitionStop");
            arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
            node = arv_gc_get_node(genicam, "FrameRate");
            if (ARV_IS_GC_NODE(node))
            {
                v_int = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
                v_int_min = arv_gc_integer_get_min(ARV_GC_INTEGER(node), NULL);
                v_int_max = arv_gc_integer_get_max(ARV_GC_INTEGER(node), NULL);
                daoInfo("\nfps (%d) was = %d (min:%d - max:%d)\n", 
                        fpsShm[0].array.SI32[0], v_int, v_int_min, v_int_max);
                if ((fpsShm[0].array.SI32[0] >= v_int_min) && (fpsShm[0].array.SI32[0] <= v_int_max))
                {
                    arv_gc_integer_set_value(ARV_GC_INTEGER(node), fpsShm[0].array.SI32[0], NULL);
                }
                else
                {
                    daoWarning("\nCannot set fps, not in the range\n");   
                }
                v_int = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
                daoInfo("fps is now = %d\n", v_int);
            } 
            node = arv_gc_get_node(genicam, "AcquisitionStart");
            arv_gc_command_execute(ARV_GC_COMMAND(node), NULL); 
        }

        // ----------------------------------------------------------------
        // DIT (exposure) change
        // ----------------------------------------------------------------
        if (cnt0DIT != ditShm[0].md[0].cnt0)
        {
            cnt0DIT = ditShm[0].md[0].cnt0;
            daoInfo("New DIT %d, setting up camera\n", ditShm[0].array.SI32[0]);
            node = arv_gc_get_node(genicam, "AcquisitionStop");
            arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
            node = arv_gc_get_node(genicam, "Exposure");
            if (ARV_IS_GC_NODE(node))
            {
                v_int = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
                v_int_min = arv_gc_integer_get_min(ARV_GC_INTEGER(node), NULL);
                v_int_max = arv_gc_integer_get_max(ARV_GC_INTEGER(node), NULL);
                daoInfo("\nexposure (%d) was = %d (min:%d - max:%d)\n", 
                        ditShm[0].array.SI32[0], v_int, v_int_min, v_int_max);
                if ((ditShm[0].array.SI32[0] >= v_int_min) && (ditShm[0].array.SI32[0] <= v_int_max))
                {
                    arv_gc_integer_set_value(ARV_GC_INTEGER(node), ditShm[0].array.SI32[0], NULL);
                }
                else
                {
                    daoWarning("\nCannot set dit, not in the range\n");
                }
                v_int = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
                daoInfo("exposure is now = %d\n", v_int);
            }
            node = arv_gc_get_node(genicam, "AcquisitionStart");
            arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
        }

        // ----------------------------------------------------------------
        // GAIN change
        // ----------------------------------------------------------------
        if (cnt0GAIN != gainShm[0].md[0].cnt0)
        {
            cnt0GAIN = gainShm[0].md[0].cnt0;
            daoInfo("New GAIN %d, setting up camera\n", gainShm[0].array.SI32[0]);
            node = arv_gc_get_node(genicam, "AcquisitionStop");
            arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
            node = arv_gc_get_node(genicam, "Gain");
            if (ARV_IS_GC_NODE(node))
            {
                v_int = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
                v_int_min = arv_gc_integer_get_min(ARV_GC_INTEGER(node), NULL);
                v_int_max = arv_gc_integer_get_max(ARV_GC_INTEGER(node), NULL);
                daoInfo("\ngain (%d) was = %d (min:%d - max:%d)\n", 
                        gainShm[0].array.SI32[0], v_int, v_int_min, v_int_max);
                if ((gainShm[0].array.SI32[0] >= v_int_min) && (gainShm[0].array.SI32[0] <= v_int_max))
                {
                    arv_gc_integer_set_value(ARV_GC_INTEGER(node), gainShm[0].array.SI32[0], NULL);
                }
                else
                {
                    daoWarning("\nCannot set gain, not in the range\n");
                }
                v_int = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
                daoInfo("gain is now = %d\n", v_int);
            }
            node = arv_gc_get_node(genicam, "AcquisitionStart");
            arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
        }

        // ----------------------------------------------------------------
        // PGAGain change
        // ----------------------------------------------------------------
        if (cnt0PGAGAIN != pgaGainShm[0].md[0].cnt0)
        {
            cnt0PGAGAIN = pgaGainShm[0].md[0].cnt0;
            daoInfo("New PGAGain %d, setting up camera\n", pgaGainShm[0].array.SI32[0]);
            node = arv_gc_get_node(genicam, "AcquisitionStop");
            arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
            node = arv_gc_get_node(genicam, "PGAGain");
            if (ARV_IS_GC_NODE(node))
            {
                v_int = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
                v_int_min = arv_gc_integer_get_min(ARV_GC_INTEGER(node), NULL);
                v_int_max = arv_gc_integer_get_max(ARV_GC_INTEGER(node), NULL);
                daoInfo("\nPGAGain (%d) was = %d (min:%d - max:%d)\n",
                        pgaGainShm[0].array.SI32[0], v_int, v_int_min, v_int_max);
                if ((pgaGainShm[0].array.SI32[0] >= v_int_min) && (pgaGainShm[0].array.SI32[0] <= v_int_max))
                {
                    arv_gc_integer_set_value(ARV_GC_INTEGER(node), pgaGainShm[0].array.SI32[0], NULL);
                }
                else
                {
                    daoWarning("\nCannot set PGAGain, not in the range\n");
                }
                v_int = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
                daoInfo("PGAGain is now = %d\n", v_int);
            }
            node = arv_gc_get_node(genicam, "AcquisitionStart");
            arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
        }

        // ----------------------------------------------------------------
        // HCG change (boolean)
        // ----------------------------------------------------------------
        if (cnt0HCG != hcgShm[0].md[0].cnt0)
        {
            cnt0HCG = hcgShm[0].md[0].cnt0;
            daoInfo("New HCG %d, setting up camera\n", hcgShm[0].array.SI32[0]);
            node = arv_gc_get_node(genicam, "AcquisitionStop");
            arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
            node = arv_gc_get_node(genicam, "HCG");
            if (ARV_IS_GC_NODE(node))
            {
                arv_gc_boolean_set_value(ARV_GC_BOOLEAN(node), hcgShm[0].array.SI32[0] ? TRUE : FALSE, NULL);
                daoInfo("HCG is now = %d\n", arv_gc_boolean_get_value(ARV_GC_BOOLEAN(node), NULL));
            }
            node = arv_gc_get_node(genicam, "AcquisitionStart");
            arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
        }

        // ----------------------------------------------------------------
        // AutoGain change (boolean)
        // ----------------------------------------------------------------
        if (cnt0AUTOGAIN != autoGainShm[0].md[0].cnt0)
        {
            cnt0AUTOGAIN = autoGainShm[0].md[0].cnt0;
            daoInfo("New AutoGain %d, setting up camera\n", autoGainShm[0].array.SI32[0]);
            node = arv_gc_get_node(genicam, "AcquisitionStop");
            arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
            node = arv_gc_get_node(genicam, "AutoGain");
            if (ARV_IS_GC_NODE(node))
            {
                arv_gc_boolean_set_value(ARV_GC_BOOLEAN(node), autoGainShm[0].array.SI32[0] ? TRUE : FALSE, NULL);
                daoInfo("AutoGain is now = %d\n", arv_gc_boolean_get_value(ARV_GC_BOOLEAN(node), NULL));
            }
            node = arv_gc_get_node(genicam, "AcquisitionStart");
            arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
        }

        // ----------------------------------------------------------------
        // PixelFormat change (enum, value written = raw GenICam enum int)
        // ----------------------------------------------------------------
        if (cnt0PIXELFORMAT != pixelFormatShm[0].md[0].cnt0)
        {
            cnt0PIXELFORMAT = pixelFormatShm[0].md[0].cnt0;
            daoInfo("New PixelFormat %d, setting up camera\n", pixelFormatShm[0].array.SI32[0]);
            node = arv_gc_get_node(genicam, "AcquisitionStop");
            arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
            node = arv_gc_get_node(genicam, "PixelFormat");
            if (ARV_IS_GC_NODE(node))
            {
                arv_gc_enumeration_set_int_value(ARV_GC_ENUMERATION(node), pixelFormatShm[0].array.SI32[0], NULL);
                daoInfo("PixelFormat is now = %s\n",
                        arv_gc_enumeration_get_string_value(ARV_GC_ENUMERATION(node), NULL));
            }
            node = arv_gc_get_node(genicam, "AcquisitionStart");
            arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
        }

        // ----------------------------------------------------------------
        // POS (OffsetX / OffsetY) change
        // Values written to SHM are aligned here before sending to camera.
        // OffsetX: inc=16, min=0, max=248
        // OffsetY: inc=4,  min=0, max=56
        // ----------------------------------------------------------------
        if (cnt0POS != posShm[0].md[0].cnt0)
        {
            cnt0POS = posShm[0].md[0].cnt0;
            daoInfo("New POS %d %d, setting up camera\n",
                    posShm[0].array.SI32[0], posShm[0].array.SI32[1]);
            node = arv_gc_get_node(genicam, "AcquisitionStop");
            arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);

            // OffsetX — align to inc=16
            node = arv_gc_get_node(genicam, "OffsetX");
            if (ARV_IS_GC_NODE(node))
            {
                v_int_min = arv_gc_integer_get_min(ARV_GC_INTEGER(node), NULL);
                v_int_max = arv_gc_integer_get_max(ARV_GC_INTEGER(node), NULL);
                int ox_inc = (int)arv_gc_integer_get_inc(ARV_GC_INTEGER(node), NULL);
                if (ox_inc < 1) ox_inc = 1;
                int ox = ALIGN_DOWN(posShm[0].array.SI32[0], ox_inc);
                if (ox < v_int_min) ox = v_int_min;
                if (ox > v_int_max) ox = v_int_max;
                arv_gc_integer_set_value(ARV_GC_INTEGER(node), ox, NULL);
                v_int = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
                daoInfo("posX is now = %d\n", v_int);
            }

            // OffsetY — align to inc=4
            node = arv_gc_get_node(genicam, "OffsetY");
            if (ARV_IS_GC_NODE(node))
            {
                v_int_min = arv_gc_integer_get_min(ARV_GC_INTEGER(node), NULL);
                v_int_max = arv_gc_integer_get_max(ARV_GC_INTEGER(node), NULL);
                int oy_inc = (int)arv_gc_integer_get_inc(ARV_GC_INTEGER(node), NULL);
                if (oy_inc < 1) oy_inc = 1;
                int oy = ALIGN_DOWN(posShm[0].array.SI32[1], oy_inc);
                if (oy < v_int_min) oy = v_int_min;
                if (oy > v_int_max) oy = v_int_max;
                arv_gc_integer_set_value(ARV_GC_INTEGER(node), oy, NULL);
                v_int = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
                daoInfo("posY is now = %d\n", v_int);
            }

            node = arv_gc_get_node(genicam, "AcquisitionStart");
            arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
        }

        // ----------------------------------------------------------------
        // NLINES change — update ROI height on the fly
        // Latency = nLines * LINE_TIME_NS ns
        //
        // Changing Height alters PayloadSize, so all stream buffers must be
        // drained, freed, and re-pushed with the new size.
        // We signal the reader thread to pause via nLinesChangePending,
        // then rebuild under the mutex.
        // ----------------------------------------------------------------
        if (cnt0NLINES != nLinesShm[0].md[0].cnt0)
        {
            cnt0NLINES = nLinesShm[0].md[0].cnt0;
            int newNLines = nLinesShm[0].array.SI32[0]; // correct: read value, not counter
            daoInfo("New NLines requested: %d (latency ~ %d ns)\n",
                    newNLines, newNLines * LINE_TIME_NS);

            // 1. Stop acquisition
            node = arv_gc_get_node(genicam, "AcquisitionStop");
            arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);

            // 2. Signal reader thread to stop using the stream buffers
            nLinesChangePending = 1;
            pthread_mutex_lock(&nLinesMutex);

            // 3. Drain all pending buffers out of the stream queue
            {
                ArvBuffer *stale;
                while ((stale = arv_stream_try_pop_buffer(stream)) != NULL)
                    g_object_unref(stale);
            }

            // 4. Set new Height, validate range and alignment
            node = arv_gc_get_node(genicam, "Height");
            if (ARV_IS_GC_NODE(node))
            {
                v_int_min = arv_gc_integer_get_min(ARV_GC_INTEGER(node), NULL);
                v_int_max = arv_gc_integer_get_max(ARV_GC_INTEGER(node), NULL);
                int h_inc = (int)arv_gc_integer_get_inc(ARV_GC_INTEGER(node), NULL);
                if (h_inc < 1) h_inc = 1;

                // Round up to alignment, then clamp
                int newNLinesAligned = ALIGN_UP(newNLines, h_inc);
                if (newNLinesAligned < v_int_min) newNLinesAligned = v_int_min;
                if (newNLinesAligned > v_int_max) newNLinesAligned = v_int_max;
                if (newNLinesAligned != newNLines)
                    daoWarning("NLines=%d adjusted to %d (inc=%d, min=%d, max=%d)\n",
                               newNLines, newNLinesAligned, h_inc, v_int_min, v_int_max);
                newNLines = newNLinesAligned;

                arv_gc_integer_set_value(ARV_GC_INTEGER(node), newNLines, NULL);

                // OffsetY is NOT touched — user controls it via Pos SHM

                nLines = newNLines;
                daoInfo("NLines is now = %d, latency ~ %d ns\n",
                        nLines, nLines * LINE_TIME_NS);
            }

            // 5. Read back new PayloadSize and re-push fresh buffers
            node = arv_gc_get_node(genicam, "PayloadSize");
            guint32 newPayload = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
            daoInfo("new payload size = %d bytes\n", newPayload);
            for (int i = 0; i < 10; i++)
                arv_stream_push_buffer(stream, arv_buffer_new(newPayload, NULL));

            // 6. Unlock reader thread, restart acquisition
            nLinesChangePending = 0;
            pthread_mutex_unlock(&nLinesMutex);

            node = arv_gc_get_node(genicam, "AcquisitionStart");
            arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
        }

        usleep(1000); // 1 ms control loop period
    }
    daoInfo("EXITING CONTROL LOOP\n");

    return DAO_SUCCESS;
}

/*--------------------------------------------------------------------------*/
// Shared state between peek thread and main reader thread
typedef struct {
    ArvBuffer           *buffer;        // current complete buffer from Aravis
    const unsigned char *data;          // raw pointer into buffer memory
    int                  sensorWidth;
    int                  sensorHeight;
    int                  bytesPerPixel;
    volatile int         abort;         // set to 1 on exit
} PeekThreadData;

static PeekThreadData peekData;

/*
 * Peek thread.
 *
 * The main thread arms this thread after arv_stream_pop_buffer() returns,
 * meaning the full frame is already in memory. The peek thread then writes
 * it into the SHM nLines rows at a time via daoShmImagePart2Shm(), without
 * waiting — no sentinel needed since the buffer is complete.
 *
 * This gives progressive SHM writes: consumers can start processing the
 * top subapertures while the peek thread is still writing the bottom ones,
 * without any risk of reading incomplete data (each Part2Shm call covers
 * only the rows already written).
 *
 * The latency gain vs. a plain daoShmImage2Shm is the time saved by not
 * doing one large memcpy at the end — instead each nLines-row chunk is
 * available to consumers as soon as it is written, which is nLines *
 * LINE_TIME_NS ns earlier than the full-frame copy.
 */
void * camPeekLoop(void *arg __attribute__((unused)))
{
    daoInfo("Peek thread started\n");
    uint64_t frameNumber = 0;

    while (!peekData.abort)
    {
        // Wait for main thread to arm a new buffer
        while (peekData.buffer == NULL && !peekData.abort)
            usleep(1);
        if (peekData.abort) break;

        const unsigned char *data   = peekData.data;
        int sensorWidth             = peekData.sensorWidth;
        int sensorHeight            = peekData.sensorHeight;
        int bytesPerPixel           = peekData.bytesPerPixel;

        pthread_mutex_lock(&nLinesMutex);
        int localNLines = nLines;
        pthread_mutex_unlock(&nLinesMutex);

        int packetTotal = (sensorHeight + localNLines - 1) / localNLines;

        for (int packetId = 0; packetId < packetTotal && !peekData.abort; packetId++)
        {
            uint32_t position = (uint32_t)packetId  * (uint32_t)sensorWidth
                                                     * (uint32_t)localNLines;
            uint32_t totalPix = (uint32_t)sensorWidth * (uint32_t)sensorHeight;
            uint32_t nbVal    = (uint32_t)sensorWidth * (uint32_t)localNLines;
            if (position + nbVal > totalPix)
                nbVal = totalPix - position;

            daoShmImagePart2Shm((char *)(data + position * bytesPerPixel),
                                nbVal,
                                &shm[0],
                                position,
                                (uint16_t)packetId,
                                (uint16_t)packetTotal,
                                frameNumber);

            daoDebug("peek pkt %02d/%02d pos=%06d nbVal=%05d\n",
                     packetId + 1, packetTotal, position, nbVal);
        }

        // All chunks written — release semaphore, timestamp, notify consumers
        daoShmImagePart2ShmFinalize(&shm[0]);

        // Print packet progress once per second
        guint64 now = g_get_real_time();
        static guint64 lastPrint = 0;
        if (now - lastPrint > 1000000)
        {
            printf("\rframe=%06llu  pkt/frame=%02d  nLines=%d  ",
                   (unsigned long long)frameNumber, packetTotal, localNLines);
            lastPrint = now;
        }

        frameNumber++;

        // Signal main thread we are done — it can recycle the buffer
        peekData.buffer = NULL;
        peekData.data   = NULL;
    }

    daoInfo("Peek thread exiting\n");
    return DAO_SUCCESS;
}

/*--------------------------------------------------------------------------*/
void * camRealTimeLoop(void *thread_data)
{
    daoInfo("ThreadId=%p\n", thread_data);
    daoInfo("ENTERING LOOP\n");

    ArvBuffer *buffer;
    uint32_t frameCount  = 0;
    uint32_t totalCount  = 0;
    guint64 start_time, time;

    ArvGcNode *node;
    guint32 payloadSize;
    node = arv_gc_get_node(genicam, "PayloadSize");
    payloadSize = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
    daoInfo("payload size = %d (0x%x)\n", payloadSize, payloadSize);

    // Initialise peek thread shared state
    memset(&peekData, 0, sizeof(peekData));
    peekData.sensorWidth   = shm[0].md[0].size[0];
    peekData.sensorHeight  = shm[0].md[0].size[1];
    peekData.bytesPerPixel = (pixelBits == 12) ? 2 : 1; // Mono12 = 2 bytes/px, Mono8 = 1

    // Launch peek thread
    pthread_t peekThread;
    if (pthread_create(&peekThread, NULL, camPeekLoop, NULL) != 0)
    {
        daoError("Cannot create peek thread\n");
        return (void *)(intptr_t)DAO_ERROR;
    }

    start_time = g_get_real_time();

    do
    {
        // Blocking pop — wait for Aravis to declare the full buffer complete.
        // Meanwhile the peek thread is already processing chunks as they arrive.
        buffer = arv_stream_pop_buffer(stream);

        if (buffer != NULL)
        {
            size_t sz;
            const unsigned char *data = arv_buffer_get_data(buffer, &sz);

            if (data)
            {
                // Arm the peek thread — it starts peeking from the top of the
                // buffer. By the time pop_buffer returned, the peek thread has
                // likely already processed most chunks.
                // Wait for any previous frame to finish first.
                while (peekData.buffer != NULL && !end)
                    usleep(1);

                peekData.data   = data;
                peekData.buffer = buffer; // this arms the peek thread

                // Wait for peek thread to finalize before recycling buffer
                while (peekData.buffer != NULL && !end)
                    usleep(1);
            }

            arv_stream_push_buffer(stream, buffer);
            frameCount++;
        }

        time = g_get_real_time();
        if (time - start_time > 1000000)
        {
            totalCount += frameCount;
            printf("\rfps=%4d Hz  nLines=%d  latency~%d ns totalCount=%d",
                    frameCount, nLines, nLines * LINE_TIME_NS, totalCount);
            fflush(stdout);
            frameCount  = 0;
            start_time  = time;
        }

    } while (!end);

    // Shut down peek thread
    peekData.abort = 1;
    pthread_join(peekThread, NULL);

    fflush(stdout);

    guint64 n_processed_buffers;
    guint64 n_failures;
    guint64 n_underruns;

    arv_stream_get_statistics(stream, &n_processed_buffers, &n_failures, &n_underruns);

    daoInfo("Processed buffers = %llu\n", (unsigned long long)n_processed_buffers);
    daoInfo("Failures          = %llu\n", (unsigned long long)n_failures);
    daoInfo("Underruns         = %llu\n", (unsigned long long)n_underruns);

    node = arv_gc_get_node(genicam, "AcquisitionStop");
    arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);

    g_object_unref(stream);
    g_object_unref(device);

    daoInfo("EXITING MAIN LOOP\n");
    return DAO_SUCCESS;
}
    
/*--------------------------------------------------------------------------*/
static int realTimeLoop()
{
    int status;
    signal(SIGINT, endme);

    shm = (IMAGE*) malloc(sizeof(IMAGE));
    daoShmShm2Img(shmName, &shm[0]);

    // Full sensor dimensions from SHM (created at full resolution by caller)
    int width  = shm[0].md[0].size[0];
    int height = shm[0].md[0].size[1];

    clock_t launch, done;
    double diff;
    daoInfo("Opening connection to CAM\n");
    launch = clock();

    GError *error = NULL;
    static gboolean arv_option_auto_buffer = FALSE;
    device = arv_open_device(cameraName, &error);

    if (device != NULL)
    {
        daoInfo("Device Created\n");
        guint32 value;
        int v_int;
        int v_int_min;
        int v_int_max;
        const char *v_string;
        int i;

        ArvGcNode *node;
        genicam = arv_device_get_genicam(device);

        // ----------------------------------------------------------------
        // Device info
        // ----------------------------------------------------------------
        node = arv_gc_get_node(genicam, "DeviceVendorName");
        v_string = arv_gc_string_get_value(ARV_GC_STRING(node), NULL);
        daoInfo("vendor        = %s\n", v_string);
        node = arv_gc_get_node(genicam, "DeviceModelName");
        v_string = arv_gc_string_get_value(ARV_GC_STRING(node), NULL);
        daoInfo("model         = %s\n", v_string);
        node = arv_gc_get_node(genicam, "DeviceID");
        v_string = arv_gc_string_get_value(ARV_GC_STRING(node), NULL);
        daoInfo("device id     = %s\n", v_string);

        // ----------------------------------------------------------------
        // Width — set from SHM. The SHM defines the image size.
        // ----------------------------------------------------------------
        {
            node = arv_gc_get_node(genicam, "Width");
            int w_max = (int)arv_gc_integer_get_max(ARV_GC_INTEGER(node), NULL);
            arv_gc_integer_set_value(ARV_GC_INTEGER(node), width, NULL);
            value = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
            daoInfo("image width   = %d (max:%d)\n", value, w_max);

            node = arv_gc_get_node(genicam, "OffsetX");
            if (ARV_IS_GC_NODE(node))
            {
                v_int = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
                daoInfo("OffsetX       = %d (unchanged)\n", v_int);
            }
        }

        // ----------------------------------------------------------------
        // Height / ROI setup
        //
        // nLines == 0 (no -n given): use full frame height from SHM.
        // nLines > 0 (-n N given): partial scan, N rows, aligned to inc=8.
        // OffsetY is NOT modified — left at whatever the camera has.
        // Use the Pos SHM to change OffsetX/OffsetY at runtime.
        // ----------------------------------------------------------------
        // ----------------------------------------------------------------
        // Height — always full frame on the camera.
        // nLines controls how many rows the peek thread processes at a time,
        // NOT the camera ROI. The camera sends the full frame each time;
        // the peek thread starts processing every nLines rows as they arrive.
        // ----------------------------------------------------------------
        if (nLines == 0)
            nLines = height;  // default: one chunk = full frame

        // Set camera to full frame height from SHM
        node = arv_gc_get_node(genicam, "Height");
        arv_gc_integer_set_value(ARV_GC_INTEGER(node), height, NULL);
        value = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
        daoInfo("image height  = %d lines (full frame, peek every %d lines, latency~%d ns)\n",
                value, nLines, nLines * LINE_TIME_NS);

        // Log current OffsetY — not modified
        node = arv_gc_get_node(genicam, "OffsetY");
        if (ARV_IS_GC_NODE(node))
        {
            v_int = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
            daoInfo("OffsetY       = %d (unchanged)\n", v_int);
        }

        // ----------------------------------------------------------------
        // Gain (min:0 max:8191, default:1000)
        // ----------------------------------------------------------------
        node = arv_gc_get_node(genicam, "Gain");
        if (ARV_IS_GC_NODE(node))
        {
            v_int_min = arv_gc_integer_get_min(ARV_GC_INTEGER(node), NULL);
            v_int_max = arv_gc_integer_get_max(ARV_GC_INTEGER(node), NULL);
            v_int = GAIN_DEFAULT;
            if (v_int < v_int_min) v_int = v_int_min;
            if (v_int > v_int_max) v_int = v_int_max;
            arv_gc_integer_set_value(ARV_GC_INTEGER(node), v_int, NULL);
            v_int = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
            daoInfo("gain          = %d (min:%d - max:%d)\n", v_int, v_int_min, v_int_max);
        }

        // ----------------------------------------------------------------
        // PGAGain (min:0 max:40, default:0)
        // ----------------------------------------------------------------
        node = arv_gc_get_node(genicam, "PGAGain");
        if (ARV_IS_GC_NODE(node))
        {
            v_int_min = arv_gc_integer_get_min(ARV_GC_INTEGER(node), NULL);
            v_int_max = arv_gc_integer_get_max(ARV_GC_INTEGER(node), NULL);
            v_int = PGA_GAIN_DEFAULT;
            if (v_int < v_int_min) v_int = v_int_min;
            if (v_int > v_int_max) v_int = v_int_max;
            arv_gc_integer_set_value(ARV_GC_INTEGER(node), v_int, NULL);
            v_int = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
            daoInfo("PGA gain      = %d (min:%d - max:%d)\n", v_int, v_int_min, v_int_max);
        }

        // ----------------------------------------------------------------
        // HCG (High Conversion Gain, default:false)
        // ----------------------------------------------------------------
        node = arv_gc_get_node(genicam, "HCG");
        if (ARV_IS_GC_NODE(node))
        {
            arv_gc_boolean_set_value(ARV_GC_BOOLEAN(node), HCG_DEFAULT, NULL);
            daoInfo("HCG           = %d\n", arv_gc_boolean_get_value(ARV_GC_BOOLEAN(node), NULL));
        }

        // ----------------------------------------------------------------
        // AutoGain (default:false)
        // ----------------------------------------------------------------
        node = arv_gc_get_node(genicam, "AutoGain");
        if (ARV_IS_GC_NODE(node))
        {
            arv_gc_boolean_set_value(ARV_GC_BOOLEAN(node), AUTO_GAIN_DEFAULT, NULL);
            daoInfo("AutoGain      = %d\n", arv_gc_boolean_get_value(ARV_GC_BOOLEAN(node), NULL));
        }

        // ----------------------------------------------------------------
        // Exposure (min:1 max:2342, default:2340)
        // ----------------------------------------------------------------
        node = arv_gc_get_node(genicam, "Exposure");
        if (ARV_IS_GC_NODE(node))
        {
            v_int_min = arv_gc_integer_get_min(ARV_GC_INTEGER(node), NULL);
            v_int_max = arv_gc_integer_get_max(ARV_GC_INTEGER(node), NULL);
            v_int = EXPOSURE_DEFAULT;
            if (v_int < v_int_min) v_int = v_int_min;
            if (v_int > v_int_max) v_int = v_int_max;
            arv_gc_integer_set_value(ARV_GC_INTEGER(node), v_int, NULL);
            v_int = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
            daoInfo("exposure      = %d (min:%d - max:%d)\n", v_int, v_int_min, v_int_max);
        }

        // ----------------------------------------------------------------
        // FrameRate (min:1 max:405, default:400)
        // ----------------------------------------------------------------
        node = arv_gc_get_node(genicam, "FrameRate");
        if (ARV_IS_GC_NODE(node))
        {
            v_int_min = arv_gc_integer_get_min(ARV_GC_INTEGER(node), NULL);
            v_int_max = arv_gc_integer_get_max(ARV_GC_INTEGER(node), NULL);
            v_int = FRAME_RATE_DEFAULT;
            if (v_int < v_int_min) v_int = v_int_min;
            if (v_int > v_int_max) v_int = v_int_max;
            arv_gc_integer_set_value(ARV_GC_INTEGER(node), v_int, NULL);
            v_int = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
            daoInfo("frame rate    = %d (min:%d - max:%d)\n", v_int, v_int_min, v_int_max);
        }

        // ----------------------------------------------------------------
        // Pixel format — driven by -r (default:Mono8, -r 12 => Mono12)
        // ----------------------------------------------------------------
        {
            const char *pixelFormatWanted = (pixelBits == 12) ? "Mono12" : PIXEL_FORMAT_DEFAULT;
            node = arv_gc_get_node(genicam, "PixelFormat");
            arv_gc_enumeration_set_string_value(ARV_GC_ENUMERATION(node), pixelFormatWanted, NULL);
            v_string = arv_gc_enumeration_get_string_value(ARV_GC_ENUMERATION(node), NULL);
            daoInfo("pixel format  = %s\n", v_string);
            value = arv_gc_enumeration_get_int_value(ARV_GC_ENUMERATION(node), NULL);
            daoInfo("pixel format  = %d (0x%x)\n", value, value);
        }

        // ----------------------------------------------------------------
        // Payload size (reflects the reduced ROI)
        // ----------------------------------------------------------------
        node = arv_gc_get_node(genicam, "PayloadSize");
        value = arv_gc_integer_get_value(ARV_GC_INTEGER(node), NULL);
        daoInfo("payload size  = %d (0x%x)\n", value, value);

        // ----------------------------------------------------------------
        // Endianness
        // ----------------------------------------------------------------
        node = arv_gc_get_node(genicam, "GevSCPSBigEndian");
        gboolean be_before = arv_gc_boolean_get_value(ARV_GC_BOOLEAN(node), NULL);
        daoInfo("GevSCPSBigEndian BEFORE = %d\n", be_before);
        arv_gc_boolean_set_value(ARV_GC_BOOLEAN(node), FALSE, NULL);
        gboolean be_after = arv_gc_boolean_get_value(ARV_GC_BOOLEAN(node), NULL);
        daoInfo("GevSCPSBigEndian AFTER  = %d\n", be_after);

        // ----------------------------------------------------------------
        // Metadata
        // ----------------------------------------------------------------
        node = arv_gc_get_node(genicam, "MetadataEn");
        gboolean meta = arv_gc_boolean_get_value(ARV_GC_BOOLEAN(node), NULL);
        daoInfo("MetadataEn    = %d\n", meta);

        // ----------------------------------------------------------------
        // Create stream and push buffers
        // ----------------------------------------------------------------
        GError *error = NULL;
        daoInfo("creating stream...\n");
        stream = arv_device_create_stream(device, NULL, NULL, &error);
        daoInfo("creating stream done\n");

        if (ARV_IS_STREAM(stream))
        {
            if (arv_option_auto_buffer)
            {
                g_object_set(stream,
                             "socket-buffer", ARV_GV_STREAM_SOCKET_BUFFER_AUTO,
                             "socket-buffer-size", 0,
                             NULL);
            }

            // Pre-fill the stream queue with buffers sized to the current payload
            daoInfo("pushing buffers...\n");
            for (i = 0; i < 10; i++)
                arv_stream_push_buffer(stream, arv_buffer_new(value, NULL));

            daoInfo("Starting Acquisition...\n");
            node = arv_gc_get_node(genicam, "AcquisitionStart");
            arv_gc_command_execute(ARV_GC_COMMAND(node), NULL);
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
        daoInfo("camera init status = %d, init time=%.3f s\n", status, diff);
        if (nLines == height)
            daoInfo("ROI: %d x %d (full frame)\n", width, nLines);
        else
            daoInfo("ROI: %d x %d, latency ~ %d ns per frame\n",
                    width, nLines, nLines * LINE_TIME_NS);
        fflush(stdout);

        // Start real-time reader thread
        if (pthread_create(&camReaderThread, NULL, camRealTimeLoop,
                           (void *)&threadIdCamReader) != 0)
        {
            daoError("Cannot create camera reader thread\n");
            return DAO_ERROR;
        }

        // Start control thread
        if (pthread_create(&camCtrlThread, NULL, camCtrlLoop,
                           (void *)&threadIdCamCtrl) != 0)
        {
            daoError("Cannot create camera controller thread\n");
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
{
    char *str;
    int a1;

    argv += 1; argc -= 1;

    while (argc-- > 0) {
        daoDebug("DecodeArgs: working on '%s'/%d\n", *argv, argc);
        str = *argv++;
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
                        (void)sscanf(*argv++, "%d", &daoLogLevel);
                        argc -= 1;
                        break;
            case 'l':
                        daoInfo("%s\n", *argv);
                        argv += 1; argc -= 1;
                        break;
            case 'u':
                        (void)sscanf(*argv++, "%d", &a1);
                        argc -= 1;
                        daoInfo("will sleep for %d usec\n", a1);
                        (void)usleep(a1);
                        break;
            case 'n':
                        // Set number of lines (ROI height) for partial scan.
                        // If -n is not passed, nLines stays 0 = full frame (default).
                        (void)sscanf(*argv++, "%d", &nLines);
                        argc -= 1;
                        if (nLines < 1) nLines = 1;
                        daoInfo("nLines = %d  (latency ~ %d ns)\n",
                                nLines, nLines * LINE_TIME_NS);
                        break;
            case 'r':
                        // Pixel bit depth: 8 (Mono8, default) or 12 (Mono12).
                        // Must be passed before -L. The SHM (-S) must already
                        // be sized to match: uint8 for 8, uint16 for 12.
                        (void)sscanf(*argv++, "%d", &pixelBits);
                        argc -= 1;
                        if (pixelBits != 8 && pixelBits != 12)
                        {
                            daoWarning("-r %d not supported, falling back to 8\n", pixelBits);
                            pixelBits = 8;
                        }
                        daoInfo("pixelBits = %d\n", pixelBits);
                        break;
            case 'S':
                        daoInfo("CAM real time control\n");
                        (void)sscanf(*argv++, "%s", shmName);
                        (void)sscanf(*argv++, "%[^\n]", cameraName);
                        daoInfo("camera SHM   = %s\n", shmName);
                        daoInfo("cameraName   = %s\n", cameraName);
                        argc -= 2;
                        break;
            case 'L':
                        realTimeLoop();
                        break;
            default:
                        daoError("Do not know arg '%s'\n", str);
                        ShowHelp();
                        exit(2);
        }
    }

    return;
}

/*==========================================================================*/
int main(int argc, char **argv)
{
    int RT_priority = 93;
    struct sched_param schedpar;

    schedpar.sched_priority = RT_priority;
    sched_setscheduler(0, SCHED_FIFO, &schedpar);

    sArgv0 = *argv;

    DecodeArgs(argc, argv);

    return DAO_SUCCESS;
}
/*==========================================================================*/