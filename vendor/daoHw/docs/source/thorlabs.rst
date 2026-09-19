Thorlabs — Spatial Light Modulator
====================================

The ``thorlabs/`` module provides a DAO driver for **Thorlabs** spatial light
modulators (SLMs). The driver renders phase maps from DAO shared memory onto
the SLM display using **VSync-locked OpenGL**, achieving frame-synchronised
updates at the display's native refresh rate (typically 60 Hz).

The SLM is treated as a secondary monitor by the operating system. The driver
opens a fullscreen borderless OpenGL window on the designated display and
continuously textures the viewport with the current phase map read from shared
memory.

.. contents::
   :local:
   :depth: 2

----

Supported Hardware
------------------

The driver renders to any display-based SLM that appears as a monitor to the
operating system. It has been tested with:

- **Thorlabs EXULUS-HD1** — 1920×1200 pixels, DisplayPort

Other Thorlabs SLM models with the same resolution can be used by adjusting
the ``SLM_WIDTH`` and ``SLM_HEIGHT`` constants.

----

Installation
------------

.. code-block:: bash

   pip install pygame PyOpenGL numpy

The SLM display must be connected and appear as a secondary monitor at the
index specified by ``DISPLAY_IDX`` (default: ``1``). On Linux, set the
``DISPLAY`` environment variable to the X server where the SLM is connected:

.. code-block:: bash

   export DISPLAY=:0

----

Files
-----

``thorlabSlm.py``
^^^^^^^^^^^^^^^^^^

VSync-locked SLM display driver. Reads an 8-bit grayscale phase map from
DAO shared memory and renders it as a full-screen texture on the SLM display
at the monitor's native refresh rate using ``pygame`` and OpenGL.

**Configuration constants** (edit at the top of the file):

.. list-table::
   :header-rows: 1
   :widths: 25 15 60

   * - Constant
     - Default
     - Description
   * - ``SLM_WIDTH``
     - ``1920``
     - SLM width in pixels
   * - ``SLM_HEIGHT``
     - ``1200``
     - SLM height in pixels
   * - ``DISPLAY_IDX``
     - ``1``
     - pygame display index (0 = primary monitor, 1 = first secondary, …)
   * - ``SHM_PATH``
     - ``/tmp/sslm.im.shm``
     - Default DAO SHM path; overridable via CLI

**Command line:**

.. code-block:: bash

   python3 thorlabSlm.py [--shm /tmp/sslm.im.shm] [--measure]

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Option
     - Description
   * - ``--shm PATH``
     - Override the shared memory path
   * - ``--measure``
     - Measure the achieved FPS without writing to shared memory (benchmark mode)

**Shared memory interface:**

.. list-table::
   :header-rows: 1
   :widths: 30 20 50

   * - SHM
     - Type
     - Description
   * - ``SHM_PATH``
     - UINT8 [1200×1920]
     - Phase map to display (8-bit grayscale)

**Rendering pipeline:**

1. ``pygame.init()`` detects available displays and opens a fullscreen NOFRAME
   OpenGL window on ``DISPLAY_IDX``.
2. VSync is enabled (``GL_SWAP_CONTROL = 1``) to lock updates to the monitor
   refresh rate.
3. A single OpenGL texture (``GL_RED``, ``GL_UNSIGNED_BYTE``) is allocated at
   startup. Each frame the texture is updated with ``glTexSubImage2D`` and
   rendered as a full-screen quad.
4. The main loop polls the DAO SHM for new data using ``get_data(check=True)``
   (semaphore-gated) and updates the texture only when new data is available.

.. note::
   ``glFinish()`` is called after each ``display.flip()`` to ensure the GPU
   has completed rendering before the SHM is read again. This prevents tearing
   but may add a small latency penalty.

----

Usage Example
-------------

.. code-block:: bash

   # Create the phase map SHM
   python3 -c "
   import dao, numpy as np
   dao.shm('/tmp/sslm.im.shm', np.zeros((1200, 1920), dtype=np.uint8))
   "

   # Start the SLM display on monitor 1
   DISPLAY=:0 python3 thorlabSlm.py --shm /tmp/sslm.im.shm

**Update the SLM from another process:**

.. code-block:: python

   import dao
   import numpy as np

   slm = dao.shm('/tmp/sslm.im.shm')

   # Write a flat (zero-phase) pattern
   slm.set_data(np.zeros((1200, 1920), dtype=np.uint8))

   # Write a blazed grating (2π ramp along x)
   x = np.tile(np.arange(1920, dtype=np.uint8), (1200, 1))
   slm.set_data(x)

.. tip::
   Use the ``--measure`` flag to verify that the display is achieving its
   target frame rate before integrating with the AO control loop:

   .. code-block:: bash

      DISPLAY=:0 python3 thorlabSlm.py --measure
      # Detected 2 display(s)
      # FPS: 60.0
