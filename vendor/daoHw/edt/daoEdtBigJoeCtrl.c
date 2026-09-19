/*****************************************************************************
  DAO project
  s.cetre  (example: SciMeasure Little Joe + EDT PDV, DAO-style args)

  This version includes the ShaneAO / BigJoe 160x160 20-tap descrambler
  directly in C, so the image written to SHM is already fully descrambled.

  This version also protects EDT access with a mutex and pauses acquisition
  when a Little Joe command is sent through the control SHM. This avoids
  disturbing the image stream while serial commands are exchanged.

  CLI style:
    -S <shm> <cfg>    set output shared memory name + EDT cfg file
    -U <unit>         EDT board/unit (default 0)
    -C <chan>         EDT channel (default 0)
    -P <n>            Little Joe personality index (sent as @RCL n)
    -B <baud>         serial baud (default 38400)
    -A 0|1            start acquisition at launch (default 1)
    -L                start loop

  Example:
    daoEdtBigJoeDescrCtrl \
      -U 1 -C 0 \
      -S /tmp/bj_descr.im.shm /home/rtc/DAODATA/config/WFS_BigJoe.cfg \
      -P 5 -A 1 -L

  Notes:
    - Descrambler is hard-coded for ShaneAO / BigJoe 160x160, 20 taps.
    - Output SHM is written as uint16 descrambled 160x160.
    - All EDT device access is serialized with a mutex.
    - User serial commands from SCmd are executed with acquisition paused.
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
#include <sys/mman.h>
#include <sys/time.h>
#include <termios.h>
#include <netinet/in.h>

#include <pthread.h>

// DAO headers
#include "dao.h"
#include "daoTools.h"

// EDT SDK
#include <edtinc.h>

/*==========================================================================*/
/* EDT device pointer */
PdvDev *pdv_p = NULL;

/* Some EDT installs expose pdv_open_channel, some don’t.
   Use weak symbol so we can fall back to pdv_open at runtime. */
extern PdvDev *pdv_open_channel(const char *interface, int unit, int channel) __attribute__((weak));

/* EDT selection */
static int edtUnit = 0;     /* -U */
static int edtChan = 0;     /* -C */

/* Globals */
IMAGE *shm = NULL;
char shmName[32] = {0};
char configFile[256] = {0};

/* Little Joe settings */
static int ljPersonality   = 0;      /* -P -> @RCL n */
static int ljBaud          = 38400;  /* -B */
static int ljStartOnLaunch = 1;      /* -A */

/* Runtime geometry (from EDT / grabber) */
static int gWidth = 0;
static int gHeight = 0;
static int gDepthBits = 0;
static int gBytesPerPixel = 0;
static int gPixels = 0;

/* Threads */
pthread_t camReaderThread;
int threadIdCamReader = 0;
pthread_t camCtrlThread;
int threadIdCamCtrl = 0;

/* termination flag */
static volatile int end = 0;

/* acquisition state / EDT access protection */
static pthread_mutex_t gEdtMutex = PTHREAD_MUTEX_INITIALIZER;
static volatile int gPauseAcq = 0;
static volatile int gAcqArmed = 0;

/* termination function for SIGINT/SIGTERM callback */
static void endme(int sig)
{
    (void)sig;
    end = 1;
}

static char *sArgv0 = NULL; /* name of executable */

/*==========================================================================*/
/* ShaneAO BigJoe descrambler constants */

#define BJ_CAM_PIX   160
#define BJ_NPIX      (BJ_CAM_PIX * BJ_CAM_PIX)
#define BJ_NTAPS     20

static const int BJ_X_TAPS[10] = {0,16,32,48,64,80,96,112,128,144};
static const int BJ_Y_TAPS[2]  = {0,80};

static const int BJ_ORDER[20] =
{
    15,11,4,7,3,8,14,17,5,1,
    2,9,13,18,12,19,6,0,16,10
};

static const int BJ_FLIP_X[20] =
{
    1,1,0,0,0,0,1,1,0,0,
    1,1,0,0,0,0,1,1,0,0
};

static const int BJ_FLIP_Y[20] =
{
    1,1,0,0,0,0,1,1,0,0,
    1,1,0,0,0,0,1,1,0,0
};

static const int BJ_TOP_TAP_SIG_OFFSETS[10] =
{
    16,12,8,4,0,2,6,10,14,18
};

static const int BJ_BOT_TAP_SIG_OFFSETS[10] =
{
    19,15,11,7,3,1,5,9,13,17
};

