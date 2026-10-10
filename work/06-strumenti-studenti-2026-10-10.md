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

## Da fare
- [ ] `PrimaAnalyzer` su `arte.dataelab`
- [ ] notebook di esercitazione
- [ ] GUI a due livelli + lanciatore unico, 41 Hz come default
- [ ] provare Record sul banco
