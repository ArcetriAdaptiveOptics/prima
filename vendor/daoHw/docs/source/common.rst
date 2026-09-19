Common Utilities
=================

The ``common/`` module contains shared utilities used by multiple daoHw drivers.
It includes a raw GigE Vision packet parser written in C, Python wrappers for
camera and SLM control, and portable endian-handling macros.

.. contents::
   :local:
   :depth: 2

----

C Utilities
-----------

``daoGigeReader.h`` / ``daoGigeReader.c``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A portable **GigE Vision packet parser** that reconstructs image frames from
raw UDP packets received on a network interface. This is an alternative to using
a full GigE Vision SDK (such as Aravis) when maximum control over the network
stack is required.

The reader supports both GigE Vision **v1** and **v2** packet formats
(leader, payload, and trailer packets) and handles jumbo frames up to
``BUFSIZE = 9000`` bytes.

**Key packet format constants:**

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Constant
     - Description
   * - ``GEV_FORMAT_LEADER`` (``0x01``)
     - Start-of-frame packet (v1)
   * - ``GEV_FORMAT_TRAILER`` (``0x02``)
     - End-of-frame packet (v1)
   * - ``GEV_FORMAT_PAYLOAD`` (``0x03``)
     - Image data payload packet (v1)
   * - ``GEV_FORMAT_LEADER_V2`` (``0x81``)
     - Start-of-frame packet (v2)
   * - ``GEV_FORMAT_TRAILER_V2`` (``0x82``)
     - End-of-frame packet (v2)
   * - ``GEV_FORMAT_PAYLOAD_V2`` (``0x83``)
     - Image data payload packet (v2)
   * - ``GEV_FORMAT_MONO`` (``0x0100``)
     - Monochrome pixel format identifier
   * - ``GEV_PAYLOAD_IMAGE`` (``0x0001``)
     - Payload type: image

**Status codes:**

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Status
     - Meaning
   * - ``GEV_STATUS_SUCCESS`` (``0x0000``)
     - Packet received and parsed successfully
   * - ``GEV_STATUS_PACKET_UNAVAILABLE`` (``0x8000``)
     - No packet available in the receive buffer
   * - ``GEV_STATUS_DATA_OVERRUN`` (``0x8001``)
     - Buffer overrun; frame data lost

``daoGigeReaderV1.c`` / ``daoGigeReaderV2.c``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Implementation files for GigE Vision v1 and v2 packet parsing respectively.
Both are compiled into ``daoGigeReader.c`` which provides the unified public
API.

``daoEndianUtils.h``
^^^^^^^^^^^^^^^^^^^^^

Portable byte-swap macros for handling big-endian / little-endian conversions
across x86, ARM, and other architectures. Used by the GigE reader and any
other driver that needs to parse network-byte-order fields.

**Key macros:**

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Macro
     - Description
   * - ``DAO_BSWAP16(x)``
     - Swap 16-bit integer byte order
   * - ``DAO_BSWAP32(x)``
     - Swap 32-bit integer byte order
   * - ``DAO_BSWAP64(x)``
     - Swap 64-bit integer byte order
   * - ``DAO_NTOH16(x)``
     - Network-to-host 16-bit conversion
   * - ``DAO_NTOH32(x)``
     - Network-to-host 32-bit conversion

``time_rdtsc.h`` / ``time_rdtsc.c``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

High-resolution timestamp utilities using the CPU's **RDTSC** (Read Time-Stamp
Counter) instruction. Provides nanosecond-resolution timing without the overhead
of a system call, used for precise frame timing and latency measurements in
camera acquisition loops.

----

Python Wrappers
---------------

The ``common/python/`` directory contains Python wrapper classes that provide
a higher-level interface for managing camera and SLM processes.

``daoHw.py``
^^^^^^^^^^^^^

The top-level daoHw Python module. Imports and re-exports all the wrapper
classes so they can be accessed via a single import:

.. code-block:: python

   from daoHw import *
   # or
   import daoHw

``daoCameraController.py``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Class:** ``cameraController``

A high-level Python wrapper for managing any DAO camera driver process. Handles
shared memory creation, process launch (via ``tmux``), and camera parameter
control through SHM.

