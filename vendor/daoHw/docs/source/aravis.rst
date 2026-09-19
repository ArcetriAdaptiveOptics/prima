Aravis — GigE Vision Cameras
==============================

The ``aravis/`` module provides DAO drivers for GigE Vision cameras using the
`Aravis <https://aravisproject.github.io/aravis/>`_ open-source library. Aravis
implements the GigE Vision and USB3 Vision standards in a vendor-neutral way,
allowing a single code base to support cameras from Allied Vision, Basler,
First Light Imaging, Teledyne FLIR, and custom in-house designs.

All drivers in this module write acquired frames to DAO shared memory segments
and expose camera control parameters (exposure time, frame rate, gain, trigger
mode) through dedicated control shared memory segments.

.. contents::
   :local:
   :depth: 2

----

Installation
------------

Aravis must be built from source. Follow the official build guide at
https://aravisproject.github.io/aravis/aravis-stable/building.html or use
the ``INSTALL_ARAVIS`` notes provided in ``aravis/``.

**Ubuntu / Debian dependencies:**

.. code-block:: bash

   sudo apt install meson libxml2-dev libglib2.0-dev cmake libusb-1.0-0-dev \
       gobject-introspection libgtk-3-dev gtk-doc-tools xsltproc \
       libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev \
       libgstreamer-plugins-good1.0-dev libgirepository1.0-dev gettext

   meson setup build
   cd build
   ninja
   sudo ninja install

**macOS:**

Aravis is not installed in the system prefix on macOS. Install to ``/opt/aravis``
and export the environment variables:

.. code-block:: bash

   export DYLD_LIBRARY_PATH=$DYLD_LIBRARY_PATH:/opt/aravis/lib
   export PKG_CONFIG_PATH=$PKG_CONFIG_PATH:/opt/aravis/lib/pkgconfig

----

Core Files
----------

``daoHwAravisCtrl.c``
^^^^^^^^^^^^^^^^^^^^^

The main Aravis camera acquisition loop. Opens a GigE Vision device by IP address
or device serial number, configures the pixel format, and pushes frames into a
DAO shared memory segment as they arrive. Supports software and hardware trigger
modes, and handles stream buffer recycling to avoid frame drops.

``daoHwAravisDeviceCtrl.c``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Lower-level Aravis device control helpers. Provides functions for reading and
writing GigE Vision feature nodes (exposure time, gain, frame rate, trigger
source) and for building the Aravis stream pipeline. Used internally by the
camera-specific controllers described below.

``daoHwAravisEVHZ.c``
^^^^^^^^^^^^^^^^^^^^^^

Specialised driver for the EV (Emergent Vision) high-frame-rate camera in EVHZ
mode. Configures the Emergent Vision transport layer extensions and exposes a
reduced-latency acquisition path.

``daoHwAravisFakeCamera.c``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A software-only fake camera that emits synthetic frames through the Aravis API.
Used for testing the DAO pipeline without physical hardware.

----

Allied Vision (AVT) Cameras
----------------------------

``daoHwAvtControlMain.c``
^^^^^^^^^^^^^^^^^^^^^^^^^^

Entry point and command-line parser for all AVT camera drivers. Selects the
correct device controller based on the camera model passed as an argument and
starts the acquisition and control threads.

``daoHwAvtG030DeviceCtrl.c``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Device-specific controller for the **Allied Vision Mako G-030** (0.3 MP GigE
camera). Configures binning, pixel format, and ROI, then runs the acquisition
loop writing frames to shared memory.

``daoHwAvtGC1020MDeviceCtrl.c``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Device-specific controller for the **Allied Vision GC1020M** (1 MP monochrome
GigE camera). Supports hardware trigger input and automatic frame rate control.

``daoHwAvtGT1920DeviceControl.c``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Device-specific controller for the **Allied Vision Goldeye GT1920** (1.9 MP
near-infrared GigE camera). Provides temperature monitoring and cooling
management via control shared memory.

----

Basler Cameras
--------------

``daoHwBaslerDeviceCtrl.c``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Standard Basler GigE camera controller. Supports Basler's GenICam feature tree
through Aravis, including exposure, gain, and hardware trigger configuration.