static const int BJ_TOP_TAP_BLOCKS[10] =
{
    0,1,2,3,4,5,6,7,8,9
};

static const int BJ_BOT_TAP_BLOCKS[10] =
{
    9,8,7,6,5,4,3,2,1,0
};

/* full final map: output pixel i <- raw pixel deintMap[i] */
static int gDeintMap[BJ_NPIX];
static int gDeintMapValid = 0;

/* scratch buffers */
static unsigned short *gRaw16  = NULL;   /* raw frame converted to uint16 */
static unsigned short *gDescr  = NULL;   /* descrambled output */
static int gScratchNPix = 0;

/*==========================================================================*/
static double now_ms_monotonic(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec * 1e3 + (double)ts.tv_nsec / 1e6;
}

/*==========================================================================*/
static void ShowHelp(void)
{
    printf("%s of " __DATE__ " at " __TIME__ "\n", sArgv0);
    printf("   arguments:\n");
    printf("   -h               display this message and exit\n");
    printf("   -d n             display program debug output level\n");
    printf("   -l str           display str in output\n");
    printf("   -u usec          sleep usec\n");
    printf("\n");
    printf("   -S shm cfg        output shared memory name + EDT cfg file\n");
    printf("   -U unit           EDT board/unit (default 0)\n");
    printf("   -C chan           EDT channel (default 0)\n");
    printf("   -P n              Little Joe personality index (@RCL n)\n");
    printf("   -B baud           serial baud (default 38400)\n");
    printf("   -A 0|1            start acquisition at launch (default 1)\n");
    printf("   -L                start loop\n");
    printf("\n");
    printf("   example:\n");
    printf("     daoEdtBigJoeDescrCtrl -U 1 -C 0 -S /tmp/bj_descr.im.shm /home/rtc/DAODATA/config/WFS_BigJoe.cfg -P 5 -A 1 -L\n");
    printf("\n");
}

/*==========================================================================*/
/* Little Joe serial helpers */

static unsigned char g_rxstash[2048];
static int g_rxstash_n = 0;

static void rxstash_push(const unsigned char *p, int n)
{
    if (!p || n <= 0)
        return;

    int room = (int)sizeof(g_rxstash) - g_rxstash_n;
    if (room <= 0)
        return;

    if (n > room)
        n = room;

    memcpy(g_rxstash + g_rxstash_n, p, (size_t)n);
    g_rxstash_n += n;
}

static int rxstash_pop(unsigned char *out, int maxn)
{
    if (!out || maxn <= 0)
        return 0;

    if (g_rxstash_n <= 0)
        return 0;

    int n = g_rxstash_n;
    if (n > maxn)
        n = maxn;

    memcpy(out, g_rxstash, (size_t)n);
    memmove(g_rxstash, g_rxstash + n, (size_t)(g_rxstash_n - n));
    g_rxstash_n -= n;

    return n;
}

static void lj_drain_serial_nolock(void)
{
    char junk[512];
    int n;
    int loops = 0;

    do
    {
        n = pdv_serial_read(pdv_p, junk, (int)sizeof(junk));
        loops++;
    }
    while (n > 0 && loops < 8);
}

static int lj_wait_ack_nolock(int timeout_ms)
{
    const unsigned char ACK = 0x06;
    unsigned char buf[256];
    int elapsed_ms = 0;

    while ((elapsed_ms < timeout_ms) && (end == 0))
    {
        int n = pdv_serial_read(pdv_p, (char*)buf, (int)sizeof(buf));
        if (n > 0)
        {
            int got_ack = 0;

            for (int i = 0; i < n; i++)
            {
                if (buf[i] == ACK)
                    got_ack = 1;
                else
                    rxstash_push(&buf[i], 1);
            }

            if (got_ack)
                return 0;
        }

        usleep(1000);
        elapsed_ms += 1;
    }

    return -1;
}

static int lj_read_text_nolock(char *out, int outsz, int timeout_ms)
{
    if (!out || outsz <= 1)
        return -1;

    out[0] = '\0';

    int total = 0;
    int elapsed_ms = 0;

    if (g_rxstash_n > 0)
    {
        int n = rxstash_pop((unsigned char*)out, outsz - 1);
        total += n;
        out[total] = '\0';
    }

    while ((elapsed_ms < timeout_ms) && (total < outsz - 1) && (end == 0))
    {
        int n = pdv_serial_read(pdv_p, out + total, (int)(outsz - 1 - total));
        if (n > 0)
        {
            total += n;
            out[total] = '\0';

            if (strchr(out, '\r') || strchr(out, '\n'))
                break;

            if (strstr(out, "@RCL!") || strstr(out, "@ERR^") || strstr(out, "@SEQ!") || strstr(out, "@PRG!"))
            {
                /* many replies are short */
            }
        }
        else
        {
            usleep(2000);
            elapsed_ms += 2;
        }
    }

    return total;
}

