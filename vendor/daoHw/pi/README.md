# pi — Physik Instrumente tip-tilt

Tip-tilt mirror (TTM) control through a **PI E-518** piezo controller.

| file | |
|------|--|
| `daoHwPiTtCtrl.py`        | read a 2-axis command from a SHM, send it to the E-518 |
| `daoHwPiTtCtrlWithRef.py` | same, with a reference/offset SHM added to the command |

```
daoHwPiTtCtrl.py <shmName> <ip> <ctrlModel> [--center A,B]
```

## Dependency

PI **GCS** interface over TCP/IP (`<ip>` of the E-518). No vendor SDK required —
the scripts speak the GCS command set directly. Needs `numpy` + `dao`.

## Build / install

Pure Python. `../wscript` installs `pi/*.py` to `$DAOROOT/bin`.
