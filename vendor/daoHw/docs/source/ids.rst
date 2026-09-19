IDS — uEye Cameras
===================

The ``ids/`` module provides a DAO driver for **IDS Imaging** uEye cameras.
uEye cameras are compact, cost-effective USB 2.0/3.0 and GigE Vision cameras
suitable for visible-band wavefront sensing, pupil imaging, and alignment tasks
in adaptive optics benches.

The driver is implemented in Python using the official **pyueye** bindings
provided with the IDS Software Suite.

.. contents::
   :local:
   :depth: 2

----

Supported Cameras
-----------------

Any camera supported by the IDS uEye SDK (``libueye_api.so``) can be used,
including:

- uEye USB 2.0 / USB 3.0 cameras (compact UI series)
- uEye GigE cameras (GC / GT series)

The driver has been tested primarily with monochrome 8-bit models in the
**UI-3060CP** and **UI-1540LE** families.

----

Installation
------------

1. Install the IDS Software Suite from https://en.ids-imaging.com/downloads.html.
   This installs ``/usr/lib/libueye_api.so`` and the uEye daemon (``ueyeusbdrc``
   for USB, ``ueyeethdrc`` for GigE).

2. Install the Python bindings:

   .. code-block:: bash

      pip install pyueye

3. Start the appropriate IDS daemon before running the driver:

   .. code-block:: bash

      # USB cameras
      sudo ueyeusbdrc start

      # GigE cameras
      sudo ueyeethdrc start

----

Files
-----

``daoUeyeCtrl.py``
^^^^^^^^^^^^^^^^^^^

Full-featured uEye camera driver that streams frames into DAO shared memory.
Implements DIT, gain, and FPS control via shared memory segments, and supports
flexible ROI configuration.

**Class:** ``UeyeShmApp``

Constructor parameters:

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Parameter
     - Description
   * - ``shm_image_name``
     - Path to the output image shared memory segment
   * - ``shm_dit_name``
     - Path to the DIT (exposure) control SHM
   * - ``shm_gain_name``
     - Path to the gain control SHM
   * - ``shm_fps_name``
     - Path to the FPS control SHM
   * - ``shm_roi_name``
     - (optional) Path to an ROI SHM ``[x, y, w, h]`` that overrides CLI ROI
   * - ``roi_x``, ``roi_y``
     - Top-left corner of the ROI (default: 0, 0)
   * - ``roi_w``, ``roi_h``
     - ROI dimensions (default: full sensor)

**ROI precedence** (highest to lowest):

1. SHM ROI (``--shm-roi`` argument) — can be updated at runtime
2. CLI ROI (``--roi-x``, ``--roi-y``, ``--roi-w``, ``--roi-h``)
3. Full sensor

**Shared memory segments:**

.. list-table::
   :header-rows: 1
   :widths: 30 20 50

   * - SHM name
     - Type
     - Description
   * - ``shm_image_name``
     - UINT8 [H×W]
     - Acquired image frame (8-bit monochrome)
   * - ``shm_dit_name``
     - FLOAT32 [1]
     - Exposure time in milliseconds
   * - ``shm_gain_name``
     - FLOAT32 [1]
     - Analogue gain (0–100, camera-specific units)
   * - ``shm_fps_name``
     - FLOAT32 [1]
     - Target frame rate in Hz (read-back after hardware limit clamping)
   * - ``shm_roi_name``
     - INT32 [4]
     - Optional ROI: ``[x, y, width, height]``

----

Usage Example
-------------

**Command line:**

.. code-block:: bash

   python3 daoUeyeCtrl.py \
       --image   /tmp/ueye.im.shm \
       --dit     /tmp/ueyeDit.im.shm \
       --gain    /tmp/ueyeGain.im.shm \
       --fps     /tmp/ueyeFps.im.shm \
       --roi-w   512 --roi-h 512

**Adjusting parameters at runtime:**

.. code-block:: python

   import dao
   import numpy as np

   # Set exposure to 5 ms
   dao.shm('/tmp/ueyeDit.im.shm').set_data(np.array([5.0], dtype=np.float32))

   # Set gain to 50 %
   dao.shm('/tmp/ueyeGain.im.shm').set_data(np.array([50.0], dtype=np.float32))

   # Set frame rate to 100 Hz
   dao.shm('/tmp/ueyeFps.im.shm').set_data(np.array([100.0], dtype=np.float32))

   # Update ROI at runtime (if shm_roi_name was set)
   dao.shm('/tmp/ueyeRoi.im.shm').set_data(
       np.array([64, 64, 256, 256], dtype=np.int32))

.. note::
   The IDS uEye SDK clamps frame rate to the hardware maximum for the
   current exposure and ROI settings. The actual frame rate is read back
   and written to ``shm_fps_name`` after any parameter change.
