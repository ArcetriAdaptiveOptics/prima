# Prima

New Arcetri AO packaging/glue project (not a fork of prisma). Working name for the
later DAO-oriented slice: **daoPrima** (deferred).

## Phase 1 focus

Device plane only: **PWFS modulator** (PI S-334 @ E-518) + **WFS camera** (Manta G-419).
No filter wheel, no science DM, no DAO bridges.

Modulator API lives in upstream **`plico_dm` / `plico_dm_server`** (revived
`PIS334Modulator` + `ModulatorClient`) — **not** `piTipTilt` / `set_shape`.

## Conf (this repo)

| File | Role |
|------|------|
| `conf/modulator-sim.conf` | `simulatedModulator` on port 7030 |
| `conf/modulator-lab-e518.conf` | `piS334Modulator` → E-518 IP / S-334 serial |
| `conf/camera-sim.conf` | Simulated pyramid WFS (pysilico) |
| `conf/camera-manta-g419.conf` | `model=avt` Manta G-419 |

## Start (laptop sim)

```bash
# editable installs (example)
source ~/git/.venv-prima/bin/activate   # or your lab env
chmod +x scripts/start-phase1-sim.sh
./scripts/start-phase1-sim.sh
```

Lab hardware:

```bash
PROFILE=lab ./scripts/start-phase1-sim.sh
```

Or start processes individually:

```bash
plico_dm_server  conf/modulator-sim.conf modulator1
pysilico_server  conf/camera-sim.conf camera1
```

## REPL smoke (modulator)

```python
import plico_dm
m = plico_dm.modulator('localhost', 7030)
m.setRadiusInMilliRad(1.5)
m.setFrequencyInHz(20.0)
m.setCenterInMilliRad([0.0, 0.0])
print(m.getStatus())
```

In-process sim (no server):

```python
import plico_dm
m = plico_dm.simulated_modulator()
m.setRadiusInMilliRad(2.0)
```

## Lab IPs (confirmed; connections not yet smoke-tested)

| Device | IP |
|--------|-----|
| Manta G-419 | `192.168.30.189` |
| E-518.I3 | `192.168.30.190` |

## Product drops

- **Drop 1:** Prisma-like main GUI + PWFS absolute metrology (this conf set). See Project Prima `docs/drop-roadmap.md`.
- **Drop 2:** DM + dao closed-loop GUI.
- **Drop 3:** Second focal-plane camera; modulator as fast TT; dao TT loop.

| Path | Role |
|------|------|
| `vendor/daoEkarus` | **Primary reference** for daoPrima — later |
| `vendor/daoTools` | AO pipeline tools |
| `vendor/daoHw` | Hardware device drivers ↔ dao SHM |

See `vendor/README.md`.

## Do not

- Edit anything under `vendor/daoHw`, `vendor/daoTools`, or `vendor/daoEkarus`.
- Drive the PWFS modulator as a 2-DoF DM (`piTipTilt` / `set_shape`).
- Fork or modify prisma for this work.
