#include "daoIportControl.h"
#include "dao.h"
#include "daoTools.h"
#include <errno.h> 

/**
 * @brief Converts a char array to the correct format for sending via Aravis GigE Vision.
 *
 * This function takes a char array, pads it appropriately, and constructs a buffer
 * for communication with Aravis GigE Vision. The resulting buffer is formatted as required
 * for sending serial commands via the iport.
 *
 * @param message The input char array to be formatted.
 * @param rLength Pointer to a guint32 variable to store the length of the resulting buffer.
 * @return A dynamically allocated char array containing the formatted data. The caller is responsible for freeing the memory.
 *
 * @note The returned buffer must be freed using free() when it is no longer needed.
 */
unsigned char * buffer2Send(char * message, guint32 *rLength)
{
    size_t origLength = strlen(message);
    const char *charArray = message;
    size_t lengthInBytes = origLength * sizeof(char);
    daoDebug("Bytes: %zu\n", lengthInBytes);

    size_t front_pad = 8;
    size_t rear_pad = 1;
    size_t sit = origLength + front_pad + rear_pad;

    size_t remainder = sit % 4;
    if (remainder != 0) {
        rear_pad += 4 - remainder;
    }

    size_t totalLength = (front_pad + origLength + rear_pad) * sizeof(unsigned char);

    daoDebug("String length: %zu\n", origLength);
    daoDebug("Front pad:     %zu\n", front_pad);
    daoDebug("Rear pad:      %zu\n", rear_pad);
    daoDebug("Total   :      %zu\n", totalLength);

    *rLength = totalLength;

    unsigned char *buffer = (unsigned char *)malloc(totalLength);

    // Pad front end
    for (size_t i = 0; i < front_pad - 1; ++i) {
        buffer[i] = 0x00;
    }
    buffer[7] = origLength + 1;

    // Copy in message
    memcpy(buffer + front_pad, charArray, origLength);
    for (size_t i = 1; i < rear_pad; i++) {
        buffer[totalLength - i] = 0x00;
    }
    buffer[totalLength - rear_pad] = 0x0d;

    if(daoLogLevel>=2)
    {
        char hexString[totalLength * 2 + 1];
        for (size_t i = 0; i < totalLength; i++)
        {
            sprintf(hexString + i * 2, "%02x", buffer[i]);
        }
        daoDebug("%s\n", hexString);
    }
    return buffer;
}

/**
 * @brief Sets the destination port for the Aravis GigE Vision device's event channel.
 *
 * This function directly writes a specified port value to the specified register,
 * configuring the destination port for the Aravis GigE Vision device's event channel.
 *
 * @param device Pointer to the ArvDevice structure representing the GigE Vision device.
 * @param port The port value to set for the destination port.
 *
 * @note This function logs an error message if it fails to set the register.
 * @note Ensure that the ArvDevice pointer is valid before calling this function.
 */
void setMC_DESTINATION_PORT(ArvDevice * device, const guint32 port)
{
    GError *error = NULL;
    if(!arv_device_write_register(device, MC_DESTINATION_PORT, port, &error))
    {
        daoError("Unable to set register %s\n", "MC_DESTINATION_PORT");
    }
    daoInfo("Register %s (0x%08x) set to %u (0x%08x)\n", "MC_DESTINATION_PORT", MC_DESTINATION_PORT, port, port);
}

/**
 * @brief Sets the destination IP address for the Aravis GigE Vision device's event channel.
 *
 * This function converts the provided IP address string to a uint32 representation and
 * writes it to the MC_DESTINATION_ADDRESS register, configuring the destination IP address
 * for the Aravis GigE Vision device's event channel.
 *
 * @param device Pointer to the ArvDevice structure representing the GigE Vision device.
 * @param address The IP address as a string in dotted-decimal format (e.g., "192.168.1.1").
 *
 * @note This function logs an error message if it fails to set the register.
 * @note Ensure that the ArvDevice pointer is valid before calling this function.
 */
