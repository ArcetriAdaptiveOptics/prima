# Strumenti per gli studenti — 2026-10-10

Torna a [[00-indice]]. Precedente: [[05-dark-roi-velocita-2026-10-10]].

Blocco "punto 3": registrazione della telemetria, analisi con `arte.dataelab`, notebook,
GUI a due livelli. Branch `claude/student-tools`.
Scelte di Marco: **GUI in inglese, materiale per gli studenti in italiano**; gli studenti
sono della magistrale in fisica (Python/numpy, Fourier, algebra lineare li sanno già).

## 1. Registrazione della telemetria (Record)
`prima/aolab/recorder.py` + `AOEngine.start_recording(n_frames, label, n_cam_frames)` /
`stop_recording()`. Nella GUI: riquadro "Loop control" → *Record frames*, *+ cam frames*,
etichetta, **RECORD** (diventa STOP), barra di avanzamento, percorso del salvataggio.

- Buffer preallocati riempiti dal thread RTC (solo copie di array); i file si scrivono
  in un thread separato a buffer pieno, quindi il loop non rallenta.
- Cartella `~/git/prima_data/telemetry/YYYYMMDD_HHMMSS[-etichetta]/`: il nome è un tag valido
  per `arte.dataelab` (deve avere **un solo** underscore, per questo l'etichetta è unita con `-`).
  Le registrazioni stanno in `telemetry/`, separate dalle calibrazioni salvate con "Save calib".
- Contenuto: `scalars.fits` (tabella per frame: t, frame, flux, dark, …), `slopes`, `modes`
  (residuo ricostruito R·s), `int_modes` (stato dell'integratore), `dist_modes`, `dm_cmd`,
  `loop_cmd`, `dist_cmd`, opzionale `frames` (primi K frame della camera), `calib.fits`
  (IM, REC, M2C, SV, REF, FLAT, ACTIVE) e `meta.json` (loop, calibrazione, camera, modulatore,
  turbolenza, statica, versione del software, frame persi, frequenza del loop misurata).
- Il frame k di tutti gli array è la stessa iterazione RTC. Verifica nel test
  `test_record_telemetry`: sui dati registrati vale esattamente c_k = leak·c_{k−1} − g·m_k.

GUI sul simulatore durante una registrazione (300 frame, 39.8 Hz, 0 frame persi):
![[figs/gui_record_sim.png]]

## 2. Analisi: `PrimaAnalyzer` su `arte.dataelab`
`prima/aolab/analysis.py`, sul modello di `ekarelab` (daoEkarus).
`PrimaAnalyzer.get(tag)` (oppure il percorso della cartella) e `list_tags()`:
- `an.loop`: `residual_modes` $m_k$, `integrated_modes` $c_k$, `disturbance_modes` $d_k$,
  `pseudo_open_loop_modes` $m_k - c_{k-D}$, tutti in nm nominali come serie `arte`
  (`get_data`, `time_std`, `power`, `plot_spectra`, …), più gain, leak e frequenza del loop;
- `an.wfs`: slope (con `to_maps`), frame della camera, flusso, dark; `an.dm`: comandi per canale;
  `an.calib`: IM, REC, M2C, valori singolari, riferimento, flat, attuatori attivi;
- `an.modalplot()`, `an.summary()`; gli scalari per frame sono in `an.scalar(nome)`.

Sul banco il disturbo lo genera il DM, quindi $d_k$ è **noto**: è la verità con cui
confrontare lo pseudo open loop. Convenzione verificata: $m_k = d_{k-D} + c_{k-D} + n_k$.
**Sul simulatore D = 1 frame**; sul banco va misurato (esercizio del notebook 3).

## 3. API per i notebook: `prima/aolab/lab.py`
`lab.sim_engine(fps, flux)` (gemello numerico già calibrato), `lab.hw_engine()` (banco, configurazione
a 41 Hz), `lab.calibrate`, `lab.record(e, N, etichetta)` (bloccante, restituisce l'analyzer),
`lab.settle`, `lab.close`. Il simulatore di default ha moltissima luce (6·10⁶ fotoni per frame,
quasi senza rumore). Con `flux = 2e4` il pavimento di rumore è quello del banco a 41 Hz:

| flux (fotoni/frame) | residuo misurato g=0.3 | residuo vero g=0.3 |
|---|---|---|
| 6·10⁶ | 0.9 nm | 0.3 nm |
| 1·10⁵ | 8.0 nm | 3.1 nm |
| 3·10⁴ | 18.6 nm | 7.1 nm |
| 1·10⁴ | 42.7 nm | 17.5 nm |

## 4. Notebook di esercitazione
`notebooks/`: sorgente unica in `notebooks/src/NN_nome.py` (celle "percent" con tag
`[esercizio]` / `[soluzione]`), `notebooks/build.py` genera la versione per gli studenti
(`notebooks/NN-nome.ipynb`) e quella con le soluzioni (`notebooks/soluzioni/`); con `--execute`
esegue le soluzioni sul simulatore. Lingua italiana, livello magistrale: gli esercizi chiedono
di ricavare e implementare, non di riempire una riga.

**Pilota: `03-controllo`** (≈ 10 min di esecuzione sul simulatore):
1. modello z dell'integratore con ritardo: $H_\mathrm{rej} = 1/(1 + g z^{-D}/(1-\ell z^{-1}))$, $H_n$;
2. stabilità: $g_\mathrm{max}$ = 2, 1, 0.62, 0.45 per D = 1…4;
3. misura: stima di D dal disturbo noto, RTF misurata = PSD(residuo)/PSD(pseudo open loop);
4. guadagno ottimo: rumore puro (varianza misurata $\sigma_n^2\,2/(2-g)$, vera $\sigma_n^2\,g/(2-g)$) e
   scan del guadagno per due velocità del vento, residuo misurato e vero;
5. sul banco: registrazioni dalla GUI e analisi per tag.

RTF misurata sul simulatore e modello con D = 1 (nessun parametro libero):
![[figs/nb03_rtf_sim.png]]

Solo rumore, luce del banco (σₙ = 23.4 nm): misurato 24.7/27.1/33.4/47.9 nm contro il modello
24.7/27.0/33.1/46.8 per g = 0.2/0.5/1/1.5; vero 7.9/13.8/23.8/41.8 contro 7.8/13.5/23.4/40.6.

Residuo in funzione del guadagno (luce del banco): ottimo g ≈ 0.5 con vento 0.1/frame (17.6 nm),
g ≈ 1.4 con vento 2/frame (78 nm).
![[figs/nb03_gain_scan_sim.png]]

## Da fare
- [x] `PrimaAnalyzer` su `arte.dataelab`
- [x] notebook pilota 03-controllo
- [ ] notebook 01, 02, 04, 05 (dopo il parere di Marco sul pilota)
- [ ] misurare D sul banco
- [ ] GUI a due livelli + lanciatore unico, 41 Hz come default
- [ ] provare Record sul banco

## Tentativo sul banco (10/10, rimandato a lunedì)
Banco spento: camera (.189) e modulatore (.190) non rispondono al ping, DM assente su USB.
`power status` fallisce: il login HTTP Meross riesce e il broker MQTT è raggiungibile,
ma **mss210 e mss425e risultano entrambe offline** ("Failed to enroll device"). Due prese
in stanze diverse insieme → probabile problema di cloud Meross o Wi‑Fi, non delle prese.
Lunedì: controllare l'app Meross/LED della presa, poi `lab.hw_engine()` → calibrazione →
`lab.record` → misura di D e RTF sul banco → Record dalla GUI.
