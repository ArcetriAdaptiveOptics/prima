Nüvü — EM-CCD Cameras
=======================

The ``nuvu/`` module provides DAO drivers for **Nüvü Camēras** electron-multiplying
CCD cameras. The Nüvü 512 series uses Nüvü's proprietary **nc_driver** SDK and
provides ultra-low noise imaging, making it an excellent wavefront sensor detector
for visible-band high-order AO systems.

All drivers in this module write acquired frames to DAO shared memory segments
and expose a rich set of camera control parameters through dedicated control
shared memory segments, following the same naming convention as the EDT drivers.

.. contents::
   :local:
   :depth: 2

----

Supported Cameras
-----------------

.. list-table::
   :header-rows: 1
   :widths: 25 20 55

   * - Camera
     - Sensor
     - Notes
   * - Nüvü 512
     - 512×512 EM-CCD
     - Single full-frame mode; standard acquisition path
   * - Nüvü 512 Multi-ROI
     - 512×512 EM-CCD
     - Up to 3 simultaneous regions-of-interest
   * - Nüvü 512 Single
     - 512×512 EM-CCD
     - Simplified single-ROI acquisition path

----

Installation
------------

The Nüvü ``nc_driver`` SDK must be installed and ``nc_driver.h`` available in
the compiler include path. Contact Nüvü Camēras for the SDK distribution for
your Linux kernel version.

----

Files
-----

``daoNuvu512Ctrl.c``
^^^^^^^^^^^^^^^^^^^^^

Base acquisition controller for the **Nüvü 512** camera. Opens the camera
via ``nc_driver``, configures binning, EM gain, and readout mode, and runs
a frame acquisition loop that writes each frame to DAO shared memory.

Shared memory segments created:

.. list-table::
   :header-rows: 1
   :widths: 30 20 50

   * - SHM name suffix
     - Type
     - Description
   * - (base name)
     - UINT16 [512×512]
     - Acquired image frame
   * - ``Dit``
     - FLOAT32 [1]
     - Integration time in seconds
   * - ``Fps``
     - FLOAT32 [1]
     - Frame rate in Hz
   * - ``Gain``
     - FLOAT32 [1]
     - Analogue gain
   * - ``EmGain``
     - FLOAT32 [1]
     - EM gain multiplier (1 = no multiplication)
   * - ``TargetTemp``
     - FLOAT32 [1]
     - Sensor cooling set point in °C
   * - ``CurrentTemp``
     - FLOAT32 [1]
     - Current sensor temperature in °C (read-only)

``daoNuvu512SingleCtrl.c``
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Simplified controller for the Nüvü 512 that acquires a single ROI at a
fixed size. Useful when multi-ROI capability is not required and the
simpler code path is preferred.

``daoNuvu512MultiCtrl.c``
^^^^^^^^^^^^^^^^^^^^^^^^^^

Full-featured multi-ROI controller for the **Nüvü 512**. Supports up to
**three simultaneous regions-of-interest** (ROIs), each writing to its own
DAO shared memory image. This allows the same EM-CCD to simultaneously
serve, for example, a high-order Shack-Hartmann sensor and a low-order
sensor.

**Command line:**

.. code-block:: bash

   daoNuvu512MultiCtrl -S imgName nbRoiName roi0Img roi1Img roi2Img extTrigName -L

Shared memory segments created (in addition to the base set):

.. list-table::
   :header-rows: 1
   :widths: 30 20 50

   * - SHM name suffix
     - Type
     - Description
   * - ``<roi0Img>Pos``
     - UINT32 [2]
     - ROI 0 position: (posX, posY) in pixels
   * - ``<roi1Img>Pos``
     - UINT32 [2]
     - ROI 1 position: (posX, posY) in pixels
   * - ``<roi2Img>Pos``
     - UINT32 [2]
     - ROI 2 position: (posX, posY) in pixels
   * - ``NbRoi``
     - UINT32 [1]
     - Number of active ROIs (1–3)
   * - (extTrigName)
     - UINT32 [1]
     - External trigger enable flag

.. note::
   ROI sizes are determined by the dimensions of the corresponding output
   SHM segments. ROI positions are read from the ``Pos`` SHMs. The multi-ROI
   buffer layout is assumed to be contiguous: ``[ROI0][ROI1][ROI2]``.

----

Multi-ROI Usage Example
-----------------------

.. code-block:: bash

   # Create output SHMs for 3 ROIs (64×64, 32×32, 32×32)
   python3 -c "
   import dao, numpy as np
   dao.shm('/tmp/wfs.im.shm',    np.zeros((64, 64), dtype=np.uint16))
   dao.shm('/tmp/wfsRoi1.im.shm', np.zeros((32, 32), dtype=np.uint16))
   dao.shm('/tmp/wfsRoi2.im.shm', np.zeros((32, 32), dtype=np.uint16))
   "

   # Start the multi-ROI controller
   daoNuvu512MultiCtrl -S /tmp/wfs /tmp/wfsNbRoi \
       /tmp/wfsRoi0 /tmp/wfsRoi1 /tmp/wfsRoi2 /tmp/wfsExtTrig -L

   # Move ROI 0 to position (100, 200)
   python3 -c "
   import dao, numpy as np
   s = dao.shm('/tmp/wfsPos.im.shm')
   s.set_data(np.array([100, 200], dtype=np.uint32))
   "

----

EM Gain and Temperature Control
--------------------------------

All Nüvü drivers expose EM gain and temperature via shared memory. A simple
pattern for adjusting these from Python:

.. code-block:: python

   import dao
   import numpy as np

   # Set EM gain to 100
   emgain_shm = dao.shm('/tmp/wfsEmGain.im.shm')
   emgain_shm.set_data(np.array([100.0], dtype=np.float32))

   # Monitor current temperature
   temp_shm = dao.shm('/tmp/wfsCurrentTemp.im.shm')
   print(f"Sensor temperature: {temp_shm.get_data()[0]:.1f} °C")

.. warning::
   EM gain should not be changed while the camera is acquiring at high frame
   rates. Use the external trigger SHM to pause acquisition before adjusting
   EM gain to avoid charge multiplication damage to the sensor.
