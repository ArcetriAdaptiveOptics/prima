/*****************************************************************************
  DAO project
  s.cetre  (example: SciMeasure Little Joe + EDT PDV, DAO-style args)

  CLI style (like your daoEdtCRED1Ctrl):
    -S <shm> <cfg>    set shared memory name + EDT cfg file
    -U <unit>         EDT board/unit (default 0)
    -C <chan>         EDT channel (default 0)
    -P <n>            Little Joe personality index (sent as @RCL n)
    -B <baud>         serial baud (default 38400)
    -A 0|1            start acquisition at launch (default 1)
    -L                start loop (init EDT, set personality, optionally start acq, run threads)

  Example:
    daoEdtBigJoeCtrl -U 1 -C 0 -S /tmp/ljImage.im.shm /home/rtc/DAODATA/config/WFS_BigJoe.cfg -P 5 -A 1 -L

  Notes:
    - Uses @RCL n (personality) because on your Big-CCD Little Joe that’s where the real Hz modes live.
    - Prints robust FPS based on CLOCK_MONOTONIC, plus time breakdown (pdv_image vs SHM copy).
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
static int ljPersonality = 0;      /* -P -> @RCL n */
static int ljBaud        = 38400;  /* -B */
static int ljStartOnLaunch = 1;    /* -A */

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

/* termination function for SIGINT/SIGTERM callback */
static void endme(int sig)
{
    (void)sig;
    end = 1;
}

static char *sArgv0 = NULL; /* name of executable */

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
    printf("   -S shm cfg        shared memory name + EDT cfg file\n");
    printf("   -U unit           EDT board/unit (default 0)\n");
    printf("   -C chan           EDT channel (default 0)\n");
    printf("   -P n              Little Joe personality index (@RCL n)\n");
    printf("   -B baud           serial baud (default 38400)\n");
    printf("   -A 0|1            start acquisition at launch (default 1)\n");
    printf("   -L                start loop\n");
    printf("\n");
    printf("   example:\n");
    printf("     daoEdtBigJoeCtrl -U 1 -C 0 -S /tmp/ljImage.im.shm /home/rtc/DAODATA/config/WFS_BigJoe.cfg -P 5 -A 1 -L\n");
    printf("\n");
}

/*==========================================================================*/
/* Little Joe serial helpers */

static unsigned char g_rxstash[2048];
static int g_rxstash_n = 0;

static void rxstash_push(const unsigned char *p, int n)
{
    if (!p || n <= 0) return;
    int room = (int)sizeof(g_rxstash) - g_rxstash_n;
    if (room <= 0) return;
    if (n > room) n = room;
    memcpy(g_rxstash + g_rxstash_n, p, (size_t)n);
    g_rxstash_n += n;
}

static int rxstash_pop(unsigned char *out, int maxn)
{
    if (!out || maxn <= 0) return 0;
    if (g_rxstash_n <= 0) return 0;
    int n = g_rxstash_n;
    if (n > maxn) n = maxn;
    memcpy(out, g_rxstash, (size_t)n);
    memmove(g_rxstash, g_rxstash + n, (size_t)(g_rxstash_n - n));
    g_rxstash_n -= n;
    return n;
}


static void lj_drain_serial(void)
{
    char junk[512];
    int n;
    int loops = 0;

    /* Drain up to a few reads; don’t spin forever */
    do {
        n = pdv_serial_read(pdv_p, junk, (int)sizeof(junk));
        loops++;
    } while (n > 0 && loops < 8);
}

static int lj_wait_ack(int timeout_ms)
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

            /* stash everything except ACK */
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


