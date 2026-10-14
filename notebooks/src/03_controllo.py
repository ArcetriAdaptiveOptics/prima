# %% [markdown]
# # 3 — Controllo: l'integratore e la funzione di reiezione
#
# Banco PRIMA: sensore a piramide modulato + DM Multi-DM 140 (96 attuatori nella pupilla).
# In questo notebook studiamo la **legge di controllo** del loop: un integratore modale con
# guadagno $g$ e *leak* $\ell$, e un ritardo di $D$ frame tra la misura e l'applicazione
# della correzione.
#
# **Obiettivi**
# 1. ricavare la funzione di trasferimento di reiezione (RTF) del loop e la sua stabilità;
# 2. misurarla dalla telemetria e confrontarla con il modello;
# 3. stimare il ritardo $D$ del sistema e scegliere il guadagno ottimo.
#
# Lavoriamo prima sul **gemello numerico** del banco (stesso software, stessa interfaccia),
# poi ripetiamo le misure sul banco vero (ultima sezione).
#
# **Convenzioni.** Tutte le grandezze modali sono coefficienti dei modi KL del ricostruttore
# (rms unitario sugli attuatori attivi), convertiti in nm di fronte d'onda *nominali*.
# Il tempo è in frame: $f$ è la frequenza normalizzata, $f/f_s \in [0, 1/2]$.
#
# Sul banco la turbolenza non arriva dall'esterno: la **genera il DM stesso**, sommando al
# comando del loop uno schermo di fase che scorre (*frozen flow*). Quindi il disturbo è
# **noto**, frame per frame: un lusso che al telescopio non si ha.

# %%
import numpy as np
import matplotlib.pyplot as plt
from scipy import signal

from prima.aolab import lab
from prima.aolab.analysis import PrimaAnalyzer, list_tags

plt.rcParams['figure.figsize'] = (8, 4.5)
plt.rcParams['axes.grid'] = True

# %% [markdown]
# ## 1. Il modello
#
# A ogni frame $k$ il ricostruttore $R$ trasforma le slope $s_k$ nei coefficienti modali
# misurati $m_k = R\,s_k$, e l'integratore aggiorna il comando (in coefficienti modali):
#
# $$ c_k = \ell\, c_{k-1} - g\, m_k . $$
#
# Il DM somma il comando del loop $c$ al disturbo $d$ (generato anch'esso dal DM). Il sensore
# vede la somma con un ritardo di $D$ frame (lettura della camera, calcolo, tempo in cui il
# comando arriva al DM mentre la camera sta già esponendo):
#
# $$ m_k = d_{k-D} + c_{k-D} + n_k , $$
#
# dove $n_k$ è il rumore di misura.
#
# **Esercizio 1.**
# (a) Passando alla trasformata $z$, ricavate la funzione di reiezione
# $H_\mathrm{rej}(z) = M(z) / \big(z^{-D} D(z)\big)$ (residuo misurato / disturbo) e la
# funzione di trasferimento del rumore $H_n(z) = C(z)/N(z)$.
# (b) Scrivete una funzione `rtf(f, g, leak=1.0, D=1)` che restituisca $|H_\mathrm{rej}|^2$
# per frequenze normalizzate $f$ e tracciatela, in scala log-log, per $g = 0.2, 0.5, 1, 1.5$
# con $D=1$, e poi con $D=2$.
# (c) Che cosa succede a bassa frequenza al variare del leak? E vicino a Nyquist?

# %% [esercizio]
def rtf(f, g, leak=1.0, D=1):
    """|H_rej|^2 alle frequenze normalizzate f (= f/fs)."""
    z = np.exp(2j * np.pi * f)
    # TODO
    raise NotImplementedError

f = np.linspace(1e-3, 0.5, 2000)
# TODO: grafici per D=1 e D=2

# %% [soluzione]
# Z-trasformata: C = -g M / (1 - l z^-1),   M = z^-D (D + C)
#   => M (1 + g z^-D / (1 - l z^-1)) = z^-D D
#   => H_rej = 1 / (1 + g z^-D / (1 - l z^-1))
#      H_n   = C/N = -g / (1 - l z^-1 + g z^-D)
def rtf(f, g, leak=1.0, D=1):
    """|H_rej|^2 alle frequenze normalizzate f (= f/fs)."""
    z = np.exp(2j * np.pi * f)
    return np.abs(1.0 / (1.0 + g * z ** -D / (1.0 - leak * z ** -1))) ** 2