void setMC_DESTINATION_ADDRESS(ArvDevice * device, GInetAddress *interfaceAddress)
{

    const char reg[]= "MC_DESTINATION_ADDRESS";
    uint32_t interfaceAddressInt = daoToolsIp2Int(g_inet_address_to_string(interfaceAddress));
    daoDebug("interfaceAddress = %s (%u)\n", g_inet_address_to_string(interfaceAddress), interfaceAddressInt);

    GError *error = NULL;
    if(!arv_device_write_register(device, MC_DESTINATION_ADDRESS, interfaceAddressInt, &error))
    {
        daoError("Unable to set register %s\n", "MC_DESTINATION_ADDRESS");
    }
    daoDebug("Register %s (0x%08x) set to %u (0x%08x - %s)\n", reg , MC_DESTINATION_ADDRESS, interfaceAddressInt, interfaceAddressInt, g_inet_address_to_string(interfaceAddress));
}
  
/**
 * @brief Sets the timeout for receiving acknowledgments on the Aravis GigE Vision device's event channel.
 *
 * This function writes the specified timeout value to the MC_TIMEOUT register,
 * configuring the timeout for receiving acknowledgments on the Aravis GigE Vision device's event channel.
 *
 * @param device Pointer to the ArvDevice structure representing the GigE Vision device.
 * @param timeout The timeout value to set for acknowledgment reception.
 *
 * @note This function logs an error message if it fails to set the register.
 * @note Ensure that the ArvDevice pointer is valid before calling this function.
 */
void setMC_TIMEOUT(ArvDevice * device, const guint32 timeout)
{
    GError *error = NULL;
    if(!arv_device_write_register(device, MC_TIMEOUT, timeout,&error))
    {
        daoError("Unable to set register %s\n", "MC_TIMEOUT");
    }
    daoDebug("Register %s (0x%08x) set to %u (0x%08x)\n", "MC_TIMEOUT", MC_TIMEOUT, timeout, timeout);
}

/**
 * @brief Sets the number of times to resend events if no acknowledgment is received.
 *
 * This function writes the specified retry count value to the MC_RETRY_COUNT register,
 * configuring the number of times to resend events in case no acknowledgment is received
 * on the Aravis GigE Vision device's event channel.
 *
 * @param device Pointer to the ArvDevice structure representing the GigE Vision device.
 * @param retry_count The number of times to resend events.
 *
 * @note This function logs an error message if it fails to set the register.
 * @note Ensure that the ArvDevice pointer is valid before calling this function.
 */
void setMC_RETRY_COUNT(ArvDevice * device, const guint32 retry_count)
{
    GError *error = NULL;
    if(!arv_device_write_register(device, MC_RETRY_COUNT, retry_count, &error))
    {
        daoError("Unable to set register %s\n", "MC_RETRY_COUNT");
    }
    daoDebug("Register %s (0x%08x) set to %u (0x%08x)\n", "MC_RETRY_COUNT",MC_RETRY_COUNT, retry_count, retry_count);
}

/**
 * @brief Turns on the event channel on the Aravis GigE Vision device.
 *
 * This function writes a specific value (0x00000001) to the MC_EVENT_CHANNEL register,
 * enabling the event channel on the Aravis GigE Vision device.
 *
 * @param device Pointer to the ArvDevice structure representing the GigE Vision device.
 *
 * @note This function logs an error message if it fails to set the register.
 * @note Ensure that the ArvDevice pointer is valid before calling this function.
 */
void setMC_EVENTS_CHANNEL(ArvDevice * device)
{
    GError *error = NULL;
    if(!arv_device_write_register(device, MC_EVENT_CHANNEL, 0x00000001,&error))
    {
        daoError("Unable to set register %s\n", "MC_EVENT_CHANNEL");
    }
    daoDebug("Register %s (0x%08x) set to %u (0x%08x)\n", "MC_EVENT_CHANNEL", MC_EVENT_CHANNEL, 0x00000001, 0x00000001);
}

/**
 * @brief Unsets the destination port for the Aravis GigE Vision device's event channel.
 *
 * This function writes a value of 0x00000000 to the MC_DESTINATION_PORT register,
 * effectively unsetting the destination port for the Aravis GigE Vision device's event channel.
 *
 * @param device Pointer to the ArvDevice structure representing the GigE Vision device.
 *
 * @note This function logs an error message if it fails to unset the register.
 * @note Ensure that the ArvDevice pointer is valid before calling this function.
 */
