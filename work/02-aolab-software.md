# Software `prima/aolab`

Torna a [[00-indice]]. Regole di sicurezza: [[03-regole-banco]].

Scopo didattico: mostrare in una sola finestra le parti principali di un loop AO:
**sensore → calibrazione (IM push-pull su una base modale) → ricostruttore → integratore con gain → DM**.
In più c'è una turbolenza generata dal DM stesso, con feedback in tempo reale (medie mobili).

## Architettura
```
camera (Manta / sim) ──frame──► PyramidProcessor ── slopes ──► R (SVD) ── modi ──► integratore
                                   (pupille, ref)                              c = leak·c − g·m
DM = flat + Σ canali ◄─────────────────────────────────────── loop = M2C·c
     canali: loop | turb | static | calib | user        (clip [0,1] e ±max_delta)
```
Tutto gira in un solo thread real-time (`AOEngine._rtc`): un frame nuovo, poi slopes, modi, integratore e comando al DM. La calibrazione gira in un thread a parte e sincronizza i poke sui frame (`settle` frame scartati dopo ogni comando).

| Modulo | Contenuto |
|---|---|
| `dm_geometry.py` | griglia 12×12 senza i 4 angoli, attuatori dentro la pupilla da 4.5 mm (**96 su 140**), basi KL (von Kármán), Zernike, zonale, Hadamard |
| `wfs.py` | ricerca delle 4 pupille, ricampionamento a 32 px sul diametro, slopes Sx/Sy normalizzate al flusso medio, riferimento |
| `calibration.py` | IM push-pull, ricostruttore SVD troncato |
| `disturbance.py` | turbolenza frozen-flow (schermo di von Kármán traslato dal "vento"), aberrazioni statiche (Zernike) |
| `telemetry.py` | buffer circolari, media mobile, rms modale |
| `engine.py` | loop, canali del DM, watchdog, salvataggio e caricamento della calibrazione |
| `devices/` | `camera_aravis.py` (Manta), `hw.py` (DM USB, E-518), `sim.py` (gemello numerico) |
| `gui/main.py` | GUI |

## GUI
![[figs/aolab_gui_sim.png]]

Pannelli:
- **WFS camera**: le 4 pupille, saturazione, fps.
- **Camera & modulation**: esposizione, raggio, frequenza e centro della modulazione.
- **Slopes**: mappe di Sx, Sy e intensità.
- **Calibration**: (1) trova pupille → (2) riferimento → (3) IM con base, numero di modi, ampiezza in nm, frame per poke → (4) ricostruttore con numero di modi e taglio SVD. Grafico dei valori singolari e della sensibilità per modo; Save/Load.
- **Modal reconstruction**: barre dei coefficienti istantanei; linee con la rms mobile del residuo e della perturbazione iniettata per modo; mappa del WF ricostruito sul DM.
- **Time history**: medie mobili (finestra regolabile) di WF ricostruito, perturbazione, comando del loop e slope rms; la banda verde indica il loop chiuso.
- **Loop control**: gain (slider), leak, CLOSE/OPEN, reset.
- **Deformable mirror**: mappa del canale scelto, poke di un attuatore, applicazione di un modo, parcheggio al flat, salvataggio del flat corrente, flat di fabbrica.
- **Disturbance**: turbolenza (rms e vento), Zernike statici in nm.

## Gemello numerico (`--sim`)
Funzioni di influenza gaussiane (accoppiamento 15 %), MEMS con deflessione proporzionale a u², pupilla di 4.5 mm, aberrazione statica di 80 nm, propagazione di Fraunhofer attraverso la piramide con 16+ punti di modulazione, rumore fotonico e di lettura.

Test (`pytest tests/test_aolab_sim.py`, 4 test): basi ortonormali, inversione del ricostruttore, IM e loop chiuso su turbolenza (residuo < 35 % dell'open loop), clip di sicurezza del DM.

![[figs/sim_gain_scan.png]]

Turbolenza di circa 230 nm rms, 60 KL. Residuo vero (WF rms) a loop chiuso: g = 0.1 → 88 nm, g = 0.3 → 58 nm, g = 0.6 → 45 nm.
Sul laptop il simulatore gira a ~60 Hz; il calcolo delle slopes richiede 0.3 ms.

## Da fare / idee
- Base KL proiettata sulle IF misurate (procedure di opticalib) quando ci sarà la calibrazione all'interferometro.
- Optical gain del PWFS in funzione della modulazione: bel tema per gli studenti.
- Pannello "PSF" per mostrare cosa vede un'immagine. Non c'è una camera scientifica: si può simulare dalla ricostruzione.