.. list-table::
   :header-rows: 1
   :widths: 25 25 50

   * - Parameter
     - Default
     - Description
   * - ``filename``
     - —
     - Base SHM file path (e.g. ``/tmp/wfs.im.shm``)
   * - ``device``
     - —
     - Camera device identifier (IP address, serial, etc.)
   * - ``controller``
     - ``daoHwAravisDeviceCtrl``
     - Executable name of the camera driver
   * - ``width`` / ``height``
     - ``1104``
     - Frame dimensions
   * - ``multicast``
     - ``224.1.1.1``
     - Multicast address for GigE Vision stream

Key methods:

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Method
     - Description
   * - ``createShm()``
     - Create all camera SHM segments (image, Dit, Fps, Gain, …)
   * - ``loadShm()``
     - Open existing SHM segments
   * - ``launch()``
     - Start the camera driver in a tmux session
   * - ``kill()``
     - Stop the camera driver tmux session
   * - ``setExposureTime(dit)``
     - Write exposure time in seconds to the ``Dit`` SHM
   * - ``getExposureTime()``
     - Read current exposure time from the ``Dit`` SHM
   * - ``setFPS(fps)``
     - Write target frame rate to the ``Fps`` SHM
   * - ``getFPS()``
     - Read current frame rate from the ``Fps`` SHM

``daoCameraControlSpilt.py``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Class:** ``cameraControllerSplit``

Variant of ``cameraController`` for cameras that output two sub-images
(e.g. the Bob camera which outputs left and right half-frames separately).
Creates two output SHM segments instead of one.

``daoCameraControllerBob.py``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Class:** ``cameraControllerBob``

Specialised camera controller for the in-house **Bob** detector board.
Extends ``cameraControllerSplit`` with Bob-specific configuration options.

``daoIportController.py``
^^^^^^^^^^^^^^^^^^^^^^^^^^

Python wrapper for managing a **Pleora iPort** camera via the Aravis OCAM2
driver. Handles iPort-specific configuration (OCAM2 descrambling, Camera Link
serial baud rate) alongside the standard SHM camera interface.

``daoFliIportController.py``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Python wrapper for managing a **First Light CRED** camera connected via a
Pleora iPort converter. Combines FLI camera control with iPort GigE Vision
transport management.

``daoSLMController.py``
^^^^^^^^^^^^^^^^^^^^^^^^

**Class:** ``slmController``

High-level Python wrapper for managing any DAO SLM display process.

.. list-table::
   :header-rows: 1
   :widths: 25 25 50

   * - Parameter
     - Default
     - Description
   * - ``filename``
     - —
     - SHM file path for the phase map
   * - ``screen``
     - —
     - Monitor index for the SLM display
   * - ``controller``
     - ``daoSLMOpenCv.py``
     - SLM display driver executable
   * - ``width`` / ``height``
     - ``None``
     - SLM resolution (auto-detected if ``None``)
   * - ``update``
     - ``100``
     - Update rate in Hz

Key methods:

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Method
     - Description
   * - ``createShm()``
     - Create the SLM phase map SHM segment
   * - ``launch()``
     - Start the SLM display driver in a tmux session
   * - ``kill()``
     - Stop the SLM display driver

``daoSLMOpenCv.py`` / ``daoSLMPygame.py`` / ``daoSLMPyQt.py``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Three alternative SLM display backends using **OpenCV**, **pygame**, and
**PyQt5** respectively. All read a phase map from DAO shared memory and
display it fullscreen on the configured monitor. The appropriate backend
is selected via the ``controller`` argument of ``slmController``.

----

Usage Example
-------------

**Start a camera with the Python wrapper:**

.. code-block:: python

   from daoHw import cameraController
   import numpy as np

   cam = cameraController(
       filename='/tmp/wfs.im.shm',
       device='192.168.1.10',
       controller='daoHwAvtControlMain',
       width=1104, height=1104,
   )

   cam.createShm()
   cam.launch()

   cam.setExposureTime(0.002)   # 2 ms
   cam.setFPS(200.0)

   # Read a frame
   import dao
   shm = dao.shm('/tmp/wfs.im.shm')
   frame = shm.get_data(check=True)

**Start an SLM:**

.. code-block:: python

   from daoHw import slmController

   slm = slmController(
       filename='/tmp/sslm.im.shm',
       screen=1,
       controller='daoSLMPygame.py',
       width=1920, height=1200,
   )
   slm.createShm()
   slm.launch()
