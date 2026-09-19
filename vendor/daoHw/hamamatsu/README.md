# hamamatsu — ORCA camera control (DCAM-API)

DAO controller + minimal binding for Hamamatsu ORCA cameras.

| file             | what it is                                                              |
|------------------|------------------------------------------------------------------------|
| `dcam_mini.py`   | tiny `ctypes` binding to `libdcamapi.so` (open, exposure, subarray, readout speed, grab) |
| `daoOrcaCtrl.py` | dao-style streamer: frames + `Dit` / `Fps` / `ReadoutSpeed` / `SetTemp` / `Roi` / `Temp` control SHMs, no GUI |
| `daoOrcaDisp.py` / `.ui` | minimal display + control GUI (PyQt5); talks to the streamer over SHM only — no acquisition / telemetry |

`daoOrcaDisp.ui` installs to `$DAOROOT/data/`, the `.py` files to `$DAOROOT/bin/`
(see the `hamamatsu/` block in `../wscript`).

---

## 1. Prerequisite: DCAM-API Lite for Linux  ← this is not bundled

`dcam_mini.py` `dlopen`s `libdcamapi.so`. It is **not** on any package repo — you
must install Hamamatsu's *DCAM-API Lite for Linux* runtime + USB3 driver:

1. Download `DCAM-API_Lite_for_Linux_vXX.X.XXXX` from the Hamamatsu support portal
   (account required) and unpack it.
2. Fresh install (driver **and** runtime):
   ```bash
   cd DCAM-API_Lite_for_Linux_v*/
   sudo ./api/install.sh usb3
   ```
   Runtime-only update later: `sudo ./api/runtime/install.sh usb3`.
3. Check it landed:
   ```bash
   ldconfig -p | grep -i dcam        # expect libdcamapi.so -> /usr/local/lib
   ```
   If `daoOrcaCtrl.py` still can't find it, pass `--lib-path /usr/local/hamamatsu_dcam/api/libdcamapi.so`.

The installer also drops `/etc/udev/rules.d/55-hamamatsu_dcamusb.rules`
(`ATTRS{idVendor}=="0661", ATTRS{idProduct}=="14xx", MODE="666"`) — see next section.

---

## 2. Make the USB camera usable without `sudo`

The udev rule above gives the raw USB node mode `0666` (world r/w), so **group
membership is irrelevant** — `plugdev` / `usbusers` do not matter here. What
matters is that udev has actually *applied* the rule, which only happens at
device enumeration.

After installing the SDK (or if the camera was plugged in before the rule
existed):

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
# then PHYSICALLY unplug the camera and plug it back in
```

A real replug is required — `udevadm trigger` alone often does not re-run the
`MODE=` action on an already-attached device.

Verify the live permission bits. The USB node path is
`/dev/bus/usb/<bus>/<device>`, and **both numbers are dynamic** — `<bus>` is the
host controller it enumerated on, `<device>` is a per-bus counter that bumps on
almost every replug — so read them back from `lsusb` *after* the replug rather
than hard-coding them. `0661` is the Hamamatsu vendor ID (the
`ATTRS{idVendor}=="0661"` from the udev rule), so it is the stable thing to match
on:

```bash
lsusb -d 0661:                        # -> Bus 004 Device 017: ID 0661:1416 Hamamatsu Photonics K.K.

