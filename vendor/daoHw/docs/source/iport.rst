Pleora iPort — Camera Link to GigE Vision Converter
=====================================================

The ``iport/`` module provides configuration management tools for the
**Pleora Technologies iPort** Camera Link to GigE Vision converter.
The iPort device re-encapsulates Camera Link serial data into standard
GigE Vision UDP packets, allowing Camera Link cameras to be accessed over
standard Ethernet infrastructure using GigE Vision drivers such as Aravis.

This is particularly useful for the **First Light OCAM2** and other high-speed
Camera Link cameras where GigE Vision transport is preferred over a dedicated
frame grabber card.

.. contents::
   :local:
   :depth: 2

----

Overview
--------

The iPort hardware converter:

- Accepts Camera Link **Base** or **Medium** configuration (depending on model)
- Streams frames over GigE Vision (UDP, standard port 3956)
- Exposes its configuration via the **Pleora eBUS SDK** (``PvDevice``,
  ``PvStream``, ``PvConfigurationWriter/Reader``)
- Passes Camera Link serial communication (for camera control) through to the
  host

The tools in this module use the **eBUS SDK** C++ API to save and restore
full device and stream configurations. This is important for preserving
frame format, packet size, and serial baud rate settings across power cycles.

Also note: the ``aravis/`` module contains the Aravis-based driver
(``daoHwIPORTDeviceCtrl.c``) for receiving and decoding the GigE Vision stream
from the iPort. See :doc:`aravis` for the acquisition driver.

----

Installation
------------

The **Pleora eBUS SDK** must be installed to build these tools. Obtain the SDK
from Pleora Technologies (https://www.pleora.com) for your platform.

The SDK installs:

- C++ headers (``PvDevice.h``, ``PvStream.h``, etc.)
- Shared libraries (``libPvBase.so``, ``libPvDevice.so``, etc.)
- ``PvSystem`` discovery tools

----

Files
-----

``daoIportGetConfig.cpp``
^^^^^^^^^^^^^^^^^^^^^^^^^^

Downloads the full device and stream configuration from a connected iPort
device and saves it to a local ``.pvcfg`` XML file for configuration management
and backup.

The tool:

1. Connects to the iPort device by GigE Vision connection ID (IP address or MAC)
2. Reads the **device configuration** (GenICam feature tree) via ``PvConfigurationWriter``
3. Opens the GigE Vision stream and reads the **stream configuration**
4. Writes both to the specified output file

**Usage:**

.. code-block:: bash

   daoIportGetConfig <connectionID> <outputFile.pvcfg>

   # Example: download config from iPort at 192.168.1.50
   daoIportGetConfig 192.168.1.50 config/iport_ocam2.pvcfg

``daoIportWriteConfig.cpp``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Uploads a previously saved ``.pvcfg`` configuration file to an iPort device,
restoring device and stream settings.

The tool:

1. Loads the ``.pvcfg`` XML file using ``PvConfigurationReader``
2. Connects to the iPort device
3. Restores the **device configuration** (pixel format, ROI, Camera Link settings)
4. Opens the stream and restores **stream parameters** (packet size, inter-packet delay)

**Usage:**

.. code-block:: bash

   daoIportWriteConfig <connectionID> <inputFile.pvcfg>

   # Example: restore config to iPort at 192.168.1.50
   daoIportWriteConfig 192.168.1.50 config/iport_ocam2.pvcfg

----

Configuration Files
-------------------

The ``config/`` directory contains saved iPort configuration files:

``config/cred2Iport.pvcfg``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Saved iPort configuration for the **First Light CRED2** camera connected via
a Pleora iPort converter. Contains the Camera Link pixel format, frame size,
baud rate, and GigE Vision stream parameters.

``config/daoHwLoadOcam2Lut.py``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Python script that loads the OCAM2 pixel lookup table (LUT) into shared memory.
The OCAM2 camera outputs pixels in a non-sequential scrambled order; the LUT
maps each pixel from its output position to its physical detector position.

``config/ocam2Lut.txt``
^^^^^^^^^^^^^^^^^^^^^^^^

The OCAM2 pixel descrambling look-up table in ASCII format. Each line contains
the remapped pixel index.

----

Typical Workflow
----------------

1. **First-time setup:** Connect the iPort to the network and the camera to
   the iPort Camera Link connector. Use the Pleora eBUS Player or ``daoIportGetConfig``
   to verify the connection and save the initial configuration.

2. **Configuration backup:**

   .. code-block:: bash

      daoIportGetConfig 192.168.1.50 config/iport_backup.pvcfg

3. **Restore configuration after power cycle:**

   .. code-block:: bash

      daoIportWriteConfig 192.168.1.50 config/iport_ocam2.pvcfg

4. **Start GigE Vision acquisition** via the Aravis driver:

   .. code-block:: bash

      daoHwIPORTOcam2DeviceCtrl -ip 192.168.1.50 -S /tmp/ocam -L

See :doc:`aravis` for details of the Aravis-based acquisition driver, and
:doc:`fli` for CRED camera configuration.

.. note::
   The iPort presents itself as a standard GigE Vision device; any GigE Vision
   viewer (e.g. ``arv-viewer``) can be used to verify connectivity before
   starting the DAO driver.
