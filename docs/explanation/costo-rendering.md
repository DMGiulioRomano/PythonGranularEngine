---
slug: costo-rendering
type: explanation
status: stable
tags: [rendering, performance, grains, numpy]
sources:
  - src/pge/rendering/numpy_audio_renderer.py
  - src/pge/core/stream.py
  - utils/bench_cost.py
  - utils/make_test_samples.py
last_synced_commit: f138d06
---

# Costo del rendering — PythonGranularEngine

> Quanto costa renderizzare, da cosa dipende, e dove va il tempo.
> Misure riproducibili con `make bench`.

**Documenti collegati:** [[INDEX]] · [[architecture]] (pipeline generazione →
rendering) · [[caching]] (come si evita di rifare il lavoro) ·
[[multi-voice]] (le voci moltiplicano i grani) · [[cli]] (`--jobs`).

---

## Problema

«Quanto ci mette?» è la prima domanda pratica di chi compone in tempo differito,
e la risposta ingenua è sbagliata in entrambi i versi. Non è «quanto dura il
pezzo», perché il motore non simula il tempo che passa: somma segmenti. Ma non è
neppure «solo il numero di grani», perché il buffer di uscita va comunque
allocato, normalizzato e scritto, e quel lavoro scala coi campioni.

Serve un modello che dica quale delle due grandezze comanda, e in quale regime.

## Modello

Il costo di un rendering si scompone in due termini indipendenti:

```
t  =  a · N_grani  +  b · D_secondi
```

Fit ai minimi quadrati su 23 punti di misura (tre sweep, da 10² a 3·10⁴ grani e
da 5 a 320 secondi), Apple M2 Max, Python 3.11, rendering sequenziale:

| coefficiente | valore | cosa paga |
|---|---|---|
| `a` | ~34 µs per grano | costruire il `Grain`, finestrarlo, sommarlo nel buffer |
| `b` | ~1,4 ms per secondo di uscita | allocare, normalizzare e scrivere il buffer |

Errore relativo mediano sotto l'1%, massimo ~9% (il punto peggiore è il più
piccolo dello sweep, dove il costo fisso dell'avvio pesa). Due parametri coprono
tre ordini di grandezza di grani e due di durata. Fra run ripetute i
coefficienti oscillano di qualche punto percentuale: i valori qui vengono da una
misura successiva alla issue #201, che ha tolto da `generate_grains()` il
flatten+sort eager della vista `Stream.grains`, e restano gli stessi entro
quell'oscillazione — il flatten valeva il ~3% della sola generazione, cioè meno
del rumore fra run.

**I due termini pareggiano attorno ai 42 grani al secondo.** Sotto quella
densità comanda la durata dell'uscita; sopra comandano i grani. Il regime
granulare d'uso sta sopra — a densità 100 il termine dei grani pesa 2,4 volte
quello della durata, a densità 800 pesa venti volte — quindi *nella pratica* il
costo lo governa la popolazione, non la durata del pezzo. Ma non è vero come
enunciato assoluto: a parità di grani, allungare l'uscita da 5 a 320 secondi
quadruplica il tempo.

### Dove va il tempo

I grani sono **lazy**: `Stream.voices` è una property che chiama
`generate_grains()` al primo accesso (`src/pge/core/stream.py`). Chi li tocca per
primo è il render, quindi senza forzare la materializzazione il costo di
costruire gli oggetti finisce dentro il tempo di rendering. Forzarla prima non
cambia il totale — è lo stesso lavoro, spostato — ma separa le due metà:

| materiale | grani | durata | parse | costruzione dei `Grain` | overlap-add + scrittura | totale |
|---|---|---|---|---|---|---|
| `configs/PGE_ff2_rassegna.yml` | 221 082 | 1 698 s | 0,12 s | 1,72 s (7,8 µs/grano) | 13,11 s | **14,95 s** |
| `configs/PGE_cim.yml` | 994 555 | 92,5 s | 0,04 s | 9,73 s (9,8 µs/grano) | 20,45 s | **30,22 s** |

