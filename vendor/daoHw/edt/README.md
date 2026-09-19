# edt — EDT PDV frame grabbers

Cameras read out through an **EDT PDV** Camera Link / interface board:

| file | camera |
|------|--------|
| `daoEdtOCAM2kCtrl.c`         | First Light OCAM²k |
| `daoEdtCRED1Ctrl.c`          | First Light C-RED One |
| `daoEdtBigJoeCtrl.c` / `daoEdtLilJoeCtrl.c` / `daoEdtLJCtrl.c` | SciMeasure Big Joe / Little Joe |
| `daoEdtCtrl.c`               | generic EDT grabber |
| `daoEdtJoe.py`               | send serial ASCII commands to a Little Joe via `/opt/EDTpdv/serial_cmd` |

Each `*Ctrl` binary streams frames to a DAO SHM and watches the usual control
SHMs (Dit / Fps / Gain / …).

## Dependency

**EDT PDV SDK** installed at `/opt/EDTpdv` (provides `libpdv`, `libedt`,
`serial_cmd`, `initcam`). Get it from <https://edt.com/> and load the camera
config once with `initcam -f <camera>.cfg`.

## Build

`../wscript` `configure` auto-detects the SDK (`--edt=/path` to override); if not
found, this folder is skipped (`HAVE_EDT`). `edt/*.py` install to `$DAOROOT/bin`
regardless.