/* Send Little Joe command (no CR) -> append '\r' and wait for ACK (best-effort).
   Caller must hold gEdtMutex. */
static int lj_send_cmd_nolock(const char *cmd_wo_cr, int ack_timeout_ms)
{
    if (!cmd_wo_cr)
        return DAO_ERROR;

    char cmd[256];
    snprintf(cmd, sizeof(cmd), "%s\r", cmd_wo_cr);

    if (pdv_serial_write(pdv_p, cmd, (int)strlen(cmd)) != 0)
    {
        daoError("pdv_serial_write failed for '%s'\n", cmd_wo_cr);
        return DAO_ERROR;
    }

    if (lj_wait_ack_nolock(ack_timeout_ms) != 0)
        daoWarning("No ACK for '%s' (continuing)\n", cmd_wo_cr);

    return DAO_SUCCESS;
}

/*==========================================================================*/
/* EDT acquisition control helpers. Caller must hold gEdtMutex. */

static int edtStopAcq_nolock(void)
{
    if (pdv_p == NULL)
        return DAO_ERROR;

    if (lj_send_cmd_nolock("@SEQ 0", 800) != DAO_SUCCESS)
        daoWarning("Failed to send @SEQ 0 cleanly\n");

    usleep(50000);
    lj_drain_serial_nolock();

    pdv_flush_fifo(pdv_p);
    gAcqArmed = 0;

    return DAO_SUCCESS;
}

static int edtStartAcq_nolock(void)
{
    if (pdv_p == NULL)
        return DAO_ERROR;

    pdv_flush_fifo(pdv_p);

    if (lj_send_cmd_nolock("@SEQ 1", 800) != DAO_SUCCESS)
        daoWarning("Failed to send @SEQ 1 cleanly\n");

    usleep(50000);
    lj_drain_serial_nolock();

    pdv_start_images(pdv_p, 8);
    gAcqArmed = 1;

    return DAO_SUCCESS;
}

/*==========================================================================*/
/* Execute one Little Joe command with acquisition paused.
   This is the important fix for stream corruption / re-scrambling. */

static int runLittleJoeCommandPaused(const char *cmd, char *rsp, int rspsz)
{
    if (!cmd)
        return DAO_ERROR;

    if (rsp && rspsz > 0)
        rsp[0] = '\0';

    gPauseAcq = 1;
    usleep(20000);  /* let reader thread leave EDT path */

    pthread_mutex_lock(&gEdtMutex);

    daoInfo("Pausing acquisition for command '%s'\n", cmd);

    if (edtStopAcq_nolock() != DAO_SUCCESS)
        daoWarning("edtStopAcq_nolock failed before command '%s'\n", cmd);

    lj_drain_serial_nolock();

    if (lj_send_cmd_nolock(cmd, 800) != DAO_SUCCESS)
        daoWarning("Command send failed for '%s'\n", cmd);

    if (rsp && rspsz > 0)
        (void)lj_read_text_nolock(rsp, rspsz, 300);

    usleep(20000);
    lj_drain_serial_nolock();

    if (edtStartAcq_nolock() != DAO_SUCCESS)
        daoWarning("edtStartAcq_nolock failed after command '%s'\n", cmd);

    pthread_mutex_unlock(&gEdtMutex);

    gPauseAcq = 0;
    return DAO_SUCCESS;
}

/*==========================================================================*/
/* Build ShaneAO/BigJoe deinterlace map exactly like the Python code */