f = np.linspace(1e-3, 0.5, 2000)
fig, axs = plt.subplots(1, 2, figsize=(12, 4.5), sharey=True)
for ax, D in zip(axs, (1, 2)):
    for g in (0.2, 0.5, 1.0, 1.5):
        ax.loglog(f, rtf(f, g, D=D), label='g = %.1f' % g)
    ax.loglog(f, rtf(f, 0.5, leak=0.95, D=D), 'k:', label='g = 0.5, leak 0.95')
    ax.axhline(1, color='k', lw=0.8)
    ax.set_title('D = %d frame' % D)
    ax.set_xlabel('f / fs')
axs[0].set_ylabel('|H_rej|²')
axs[0].set_ylim(1e-4, 100)
axs[1].legend()
plt.show()
# - bassa frequenza: con leak = 1, |H|² ~ (2πf/g)² -> 0; con leak < 1 tende a
#   ((1-l)/(1-l+g))², cioè una reiezione finita (il leak "dimentica").
# - vicino a Nyquist (z = -1): |H|² = 1/(1 - g/(1+l))² per D=1 (pari) ...
#   l'amplificazione cresce con g: il loop amplifica rumore e disturbo veloci.
# - con D=2 le curve per g >= 1 non hanno senso fisico: il loop è instabile (esercizio 2).

# %% [markdown]
# ## 2. Stabilità
#
# **Esercizio 2.** I poli del sistema ad anello chiuso sono le radici di
# $z^{D-1}(z-\ell) + g = 0$. Calcolate numericamente (con `np.roots`) il guadagno massimo
# stabile $g_\mathrm{max}$ per $D = 1, 2, 3, 4$ e $\ell = 1$. Confrontate con il risultato
# analitico per $D=1$ e $D=2$. Qual è la **banda di reiezione** (frequenza dove $|H|^2 = 1$)
# a $g = g_\mathrm{max}/2$?

# %% [esercizio]
# TODO

# %% [soluzione]
def gmax(D, leak=1.0):
    gs = np.linspace(0.001, 3, 3000)
    for g in gs:
        p = np.zeros(D + 1)
        p[0], p[1] = 1.0, -leak        # z^D - l z^(D-1)
        p[-1] += g                     # + g
        if np.max(np.abs(np.roots(p))) >= 1:
            return g
    return np.inf

for D in (1, 2, 3, 4):
    g = gmax(D) / 2
    fbw = f[np.argmax(rtf(f, g, D=D) >= 1)]
    print('D = %d   g_max = %.3f   banda (g = g_max/2) = %.3f fs' % (D, gmax(D), fbw))
# D=1: polo z = 1 - g -> g_max = 2.   D=2: z^2 - z + g, |z|^2 = g -> g_max = 1.
# Un frame di ritardo in più dimezza (circa) guadagno e banda utilizzabili.

# %% [markdown]
# ## 3. La misura: telemetria dal simulatore
#
# Avviamo il gemello numerico del banco già calibrato (pupille, riferimento, matrice di
# interazione con 50 modi KL, ricostruttore). Si usa esattamente come il banco vero:
# `e` è lo stesso `AOEngine` che c'è dietro la GUI.
#
# | comando | effetto |
# |---|---|
# | `e.set_turbulence(True, rms=0.01, wind=0.5, seed=1)` | turbolenza sul DM: `rms` in unità DM (×18000 ≈ nm), `wind` in campioni/frame |
# | `e.lp.gain`, `e.lp.leak` | parametri dell'integratore |
# | `e.close_loop()`, `e.open_loop(reset=True)` | chiude / apre (e azzera) il loop |
# | `lab.record(e, N, 'etichetta')` | registra N frame e restituisce un `PrimaAnalyzer` |
#
# Ogni registrazione finisce in `~/git/prima_data/telemetry/<tag>/` e si può riaprire con
# `PrimaAnalyzer.get(tag)`: vedi `list_tags()`.

# %%
e = lab.sim_engine()
e.set_turbulence(True, rms=0.01, wind=0.5, seed=1)
lab.settle(e, 50)
print('loop rate %.0f Hz (simulatore), %d modi' % (e.loop_rate_hz(), e.rec.n_modes))

