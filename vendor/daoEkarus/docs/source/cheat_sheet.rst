===========
Cheat Sheet
===========

DAO / Ekarus Bench Quick Start
==============================

Startup
-------

Hardware
~~~~~~~~

Switching on the bench:

    #. Camera coolers
    #. Laser sources (visible and IR)
    #. Cameras

Software
~~~~~~~~

On PAPY-RTC
^^^^^^^^^^^

Open MATLAB and launch the following script. If it is already running, kill the server and restart it.

.. code-block:: matlab

   C:/Users/papyrus/Documents/GitHub/papyrus/bench_quickStart/lib/TTserver.m

On DAO-RTC
^^^^^^^^^^

Launch:

.. code-block:: bash

   daoEkarusStart


DAO - Basic Stuff
=================

Handling SHM for Beginners
--------------------------

Import DAO in Python:

.. code-block:: python

   import dao

Create a shared memory (SHM):

.. code-block:: python

   example = dao.shm(
       '/tmp/example.im.shm',
       np.zeros((a, b)).astype(np.float32)
   )

Access an existing SHM:

.. code-block:: python

   example = dao.shm('/tmp/example.im.shm')

Read data from SHM:

.. code-block:: python

   example.get_data()

Write data to SHM:

.. code-block:: python

   example.set_data(new_data)

.. warning::

   ``new_data`` must have the correct data type and shape.


Checking Background Processes
-----------------------------

DAO uses several ``tmux`` sessions to run processes in the background.

List all sessions:

.. code-block:: bash

   tmux ls

Attach to a session:

.. code-block:: bash

   tmux a -t sessionName

Detach from a session:

#. Press ``Ctrl-b``.
#. Release both keys.
#. Press ``d``.


EKARUS Shared Memories
----------------------

All EKARUS shared memories are created in:

.. code-block:: text

   /home/daouser/dao/Ekarus/daoEkarus/apps/daoEkarusCreateShm.py

The corresponding shared memory names are defined in:

.. code-block:: text

   /home/daouser/dao/Ekarus/daoEkarus/src/python/daoEkarusShmNames.py


Deploying DAO EKARUS
--------------------

Any modification made inside ``~/dao/daoEkarus`` is **not** automatically deployed to DAO.

From the ``~/dao/daoEkarus`` directory, run:

.. code-block:: bash

   waf install

This command deploys all scripts into ``$DAOROOT``.

If ``waf install`` fails (which may happen after a reboot), first configure the build:

.. code-block:: bash

   waf configure --prefix=$DAOROOT

Then install again:

.. code-block:: bash

   waf install


Cameras
=======

Ocam2k
------

The camera is normally launched when running daoEkarusStart. If the camera feed on the GUI is not working, try running 

.. code-block:: bash

   daoEkarusStartOcamAcqusition.py 

If it does not work try with

.. code-block:: bash

   daoEkarusStartOcamCamera

If it still is not working, we suggest to restart the pipeline doing

.. code-block:: bash

   daoEkarusStart

Diagnostics
~~~~~~~~~~~

You can access the frames of the OCAM with the following block of code

.. code-block:: python

   import dao
   import numpy as np
   import pylab as plt

   ocam_frames_shm = dao.shm("/tmp/ocam2.im.shm")
   ocam_frame = ocam_frames_shm.get_data(check=True, semNb=2)

   plt.imshow(ocam_frame)
   plt.colorbar()
   plt.show()

Common Errors
~~~~~~~~~~~~~

The Iport sometimes gets in a weird state after a reboot. it doesn't stream pixels correctly or respond to the serial interface. Confirm bu looking at the reciever tmux `OCAM_WFS_ACQUISITION` if you see a lot of error in receiving payload or trailer, this is likey the issue. Also if you send serial commands and get nothing or gargbage back it is likely in the weird state.

Fix is easy, We upload known good firmware. This is located and backed up in daoEkarus/config/iportOcam.pvxml. To install this we use the tool `daoIportWriteConfig`, I have written a wrapper scripted `daoEkarusIportFirmwareUpdate` which will do this for you.


fix commited in main branch- ef2438f and d4f3059

CBlue - GSC
-----------

The camera is normally launched when running daoEkarusStart. If the camera feed on the GUI is not working, try running 