static int buildBigJoeDeintMap(void)
{
    int stage1[BJ_NPIX];
    int blocks[BJ_NTAPS][80][16];

    int top_col = 0;
    int bot_col = 15;
    int top_row = 0;
    int bot_row = 159;

    int i;
    int k;
    int y0;
    int x0;
    int yy;
    int xx;

    if (gWidth != BJ_CAM_PIX || gHeight != BJ_CAM_PIX)
    {
        daoError("BigJoe descrambler requires %dx%d input, got %dx%d\n",
                 BJ_CAM_PIX, BJ_CAM_PIX, gWidth, gHeight);
        return DAO_ERROR;
    }

    /*------------------------------------------------------------------*/
    /* stage 1 */
    for (i = 0; i < BJ_NPIX; i += BJ_NTAPS)
    {
        int cols_top[10];
        int cols_bot[10];

        for (k = 0; k < 10; k++)
        {
            cols_top[k] = BJ_TOP_TAP_BLOCKS[k] * 16 + top_col;
            cols_bot[k] = BJ_BOT_TAP_BLOCKS[k] * 16 + bot_col;
        }

        for (k = 0; k < 10; k++)
            stage1[top_row * BJ_CAM_PIX + cols_top[k]] = i + BJ_TOP_TAP_SIG_OFFSETS[k];

        for (k = 0; k < 10; k++)
            stage1[bot_row * BJ_CAM_PIX + cols_bot[k]] = i + BJ_BOT_TAP_SIG_OFFSETS[k];

        if (top_col < 15)
        {
            top_col += 1;
            bot_col -= 1;
        }
        else
        {
            top_col = 0;
            bot_col = 15;
            top_row += 1;
            bot_row -= 1;
        }
    }

    /*------------------------------------------------------------------*/
    /* extract 20 blocks of stage1, shape (20,80,16) */
    k = 0;
    for (int iy = 0; iy < 2; iy++)
    {
        y0 = BJ_Y_TAPS[iy];
        for (int ix = 0; ix < 10; ix++)
        {
            x0 = BJ_X_TAPS[ix];
            for (yy = 0; yy < 80; yy++)
                for (xx = 0; xx < 16; xx++)
                    blocks[k][yy][xx] = stage1[(y0 + yy) * BJ_CAM_PIX + (x0 + xx)];
            k++;
        }
    }

    /*------------------------------------------------------------------*/
    /* final reorder + flips into gDeintMap */
    k = 0;
    for (int iy = 0; iy < 2; iy++)
    {
        y0 = BJ_Y_TAPS[iy];
        for (int ix = 0; ix < 10; ix++)
        {
            x0 = BJ_X_TAPS[ix];

            int src = BJ_ORDER[k];

            for (yy = 0; yy < 80; yy++)
            {
                for (xx = 0; xx < 16; xx++)
                {
                    int sy = BJ_FLIP_Y[k] ? (79 - yy) : yy;
                    int sx = BJ_FLIP_X[k] ? (15 - xx) : xx;

                    gDeintMap[(y0 + yy) * BJ_CAM_PIX + (x0 + xx)] = blocks[src][sy][sx];
                }
            }

            k++;
        }
    }

    gDeintMapValid = 1;
    daoInfo("Built BigJoe descramble map for %dx%d image\n", gWidth, gHeight);

    return DAO_SUCCESS;
}

/*==========================================================================*/
static int allocDescrambleBuffers(void)
{
    if (gPixels != BJ_NPIX)
    {
        daoError("allocDescrambleBuffers expects %d pixels, got %d\n", BJ_NPIX, gPixels);
        return DAO_ERROR;
    }

    if (gScratchNPix == gPixels && gRaw16 && gDescr)
        return DAO_SUCCESS;

    free(gRaw16);
    free(gDescr);
    gRaw16 = NULL;
    gDescr = NULL;
    gScratchNPix = 0;

    gRaw16 = (unsigned short*)calloc((size_t)gPixels, sizeof(unsigned short));
    gDescr = (unsigned short*)calloc((size_t)gPixels, sizeof(unsigned short));

    if (!gRaw16 || !gDescr)
    {
        daoError("Could not allocate descramble buffers for %d pixels\n", gPixels);
        free(gRaw16);
        free(gDescr);
        gRaw16 = NULL;
        gDescr = NULL;
        return DAO_ERROR;
    }

    gScratchNPix = gPixels;
    return DAO_SUCCESS;
}

/*==========================================================================*/
/* Convert EDT frame to uint16 flat raw buffer */
static int convertCapturedToRaw16(void *captured_image)
{
    if (!captured_image)
        return DAO_ERROR;

    if (!gRaw16 || gScratchNPix != gPixels)
        return DAO_ERROR;

    if (gBytesPerPixel == 2)
    {
        memcpy(gRaw16, captured_image, (size_t)gPixels * sizeof(unsigned short));
        return DAO_SUCCESS;
    }
    else if (gBytesPerPixel == 1)
    {
        unsigned char *u8 = (unsigned char*)captured_image;
        for (int i = 0; i < gPixels; i++)
            gRaw16[i] = (unsigned short)u8[i];
        return DAO_SUCCESS;
    }

    daoError("Unsupported bytes/pixel=%d\n", gBytesPerPixel);
    return DAO_ERROR;
}

