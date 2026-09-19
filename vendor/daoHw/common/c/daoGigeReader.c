#include "daoGigeReader.h"
#include <string.h>
#include <stdint.h>
#include <inttypes.h>
#include <errno.h>

#include <netdb.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <netinet/in.h>
#include <arpa/inet.h>

#include <stdarg.h>
#include <stdio.h>


#include <daoEndianUtils.h>
#include <time_rdtsc.h>

#include "dao.h"
#include <sched.h>
#include <pthread.h>
#include <unistd.h>
#include <errno.h>


void daoGigeReaderV1(const char * serverhost, const int portno, const char * file, uint32_t width, uint32_t height, uint32_t MTU)
{

    uint32_t size = width * height;
    uint32_t sizeInBytes = size*2;
    IMAGE * shm = (IMAGE*) malloc(sizeof(IMAGE));
    daoShmShm2Img(file, &shm[0]);
    if(width != (uint32_t) shm[0].md[0].size[0] && height != (uint32_t) shm[0].md[0].size[1])
    {
        printf("Check size: expected %u x %u but got %u x %u\n", width, height, (uint32_t) shm[0].md[0].size[0], (uint32_t) shm[0].md[0].size[1]);
        return;
    }
    
    int sockfd; /* socket */

    socklen_t clientlen;           /* byte size of client's address */
    struct sockaddr_in serveraddr; /* server's addr */
    struct sockaddr_in clientaddr; /* client addr */
    char buf[BUFSIZE * 273];         /* message buf */
    int optval;                    /* flag value for setsockopt */
    int n;   

    /* create socket */
    sockfd = socket(AF_INET, SOCK_DGRAM,0);
    if (sockfd < 0)
    {
        daoError("Error: openeing socket\n");
        return;
    }
    
     /* setsockopt: Handy debugging trick that lets
     * us rerun the server immediately after we kill it;
     * otherwise we have to wait about 20 secs.
     * Eliminates "ERROR on binding: Address already in use" error.
     */
    optval = 1;
    setsockopt(sockfd, SOL_SOCKET, SO_REUSEADDR, (const void *)&optval, sizeof(int));
    // define buffer size of sock, bigger than buf
    int rcvbuf = 400 * width*height*2; /* receive buffer size */
    #ifdef __linux__
//    if (setsockopt(sockfd, SOL_SOCKET, SO_RCVBUFFORCE, &rcvbuf, sizeof(rcvbuf))) {
//        daoError("setsockopt(SO_RCVBUFFORCE) failed\n");
//        return;
//    }

    // SO_BUSY_POLL only on Linux
    int busy_poll = 1;
    setsockopt(sockfd, SOL_SOCKET, SO_BUSY_POLL, &busy_poll, sizeof(busy_poll));
    #else
    // macOS fallback to SO_RCVBUF
    if (setsockopt(sockfd, SOL_SOCKET, SO_RCVBUF, &rcvbuf, sizeof(rcvbuf))) {
        daoError("setsockopt(SO_RCVBUF) failed\n");
        return;
    }
    #endif

    /*
     * build the server's Internet address
     */
    /* gethostbyname: get the server's DNS entry */
    struct hostent *server;
    server = gethostbyname(serverhost);
    if (server == NULL)
    {
        daoError("ERROR, no such host as %s\n", serverhost);
        return;
    }

    bzero((char *)&serveraddr, sizeof(serveraddr));
    serveraddr.sin_family = AF_INET;
    bcopy((char *)server->h_addr,
          (char *)&serveraddr.sin_addr.s_addr, server->h_length);
    serveraddr.sin_port = htons((unsigned short)portno);

    /*
     * bind: associate the parent socket with a port
     */
    int ret = bind(sockfd, (struct sockaddr *)&serveraddr, sizeof(serveraddr));
    if ( ret < 0)
    {
        daoError("ERROR on binding % d\n", ret);
        fprintf(stderr,"ERROR on Binding %s\n", strerror(errno));
        return;
    }

    //set_real_time_scheduling_and_cpu_affinity(98, 5);

    // calculate the expected packet train via data and MTU size
    uint32_t expectedPackets = 0;
    if (sizeInBytes % MTU == 0)
    {
        expectedPackets = sizeInBytes / MTU;
    }
    else
    {
        expectedPackets = sizeInBytes / MTU + 1;
    }
    printf("expected packets %d\n", expectedPackets);

    uint32_t* positions = (uint32_t*) malloc(expectedPackets*sizeof(uint32_t));
    uint32_t* payloadSize = (uint32_t*) malloc(expectedPackets*sizeof(uint32_t));

    uint32_t perPacket = MTU/sizeof(uint16_t);
    for(uint32_t i = 0; i < expectedPackets; i++)
    {

        positions[i] =  i*perPacket;
        payloadSize[i] = perPacket;
    }
    payloadSize[expectedPackets-1] = size - (perPacket*(expectedPackets-1));

    // for(uint32_t i = 0; i < expectedPackets; i++)
    // {
    //     daoInfo("Pos[%u] - %u, payload[%u] - %u\n", i, positions[i], i, payloadSize[i]);
    // }
 
    // set frame Id 
    n = recvfrom(sockfd, buf, BUFSIZE, 0, (struct sockaddr *)&clientaddr, &clientlen);
    if (n < 0)
    {
        daoError("ERROR in recvfrom");
        return;
    }
    printHeaderV1(buf);

    uint16_t frame = *(getBlockIdV1(buf));
    // uint32_t frameId = *(getBlockIdV1(buf));

    // 
    unsigned buffer_count = 0;
    uint64_t start = rdtsc();
    unsigned framerate = 0;
    unsigned packet_count = 0;
    uint16_t expectedFrame = swapEndian_uint16(swapEndian_uint16(frame)+1);

    uint32_t recvPacket = 0;

    uint32_t missingPackets = 0;
    uint64_t frequency = get_cpu_frequency();

    printf("Starting Loop \n");
    while(1)
    {

        n = recvfrom(sockfd, buf, BUFSIZE, 0, (struct sockaddr *)&clientaddr, &clientlen);
        packet_count++;
        if (n < 0)
        {
            daoError("ERROR in recvfrom");
            return;
        }
        if (*(getFormatV1(buf)) == 0x001)
        {
            // recving leader
            //printf("recving leader\n");
            frame = *getBlockIdV1(buf);
            if (frame != expectedFrame)
            {
                printf("Frame received out of sequnece expected: Frame: %u recv: %u\n", expectedFrame, frame);
            }

            for(uint32_t packet = 0 ; packet < expectedPackets; packet++)
            {
                n = recvfrom(sockfd, buf, BUFSIZE, 0, (struct sockaddr *)&clientaddr, &clientlen);
                packet_count++;
                if (n < 0)
                {
                    daoError("ERROR in recvfrom");
                    return;
                }
                if (*(getFormatV1(buf)) == 0x003)
                {
                    // recving payload
                    recvPacket = *getPacketIdV1(buf, &recvPacket);
                    // printf("recving payload for pakcet %d - %u\n", packet, recvPacket);

                    // check that it is equal
                    if(recvPacket == packet+1)
                    {
void * payload = getPayloadV1(buf);
// if (packet == 0) {
//     printf("First packet: position=%u, payloadSize=%u, first bytes: %02x %02x %02x %02x %02x %02x %02x %02x\n",
//           positions[packet], payloadSize[packet],
//           ((unsigned char*)payload)[0], ((unsigned char*)payload)[1],
//           ((unsigned char*)payload)[2], ((unsigned char*)payload)[3],
//           ((unsigned char*)payload)[4], ((unsigned char*)payload)[5],
//           ((unsigned char*)payload)[6], ((unsigned char*)payload)[7]);
//}	
                        uint32_t A = swapEndian_int16(frame);
                        //void * payload = getPayloadV1(buf);
                        //copy payload
                        // printf("Received %d from Packet %u (%u): position: %u payload: %u\n",n, packet, recvPacket, positions[packet],payloadSize[packet]);
                        //  set cnt2+
                        //shm[0].md[0].cnt2 = frame;
                        daoShmImagePart2Shm(payload, payloadSize[packet], &shm[0], positions[packet],packet, expectedPackets, A);
                        // valuesRead+=nValues;
                    }
                    else
                    {
                        // work out where it should be copy payload there and rsync but flag missing packet
                        missingPackets++;
                        printf("missing packet %d\n", missingPackets);
                        packet =recvPacket-1;
                    }
                }
                else
                {
                    daoError("ERROR in recving payload for packet %d\n", packet);
                    // return;
                }
            }

            // recving trailer 
            n = recvfrom(sockfd, buf, BUFSIZE, 0, (struct sockaddr *)&clientaddr, &clientlen);
            packet_count++;
            if (n < 0)
            {
                daoError("ERROR in recvfrom");
                return;
            }
            if (*(getFormatV1(buf)) == 0x002)
            {
                // recving trailer
                // printf("\n");
                // printf("recving trailer\n\n");
                // printf("\n");
                shm[0].md[0].cnt2 = swapEndian_uint16(frame);
                daoShmImagePart2ShmFinalize(&shm[0]);
            }
            else
            {
               printf("Format: %u\n", *(getFormatV1(buf)));
               daoError("ERROR in recving trailer\n");
            }
            buffer_count++;
            missingPackets = 0;
            printf("\rcnt = %04d - cnt2 = %08d - framerate %04d Hz", buffer_count, packet_count, framerate);
            if(rdtsc() - start >= frequency)
            {
                // printf("\rcnt = %04d - framerate %04d Hz", buffer_count, framerate);
                framerate = buffer_count;
                buffer_count = 0;
                start = rdtsc();
            }
        }
        expectedFrame = swapEndian_uint16(swapEndian_uint16(frame)+1);

    }

    return;
}


