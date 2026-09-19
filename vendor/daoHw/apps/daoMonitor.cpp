/**
 * @ Author: Thomas N. Davies
 * @ Company: Centre for Advanced Instrumentation, Durham University
 * @ Contact: thomas.n.davies@durham.ac.uk
 * @ Create Time: 2025-12-02 09:09:51
 * @ Description: Application to passively monitor AO RTC latency in real-time using ErspanV3.
 */

/******************************
  EXAMPLE CONFIGURATION FILE
******************************

     App_Configuration:
         Erspan_Clock_Resolution: 100e-12            // See your Cisco switch docs for erspan clock resolution (in seconds).
         Erspan_Stream_Interface: eno34              // Interface name receiving RTC Erspan traffic.
         Erspan_Stream: null                         // Erspan stream ID - null will process all Erspan streams present.
         Packet_Buffer_Limit: 1000                   // Packet buffer limit (in packets).
         Output_Location: /tmp/erspan_demo.im.shm    // Path to the desired shared memory for latency information to be written.
         Output_Scale_Factor: 1.0                    // Factor to scale latency values (in seconds) by, before writing out to shared memory.
         Include_Readout: true                       // Include readout latency and spacing in output.
         Include_Slopes: false                       // Include slope latency in output.

     Traffic_Register:                               // Register traffic to various RTC telemetry (based on traffic destination).
     - Type: Camera
         Port: 5123
         IP: 192.168.3.1

     - Type: Slopes
         Port: 9001
         IP: 192.168.3.2

     - Type: Command
         Port: 5125
         IP: 192.168.3.1

 */

/******************************
        INCLUDES
******************************/

#include <daoGigeReader.h>
#include <yaml-cpp/yaml.h>
#include "daoErspan.hpp"
#include <netinet/in.h>
#include <CLI/CLI.hpp>
#include <daoLog.hpp>
#include <daoShm.hpp>
#include <optional>
#include <mudpi.h>
#include <utility>
#include <cstddef>
#include <csignal>
#include <cassert>
#include <thread>
#include <queue>

/******************************
        DEFINITIONS
******************************/

/**
 * @brief Specifies the maximum number of
 * latency measurements that can be written
 * to the output shared memory.
*/
#define MAX_OUTPUT_COUNT    4

/**
 * @brief Flag set upon receiving an interrupt signal
 * and informs the program to gracefully end.
*/
bool g_terminateProgram {};

/**
 * @brief The application logging level; this is >=DEBUG for a debug
 * build and >=INFO for a release build.
*/
const Dao::Log::LEVEL APP_LOG_LEVEL {
    #ifdef DEBUG_
    Dao::Log::LEVEL::DEBUG
    #else
    Dao::Log::LEVEL::INFO
    #endif
};

/**
 * @brief Houses related information for an
 * RTC camera frame, including the various pipeline latencies
 * that are related to the frame.
 */
struct Frame_Info
{
    struct
    {
        float readoutSpacing;
        float readoutLatency;
        float slopesLatency;
        float commandLatency;
    } profile;

    uint64_t timestamp;
    uint64_t frameID;
    size_t received;
    bool complete;
};

/**
 * @brief Classifies a given type of network traffic,
 * based on its destination IPv4 and UDP port, into
 * a recognised AORTC traffic class.
 */
struct Traffic_Class
{
    std::string ip;
    uint16_t port;

    enum class Type : uint8_t
    {
        Unknown,
        Camera,
        Slopes,
        Command
    } type;

    static inline const std::unordered_map<std::string, Traffic_Class::Type> typeMap
    {
        {"Camera",  Type::Camera},
        {"Slopes",  Type::Slopes},
        {"Command", Type::Command}
    };
};

/**
 * @brief Houses all configuration parameters that
 * are parsed from the provided configuration file.
 */
