# daoHw

DAO interfaces to instrument hardware — cameras, frame grabbers, SLMs, tip-tilt
stages, PDUs, and RTC latency monitoring.

Every device driver follows the same pattern: a small process opens the vendor
device, publishes frames / state to POSIX shared memory (`dao.shm`), and watches
a set of control SHMs for runtime updates. GUIs and pipelines only ever talk to
the SHMs, never to the hardware directly.

## Layout

| folder | hardware | build type | needs |
|--------|----------|------------|-------|
| [`aravis/`](aravis/README.md)       | GigE / USB3 Vision cameras (AVT, FLIR, First Light C-BLUE, …) | C, waf | `aravis-0.8` |
| [`edt/`](edt/README.md)             | EDT PDV frame grabbers (OCAM²k, C-RED 1, SciMeasure Joe)      | C, waf | EDT PDV SDK |
| [`fli/`](fli/README.md)             | First Light C-RED 1 / 2 / 3                                   | C + Py | EDT PDV and/or FLI SDK |
| [`nuvu/`](nuvu/README.md)           | Nüvü HNü 512 EMCCD                                            | C, waf | Nüvü SDK |
| [`evt/`](evt/README.md)             | Emergent Vision 10/25/100 GigE                                | C, waf | EVT eSDK |
| [`iport/`](iport/README.md)         | Pleora iPORT config download/upload                           | C++, waf | Pleora eBUS SDK |
| [`hamamatsu/`](hamamatsu/README.md) | Hamamatsu ORCA (DCAM)                                         | Python + Qt | DCAM-API Lite |
| [`ids/`](ids/README.md)             | IDS uEye                                                      | Python | uEye SDK + `pyueye` |
| [`basler/`](basler/README.md)       | Basler Ace                                                    | Python | pylon + `pypylon` |
| [`meadowlark/`](meadowlark/README.md) | Meadowlark SLM                                              | Python | Blink SDK (Windows) |
| [`thorlabs/`](thorlabs/README.md)   | Thorlabs EXULUS SLM display                                   | Python | `pygame`, `PyOpenGL` |
| [`pi/`](pi/README.md)               | PI E-518 tip-tilt mirror                                      | Python | GCS over TCP/IP |
| [`arcus/`](arcus/README.md)         | Arcus ACE-SDE motor controller                                | Python | `pyserial` |
| [`rittal/`](rittal/README.md)       | Rittal CMC III PDU                                            | Python | `pysnmp` |
| [`cisco/`](cisco/README.md)         | Cisco ERSPAN v3 traffic capture (header lib)                  | C++ hdr | Linux raw socket |

Support folders: `common/` (shared C — GigE readers, timing), `apps/` (helpers +
`daoMonitor`), `config/` (camera LUTs / iPORT configs), `gui/`, `docs/`.

## Build

Prerequisites: **daoBase** installed (`mudpi.h`, `libdao*` in `$DAOROOT`), a C/C++
toolchain, and `waf`.

```bash
waf configure --prefix=$DAOROOT
waf
waf install
```

`configure` probes each vendor SDK and **silently skips** any folder whose SDK is
absent — a missing SDK is a warning, not an error:

```
Checking for EDT PDV SDK      : not found
EDT SDK not found. Skipping edt build. Use --edt=/path/to/EDTpdv
```

Override auto-detection with `--edt=`, `--nuvu=`, `--evt=`, `--pleora=` (or the
`EDT_ROOT` / `NUVU_ROOT` / `EVT_ROOT` / `PUREGEV_ROOT` env vars). Pure-Python
device folders are always installed; `basler/` installs only if `pypylon`
imports.

Other options: `--debug` (`-g`), `--sanitizer` (ASan), `--test`.

### aravis

Aravis is not packaged — build it from source
(<https://github.com/AravisProject/aravis>,
[docs](https://aravisproject.github.io/aravis/aravis-stable/building.html)):

```bash
sudo apt install meson libxml2-dev libglib2.0-dev libusb-1.0-0-dev \
                 libgirepository1.0-dev gettext gobject-introspection
git clone https://github.com/AravisProject/aravis && cd aravis
meson setup build && cd build && ninja && sudo ninja install
```

On macOS install to `/opt/aravis` and export:

```bash
export DYLD_LIBRARY_PATH=$DYLD_LIBRARY_PATH:/opt/aravis/lib
export PKG_CONFIG_PATH=$PKG_CONFIG_PATH:/opt/aravis/lib/pkgconfig
```

## Control-SHM convention

For an image SHM `/tmp/<name>.im.shm`, controllers create sibling scalar SHMs:

| SHM | meaning |
|-----|---------|
| `<name>Dit.im.shm`  | exposure time |
| `<name>Fps.im.shm`  | frame / loop rate |
| `<name>Gain.im.shm` | gain (camera dependent) |

plus camera-specific extras (`EmGain`, `TargetTemp`, `Roi`, `ReadoutSpeed`,
`SetTemp`, …) documented in each folder's README. `apps/daoHwSet*.py` are
command-line setters for these; `daoImgDisp.py <shm>` is a quick viewer.

## daoMonitor

`apps/daoMonitor` passively measures AO RTC latency from an ERSPAN mirror. It
needs raw-socket capability:

```sh
sudo setcap cap_net_raw,cap_net_admin+ep $DAOROOT/bin/daoMonitor
```
