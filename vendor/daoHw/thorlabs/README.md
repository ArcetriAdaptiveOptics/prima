# thorlabs — Thorlabs EXULUS SLM display

`thorlabSlm.py` — full-screen, VSync-locked SLM display. Reads a `uint8` phase
pattern from shared memory (`/tmp/sslm.im.shm`, shape `(1200, 1920)`) and blits
it to the SLM panel at 60 Hz.

```bash
DISPLAY=:0 thorlabSlm.py                 # panel on DP-1-2 (DISPLAY_IDX = 1)
DISPLAY=:0 thorlabSlm.py --measure       # FPS check only, no SHM
```

Panel geometry (`1920x1200`, output, display index) is set near the top of the
file — adjust for your monitor layout.

## Dependency

`pip install pygame PyOpenGL numpy` + `dao`. Needs a real X display with the SLM
attached as a second monitor.

## Build / install

Pure Python. `../wscript` installs `thorlabs/*.py` to `$DAOROOT/bin`.
