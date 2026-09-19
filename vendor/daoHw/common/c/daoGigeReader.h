#ifndef DAO_GIGE_READER_H_
#define DAO_GIGE_READER_H_

#include <stdlib.h>
#include <stdint.h>
#include <stdio.h>
#include <inttypes.h>
#include <unistd.h>
#include <errno.h>

#include <daoEndianUtils.h>

#ifdef __linux__
#include <sched.h>
#include <pthread.h>
#endif

#ifdef __APPLE__
// optionally include <mach/thread_policy.h> for similar scheduling
#endif

#define GEV_STATUS_SUCCESS              0x0000
#define GEV_STATUS_PACKET_UNAVAILABLE   0x8000
#define GEV_STATUS_DATA_OVERRUN         0x8001

#define GEV_FORMAT_LEADER               0x01
#define GEV_FORMAT_TRAILER              0x02
#define GEV_FORMAT_PAYLOAD              0x03

#define GEV_FORMAT_LEADER_V2            0x81
#define GEV_FORMAT_TRAILER_V2           0x82
#define GEV_FORMAT_PAYLOAD_V2           0x83

#define GEV_FORMAT_MONO                 0x0100
#define GEV_PAYLOAD_IMAGE               0x0001


#define BUFSIZE 9000 // jumbo


//TODO: need to add some controls for stopping the thread and some affinity/prority support.

void daoGigeReaderV1(const char * serverhost, const int portno, const char * file, uint32_t width, uint32_t height, uint32_t MTU);


typedef struct
{
    uint16_t    * status;           // 2 : 0  - 2  
    uint16_t    * block_id;         // 2 : 2  - 4 
    uint8_t     * format;           // 1 : 4  - 5 
    uint32_t    * packet_id;        // 3 : 5  - 8
    uint8_t     * field_info;       // 1 : 8  - 10 // 1 byte plus 1 byte gap
    uint16_t    * payload_type;     // 2 : 10 - 12
    uint64_t    * timestamp;        // 8 : 12 - 20
    uint32_t    * pixel_format;     // 4 : 20 - 24
    uint32_t    * width;            // 4 : 24 - 28
    uint32_t    * height;           // 4 : 28 - 32
    uint32_t    * x_offset;         // 4 : 32 - 36
    uint32_t    * y_offset;         // 4 : 36 - 40
    uint32_t    * x_padding;        // 4 : 40 - 44
    uint32_t    * y_padding;        // 4 : 44 - 48
    void        * payload;          // from 8 
} GigeHeaderV1;

inline
uint16_t*   getStatusV1(char* buffer)
{
    return (uint16_t*)buffer;
}

inline
uint16_t*   getBlockIdV1(char* buffer)
{
    return (uint16_t*)(buffer + 2);
}

inline
uint8_t*    getFormatV1(char* buffer)
{
    return (uint8_t*)(buffer + 4);
}
// Todo::actully a 24 bit number will check later
inline
uint32_t*   getPacketIdV1(char* buffer, uint32_t * recvPacket)
{
    convert_24bit_to_uint32(buffer+5, recvPacket);
    return recvPacket;
}

inline
uint8_t*     getFieldInfoV1(char* buffer)
{
    return (uint8_t*)(buffer + 8);
}

inline
uint16_t*     getPayloadTypeV1(char* buffer)
{
    return (uint16_t*)(buffer + 10);
}

inline
uint64_t*   getTimestampV1(char* buffer)
{
    return (uint64_t*)(buffer + 12);
}

inline
uint32_t*   getPixelFormatV1(char* buffer)
{
    return (uint32_t*)(buffer + 20);
}

inline
uint32_t*   getWidthV1(char* buffer)
{
    return (uint32_t*)(buffer + 24);
}

inline
uint32_t*   getHeightV1(char* buffer)
{
    return (uint32_t*)(buffer + 28);
}

inline
uint32_t*   getXOffsetV1(char* buffer)
{
    return (uint32_t*)(buffer + 32);
}

inline
uint32_t*   getYOffsetV1(char* buffer)
{
    return (uint32_t*)(buffer + 36);
}

inline
uint16_t*   getXPaddingV1(char* buffer)
{
    return (uint16_t*)(buffer + 40);
}

inline
uint16_t*   getYPaddingV1(char* buffer)
{
    return (uint16_t*)(buffer + 42);
}
// only if format is GEV_FORMAT_PAYLOAD
inline
void*       getPayloadV1(char* buffer)
{
    return (void*)(buffer + 8);
}


