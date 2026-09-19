// *****************************************************************************
//
//     Copyright (c) 2013, Pleora Technologies Inc., All rights reserved.
//
// *****************************************************************************

//
// Configuration uploader tool - loads device and stream configuration
// from a local file and applies it to an iPort device.
//

#include <PvDevice.h>
#include <PvDeviceGEV.h>
#include <PvDeviceU3V.h>
#include <PvStream.h>
#include <PvStreamGEV.h>
#include <PvStreamU3V.h>
#include <PvConfigurationReader.h>
#include <iostream>
#include <fstream>
#include <cstring>
#include <PvSystem.h>
#include <PvTypes.h>

using namespace std;

#define DEVICE_CONFIGURATION_TAG ( "DeviceConfiguration" )
#define STREAM_CONFIGURATION_TAG ( "StreamConfiguration" )
#define METADATA_TAG ( "ConfigurationMetadata" )

//
// Upload configuration from file to device
//
bool UploadConfiguration( const PvString &aConnectionID, const PvString &aFileName )
{
    PvConfigurationReader lReader;
    PvResult lResult;
    
    // Load configuration from file
    cout << "Loading configuration from file: " << aFileName.GetAscii() << endl;
    lResult = lReader.Load( aFileName );
    if ( !lResult.IsOK() )
    {
        cout << "Error: Unable to load configuration file - " << lResult.GetCodeString().GetAscii() << endl;
        return false;
    }

    // Try to read metadata if available
    PvString lMetadata;
    lResult = lReader.Restore( METADATA_TAG, lMetadata );
    if ( lResult.IsOK() )
    {
        cout << "Configuration metadata: " << lMetadata.GetAscii() << endl;
    }

    // Connect to device first to determine device type
    cout << "Connecting to device..." << endl;
    PvDevice *lDevice = PvDevice::CreateAndConnect( aConnectionID, &lResult );
    if ( !lResult.IsOK() )
    {
        cout << "Error: Unable to connect to device - " << lResult.GetCodeString().GetAscii() << endl;
        PvDevice::Free( lDevice );
        return false;
    }

    cout << "Device connected successfully" << endl;
    
    // Disconnect temporarily to allow configuration restore
    lDevice->Disconnect();
    PvDevice::Free( lDevice );
    lDevice = NULL;

    // Restore device configuration
    cout << "Restoring device configuration..." << endl;
    
    PvDeviceGEV lDeviceGEV;
    PvDeviceU3V lDeviceU3V;
    
    // Attempt restoring as a GEV device
    lResult = lReader.Restore( DEVICE_CONFIGURATION_TAG, &lDeviceGEV );
    if ( lResult.IsOK() )
    {
        cout << "Device configuration restored as GigE Vision device" << endl;
        lDevice = &lDeviceGEV;
    }
    else
    {
        // Attempt restoring as a U3V device
        lResult = lReader.Restore( DEVICE_CONFIGURATION_TAG, &lDeviceU3V );
        if ( lResult.IsOK() )
        {
            cout << "Device configuration restored as USB3 Vision device" << endl;
            lDevice = &lDeviceU3V;
        }
        else
        {
            cout << "Error: Unable to restore device configuration - " << lResult.GetCodeString().GetAscii() << endl;
            return false;
        }
    }

    // Verify device connection
    if ( !lDevice->IsConnected() )
    {
        cout << "Error: Device is not connected after configuration restore" << endl;
        return false;
    }

    // Try to restore stream configuration
    cout << "Restoring stream configuration..." << endl;
    
    PvStreamGEV lStreamGEV;
    PvStreamU3V lStreamU3V;
    PvStream *lStream = NULL;

    // Attempt restoring as a GEV Stream
    lResult = lReader.Restore( STREAM_CONFIGURATION_TAG, &lStreamGEV );
    if ( lResult.IsOK() )
    {
        cout << "Stream configuration restored as GigE Vision stream" << endl;
        lStream = &lStreamGEV;
    }
    else
    {
        // Attempt restoring as a U3V Stream
        lResult = lReader.Restore( STREAM_CONFIGURATION_TAG, &lStreamU3V );
        if ( lResult.IsOK() )
        {
            cout << "Stream configuration restored as USB3 Vision stream" << endl;
            lStream = &lStreamU3V;
        }
        else
        {
            cout << "Warning: Unable to restore stream configuration - " << lResult.GetCodeString().GetAscii() << endl;
            cout << "Continuing with device configuration only..." << endl;
        }
    }

    // Verify stream if it was restored
    if ( lStream != NULL )
    {
        if ( !lStream->IsOpen() )
        {
            cout << "Warning: Stream is not open after configuration restore" << endl;
        }
        else
        {
            cout << "Stream configuration applied successfully" << endl;
            lStream->Close();
        }
    }

    cout << "Configuration upload completed successfully!" << endl;

    // Clean up
    lDevice->Disconnect();

    return true;
}

//
// Print usage information
//
void PrintUsage()
{
    cout << "Usage: write_config [options] [input_file.pvxml]" << endl;
    cout << "Options:" << endl;
    cout << "  -ip <ip_address>  Connect to device at specific IP address" << endl;
    cout << "  -h, --help        Show this help message" << endl;
    cout << "  If no input file is specified, 'device_config.pvxml' will be used" << endl;
    cout << "  This tool loads a previously saved configuration and applies it" << endl;
    cout << "  to an iPort device." << endl;
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

    cout << "daoIportWriteConfig" << endl;
    cout << "===================" << endl << endl;

    // Check if file exists
    ifstream file(lFileName.GetAscii());
    if ( !file.good() )
    {
        cout << "Error: Configuration file '" << lFileName.GetAscii() << "' not found." << endl;
        return 1;
    }
    file.close();

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

    // Upload configuration
    if ( !UploadConfiguration( lConnectionID, lFileName ) )
    {
        cout << "Failed to upload configuration." << endl;
        return 1;
    }

    cout << endl << "Configuration upload completed successfully." << endl;

    return 0;
}