/*==========================================================================*/
/* Apply descramble map: descr[i] = raw[map[i]] */
static int descrambleBigJoeRaw16(void)
{
    if (!gDeintMapValid)
    {
        daoError("descrambleBigJoeRaw16 called without valid map\n");
        return DAO_ERROR;
    }

    if (!gRaw16 || !gDescr)
    {
        daoError("descrambleBigJoeRaw16 scratch buffers not ready\n");
        return DAO_ERROR;
    }

    for (int i = 0; i < BJ_NPIX; i++)
        gDescr[i] = gRaw16[gDeintMap[i]];

    return DAO_SUCCESS;
}

/*==========================================================================*/
/* Control thread: SCmd/SRsp SHM pair */
void *camCtrlLoop(void *thread_data)
{
    int threadId;
    memcpy(&threadId, thread_data, sizeof(int));
    daoDebug("camCtrlLoop thread id %d\n", threadId);

    IMAGE *serialCmdShm = (IMAGE*)malloc(sizeof(IMAGE));
    IMAGE *serialRspShm = (IMAGE*)malloc(sizeof(IMAGE));
    if (!serialCmdShm || !serialRspShm)
    {
        daoError("malloc serialCmdShm/serialRspShm failed\n");
        end = 1;
        pthread_exit(NULL);
    }

    char serialCmdShmFname[200];
    char serialRspShmFname[200];

    daoToolsInsertShmNamePrefix(shmName, "SCmd", serialCmdShmFname);
    daoToolsInsertShmNamePrefix(shmName, "SRsp", serialRspShmFname);

    uint32_t size[2];
    size[0] = 1024;
    size[1] = 1;

    daoShmImageCreate(serialCmdShm, serialCmdShmFname, 2, size, _DATATYPE_UINT8, 1, 0);
    daoShmImageCreate(serialRspShm, serialRspShmFname, 2, size, _DATATYPE_UINT8, 1, 0);

    ((char*)serialRspShm[0].array.V)[0] = '\0';
    serialRspShm[0].md[0].write = 1;
    serialRspShm[0].md[0].cnt0++;

    unsigned long cnt0SCMD = serialCmdShm[0].md[0].cnt0;

    daoInfo("ENTERING CONTROL LOOP\n");
    while (end == 0)
    {
        if (cnt0SCMD != serialCmdShm[0].md[0].cnt0)
        {
            cnt0SCMD = serialCmdShm[0].md[0].cnt0;

            char *user = (char*)serialCmdShm[0].array.V;
            if (!user || user[0] == '\0')
            {
                daoWarning("Empty serial command\n");
            }
            else
            {
                char rsp[1024];
                rsp[0] = '\0';

                daoInfo("New Serial Command: '%s'\n", user);

                if (user[0] != '@')
                    daoWarning("Little Joe expects '@XXX ...' commands (got '%s')\n", user);

                if (runLittleJoeCommandPaused(user, rsp, sizeof(rsp)) != DAO_SUCCESS)
                {
                    daoError("runLittleJoeCommandPaused failed for '%s'\n", user);
                    snprintf(rsp, sizeof(rsp), "ERROR running command: %s", user);
                }

                if (rsp[0] != '\0')
                {
                    int L = (int)strlen(rsp);
                    if (L > 0 && rsp[L-1] != '\n')
                        daoInfo("Command reply: %s\n", rsp);
                    else
                        daoInfo("Command reply: %s", rsp);
                }
                else
                {
                    daoInfo("Command reply: (none)\n");
                }

                int n = (int)strlen(rsp);
                if (n > 1023)
                    n = 1023;

                memcpy(serialRspShm[0].array.V, rsp, (size_t)n);
                ((char*)serialRspShm[0].array.V)[n] = '\0';

                serialRspShm[0].md[0].write = 1;
                serialRspShm[0].md[0].cnt0++;
            }
        }

        usleep(2000);
    }

    daoInfo("EXITING CONTROL LOOP\n");
    int exit_code = DAO_SUCCESS;
    pthread_exit(&exit_code);
}

