# Prima

New Arcetri AO packaging/glue project (not a fork of prisma).

| Slice | Role |
|------|------|
| **`prima`** | Drop 1 PWFS metrology on the **plico** stack |
| **`daoprima`** | Drop 2+ AO loop scaffold — daoEkarus-shaped SHM/GUI, plico I/O |

## Hardware (bench)

| Role | Device | Path |
|------|--------|------|
| WFS camera | Allied Vision **Manta G-419** (`192.168.30.189`) | pysilico `model=avt` |
| WFS camera (alt) | Allied Vision **Alvium G1** | same `avt` path — conf `camera-alvium-g1.conf`; Drop 1 swap or Drop 3 FP |
| PWFS modulator | PI **S-334** @ E-518 (`192.168.30.190`) | `plico_dm` `piS334Modulator` |
| Science DM | BMC **Multi-DM 5.5 µm** (140 act, USB) | `plico_dm_server` `bmc` / `bmcMultiDM` |
| Tip-tilt | S-334 | Drop 2 modulator; Drop 3 TT DM + FP camera |

## Conf

| File | Role |
|------|------|
| `conf/modulator-sim.conf` / `modulator-lab-e518.conf` | PWFS modulator |
| `conf/camera-sim.conf` / `camera-manta-g419.conf` / `camera-alvium-g1.conf` | WFS GigE cameras |
| `conf/dm-bmc-sim.conf` / `dm-bmc-lab.conf` | BMC Multi-DM 140-act |

## Drop 1 — PWFS metrology

**Desktop (x2go):** double-click **Prima Drop 1** on the Desktop (or open it from the Applications menu).  
That runs `scripts/start-drop1-live-gui.sh` → `prima-gui --live-aravis --aravis-ip 192.168.30.189` (Manta).

In the GUI, lab modulator needs **Start** (lab profile) then **Connect live** once `plico_dm_server` can stay up on `:7030`. **Note:** the PI GCS2 shared library (`libpi_pi_gcs2.so` from the PI E-518 SDK) is still missing on this laptop, so real E-518 via `plico_dm_server` / `pi_gcs` will not start until that `.so` is installed — camera live works without it.

```bash
source ~/git/.venv-prima/bin/activate
pip install -e ~/git/prima

# Live bench GUI (same as the desktop launcher)
./scripts/start-drop1-live-gui.sh
# or:
prima-gui --live-aravis --aravis-ip 192.168.30.189

# Sim stack (no camera/hardware)
./scripts/start-phase1-sim.sh
prima-gui
python scripts/smoke_drop1_metrology.py
```

Re-install the launcher after a fresh clone:

```bash
cp ~/git/prima/scripts/Prima-Drop1.desktop ~/Desktop/
cp ~/git/prima/scripts/Prima-Drop1.desktop ~/.local/share/applications/
chmod +x ~/Desktop/Prima-Drop1.desktop ~/git/prima/scripts/start-drop1-live-gui.sh
gio set ~/Desktop/Prima-Drop1.desktop metadata::trusted true
```

## Drop 2 — BMC Multi-DM + DaoPrima

```bash
# 140-act sim DM server
./scripts/start-drop2-dm-sim.sh
# or full sim stack (camera + modulator + DM):
./scripts/start-drop2-sim.sh

# Open-loop DM panel (demo or --live against port 7050)
prima-dm-gui
prima-dm-gui --live
python scripts/smoke_drop2_dm.py --demo

# DaoPrima main GUI (SHM ICD; pipelined Python loop until daoBase)
daoprima-gui
daoprima-gui --close-loop --screenshot media/daoprima-main.png

# Pipelined loop + frame_id E2E + MVM backend report
python scripts/smoke_drop2_daoprima.py --frames 80
python scripts/smoke_frame_id.py
```

Architecture: free-run stages `cam → recon(MVM) → rtc → DM` with **`frame_id`** SHM stamps (DaoPrima improvement over daoEkarus). RTC writes `/tmp/prima_dm1Cmd.im.shm` → `ShmToDmBridge` → `plico_dm.set_shape` → BMC USB (or 140-act sim). MVM prefers CuPy GPU (daoMvMGPU-like); falls back to NumPy if CuPy/CUDA missing.

## Product drops

- **Drop 1:** Prisma-like main GUI + PWFS absolute metrology.
- **Drop 2:** BMC Multi-DM + DaoPrima AO loop (Python OK at ~Manta rates; daoBase later).
- **Drop 3:** Focal-plane camera; modulator as fast TT; dao TT loop.

## Vendor references (DO NOT MODIFY)

| Path | Role |
|------|------|
| `vendor/daoEkarus` | Primary reference for DaoPrima (SHM names, GUIs, apps) |
| `vendor/daoTools` | AO pipeline tools |
| `vendor/daoHw` | Hardware ↔ dao SHM |

## Do not

- Edit anything under `vendor/daoHw`, `vendor/daoTools`, or `vendor/daoEkarus`.
- Drive the PWFS modulator as a 2-DoF DM (`piTipTilt` / `set_shape`).
- Add a native BMC driver under daoHw for Arcetri — use plico + SHM bridge.
