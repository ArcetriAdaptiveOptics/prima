# iport — Pleora iPORT configuration tools

`daoIportGetConfig` / `daoIportWriteConfig` — download and upload the device +
stream configuration of a **Pleora iPORT** external frame grabber from the
command line (i.e. what eBUSPlayer does, scriptable).

## Dependency

**Pleora eBUS SDK** installed at
`/opt/pleora/ebus_sdk/{Ubuntu-20.04,RHEL-CentOS}-x86_64/` (headers `PvDevice.h`
etc., libs `PvBase`, `PvBuffer`, `PvDevice`, …). Proprietary — download from the
Pleora support portal (account required).

## Build

`../wscript` `configure` auto-detects the SDK (`--pleora=/path` or the
`PUREGEV_ROOT` / `EBUS_ROOT` env var to override). If not found, this folder is
skipped (`HAVE_EBUS`), exactly like the other vendor-SDK folders.

The C++ iPORT *camera* controllers (`daoHwIPORTDeviceCtrl`, …) live in
`../aravis/`.