/*==========================================================================*/
/* Reader thread */
void *camRealTimeLoop(void *thread_data)
{
    daoInfo("ENTERING ACQ LOOP\n");

    int threadId;
    memcpy(&threadId, thread_data, sizeof(int));
    daoDebug("CamRealTimeLoop thread id %d\n", threadId);

    pthread_mutex_lock(&gEdtMutex);
    pdv_set_timeout(pdv_p, 1000);
    pdv_multibuf(pdv_p, 8);
    pdv_flush_fifo(pdv_p);
    if (ljStartOnLaunch)
    {
        pdv_start_images(pdv_p, 8);
        gAcqArmed = 1;
    }
    else
    {
        gAcqArmed = 0;
    }
    pthread_mutex_unlock(&gEdtMutex);

    void *captured_image = NULL;

    double t0 = now_ms_monotonic();
    double t_last_print = t0;
    unsigned long frames = 0;

    while (!end)
    {
        if (gPauseAcq)
        {
            usleep(2000);
            continue;
        }

        pthread_mutex_lock(&gEdtMutex);

        if (!gAcqArmed)
        {
            pthread_mutex_unlock(&gEdtMutex);
            usleep(2000);
            continue;
        }

        double ta = now_ms_monotonic();
        captured_image = pdv_wait_image(pdv_p);
        double tb = now_ms_monotonic();

        if ((captured_image != NULL) && (gPauseAcq == 0) && (end == 0))
            pdv_start_image(pdv_p);

        pthread_mutex_unlock(&gEdtMutex);

        if (gPauseAcq)
            continue;

        if (captured_image == NULL)
        {
            daoWarning("pdv_wait_image timeout (no frame)\n");
            continue;
        }

        if (convertCapturedToRaw16(captured_image) != DAO_SUCCESS)
        {
            daoError("convertCapturedToRaw16 failed\n");
            break;
        }

        double tdescr0 = now_ms_monotonic();

        if (descrambleBigJoeRaw16() != DAO_SUCCESS)
        {
            daoError("descrambleBigJoeRaw16 failed\n");
            break;
        }

        double tdescr1 = now_ms_monotonic();

        daoShmImage2Shm(gDescr, gPixels, &shm[0]);

        double tc = now_ms_monotonic();
        frames++;

        if (tc - t_last_print >= 1000.0)
        {
            double dt = tc - t0;
            double fps = (dt > 0.0) ? (1000.0 * (double)frames / dt) : 0.0;

            double dt_img_ms   = tb - ta;
            double dt_descr_ms = tdescr1 - tdescr0;
            double dt_copy_ms  = tc - tdescr1;

            printf("\r fps=%.1f  grab=%.3fms  descramble=%.3fms  shm=%.3fms   ",
                   fps, dt_img_ms, dt_descr_ms, dt_copy_ms);
            fflush(stdout);

            t_last_print = tc;
            t0 = tc;
            frames = 0;
        }
    }

    printf("\n");
    daoInfo("EXITING ACQ LOOP\n");
    int exit_code = DAO_SUCCESS;
    pthread_exit(&exit_code);
}

/*==========================================================================*/
/* Attach or create SHM sized to descrambled geometry */
static int attach_or_create_shm(void)
{
    int rc;

    shm = (IMAGE*)malloc(sizeof(IMAGE));
    if (!shm)
    {
        daoError("malloc shm failed\n");
        return DAO_ERROR;
    }

    rc = daoShmShm2Img(shmName, &shm[0]);
    if (rc != DAO_SUCCESS)
    {
        daoWarning("SHM '%s' not found -> creating\n", shmName);

        uint32_t size[2];
        size[0] = (uint32_t)gHeight;
        size[1] = (uint32_t)gWidth;

        rc = daoShmImageCreate(&shm[0], shmName, 2, size, _DATATYPE_UINT16, 1, 0);
        if (rc != DAO_SUCCESS)
        {
            daoError("Failed to create SHM '%s'\n", shmName);
            return DAO_ERROR;
        }

        daoInfo("Created SHM '%s' size=%ux%u dtype=uint16\n",
                shmName, size[1], size[0]);
        return DAO_SUCCESS;
    }

    int shmRows = (int)shm[0].md[0].size[0];
    int shmCols = (int)shm[0].md[0].size[1];

    if (shmCols != gWidth || shmRows != gHeight)
    {
        daoError("SHM size mismatch: shm=%dx%d but camera=%dx%d\n",
                 shmCols, shmRows, gWidth, gHeight);
        daoError("Fix: create SHM with correct size or use per-program shm name.\n");
        return DAO_ERROR;
    }

    return DAO_SUCCESS;
}

