# Prima — Drop 1 PWFS absolute metrology

Arcetri packaging for Drop 1: live **Aravis** Manta frames + **direct PI E-518 GCS** tip/tilt modulation, with a Prisma-like metrology GUI.

## Live stack (this PR)

| Role | Device | Path |
|------|--------|------|
| WFS camera | Allied Vision **Manta G-419** (`192.168.30.189`) | **Aravis** GigE |
| PWFS modulator | PI **S-334** @ E-518 (`192.168.30.190:50000`) | **direct GCS TCP** |

**Deferred (not in this PR):** `pysilico_server` (`:7130`), `plico_dm_server` (`:7030`), VimbaX/vmbpy camera path, BMC Multi-DM / DaoPrima (Drop 2).

## Run

```bash
source ~/git/.venv-prima/bin/activate   # or your venv
pip install -e ~/git/prima

# Live bench (also Desktop launcher “Prima Drop 1”)
./scripts/start-drop1-live-gui.sh
# or:
prima-gui --live --aravis-ip 192.168.30.189 --e518-host 192.168.30.190

# Offline demo
prima-gui
python scripts/smoke_drop1_metrology.py
```

Desktop installer:

```bash
cp scripts/Prima-Drop1.desktop ~/Desktop/ ~/.local/share/applications/
chmod +x ~/Desktop/Prima-Drop1.desktop scripts/start-drop1-live-gui.sh
gio set ~/Desktop/Prima-Drop1.desktop metadata::trusted true
```

## GUI (what works)

- **Connect live** / **Use demo** (no plico Start/Stop)
- Exposure lock `t_exp = 1/f_mod`; radius does not change exposure
- Modulator radius / freq / center → **Apply to E-518**; gain presets 0–40 mrad
- Idle park at **+50 V** mid-scale; modulation swings around mid
- E-518 live readback: Vpp, frequency, VOL, WGO / PARKED
- Pupils, Take Measure, Auto Align, sync dialog

## Hardware notes

- Camera: single Aravis owner (close other Vision apps before Connect).
- Modulator: single GCS TCP client; mid-travel park uses `SVA` with servo off.
- Safe radius ceiling default **40 mrad** (`PRIMA_MOD_MAX_MRAD`).

## Tests (bench)

```bash
python scripts/test_drop1_exp_freq_sync.py
python scripts/test_drop1_pi_direct.py
python scripts/test_drop1_park_midscale.py
python scripts/test_drop1_modulation_frames.py
```

## Vendor references (do not modify)

Read-only trees under `vendor/` (daoEkarus / daoTools / daoHw) if present — not required to run Drop 1.
