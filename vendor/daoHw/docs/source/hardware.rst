Hardware Index
==============

This page lists all hardware interfaces supported by daoHw, organised by category.
Each entry links to the dedicated documentation page for that device.

.. contents::
   :local:
   :depth: 2

----

Cameras
-------

.. list-table::
   :header-rows: 1
   :widths: 20 25 30 25

   * - Device
     - Manufacturer
     - Interface
     - Documentation
   * - AVT Mako G-030
     - Allied Vision
     - GigE Vision (Aravis)
     - :doc:`aravis`
   * - AVT GC1020M
     - Allied Vision
     - GigE Vision (Aravis)
     - :doc:`aravis`
   * - AVT Goldeye GT1920
     - Allied Vision
     - GigE Vision (Aravis)
     - :doc:`aravis`
   * - Basler (standard)
     - Basler
     - GigE Vision (Aravis)
     - :doc:`aravis`
   * - Basler WBin
     - Basler
     - GigE Vision (Aravis)
     - :doc:`aravis`
   * - Bob camera
     - Custom / internal
     - GigE Vision (Aravis)
     - :doc:`aravis`
   * - C-Blue One
     - First Light Imaging
     - GigE Vision (Aravis)
     - :doc:`aravis`
   * - FLIR camera
     - Teledyne FLIR
     - GigE Vision (Aravis)
     - :doc:`aravis`
   * - OCAM2 (iPort path)
     - First Light Imaging
     - GigE Vision (Aravis / iPort)
     - :doc:`aravis`
   * - EVHZ camera
     - Custom / EV
     - GigE Vision (Aravis)
     - :doc:`aravis`
   * - Fake / Simulator
     - —
     - Software (Aravis fake)
     - :doc:`aravis`
   * - OCAM2k
     - First Light Imaging
     - Camera Link (EDT)
     - :doc:`edt`
   * - CRED1 (EDT path)
     - First Light Imaging
     - Camera Link (EDT)
     - :doc:`edt`
   * - Andor BigJoe
     - Andor / custom
     - Camera Link (EDT)
     - :doc:`edt`
   * - Andor LilJoe
     - Andor / custom
     - Camera Link (EDT)
     - :doc:`edt`
   * - Andor LJ
     - Andor / custom
     - Camera Link (EDT)
     - :doc:`edt`
   * - CRED1
     - First Light Imaging
     - Camera Link (FLI/EDT)
     - :doc:`fli`
   * - CRED2
     - First Light Imaging
     - Camera Link (FLI/EDT)
     - :doc:`fli`
   * - Nüvü 512
     - Nüvü Camēras
     - PCIe (nc_driver)
     - :doc:`nuvu`
   * - Nüvü 512 Multi-ROI
     - Nüvü Camēras
     - PCIe (nc_driver)
     - :doc:`nuvu`
   * - uEye (USB / GigE)
     - IDS Imaging
     - USB / GigE (pyueye)
     - :doc:`ids`

----

Deformable Mirrors & Tip-Tilt Stages
--------------------------------------

.. list-table::
   :header-rows: 1
   :widths: 20 25 30 25

   * - Device
     - Manufacturer
     - Interface
     - Documentation
   * - Tip-Tilt Mirror (E-518)
     - Physik Instrumente (PI)
     - Ethernet (pipython)
     - :doc:`pi`

----

Spatial Light Modulators
-------------------------

.. list-table::
   :header-rows: 1
   :widths: 20 25 30 25

   * - Device
     - Manufacturer
     - Interface
     - Documentation
   * - Meadowlark SLM
     - Meadowlark Optics
     - USB / PCIe (Blink SDK)
     - :doc:`meadowlark`
   * - Thorlabs SLM
     - Thorlabs
     - DisplayPort / HDMI (OpenGL)
     - :doc:`thorlabs`

----

Motor Controllers
-----------------

.. list-table::
   :header-rows: 1
   :widths: 20 25 30 25

   * - Device
     - Manufacturer
     - Interface
     - Documentation
   * - ACE-SDE
     - Arcus Technology
     - USB (Windows) / Serial
     - :doc:`arcus`

----

Infrastructure & Network
-------------------------

.. list-table::
   :header-rows: 1
   :widths: 20 25 30 25

   * - Device
     - Manufacturer
     - Interface
     - Documentation
   * - CMC III PDU
     - Rittal
     - SNMP over Ethernet
     - :doc:`rittal`
   * - ERSPAN v3 capture
     - Cisco
     - Raw socket (Linux)
     - :doc:`cisco`
   * - iPort (Camera Link → GigE)
     - Pleora Technologies
     - GigE Vision
     - :doc:`iport`

----

Common / Shared Utilities
--------------------------

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Module
     - Purpose
   * - ``daoGigeReader``
     - Raw GigE Vision packet parser (leader/trailer/payload, V1 & V2)
   * - ``daoCameraController``
     - Python wrapper for camera DIT/FPS/gain control via shared memory
   * - ``daoSLMController``
     - Python wrapper for SLM phase-map updates via shared memory
   * - ``daoIportController``
     - Python wrapper for Pleora iPort camera link converter
   * - ``daoEndianUtils``
     - Portable byte-swap macros for multi-platform endian handling

See :doc:`common` for full details.
