---
slug: supercollider-backend
type: explanation
status: stable
tags: [renderer, supercollider, nrt, osc, architecture]
sources:
  - src/pge/rendering/supercollider_renderer.py
  - src/pge/rendering/sc_score_writer.py
  - src/pge/rendering/osc.py
  - supercollider/pge_grain.scd
last_synced_commit: 2da308b
---

# Backend SuperCollider — la partitura è un file OSC

**Documenti collegati:** [[INDEX]] · [[architecture]] (OCP dei renderer) ·
[[add-renderer]] (la procedura) · [[cli]] (flag `--sc-*`) · [[errors]]
(`SuperColliderRenderError`).

---

## Problema

La lista dei grani è la rappresentazione intermedia del motore: la fase
algoritmica la produce una volta e sei consumatori la leggono — tre non sonori
(Reaper, Sonic Visualiser, JSON) e, fino a #228, due sonori (Csound, NumPy).
Due backend sonori bastano a rendere un suono, non a **falsificare** il
rendering: quando Csound e NumPy divergono non c'è un terzo parere, e quando
concordano non si sa se concordano perché hanno ragione o perché condividono
un assunto.

Serviva un terzo motore, e SuperCollider è il candidato con meno attrito:
`scsynth -N` rende in non-realtime da sempre, senza niente di sperimentale.

Il problema vero non era «far suonare SuperCollider»: era **non introdurre un
terzo comportamento**. Un backend nuovo che reimplementa le finestre, la
conversione dei dB o la soglia dei grani corti aggiunge un dialetto invece di
un controllo.

## Modello

La catena ricalca quella Csound, con un serializzatore diverso:

```
Stream -> SuperColliderScoreWriter -> .osc -> scsynth -N -> .aif
   ↑                                   ↑
   la stessa lista di grani        l'omologo binario del .sco
```

Uno score NRT è una sequenza di bundle OSC ordinati per tempo, ognuno
preceduto dalla propria lunghezza: esattamente la struttura del `.sco`
Csound — prima le tabelle, poi un evento per grano — in forma binaria.

| `.sco` Csound | `.osc` SuperCollider |
|---|---|
| `f 1 0 0 1 "pino.wav" 0 0 1` | `/b_allocReadChannel 1 "/abs/pino.wav" 0 0 0` |
| `f 2 0 1024 20 2 1` | `/b_alloc 2 4096 1` + `/b_setn 2 ...` |
| `i "Grain" 0.5 0.05 ...` | `/s_new "pgeGrain" 1000 0 0 ...` |
| `e` | `/c_set 0 0` al tempo finale |

Lo score è generato da Python: il percorso di rendering non fa girare nessun
linguaggio intermedio.

### Dove vive la parità

Tre decisioni stanno **nello score** e non nella SynthDef, e sono ciò che
tiene il backend allineato a NumPy invece che parallelo ad esso:

1. **Le finestre sono tabelle riempite dalla `NumpyWindowRegistry`**, la stessa
   che usa il renderer NumPy. Non c'è un catalogo SuperCollider: due cataloghi
   possono divergere, uno solo no. La tabella si percorre da `0` a `N-1`
   nell'arco del grano, e questa non è una scelta estetica: la registry genera
   ogni finestra su `linspace(a, b, n)`, cioè indicizzando `k/(n-1)`. Leggere
   una tabella di `N` punti da `0` a `N-1` in `n` campioni dà gli stessi
   valori, a meno dell'errore di interpolazione.

