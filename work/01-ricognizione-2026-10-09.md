# Ricognizione — 2026-10-09

Torna a [[00-indice]].

## Laptop alienware
- Intel Ultra 9 185H (22 core), 30 GB di RAM, RTX 4060 8 GB, Python 3.14 (venv `~/git/.venv-prima`, che usa anche i pacchetti di sistema).
- NIC del banco: `enp45s0` 192.168.30.192/24, **MTU 1500**, 1 Gb/s.
- Repo `prima`: HEAD su `cursor/drop2-dao-bmc-7fc6`; ora `main` è stato portato a quel commit in fast-forward e i nuovi commit vanno su `main`.

## Hardware
| Dispositivo | Indirizzo | Note |
|---|---|---|
| Manta G-419B (FW 00.01.54) | 192.168.30.189 | 2048×2048, Mono8/Mono12, **niente binning** (max 1), decimazione 1–8 |
| PI E-518 + S-334 | 192.168.30.190:50000 | GCS ASCII su TCP (driver `prima/hardware/pi_e518_modulator.py`) |
| BMC Multi-DM 140 | USB 1781:0ed8 | driver pyusb `daoprima/hw/bmc_usb.py`, flat di fabbrica `data/bmc/multidm-flat.txt` (media 0.82) |
| Presa Meross mss210 | cloud | alimenta tutto il banco tranne il laptop, vedi [[03-regole-banco]] |

Un processo `daodm_bmc_ctrl --prefer usb` girava **dal 1° ottobre** e teneva il DM occupato.

## Camera: perché a volte non arrivavano frame
- Con `gv_auto_packet_size` la camera negozia **8228 byte** (jumbo), ma la NIC ha MTU 1500 → **0 frame, 156 errori in 6 s**.
- Con pacchetti da **1500** byte: **12.9 fps** a pieno frame Mono12 (8 MB/frame; il limite GigE è 115 MB/s).
- Per il loop conviene ridurre i dati: decimazione 2 (1024²) e/o ROI sulle pupille.
- Opzionale, va fatto da Marco con sudo: `sudo ip link set enp45s0 mtu 9000` e `sudo sysctl -w net.core.rmem_max=33554432`, poi pacchetti da 8228.

## Pupille e modulazione
![[figs/probe_modulation.png]]

- A **R = 0** tutta la luce cade su una faccia (in alto a destra): la PSF è fuori dall'apice della piramide.
- Da R ≥ 10 mrad compaiono tutte e 4 le pupille, ma con uno sbilanciamento basso/alto: a 10 mrad i flussi sono 1.42 / 1.22 / 0.70 / 0.67 della media.
- Centri a pieno frame (riga, colonna): (514, 475), (549, 1640), (1686, 443), (1718, 1603). Raggio ≈ 195–200 px, cioè ≈ 89 px/mm sul DM (pupilla di 4.5 mm).
- Nelle pupille si vede bene la griglia degli attuatori (print-through del MEMS, passo ≈ 36 px).
- Azione: Marco centra la PSF con il tip-tilt manuale della montatura usando `scripts/aolab/align_viewer.py`.