/*==========================================================================*/
static int realTimeLoop(void)
{
    signal(SIGINT, endme);
    signal(SIGTERM, endme);

    clock_t launch = clock();

    PdvDependent *dd_p;
    Edtinfo edtinfo;

    dd_p = pdv_alloc_dependent();
    if (dd_p == NULL)
    {
        daoError("Could not allocate memory for camera configuration.\n");
        return DAO_ERROR;
    }

    if (pdv_readcfg(configFile, dd_p, &edtinfo) != 0)
    {
        daoError("Failed to load configuration file: %s\n", configFile);
        free(dd_p);
        return DAO_ERROR;
    }
    daoInfo("Successfully loaded configuration file: %s\n", configFile);

    daoInfo("Opening EDT device unit=%d chan=%d\n", edtUnit, edtChan);

    if (pdv_open_channel)
        pdv_p = pdv_open_channel(EDT_INTERFACE, edtUnit, edtChan);
    else
        pdv_p = pdv_open(EDT_INTERFACE, edtUnit);

    if (pdv_p == NULL)
    {
        daoError("could not open EDT device (unit=%d chan=%d).\n", edtUnit, edtChan);
        free(dd_p);
        return DAO_ERROR;
    }

    if (pdv_initcam(pdv_p, dd_p, edtUnit, &edtinfo, configFile, NULL, 0) != 0)
    {
        daoError("Could not initialize camera.\n");
        pdv_close(pdv_p);
        pdv_p = NULL;
        free(dd_p);
        return DAO_ERROR;
    }

    daoInfo("Camera successfully initialized.\n");

    pthread_mutex_lock(&gEdtMutex);

    pdv_set_baud(pdv_p, ljBaud);
    lj_drain_serial_nolock();

    {
        char cmd[64];

        (void)lj_send_cmd_nolock("@SEQ 0", 800);
        usleep(50000);
        lj_drain_serial_nolock();

        snprintf(cmd, sizeof(cmd), "@RCL %d", ljPersonality);
        daoInfo("Sending %s\n", cmd);
        (void)lj_send_cmd_nolock(cmd, 800);

        {
            char rsp[256];
            rsp[0] = '\0';
            (void)lj_read_text_nolock(rsp, sizeof(rsp), 200);
            if (rsp[0] != '\0')
                daoInfo("RCL reply: %s", rsp);
        }

        usleep(50000);
        lj_drain_serial_nolock();
    }

    if (ljStartOnLaunch)
    {
        daoInfo("Sending @SEQ 1\n");
        (void)lj_send_cmd_nolock("@SEQ 1", 800);
    }

    {
        char rsp[256] = {0};
        (void)lj_read_text_nolock(rsp, sizeof(rsp), 200);
        daoInfo("SEQ reply: %s\n", rsp[0] ? rsp : "(none)");
    }

    pthread_mutex_unlock(&gEdtMutex);

    gWidth = pdv_get_width(pdv_p);
    gHeight = pdv_get_height(pdv_p);
    gDepthBits = pdv_get_depth(pdv_p);
    gBytesPerPixel = (gDepthBits + 7) / 8;
    gPixels = gWidth * gHeight;

    daoInfo("Active EDT geometry: %dx%d depth=%d bits => %d bytes/pixel\n",
            gWidth, gHeight, gDepthBits, gBytesPerPixel);

    if (gWidth != BJ_CAM_PIX || gHeight != BJ_CAM_PIX)
    {
        daoError("This program expects BigJoe %dx%d frames, got %dx%d\n",
                 BJ_CAM_PIX, BJ_CAM_PIX, gWidth, gHeight);
        pdv_close(pdv_p);
        pdv_p = NULL;
        free(dd_p);
        return DAO_ERROR;
    }

    if (buildBigJoeDeintMap() != DAO_SUCCESS)
    {
        daoError("buildBigJoeDeintMap failed\n");
        pdv_close(pdv_p);
        pdv_p = NULL;
        free(dd_p);
        return DAO_ERROR;
    }

    if (allocDescrambleBuffers() != DAO_SUCCESS)
    {
        daoError("allocDescrambleBuffers failed\n");
        pdv_close(pdv_p);
        pdv_p = NULL;
        free(dd_p);
        return DAO_ERROR;
    }

    if (attach_or_create_shm() != DAO_SUCCESS)
    {
        daoError("SHM attach/create failed\n");
        pdv_close(pdv_p);
        pdv_p = NULL;
        free(dd_p);
        return DAO_ERROR;
    }

    clock_t done = clock();
    double diff = (double)(done - launch) / CLOCKS_PER_SEC;
    daoInfo("camera init time=%.3f s\n", diff);
    fflush(stdout);

    if (pthread_create(&camReaderThread, NULL, camRealTimeLoop, (void*)&threadIdCamReader) != 0)
    {
        daoError("Cannot create camera reader thread\n");
        pdv_close(pdv_p);
        pdv_p = NULL;
        free(dd_p);
        return DAO_ERROR;
    }

    if (pthread_create(&camCtrlThread, NULL, camCtrlLoop, (void*)&threadIdCamCtrl) != 0)
    {
        daoError("Cannot create camera controller thread\n");
        end = 1;
    }

    void *status;
    (void)pthread_join(camReaderThread, &status);

    end = 1;
    (void)pthread_join(camCtrlThread, &status);

    pthread_mutex_lock(&gEdtMutex);

    daoInfo("Sending @SEQ 0\n");
    lj_drain_serial_nolock();
    (void)lj_send_cmd_nolock("@SEQ 0", 800);
    usleep(50000);
    lj_drain_serial_nolock();
    pdv_flush_fifo(pdv_p);
    gAcqArmed = 0;

    pthread_mutex_unlock(&gEdtMutex);

    pdv_close(pdv_p);
    pdv_p = NULL;
    free(dd_p);

    free(gRaw16);
    free(gDescr);
    gRaw16 = NULL;
    gDescr = NULL;
    gScratchNPix = 0;

    return DAO_SUCCESS;
}