void daoGigeReaderV2(const char * serverhost, const int portno, const char * file, uint32_t width, uint32_t height, uint32_t MTU)
{
    uint32_t size = width * height;
    uint32_t sizeInBytes = size;
    IMAGE * shm = (IMAGE*) malloc(sizeof(IMAGE));
    daoShmShm2Img(file, &shm[0]);
    if(width != (uint32_t) shm[0].md[0].size[0] && height != (uint32_t) shm[0].md[0].size[1])
    {
        printf("Check size: expected %u x %u but got %u x %u\n", width, height, (uint32_t) shm[0].md[0].size[0], (uint32_t) shm[0].md[0].size[1]);
        return;
    }
    
    int sockfd; /* socket */

    socklen_t clientlen;           /* byte size of client's address */
    struct sockaddr_in serveraddr; /* server's addr */
    struct sockaddr_in clientaddr; /* client addr */
    char buf[BUFSIZE * 2];         /* message buf */
    int optval;                    /* flag value for setsockopt */
    int n;   

    /* create socket */
    sockfd = socket(AF_INET, SOCK_DGRAM,0);
    if (sockfd < 0)
    {
        daoError("Error: openeing socket\n");
        return;
    }
    
     /* setsockopt: Handy debugging trick that lets
     * us rerun the server immediately after we kill it;
     * otherwise we have to wait about 20 secs.
     * Eliminates "ERROR on binding: Address already in use" error.
     */
    optval = 1;
    setsockopt(sockfd, SOL_SOCKET, SO_REUSEADDR, (const void *)&optval, sizeof(int));

    /*
     * build the server's Internet address
     */
    /* gethostbyname: get the server's DNS entry */
    struct hostent *server;
    server = gethostbyname(serverhost);
    if (server == NULL)
    {
        daoError("ERROR, no such host as %s\n", serverhost);
        return;
    }

    bzero((char *)&serveraddr, sizeof(serveraddr));
    serveraddr.sin_family = AF_INET;
    bcopy((char *)server->h_addr,
          (char *)&serveraddr.sin_addr.s_addr, server->h_length);
    serveraddr.sin_port = htons((unsigned short)portno);

    /*
     * bind: associate the parent socket with a port
     */
    int ret = bind(sockfd, (struct sockaddr *)&serveraddr, sizeof(serveraddr));
    if ( ret < 0)
    {
        daoError("ERROR on binding % d\n", ret);
        fprintf(stderr,"ERROR on Binding %s\n", strerror(errno));
        return;
    }
    // define buffer size of sock, bigger than buf
    int rcvbuf = 1000 * width*height; /* receive buffer size */
    if (setsockopt(sockfd, SOL_SOCKET, SO_RCVBUF, &rcvbuf, sizeof rcvbuf))
    {
        daoError("setsockopt(s,SOL_SOCKET,SO_RCVBUF)\n");
        return;
    }  /* message byte size */

    // calculate the expected packet train via data and MTU size
    uint32_t expectedPackets = 0;
    if (sizeInBytes % MTU == 0)
    {
        expectedPackets = sizeInBytes / MTU;
    }
    else
    {
        expectedPackets = sizeInBytes / MTU + 1;
    }
    printf("expected packets %d\n", expectedPackets);

    uint32_t* positions = (uint32_t*) malloc(expectedPackets*sizeof(uint32_t));
    uint32_t* payloadSize = (uint32_t*) malloc(expectedPackets*sizeof(uint32_t));

    uint32_t perPacket = MTU/sizeof(uint8_t);
    for(uint32_t i = 0; i < expectedPackets; i++)
    {

        positions[i] =  i*perPacket;
        payloadSize[i] = perPacket;
    }
    payloadSize[expectedPackets-1] = size - (perPacket*(expectedPackets-1));

    // for(uint32_t i = 0; i < expectedPackets; i++)
    // {
    //     daoInfo("Pos[%u] - %u, payload[%u] - %u\n", i, positions[i], i, payloadSize[i]);
    // }
 
    // set frame Id 
    n = recvfrom(sockfd, buf, BUFSIZE, 0, (struct sockaddr *)&clientaddr, &clientlen);
    if (n < 0)
    {
        daoError("ERROR in recvfrom");
        return;
    }
    printHeaderV2(buf);

    uint64_t frame = *(getBlockIdV2(buf));
    // uint32_t frameId = *(getBlockIdV1(buf));

    // 
    unsigned buffer_count = 0;
    uint64_t start = rdtsc();
    unsigned framerate = 0;
    unsigned packet_count = 0;
    uint64_t expectedFrame = swapEndian_uint64(swapEndian_uint64(frame)+1);

    uint32_t recvPacket = 0;

    uint32_t missingPackets = 0;
    uint64_t frequency = get_cpu_frequency();

    printf("Starting Loop \n");
    while(1)
    {

        n = recvfrom(sockfd, buf, BUFSIZE, 0, (struct sockaddr *)&clientaddr, &clientlen);
        packet_count++;
        if (n < 0)
        {
            daoError("ERROR in recvfrom");
            return;
        }
        
        if (*(getFormatV2(buf)) == 0x81)
        {
            // recving leader
            frame = *getBlockIdV2(buf);
            //printf("recving leader for frame %" PRIu64 " \n", swapEndian_uint64(frame));
            
            if (frame != expectedFrame)
            {
                printf("\nFrame received out of sequnece expected: Frame: %llu recv: %llu\n", swapEndian_uint64(expectedFrame), swapEndian_uint64(frame));
            }

            for(uint32_t packet = 0 ; packet < expectedPackets; packet++)
            {
                n = recvfrom(sockfd, buf, BUFSIZE, 0, (struct sockaddr *)&clientaddr, &clientlen);
                packet_count++;
                if (n < 0)
                {
                    daoError("ERROR in recvfrom");
                    return;
                }
                if (*(getFormatV2(buf)) == 0x83)
                {
                    // recving payload
                    recvPacket = swapEndian_uint32(*getPacketIdV2(buf));
                    // printf("recving payload for packet %d - %u\n", packet, recvPacket);

                    // check that it is equal
                    if(recvPacket == packet+1)
                    {
                        uint64_t A = swapEndian_int64(frame);
                        void * payload = getPayloadV2(buf);
                        //copy payload
                        // printf("Received %d from Packet %u (%u): position: %u payload: %u\n",n, packet, recvPacket, positions[packet],payloadSize[packet]);
                        daoShmImagePart2Shm(payload, payloadSize[packet], &shm[0], positions[packet], packet, expectedPackets, A);
                        // valuesRead+=nValues;
                    }
                    else
                    {
                        // work out where it should be copy payload there and rsync but flag missing packet
                        missingPackets++;
                        printf("missing packet %d\n", missingPackets);
                        packet =recvPacket-1;
                    }
                }
                else
                {
                    daoError("ERROR in recving payload for packet %d\n", packet);
                    goto continue_loop;
                    //return;
                }
            }

            // recving trailer 
            n = recvfrom(sockfd, buf, BUFSIZE, 0, (struct sockaddr *)&clientaddr, &clientlen);
            packet_count++;
            if (n < 0)
            {
                daoError("ERROR in recvfrom");
                return;
            }
            if (*(getFormatV2(buf)) == 0x82)
            {
                // recving trailer
                // printf("\n");
                // printf("recving trailer\n\n");
                // printf("\n");
                
                shm[0].md[0].cnt2 = swapEndian_uint64(frame);
                daoShmImagePart2ShmFinalize(&shm[0]);
            }
            else
            {
               printf("Format: %u\n", *(getFormatV2(buf)));
               daoError("ERROR in recving trailer\n");
            }
            buffer_count++;
            printf("\rcnt = %04d - cnt2 = %08d - framerate %04d Hz", buffer_count, packet_count, framerate);
            if(rdtsc() - start >= frequency)
            {
                // printf("\rcnt = %04d - framerate %04d Hz", buffer_count, framerate);
                framerate = buffer_count;
                buffer_count = 0;
                start = rdtsc();
            }
        }
        expectedFrame = swapEndian_uint64(swapEndian_uint64(frame)+1);

    continue_loop:
        ; // placeholder to end label
    }

    return;
}