struct Configuration
{
    std::optional<Dao::Erspan::Stream::ID_t> streamID;
    std::vector<Traffic_Class> trafficRegistry;
    std::string interface;
    std::string outShmPath;
    size_t packetQueueLimit;
    float clockResolution;
    float scaleFactor;
    bool includeReadout;
    bool includeSlopes;
};

/**
 * @brief Houses program state that is shared between the main
 * thread and the background processing thread.
 */
struct Shared_State
{
    Shared_State(
        Dao::Log::Logger &logger,
        const Configuration &configuration
    ) : logger(logger), trafficRegistry(configuration.trafficRegistry), outShmPath(configuration.outShmPath),
        clockResolution(configuration.clockResolution), scaleFactor(configuration.scaleFactor),
        includeReadout(configuration.includeReadout), includeSlopes(configuration.includeSlopes),
        endProcessing(false)
    {
    }

    Dao::Log::Logger &logger;
    const std::vector<Traffic_Class> trafficRegistry;
    const std::string outShmPath;
    const float clockResolution;
    const float scaleFactor;
    const bool includeReadout;
    const bool includeSlopes;

    std::queue<Dao::Erspan::Packet_Summary> packetQueue;
    std::atomic<bool> endProcessing;
    std::mutex packetQueueMutex;
};

/**
* @brief Container for storing camera frame information.
*/
using FramesMap = std::unordered_map<uint64_t, Frame_Info>;

/******************************
        TRAFFIC ANALYSIS
 ******************************/

/**
 * @brief Accepts and processes a GVSP (v2) readout packet, determining the readout
 * latency and average inter-packet spacing throughout the frame's readout stream. These
 * readout metrics are stored for RTC latency calculations later on.
 */
void processGvspV2Packet(
    Dao::Log::Logger &logger,
    const std::byte *data,
    const uint64_t timestamp,
    FramesMap &frames,
    const float clockResolution
)
{
    uint8_t type = *getFormatV2((char *)data);
    uint64_t frameID = be64toh(*getBlockIdV2((char *)data));

    if (type == GEV_FORMAT_LEADER_V2) {
        Frame_Info frame {};
        frame.received = 1;
        frame.frameID = frameID;
        frame.timestamp = timestamp;
        frames[frame.frameID] = frame;
        logger.Debug("Recevied readout leader for frame %d", frame.frameID);
    }
    else {
        auto itr = frames.find(frameID);
        if (itr != frames.end()) {
            Frame_Info &frame = itr->second;
            frame.profile.readoutLatency += (timestamp - frame.timestamp) * clockResolution;
            frame.timestamp = timestamp;
            frame.received++;

            if (type == GEV_FORMAT_TRAILER_V2) {
                uint32_t trailerPacketID = be32toh(*getPacketIdV2((char *)data));
                size_t numReadoutPackets = 1 + trailerPacketID;

                frame.profile.readoutSpacing = frame.profile.readoutLatency / trailerPacketID;
                frame.complete = (frame.received == numReadoutPackets);

                logger.Debug(
                    "Recevied readout trailer for frame %d (%d/%d - %s)",
                    frame.frameID,
                    frame.received,
                    numReadoutPackets,
                    frame.complete ? "COMPLETE" : "PARTIAL"
                );
            }
        }
    }
}

/**
 * @brief Intra-pipeline data results are transmitted between nodes using
 * the ESO RTMS data protocol. This function accepts such a packet and
 * returns its associated GigeVision frame identifier. This is used throughout
 * the program to align the data packet with the correct camera frame to ensure
 * an accurate and robust frame->result latency measurement.
 */
uint32_t getPacketID(const std::byte *data)
{
    mudpi::mudpiHeader mudpiHeader {};
    std::memcpy(&mudpiHeader, data, sizeof(mudpiHeader));
    return mudpiHeader.sampleId;
}

/**
 * @brief Accepts an RTC slopes packet timestamp and calculates readout->slopes latency.
 */