/*==========================================================================*/
static void DecodeArgs(int argc, char **argv)
{
    char *str;
    int a1;

    argv += 1;
    argc -= 1;

    while (argc-- > 0)
    {
        daoDebug("DecodeArgs: working on '%s'/%d\n", *argv, argc);
        str = *argv++;

        if (str[0] != '-')
        {
            daoError("Do not know arg '%s'\n", str);
            ShowHelp();
            exit(1);
        }

        switch (str[1])
        {
            case 'h':
                ShowHelp();
                exit(0);

            case 'd':
                (void)sscanf(*argv++, "%d", &daoLogLevel);
                argc -= 1;
                break;

            case 'l':
                daoInfo("%s\n", *argv);
                argv += 1;
                argc -= 1;
                break;

            case 'u':
                (void)sscanf(*argv++, "%d", &a1);
                argc -= 1;
                daoInfo("will sleep for %d usec\n", a1);
                (void)usleep(a1);
                break;

            case 'S':
                daoInfo("CAM parameters\n");
                (void)sscanf(*argv++, "%31s", shmName);
                (void)sscanf(*argv++, "%255[^\n]", configFile);
                argc -= 2;
                daoInfo("camera SHM  = %s\n", shmName);
                daoInfo("configFile  = %s\n", configFile);
                break;

            case 'U':
                (void)sscanf(*argv++, "%d", &edtUnit);
                argc -= 1;
                daoInfo("EDT unit = %d\n", edtUnit);
                break;

            case 'C':
                (void)sscanf(*argv++, "%d", &edtChan);
                argc -= 1;
                daoInfo("EDT channel = %d\n", edtChan);
                break;

            case 'P':
                (void)sscanf(*argv++, "%d", &ljPersonality);
                argc -= 1;
                daoInfo("Little Joe personality (RCL) = %d\n", ljPersonality);
                break;

            case 'B':
                (void)sscanf(*argv++, "%d", &ljBaud);
                argc -= 1;
                daoInfo("Little Joe baud = %d\n", ljBaud);
                break;

            case 'A':
                (void)sscanf(*argv++, "%d", &ljStartOnLaunch);
                argc -= 1;
                daoInfo("Start acquisition on launch = %d\n", ljStartOnLaunch);
                break;

            case 'L':
                daoInfo("Starting loop\n");
                if (shmName[0] == '\0' || configFile[0] == '\0')
                {
                    daoError("You must provide -S <shm> <cfg> before -L\n");
                    ShowHelp();
                    exit(2);
                }
                (void)realTimeLoop();
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

    daoLogLevel = 0; // default log level only warning
    sArgv0 = *argv;

    DecodeArgs(argc, argv);

    return DAO_SUCCESS;
}
/*==========================================================================*/