void unsetMC_DESTINATION_PORT(ArvDevice * device)
{
    GError *error = NULL;

    if(!arv_device_write_register(device, MC_DESTINATION_PORT, 0x00000000,&error))
    {
        daoError("Unable to unset register %s\n", "MC_DESTINATION_PORT");
    }
    daoDebug("Register %s (0x%08x) unset to %u (0x%08x)\n", "MC_DESTINATION_PORT", MC_DESTINATION_PORT, 0x00000000, 0x00000000);
}

/**
 * @brief Unsets the destination IP address for the Aravis GigE Vision device's event channel.
 *
 * This function writes a value of 0x00000000 to the MC_DESTINATION_ADDRESS register,
 * effectively unsetting the destination IP address for the Aravis GigE Vision device's event channel.
 *
 * @param device Pointer to the ArvDevice structure representing the GigE Vision device.
 *
 * @note This function logs an error message if it fails to unset the register.
 * @note Ensure that the ArvDevice pointer is valid before calling this function.
 */
void unsetMC_DESTINATION_ADDRESS(ArvDevice * device)
{
    GError *error = NULL;
    if(!arv_device_write_register(device, MC_DESTINATION_ADDRESS, 0x00000000,&error))
    {
        daoError("Unable to unset register %s\n", "MC_DESTINATION_ADDRESS");
    }
    daoDebug("Register %s (0x%08x) unset to %u (0x%08x)\n", "MC_DESTINATION_ADDRESS", MC_DESTINATION_ADDRESS, 0x00000000, 0x00000000);
}

/**
 * @brief Unsets the timeout for receiving acknowledgments on the Aravis GigE Vision device's event channel.
 *
 * This function writes a value of 0x00000000 to the MC_TIMEOUT register,
 * effectively unsetting the timeout for receiving acknowledgments on the Aravis GigE Vision device's event channel.
 *
 * @param device Pointer to the ArvDevice structure representing the GigE Vision device.
 *
 * @note This function logs an error message if it fails to unset the register.
 * @note Ensure that the ArvDevice pointer is valid before calling this function.
 */
void unsetMC_TIMEOUT(ArvDevice * device)
{
    GError *error = NULL;
    if(!arv_device_write_register(device, MC_TIMEOUT, 0x00000000,&error))
    {
        daoError("Unable to unset register %s\n", "MC_TIMEOUT");
    }
    daoDebug("Register %s (0x%08x) unset to %u (0x%08x)\n", "MC_TIMEOUT", MC_TIMEOUT, 0x00000000, 0x00000000);
}

/**
 * @brief Unsets the number of times to resend events if no acknowledgment is received.
 *
 * This function writes a value of 0x00000000 to the MC_RETRY_COUNT register,
 * effectively unsetting the number of times to resend events on the Aravis GigE Vision device's event channel.
 *
 * @param device Pointer to the ArvDevice structure representing the GigE Vision device.
 *
 * @note This function logs an error message if it fails to unset the register.
 * @note Ensure that the ArvDevice pointer is valid before calling this function.
 */
void unsetMC_RETRY_COUNT(ArvDevice * device)
{
    GError *error = NULL;
    if(!arv_device_write_register(device, MC_RETRY_COUNT, 0x00000000,&error))
    {
        daoError("Unable to unset register %s\n", "MC_RETRY_COUNT");
    }
    daoDebug("Register %s (0x%08x) unset to %u (0x%08x)\n", "MC_RETRY_COUNT", MC_RETRY_COUNT, 0x00000000, 0x00000000);
}

/**
 * @brief Unsets the event channel on the Aravis GigE Vision device.
 *
 * This function writes a value of 0x00000000 to the MC_EVENT_CHANNEL register,
 * effectively turning off the event channel on the Aravis GigE Vision device.
 *
 * @param device Pointer to the ArvDevice structure representing the GigE Vision device.
 *
 * @note This function logs an error message if it fails to unset the register.
 * @note Ensure that the ArvDevice pointer is valid before calling this function.
 */
