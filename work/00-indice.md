# PRIMA — diario di lavoro (Claude)

Banco AO didattico: PWFS modulato (Manta G-419 + PI S-334/E-518) e BMC Multi-DM 140.
Software nuovo in `prima/aolab` (motore AO + GUI stile daoEkarus).

## Note
- [[01-ricognizione-2026-10-09]] — stato di partenza di hardware, rete, repo e prime misure
- [[02-aolab-software]] — architettura del software, come si usa, test sul simulatore
- [[03-regole-banco]] — regole di sicurezza: presa Meross, DM, modulatore
- [[04-test-hw-2026-10-09]] — test su hardware: bug del pivot E-518, bug HV del DM, **primo loop chiuso**
- [[05-dark-roi-velocita-2026-10-10]] — dark follower, ROI automatica, frame rate della Manta, banda passante del modulatore, loop a 20/41/80 Hz
- [[06-strumenti-studenti-2026-10-10]] — materiale per gli studenti: registrazione della telemetria (Record), analisi, notebook

## Come lanciare
```bash
source ~/git/.venv-prima/bin/activate
cd ~/git/prima
python -m prima.aolab.gui --sim     # gemello numerico, senza hardware
python -m prima.aolab.gui --hw      # banco vero (20 Hz)
python -m prima.aolab.gui --hw --binning 2 --exposure 20 --fmod 50 --cam-gain 6   # 41 Hz, poi 'ROI on pupils'
```
Icone sul desktop: **PRIMA AO lab GUI** (`scripts/start-aolab-gui.sh`, banco a 41 Hz;
con argomenti, es. `--sim`, li passa alla GUI) e **PRIMA labrunner** (`scripts/start-labrunner.sh`).

## Convenzioni
- Le ampiezze in **nm** sono *nominali*: stroke di 5.5 µm, deflessione proporzionale a u²,
  WF = 2 × superficie. Il DM non è ancora calibrato all'interferometro.
- Dati di calibrazione: `~/git/prima_data/<data>_<tag>/` (`calib.npz` + `meta.json`).
- Registrazioni di telemetria: `~/git/prima_data/telemetry/YYYYMMDD_HHMMSS[-etichetta]/` (FITS + `meta.json`).
- Dati grezzi dei test: `work/data/` (gli npz/npy non vanno in git).