I due casi hanno il rapporto grani/durata rovesciato — 130 grani al secondo il
primo, 10 700 il secondo — ed è il motivo per cui la quota di costruzione
cambia: un ottavo del totale sul primo, quasi un terzo sul secondo. Nel regime
denso **materializzare la popolazione** costa quanto una fetta consistente del
DSP. È il prezzo della rappresentazione intermedia esplicita: la lista di
`Grain` esiste come oggetto ispezionabile prima di diventare campioni, ed è
quello che rende possibili la `map`, gli export e il debugging.

In memoria quella lista costa **~225 byte per grano** (`Grain` ha `__slots__`
e 8 campi): 50 MB per i 221 082 grani di `PGE_ff2_rassegna.yml`, 224 MB per i
994 555 di `PGE_cim.yml`. Non è trascurabile nel regime denso, ma il picco del
processo resta dominato da NumPy e dal buffer audio, non dai grani. Se ne
teneva una seconda copia — la vista flat, ~8 MB per milione di grani — finché
la issue #201 non l'ha resa derivata.

## Trade-off

**Sequenziale contro parallelo.** Le misure qui sono a `--jobs 1`. Il default
della CLI è `--jobs auto`, e sopra `min_parallel_grains` l'overlap-add si
distribuisce su un pool di processi (`_overlap_add_parallel`). Sotto il migliaio
di grani il pool costa più di quanto rende: lo spawn aggiunge circa un secondo
fisso alla prima chiamata, contro i 40 ms di un rendering sequenziale di 999
grani. Il parallelo conviene sul materiale grosso, ed è lì che è acceso per
default.

**Lazy contro eager.** La property lazy non fa risparmiare lavoro — end-to-end i
due regimi coincidono entro il rumore — serve a non pagare la generazione quando
uno `Stream` viene istanziato ma non renderizzato. È il motivo per cui
`Stream.__repr__` conta da `_voices` invece che dalla property: stampare gli
stream appena creati, altrimenti, li genererebbe tutti.

**Cosa non è misurato qui.** L'export della `map` (matplotlib) e gli altri export
non entrano in questi numeri: sono consumatori della stessa lista di grani, con
un costo proprio. E l'avvio del processo — import di NumPy e matplotlib — pesa
circa 0,3 s a invocazione, che su un rendering breve non è trascurabile.

## Implicazioni codice

- `src/pge/rendering/numpy_audio_renderer.py` — `_overlap_add` sceglie fra il
  path sequenziale e `_overlap_add_parallel` in base a `jobs` e
  `min_parallel_grains`; è il termine `a` del modello.
- `src/pge/core/stream.py` — la property `voices` e la generazione lazy; è la
  metà del termine `a` che non è DSP. (`grains` è una vista derivata di
  `voices`, deprecata dalla issue #201: non partecipa al costo se non la si
  legge, e il benchmark non la legge.)
- `utils/bench_cost.py` — produce tutte le misure di questa pagina. Non ha
  dipendenze oltre a quelle del motore e gira su un clone pulito: se manca
  `refs/voice.wav` genera un seno sintetico in una directory temporanea
  riusando `utils/make_test_samples.py`, e passa quella directory come
  `samples_dir` sia al `Generator` sia al renderer — non come `ssdir`, che
  vale solo per Csound (issue #243). Il seno vale per i tre sweep, che di
  materiale audio non guardano niente; il *caso di riferimento*
  (`make bench YAML=...`) legge invece da `refs/`, perche' uno YAML reale cita
  il proprio sample.

Un cambiamento che tocchi la costruzione del `Grain` o l'overlap-add si vede
sul coefficiente `a`; uno che tocchi la scrittura del file si vede su `b`.
Rilanciare `make bench` prima e dopo è il modo più diretto per accorgersene.

## Vedi anche

- [[architecture]] — la separazione fra generazione e rendering, che è la ragione
  per cui i due termini sono separabili
- [[caching]] — come si evita di ripagare `a` su stream già renderizzati
- [[cli]] — `--jobs`
- [[multi-voice]] — ogni voce moltiplica i grani, quindi moltiplica `a`

## Riproduzione

```bash
make bench                            # i tre sweep + il fit
make bench YAML=configs/PGE_cim.yml   # + un caso di riferimento reale
```

Lo script stampa i tre sweep, la ripartizione delle fasi sul caso di riferimento
e i coefficienti del fit, e scrive un JSON con tutti i punti in una directory
temporanea. I coefficienti dipendono dalla macchina: su hardware diverso cambiano
i numeri, non la forma del modello.