void unsetMC_EVENTS_CHANNEL(ArvDevice * device)
{
    GError *error = NULL;
    if(!arv_device_write_register(device, MC_EVENT_CHANNEL, 0x00000000,&error))
    {
        daoError("Unable to unset register %s\n", "MC_EVENT_CHANNEL");
    }
    daoDebug("Register %s (0x%08x) unset to %u (0x%08x)\n", "MC_EVENT_CHANNEL", MC_EVENT_CHANNEL, 0x00000000, 0x00000000);
}

/**
 * @brief Thread function to handle events on the specified IP and port.
 *
 * This thread function listens to the event channel on the specified IP and port,
 * processes received data, sends an acknowledgment, and stores the payload in a shared struct.
 *
 * @param args Pointer to the struct eventThreadArgs containing IP, port, and shared data.
 * @return NULL
 */
void * eventHandleThread(void * args)
{
    struct eventThreadArgs *threadArgs = (struct eventThreadArgs *)args;
    daoDebug("EventThread: %s:%u\n", g_inet_address_to_string(threadArgs->ip), threadArgs->port);

    // Create a UDP socket
    int sockfd = socket(AF_INET, SOCK_DGRAM, 0);
    if (sockfd == -1)
    {
        daoError("Error creating socket");
        pthread_exit(NULL);
    }


    struct timeval timeout;
    timeout.tv_sec = 0;
    timeout.tv_usec = 100000; // 100 ms TODO: make this configurable
    if (setsockopt(sockfd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) == -1)
    {
        daoError("Error setting socket receive timeout\n");
        close(sockfd);
        pthread_exit(NULL);
    }

    struct sockaddr_in serverAddr;
    memset(&serverAddr, 0, sizeof(serverAddr));
    serverAddr.sin_family = AF_INET;
    
    serverAddr.sin_addr.s_addr = inet_addr(g_inet_address_to_string(threadArgs->ip));
    serverAddr.sin_port = htons(threadArgs->port); //

    // Bind the socket to the address and port

    if (bind(sockfd, (struct sockaddr*)&serverAddr, sizeof(serverAddr)) == -1)
    {
        daoError("Error binding socket socket");
        close(sockfd);
        pthread_exit(NULL);
    }


    unsigned char buffer[1024];
    struct sockaddr_in clientAddr;
    socklen_t clientAddrLen = sizeof(clientAddr);

    while(threadArgs->exit==0)
    {
        ssize_t bytesRead = recvfrom(sockfd, buffer, sizeof(buffer), 0, (struct sockaddr*)&clientAddr, &clientAddrLen);
        if (bytesRead == -1)
        {
            if (errno == EAGAIN || errno == EWOULDBLOCK)
            {
                if(threadArgs->exit != 0)
                    break;
                continue;  // You can add other periodic checks here if needed
            }
            else
            {
                daoError("Error recieving data on event channel\n");
                break;  // Exit the loop on other errors
            }
            
        }
        else
        {
        // Get the source IP and port
            char clientIpStr[INET_ADDRSTRLEN];
            inet_ntop(AF_INET, &clientAddr.sin_addr, clientIpStr, INET_ADDRSTRLEN);
            uint16_t clientPort = ntohs(clientAddr.sin_port); 
            daoDebug("Bytes Recv:  %zd\n", bytesRead);
            daoDebug("Source IP:   %s\n", clientIpStr);
            daoDebug("Source port: %d\n", clientPort);

            struct GigePacket eventRecv;
            struct AckGigePacket eventAck;
            initGigePacket(&eventRecv, buffer, bytesRead);
            //printGigePacket(&eventRecv);
            initAckGigePacket(&eventAck, eventRecv.RequestID);
            //printAckGigePacket(&eventAck);
            sendto(sockfd, eventAck.reply, sizeof(eventAck.reply), 0, (struct sockaddr*)&clientAddr, clientAddrLen);

           

            memcpy(threadArgs->response, eventRecv.Payload, sizeof(char)*(eventRecv.reported_length + 1));
            threadArgs->awaiting = 1;
            
            // replaceLineBreaks(eventRecv.Payload);
            // daoDebug("payload: %s", eventRecv.Payload);
        }

    }
    // Close the socket
    close(sockfd);
    
    pthread_exit(NULL);
}

