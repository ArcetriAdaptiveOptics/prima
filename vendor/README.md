# Vendor DAO references — DO NOT MODIFY

These directories are **read-only** copies of Durham Adaptive Optics repositories,
extracted from local zip archives. They exist so Prima / **daoPrima** can be
designed against real EKARUS and DAO sources without mutating upstream trees.

| Directory | Upstream | Purpose for Prima |
|-----------|----------|-------------------|
| `daoEkarus/` | daoEkarus | **Reference repository for daoPrima** — loop scripts, SHM names, ICD, GUIs, calibration apps |
| `daoTools/` | daoTools | Centroider / MVM / leaky integrator / SHM apps built on daoBase |
| `daoHw/` | daoHw | Camera/DM/hardware processes that speak dao SHM (Durham HW paths; Arcetri may prefer plico bridges) |

## Rules

1. **Do not edit** files under these three trees.
2. Treat them as documentation and API/shape references for a new Prima/daoPrima codebase.
3. Nested `.git` metadata (if present in the zip) is **stripped** on import; do not restore credentials into this repo.
4. Parallel read-only extracts: `/home/labot/git/vendor/dao-refs/{daoHw,daoTools,daoEkarus}`.

Build hints (upstream READMEs): each uses `waf configure --prefix=$DAOROOT && waf && waf install` after **daoBase** is installed.