void processSlopesPacket(Dao::Log::Logger &logger, const uint64_t timestamp, Frame_Info &frame, const float clockResolution)
{
    frame.profile.slopesLatency = (timestamp - frame.timestamp) * clockResolution;
    logger.Debug("Received slopes packet for frame %d", frame.frameID);
}

/**
 * @brief Accepts an RTC command packet timestamp and calculates readout->command latency.
 */
void processCommandPacket(Dao::Log::Logger &logger, const uint64_t timestamp, Frame_Info &frame, const float clockResolution)
{
    frame.profile.commandLatency = (timestamp - frame.timestamp) * clockResolution;
    logger.Debug("Received command packet for frame %d", frame.frameID);
}

/**
 * @brief If the provided frame is considered complete then this function outputs
 * the desired components of its latency profile according to the program configuration,
 * on the other hand if the frame is considered incomplete then no profile is output, in
 * either case the frame is removed from memory.
 */
void commitFrameProfile(
    Dao::Log::Logger &logger,
    Frame_Info &frame,
    const bool includeReadout,
    const bool includeSlopes,
    const float scaleFactor,
    FramesMap &frames,
    const std::unique_ptr<Dao::Shm<float>> &outputShm
)
{
    assert(frame.profile.readoutSpacing >= 0.0f);
    assert(frame.profile.readoutLatency >= 0.0f);
    assert(frame.profile.slopesLatency >= 0.0f);
    assert(frame.profile.commandLatency >= 0.0f);

    size_t i {};
    std::vector<float> outputs(MAX_OUTPUT_COUNT);
    if (includeReadout) {
        outputs[i++] = frame.profile.readoutSpacing * scaleFactor;
        outputs[i++] = frame.profile.readoutLatency * scaleFactor;
    }
    if (includeSlopes) {
        outputs[i++] = frame.profile.slopesLatency * scaleFactor;
    }
    outputs[i] = frame.profile.commandLatency * scaleFactor;

    if (frame.complete) {
        outputShm->get_meta_data()->cnt2 = frame.frameID;
        outputShm->set_frame(outputs.data());
        logger.Info(
            "spacing: %f, readout: %f, slopes: %f, command: %f",
            outputs[0], outputs[1], outputs[2], outputs[3]
        );
    }
    else {
        logger.Debug("No commit for frame %d due to partial readout", frame.frameID);
    }

    // @todo handle potential build up of frames in which we received no
    // @todo command for - this is a potential memory leak and crash
    // @todo if it goes on long enough. 
    frames.erase(frame.frameID);
}

/**
 * @brief Accepts Erspan packet from daoErspan library and processes any RTC packets.
 */
void processPacket(
    Dao::Log::Logger &logger,
    const Dao::Erspan::Packet_Summary &packet,
    Shared_State &sharedState,
    FramesMap &frames,
    const std::unique_ptr<Dao::Shm<float>> &outputShm
)
{
    // The RTC traffic is all UDP packets (GigeVision, MudPi, Raw UDP)
    // so we first filter out any packets that are not UDP, and then
    // parse the UDP frame.
    if (packet.IP.protocol != IPPROTO_UDP) {
        return;
    }

    // Parse UDP packet.
    uint16_t destPort {};
    const std::byte *data = packet.IP.payloadSample;
    std::memcpy(&destPort, data + 2, sizeof(uint16_t));
    destPort = be16toh(destPort);
    data += 8;

    // Now we need to detect if this UDP packet is part of the RTC
    // traffic and if so what is it (GigeVision, Slopes, Command etc).
    Traffic_Class::Type trafficClass = Traffic_Class::Type::Unknown;
    for (const Traffic_Class &T : sharedState.trafficRegistry) {
        if (T.ip == packet.IP.dest && T.port == destPort) {
            trafficClass = T.type;
            break;
        }
    }

    // Drop non-RTC packet.
    if (trafficClass == Traffic_Class::Type::Unknown) {
        return;
    }

    // Process RTC packet.

    // .. Camera readout packet.
    if (trafficClass == Traffic_Class::Type::Camera) {
        processGvspV2Packet(logger, data, packet.Erspan.timestamp, frames, sharedState.clockResolution);
        return;
    }

    // .. Intra-pipeline data packet.
    uint32_t frameID = getPacketID(data);
    if (frames.find(frameID) == frames.end()) {
        logger.Debug("not got frame for results packet (frame: %ld)", frameID);
        return;
    }

    Frame_Info &frame = frames.at(frameID);
    switch (trafficClass) {
        case Traffic_Class::Type::Slopes:
            processSlopesPacket(logger, packet.Erspan.timestamp, frame, sharedState.clockResolution);
            break;

        case Traffic_Class::Type::Command:
            processCommandPacket(logger, packet.Erspan.timestamp, frame, sharedState.clockResolution);
            commitFrameProfile(logger, frame, sharedState.includeReadout, sharedState.includeSlopes, sharedState.scaleFactor, frames, outputShm);
            break;

        default:
            break;
    }
}