/**
 * @brief Swaps the byte order of a 2-byte char array.
 *
 * This function takes a 2-byte char array and swaps the byte order in-place.
 *
 * @param value Pointer to the 2-byte char array to swap the byte order.
 */
void swapByteOrderChar2(unsigned char * value)
{
    unsigned char tmp;
    tmp = value[0];
    value[0] = value[1];
    value[1] = tmp;
}

/**
 * @brief Converts a 2-byte char array to a uint32_t with byte order conversion.
 *
 * This function converts a 2-byte char array to a uint32_t, performing a byte order conversion.
 *
 * @param value Pointer to the 2-byte char array to convert.
 * @return The uint32_t value obtained by converting the input char array with byte order conversion.
 */
uint32_t convertChar2ToUint32(unsigned char * value)
{
    uint32_t convert;
    unsigned char copy[2];
    memcpy(copy,value,sizeof(copy));
    swapByteOrderChar2(copy);
    memcpy(&convert, copy, sizeof(copy));

    return convert;
}

/**
 * @brief Replaces line breaks with spaces in a null-terminated string.
 *
 * This function replaces newline characters ('\n') with spaces in the provided null-terminated string.
 *
 * @param str Pointer to the null-terminated string to process.
 */
void replaceLineBreaks(unsigned char *str)
{
    // for (size_t i = 0; i < strlen(str); i++) {
    //     if (str[i] == '\n') {
    //         str[i] = ' ';  // Replace newline with space
    //     }
    // }
}

/**
 * @brief Initializes a GigePacket structure with raw data from a GigE Vision packet.
 *
 * This function takes raw data and populates a GigePacket structure with decoded information.
 *
 * @param packet Pointer to the GigePacket structure to be initialized.
 * @param data Pointer to the raw data of the GigE Vision packet.
 * @param length The length of the raw data.
 */
void initGigePacket(struct GigePacket *packet, const unsigned char *data, size_t length)
{
    if (length >= 24)
    {
        packet->MessageKeyCode = data[0];
        packet->FLAGS = data[1];
        memcpy(packet->Command, data + 2, 2);
        memcpy(packet->PayloadLength, data + 4, 2);
        memcpy(packet->RequestID, data + 6, 2);
        memcpy(packet->DeviceSpecficId, data + 8, 2);
        memcpy(packet->StreamChannelIndex, data + 12, 2);
        memcpy(packet->BlockID, data + 14, 2);
        memcpy(packet->Timestamp, data + 16, 8);
        memcpy(packet->rLength, data+26, 2);


        size_t metadata_length = 28;
        packet->payload_length  =  ((uint32_t)packet->PayloadLength[0] << 8) | (uint32_t)packet->PayloadLength[1];
        packet->reported_length  =  ((uint32_t)packet->rLength[0] << 8) | (uint32_t)packet->rLength[1];


        daoDebug("Reported Payload length: %u (%02X %02X)\n",packet->payload_length, packet->PayloadLength[0],packet->PayloadLength[1]);
        daoDebug("In Payload length: %u (%02X %02X)\n",packet->reported_length, packet->rLength[0],packet->rLength[1]);
        memcpy(packet->Payload, data+metadata_length, sizeof(char)*(packet->reported_length));
        packet->Payload[packet->reported_length] = '\0';
        daoDebug("Payload: %s\n",packet->Payload);

    }
    else
    {
        // Handle error - not enough data for decoding
        daoError("Error: Insufficient data for decoding.\n");
        exit(EXIT_FAILURE);
    }
}

/**
 * @brief Prints information from a GigePacket structure.
 *
 * This function prints the decoded information from a GigePacket structure.
 *
 * @param packet Pointer to the GigePacket structure to be printed.
 */