# build the node path from that line and check the mode bits
node=$(lsusb -d 0661: | sed -E 's|Bus ([0-9]+) Device ([0-9]+):.*|/dev/bus/usb/\1/\2|')
echo "$node"
ls -l "$node"                         # want:  crw-rw-rw-  (not crw-rw---- or crw-------)
```

Once that node reads `crw-rw-rw-`, `daoOrcaCtrl.py` should run as your normal user.

---

## 3. Troubleshooting

### `dcamapi_init failed (DCAM error code 0x80000206)` = `DCAMERR_NOCAMERA`

The library loaded fine (a load failure raises a different `OSError` about
`libdcamapi.so`); `dcamapi_init` just found no compatible camera. Work through:

1. **Another process holds it.** DCAM access is exclusive — a second client (or a
   crashed one that never released) shows up as "no camera", not "busy":
   ```bash
   ps aux | grep -iE 'orca|dcam|daoOrca'
   sudo fuser -v "$(lsusb -d 0661: | sed -E 's|Bus ([0-9]+) Device ([0-9]+):.*|/dev/bus/usb/\1/\2|')"
   ```
   Kill stragglers, retry. (Killing `daoOrcaCtrl.py` with `SIGKILL` skips camera
   teardown and can wedge the device until a replug — it installs a `SIGTERM`
   handler, so prefer `kill` / Ctrl-C.)

2. **Permissions not live yet.** If it works under `sudo` but not as your user,
   the node bit isn't applied — redo the replug in §2.

3. **A separate vendor device node.** The USB3 driver can create its own node the
   bus-device rule doesn't cover:
   ```bash
   lsmod  | grep -i dcam
   ls -la /dev | grep -i dcam
   dmesg  | grep -i dcam
   ```
   If there's a loaded module and a `root:root`, non-world node, add a rule for it
   (or `sudo chmod 666` it as a quick test), then reload + replug.

4. **Not a permissions problem at all.** If it also fails as `root` with the same
   `NOCAMERA`: check power/cabling, use a real USB3 (SuperSpeed) port + cable, and
   look at `dmesg | tail -40` right after a fresh plug-in for descriptor / link
   errors or the camera enumerating as USB2.

5. **Sanity check against Hamamatsu's own tools** in the SDK's
   `tools/x86_64/` folder — if their sample also sees no camera as non-root, the
   problem is below our code (driver / environment), not in `dcam_mini.py`.

---

## 4. Usage

```bash
# stream ORCA 0 to /tmp/orca*.im.shm  (Dit in ms, Fps in Hz, 0 = free run)
daoOrcaCtrl.py -S /tmp/orca.im.shm --dit 35 --fps 20

# then, separately:
daoOrcaDisp.py -s /tmp/orca.im.shm         # the display + control GUI
daoImgDisp.py /tmp/orca.im.shm             # or just a viewer
```

Control SHMs (created by the streamer, written by anyone):

| SHM                          | dtype        | meaning                                   |
|------------------------------|--------------|-------------------------------------------|
| `/tmp/orca.im.shm`           | uint16/uint8 | frames                                    |
| `/tmp/orcaDit.im.shm`        | float32      | exposure time [ms]                        |
| `/tmp/orcaFps.im.shm`        | float32      | target loop rate [Hz], 0 = free run       |
| `/tmp/orcaReadoutSpeed.im.shm` | float32    | DCAM readout speed enum (1 = low noise …) |
| `/tmp/orcaRoi.im.shm`        | int32 (1,4)  | subarray `x, y, w, h` (0,0,0,0 = full)    |
| `/tmp/orcaTemp.im.shm`       | float32      | sensor temperature [°C], published ~1 Hz (read-only) |
| `/tmp/orcaSetTemp.im.shm`    | float32      | cooling setpoint [°C] — ignored on fixed-cooling models |

Notes:

- Scientific sCMOS ORCA models have **no analog gain** — "readout speed" is the
  noise/rate knob and is what the GUI exposes.
- **Temperature** is read automatically (`SENSORTEMPERATURE` → `orcaTemp` SHM,
  shown in the GUI). The **cooling setpoint** (`SENSORTEMPERATURETARGET`) is only
  writable on models that support it; on Fusion / Flash sCMOS it is fixed and the
  streamer prints `Cooling setpoint: fixed …` and ignores `orcaSetTemp`.
- `daoOrcaCtrl.py --help` lists all options (`--dit`, `--fps`, `--readout-speed`,
  `--set-temp`, `--roi-*`, …).
