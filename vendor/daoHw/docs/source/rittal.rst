Rittal — Power Distribution Unit Control
==========================================

The ``rittal/`` module provides SNMP-based control for **Rittal CMC III**
intelligent power distribution units (PDUs). The PDU controller is used in
DAO instrument racks to remotely switch power outlets on and off — for example,
to cycle lamps, cameras, or controllers without physical access to the rack.

.. contents::
   :local:
   :depth: 2

----

Supported Hardware
------------------

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Device
     - Description
   * - **Rittal CMC III** master PDU
     - Main switchable PDU (outlets 6+ are switched; outlets 1–5 are power-sensor-only)
   * - **Rittal CMC III** slave PDU
     - Secondary switchable PDU on the same CMC III chain

The driver has been tested against a two-PDU CMC III rack configuration:

- **dev 2** — master PDU
- **dev 4** — slave PDU
- **dev 1, dev 3** — CMC III system units (system sensors, login — skipped)

----

Installation
------------

.. code-block:: bash

   pip install pysnmp

.. note::
   ``pysnmp`` v7 is required. The driver uses the async ``hlapi.v3arch.asyncio``
   interface and will not work with pysnmp v4.

----

Files
-----

``rittal_pdu_controller.py``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

SNMP-based PDU control script using **pysnmp v7**. Provides outlet
``status``, ``on``, and ``off`` commands, addressed by outlet index
or by outlet name string.

**Configuration** (edit at the top of the file):

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Constant
     - Description
   * - ``PDU_HOST``
     - IP address of the Rittal CMC III unit (e.g. ``192.168.5.94``)

**OID layout** (from live snmpwalk):

.. list-table::
   :header-rows: 1
   :widths: 55 45

   * - OID
     - Description
   * - ``1.3.6.1.4.1.2606.7.4.3.2.1.3.<dev>.<idx>``
     - Outlet name (STRING)
   * - ``1.3.6.1.4.1.2606.7.4.3.2.1.4.<dev>.<idx>``
     - Outlet state (INTEGER: 10 = OFF, 11 = ON)

**Outlet state integers:**

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Value
     - Meaning
   * - ``10``
     - Outlet is OFF
   * - ``11``
     - Outlet is ON

----

Usage
-----

**Show status of all switchable outlets:**

.. code-block:: bash

   python3 rittal_pdu_controller.py status

**Show status of a specific outlet by index:**

.. code-block:: bash

   python3 rittal_pdu_controller.py status 3

**Show status by outlet name:**

.. code-block:: bash

   python3 rittal_pdu_controller.py status "NGS LAMP1"

**Turn an outlet on:**

.. code-block:: bash

   python3 rittal_pdu_controller.py on 3
   python3 rittal_pdu_controller.py on "NGS LAMP1"

**Turn an outlet off:**

.. code-block:: bash

   python3 rittal_pdu_controller.py off 3
   python3 rittal_pdu_controller.py off "NGS LAMP1"

----

Example Output
--------------

.. code-block:: text

   $ python3 rittal_pdu_controller.py status
   PDU Master (dev 2):
     [6]  NGS LAMP1       ON
     [7]  NGS LAMP2       OFF
     [8]  WFS CAMERA      ON
     [9]  DM CONTROLLER   ON
   PDU Slave (dev 4):
     [6]  AUX POWER 1     OFF
     [7]  AUX POWER 2     OFF

.. warning::
   Turning off a PDU outlet that powers a camera or DM controller during
   an AO loop will abort the run without a clean shutdown. Always
   command a controlled stop before cycling instrument power.
