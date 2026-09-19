# evt — Emergent Vision Technologies cameras

`daoEvtCtrl.C` — control + acquisition for **Emergent Vision (EVT)** 10/25/100 GigE
cameras. Streams frames to a DAO SHM and watches the standard control SHMs.

## Dependency

**EVT eSDK** installed at `/opt/EVT/eSDK` (headers `EmergentCameraAPIs.h`,
libs `EmergentCamera`, `EmergentGigEVision`, `EmergentGenICam`).
Download from <https://emergentvisiontec.com/>.

EVT cameras need a tuned high-speed NIC (large ring buffers, jumbo frames, and
usually the EVT-provided network optimisation script).

## Build

`../wscript` `configure` auto-detects the SDK (`--evt=/path/to/eSDK` to
override); if not found, this folder is skipped (`HAVE_EVT`).