/**
 * @brief Function that dequeues packets and processes them to provide
 * real-time pipeline latency information.
 */
void packetProcessingFunc(Dao::Log::Logger &logger, Shared_State &sharedState)
{
    FramesMap frames {};
    auto outputShm = std::make_unique<Dao::Shm<float>>(sharedState.outShmPath, Dao::Shape { 1, MAX_OUTPUT_COUNT });

    while (!sharedState.endProcessing) {
        bool packetGrabbed {};
        Dao::Erspan::Packet_Summary packetSummary {};

        {
            std::lock_guard<std::mutex> lock(sharedState.packetQueueMutex);
            if (sharedState.packetQueue.size()) {
                packetSummary = sharedState.packetQueue.front();
                sharedState.packetQueue.pop();
                packetGrabbed = true;
            }
        }

        if (packetGrabbed) {
            processPacket(logger, packetSummary, sharedState, frames, outputShm);
        }
    }

    logger.Debug("Packet processing thread exited");
};

/******************************
         CONFIGURATION
 ******************************/
/**
 * @brief Parses application YAML configuration file and populates the application
 * context for later use by the program.
 *
 * @return Returns a configuration if the configuration file was succesfully parsed, and nullopt otherwise.
 */
std::optional<Configuration>
configureFromFile(Dao::Log::Logger &logger, const std::string &configPath)
{
    Configuration configuration {};

    // load file..
    YAML::Node root;
    try {
        root = YAML::LoadFile(configPath);
    }
    catch (std::exception &e) {
        logger.Critical("Configuration file load failed: %s", e.what());
        return std::nullopt;
    }

    // parse app configs..
    YAML::Node app = root["App_Configuration"];
    if (!app.IsDefined() || !app.IsMap()) {
        logger.Critical("Configuration file has no app configuration map!");
        return std::nullopt;
    }

    try {
        configuration.clockResolution = app["Erspan_Clock_Resolution"].as<float>();
        configuration.interface = app["Erspan_Stream_Interface"].as<std::string>();
        configuration.packetQueueLimit = app["Packet_Queue_Limit"].as<size_t>();
        configuration.outShmPath = app["Output_Location"].as<std::string>();
        configuration.scaleFactor = app["Output_Scale_Factor"].as<float>();
        configuration.includeReadout = app["Include_Readout"].as<bool>();
        configuration.includeSlopes = app["Include_Slopes"].as<bool>();

        if (!app["Erspan_Stream"].IsDefined()) {
            logger.Critical("Configuration file requires erspan-stream field within app configuration!");
            return std::nullopt;
        }
        else if (app["Erspan_Stream"].IsNull()) {
            configuration.streamID = std::nullopt;
        }
        else {
            configuration.streamID = app["Erspan_Stream"].as<Dao::Erspan::Stream::ID_t>();
        }
    }
    catch (std::exception &e) {
        logger.Critical("Configuration file has invalid app configuration: %s", e.what());
        return std::nullopt;
    }

    if (configuration.scaleFactor <= 0.0f) {
        logger.Critical("Configuration file requires an output scale factor >= 1.0!");
        return std::nullopt;
    }

    // parse traffic register..
    YAML::Node trafficList = root["Traffic_Register"];
    if (!trafficList.IsDefined() || !trafficList.IsSequence()) {
        logger.Critical("Configuration file has no traffic register list!");
        return std::nullopt;
    }

    try {
        for (const YAML::Node &node : trafficList) {
            Traffic_Class traffic_entry {};
            traffic_entry.type = Traffic_Class::typeMap.at(node["Type"].as<std::string>());
            traffic_entry.port = node["Port"].as<uint16_t>();
            traffic_entry.ip = node["IP"].as<std::string>();
            configuration.trafficRegistry.push_back(traffic_entry);
        }
    }
    catch (std::exception &e) {
        logger.Critical("Configuration file has invalid traffic register entry: %s", e.what());
        return std::nullopt;
    }

    if (!configuration.trafficRegistry.size()) {
        logger.Warning("Traffic register is empty!");
        return std::nullopt;
    }

    //
    return configuration;
}