``daoHwBaslerWBinDeviceCtrl.c``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Basler camera controller with **weighted binning** support. Used when sub-pixel
resolution is traded for improved SNR by combining pixels with configurable
weights before writing frames to shared memory.

----

Bob Camera
----------

``daoHwBobDeviceCtrl.c``
^^^^^^^^^^^^^^^^^^^^^^^^^^

Controller for the custom in-house **Bob** detector board. Interfaces via
GigE Vision and handles Bob-specific packet framing and payload reconstruction.

``daoHwBobDeviceSWTrigCtrl.c``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Variant of the Bob controller that uses **software triggering** instead of
hardware exposure triggers. Allows the DAO control loop to issue exposure
commands through a shared memory flag.

----

C-Blue and EV Cameras
----------------------

``daoHwCBlueDeviceCtrl.c``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Controller for the **First Light C-Blue One** CMOS camera over GigE Vision.
Provides sub-electron noise performance in the visible band.

``daoHwStandaloneCblueCtrl.c``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Standalone entry point for the C-Blue controller, allowing it to run as an
independent process without the AVT command-line wrapper.

``daoHwStandaloneEVCtrl.c``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Standalone entry point for the Emergent Vision high-frame-rate camera driver.

----

FLIR Camera
-----------

``daoHwFlirDeviceCtrl.c``
^^^^^^^^^^^^^^^^^^^^^^^^^^

Controller for **Teledyne FLIR** GigE cameras. Supports FLIR-specific features
accessed through the Aravis GenICam interface, including temperature regulation
and frame metadata extraction.

----

OCAM2 via iPort
---------------

``daoHwIPORTDeviceCtrl.c``
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Driver for the **First Light OCAM2** camera when connected through a
**Pleora iPort** Camera Link to GigE Vision converter. The iPort re-encapsulates
Camera Link data into GigE Vision packets; this driver handles the resulting
stream and reconstructs full frames in shared memory.

``daoHwIPORTOcam2DeviceCtrl.c``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

OCAM2-specific variant of the iPort device controller. Applies the OCAM2
pixel descrambling step (see ``daoHwOcamDescramble.py``) before writing frames
to shared memory.

``daoHwOcamDescramble.py``
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Python utility that implements the OCAM2 pixel descrambling algorithm. The
OCAM2 EM-CCD outputs pixels in a non-sequential order that must be remapped
before the image can be used. This module can be imported and called from the
C driver via Python embedding, or used standalone.

----

iPort Control Utilities
-----------------------

``daoIportControl.h`` / ``daoIportControl.c``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

C library for communicating with the Pleora iPort converter's serial control
channel. Provides functions for reading and writing camera link configuration
registers on the iPort device.

``daoIportControlMain.c``
^^^^^^^^^^^^^^^^^^^^^^^^^^

Command-line tool that uses ``daoIportControl`` to inspect or modify iPort
converter settings from the shell.

----

Shared Memory Layout
--------------------

All Aravis drivers create the following shared memory segments (names are
configured on the command line):

.. list-table::
   :header-rows: 1
   :widths: 30 20 50

   * - SHM name suffix
     - Type
     - Description
   * - (base name)
     - UINT16 [H×W]
     - Acquired image frame
   * - ``Dit``
     - FLOAT32 [1]
     - Exposure time (integration time) in seconds
   * - ``Fps``
     - FLOAT32 [1]
     - Frame rate in Hz (read-back or setpoint)
   * - ``Gain``
     - FLOAT32 [1]
     - Analogue gain (camera-specific units)

.. note::
   Some camera models expose additional control SHMs (e.g. temperature,
   trigger mode). Refer to the individual controller source file for the
   full list.

----

Usage Example
-------------

.. code-block:: bash

   # Start an Allied Vision Mako G-030 streaming to /tmp/wfs.im.shm
   daoHwAvtControlMain -cam g030 -S /tmp/wfs -ip 192.168.1.10

   # Read the live frame rate
   python3 -c "import dao; s=dao.shm('/tmp/wfsFps.im.shm'); print(s.get_data())"

   # Set exposure time to 2 ms
   python3 -c "import dao,numpy as np; s=dao.shm('/tmp/wfsDit.im.shm'); s.set_data(np.array([0.002],dtype=np.float32))"

See also :doc:`common` for the Python ``daoCameraController`` wrapper which
simplifies camera parameter management.
