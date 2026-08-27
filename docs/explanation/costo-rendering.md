---
slug: costo-rendering
type: explanation
status: stable
tags: [rendering, performance, grains, numpy]
sources:
  - src/pge/rendering/numpy_audio_renderer.py
  - src/pge/core/stream.py
  - utils/bench_cost.py
last_synced_commit: 855f00e
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
| `a` | ~32 µs per grano | costruire il `Grain`, finestrarlo, sommarlo nel buffer |
| `b` | ~1,3 ms per secondo di uscita | allocare, normalizzare e scrivere il buffer |

Errore relativo mediano sotto l'1,5%, massimo ~5%. Due parametri coprono tre
ordini di grandezza di grani e due di durata. Fra run ripetute i coefficienti
oscillano di qualche punto percentuale.

**I due termini pareggiano attorno ai 40 grani al secondo.** Sotto quella
densità comanda la durata dell'uscita; sopra comandano i grani. Il regime
granulare d'uso sta sopra — a densità 100 il termine dei grani pesa 2,4 volte
quello della durata, a densità 800 pesa venti volte — quindi *nella pratica* il
costo lo governa la popolazione, non la durata del pezzo. Ma non è vero come
enunciato assoluto: a parità di grani, allungare l'uscita da 5 a 320 secondi
quadruplica il tempo.

### Dove va il tempo

I grani sono **lazy**: `Stream.grains` è una property che chiama
`generate_grains()` al primo accesso (`src/pge/core/stream.py`). Chi li tocca per
primo è il render, quindi senza forzare la materializzazione il costo di
costruire gli oggetti finisce dentro il tempo di rendering. Forzarla prima non
cambia il totale — 1,071 s contro 1,085 s sullo stesso materiale — ma separa le
due metà del lavoro:

| materiale | grani | durata | parse | costruzione dei `Grain` | overlap-add + scrittura | totale |
|---|---|---|---|---|---|---|
| esempio didattico multi-stream | 38 072 | 32,4 s | 0,008 s | 0,52 s (13,7 µs/grano) | 0,57 s | **1,10 s** |
| `configs/PGE_cim.yml` | 994 291 | 92,5 s | 0,036 s | 8,87 s (8,9 µs/grano) | 19,94 s | **28,85 s** |

Circa un terzo del costo, in un caso reale, è **materializzare la popolazione**,
non il DSP. È il prezzo della rappresentazione intermedia esplicita: la lista di
`Grain` esiste come oggetto ispezionabile prima di diventare campioni, ed è
quello che rende possibili la `map`, gli export e il debugging.

In memoria quella lista costa poco: **~225 byte per grano** (`Grain` ha
`__slots__` e 8 campi), cioè 8,5 MB per 38 000 grani. Il picco del processo è
dominato da NumPy e dal buffer audio, non dai grani.

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
`Stream.__repr__` legge `_grains` invece della property: stampare gli stream
appena creati, altrimenti, li genererebbe tutti.

**Cosa non è misurato qui.** L'export della `map` (matplotlib) e gli altri export
non entrano in questi numeri: sono consumatori della stessa lista di grani, con
un costo proprio. E l'avvio del processo — import di NumPy e matplotlib — pesa
circa 0,3 s a invocazione, che su un rendering breve non è trascurabile.

## Implicazioni codice

- `src/pge/rendering/numpy_audio_renderer.py` — `_overlap_add` sceglie fra il
  path sequenziale e `_overlap_add_parallel` in base a `jobs` e
  `min_parallel_grains`; è il termine `a` del modello.
- `src/pge/core/stream.py` — la property `grains` e la generazione lazy; è la
  metà del termine `a` che non è DSP.
- `utils/bench_cost.py` — produce tutte le misure di questa pagina. Non ha
  dipendenze oltre a quelle del motore e genera un sample sintetico se `refs/`
  è vuota, quindi gira su un clone pulito.

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
