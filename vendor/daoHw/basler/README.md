# basler — Basler Ace cameras (pypylon)

`daoHwBaslerAce.py` — opens a Basler Ace over `pypylon`, publishes frames to
`/tmp/<name>.im.shm`, and watches control SHMs for runtime frame-rate, gain and
exposure updates.

(C++ Basler device controllers driven through Aravis instead live in
`../aravis/` — `daoHwBaslerDeviceCtrl`, `daoHwBaslerWBinDeviceCtrl`.)

## Dependency

Basler **pylon SDK** + `pip install pypylon`.
Download pylon from <https://www.baslerweb.com/en/software/pylon/>.

## Build / install

Pure Python. `../wscript` installs `basler/*.py` to `$DAOROOT/bin` **only if
`pypylon` imports at configure time** (`HAVE_PIPYLON`); otherwise it is skipped
with a warning.

## Usage

```bash
daoHwBaslerAce.py            # see the file header for the SHM layout / args
```
