GUI Tools
=========

daoHw ships a set of **PyQt5** GUI applications for hardware control and monitoring. All GUIs are installed to ``$DAOROOT/bin`` and require PyQt5 plus the hardware-specific Python modules from each subsystem.

Source: ``gui/``


daoHwCamCtrl
------------

Multi-camera control panel for DAO-supported cameras (Aravis GigE, EDT, FLI, Nüvü, IDS, etc.).

.. code-block:: bash

    python daoHwCamCtrl.py

Features:

- Live image display via an embedded Matplotlib canvas (``FigureCanvas``)
- Camera parameter controls: exposure, gain, frame rate, ROI
- Background subprocess worker (``SubprocessWorker`` / ``QRunnable``) so acquisition commands do not block the GUI
- "Save" functionality that runs the capture command in a background thread and extracts the saved file path from stdout
- Loads the ``.ui`` layout from ``$DAOROOT/data/daoHwCamCtrl.ui`` at runtime

.. note::

    ``DAOROOT`` must be set in the environment before launching. The UI file ``daoHwCamCtrl.ui`` is installed there by ``waf install``.


daoPDUCtrlGui
-------------

GUI for the Rittal CMC III PDU (power distribution unit) via SNMP.

.. code-block:: bash

    python daoPDUCtrlGui.py

Features:

- Table view showing all PDU outlets: socket number, unit, description, LED state, and power status
- Per-outlet toggle buttons (On/Off) that dispatch commands via the ``rittal_pdu_controller.py`` CLI
- ``StatusPoller`` background ``QThread`` polls all outlet states at ~1 Hz using ``get_all_outlets()``
- Colour-coded status cells (green/red) for at-a-glance power state
- Timestamp display for the last successful poll

Requires ``rittal_pdu_controller.py`` (from ``rittal/``) to be importable and a reachable PDU on the network. See :doc:`rittal` for SNMP configuration.


daoLatency
----------

Real-time RTC latency monitoring plot.

.. code-block:: bash

    python daoLatency.py

Features:

- Reads latency measurements from a DAO SHM (a 1×1 float SHM written by the RTC timing process)
- ``dao_latency_acc`` background ``QThread`` accumulates frames, discarding the oldest 20 % when the buffer is full to maintain a rolling window
- Live scatter/line plot via ``pyqtgraph`` showing latency vs. frame index
- Tracks total accumulated frames and missed frames (from SHM counter jumps)
- YAML configuration file support for SHM path and buffer capacity

Requires ``pyqtgraph``:

.. code-block:: bash

    pip install pyqtgraph


daoCLSerialControl
------------------

Serial command terminal for Camera Link (CL) devices that expose a command/response SHM interface.

.. code-block:: bash

    python daoCLSerialControl.py --cmd <cmd_shm> --rsp <rsp_shm>

Features:

- Text entry field with command history (up/down arrow key navigation)
- Sends typed commands into the command SHM; ``MonitorThread`` (``QThread``) watches the response SHM and displays replies in a scrollable log
- Response decoded as UTF-8 (with error replacement) up to the first null byte
- Useful for directly interrogating camera heads (e.g. sending CLHS control strings to EDT or iPort devices)


daoIportSerialControl
---------------------

Identical in layout and function to ``daoCLSerialControl`` but targets **Pleora iPort** Camera Link-to-GigE bridges. Response bytes are decoded as Latin-1 to handle iPort's extended ASCII responses.

.. code-block:: bash

    python daoIportSerialControl.py --cmd <cmd_shm> --rsp <rsp_shm>

See :doc:`iport` for details on the iPort SHM command/response protocol.
