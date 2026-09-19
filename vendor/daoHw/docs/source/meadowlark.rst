Meadowlark Optics — Spatial Light Modulators
=============================================

The ``meadowlark/`` module provides a DAO driver for **Meadowlark Optics** liquid
crystal spatial light modulators (SLMs). Meadowlark SLMs are used in adaptive
optics for wavefront correction (as an alternative to a deformable mirror),
holographic beam shaping, and laboratory calibration.

The driver interfaces with the **Blink SDK** (``Blink_C_wrapper``) and reads phase
maps from DAO shared memory. Multiple SLM boards can be controlled simultaneously
using a threaded approach.

.. contents::
   :local:
   :depth: 2

----

Supported Hardware
------------------

Any Meadowlark SLM supported by the **Blink Plus SDK** can be used. The driver
has been tested with the following:

- Meadowlark 1920×1152 PCIe SLM (visible band)

.. note::
   The Blink SDK and LUT files are Windows-only. The driver is therefore
   designed for Windows control computers.

----

Installation
------------

1. Install the **Meadowlark Optics Blink Plus SDK** from the disc provided with
   the SLM (or from the Meadowlark customer portal).

2. Verify that the default SDK paths are present:

   .. code-block:: text

      C:\Program Files\Meadowlark Optics\Blink Plus\SDK\Blink_C_wrapper.dll
      C:\Program Files\Meadowlark Optics\Blink Plus\SDK\ImageGen.dll
      C:\Program Files\Meadowlark Optics\Blink Plus\LUT Files\slm<serial>_at<nm>_<T>C.LUT

3. Install Python dependencies:

   .. code-block:: bash

      pip install numpy matplotlib

----

Files
-----

``daoMeadowLark.py``
^^^^^^^^^^^^^^^^^^^^^

Multi-threaded SLM controller. Spawns one worker thread per SLM board, each of
which:

1. Loads the factory-calibrated **LUT file** for the SLM
2. Reads the image dimensions from the hardware
3. Opens a DAO shared memory segment
4. Loops, reading phase maps from shared memory and writing them to the SLM board
   via ``Blink_C_wrapper``

**Configuration constants** (edit at the top of the file):

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Constant
     - Description
   * - ``BLINK_C_WRAPPER_PATH``
     - Full path to the ``Blink_C_wrapper`` DLL (Windows)
   * - ``IMAGE_GEN_PATH``
     - Full path to the ``ImageGen`` DLL (Windows)
   * - ``LUT_FILE``
     - Full path to the SLM LUT calibration file

**Key function — ``ThreadedControl``:**

.. code-block:: python

   ThreadedControl(slm_lib, board_number, shm_filename, timeout)

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Parameter
     - Description
   * - ``slm_lib``
     - Handle to the loaded Blink C wrapper DLL
   * - ``board_number``
     - 1-based index of the SLM board (``c_uint``)
   * - ``shm_filename``
     - Path to the DAO shared memory segment containing the phase map
   * - ``timeout``
     - SLM write timeout in milliseconds

**Shared memory interface:**

.. list-table::
   :header-rows: 1
   :widths: 30 20 50

   * - SHM
     - Type
     - Description
   * - ``shm_filename``
     - UINT8 [H×W]
     - Phase map to display (8-bit grayscale, 0–255 maps to 0–2π via LUT)

----

Usage Example
-------------

.. code-block:: python

   import daoMeadowLark
   import dao
   import numpy as np

   # Create the phase map SHM (1152×1920 for a full-frame SLM)
   shm = dao.shm('/tmp/slm1.im.shm',
                 np.zeros((1152, 1920), dtype=np.uint8))

   # Start the controller (runs in a background thread)
   # (see daoMeadowLark.py main block for startup code)

   # Update the phase map
   phase = np.random.randint(0, 256, (1152, 1920), dtype=np.uint8)
   shm.set_data(phase)

.. note::
   Wait-for-trigger is set to **False** by default so the SLM updates
   immediately on each ``set_data`` call. Enable VSync-locked updates
   by calling ``SetWaitForTrigger(board_number, True)`` before starting
   the loop.

.. warning::
   Always load the correct LUT file for your SLM serial number, wavelength,
   and operating temperature. Using the wrong LUT will produce incorrect
   phase depth calibration.