# %% [markdown]
# Prima registrazione: **anello aperto**. Il residuo misurato è il disturbo (ritardato) più
# il rumore.

# %%
e.open_loop(reset=True)
lab.settle(e, 20)
ol = lab.record(e, 2048, 'ctrl-ol')
ol.summary()

# %% [markdown]
# Il `PrimaAnalyzer` espone la telemetria come serie temporali di `arte`:
#
# - `an.loop.residual_modes` — $m_k$ (tempo × modo, nm)
# - `an.loop.integrated_modes` — $c_k$
# - `an.loop.disturbance_modes` — $d_k$, il disturbo vero proiettato sui modi
# - `an.loop.pseudo_open_loop_modes` — $m_k - c_{k-D}$ (con `an.delay_frames`)
# - `an.wfs.slopes`, `an.dm.commands`, `an.calib.im`, `an.meta`, …
#
# `.get_data()` restituisce l'array (una `Quantity` di astropy: `.value` per il numpy puro),
# `.time_std`, `.power()`, `.plot_spectra()` fanno statistiche e spettri.

# %%
m = ol.loop.residual_modes.get_data().value
d = ol.loop.disturbance_modes.get_data().value
plt.plot(ol.time, m[:, 0], label='misurato m (modo 0, tip)')
plt.plot(ol.time, d[:, 0], label='disturbo d (modo 0)')
plt.xlabel('t [s]'); plt.ylabel('nm'); plt.legend(); plt.show()

# %% [markdown]
# **Esercizio 3 — il ritardo.** In anello aperto $m_k = d_{k-D} + n_k$.
# Usate la telemetria (`m`, `d`) per stimare $D$: per esempio con la cross-correlazione,
# oppure trovando lo shift che minimizza $\mathrm{rms}(m_k - d_{k-D})$. Attenzione al termine
# costante: il WFS vede anche l'aberrazione statica del banco.
# Quanto vale il rumore $n_k$ (rms totale in nm)?

# %% [esercizio]
# TODO

# %% [soluzione]
def mismatch(m, d, D):
    a = m[D:] - m[D:].mean(0)
    b = d[:len(d) - D] - d[:len(d) - D].mean(0)
    return np.sqrt(((a - b) ** 2).sum(1).mean())

for D in range(5):
    print('D = %d   rms(m_k - d_k-D) = %6.1f nm' % (D, mismatch(m, d, D)))
D_sim = min(range(5), key=lambda D: mismatch(m, d, D))
print('-> D = %d; rumore + aliasing ~ %.1f nm su %.1f nm di disturbo'
      % (D_sim, mismatch(m, d, D_sim), np.sqrt((d.std(0) ** 2).sum())))

# %% [markdown]
# Ora chiudiamo il loop con diversi guadagni (leak = 1, integratore puro) e registriamo.
# Per ogni registrazione la **RTF misurata** è il rapporto tra lo spettro del residuo e lo
# spettro del disturbo in anello aperto, che stimiamo con il *pseudo open loop*
# $m_k - c_{k-D}$ (lo stesso che si fa al telescopio, dove $d$ non è noto).
#
# **Esercizio 4.**
# (a) Registrate 2048 frame per $g = 0.2, 0.5, 1.0, 1.5$ (lasciate assestare il loop prima
# di registrare: `lab.settle(e, 100)`).
# (b) Calcolate le PSD (Welch, per esempio `nperseg=256`, media sui modi) di residuo e pseudo
# open loop, il loro rapporto, e confrontatelo con `rtf(f, g, D=...)` dell'esercizio 1.
# (c) Verificate che lo pseudo open loop coincida con il disturbo vero $d$.

# %% [esercizio]
gains = [0.2, 0.5, 1.0, 1.5]
runs = {}
for g in gains:
    pass   # TODO: imposta gain/leak, chiudi, assesta, registra in runs[g]

# %% [soluzione]
gains = [0.2, 0.5, 1.0, 1.5]
runs = {}
for g in gains:
    e.lp.gain, e.lp.leak = g, 1.0
    e.reset_loop()
    e.close_loop()
    lab.settle(e, 100)
    runs[g] = lab.record(e, 2048, 'ctrl-g%.1f' % g)
    e.open_loop(reset=True)
    print('g = %.1f  ->  %s' % (g, runs[g].snapshot_tag()))

