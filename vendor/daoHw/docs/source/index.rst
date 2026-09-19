.. daoHw documentation master file

daoHw — Hardware Abstraction Layer
====================================

.. raw:: html

   <div class="hero-section">
      <h1>daoHw</h1>
      <p class="tagline">Hardware Abstraction Layer for Adaptive Optics Systems</p>
      <p class="description">
         daoHw provides a unified interface to the diverse range of hardware used in Durham Adaptive Optics systems —
         from wavefront sensor cameras and deformable mirrors to tip-tilt stages, spatial light modulators,
         frame grabbers, and network infrastructure. All devices are integrated via the DAO shared memory
         framework for low-latency real-time control.
      </p>
      <div class="cta-buttons">
         <a href="hardware.html" class="cta-button">Browse Hardware</a>
         <a href="https://github.com/Durham-Adaptive-Optics/daoHw" class="cta-button secondary">GitHub</a>
      </div>
   </div>

Overview
========

daoHw wraps vendor SDKs, GigE Vision stacks, frame grabbers, serial/USB motor controllers,
SLM display backends, and network capture libraries into a consistent DAO shared memory
interface. Each driver process acquires frames or commands from its hardware and writes them
to shared memory segments, decoupling hardware-specific timing from the AO control loop.

Hardware Categories
===================

.. raw:: html

   <div class="feature-grid">
      <div class="feature-card">
         <h3><span class="icon">📷</span>GigE Vision Cameras</h3>
         <p>Allied Vision, Basler, First Light, and other GigE cameras via the open-source Aravis library.</p>
         <a href="aravis.html">Aravis →</a>
      </div>
      <div class="feature-card">
         <h3><span class="icon">🎞️</span>Camera Link / Frame Grabbers</h3>
         <p>EDT frame grabbers supporting OCAM2k, CRED1, and Andor iXon camera families.</p>
         <a href="edt.html">EDT →</a>
      </div>
      <div class="feature-card">
         <h3><span class="icon">🔭</span>FLI CRED Cameras</h3>
         <p>First Light Imaging CRED1 and CRED2 infrared wavefront sensor cameras.</p>
         <a href="fli.html">FLI →</a>
      </div>
      <div class="feature-card">
         <h3><span class="icon">🌟</span>Nüvü EM-CCD Cameras</h3>
         <p>Nüvü Camēras 512 series with multi-ROI acquisition and EM gain control.</p>
         <a href="nuvu.html">Nüvü →</a>
      </div>
      <div class="feature-card">
         <h3><span class="icon">🎥</span>IDS uEye Cameras</h3>
         <p>IDS Imaging uEye USB and GigE cameras for visible-band wavefront sensing.</p>
         <a href="ids.html">IDS uEye →</a>
      </div>
      <div class="feature-card">
         <h3><span class="icon">🪞</span>Tip-Tilt Mirrors (PI)</h3>
         <p>Physik Instrumente E-518 piezo controller for tip-tilt mirror stages.</p>
         <a href="pi.html">PI →</a>
      </div>
      <div class="feature-card">
         <h3><span class="icon">💡</span>Meadowlark SLM</h3>
         <p>Meadowlark Optics spatial light modulators via the Blink SDK.</p>
         <a href="meadowlark.html">Meadowlark →</a>
      </div>
      <div class="feature-card">
         <h3><span class="icon">🔆</span>Thorlabs SLM</h3>
         <p>Thorlabs spatial light modulator display via VSync-locked OpenGL rendering.</p>
         <a href="thorlabs.html">Thorlabs →</a>
      </div>
      <div class="feature-card">
         <h3><span class="icon">⚙️</span>Arcus Motor Controllers</h3>
         <p>Arcus ACE-SDE stepper motor controller for focusers and filter wheels.</p>
         <a href="arcus.html">Arcus →</a>
      </div>
      <div class="feature-card">
         <h3><span class="icon">🔌</span>Rittal PDU</h3>
         <p>Rittal CMC III power distribution unit control via SNMP for instrument power management.</p>
         <a href="rittal.html">Rittal →</a>
      </div>
      <div class="feature-card">
         <h3><span class="icon">🌐</span>Cisco ERSPAN</h3>
         <p>Cisco ERSPAN v3 network packet capture for camera-link-over-network diagnostics.</p>
         <a href="cisco.html">Cisco ERSPAN →</a>
      </div>
      <div class="feature-card">
         <h3><span class="icon">🔗</span>Pleora iPort</h3>
         <p>Pleora iPort Camera Link to GigE Vision converter configuration and control.</p>
         <a href="iport.html">Pleora iPort →</a>
      </div>
      <div class="feature-card">
         <h3><span class="icon">🛠️</span>Common Utilities</h3>
         <p>Shared GigE reader, Python camera/SLM wrappers, and endian utilities used across drivers.</p>
         <a href="common.html">Common →</a>
      </div>
      <div class="feature-card">
         <h3><span class="icon">🖥️</span>GUI Tools</h3>
         <p>PyQt5 GUI applications for camera control, PDU management, latency monitoring, and serial device terminals.</p>
         <a href="gui.html">GUI Tools →</a>
      </div>
      <div class="feature-card">
         <h3><span class="icon">📟</span>Applications</h3>
         <p>Camera parameter helpers (DIT, FPS, temperature) and ERSPAN-based RTC latency monitor with Qt GUI.</p>
         <a href="apps.html">Applications →</a>
      </div>
   </div>

