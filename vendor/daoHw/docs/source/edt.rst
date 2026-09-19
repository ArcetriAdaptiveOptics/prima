EDT — Camera Link Frame Grabber Cameras
=========================================

The ``edt/`` module provides DAO drivers for Camera Link cameras connected via
`EDT <https://edt.com/>`_ (Engineering Design Team) PCIe frame grabber cards.
EDT frame grabbers are widely used in high-speed scientific imaging; the ``edtinc.h``
SDK provides a unified API for configuring and streaming from any Camera Link device.

All drivers in this module write acquired frames to DAO shared memory segments
and expose camera control parameters through dedicated control shared memory
segments. Camera Link serial communication (for exposure, gain, etc.) is handled
through the EDT card's on-board UART.

.. contents::
   :local:
   :depth: 2

----

Installation
------------

The EDT PCI/PCIe SDK (``pdv`` package) must be installed before building the
daoHw EDT drivers. Follow the installation guide from EDT:
https://edt.com/developer-resources/

The SDK installs ``edtinc.h`` and associated libraries which the daoHw build
system detects automatically via ``pkg-config`` or the ``EDTDIR`` environment
variable.

----

Core Files
----------

``daoEdtCtrl.c``
^^^^^^^^^^^^^^^^^

The base EDT acquisition controller. Opens the EDT device (``/dev/pdv0`` or
similar), sets the Camera Link configuration file, and runs a multi-threaded
acquisition loop that double-buffers frames from the EDT DMA engine into DAO
shared memory.

Key features:

- Configures the EDT card via a ``.cfg`` Camera Link description file
- Spawns a dedicated camera reader thread pinned to a real-time priority
- Spawns a camera control thread that monitors control shared memory segments
  and forwards serial commands to the camera via the EDT UART
- Spawns an event thread for DAO event handling
- Handles ``SIGINT`` / ``SIGTERM`` for clean shutdown

``daoEdtJoe.py``
^^^^^^^^^^^^^^^^^

Python helper script for managing EDT-based ``Joe`` detector boards.  Provides
command-line utilities for loading camera configurations, resetting the frame
grabber, and verifying the Camera Link signal.

----

Supported Cameras
-----------------

``daoEdtOCAM2kCtrl.c``
^^^^^^^^^^^^^^^^^^^^^^^^

Controller for the **First Light OCAM2k** (1024×1024 EM-CCD) connected via
Camera Link and EDT frame grabber. OCAM2k is one of the fastest low-noise
EM-CCDs available and is commonly used as a Shack-Hartmann wavefront sensor
detector in high-order AO systems.

Features:

- Full 1024×1024 frame acquisition at up to 1500 fps
- EM gain control via Camera Link serial
- Exposure (DIT) and frame rate (FPS) control
- Hardware external trigger support
- OCAM2k pixel descrambling (the camera outputs pixels in a non-trivial order)

Shared memory segments created:

.. list-table::
   :header-rows: 1
   :widths: 30 20 50

   * - SHM name suffix
     - Type
     - Description
   * - (base name)
     - UINT16 [1024×1024]
     - Descrambled image frame
   * - ``Dit``
     - FLOAT32 [1]
     - Exposure time in seconds
   * - ``Fps``
     - FLOAT32 [1]
     - Frame rate in Hz
   * - ``EmGain``
     - FLOAT32 [1]
     - EM gain multiplier

``daoEdtCRED1Ctrl.c``
^^^^^^^^^^^^^^^^^^^^^^

Controller for the **First Light CRED1** (320×256 InGaAs SWIR camera) connected
via Camera Link and EDT frame grabber. CRED1 provides sub-electron noise
performance in the 0.9–1.7 µm band, making it the detector of choice for
near-infrared wavefront sensing.

Features:

- Up to 3500 fps at full frame in sub-windowed mode
- DIT, FPS, and gain control via Camera Link serial
- Temperature set point monitoring
- External trigger mode

``daoEdtBigJoeCtrl.c``
^^^^^^^^^^^^^^^^^^^^^^^^

Controller for the **Andor iXon (BigJoe)** EMCCD camera connected via a
custom Camera Link interface. BigJoe refers to a large-format Andor EM-CCD
used in prototype and laboratory AO benches at Durham.

``daoEdtLilJoeCtrl.c``
^^^^^^^^^^^^^^^^^^^^^^^^

Controller for the **Andor iXon (LilJoe)** — a smaller-format Andor EM-CCD
variant used in bench setups where compactness is important.

``daoEdtLJCtrl.c``
^^^^^^^^^^^^^^^^^^^^

Controller for the **LJ** detector (a variant of the Joe detector family).
Provides the same DIT/FPS/gain shared memory interface as the other Joe
controllers.

----

Shared Memory Layout
--------------------

All EDT camera drivers follow the same shared memory naming convention:

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
     - Exposure / integration time in seconds
   * - ``Fps``
     - FLOAT32 [1]
     - Frame rate in Hz
   * - ``Gain``
     - FLOAT32 [1]
     - Analogue gain
   * - ``EmGain``
     - FLOAT32 [1]
     - EM gain (EM-CCD cameras only)
   * - ``TargetTemp``
     - FLOAT32 [1]
     - Sensor cooling set point in °C
   * - ``CurrentTemp``
     - FLOAT32 [1]
     - Current sensor temperature in °C (read-only)

----

Usage Example
-------------

.. code-block:: bash

   # Start OCAM2k driver, writing frames to /tmp/ocam.im.shm
   daoEdtOCAM2kCtrl -S /tmp/ocam -L

   # Start CRED1 driver
   daoEdtCRED1Ctrl -S /tmp/cred1 -L

   # Set exposure time to 1 ms
   python3 -c "
   import dao, numpy as np
   s = dao.shm('/tmp/ocamDit.im.shm')
   s.set_data(np.array([0.001], dtype=np.float32))
   "

.. note::
   The ``-L`` flag enables DAO logging output. The ``-S`` argument specifies
   the base shared memory path; control SHMs are automatically appended with
   their suffix (``Dit``, ``Fps``, etc.).

See also :doc:`fli` for the FLI SDK path to CRED1/CRED2 cameras, and
:doc:`aravis` for GigE Vision cameras.
