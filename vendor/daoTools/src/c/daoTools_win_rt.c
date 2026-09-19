/* POSIX RT stubs for MSVC builds of daoTools. */
#include <windows.h>
#include <errno.h>
#include <stdio.h>
#include <time.h>
#include <sched.h>
#include <unistd.h>

#define WIN_UNIX_EPOCH_GAP 11644473600ULL

int clock_gettime(int clk_id, struct timespec *t)
{
	FILETIME currentTime;
	(void)clk_id;
	GetSystemTimePreciseAsFileTime(&currentTime);
	long long hundredNanos =
		((long long)currentTime.dwLowDateTime) |
		(((long long)currentTime.dwHighDateTime) << 32);
	hundredNanos -= (long long)(WIN_UNIX_EPOCH_GAP * 10000000ULL);
	t->tv_sec = (time_t)(hundredNanos / 10000000LL);
	t->tv_nsec = (long)((hundredNanos % 10000000LL) * 100L);
	return 0;
}

int clock_nanosleep(int clock_id, int flags, const struct timespec *request, struct timespec *remain)
{
	struct timespec now;
	struct timespec delay;
	(void)remain;
	if (!request) {
		return EINVAL;
	}
	if (flags == TIMER_ABSTIME) {
		clock_gettime(clock_id, &now);
		delay.tv_sec = request->tv_sec - now.tv_sec;
		delay.tv_nsec = request->tv_nsec - now.tv_nsec;
		if (delay.tv_nsec < 0) {
			delay.tv_sec -= 1;
			delay.tv_nsec += 1000000000L;
		}
		if (delay.tv_sec < 0 || (delay.tv_sec == 0 && delay.tv_nsec <= 0)) {
			return 0;
		}
	} else {
		delay = *request;
	}
	{
		DWORD ms = (DWORD)(delay.tv_sec * 1000L + delay.tv_nsec / 1000000L);
		if (ms == 0) {
			ms = 1;
		}
		Sleep(ms);
	}
	return 0;
}

int sched_setscheduler(pid_t pid, int policy, const struct sched_param *param)
{
	(void)pid;
	(void)policy;
	(void)param;
	return 0;
}

int sched_getscheduler(pid_t pid)
{
	(void)pid;
	return SCHED_OTHER;
}

int sched_getparam(pid_t pid, struct sched_param *param)
{
	(void)pid;
	if (param) {
		param->sched_priority = 0;
	}
	return 0;
}

int sched_yield(void)
{
	SwitchToThread();
	return 0;
}

int sched_setaffinity(pid_t pid, size_t cpusetsize, cpu_set_t *mask)
{
	(void)pid;
	(void)cpusetsize;
	(void)mask;
	return 0;
}

int sched_getaffinity(pid_t pid, size_t cpusetsize, cpu_set_t *mask)
{
	(void)pid;
	(void)cpusetsize;
	(void)mask;
	return 0;
}

char *daoBaseGetTimeStamp(void)
{
	struct timespec curTime;
	static char currentTime[128];
	char buffer[80];
	int micro;
	clock_gettime(CLOCK_REALTIME, &curTime);
	micro = (int)((double)curTime.tv_nsec / 1000.0);
	strftime(buffer, sizeof(buffer), "%Y-%m-%d_%H:%M:%S", localtime(&curTime.tv_sec));
	sprintf(currentTime, "%s:%d", buffer, micro);
	return currentTime;
}