Repository Structure
====================

.. raw:: html

   <div class="repo-badges">
      <a href="https://github.com/Durham-Adaptive-Optics/daoBase" class="repo-badge">🏗️ daoBase - Core Library</a>
      <a href="https://github.com/Durham-Adaptive-Optics/daoTools" class="repo-badge">🛠️ daoTools - Utilities</a>
      <a href="https://github.com/Durham-Adaptive-Optics/daoHw" class="repo-badge">⚙️ daoHw - Hardware Layer</a>
   </div>

daoHw is part of the DAO ecosystem and depends on **daoBase** for shared memory and
thread management. Each hardware driver follows the same pattern:

1. Acquire data from the device (camera frame, sensor reading, or command output)
2. Write it to one or more DAO shared memory segments
3. Optionally read control parameters from dedicated control SHM segments

Documentation
=============

.. raw:: html

   <div class="section-group">
      <h2>📋 Hardware Reference</h2>
      <div class="doc-grid">
         <a href="hardware.html" class="doc-link">
            <h4>Hardware Index</h4>
            <p>Complete listing of all supported devices with quick-reference links</p>
         </a>
         <a href="aravis.html" class="doc-link">
            <h4>Aravis — GigE Vision Cameras</h4>
            <p>Allied Vision, Basler, FLIR, First Light and custom GigE cameras</p>
         </a>
         <a href="edt.html" class="doc-link">
            <h4>EDT — Frame Grabber Cameras</h4>
            <p>Camera Link cameras via EDT PCIe frame grabbers</p>
         </a>
         <a href="fli.html" class="doc-link">
            <h4>FLI — CRED Infrared Cameras</h4>
            <p>First Light CRED1 and CRED2 near-infrared cameras</p>
         </a>
         <a href="nuvu.html" class="doc-link">
            <h4>Nüvü — EM-CCD Cameras</h4>
            <p>Nüvü 512 series electron-multiplying CCD cameras</p>
         </a>
         <a href="ids.html" class="doc-link">
            <h4>IDS — uEye Cameras</h4>
            <p>IDS Imaging uEye visible-band cameras</p>
         </a>
         <a href="pi.html" class="doc-link">
            <h4>PI — Tip-Tilt Controllers</h4>
            <p>Physik Instrumente E-518 piezo tip-tilt mirror control</p>
         </a>
         <a href="meadowlark.html" class="doc-link">
            <h4>Meadowlark — SLM</h4>
            <p>Meadowlark Optics spatial light modulators via Blink SDK</p>
         </a>
         <a href="thorlabs.html" class="doc-link">
            <h4>Thorlabs — SLM</h4>
            <p>Thorlabs SLM via VSync-locked OpenGL fullscreen display</p>
         </a>
         <a href="arcus.html" class="doc-link">
            <h4>Arcus — Motor Controllers</h4>
            <p>Arcus ACE-SDE stepper motor controller</p>
         </a>
         <a href="rittal.html" class="doc-link">
            <h4>Rittal — PDU Control</h4>
            <p>Rittal CMC III power distribution unit via SNMP</p>
         </a>
         <a href="cisco.html" class="doc-link">
            <h4>Cisco — ERSPAN Capture</h4>
            <p>Cisco ERSPAN v3 network packet capture header library</p>
         </a>
         <a href="iport.html" class="doc-link">
            <h4>Pleora iPort</h4>
            <p>Camera Link to GigE Vision converter configuration</p>
         </a>
         <a href="common.html" class="doc-link">
            <h4>Common Utilities</h4>
            <p>Shared GigE reader, Python wrappers, and endian utilities</p>
         </a>
         <a href="gui.html" class="doc-link">
            <h4>GUI Tools</h4>
            <p>PyQt5 GUIs: camera control, PDU panel, latency monitor, serial terminals</p>
         </a>
         <a href="apps.html" class="doc-link">
            <h4>Applications</h4>
            <p>Camera parameter helpers and ERSPAN RTC latency monitor CLI + Qt GUI</p>
         </a>
      </div>
   </div>

.. toctree::
   :maxdepth: 2
   :hidden:
   :caption: Hardware Reference

   hardware
   aravis
   edt
   fli
   nuvu
   ids
   pi
   meadowlark
   thorlabs
   arcus
   rittal
   cisco
   iport
   common
   gui
   apps