2. **Sotto `WINDOW_MIN_SHAPE_SAMPLES` (10 campioni) la finestra non si
   applica** (issue #225). Il renderer NumPy lo decide dentro `get()`, perché
   genera la finestra alla lunghezza del grano; qui la tabella è a lunghezza
   fissa e la lunghezza del grano la conosce solo lo score, che punta il grano
   a un buffer piatto. Csound quel difetto ce l'ha ancora: la sua `poscil`
   legge la tabella da 1024 punti comunque, e a tre campioni la decima.

3. **Le conversioni di unità si fanno in Python**, dove esistono già: dB →
   ampiezza lineare (`10**(v/20)`, l'`ampdb` di `main.orc`) e gradi → radianti
   (l'`irad` di `main.orc`). Due UGen in meno nel grafo e nessun posto nuovo
   dove sbagliare.

### La SynthDef, e perché sclang compare comunque

L'unico pezzo davvero nuovo è la SynthDef del grano
(`supercollider/pge_grain.scd`): l'equivalente di `csound/main.orc`, e come
quello sta nel repository come **sorgente leggibile e versionata**. Il
`.scsyndef` compilato è un artefatto di build — il renderer lo rigenera quando
manca o quando il sorgente è più recente, con la stessa regola di un Makefile
— e i suoi byte viaggiano dentro lo score via `/d_recv`, così il `.osc` è
autosufficiente.

L'alternativa era emettere il binario `.scsyndef` direttamente da Python,
eliminando sclang: la issue #228 la indicava come strada preferita, ed è stata
scartata. Il costo che eviterebbe è basso (sclang arriva nello stesso pacchetto
di scsynth, e serve una volta per checkout, non a ogni render); il costo che
introdurrebbe è un grafo di UGen serializzato a mano, che nessuno rilegge come
DSP e che nessun test può validare senza un server. Un `.scd` accanto a
`main.orc` è la forma in cui questo progetto tiene già il proprio DSP scritto
a mano.

## Trade-off

**Block size 1 di default.** `scsynth` schedula i nodi al confine del blocco:
col default (64) gli onset dei grani si quantizzerebbero a 1.33 ms a 48 kHz.
Nella sintesi granulare la posizione del grano *è* il materiale, non un
dettaglio di scheduling — e `main.orc` gira già a `ksmps=1`. Il prezzo è il
tempo di render, ed è il motivo per cui `--sc-block-size` esiste.

**Divergenze dichiarate rispetto a NumPy.** Nessuna è un difetto da chiudere:
sono scelte di cui vale la pena sapere.

| Aspetto | NumPy | SuperCollider | Perché |
|---|---|---|---|
| DC blocker + clamp | sì | no | sono post-processing del solo backend NumPy; nemmeno Csound li ha |
| File multicanale | media dei canali | primo canale | segue Csound (`GEN01` con `chan 1`); la divergenza è fra NumPy e Csound e precede questo backend |
| Finestra | generata a `n` campioni esatti | tabella da 4096 letta con interpolazione lineare | l'errore è sotto il rumore di quantizzazione a 24 bit |
| Coda della finestra | ultimo campione = `w[n-1]` | `Line` si ferma un passo prima di `end` | meno di un passo di tabella |
| Durata in campioni | `round(dur*sr)` | `trunc(dur*sr)` | sotto il campione |

**Nodi.** Il default di `scsynth` è 1024 nodi, cioè quanti grani possono
suonare insieme: una densità alta con grani lunghi lo supererebbe e il render
morirebbe a metà. Il backend chiede 32768 — è una hash table di puntatori,
costa memoria trascurabile.

**Cosa i test possono e non possono dire.** Encoder OSC, score writer, riga di
comando, cache ed errori sono verificabili senza SuperCollider installato, e lo
sono. Il grafo della SynthDef no: esiste un solo posto in cui `pge_grain.scd`
viene eseguito davvero, `tests/e2e/test_supercollider_e2e.py`. Per questo il
job e2e di CI installa `supercollider`: un e2e che si skippa non verifica
niente.

## Implicazioni codice

- `rendering/osc.py` — encoder OSC 1.0 e scrittore NRT. Un solo verso e sei
  tipi: una libreria OSC completa porterebbe parsing, trasporto UDP e pattern
  matching che qui non servono, e il formato è congelato dal 2002.
- `rendering/sc_score_writer.py` — `SuperColliderScoreWriter`, omologo di
  `ScoreWriter`. È qui che vivono le tre decisioni di parità.
- `rendering/supercollider_renderer.py` — l'adapter, modellato su
  `CsoundRenderer`: cache per stem inclusa, `--keep-osc` come `--keep-sco`.
- `RendererFactory.available_types()` e `api.renderer_types()` — l'elenco dei
  backend esiste in un posto solo. Prima era ricopiato nei messaggi d'errore
  e nel guard del print `[CACHE] Manifest:` in `cli.py`, che è il motivo per
  cui un terzo backend con la cache attiva sarebbe rimasto senza annuncio.
- `make/build.mk` — il ramo generico è `ifneq ($(RENDERER), csound)`: csound è
  l'unico che ha bisogno di flag propri, quindi è lui il caso speciale.

## Vedi anche

- [[architecture]] — l'ABC `AudioRenderer` e il perché dei due metodi atomici
- [[add-renderer]] — la procedura, di cui questo backend è l'esempio lavorato
- [[cli]] — flag `--renderer supercollider`, `--sc-*`, `--keep-osc`
- [[errors]] — `SuperColliderRenderError` e `SuperColliderNotFoundError`
- Issue [#228](https://github.com/DMGiulioRomano/PythonGranularEngine/issues/228)
