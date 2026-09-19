
/*****************************************************************************
  DAO project
  David Barr
 *****************************************************************************/

/*==========================================================================*/
#ifndef DAO_IPORT_CONTROL_HPP
#define DAO_IPORT_CONTROL_HPP

#include <arv.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <string.h>
#include <unistd.h>

#include "dao.h" 
#include "daoTools.h" 


typedef int bool_t;
#ifndef TRUE
#define TRUE	1
#endif
#ifndef FALSE
#define FALSE	0
#endif

// Some defines from ARV and IPORT 
const guint32 EVENTDATA_CMD = 0x00c2;
const guint32 EVENTDATA_ACK = 0x00c3;

const guint32 MC_EVENT_CHANNEL = 0x00016000;

const guint32 MC_DESTINATION_PORT = 0x00000b00;
const guint32 MC_DESTINATION_ADDRESS = 0x00000b10;
const guint32 MC_TIMEOUT = 0x00000b14;
const guint32 MC_RETRY_COUNT = 0x00000b18;

const guint32 SERIAL_REGISTER = 0x40058000;

const guint32 REG_TEST_PATTERN = 0x00012550;
const guint32 TEST_PATTERN_ON  = 0x80000000;
const guint32 TEST_PATTERN_OFF = 0x00000000;


const guint32 STREAM_CHANNEL_0_DESTINTATION_IP = 0x00000d18;
const guint32 STREAM_CHANNEL_0_DESTINTATION_PORT = 0x00000d00;
const guint32 STREAM_CHANNEL_0_PACKET_SIZE = 0x00000d04;

/**
 * @brief Structure containing arguments for the event handling thread.
 *
 * The eventThreadArgs structure holds information such as the IP, port, exit flag, response buffer,
 * and an indicator for awaiting response in a thread-safe manner.
 */
struct eventThreadArgs
{
    GInetAddress *ip;        /**< Pointer to the IP address to listen on. */
    guint32 port;            /**< Port number to listen on. */
    volatile int exit;       /**< Exit flag for terminating the thread. */
    unsigned char response[1024];    /**< Buffer to store the response payload. */
    uint8_t awaiting;       /**< Indicator for awaiting response (thread-safe). */
};

/**
 * @brief Structure representing a decoded GigE Vision packet.
 *
 * The GigePacket structure holds raw data without any conversions, as well as
 * any useful converted data for decoding GigE Vision packets.
 */
struct GigePacket
{
    // raw data without any conversions
    unsigned char MessageKeyCode;                /**< Message Code */
    unsigned char FLAGS;                         /**< Flags 1 indicated acknowledge required */
    unsigned char Command[2];                    /**< Commands  */
    unsigned char PayloadLength[2];              /**< Payload length with padding */
    unsigned char RequestID[2];                  /**< Request ID needs to be used in acknowledgement */
    unsigned char DeviceSpecficId[2];            /**< DeviceSpecficId */
    unsigned char StreamChannelIndex[2];         /**< Channel Index for stream - */
    unsigned char BlockID[2];                    /**< Block ID - not used in this mode */
    unsigned char Timestamp[8];                  /**< Time stamp */
    unsigned char rLength[2];                    /**< real leangth embedded in the payload and padding */
    unsigned char Payload[1024];                 /**< Payload string */

    // this holds any useful converted data
    uint32_t payload_length;            /**< Payload length as reported by packet */
    uint32_t reported_length;           /**< Payload length as reported by value in padding (this is the length of the actual useful payload)  */
};

/**
 * @brief Structure representing an acknowledgment reply GigE Vision packet.
 *
 * The AckGigePacket structure holds information for creating an acknowledgment reply
 * for GigE Vision packets.
 */
struct AckGigePacket
{
    guint32 Status;         /**< Status code for the acknowledgment reply. */
    guint32 Ack;            /**< Acknowledgment code for the acknowledgment reply. */
    guint32 PayloadLength;  /**< Payload length for the acknowledgment reply. */
    guint32 RequestID;      /**< Request ID for the acknowledgment reply. */
    unsigned char reply[8];          /**< Raw reply data for the acknowledgment reply. */
};

// Convert a char array to byte order with correct padding to be sent to aravis.
unsigned char * buffer2Send(char * message, guint32 * rLength);


//Utility functions to send and send specific registers for event channels
void setMC_DESTINATION_PORT(ArvDevice * device, const guint32 port);
void setMC_DESTINATION_ADDRESS(ArvDevice * device, GInetAddress *interfaceAddress);

void setMC_TIMEOUT(ArvDevice * device, const guint32 timeout);
void setMC_RETRY_COUNT(ArvDevice * device, const guint32 retry_count);
void setMC_EVENTS_CHANNEL(ArvDevice * device);

// unset everything we set previously
void unsetMC_DESTINATION_PORT(ArvDevice * device);
void unsetMC_DESTINATION_ADDRESS(ArvDevice * device);
void unsetMC_TIMEOUT(ArvDevice * device);
void unsetMC_RETRY_COUNT(ArvDevice * device);
void unsetMC_EVENTS_CHANNEL(ArvDevice * device);

// thread to run the event communications
void * eventHandleThread(void * args);


// some utility
void swapByteOrderChar2(unsigned char * value);
uint32_t convertChar2ToUint32(unsigned char * value);
void replaceLineBreaks(unsigned char *str);

// Function to initialize an AckGigePacket
void initGigePacket(struct GigePacket *packet, const unsigned char *data, size_t length);
// Function to print GigePacket information
void printGigePacket(const struct GigePacket *packet);

// Function to initialize an AckGigePacket
void initAckGigePacket(struct AckGigePacket *packet, unsigned char *requestID);
// Function to print AckGigePacket information
void printAckGigePacket(const struct AckGigePacket *packet);


void configureStream(ArvDevice * device, guint32 port, guint32 packetSize, bool_t DoNotFragment,bool_t pixelEndian, bool_t FireTestPacket);

#endif