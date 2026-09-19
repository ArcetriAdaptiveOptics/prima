# meadowlark — Meadowlark Optics SLM

`daoMeadowLark.py` — drive a Meadowlark **spatial light modulator** from a DAO
SHM: reads a phase/greyscale array from shared memory and writes it to the SLM.

## Dependency

Meadowlark **Blink** SDK — the C wrapper DLL, by default at

```
C:\Program Files\Meadowlark Optics\Blink Plus\SDK\Blink_C_wrapper
```

so this script is effectively **Windows only**. Needs `numpy` (+ `matplotlib`
for the preview).

## Build / install

Pure Python. `../wscript` installs `meadowlark/*.py` to `$DAOROOT/bin`.
