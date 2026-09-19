# fli — First Light Imaging cameras (C-RED)

C-RED 1 / C-RED 2 / C-RED 3 infrared cameras.

| file | interface |
|------|-----------|
| `daoFliEdtCred1Ctrl.c` | C-RED 1 over an **EDT PDV** Camera Link board (`/opt/EDTpdv`, `libpdv`) |
| `cred1Init.py`, `cred.py` | C-RED via the **FLI SDK** (`$FLISDK_DIR/Python/lib/FliSdk_V2`) |
| `cred2CL.py` | C-RED 2, Camera Link |
| `archive/` | older / reference scripts |

## Dependencies

- EDT path: **EDT PDV SDK** at `/opt/EDTpdv` (for `daoFliEdtCred1Ctrl`).
- SDK path: **First Light FLI SDK**, with `FLISDK_DIR` exported so
  `$FLISDK_DIR/Python/lib` is importable. Get it from First Light Imaging.

## Build

`fli/wscript_build` builds `daoFliEdtCred1Ctrl` (links `-lpdv`). `fli/*.py`
install to `$DAOROOT/bin`. The Python scripts need `FLISDK_DIR` set at runtime.