void printGigePacket(const struct GigePacket *packet)
{
    daoInfo("MessageKeyCode: %x\n", packet->MessageKeyCode);
    daoInfo("FLAGS: %x\n", packet->FLAGS);
    daoInfo("Command: %x, %x\n", packet->Command[0], packet->Command[1]);
    daoInfo("PayloadLength: %x, %x\n", packet->PayloadLength[0], packet->PayloadLength[1]);
    daoInfo("RequestID: %x, %x\n", packet->RequestID[0], packet->RequestID[1]);
    daoInfo("DeviceSpecficId: %x, %x\n", packet->DeviceSpecficId[0], packet->DeviceSpecficId[1]);
    daoInfo("StreamChannelIndex: %x, %x\n", packet->StreamChannelIndex[0], packet->StreamChannelIndex[1]);
    daoInfo("BlockID: %x, %x\n", packet->BlockID[0], packet->BlockID[1]);
    char timestampStr[24];
    snprintf(timestampStr, 24, "%02x %02x %02x %02x %02x %02x %02x %02x",
             packet->Timestamp[0], packet->Timestamp[1], packet->Timestamp[2], packet->Timestamp[3],
             packet->Timestamp[4], packet->Timestamp[5], packet->Timestamp[6], packet->Timestamp[7]);
    daoInfo("Timestamp: %s\n", timestampStr);
    daoInfo("Payload: %s\n", packet->Payload);
}


/**
 * @brief Initializes an AckGigePacket structure with acknowledgment reply information.
 *
 * This function initializes an AckGigePacket structure with acknowledgment reply information.
 *
 * @param packet Pointer to the AckGigePacket structure to be initialized.
 * @param requestID Pointer to the Request ID for the acknowledgment reply.
 */
void initAckGigePacket(struct AckGigePacket *packet, unsigned char *requestID)
{
    packet->Status = 0x0000;
    packet->Ack = EVENTDATA_ACK;
    packet->PayloadLength = 0x0000;
    memcpy(&packet->RequestID, requestID, sizeof(packet->RequestID));
    // &packet->reply[2] = 0x00;
    // &packet->reply[3] = 0xc3;
    memcpy(packet->reply, &packet->Status, sizeof(packet->Status));
    memcpy(packet->reply + 3, &packet->Ack, sizeof(packet->Ack));
    memcpy(packet->reply + 4, &packet->PayloadLength, sizeof(packet->PayloadLength)); //TODO: investigate why +3 works when +2 doesn't????
    memcpy(packet->reply + 6, &packet->RequestID, sizeof(packet->RequestID));

}


/**
 * @brief Prints information from an AckGigePacket structure.
 *
 * This function prints the information from an AckGigePacket structure.
 *
 * @param packet Pointer to the AckGigePacket structure to be printed.
 */
void printAckGigePacket(const struct AckGigePacket *packet)
{
    daoInfo("Status:        %x\n", packet->Status);
    daoInfo("Ack:           %x\n", packet->Ack);
    daoInfo("PayloadLength: %x\n", packet->PayloadLength);
    daoInfo("RequestID:     %x\n", packet->RequestID);


    char hexString[8 * 2 + 1];
    for (size_t i = 0; i < 8; i++)
    {
        sprintf(hexString + i * 2, "%02x", packet->reply[i]);
    }
    daoInfo("Reply: %s\n", hexString);
}


int send_udp_payload(const char* destination_ip, int destination_port, const unsigned char* payload, size_t payload_length)
{
    int sockfd;
    struct sockaddr_in dest_addr;

    // Create UDP socket
    if ((sockfd = socket(AF_INET, SOCK_DGRAM, 0)) == -1)
    {
        perror("socket");
        return -1;
    }

    // Fill in destination information
    memset(&dest_addr, 0, sizeof(dest_addr));
    dest_addr.sin_family = AF_INET;
    dest_addr.sin_port = htons(destination_port);
    if (inet_pton(AF_INET, destination_ip, &dest_addr.sin_addr) <= 0)
    {
        perror("inet_pton");
        close(sockfd);
        return -1;
    }

    // Send payload
    ssize_t sent_bytes = sendto(sockfd, payload, payload_length, 0, (struct sockaddr*)&dest_addr, sizeof(dest_addr));
    if (sent_bytes == -1) {
        perror("sendto");
        close(sockfd);
        return -1;
    }

    printf("Sent %zd bytes to %s:%d\n", sent_bytes, destination_ip, destination_port);

    // Close socket
    close(sockfd);

    return 0;
}