# %% [soluzione]
def psd(x, nperseg=256):
    fr, p = signal.welch(x - x.mean(0), fs=1.0, nperseg=nperseg, axis=0)
    return fr, p.mean(axis=1)

fig, axs = plt.subplots(2, 2, figsize=(12, 8), sharex=True, sharey=True)
for ax, g in zip(axs.flat, gains):
    an = runs[g]
    fr, p_res = psd(an.loop.residual_modes.get_data().value)
    _, p_pol = psd(an.pseudo_open_loop(D_sim))
    ax.loglog(fr[1:], (p_res / p_pol)[1:], '.', label='misurata')
    ax.loglog(fr[1:], rtf(fr[1:], g, D=D_sim), 'k', label='modello D=%d' % D_sim)
    ax.axhline(1, color='gray', lw=0.8)
    ax.set_title('g = %.1f' % g)
axs[0, 0].legend(); axs[1, 0].set_xlabel('f / fs'); axs[1, 1].set_xlabel('f / fs')
axs[0, 0].set_ylabel('|H_rej|²'); axs[1, 0].set_ylabel('|H_rej|²')
plt.show()

an = runs[0.5]
pol = an.pseudo_open_loop(D_sim)
dd = an.loop.disturbance_modes.get_data().value[:len(pol)]
plt.plot(an.time[D_sim:], pol[:, 0], label='pseudo open loop, modo 0')
plt.plot(an.time[D_sim:], dd[:, 0], '--', label='disturbo vero, modo 0')
plt.xlabel('t [s]'); plt.ylabel('nm'); plt.legend(); plt.show()

# %% [markdown]
# ## 4. Il guadagno ottimo
#
# Il residuo ha due contributi con andamento opposto in $g$: l'errore **temporale**
# (disturbo non inseguito, diminuisce con $g$) e il **rumore** propagato (cresce con $g$).
# Finora il simulatore aveva moltissima luce (6·10⁶ fotoni per frame) e quasi niente rumore.
# Portiamolo alla luce del banco a 41 Hz: `e.sim_model.flux = 2e4`.
#
# **Esercizio 5.**
# (a) Rumore puro: spegnete la turbolenza, registrate in anello aperto e stimate $\sigma_n$
# (rms totale per frame, nm). Poi chiudete il loop con $g = 0.2, 0.5, 1, 1.5$ e mostrate che,
# per $D=1$ e $\ell=1$, la varianza del residuo *misurato* vale $\sigma_n^2 \cdot 2/(2-g)$
# e quella del residuo *vero* sul DM ($d+c$) vale $\sigma_n^2 \cdot g/(2-g)$.
# (b) Con la turbolenza, misurate il residuo rms misurato e vero in funzione di $g$ tra 0.05
# e 1.8, per `wind=0.1` e `wind=2.0` campioni/frame (1024 frame per punto bastano).
# (c) Dove sta il guadagno ottimo nei due casi? Perché si sposta? Quale dei due residui
# (misurato o vero) usereste per sceglierlo, e perché?

# %% [esercizio]
e.sim_model.flux = 2e4
# TODO

# %% [soluzione]
e.sim_model.flux = 2e4

def res_rms(an):
    """(residuo misurato, residuo vero sul DM) rms totali in nm."""
    r = an.loop.residual_modes.get_data().value
    c = an.loop.integrated_modes.get_data().value
    dd = an.loop.disturbance_modes.get_data().value
    return np.sqrt((r.std(0) ** 2).sum()), np.sqrt(((c + dd).std(0) ** 2).sum())

def run(g, n=1024, label='ctrl'):
    e.lp.gain, e.lp.leak = g, 1.0
    e.reset_loop()
    if g > 0:
        e.close_loop()
    lab.settle(e, 150)
    an = lab.record(e, n, '%s-g%.2f' % (label, g))
    e.open_loop(reset=True)
    return an

