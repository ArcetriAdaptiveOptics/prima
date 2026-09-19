Arcus — Motor Controllers
===========================

The ``arcus/`` module provides a DAO driver for **Arcus Technology** stepper
motor controllers. Arcus controllers are used in adaptive optics benches to
drive focusers, filter wheels, and other motorised optomechanical components.

.. contents::
   :local:
   :depth: 2

----

Supported Controllers
---------------------

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Model
     - Description
   * - **ACE-SDE**
     - Single-axis stepper drive with USB (Windows) and RS-232 serial interfaces

----

Installation
------------

**Serial interface (Linux and Windows):**

.. code-block:: bash

   pip install pyserial

**USB interface (Windows only):**

The Arcus USB driver DLL (``ACE.dll``) must be installed via the Arcus device
driver package. The ``ACE_SDE`` class will detect whether the system is Windows
and load the USB interface automatically.

.. note::
   The USB interface is only supported on Windows. On Linux, use the serial
   interface (``/dev/ttyUSBx`` or ``/dev/ttyACMx``).

----

Files
-----

``daoAceSde.py``
^^^^^^^^^^^^^^^^^

Python control library for the Arcus ACE-SDE motor controller.
Supports both the **USB** (Windows, via ``ACE.dll`` ctypes interface) and
**RS-232 serial** (cross-platform, via ``pyserial``) communication methods.

**Class:** ``ACE_SDE``

.. code-block:: python

   from daoAceSde import ACE_SDE

   # Open via serial (Linux / Windows)
   ctrl = ACE_SDE(serialPort='/dev/ttyUSB0')

   # Open via USB (Windows only, uses ACE.dll)
   ctrl = ACE_SDE()

The constructor automatically detects the communication type and verifies
the connection by querying the device name and firmware version.

**Key methods:**

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Method
     - Description
   * - ``send(command)``
     - Send a raw ASCII command to the controller and return the response string
   * - ``cleanup()``
     - Close the communication channel (called automatically at exit)

The ACE-SDE uses a simple ASCII command protocol. Common commands:

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Command
     - Description
   * - ``DN``
     - Query device name
   * - ``VER``
     - Query firmware version
   * - ``X``
     - Query current motor position (steps)
   * - ``MR<steps>``
     - Move relative by ``<steps>`` steps (positive = forward)
   * - ``MA<pos>``
     - Move absolute to position ``<pos>``
   * - ``HSPD<n>``
     - Set high speed (steps/s)
   * - ``LSPD<n>``
     - Set low speed / start speed (steps/s)
   * - ``ACC<n>``
     - Set acceleration (steps/s²)
   * - ``STOP``
     - Immediate motor stop

**Internal constants:**

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Constant
     - Description
   * - ``DEVICE_BAUDRATE``
     - ``9600`` — fixed by the Arcus hardware specification
   * - ``BUFFER_SIZE``
     - ``64`` — the device expects 64-byte buffers for all read/write operations

----

Usage Example
-------------

.. code-block:: python

   from daoAceSde import ACE_SDE

   # Connect to controller on COM3 (Windows) or /dev/ttyUSB0 (Linux)
   motor = ACE_SDE(serialPort='/dev/ttyUSB0')

   # Query position
   pos = motor.send('X')
   print(f"Current position: {pos} steps")

   # Move +500 steps
   motor.send('MR500')

   # Move to absolute position 0
   motor.send('MA0')

   # Clean up
   motor.cleanup()

**Typical focuser loop:**

.. code-block:: python

   import time
   from daoAceSde import ACE_SDE

   motor = ACE_SDE(serialPort='/dev/ttyUSB0')
   motor.send('HSPD5000')
   motor.send('LSPD500')
   motor.send('ACC2000')

   for step in range(0, 10000, 500):
       motor.send(f'MA{step}')
       time.sleep(0.5)
       print(f"Position: {motor.send('X')}")

.. note::
   The ACE-SDE does not natively report a "move complete" status over serial.
   Allow sufficient time for the move to complete based on the configured speed
   and acceleration, or poll the position register until it stabilises.