void configureStream(ArvDevice * device,  guint32 port, guint32 packetSize, bool_t DoNotFragment, bool_t pixelEndian, bool_t FireTestPacket)
{
    GError *error = NULL;
    daoInfo("Configuring Stream\n");
    GInetAddress *interfaceAddress = g_inet_socket_address_get_address(G_INET_SOCKET_ADDRESS(arv_gv_device_get_interface_address(device)));
    uint32_t interfaceAddressInt = daoToolsIp2Int(g_inet_address_to_string(interfaceAddress));
    daoInfo("interfaceAddress = %s (%u)\n", g_inet_address_to_string(interfaceAddress), interfaceAddressInt);
    if(!arv_device_write_register(device, STREAM_CHANNEL_0_DESTINTATION_IP, interfaceAddressInt, &error))
    {
        daoError("Unable to set register %s\n", "STREAM_CHANNEL_0_DESTINTATION_IP");
    }
    daoInfo("Register %s (0x%08x) set to %u (0x%08x - %s)\n", "STREAM_CHANNEL_0_DESTINTATION_IP", STREAM_CHANNEL_0_DESTINTATION_IP, interfaceAddressInt, interfaceAddressInt, g_inet_address_to_string(interfaceAddress));

    error = NULL;
    if(!arv_device_write_register(device, STREAM_CHANNEL_0_DESTINTATION_PORT, port, &error))
    {
        daoError("Unable to set register %s\n", "STREAM_CHANNEL_0_DESTINTATION_PORT");
    }
    daoInfo("Register %s (0x%08x) set to %u (0x%04x)\n", "STREAM_CHANNEL_0_DESTINTATION_PORT",STREAM_CHANNEL_0_DESTINTATION_PORT, port, (unsigned char *)port);


    daoInfo("Setting packet Size to %u before bit modifcation.\n", packetSize);
    // setting bits to control the stream of pixels
    if(DoNotFragment == TRUE)
    {
        packetSize |= (1 << 30);    // This sets the do not fragment bit.
        daoInfo("In configure stream setting DoNotFragment to TRUE\n");
    }
    if(pixelEndian == TRUE)
    {
        packetSize |= (1 << 29);    // pixel endianess
        daoInfo("In configure stream setting pixelEndian to TRUE\n");
    }
    if(FireTestPacket == TRUE)
    {
        packetSize |= (1 << 31);    // fire test packet.
        daoInfo("In configure stream setting FireTestPacket to TRUE\n");
    }

    error = NULL;
    if(!arv_device_write_register(device, STREAM_CHANNEL_0_PACKET_SIZE, packetSize, &error))
    {
        daoError("Unable to set register %s\n", "STREAM_CHANNEL_0_PACKET_SIZE");
    }
    daoInfo("Register %s (0x%08x) set to %u (0x%04x)\n", "STREAM_CHANNEL_0_PACKET_SIZE",STREAM_CHANNEL_0_DESTINTATION_PORT, packetSize, (unsigned char *)packetSize);
    daoInfo("StreamConfigured\n");
}

void sendConfigByHand(uint16_t packetSize, uint8_t fireTest, uint8_t doNotFragment, uint8_t pixelEndian)
{
    unsigned char toSend[16];
    toSend[0] = 0x42;
    toSend[1] = 0x01;
    toSend[2] = 0x00;
    toSend[3] = 0x82;
    toSend[4] = 0x00;
    toSend[5] = 0x08;
    toSend[6] = 0xff;
    toSend[7] = 0x75;
    toSend[8] = 0x00;
    toSend[9] = 0x00;
    toSend[10]= 0x0d;
    toSend[11]= 0x04;
    toSend[12]= 0x40; // 0x40 for 010 0xC0 for 110
    toSend[13]= 0x00;
    toSend[14] = 0x23;
    toSend[15] = 0x10;


    char hexString[16 * 2 + 1];
    for (size_t i = 0; i < 16; i++)
    {
        sprintf(hexString + i * 2, "%02x", toSend[i]);
    }
    daoInfo("Reply: %s\n", hexString);
    send_udp_payload("192.168.60.65", 3956, toSend, sizeof(toSend));
}
