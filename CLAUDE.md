# PRIMA — banco AO didattico (istruzioni per Claude Code)

Banco di ottica adattiva per il corso di laurea magistrale in astrofisica (INAF‑Arcetri).
Sensore a piramide con modulazione di tip/tilt + MEMS BMC Multi‑DM 140, tutto pilotato dal laptop
"alienware" (utente `labot`). Al corso ci saranno solo questo laptop e il banco: tutto deve girare qui.

## Hardware
| Parte | Dispositivo | Accesso |
|---|---|---|
| WFS | Allied Vision Manta G‑419 (GigE, CMV4000 2048², 5.5 µm) | Aravis, `prima/aolab/devices/camera_aravis.py` |
| Correttore | BMC Multi‑DM 140 (USB FX2 1781:0ed8) | `daoprima/hw/bmc_usb.py` → `BmcUsbDM` |
| Modulatore | PI S‑334 su controller E‑518 (TCP, GCS ASCII) | `prima/aolab/devices/pi_modulator.py` |
| Alimentazione | presa Meross **mss210** | `python -m prima.hardware.power status\|on\|off\|cycle` |

Pupilla sul DM ≈ 4.5 mm → 96 attuatori attivi su 140. Non c'è sorgente di turbolenza esterna:
la turbolenza la genera il DM. Le facce della piramide sono leggermente sghembe (pupille mai
perfettamente uguali a 0 mrad: è normale).

## ⚠️ Regole di sicurezza (obbligatorie)
1. **Alimentazione: SOLO la presa `mss210`. Non toccare MAI la `mss425e`** (è un altro banco).
   Usa solo `prima.hardware.power`, che rifiuta qualsiasi altro tipo di presa. Non scrivere codice
   che elenchi o comandi altre prese Meross.
2. **Credenziali** in `~/git/.secrets/meross.json` (chmod 600): mai stamparle, copiarle, committarle.
3. **DM**: comandi sempre in [0, 1]; il motore limita lo scostamento dal flat a ±`max_delta` (0.25).
   All'apertura il DM va al flat; alla chiusura rampa al flat e poi **HV off** (`close()`).
   Non usare il vecchio `daodm_bmc_ctrl` insieme a `BmcUsbDM`.
   Sequenza control bits (da BMCUSB di J. Codona): 0x0002 → 0x0082, HV on 0x0088, HV off 0x0008.
4. **Modulatore**: raggio ≤ 40 mrad. **R = 0 significa uscite in DC a metà corsa (MOV al centro 50 GCS),
   mai uscite disabilitate.** La modulazione deve essere sempre centrata a metà range degli assi.
   Pivot: `SVO C 0; SVA C 100`. I potenziometri di offset manuali del driver sono a 0: non assumere offset esterni.
5. **Niente sudo, niente root.** Se serve un pacchetto di sistema, chiedi a Marco.
6. **Fine sessione**: quando il lavoro sul banco è chiuso e i risultati sono soddisfacenti →
   modulatore R=0 al centro, DM al flat + HV off, poi `python -m prima.hardware.power off`.
   Prima di spegnere chiudi GUI e script che tengono aperti i dispositivi.

## Ambiente
```bash
source ~/git/.venv-prima/bin/activate      # usa sempre questo python
cd ~/git/prima
python -m pytest tests/test_aolab_sim.py -q    # test sul simulatore (devono passare)
python -m prima.aolab.gui --sim                # GUI col gemello numerico
python -m prima.aolab.gui --hw --binning 2 --exposure 20 --fmod 50 --cam-gain 6   # banco, 41 Hz
```
Nella GUI: Find pupils → ROI on pupils → Reference = now → Acquire IM → CLOSE LOOP.

Repo vicini utili: `~/git/arte` (libreria di analisi del gruppo, da usare per telemetria/analisi),
`~/git/prima_data` (calibrazioni e dati, fuori da git), opticalib su GitHub ArcetriAdaptiveOptics.