static int lj_read_text(char *out, int outsz, int timeout_ms)
{
    if (!out || outsz <= 1) return -1;
    out[0] = '\0';

    int total = 0;
    int elapsed_ms = 0;

    /* first consume any bytes saved while waiting for ACK */
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

            /* Prefer CR/LF termination */
            if (strchr(out, '\r') || strchr(out, '\n'))
                break;

            /* If we got something that *looks* like a full AIA reply, we can also stop. */
            if (strstr(out, "@RCL!") || strstr(out, "@ERR^") || strstr(out, "@SEQ!") || strstr(out, "@PRG!"))
            {
                /* many replies are short; if no CR/LF arrives, we’ll still time out */
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


/* Send Little Joe command (no CR) -> append '\r' and wait for ACK (best-effort). */
static int lj_send_cmd(const char *cmd_wo_cr, int ack_timeout_ms)
{
    if (!cmd_wo_cr) return DAO_ERROR;

    char cmd[256];
    snprintf(cmd, sizeof(cmd), "%s\r", cmd_wo_cr);

    if (pdv_serial_write(pdv_p, cmd, (int)strlen(cmd)) != 0)
    {
        daoError("pdv_serial_write failed for '%s'\n", cmd_wo_cr);
        return DAO_ERROR;
    }

    if (lj_wait_ack(ack_timeout_ms) != 0)
        daoWarning("No ACK for '%s' (continuing)\n", cmd_wo_cr);

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
                daoInfo("New Serial Command: '%s'\n", user);

                if (user[0] != '@')
                    daoWarning("Little Joe expects '@XXX ...' commands (got '%s')\n", user);

                lj_drain_serial();
                (void)lj_send_cmd(user, 800);

                char rsp[1024];
                rsp[0] = '\0';
                (void)lj_read_text(rsp, sizeof(rsp), 250);
                if (rsp[0] != '\0')
                {
                    int L = (int)strlen(rsp);
                    if (L > 0 && rsp[L-1] != '\n')
                        daoInfo("RCL reply: %s\n", rsp);
                    else
                        daoInfo("RCL reply: %s", rsp);
                }


                int n = (int)strlen(rsp);
                if (n > 1023) n = 1023;
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

    /* EDT timeout */
    pdv_set_timeout(pdv_p, 1000);
    pdv_multibuf(pdv_p, 4);
    pdv_flush_fifo(pdv_p);
    /* Start continuous acquisition on grabber */
    pdv_start_images(pdv_p, 8);

    void *captured_image = NULL;

    /* Optional uint8->uint16 conversion buffer */
    static unsigned short *tmp16 = NULL;
    static int tmp16sz = 0;

    /* Robust FPS: count frames over 1 second using CLOCK_MONOTONIC */
    double t0 = now_ms_monotonic();
    double t_last_print = t0;
    unsigned long frames = 0;

    while (!end)
    {
        double ta = now_ms_monotonic();
        //pdv_start_image(pdv_p);
        captured_image = pdv_wait_image(pdv_p);
        double tb = now_ms_monotonic();

        if (captured_image == NULL)
        {
            daoWarning("pdv_image timeout (no frame)\n");
            continue;
        }
        pdv_start_image(pdv_p);
        /* Copy to SHM */
        if (gBytesPerPixel == 2)
        {
            daoShmImage2Shm((unsigned short*)captured_image, gPixels, &shm[0]);
        }
        else if (gBytesPerPixel == 1)
        {
            if (tmp16sz != gPixels)
            {
                free(tmp16);
                tmp16 = (unsigned short*)calloc((size_t)gPixels, sizeof(unsigned short));
                tmp16sz = gPixels;
            }
            unsigned char *u8 = (unsigned char*)captured_image;
            for (int i = 0; i < gPixels; i++) tmp16[i] = (unsigned short)u8[i];
            daoShmImage2Shm(tmp16, gPixels, &shm[0]);
        }
        else
        {
            daoWarning("Unsupported bytes/pixel=%d (depth=%d bits)\n", gBytesPerPixel, gDepthBits);
        }

        double tc = now_ms_monotonic();
        frames++;

        /* Print once per ~1 second */
        double now = tc;
        if (now - t_last_print >= 1000.0)
        {
            double dt = now - t0;
            double fps = (dt > 0.0) ? (1000.0 * (double)frames / dt) : 0.0;

            /* time breakdown (ms) for sanity */
            double dt_img_ms  = tb - ta;
            double dt_copy_ms = tc - tb;

            printf("\r fps=%.1f  pdv_image=%.3fms  copy=%.3fms   ",
                   fps, dt_img_ms, dt_copy_ms);
            fflush(stdout);

            /* reset window */
            t_last_print = now;
            t0 = now;
            frames = 0;
        }
    }

    printf("\n");
    daoInfo("EXITING ACQ LOOP\n");
    int exit_code = DAO_SUCCESS;
    pthread_exit(&exit_code);
}

/*==========================================================================*/
/* Attach or create SHM sized to EDT geometry */
static int attach_or_create_shm()
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
        size[0] = (uint32_t)gHeight; /* rows */
        size[1] = (uint32_t)gWidth;  /* cols */

        int dtype = (gBytesPerPixel == 1) ? _DATATYPE_UINT8 : _DATATYPE_UINT16;

        rc = daoShmImageCreate(&shm[0], shmName, 2, size, dtype, 1, 0);
        if (rc != DAO_SUCCESS)
        {
            daoError("Failed to create SHM '%s'\n", shmName);
            return DAO_ERROR;
        }

        daoInfo("Created SHM '%s' size=%ux%u dtype=%s\n",
                shmName, size[1], size[0], (dtype == _DATATYPE_UINT16) ? "uint16" : "uint8");
        return DAO_SUCCESS;
    }

    int shmRows = (int)shm[0].md[0].size[0];
    int shmCols = (int)shm[0].md[0].size[1];

    if (shmCols != gWidth || shmRows != gHeight)
    {
        daoError("SHM size mismatch: shm=%dx%d but EDT=%dx%d\n",
                 shmCols, shmRows, gWidth, gHeight);
        daoError("Fix: create SHM with correct size or use per-program shm name.\n");
        return DAO_ERROR;
    }

    return DAO_SUCCESS;
}

