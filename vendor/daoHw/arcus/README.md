# arcus — Arcus ACE-SDE motor controller

`daoAceSde.py` — control library for the Arcus **ACE-SDE** stepper/motor
controller (USB and RS-232 serial).

## Dependency

- `pyserial` (`pip install pyserial`) for the serial interface.
- The USB interface uses the vendor DLL and is **Windows only** (`ctypes.wintypes`);
  on Linux use the serial port.

Device defaults: 9600 baud, 64-byte read/write buffers.

## Build / install

Pure Python, not wired into `../wscript` — run in place or copy `daoAceSde.py`
next to the code that imports it.

## Usage

```python
from daoAceSde import ACE_SDE
m = ACE_SDE(serialPort="/dev/ttyUSB0")
```