// Function to convert a byte array to a hex string (up to 16 bytes)
char * bytes_to_hex_string(void *buffer, int length)
{
    static char hex_string[33]; // Static for reusability, size accommodates 16 bytes

    // Input validation: check for null pointer and invalid length
    if (buffer == NULL || length <= 0 || length > 16)
    {
        return NULL;
    }

    // Clear the static buffer before each use to avoid unintended concatenation
    memset(hex_string, 0, sizeof(hex_string));

    // Convert each byte to hex representation using sprintf
    for (int i = 0; i < length; i++)
    {
        sprintf(hex_string + (i * 2), "%02x", ((unsigned char *)buffer)[i]);
    }

    return hex_string;
}


void printHeaderV1(void * buffer)
{
    uint32_t recv;
    uint16_t status         = *getStatusV1(buffer);          // 2 : 0  - 2
    uint16_t block_id       = *getBlockIdV1(buffer);         // 2 : 2  - 4
    uint8_t  format         = *getFormatV1(buffer);          // 1 : 4  - 5
    uint32_t packet_id      = *getPacketIdV1(buffer, &recv);  // 3 : 5  - 8 // copy into 4
    uint16_t field_info     = *getFieldInfoV1(buffer);       // 2 : 8  - 10 // 1 byte + 1 byte gap
    uint16_t payload_type   = *getPayloadTypeV1(buffer);     // 2 : 10 - 12
    uint64_t timestamp      = *getTimestampV1(buffer);       // 8 : 12 - 20
    uint32_t pixel_format   = *getPixelFormatV1(buffer);     // 4 : 20 - 24
    uint32_t width          = *getWidthV1(buffer);           // 4 : 24 - 28
    uint32_t height         = *getHeightV1(buffer);          // 4 : 28 - 32
    uint32_t x_offset       = *getXOffsetV1(buffer);         // 4 : 32 - 36
    uint32_t y_offset       = *getYOffsetV1(buffer);         // 4 : 36 - 40
    uint16_t x_padding      = *getXPaddingV1(buffer);        // 2 : 40 - 42
    uint16_t y_padding      = *getYPaddingV1(buffer);        // 2 : 42 - 44

    
    // working at the moment.
    printf("status:       %-10u - %10u  (%s)\n", status,          swapEndian_uint16(status),        bytes_to_hex_string(buffer,    2));
    printf("block_id:     %-10u - %10u  (%s)\n", block_id,        swapEndian_uint16(block_id),      bytes_to_hex_string(buffer+2,  2));
    printf("format:       %-10u - %10u  (%s)\n", format,          format,                           bytes_to_hex_string(buffer+4,  1));
    printf("packet_id:    %-10u - %10u  (%s)\n", packet_id,       swapEndian_uint32(packet_id),     bytes_to_hex_string(buffer+5,  3));
    printf("field_info:   %-10u - %10u  (%s)\n", field_info,      field_info,                       bytes_to_hex_string(buffer+8,  2));
    printf("payload_type: %-10u - %10u  (%s)\n", payload_type,    swapEndian_uint16(payload_type),  bytes_to_hex_string(buffer+10, 2));
    printf("timestamp:    %llu - %llu (%s)\n", timestamp,   swapEndian_uint64(timestamp),     bytes_to_hex_string(buffer+12, 8));
    printf("pixel_format: %-10u - %10u  (%s)\n", pixel_format,    swapEndian_uint32(pixel_format),  bytes_to_hex_string(buffer+20, 4));
    printf("width:        %-10u - %10u  (%s)\n", width,           swapEndian_uint32(width),         bytes_to_hex_string(buffer+24, 4));
    printf("height:       %-10u - %10u  (%s)\n", height,          swapEndian_uint32(height),        bytes_to_hex_string(buffer+28, 4));
    printf("x_offset:     %-10u - %10u  (%s)\n", x_offset,        swapEndian_uint32(x_offset),      bytes_to_hex_string(buffer+32, 4));
    printf("y_offset:     %-10u - %10u  (%s)\n", y_offset,        swapEndian_uint32(y_offset),      bytes_to_hex_string(buffer+36, 4));
    printf("x_padding:    %-10u - %10u  (%s)\n", x_padding,       swapEndian_uint16(x_padding),     bytes_to_hex_string(buffer+40, 2));
    printf("y_padding:    %-10u - %10u  (%s)\n", y_padding,       swapEndian_uint16(y_padding),     bytes_to_hex_string(buffer+42, 2));
}


