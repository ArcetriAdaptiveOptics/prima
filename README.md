# Prima

New Arcetri AO packaging/glue project (not a fork of prisma). Working name for the
DAO-oriented slice: **daoPrima**.

## Status

Scaffold deferred. This repo currently vendors **read-only** Durham DAO reference
trees used to design daoPrima.

## Vendor references (DO NOT MODIFY)

| Path | Role |
|------|------|
| `vendor/daoEkarus` | **Primary reference** for daoPrima — EKARUS AO system RTC glue on daoBase/daoHw/daoTools |
| `vendor/daoTools` | AO pipeline tools (centroids, MVM, integrators, SHM utilities) |
| `vendor/daoHw` | Hardware device drivers publishing/consuming dao SHM |

See `vendor/README.md`. Mirror extracts also live at `/home/labot/git/vendor/dao-refs/`.

## Do not

- Edit anything under `vendor/daoHw`, `vendor/daoTools`, or `vendor/daoEkarus`.
- Fork or modify prisma for this work.
