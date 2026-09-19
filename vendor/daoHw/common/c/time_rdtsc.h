#ifndef TIME_RDTSC_H
#define TIME_RDTSC_H

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>

// Platform-independent rdtsc declaration
uint64_t rdtsc(void);  // Always declared



double get_cpu_frequency(void);
double cycles_to_seconds(uint64_t cycles, double frequency);

#endif // TIME_RDTSC_H