/******************************
          APP ENTRY
 ******************************/

/**
 * @brief Function invoked upon interrupt signal
 * to inform the program to exit gracefully.
 */
void exitHandler([[maybe_unused]] int signal)
{
    g_terminateProgram = true;
}

int main(int argc, char *argv[])
{
    // Register signal handler.
    std::signal(SIGINT, exitHandler);

    // Define main thread state.
    std::unique_ptr<Dao::Erspan::Stream> packetStream {};
    size_t recvPacketsDropped {};

    // Define application logger.
    Dao::Log::Logger logger("daoMonitor", Dao::Log::Logger::DESTINATION::SCREEN); logger.SetLevel(APP_LOG_LEVEL);

    // Parse CLI.
    std::string configPath {};
    CLI::App app("Real-time Latency Monitoring Tool (ErspanV3)", "daoMonitor");
    app.add_option("CONFIG", configPath, "Application configuration file path (YAML)")->required();
    CLI11_PARSE(app, argc, argv);

    // Load configuration.
    std::optional<Configuration> configurationResult = configureFromFile(logger, configPath);
    if (!configurationResult) {
        return EXIT_FAILURE;
    }
    const Configuration &configuration = *configurationResult;

    // Construct thread-shared state.
    Shared_State sharedState(logger, configuration);

    // Define the packet receive function which is handed to the Erspan library
    // to handle received packets.
    auto packetReceiveFunc = [&sharedState, &recvPacketsDropped, &configuration, &logger](Dao::Erspan::Packet_Summary &packetSummary) {
        std::lock_guard<std::mutex> lock(sharedState.packetQueueMutex);
        if (sharedState.packetQueue.size() == configuration.packetQueueLimit) {
            ++recvPacketsDropped;
            logger.Warning("Dropped total of %ld packets due to internal queue full", recvPacketsDropped);
            return;
        }
        sharedState.packetQueue.push(packetSummary);
    };

    // Create output shared memory & Erspan interface.
    try {
        packetStream = std::make_unique<Dao::Erspan::Stream>(
            logger,
            configuration.interface,
            configuration.streamID,
            packetReceiveFunc
        );
    }
    catch (const std::exception &e) {
        logger.Critical("Error: %s", e.what());
        return EXIT_FAILURE;
    }

    // Begin packet processing loop.
    std::thread packetProcessingThread(
        packetProcessingFunc,
        std::ref(logger),
        std::ref(sharedState)
    );

    // Begin packet receive loop (blocking).
    bool streamEndGood = packetStream->begin(g_terminateProgram);
    logger.Info("Packet receive loop has ended: %s", streamEndGood ? "Good" : "Error");

    // Cleanup processing thread.
    sharedState.endProcessing = true;
    packetProcessingThread.join();

    //
    return streamEndGood ? EXIT_SUCCESS : EXIT_FAILURE;
}

