# Esercitazioni PRIMA — notebook

Banco di ottica adattiva PRIMA: sensore di fronte d'onda a piramide con modulazione,
specchio deformabile MEMS Multi-DM 140 (96 attuatori nella pupilla).
Tutti i notebook funzionano sul **gemello numerico** del banco e, nell'ultima sezione,
sulle **registrazioni fatte sul banco vero** con la GUI.

| notebook | argomento | stato |
|---|---|---|
| `01-sensore` | il sensore a piramide: pupille, slope, linearità, modulazione | da fare |
| `02-calibrazione` | matrice di interazione push-pull, SVD, propagazione del rumore | da fare |
| `03-controllo.ipynb` | integratore, funzione di reiezione, ritardo, guadagno ottimo | **pronto** |
| `04-turbolenza` | schermi di von Kármán con `arte.atmo`, errore di fitting | da fare |
| `05-prestazioni` | error budget, Strehl, confronto banco / simulatore | da fare |

## Come si parte
```bash
source ~/git/.venv-prima/bin/activate
cd ~/git/prima/notebooks
jupyter lab
```

Il banco può essere usato da **un solo programma alla volta**: se un notebook usa
`lab.hw_engine()`, la GUI deve essere chiusa (e viceversa). Il simulatore (`lab.sim_engine()`)
invece si può usare sempre.

## Strumenti
- `prima.aolab.lab`: `sim_engine()`, `hw_engine()`, `calibrate(e)`, `record(e, N, etichetta)`,
  `settle(e, N)`, `close(e)`.
- `prima.aolab.analysis.PrimaAnalyzer`: apre una registrazione (`PrimaAnalyzer.get(tag)`, vedi
  `list_tags()`) ed espone la telemetria come serie temporali di
  [`arte`](https://github.com/ArcetriAdaptiveOptics/arte):
  `an.loop.residual_modes`, `an.loop.integrated_modes`, `an.loop.disturbance_modes`,
  `an.loop.pseudo_open_loop_modes`, `an.wfs.slopes`, `an.dm.commands`, `an.calib`, `an.meta`.
- Le registrazioni (dalla GUI, pulsante **RECORD**, o da `lab.record`) sono in
  `~/git/prima_data/telemetry/<data>_<ora>-<etichetta>/`: un file FITS per grandezza più
  `meta.json` con tutti i parametri.

## Convenzioni
- Coefficienti modali: modi KL del ricostruttore, rms unitario sugli attuatori attivi,
  convertiti in **nm di fronte d'onda nominali** (il DM non è ancora calibrato
  all'interferometro: `meta['nm_per_unit']` ≈ 18000 nm per unità di comando).
- Tempo e vento in **frame**: il simulatore gira più veloce del banco, ma in frame il
  comportamento è lo stesso.

## Per i docenti
`src/*.py` è la sorgente unica: `python build.py` rigenera i notebook con gli esercizi
(qui) e quelli con le soluzioni (`soluzioni/`); `python build.py 03 --execute` esegue anche
le soluzioni sul simulatore (copie eseguite in `soluzioni/_eseguiti/`, fuori da git).
