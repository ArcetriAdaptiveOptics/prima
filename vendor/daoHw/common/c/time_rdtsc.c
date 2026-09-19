#include "time_rdtsc.h"

#if defined(__APPLE__)

#include <mach/mach_time.h>

uint64_t rdtsc(void) {
    return mach_absolute_time();  // Works for both Intel and M1/M2
}

double get_cpu_frequency(void) {
    mach_timebase_info_data_t timebase;
    mach_timebase_info(&timebase);
    return 1e9 * ((double)timebase.denom / (double)timebase.numer);  // ticks/sec
}

#elif defined(__linux__)

#include <stdio.h>
#include <string.h>
#include <sched.h>

#if defined(__i386__)
uint64_t rdtsc(void) {
    uint64_t x;
    __asm__ volatile ("rdtsc" : "=A" (x));
    return x;
}
#elif defined(__x86_64__)
uint64_t rdtsc(void) {
    uint32_t lo, hi;
    __asm__ volatile ("rdtsc" : "=a" (lo), "=d" (hi));
    return ((uint64_t)hi << 32) | lo;
}
#else
uint64_t rdtsc(void) {
    return 0;
}
#endif

double get_cpu_frequency(void) {
    FILE* fp = fopen("/proc/cpuinfo", "r");
    if (!fp) return -1.0;

    char buffer[256];
    double freq = 0.0;
    while (fgets(buffer, sizeof(buffer), fp)) {
        if (strstr(buffer, "cpu MHz")) {
            sscanf(buffer, "cpu MHz : %lf", &freq);
            break;
        }
    }
    fclose(fp);
    return freq * 1e6;
}

#else
#error "Unsupported platform"
#endif

double cycles_to_seconds(uint64_t cycles, double frequency) {
    return cycles / frequency;
}
