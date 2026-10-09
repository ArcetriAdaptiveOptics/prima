# Dark follower, ROI e loop più veloce — 2026-10-09/10

Torna a [[00-indice]]. Precedente: [[04-test-hw-2026-10-09]].

## 1. Dark follower
- Prima: per ogni frame veniva sottratta la mediana di un campione di pixel fuori dalle pupille (oltre 1.3 r), senza alcun filtro nel tempo.
- Ora (`PyramidProcessor`, `dark_mode`):
  - pixel di fondo = fuori dai 4 dischi oltre **1.2 r** (per escludere l'alone), sottocampionati a circa 40k pixel;
  - su questi pixel si calcola la **media**, scartando il 5 % più luminoso (luce diffusa, pixel caldi);
  - la media viene poi filtrata con una **media mobile esponenziale** su `dark_frames` frame (20 di default).
- Modalità disponibili: `follower` (default), `frame` (solo il frame corrente), `fixed`, `off`. Nella GUI ci sono la combo "Dark", il numero di frame e la casella "show dark area"; il valore del dark compare sotto l'immagine della camera.
- Sul banco (20 ms, gain 6 dB): dark = 99.2 ± 1.1 ADU nel tempo, contro un picco delle pupille di circa 770 ADU.

![[figs/dark_roi.png]]

## 2. ROI e frame rate
**Bug**: la Manta non alza da sola `AcquisitionFrameRateAbs` quando si riduce la ROI o l'esposizione, quindi restava a 12.9 fps. Ora `AravisCamera.set_fps(None)` porta il frame rate al massimo consentito dopo ogni cambio di ROI, decimazione o esposizione.

`scripts/aolab/cam_bench.py`, fps misurati:

| decimazione | ROI | t_exp 20 ms | t_exp ≤ 10 ms |
|---|---|---|---|
| 1 | pieno frame 2048² | 12.9 | 12.9 |
| 1 | pupille (1624×1648) | 20 | 20 |
| 2 | pieno frame 1024² | 32.8 | 32.8 |
| 2 | pupille (816×832) | **40.4** | 40.4 |
| 4 | pieno frame 512² | 49.7 | 65.2 |
| 4 | pupille (408×416) | 49.7 | **80.0** |

ROI automatica: `AOEngine.roi_to_pupils(margin_px)` (nella GUI "ROI on pupils"). Il riquadro è tangente alle pupille esterne più un margine. La geometria viene traslata e la calibrazione resta valida.

## 3. Modulatore: banda passante
`scripts/aolab/mod_bench.py` (POS? campionato, R = 10 mrad): rapporto tra ampiezza ottenuta e richiesta = 0.95 a 20 Hz, 0.77 a 50 Hz, 0.49 a 100 Hz, 0.21 a 200 Hz, 0.05 a 400 Hz.
Compensazione nel driver: `AMP_GAIN_*`, il raggio comandato è diviso per il guadagno. Con la compensazione, a 50/100/150 Hz il p-p letto dal sensore è 23.3 / 24.6 / 23.5 GCS (atteso 23.0) e il cerchio resta un cerchio (`mod_ellipse.py`, rapporto assi ≥ 0.98).
**Ma a 100 Hz la modulazione ottica effettiva è circa la metà**: la sensibilità del PWFS a tip/tilt raddoppia (IM: 96–100 contro 50 a 20 Hz), e per la piramide la sensibilità va come 1/R_mod. Quindi il sensore di posizione dell'S-334 a 100 Hz non rappresenta il tilt reale dello specchio. A 50 Hz la sensibilità è uguale a quella a 20 Hz, quindi la modulazione è corretta.

## 4. Loop a tre velocità (60 KL, gain 0.3, leak 0.99)
![[figs/speed_configs_telemetry.png]]

| config | Hz | IM | residuo misurato, flat closed | statico open → closed | turbolenza closed |
|---|---|---|---|---|---|
| decim. 2, pieno frame, 50 ms, mod. 20 Hz | 20 | 30 s | 16 nm | 222 → 18 nm | 32 nm |
| decim. 2 + ROI, 20 ms, mod. 50 Hz, gain 6 dB | **41** | 15 s | 30 nm | 187 → 32 nm | 45 nm |
| decim. 4 + ROI, 10 ms, mod. 100 Hz, gain 12 dB | 80 | 7.5 s | 46 nm | 90 → 46 nm | 52 nm |

Lettura:
- In tutti e tre i casi il comando del loop (blu) insegue il disturbo (arancio): la correzione funziona.
- Il **pavimento di rumore** del residuo misurato cresce con la velocità: meno fotoni per frame (esposizione più corta e decimazione, che scarta pixel invece di sommarli).
- A 80 Hz il PWFS si **satura**: un'aberrazione statica di 230 nm viene letta come 90 nm (modulazione ottica dimezzata, vedi §3). Il loop chiude comunque, perché porta il segnale verso 0, ma insegue peggio i picchi della turbolenza.
- Il vento è in pixel per frame, quindi a 80 Hz la turbolenza scorre 4 volte più veloce in tempo reale.
- **Configurazione consigliata per il corso: 41 Hz** (decimazione 2 + ROI, 20 ms, modulazione 50 Hz).

GUI sul banco a 41 Hz, turbolenza di 150 nm, loop chiuso (calcolo 3.8 ms per frame):
![[figs/gui_hw_turb_closed.png]]

## 5. Telemetria
Nuovo canale `dm_res_rms` = rms di (turb + static + loop) sugli attuatori attivi: è ciò che resta, sul DM, del disturbo dopo la correzione, ed è indipendente dal rumore del WFS. Si somma all'offset costante della correzione della statica del banco.

## Da fare
- Più luce dalla sorgente per abbassare il rumore e salire oltre i 40 Hz (domanda aperta a Marco).
- Calibrazione ottica della modulazione ad alta frequenza (regolare R_cmd finché la sensibilità a TT non torna quella a 20 Hz) oppure accettare 50 Hz come massimo.
