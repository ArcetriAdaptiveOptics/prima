# Drop 2 — BMC via DAO (binding update)

**Date:** 2026-09-22  
**Change:** Science DM bring-up uses **DAO / daoHw patterns**, not plico_dm as primary.

## Architecture

```
[prima-dm-gui / DaoPrima loop]
        │  writes float[140] in [0,1]
        ▼
 /tmp/prima_dm1Cmd.im.shm
        │
[daodm_bmc_ctrl]   ← like daoEkarus daodmAlpaoCtrl / daoHw meadowlark
        │
 BMC Multi-DM USB (pyusb 1781:0ed8)  or  sim  or  vendor bmc.BmcDm
```

## Run

```bash
source ~/git/.venv-prima/bin/activate
cd ~/git/prima
python scripts/check_bmc_usb.py
python -m prima.gui.control_launcher          # open Drop1 / Drop2
python -m prima.gui.dm_panel                 # Drop2 only
python -m daoprima.apps.daodm_bmc_ctrl --prefer auto --create-graph
```

USB check notes: store `internal/drop2-bmc-usb-check.md`.
