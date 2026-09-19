# ids — IDS uEye cameras

`daoUeyeCtrl.py` — IDS **uEye** camera → DAO shared memory streamer. Publishes
frames to `/tmp/<name>.im.shm` and takes DIT / Gain / FPS via SHM; ROI via CLI
or a `<name>Roi` SHM (SHM wins).

ROI precedence: `--shm-roi` → `--roi-x/y/w/h` → full sensor.

## Dependency

IDS **uEye SDK** + the `pyueye` Python wrapper (`pip install pyueye`).
Download the SDK from <https://en.ids-imaging.com/>.

## Build / install

Pure Python. `../wscript` installs `ids/*.py` to `$DAOROOT/bin`.

## Usage

```bash
daoUeyeCtrl.py -S /tmp/ueye.im.shm --shm-dit /tmp/ueyeDit.im.shm
```
