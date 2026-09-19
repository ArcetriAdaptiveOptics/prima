PI — Tip-Tilt Mirror Controllers
==================================

The ``pi/`` module provides a DAO driver for **Physik Instrumente (PI)** piezo
controllers used to drive **tip-tilt mirrors (TTM)** in adaptive optics systems.
The driver reads command values from a DAO shared memory segment and sends them
to the PI controller over Ethernet using the **pipython** library.

.. contents::
   :local:
   :depth: 2

----

Supported Controllers
---------------------

.. list-table::
   :header-rows: 1
   :widths: 25 25 50

   * - Model
     - Type
     - Notes
   * - PI E-518
     - 3-channel piezo servo controller
     - Primary target; controls two tip/tilt axes (channels A and B)

Any PI controller supported by the **pipython** GCS 2.0 API can in principle
be used, as the driver uses the generic ``GCSDevice`` interface.

----

Installation
------------

.. code-block:: bash

   pip install pipython

The PI controller must be reachable over the network. Configure a static IP
address on the controller's Ethernet interface and verify connectivity with
``ping`` before starting the driver.

----

Files
-----

``daoHwPiTtCtrl.py``
^^^^^^^^^^^^^^^^^^^^^

Python daemon that reads a two-element command array from a DAO shared memory
segment and applies the values to the PI controller's tip (axis A) and tilt
(axis B) channels in a tight loop.

**Usage:**

.. code-block:: bash

   daoHwPiTtCtrl.py <shmName> <ip> <ctrlModel> [--center A,B]

**Arguments:**

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Argument
     - Description
   * - ``shmName``
     - Path to the command shared memory segment (e.g. ``/tmp/ttm1Cmd.im.shm``)
   * - ``ip``
     - IP address of the PI controller (e.g. ``192.168.68.47``)
   * - ``ctrlModel``
     - Controller model string (e.g. ``E-518``)
   * - ``--center A,B``
     - Center / zero-point position in controller units 0–100 (default: ``50.0,50.0``)

**Shared memory interface:**

.. list-table::
   :header-rows: 1
   :widths: 30 20 50

   * - SHM
     - Type
     - Description
   * - ``shmName``
     - FLOAT32 [2]
     - Command: ``[tip_offset, tilt_offset]`` in controller units (0–100)

The driver adds the ``--center`` offset to the command values before sending
to the controller, so a command of ``[0.0, 0.0]`` always maps to the configured
centre position.

----

Usage Examples
--------------

.. code-block:: bash

   # Start TTM 1 controller
   python3 daoHwPiTtCtrl.py /tmp/ttm1Cmd.im.shm 192.168.68.47 E-518

   # Start TTM 2 controller with a custom centre
   python3 daoHwPiTtCtrl.py /tmp/ttm2Cmd.im.shm 192.168.68.48 E-518 --center 55.0,45.0

**Sending a command from Python:**

.. code-block:: python

   import dao
   import numpy as np

   cmd_shm = dao.shm('/tmp/ttm1Cmd.im.shm')

   # Apply +2 units tip, -1 unit tilt (relative to centre)
   cmd_shm.set_data(np.array([2.0, -1.0], dtype=np.float32))

   # Return to centre
   cmd_shm.set_data(np.array([0.0, 0.0], dtype=np.float32))

.. note::
   Controller units are 0–100 (percent of full range). For the PI E-518 the
   default centre of 50.0 corresponds to the mid-travel position. Physical
   stroke and sensitivity depend on the actuator model; consult the PI datasheet
   for your specific mirror/actuator combination.

.. warning::
   Sending commands beyond the controller's configured range will saturate
   the output at the hardware limit. Always verify the safe operating range
   with the PI controller's own software before closing the AO loop.