# (a) solo rumore: m = H_rej n,  c = H_n n.  Per D=1, l=1:
#     2 int_0^1/2 |H_rej|^2 df = 2/(2-g),    2 int |H_n|^2 df = g/(2-g)
e.set_turbulence(False)
sigma_n = res_rms(run(0.0, label='ctrl-noise'))[0]
print('sigma_n = %.1f nm per frame' % sigma_n)
print('   g   misurato  modello |  vero (DM)  modello   [nm]')
for g in (0.2, 0.5, 1.0, 1.5):
    meas, true = res_rms(run(g, label='ctrl-noise'))
    print('%4.1f   %7.1f  %7.1f  |  %7.1f  %7.1f' % (
        g, meas, sigma_n * np.sqrt(2 / (2 - g)), true, sigma_n * np.sqrt(g / (2 - g))))

# %% [soluzione]
# (b), (c)
g_scan = [0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0, 1.4, 1.8]
scan = {}
for wind in (0.1, 2.0):
    e.set_turbulence(True, rms=0.01, wind=wind, seed=1)
    scan[wind] = np.array([res_rms(run(g, label='ctrl-w%.1f' % wind)) for g in g_scan])
fig, axs = plt.subplots(1, 2, figsize=(12, 4.5))
for wind, r in scan.items():
    l, = axs[0].semilogy(g_scan, r[:, 0], 'o-', label='wind %.1f' % wind)
    axs[1].semilogy(g_scan, r[:, 1], 'o-', color=l.get_color(), label='wind %.1f' % wind)
    print('wind %.1f: g ottimo %.2f (misurato), %.2f (vero); residuo vero minimo %.1f nm'
          % (wind, g_scan[int(np.argmin(r[:, 0]))], g_scan[int(np.argmin(r[:, 1]))], r[:, 1].min()))
axs[0].set_title('residuo misurato dal WFS'); axs[1].set_title('residuo vero sul DM (d + c)')
for ax in axs:
    ax.set_xlabel('guadagno g'); ax.set_ylabel('rms [nm]'); ax.legend()
plt.show()
# Con vento lento l'errore temporale è piccolo e conviene un guadagno basso (meno rumore);
# con vento veloce serve più banda.  Il residuo misurato *sovrastima* il rumore di un
# fattore sqrt(2/g) e lo pesa in modo diverso: il criterio giusto è il residuo vero, che al
# telescopio non si conosce, ma si può stimare (pseudo open loop + modello di H_rej e H_n).

# %% [markdown]
# **Domande.**
# - Il residuo *misurato* dal WFS non è il residuo *vero* del fronte d'onda: in che cosa
#   differiscono? (Suggerimento: `an.dm.residual_commands` è disturbo + correzione sul DM,
#   indipendente dal rumore del sensore.)
# - Per il solo rumore il residuo misurato è $\sqrt{2/g}$ volte quello vero. Per l'errore
#   temporale invece misurato e vero coincidono (a meno del ritardo): perché?
# - Con $D=2$ come cambierebbero i risultati?

# %%
lab.close(e)

# %% [markdown]
# ## 5. Sul banco
#
# Ripetete le misure principali sul banco vero, a 41 Hz (modulazione 50 Hz, esposizione 20 ms).
#
# 1. Avviate la GUI dall'icona **PRIMA AO lab GUI** e seguite la sequenza
#    *Find pupils → ROI on pupils → Reference = now → Acquire IM → Compute reconstructor*.
# 2. Accendete la turbulenza dal riquadro *Disturbance* (rms 150 nm, wind 0.3).
# 3. Nel riquadro *Loop control* registrate (pulsante **RECORD**, 2048 frame, ≈ 50 s)
#    una sequenza in anello aperto e almeno tre guadagni, con etichette chiare
#    (es. `ol`, `g0.2`, `g0.5`, `g1.0`).
# 4. Analizzate le registrazioni qui sotto con `PrimaAnalyzer.get(tag)`.
#
# **Esercizio 6.** Quanto vale $D$ sul banco? Qual è $g_\mathrm{max}$? Confrontate la RTF
# misurata con il modello: dove si discosta, e perché? (Pensate a che cosa fa la camera
# mentre il DM si muove, e all'esposizione di 20 ms su un periodo di 24 ms.)

# %%
list_tags('*-ol')[-5:]        # le ultime registrazioni in anello aperto

# %% [esercizio]
# bench = {g: PrimaAnalyzer.get('...') for g in (...)}
# TODO
