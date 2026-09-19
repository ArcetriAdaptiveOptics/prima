===============
startup scripts
===============

daoEkarus provides a set of startup scripts to facilitate the initialization and management of its components. These scripts are designed to streamline the process of starting up the components that make up the daoEkarus system.

The following scripts are available:

- `daoEkarusStop`_
- `daoEkarusLaunchMessage`_
- `daoEkarusStart`_
- `daoEkarusStartCBLUECamera`_
- `daoEkarusStartDM468`_
- `daoEkarusStartFastTT`_
- `daoEkarusStartModulator`_
- `daoEkarusStartOcamCamera`_

daoEkarusStop
----------------

daoEkarusStop is a script that cleans up shared memory segments and semaphores used by the daoEkarus system. It is recommended to run this script before starting the system to ensure a clean state.
It will kill any process that is running inside a tmux session and remove all shared memory segments and semaphores used by the daoEkarus system.

daoEkarusLaunchMessage
----------------------

This is the script that prints the launch message for the daoEkarus system.

.. code-block:: text

                                  ---------%--------
                              --%----------%-------------
                           --%--%------------------------%--
                         ---%---------------%------------%--%-
                       --%--%--%-------------------------%--%---
                      ---=-----%-------------%-----------%--%--%-
                    --%-%---------------------%----------%--%--%---
                   --%--%--%--=----------------%---------%--%--%--%-
                  -%-%--%--*---%----------------*--------%--%--%--%--
                 --*-%--%---%---%---------------%--------%--%--%--%---
                 ----%---+---*---%--------------%--------%--%--%--%---
                ---%--%---=--=---------------------------%--%--%--%----
                ---%---%--%---%---%----------%%----------%--%--%--%----
                -%--%---%%%%--%---%---%----%--%--%-------%--%--%--%----
               ----=-=--%%-%%-%---*--%-----%--%--%-------%--%--%--%-----
               ----%----%*--%%%--%--%------%--%--%-------%--%--%--%-----
               ----*---%%----%--%----------%--%--%-------%--%--%--%-----
                --%--%-%-----%%%---%-----%%%%%%--%-------%--%--%--%----
                --%-%-%+------%%%%-%----%%----%%-%-------%--%--%--%----
                 %---%%----------%%%--+%-------%%%-------%--%--%--%----
                 --%%%-------------%%%%-----------%%%%---%--%--%--%---
                  -%%---------------------------------#%%%%-%--%--%--
                %%%-----------------------------------------%%%%%%%%%%%%
      %-------------------------------------------------------------------------

        %%%%%%%%    %%    %%%      %%%       %%%%%      %%%    %%%      %%%%
        %%%%%%%%    %%   %%%       %%%       %%  %%%    %%%    %%%    %%%  %%
        %%          %%  %%        %% %%      %%   %%    %%%    %%%   %%%   %%
        %%%%%%%%    %%%%%         %% %%%     %%%%%%%    %%%    %%%    %%%%%
        %%          %% %%%       %%%%%%%     %% %%%     %%%    %%         %%%
        %%          %%  %%%     %%%%%%%%%    %%  %%%     %%    %%    %%     %%
        %%%%%%%%    %%    %%    %%     %%%   %%   %%%    %%%%%%%%    %%%%%%%%

daoEkarusStart
--------------

The main entry point to the system. it is designed to clean up anything running, create the shared memory segments, and start all the components of the daoEkarus system in a tmux session.

it launches:

- daoDAQ: the data acquisition system
- daoServer: the remote server allows for accessing shm remotelt
- and others...

daoEkarusStartCBLUECamera
-------------------------

Starts the CBLUE camera acquisition component of the daoEkarus system. This script initializes the necessary processes and configurations to enable data acquisition from the CBLUE camera.
it launches the cblue camera controller and the cblue gigevision reaciver in tmux sessions and starts the acqusision.


daoEkarusStartDM468
-------------------

daoEkarusStartFastTT
--------------------

daoEkarusStartModulator
-----------------------

daoEkarusStartOcamCamera
------------------------