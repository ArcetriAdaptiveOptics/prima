// *****************************************************************************
//
//     Copyright (c) 2013, Pleora Technologies Inc., All rights reserved.
//
// *****************************************************************************

//
// Configuration downloader tool - downloads device and stream configuration
// from an iPort device and saves it locally for configuration management.
//

#include <PvDevice.h>
#include <PvDeviceGEV.h>
#include <PvDeviceU3V.h>
#include <PvStream.h>
#include <PvStreamGEV.h>
#include <PvStreamU3V.h>
#include <PvConfigurationWriter.h>
#include <PvSystem.h>
#include <PvTypes.h>
#include <iostream>
#include <ctime>
#include <cstring>

using namespace std;

#define DEVICE_CONFIGURATION_TAG ( "DeviceConfiguration" )
#define STREAM_CONFIGURATION_TAG ( "StreamConfiguration" )
#define METADATA_TAG ( "ConfigurationMetadata" )

//
// Download configuration from device and save to file
//
bool DownloadConfiguration( const PvString &aConnectionID, const PvString &aFileName )
{
    PvResult lResult;
    PvConfigurationWriter lWriter;

    // Connect to the GigE Vision or USB3 Vision device
    cout << "Connecting to device..." << endl;
    PvDevice *lDevice = PvDevice::CreateAndConnect( aConnectionID, &lResult );
    if ( !lResult.IsOK() )
    {
        cout << "Error: Unable to connect to device - " << lResult.GetCodeString().GetAscii() << endl;
        PvDevice::Free( lDevice );
        return false;
    }

    cout << "Device connected successfully" << endl;

    // Store device configuration
    cout << "Reading device configuration..." << endl;
    lWriter.Store( lDevice, DEVICE_CONFIGURATION_TAG );

    // Create and open PvStream
    cout << "Opening stream..." << endl;
    PvStream *lStream = PvStream::CreateAndOpen( aConnectionID, &lResult );
    if ( !lResult.IsOK() )
    {
        cout << "Warning: Unable to open stream - " << lResult.GetCodeString().GetAscii() << endl;
        cout << "Continuing with device configuration only..." << endl;
    }
    else
    {
        cout << "Reading stream configuration..." << endl;
        lWriter.Store( lStream, STREAM_CONFIGURATION_TAG );
        PvStream::Free( lStream );
    }

    // Add metadata with timestamp and device info
    time_t rawtime;
    struct tm * timeinfo;
    char timestamp[80];
    
    time(&rawtime);
    timeinfo = localtime(&rawtime);
    strftime(timestamp, sizeof(timestamp), "%Y-%m-%d %H:%M:%S", timeinfo);
    
    char metadataStr[256];
    snprintf(metadataStr, sizeof(metadataStr), "Downloaded on: %s", timestamp);
    PvString metadata(metadataStr);
    lWriter.Store( metadata, METADATA_TAG );

    // Save to file
    cout << "Saving configuration to file: " << aFileName.GetAscii() << endl;
    lResult = lWriter.Save( aFileName );
    if ( !lResult.IsOK() )
    {
        cout << "Error: Unable to save configuration file - " << lResult.GetCodeString().GetAscii() << endl;
        lDevice->Disconnect();
        PvDevice::Free( lDevice );
        return false;
    }

    cout << "Configuration downloaded successfully!" << endl;

    // Clean up
    lDevice->Disconnect();
    PvDevice::Free( lDevice );

    return true;
}

//
// Print usage information
//
void PrintUsage()
{
    cout << "Usage: get_config [options] [output_file.pvxml]" << endl;
    cout << "Options:" << endl;
    cout << "  -ip <ip_address>  Connect to device at specific IP address" << endl;
    cout << "  -h, --help        Show this help message" << endl;
    cout << "  If no output file is specified, 'device_config.pvxml' will be used" << endl;
    cout << "  This tool downloads the current configuration from an iPort device" << endl;
    cout << "  and saves it locally for configuration management." << endl;
}

//
// Simple device discovery and selection
//
bool SelectDevice(PvString &aConnectionID)
{
    PvSystem lSystem;
    
    cout << "Discovering devices..." << endl;
    lSystem.Find();
    
    uint32_t lDeviceCount = lSystem.GetDeviceCount();
    if (lDeviceCount == 0)
    {
        cout << "No devices found." << endl;
        return false;
    }
    
    cout << "Found " << lDeviceCount << " device(s):" << endl;
    for (uint32_t i = 0; i < lDeviceCount; i++)
    {
        const PvDeviceInfo *lDeviceInfo = lSystem.GetDeviceInfo(i);
        cout << "[" << i << "] " << lDeviceInfo->GetDisplayID().GetAscii() 
             << " (" << lDeviceInfo->GetConnectionID().GetAscii() << ")" << endl;
    }
    
    if (lDeviceCount == 1)
    {
        // Auto-select if only one device
        const PvDeviceInfo *lDeviceInfo = lSystem.GetDeviceInfo(0);
        aConnectionID = lDeviceInfo->GetConnectionID();
        cout << "Auto-selecting device: " << lDeviceInfo->GetDisplayID().GetAscii() << endl;
        return true;
    }
    
    // Ask user to select
    cout << "Select device (0-" << (lDeviceCount - 1) << "): ";
    int selection;
    cin >> selection;
    
    if (selection < 0 || selection >= (int)lDeviceCount)
    {
        cout << "Invalid selection." << endl;
        return false;
    }
    
    const PvDeviceInfo *lDeviceInfo = lSystem.GetDeviceInfo(selection);
    aConnectionID = lDeviceInfo->GetConnectionID();
    cout << "Selected device: " << lDeviceInfo->GetDisplayID().GetAscii() << endl;
    
    return true;
}

//
// Main function
//
int main( int argc, char* argv[] )
{
    // Parse command line arguments
    PvString lFileName = "device_config.pvxml";
    PvString lIPAddress = "";
    
    for (int i = 1; i < argc; i++)
    {
        if (strcmp(argv[i], "-h") == 0 || strcmp(argv[i], "--help") == 0)
        {
            PrintUsage();
            return 0;
        }
        else if (strcmp(argv[i], "-ip") == 0 && i + 1 < argc)
        {
            lIPAddress = argv[++i];
        }
        else if (argv[i][0] != '-')
        {
            lFileName = argv[i];
        }
    }

    cout << "daoIportGetConfig" << endl;
    cout << "=================" << endl << endl;

    // Get device connection
    PvString lConnectionID;
    
    if (lIPAddress.GetAscii() && strlen(lIPAddress.GetAscii()) > 0)
    {
        // Connect directly to specified IP
        lConnectionID = lIPAddress;
        cout << "Connecting to device at IP: " << lIPAddress.GetAscii() << endl;
    }
    else
    {
        // Discover and select device
        if (!SelectDevice(lConnectionID))
        {
            cout << "No device selected. Exiting." << endl;
            return 1;
        }
    }

    // Download configuration
    if ( !DownloadConfiguration( lConnectionID, lFileName ) )
    {
        cout << "Failed to download configuration." << endl;
        return 1;
    }

    cout << endl << "Configuration download completed successfully." << endl;
    cout << "File saved as: " << lFileName.GetAscii() << endl;

    return 0;
}