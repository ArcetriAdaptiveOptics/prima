# aravis — GigE Vision / USB3 Vision cameras (Aravis)

GenICam cameras driven through the [Aravis](https://github.com/AravisProject/aravis)
library: AVT/Allied Vision (G-030, GC1020M, GT1920), FLIR, First Light C-BLUE,
"Bob" test cameras, and a fake camera for offline work. Each `daoHw*DeviceCtrl`
binary streams frames to a DAO SHM and watches control SHMs (Dit / Fps / Gain / …).

## Dependency

`aravis-0.8` (pkg-config). Build it from source — see `INSTALL_ARAVIS` in this
folder, or:

```bash
sudo apt install meson libxml2-dev libglib2.0-dev libusb-1.0-0-dev \
                 libgirepository1.0-dev gettext gobject-introspection
git clone https://github.com/AravisProject/aravis && cd aravis
meson setup build && cd build && ninja && sudo ninja install
```

macOS installs to `/opt/aravis` — export `DYLD_LIBRARY_PATH` and
`PKG_CONFIG_PATH` accordingly (see the top-level `../README.md`).

## Build

`../wscript` `configure` probes `aravis-0.8`; if missing, this folder is skipped
(`HAVE_ARAVIS`). Targets are defined in `wscript_build`.

## Notes

- GigE cameras need the host NIC on the camera subnet with a large MTU / receive
  buffers; jumbo frames strongly recommended.
- `daoHwOcamDescramble.py` de-scrambles OCAM2 readout order.
- `test/` has helper scripts (`daoHwAravisTest.py`, …) installed to `$DAOROOT/bin`.