## Struttura del codice
- `prima/aolab/` — software nuovo del banco:
  `dm_geometry.py` (attuatori, basi KL/Zernike/zonale/Hadamard), `wfs.py` (pupille, slopes PWFS,
  dark follower), `calibration.py` (IM push‑pull, ricostruttore SVD), `disturbance.py` (turbolenza
  frozen‑flow, statica), `telemetry.py`, `engine.py` (`AOEngine`: thread RTC, loop, calibrazione,
  save/load), `devices/` (sim, Aravis, PI, BMC), `gui/` (GUI stile daoEkarus).
- `daoprima/`, `prima/hardware/` — codice precedente; modificare con cautela.
- `scripts/aolab/` — script di prova sul banco (`hw_smoke.py`, `cam_bench.py`, `mod_bench.py`, …).
- `tools/labrunner.py` — coda di job usata da Claude in Cowork quando non c'è shell locale.
  Con Claude Code in locale non serve; non lanciare job sulla coda mentre lavori qui.

## Note tecniche già verificate (non riscoprirle)
- Camera: packet size **1500** (MTU 1500; i jumbo danno zero frame). La Manta **non ha binning**:
  si usa la decimazione (scarta pixel, non li somma). Dopo ogni cambio di ROI/decimazione/esposizione
  chiamare `set_fps(None)` (la camera non alza da sola `AcquisitionFrameRateAbs`).
- Frame rate: decim. 2 + ROI ≈ 40 fps; decim. 4 + ROI ≈ 80 fps. Oltre 41 Hz il loop è limitato dalla luce.
- Modulatore: risposta in ampiezza 0.95 @20 Hz, 0.77 @50, 0.49 @100, 0.21 @200 (compensata in
  `AMP_GAIN_*`). A 100 Hz la modulazione ottica reale è ~metà (sensibilità TT dell'IM doppia):
  per il corso **modulazione 50 Hz, esposizione = 1 periodo (20 ms), loop 41 Hz**.
  L'esposizione deve essere sempre un multiplo esatto del periodo di modulazione.
- Le ampiezze in nm sono **nominali** (DM non ancora calibrato all'interferometro):
  `nm_per_unit ≈ 18000` nm di fronte d'onda per unità di comando.

## Modo di lavorare
- **Prima simula, poi prova sul banco**: accendi, misura, correggi, itera; a fine sessione spegni (regola 6).
- Non rompere l'hardware; il software si può sempre riportare indietro.
- Lavora in autonomia, chiedi a Marco solo per decisioni vere o azioni manuali sul banco
  (allineamenti, potenziometri, sorgente).
- **Log di lavoro** in `work/NN-titolo-data.md` (letti con Obsidian: usa link `[[...]]`), figure in
  `work/figs/`, dati grezzi in `work/data/` (npz/npy non vanno in git). Aggiorna `work/00-indice.md`.
- Alla fine di ogni blocco di lavoro: mini report per Marco (scritto per chi non sa nulla del lavoro,
  con plot e screenshot). Il report condiviso su claude.ai lo cura la sessione Cowork del progetto PRIMA;
  qui basta che il log in `work/` sia completo e con le figure.
- **Git**: commit con messaggi concisi ma esaustivi; push e PR con `~/git/.local/bin/gh`
  (repo ArcetriAdaptiveOptics/prima). Commit piccoli su `main` consentiti; lavori più grandi su branch
  `claude/*` con PR. Mai committare segreti, dati pesanti o `work/runner/`.

## Prossimi passi (ottobre 2026)
- Laser 632 nm in arrivo: ricontrollare saturazione/esposizione, rifare misure velocità vs rumore.
- Provare l'S‑334 in anello aperto (servo off) a 100 Hz, ampiezza calibrata otticamente dalla sensibilità TT.
- Per gli studenti: pulsante Record della telemetria (fatto: FITS + meta.json in `~/git/prima_data/telemetry/<tag>/`),
  `PrimaAnalyzer` su `arte.dataelab`, notebook di esercitazione (sensore, calibrazione, controllo,
  turbolenza con `arte.atmo`, prestazioni), GUI a due livelli, lanciatore unico.
- Configurazione 41 Hz come default della GUI.
- Camera più veloce (Alvium 1800 U‑052m): in attesa.