/*==========================================================================*/
static int realTimeLoop()
{
    /* Clean shutdown on Ctrl-C and kill */
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

    /* Initialize camera with config */
    if (pdv_initcam(pdv_p, dd_p, edtUnit, &edtinfo, configFile, NULL, 0) != 0)
    {
        daoError("Could not initialize camera.\n");
        pdv_close(pdv_p);
        pdv_p = NULL;
        free(dd_p);
        return DAO_ERROR;
    }

    daoInfo("Camera successfully initialized.\n");

    /* Serial settings */
    pdv_set_baud(pdv_p, ljBaud);

    /* Drain any chatter */
    lj_drain_serial();

    /* Select Little Joe personality using @RCL n */
    {
        char cmd[64];

        /* Stop first (safe) */
        (void)lj_send_cmd("@SEQ 0", 800);
        usleep(50000);
        lj_drain_serial();

        snprintf(cmd, sizeof(cmd), "@RCL %d", ljPersonality);
        daoInfo("Sending %s\n", cmd);
        (void)lj_send_cmd(cmd, 800);

        /* Optional: read text reply (nice for logs) */
        {
            char rsp[256];
            rsp[0] = '\0';
            (void)lj_read_text(rsp, sizeof(rsp), 200);
            if (rsp[0] != '\0')
                daoInfo("RCL reply: %s", rsp);
        }

        usleep(50000);
        lj_drain_serial();
    }

    /* Start acquisition on camera if requested */
    if (ljStartOnLaunch)
    {
        daoInfo("Sending @SEQ 1\n");
        (void)lj_send_cmd("@SEQ 1", 800);
    }
    char rsp[256] = {0};
    (void)lj_read_text(rsp, sizeof(rsp), 200);
    daoInfo("SEQ reply: %s\n", rsp[0] ? rsp : "(none)");

    /* Geometry from EDT (grabber truth) */
    gWidth = pdv_get_width(pdv_p);
    gHeight = pdv_get_height(pdv_p);
    gDepthBits = pdv_get_depth(pdv_p);
    gBytesPerPixel = (gDepthBits + 7) / 8;
    gPixels = gWidth * gHeight;

    daoInfo("Active EDT geometry: %dx%d depth=%d bits => %d bytes/pixel\n",
            gWidth, gHeight, gDepthBits, gBytesPerPixel);

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

    /* Stop camera (best effort) */
    daoInfo("Sending @SEQ 0\n");
    lj_drain_serial();
    (void)lj_send_cmd("@SEQ 0", 800);
    usleep(50000);
    lj_drain_serial();

    pdv_close(pdv_p);
    pdv_p = NULL;
    free(dd_p);

    return DAO_SUCCESS;
}

/*==========================================================================*/
static void DecodeArgs(int argc, char **argv)
{
    char *str;
    int a1;

    argv += 1; argc -= 1;

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
                argv += 1; argc -= 1;
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
    int RT_priority = 93; /* 0-99 */
    struct sched_param schedpar;

    schedpar.sched_priority = RT_priority;
    sched_setscheduler(0, SCHED_FIFO, &schedpar);

    daoLogLevel = 1;
    sArgv0 = *argv;

    DecodeArgs(argc, argv);

    return DAO_SUCCESS;
}
/*==========================================================================*/
