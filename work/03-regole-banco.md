# Regole del banco

Torna a [[00-indice]].

## Alimentazione — presa Meross
> [!danger] Regola
> Il banco PRIMA è alimentato dalla presa **mss210**. La **mss425e** è un ALTRO banco: **non va mai toccata**.

- Wrapper: `python -m prima.hardware.power status|on|off|cycle`.
- Accetta solo dispositivi di tipo `mss210` e rifiuta qualsiasi altro tipo. Se sull'account ci sono zero o più `mss210`, si rifiuta comunque.
- Il labrunner rifiuta ogni job che contenga la stringa `mss425e`.
- Credenziali **fuori dal repo**: `~/git/.secrets/meross.json` (permessi 600).
- Il laptop non è sulla presa: un power cycle non lo spegne.
- Prima di spegnere: DM al flat, poi chiusura del driver (HV off).

## DM (BMC Multi-DM 140)
- Comandi sempre in [0, 1], con clip nel driver (`BmcUsbDM`) e nel motore.
- Il motore limita anche lo scostamento dal flat a ±`max_delta` (default 0.25).
- All'apertura il DM va **direttamente al flat**, senza passare da 0.5. All'uscita viene parcheggiato al flat con una rampa, poi HV off.
- Watchdog del loop: se la slope rms supera 4 volte quella alla chiusura, oppure più del 30 % degli attuatori è saturo, per 30 frame → loop aperto e integratore azzerato.
- Il vecchio `daodm_bmc_ctrl` va fermato prima di aprire il DM via USB (`BmcUsbDM` si rifiuta se lo trova attivo).

## Modulatore (E-518 / S-334)
- Raggio massimo 40 mrad (limite già presente nel driver). All'avvio il driver porta gli assi a metà corsa (+50 V).
- Lavoro: 10 mrad, 20 Hz, t_exp = 50 ms (un periodo).

## Labrunner
- `python3 ~/git/prima/tools/labrunner.py` in un terminale sul laptop: esegue i job che Claude mette in `work/runner/queue/` e scrive i log in `work/runner/out/`.
- Ctrl-C per fermarlo. Non usa mai sudo e non gira come root.
