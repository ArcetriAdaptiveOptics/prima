FLI — First Light Imaging CRED Cameras
========================================

The ``fli/`` module provides DAO drivers for **First Light Imaging (FLI)** CRED-series
infrared cameras using the **FLI SDK** (``FliSdk_V2``). These are among the lowest-noise
infrared cameras available and are widely used as wavefront sensor detectors in
near-infrared adaptive optics systems.

The module also includes a Camera Link acquisition path for CRED1 via EDT frame
grabbers (``daoFliEdtCred1Ctrl.c``), which pre-dates the FLI SDK and is maintained
for legacy hardware setups.

.. contents::
   :local:
   :depth: 2

----

Supported Cameras
-----------------

.. list-table::
   :header-rows: 1
   :widths: 20 20 60

   * - Camera
     - Sensor
     - Notes
   * - CRED1
     - 320×256 InGaAs (SWIR)
     - Near-IR (0.9–1.7 µm), sub-electron noise; supported via FLI SDK and via EDT Camera Link
   * - CRED2
     - 640×512 InGaAs (SWIR)
     - 1.7–2.5 µm band; controlled via FLI SDK ``FliCredTwo``
   * - CRED3
     - 640×512 InGaAs
     - Controlled via FLI SDK ``FliCredThree``; lowest readout noise variant

----

Installation
------------

The FLI SDK must be installed and the ``FLISDK_DIR`` environment variable set
to its installation path before the Python scripts can be used:

.. code-block:: bash

   export FLISDK_DIR=/opt/FliSdk

   # Add the Python bindings to your path
   export PYTHONPATH=$FLISDK_DIR/Python/lib:$PYTHONPATH

For the EDT Camera Link path (CRED1 only), see :doc:`edt` for EDT SDK
installation instructions.

----

Files
-----

``cred.py``
^^^^^^^^^^^

Minimal interactive daemon for **CRED2/CRED3** cameras via the FLI SDK.
Designed to be launched with ``ipython3 -i`` so that the camera object is
accessible at an interactive prompt for quick parameter changes.

Key functions:

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Function
     - Description
   * - ``getImage(context)``
     - Block until a new frame is available and return it as a NumPy array
   * - ``setFps(context, fps)``
     - Set the frame rate and confirm the new value
   * - ``setTint(context, tInt)``
     - Set integration time (supports CRED2 and CRED3 variants automatically)
   * - ``getTint(context)``
     - Read back current integration time and its min/max limits
   * - ``get_roi()``
     - Return the current region-of-interest as ``[x, y, width, height]``

``cred1Init.py``
^^^^^^^^^^^^^^^^

Initialisation script for the **CRED1** camera via the FLI SDK. Sets up the
camera connection, configures the default frame rate and exposure, and
starts the DAO shared memory segment before handing control to the
acquisition loop.

``cred2CL.py``
^^^^^^^^^^^^^^

Full-featured, thread-safe daemon for the **CRED2** camera. Uses a command
queue to ensure all FLI SDK calls are serialised within the acquisition thread,
preventing conflicts between frame grabbing and serial control commands.

Key design principles:

- A single acquisition thread owns all ``FliSdk.*`` calls.
- Control operations (``setFps``, ``setTint``, ``setGain``) are enqueued
  asynchronously and applied between frames.
- Synchronous getters block the caller until the acquisition thread can
  safely execute them.
- The camera is stopped and restarted around control commands to avoid
  interleaving image and serial traffic.

Key functions:

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Function
     - Description
   * - ``setFps(fps)``
     - Set frame rate (enqueued, applied between frames)
   * - ``setTint(tInt)``
     - Set integration time in µs (enqueued)
   * - ``setGain(gain)``
     - Set analogue gain (enqueued)
   * - ``setExtSynchro(enable)``
     - Enable or disable external synchronisation trigger (enqueued)
   * - ``getFps()``
     - Read back current frame rate (synchronous)
   * - ``getTemp()``
     - Read current sensor temperature (synchronous)
   * - ``get_roi()``
     - Read current ROI state from the camera

``daoFliEdtCred1Ctrl.c``
^^^^^^^^^^^^^^^^^^^^^^^^^

Legacy C driver for the **CRED1** camera connected via **Camera Link** and an
**EDT frame grabber**. This path pre-dates the FLI SDK and uses the EDT ``edtinc.h``
API for frame acquisition and the Camera Link serial channel for camera control.

Provides the same shared memory interface as the EDT module drivers:

.. list-table::
   :header-rows: 1
   :widths: 30 20 50

   * - SHM name suffix
     - Type
     - Description
   * - (base name)
     - UINT16 [320×256]
     - Acquired image frame
   * - ``Dit``
     - FLOAT32 [1]
     - Integration time in seconds
   * - ``Fps``
     - FLOAT32 [1]
     - Frame rate in Hz
   * - ``TargetTemp``
     - FLOAT32 [1]
     - Cooling set point in °C
   * - ``CurrentTemp``
     - FLOAT32 [1]
     - Current sensor temperature in °C

----

Shared Memory Layout (FLI SDK path)
-------------------------------------

.. list-table::
   :header-rows: 1
   :widths: 30 20 50

   * - SHM name suffix
     - Type
     - Description
   * - (base name)
     - UINT16 [H×W]
     - Acquired image frame (size matches ROI)
   * - ``Dit``
     - FLOAT32 [1]
     - Integration time in seconds
   * - ``Fps``
     - FLOAT32 [1]
     - Target frame rate in Hz

----

Usage Example
-------------

.. code-block:: bash

   # Launch the CRED2 daemon in interactive mode
   FLISDK_DIR=/opt/FliSdk ipython3 -i cred2CL.py

   # Once running, set exposure and frame rate from the prompt
   In [1]: setTint(2500)   # 2.5 ms
   In [2]: setFps(400.0)
   In [3]: getTemp()

.. note::
   For production use, ``cred2CL.py`` should be launched as a background
   service. The control functions can then be called from a separate Python
   process that imports the module, or via DAO shared memory control segments.

See also :doc:`edt` for the Camera Link / EDT acquisition path.