void printHeaderV2(void * buffer)
{

    uint16_t status         = *getStatusV2(buffer);       // 2 : 0  - 2
    uint16_t flags          = *getFlagsV2(buffer);        // 2 : 2  - 4
    uint8_t format          = *getFormatV2(buffer);       // 1 : 4  - 5
    uint64_t block_id       = *getBlockIdV2(buffer);      // 8 : 8  - 16
    uint32_t packet_id      = *getPacketIdV2(buffer);     // 4 : 16 - 20
    uint8_t  field_info     = *getFieldInfoV2(buffer);    // 1 : 20 - 21
    uint16_t payload_type   = *getPayloadTypeV2(buffer);  // 2 : 22 - 24
    uint64_t timestamp      = *getTimestampV2(buffer);    // 8 : 24 - 32
    uint32_t pixel_format   = *getPixelFormatV2(buffer);  // 4 : 32 - 36 
    uint32_t width          = *getWidthV2(buffer);        // 4 : 36 - 40
    uint32_t height         = *getHeightV2(buffer);       // 4 : 40 - 44
    uint32_t x_offset       = *getXOffsetV2(buffer);      // 4 : 44 - 48
    uint32_t y_offset       = *getYOffsetV2(buffer);      // 4 : 48 - 52
    uint32_t x_padding      = *getXPaddingV2(buffer);     // 4 : 52 - 56
    uint32_t y_padding      = *getYPaddingV2(buffer);     // 4 : 56 - 60
    
    // working at the moment.
    printf("status:      %u - %u (%s)\n", status,         swapEndian_uint16(status), bytes_to_hex_string(buffer, 2));
    printf("flags:       %u - %u (%s)\n", flags,          swapEndian_uint16(flags),  bytes_to_hex_string(buffer+2, 2));
    printf("format:      %u - %u (%s)\n", format, format, bytes_to_hex_string(buffer+4, 1));
    printf("block_id:     %llu - %llu (%s)\n", block_id,  swapEndian_uint64(block_id),     bytes_to_hex_string(buffer+8,  8));
    printf("packet_id:    %u - %u (%s)\n", packet_id, swapEndian_uint32(packet_id),    bytes_to_hex_string(buffer+16, 4));


    printf("field_info:   %u - %u (%s)\n", field_info,   field_info,     bytes_to_hex_string(buffer+20, 2));
    printf("payload_type: %u - %u (%s)\n", payload_type, swapEndian_uint16(payload_type),  bytes_to_hex_string(buffer+22, 2));
    printf("timestamp:    %llu - %llu (%s)\n", timestamp,swapEndian_uint64(timestamp),     bytes_to_hex_string(buffer+24, 8));
    printf("pixel_format: %u - %u (%s)\n", pixel_format, swapEndian_uint32(pixel_format),  bytes_to_hex_string(buffer+32, 4));
    printf("width:        %u - %u (%s)\n", width, swapEndian_uint32(width),                bytes_to_hex_string(buffer+26, 4));
    printf("height:       %u - %u (%s)\n", height, swapEndian_uint32(height),              bytes_to_hex_string(buffer+40, 4));
    printf("x_offset:     %u - %u (%s)\n", x_offset, swapEndian_uint32(x_offset),          bytes_to_hex_string(buffer+44, 4));
    printf("y_offset:     %u - %u (%s)\n", y_offset, swapEndian_uint32(y_offset),          bytes_to_hex_string(buffer+48, 4));
    printf("x_padding:    %u - %u (%s)\n", x_padding, swapEndian_uint32(x_padding),        bytes_to_hex_string(buffer+52, 4));
    printf("y_padding:    %u - %u (%s)\n", y_padding, swapEndian_uint32(y_padding),        bytes_to_hex_string(buffer+56, 4));
}


