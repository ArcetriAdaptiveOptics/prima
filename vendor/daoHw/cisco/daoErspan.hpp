/**
 * @ Author: Thomas N. Davies
 * @ Company: Centre for Advanced Instrumentation, Durham University
 * @ Contact: thomas.n.davies@durham.ac.uk
 * @ Create Time: 2025-11-19 15:18:48
 * @ Description: Header library to capture, filter and parse ErspanV3 stream.
 */

#ifndef DAO_ERSPAN_HPP
#define DAO_ERSPAN_HPP

#include <unordered_map>
#include <daoLog.hpp>
#include <functional>
#include <stdexcept>
#include <string.h>
#include <memory>

#include <sys/socket.h>
#include <arpa/inet.h>
#include <net/if.h>
#include <linux/if_packet.h>
#include <linux/if_ether.h>
#include <linux/filter.h>
#include <netinet/ip.h>

/*  Determines the maximum number of bytes retained from
    an Erspan packet's origin payload when the packet
    is passed to the registered handler.

    Define before including this header library
    to specify a custom value to be used.
*/
#ifndef DAO_ERSPAN_RETENTION
#define DAO_ERSPAN_RETENTION    200
#endif


// Erspan related masks.
#define ERSPAN_MASK_PLATFORM_DATA   ~(0xFCULL << 58)
#define ERSPAN_MASK_PLATFORM        0xFC
#define ERSPAN_MASK_SUBHEADER       0x01
#define ERSPAN_MASK_STREAM          0x3FF
#define ERSPAN_MASK_VLAN            0xFFF
#define ERSPAN_MASK_FT              0x7C

// Max packet size (in bytes).
#define MAX_PACKET_SIZE             0xFFFF

// Macro for dropping packets during processing.
#define PKT_DROP(expr, msg, logger) do {if(expr) { logger.Trace("Dropped packet: " msg); return; }} while(false)

namespace Dao
{
    namespace Erspan
    {
        /**
         * @brief Contains a summary of a parsed Erspan packet.
         */
        struct Packet_Summary
        {
            struct
            {
                uint64_t timestamp;
            } Erspan;

            struct
            {
                std::string src;
                std::string dest;
                uint8_t protocol;
                size_t payloadFullLen;
                std::byte payloadSample[DAO_ERSPAN_RETENTION];
            } IP;
        };

        /**
         * @brief Implements raw packet capture and processing of ErspanV3 packets
         * into summaries that are then handed off to the provided packet
         * handler.
         */
        class Stream
        {
            public:
            using HandoffFunc_t = std::function<void(Packet_Summary &)>;
            using ID_t = uint16_t;

            Stream(Dao::Log::Logger &logger,
                const std::string &interface,
                const std::optional<ID_t> &streamID,
                const HandoffFunc_t &handoffFunc
            ) : logger_(logger), interfaceName_(interface),
                registeredPacketHandler(handoffFunc), streamID_(streamID)
            {
                initSocket();
            }

            ~Stream()
            {
                close(socket_);
            }

            /**
             * @brief Implements the core loop: packet receive -> process -> handoff.
             * The core loop ends and the method returns if the provided flag
             * is set.
             *
             * @param stopFlag Reference to an external stop flag.
             *
             * @return Returns true if the loop ended due to the provided flag being set,
             * or false if an error caused the loop to end.
             */
            bool begin(const bool &stopFlag)
            {
                while (!stopFlag) {
                    ssize_t packetSize = recv(socket_, packet_, MAX_PACKET_SIZE, MSG_TRUNC);
                    if (packetSize < 0) {
                        logger_.Critical("Socket receive failed: %s", strerror(errno));
                        return false;
                    }
                    assert(packetSize <= MAX_PACKET_SIZE);
                    parseRawPacket();
                }
                return true;
            }

            private:
            Dao::Log::Logger &logger_;
            std::string interfaceName_;
            HandoffFunc_t registeredPacketHandler;
            std::optional<ID_t> streamID_;
            std::byte packet_[MAX_PACKET_SIZE];
            int socket_;

            /**
             * @brief Creates a low-level network socket and configures it to retrieve
             * Ethernet packets off the specified interface as they enter the network
             * stack. A BPF filter is also applied to only accept packets that follow
             * an Ethernet->IPv4->GRE->___ structure.
             */
            void initSocket()
            {
                socket_ = socket(PF_PACKET, SOCK_RAW, 0);
                if (socket_ < 0) {
                    logger_.Critical("Socket creation failed: %s", strerror(errno));
                    throw std::runtime_error("Socket creation failed");
                }

                auto interfaceID = if_nametoindex(interfaceName_.c_str());
                if (!interfaceID) {
                    logger_.Critical("ID lookup failed for interface %s: %s", interfaceName_.c_str(), strerror(errno));
                    throw std::runtime_error("ID lookup failed for interface");
                }

                sockaddr_ll socketConfig {};
                socketConfig.sll_family = PF_PACKET;
                socketConfig.sll_ifindex = interfaceID;
                socketConfig.sll_protocol = htons(ETH_P_ALL);
                if (bind(socket_, (sockaddr *)&socketConfig, sizeof(sockaddr_ll)) < 0) {
                    logger_.Critical("Socket configuration failed: %s", strerror(errno));
                    throw std::runtime_error("Socket configuration failed");
                }

                sock_filter BPF[] = {
                    { 0x28, 0, 0, 0x0000000c },
                    { 0x15, 0, 3, 0x00000800 },
                    { 0x30, 0, 0, 0x00000017 },
                    { 0x15, 0, 1, 0x0000002f },
                    { 0x6, 0, 0, 0x00040000 },
                    { 0x6, 0, 0, 0x00000000 }
                };
                sock_fprog socketFilter {};
                socketFilter.filter = BPF;
                socketFilter.len = sizeof(BPF) / sizeof(sock_filter);
                if (setsockopt(socket_, SOL_SOCKET, SO_ATTACH_FILTER, &socketFilter, sizeof(sock_fprog)) < 0) {
                    logger_.Critical("Socket filter setup failed: %s", strerror(errno));
                    throw std::runtime_error("Socket filter setup failed");
                }

                logger_.Debug("Successfully created and configured network socket");
            }

