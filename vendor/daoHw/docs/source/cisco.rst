Cisco — ERSPAN Network Packet Capture
======================================

The ``cisco/`` module provides a C++ header library for capturing and parsing
**Cisco ERSPAN v3** (Encapsulated Remote SPAN) network packets. ERSPAN is a
Cisco protocol that mirrors network traffic from a switch port across the IP
network to a monitoring host.

In DAO instrument systems, ERSPAN is used to capture and analyse GigE Vision
camera traffic — for example, to diagnose frame drops, measure packet timing,
or reconstruct frames from a network tap without modifying the camera's IP
configuration.

.. contents::
   :local:
   :depth: 2

----

Overview
--------

ERSPAN v3 encapsulates mirrored Ethernet frames inside GRE (Generic Routing
Encapsulation) packets. The ``daoErspan.hpp`` library:

1. Opens a raw socket on the specified network interface (Linux only)
2. Applies a BPF (Berkeley Packet Filter) to select only ERSPAN/GRE packets
3. Parses the ERSPAN v3 header and extracts the inner IP packet
4. Delivers a ``Packet_Summary`` structure to a user-provided callback

The library is header-only and is included with a single ``#include``.

.. note::
   Raw socket capture requires either ``CAP_NET_RAW`` capability or root
   privileges. Grant the capability to the binary with:

   .. code-block:: bash

      sudo setcap cap_net_raw,cap_net_admin+ep ./myApp

----

Installation
------------

No external dependencies beyond a C++17 compiler and Linux system headers.
The library uses:

- ``sys/socket.h`` — raw socket creation
- ``linux/if_packet.h`` — packet socket
- ``linux/filter.h`` — BPF filter attachment
- ``arpa/inet.h`` — IP address parsing
- ``daoLog.hpp`` — DAO logging (from daoBase)

----

Files
-----

``daoErspan.hpp``
^^^^^^^^^^^^^^^^^^

Header-only C++ library in the ``Dao::Erspan`` namespace.

**Compile-time configuration:**

Define ``DAO_ERSPAN_RETENTION`` before including the header to control how
many bytes of the inner payload are retained in each ``Packet_Summary``:

.. code-block:: cpp

   #define DAO_ERSPAN_RETENTION 400   // retain up to 400 bytes of payload
   #include <daoErspan.hpp>

Default is ``200`` bytes.

**Key types:**

``Dao::Erspan::Packet_Summary``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Populated for each received packet and passed to the user callback:

.. code-block:: cpp

   struct Packet_Summary {
       struct {
           uint64_t timestamp;  // ERSPAN hardware timestamp
       } Erspan;

       struct {
           std::string src;             // Source IP address (string)
           std::string dest;            // Destination IP address (string)
           uint8_t protocol;            // IP protocol number (e.g. 0x11 = UDP)
           size_t payloadFullLen;       // Full inner payload length in bytes
           std::byte payloadSample[DAO_ERSPAN_RETENTION]; // Retained payload bytes
       } IP;
   };

**Key masks and constants:**

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Constant / Macro
     - Description
   * - ``DAO_ERSPAN_RETENTION``
     - Number of payload bytes retained per packet (default: 200)
   * - ``MAX_PACKET_SIZE``
     - Maximum raw packet size (``0xFFFF`` = 65535 bytes)
   * - ``ERSPAN_MASK_STREAM``
     - Mask for the ERSPAN stream ID field (10 bits, ``0x3FF``)
   * - ``ERSPAN_MASK_VLAN``
     - Mask for the VLAN tag (12 bits, ``0xFFF``)
   * - ``ERSPAN_MASK_TIMESTAMP``
     - Mask for the ERSPAN hardware timestamp field
   * - ``PKT_DROP(expr, msg, logger)``
     - Helper macro: if ``expr`` is true, log ``msg`` and skip the packet

----

Usage Example
-------------

.. code-block:: cpp

   #define DAO_ERSPAN_RETENTION 300
   #include <daoErspan.hpp>
   #include <daoLog.hpp>
   #include <iostream>

   int main()
   {
       DaoLog logger("erspan_example");

       // Instantiate the capture engine on interface "eth0"
       Dao::Erspan::Capture capture("eth0", logger);

       // Register a packet handler callback
       capture.setHandler([](const Dao::Erspan::Packet_Summary &pkt) {
           std::cout << "Packet: "
                     << pkt.IP.src << " -> " << pkt.IP.dest
                     << "  payload=" << pkt.IP.payloadFullLen << " bytes"
                     << "  ts=" << pkt.Erspan.timestamp
                     << std::endl;
       });

       // Start capture (blocks until stopped)
       capture.run();
       return 0;
   }

**Build:**

.. code-block:: bash

   g++ -std=c++17 -I$DAOBASE/include -o erspan_example erspan_example.cpp

**Grant raw socket capability:**

.. code-block:: bash

   sudo setcap cap_net_raw,cap_net_admin+ep ./erspan_example

.. warning::
   ERSPAN capture requires a Cisco switch configured to mirror the target
   port to the monitoring host using ERSPAN v3. Ensure the ERSPAN destination
   IP matches the monitoring host's interface address. Only Linux is supported.
