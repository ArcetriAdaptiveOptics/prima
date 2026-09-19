# cisco — ERSPAN capture

`daoErspan.hpp` — header-only C++ library to capture, filter and parse a
**Cisco ERSPAN v3** mirrored traffic stream (raw `AF_PACKET` socket + BPF
filter). Used to tap camera/instrument traffic that a Cisco switch SPAN-mirrors
to this host.

## Dependency

Linux only (`linux/if_packet.h`, `linux/filter.h`). Links `daoLog`. No external
SDK.

## Privileges

Opening a raw packet socket needs `CAP_NET_RAW` (or root). For a built consumer:

```bash
sudo setcap cap_net_raw,cap_net_admin+ep <binary>
```

## Build / install

Header only — `#include "daoErspan.hpp"`. Not a standalone build target.
