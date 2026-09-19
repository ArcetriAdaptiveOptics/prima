Applications
============

daoHw ships a small set of command-line utilities for runtime hardware control and network-based latency monitoring.

Source: ``apps/``


Camera Parameter Helpers
-------------------------

These three Python scripts write directly to the camera's control SHM files, allowing runtime adjustment of detector parameters without restarting the camera process.

daoHwSetDit
~~~~~~~~~~~

Set the detector integration time (exposure) for a named camera:

.. code-block:: bash

    daoHwSetDit.py <cameraName> <dit_ms>

``<dit_ms>`` is the integration time in **milliseconds**. The value is converted to microseconds internally and written to ``/tmp/<cameraName>Dit.im.shm``.

Example — set C-Blue exposure to 2 ms:

.. code-block:: bash

    daoHwSetDit.py cblue 2.0

daoHwSetFps
~~~~~~~~~~~

Set the frame rate for a named camera:

.. code-block:: bash

    daoHwSetFps.py <cameraName> <fps>

Writes the target frame rate (in Hz) to ``/tmp/<cameraName>Fps.im.shm``. The camera process reads this SHM and adjusts its timing accordingly.

Example — set to 1000 Hz:

.. code-block:: bash

    daoHwSetFps.py cblue 1000.0

daoHwSetTemp
~~~~~~~~~~~~

Set the detector target temperature for a cooled camera:

.. code-block:: bash

    daoHwSetTemp.py <cameraName> <temperature_C>

Writes the target temperature (in degrees Celsius) to ``/tmp/<cameraName>SetTemp.im.shm``.

Example — cool to −40 °C:

.. code-block:: bash

    daoHwSetTemp.py cblue -40.0


Latency Monitoring
------------------

daoMonitor
~~~~~~~~~~

Command-line application that passively monitors AO RTC end-to-end latency in real time using Cisco **ERSPAN v3** mirrored network traffic (see :doc:`cisco`).

.. code-block:: bash

    daoMonitor --config monitor_config.yaml

Configuration file (YAML):

.. code-block:: yaml

    App_Configuration:
        Erspan_Clock_Resolution: 100e-12       # Cisco switch ERSPAN clock resolution (seconds)
        Erspan_Stream_Interface: eno34          # Network interface receiving ERSPAN traffic
        Erspan_Stream: null                     # ERSPAN stream ID; null = all streams
        Packet_Buffer_Limit: 1000
        Output_Location: /tmp/erspan_demo.im.shm
        Output_Scale_Factor: 1.0               # Scale factor applied to latency values (seconds)
        Include_Readout: true                  # Include camera readout latency
        Include_Slopes: false                  # Include slope computation latency

    Traffic_Register:
      - Type: Camera
        Port: 5123
        IP: 192.168.3.1
      - Type: Slopes
        Port: 9001
        IP: 192.168.3.2

The tool writes per-packet latency values to the configured output SHM. These can be read and plotted live using ``daoMonitorGUI`` or ``daoLatency`` (from daoTools GUI).

.. note::

    ``daoMonitor`` requires ``cap_net_raw`` and ``cap_net_admin`` capabilities to capture raw ERSPAN packets. Grant these after installation:

    .. code-block:: bash

        sudo setcap cap_net_raw,cap_net_admin+ep $DAOROOT/bin/daoMonitor

daoMonitorGUI
~~~~~~~~~~~~~

Qt-based GUI that reads from the latency SHM written by ``daoMonitor`` and displays a live rolling plot.

.. code-block:: bash

    daoMonitorGUI --config monitor_config.yaml

Key configuration parameters (same YAML as ``daoMonitor``):

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Parameter
     - Description

   * - ``latency_shm``
     - Path to the SHM file written by ``daoMonitor`` (default: ``/tmp/dlt-latency.im.shm``).

   * - ``refresh_rate``
     - GUI refresh rate in Hz (default: 5 Hz).

   * - ``buffer_capacity``
     - Number of latency samples to hold in the rolling plot buffer (default: 1000).

   * - ``series_yclip``
     - Y-axis clip value in microseconds for display (default: 1000 µs).

   * - ``hist_density``
     - Histogram bin density for the latency distribution panel.

   * - ``plot_colour``
     - Hex colour string for the plot line (default: ``#b41bcc``).

Requires Qt Charts (``libqt5charts5-dev``) and is built alongside ``daoMonitor`` by waf when Qt is detected.