void set_real_time_scheduling_and_cpu_affinity(int priority, int cpu) 
{
    #ifdef __linux__
        struct sched_param param;
        param.sched_priority = priority;
        if (pthread_setschedparam(pthread_self(), SCHED_FIFO, &param) != 0) 
        {
            perror("pthread_setschedparam");
            exit(EXIT_FAILURE);
        }
    
        cpu_set_t cpuset;
        CPU_ZERO(&cpuset);
        CPU_SET(cpu, &cpuset);
        if (pthread_setaffinity_np(pthread_self(), sizeof(cpu_set_t), &cpuset) != 0) 
        {
            perror("pthread_setaffinity_np");
            exit(EXIT_FAILURE);
        }
    
        printf("Real-time scheduling and CPU affinity set successfully for the current thread.\n");
    #else
        // Stub for macOS
        printf("Real-time scheduling and CPU affinity not supported on this platform\n");
        printf("priotity %d , cpu %d ignored\n", priority, cpu);
    #endif
}


// ssize_t busy_wait_recvfrom(int sockfd, void *buf, size_t len, int flags, struct sockaddr *src_addr, socklen_t *addrlen) {
//     ssize_t n;
//     while (1) 
//     {
//         n = recvfrom(sockfd, buf, len, flags, src_addr, addrlen);
//         if (n >= 0) 
//         {

//             return n;
//         } else if (errno != EAGAIN && errno != EWOULDBLOCK) {
//             // An error occurred
//             perror("recvfrom");
//             return -1;
//         }
//         // Busy wait
//         //usleep(1);
//     }
// }
