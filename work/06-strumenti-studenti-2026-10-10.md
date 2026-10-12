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
- [x] misurare D sul banco → **D = 2**
- [ ] GUI a due livelli + lanciatore unico, 41 Hz come default
- [x] provare Record sul banco
- [ ] notebook 03, parte sul banco: D = 2 ⇒ g_max = 1 (non 2); usare g ≤ 0.8
- [ ] capire il rumore anomalo sul tip (modo 0) e il salto di tip a metà registrazione

## Prova sul banco (12/10)
Il 10/10 le prese Meross (mss210 e mss425e, stanze diverse) risultavano entrambe offline sul
cloud; il 12/10 erano di nuovo raggiungibili. Banco acceso, tutto su in 12 s.

Script `scripts/aolab/hw_student_tools.py` (con `--sim` gira sul gemello numerico): lo stesso
percorso del notebook 03 sul banco, solo con `lab.py` — `hw_engine` → `calibrate` (KL, 50 modi,
180 nm, 2 frame/poke) → solo rumore → anello aperto con turbolenza dal DM (180 nm, vento 0.5
px/frame) → anello chiuso a vari guadagni, 2048 frame per registrazione. Log in `work/data/`.

**Prima prova: 32.8 Hz invece di 41.** `lab.calibrate` non ritagliava la camera sulle pupille
(il passo "ROI on pupils" della GUI): pieno campo decimato 1024² va a 33 fps. Corretto:
sul banco `calibrate` ora chiama `roi_to_pupils(5)` (816×816) → **41.1 Hz**, 0 frame persi.

**Ritardo: D = 2 frame** (sul simulatore 1). Dall'anello aperto il minimo di
rms(m_k − d_{k−D}) è poco marcato (59/57/60 nm per D = 1/2/3), ma la RTF misurata,
PSD(residuo)/PSD(pseudo open loop), coincide col modello D = 2 a ogni guadagno senza parametri liberi:
![[figs/hw_rtf_41hz.png]]

Con D = 2 il guadagno massimo è 1: nella prima prova g = 1.0 ha dato la risonanza a fs/6
(residuo ~1100 nm, il watchdog non è scattato perché il loop è al limite, non divergente):
![[figs/hw_rtf_33hz_fullframe.png]]

| g (41 Hz) | residuo misurato | residuo sul DM (c+d) |
|---|---|---|
| anello aperto | 152 nm | 173 nm (disturbo) |
| 0.2 | 85 nm | 91 nm |
| 0.5 | 60 nm | 61 nm |
| 0.8 | 62 nm | 68 nm |

Rumore in anello aperto senza turbolenza: **40 nm** (il simulatore con `flux = 2e4` dà 25 nm),
dominato dal **tip**: modo 0 = 34 nm, tilt 8, gli altri ≲ 10. Lo spettro del tip è bianco e
~30× quello del tilt → il sensore è molto meno sensibile in tip (modulazione non circolare? da capire).
Nella prima prova a g = 0.5 c'è anche un **salto di tip di ~400 nm** a t ≈ 44 s più una deriva
lenta (~3 nm/s): il loop li insegue col DM, per cui c+d ≠ residuo vero (c+d include la
correzione di disturbi del banco che non vengono dal DM). Da tenere presente negli esercizi:
sul banco $d$ non è *tutto* il disturbo.
![[figs/hw_tip_drift.png]]

**Record dalla GUI** (`scripts/aolab/_shot_hw_record.py`, GUI offscreen che preme davvero il
pulsante): 2048 frame + 20 frame camera a 41.1 Hz, tutti i file scritti, l'analyzer li apre;
1 frame perso su 2048 (forse la copia dei frame camera).
![[figs/gui_hw_recording.png]]
![[figs/gui_hw_recorded.png]]

Fine prova: GUI chiusa (DM al flat + HV off), modulatore R = 0 al centro.
