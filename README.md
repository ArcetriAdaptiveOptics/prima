# Prima — Drop 1 PWFS + Drop 2 BMC Multi-DM (DAO)

Arcetri packaging for the Prima bench.

## Drops

| Drop | Hardware | Control path |
|------|----------|--------------|
| **1** | Manta G-419 + PI S-334 @ E-518 | Aravis + direct GCS TCP |
| **2** | BMC Multi-DM 5.5 µm (140 act) | **DAO SHM** → `daodm_bmc_ctrl` → USB/sim |

plico_dm BMC is optional later — not the Drop 2 bring-up path.

## Run

```bash
source ~/git/.venv-prima/bin/activate
pip install -e ~/git/prima

# Main launcher (opens Drop1 / Drop2 sub-GUIs)
python -m prima.gui.control_launcher
# or: ./scripts/start-prima-control.sh

# Drop 1 live
./scripts/start-drop1-live-gui.sh

# Drop 2 DM (DAO)
python scripts/check_bmc_usb.py
python -m daoprima.apps.daodm_bmc_ctrl --prefer auto --create-graph &
python -m prima.gui.dm_panel
```

Expected USB ID: **1781:0ed8**. If missing, sim backend still exercises SHM + GUI.

### udev (once, when DM is plugged)

```bash
sudo cp ~/git/prima/udev/99-bmc-multidm.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
```

## Desktop

```bash
cp scripts/Prima-Control.desktop scripts/Prima-Drop1.desktop \
  ~/Desktop/ ~/.local/share/applications/
```

## Vendor references (read-only)

`vendor/daoEkarus`, `vendor/daoHw`, `vendor/daoTools` — do not modify.