void daoGigeReaderV2(const char * serverhost, const int portno, const char * file, uint32_t width, uint32_t height, uint32_t MTU);

// TODO: modulize the header to account for changes in V2
typedef struct {
    uint16_t status;        // 2 : 0  - 2
    uint16_t flags;         // 2 : 2  - 4
    uint8_t format;         // 1 : 4  - 5
    void *   padding;       // 3 : 5  - 8   // 3 bytes of zeros
    uint64_t block_id;      // 8 : 8  - 16
    uint32_t packet_id;     // 4 : 16 - 20
    uint8_t  field_info;    // 1 : 20 - 21
    void *   field_pad;     // 1 : 21 - 22 // 1 byte of zeroing
    uint16_t payload_type;  // 2 : 22 - 24
    uint64_t timestamp;     // 8 : 24 - 32
    uint32_t pixel_format;  // 4 : 32 - 36 
    uint32_t width;         // 4 : 36 - 40
    uint32_t height;        // 4 : 40 - 44
    uint32_t x_offset;      // 4 : 44 - 48
    uint32_t y_offset;      // 4 : 48 - 52
    uint32_t x_padding;     // 4 : 52 - 56
    uint32_t y_padding;     // 4 : 56 - 60
    void * payload;         // * -> from 20 
} GigeHeaderV2;


inline
uint16_t*   getStatusV2(char* buffer)
{
    return (uint16_t*)(buffer);
}

inline
uint16_t*   getFlagsV2(char* buffer)
{
    return (uint16_t*)(buffer + 2);
}

inline
uint8_t*    getFormatV2(char* buffer)
{
    return (uint8_t*)(buffer + 4);
}

inline
uint64_t*   getBlockIdV2(char* buffer)
{
    return (uint64_t*)(buffer + 8);
}

inline
uint32_t*   getPacketIdV2(char* buffer)
{
    return (uint32_t*)(buffer + 16);
}

inline
uint8_t*     getFieldInfoV2(char* buffer)
{
    return (uint8_t*)(buffer + 20);
}

inline
uint8_t*     getPayloadTypeV2(char* buffer)
{
    return (uint8_t*)(buffer + 22);
}


inline
uint64_t*   getTimestampV2(char* buffer)
{
    return (uint64_t*)(buffer + 24);
}

inline
uint32_t*   getPixelFormatV2(char* buffer)
{
    return (uint32_t*)(buffer + 32);
}

inline
uint32_t*   getWidthV2(char* buffer)
{
    return (uint32_t*)(buffer + 36);
}

inline
uint32_t*   getHeightV2(char* buffer)
{
    return (uint32_t*)(buffer + 40);
}

inline
uint32_t*   getXOffsetV2(char* buffer)
{
    return (uint32_t*)(buffer + 44);
}

inline
uint32_t*   getYOffsetV2(char* buffer)
{
    return (uint32_t*)(buffer + 48);
}

inline
uint32_t*   getXPaddingV2(char* buffer)
{
    return (uint32_t*)(buffer + 52);
}

inline
uint32_t*   getYPaddingV2(char* buffer)
{
    return (uint32_t*)(buffer + 56);
}
// only if format is GEV_FORMAT_PAYLOAD
inline
void*       getPayloadV2(char* buffer)
{
    return (void*)(buffer + 20);
}


char * bytes_to_hex_string(void *buffer, int length);

void printHeaderV1(void * buffer);
void printHeaderV2(void * buffer);

void set_real_time_scheduling_and_cpu_affinity(int priority, int cpu);
// ssize_t busy_wait_recvfrom(int sockfd, void *buf, size_t len, int flags, struct sockaddr *src_addr, socklen_t *addrlen);

#endif // READER_HPP


// 
//
// 2: 0 - 2    00 00       // Status
// 2: 2 - 4    00 00       // flags
// 1: 4 - 5    81          // format    
// 3: 5 - 8    00 00 00    // pad
// 8: 8 - 16   00 00 00 00 00 00 00 01 // block id
// 4: 16- 20   00 00 00 00 // packet id is correct

// 00 00 // field info 
// 00 01 // payload type

// 00 00 0a e0 85 0f 01 58
// 01 10 00 05 00 00 02 80 00 00 02 00 00 00 00 00
// 00 00 00 00 00 00 00 00