.. code-block:: bash

   daoEkarusStartCblueAqusition.py 

If it does not work try with

.. code-block:: bash

   daoEkarusStartCBLUECamera

If it still is not working, we suggest to restart the pipeline doing

.. code-block:: bash

   daoEkarusStart

Diagnostics
~~~~~~~~~~~

You can access the frames of the CBlue with the following block of code

.. code-block:: python

   import dao
   import numpy as np
   import pylab as plt

   cblue_frames_shm = dao.shm("/tmp/cblue.im.shm")
   cblue_frame = cblue_frames_shm.get_data(check=True, semNb=2)

   plt.imshow(cblue_frame)
   plt.colorbar()
   plt.show()


Mirrors
=======

Fast TipTilt
------------

If the bench was previously turned off, first you have to start the process

.. code-block:: bash

      daoEkarusCreateShm.py

.. code-block:: bash
   
      daoEkarusStartFastTT

Once the process is started (you can check by doing ``tmux ls`` and looking for ``FASTTT_CONTROL``) you can send positions with the following command

.. code-block:: bash
   
      moveFastTT.py posx posy

.. code-block:: bash
   :caption: Example

   moveFastTT.py 10 -20

To remove hysteresis you can call the Fast TT relaxation script

.. code-block:: bash

   relaxFastTT.py

Modulator
---------

If you need to start the modulation from scratch you need follow these steps

On the PapyRTC, run the Matlab script

.. code-block:: matlab

   TTserver.m

On daoRTC, run 

.. code-block:: bash

   daoEkarusStartModulator

.. warning::

   If you see the following error when starting the modulator:

   .. code-block:: text

      [error] daoShmShm2Img:512: Cannot import shared memory file

   the required shared memory is probably missing. Create it by running:

   .. code-block:: bash

      daoEkarusCreateShm.py

To control the modulator you can do it through the GUI, in which you can set the modulation radius and it automatically syncs the frequency to the Ocam FPS, or using the following script

.. code-block:: bash
   
      setModulation.py freq radius

.. code-block:: bash
   :caption: Example

   setModulation.py 100 3



Telescope
=========

The telescope is controlled from the **control room** using the wireless keyboard and mouse connected to the two upper monitors.

**Login credentials**

* **User:** `Ekar`
* **Password:** `copernico`

Powering On the Telescope
-------------------------

Open the following applications:

* `Ossia VMS` (live camera feed of the telescope)
* `TPS` (telescope control)
* `Relay controller` (power control)

#. If needed, switch on the dome lights using the `Relay controller`.
#. In the `Relay controller`, click **Main System Power**.
#. In `TPS`, navigate to:

   **Telescope → Telescope Power → Power ON**

#. Wait until the telescope has completed its startup sequence before issuing any commands.

Powering Off the Telescope
--------------------------

Before switching off the telescope, it must be parked.

#. In `TPS`, park the telescope by navigating to:

   **Telescope → Park the telescope**

#. Wait until the confirmation message indicates that the telescope has been successfully parked.
#. In `TPS`, switch off the telescope:

   **Telescope → Telescope Power → Power OFF**

#. Finally, in the `Relay controller`, click **Main System Power** to remove power from the system.

.. warning::

   Always verify on the `Ossia VMS` camera feed that the telescope is parked before powering it off.

GUI
===

To launch the GUIs of the WFSing controll, in DAO run ``EkarusCtrl.py``. For the GSC, run ``cblueGUI.py``

If you are using windows, you can use Windows PowerShell, but you need to follow these steps to set it up.

#. Install and run XLaunch:
   You can install XLaunch from here ``https://sourceforge.net/projects/xming/``. Make sure that the XLaunch check box is checked when installing.
#. In PowerShell, run ``ipconfig`` and look for your IPv4 Address:

   .. code-block:: text
      :caption: Example

      IPv4 Address . . . : 193.206.244.201

#. In PowerShell, run ``$env:DISPLAY="your_ip:0.0"``

   .. code-block:: bash
      :caption: Example

      $env:DISPLAY="193.206.244.201:0.0"

#. Connect to DAO using ``ssh -YC dao``

#. Check if you have a display in DAO by running ``echo $DISPLAY``. You should see ``localhost:10.0`` or something similar.

#. You should now be able to display the GUIs.