            /**
             * @brief Parses raw GRE packet to detect and summarise valid ErspanV3 packets
             * which are then handed off to the user's registered processing handler.
             */
            void parseRawPacket()
            {
                /******************************
                        TUNNELING FRAME
                ******************************/
                // logger_.Debug("Processing packet..");
                const std::byte *head = packet_;

                //*  Ethernet
                // Note we assume an ethernet datalink
                // for the tunnel. 
                head += sizeof(ethhdr);

                //*  IPv4
                // Note the BPF filter ensures an IPv4 header follows.
                head += ((ip *)head)->ip_hl * sizeof(uint32_t);

                //*  GRE
                // BPF filter ensures a GRE header is next.
                // Note Erspan packets have a GRE header with a sequence field present only 
                // (see draft-foschiano-erspan-03).
                head += sizeof(__be16);
                uint16_t greProtocol = be16toh(*((__be16 *)head));
                PKT_DROP(greProtocol != ETH_P_ERSPAN2, "GRE tunnel header did not contain ErspanV3", logger_);
                head += 6;

                //*  ErspanV3
                // uint16_t vlan = *(__be16 *)head;
                // vlan = be16toh(vlan) & ERSPAN_MASK_VLAN;
                // logger_.Debug("vlan: %hu", vlan);
                head += sizeof(__be16);

                uint16_t stream = *(__be16 *)head;
                stream = be16toh(stream) & ERSPAN_MASK_STREAM;
                // logger_.Debug("stream: %hu (configured for stream %hu)", stream, streamID_ ? streamID_.value() : -1);
                PKT_DROP(streamID_ && streamID_.value() != stream, "Packet does not belong to specified Erspan stream", logger_);
                head += sizeof(__be16);

                uint32_t timestampLow = *(__be32 *)head; // lower 32-bits of 64-bit timestamp.
                timestampLow = be32toh(timestampLow);
                head += sizeof(__be32);
                head += sizeof(__be16); // skip SGT field.

                uint8_t frameType = (uint8_t(*head++) & ERSPAN_MASK_FT) >> 2; // Will be zero for an ethernet frame.
                PKT_DROP(frameType != 0, "Erspan does not contain Ethernet", logger_);

                bool hasSubheader = uint8_t(*head++) & ERSPAN_MASK_SUBHEADER;
                PKT_DROP(!hasSubheader, "Erspan has no subheader", logger_);

                uint8_t platform = (uint8_t(*head) & ERSPAN_MASK_PLATFORM) >> 2;
                PKT_DROP(platform != 7, "Erspan subheader platform is not supported", logger_);

                uint64_t timestampHigh = *(__be64 *)head; // high 32-bits of 64-bit timestamp.
                timestampHigh = be64toh(timestampHigh) & ERSPAN_MASK_PLATFORM_DATA;

                uint64_t timestamp = timestampHigh << 32 | timestampLow; // full 64-bit erspan packet timestamp.
                // logger_.Debug("timestamp: %llu", timestamp);
                head += sizeof(__be64);

                /******************************
                        ORIGIN FRAME
                ******************************/
                std::optional<Packet_Summary> summaryResult = produceSummary(head, timestamp);
                if (summaryResult) {
                    registeredPacketHandler(summaryResult.value());
                }
            }

            /**
             * @brief Produces a summary of an ErspanV3 packet and its
             * origin packet.
             *
             * @param originPacket Payload of ErspanV3 origin packet IPv4 payload.
             * @param packetTimestamp ErspanV3 timestamp of ErspanV3 packet.
             *
             * @return Summary of ErspanV3 packet, or an empty summary (std::nullopt)
             * if there was an issue during the summary process.
             */
            std::optional<Packet_Summary> produceSummary(
                const std::byte *originPacket,
                uint64_t packetTimestamp
            )
            {
             //*  Ethernet
                uint16_t ethProtocol = ((ethhdr *)originPacket)->h_proto;
                ethProtocol = be16toh(ethProtocol);
                originPacket += sizeof(ethhdr);
                if (ethProtocol != ETH_P_IP) {
                    logger_.Trace("No IPv4 in origin packet");
                    return std::nullopt;
                }

                //*  IPv4
                ip *ipv4 = (ip *)originPacket;
                size_t ipHeaderLen = ipv4->ip_hl * sizeof(uint32_t);
                size_t ipPayloadLen = ipv4->ip_len - ipHeaderLen;
                originPacket += ipHeaderLen;

                Packet_Summary packetSummary {};
                packetSummary.Erspan.timestamp = packetTimestamp;
                packetSummary.IP.src = inet_ntoa(ipv4->ip_src);
                packetSummary.IP.dest = inet_ntoa(ipv4->ip_dst);
                packetSummary.IP.protocol = ipv4->ip_p;
                packetSummary.IP.payloadFullLen = ipPayloadLen;
                std::memcpy(
                    packetSummary.IP.payloadSample,
                    originPacket,
                    DAO_ERSPAN_RETENTION >= ipPayloadLen ? ipPayloadLen : DAO_ERSPAN_RETENTION
                );

                return packetSummary;
            }
        };

    }; // namespace Erspan
}; // namespace Dao

#endif // DAO_ERSPAN_HPP


