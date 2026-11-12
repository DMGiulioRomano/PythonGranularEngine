---
slug: mappe-caotiche
type: explanation
status: stable
tags: [maps, expressions, chaos, grain, pointer, density]
sources:
  - src/pge/maps/catalog.py
  - src/pge/maps/map_set.py
  - src/pge/expressions/expression.py
  - src/pge/expressions/fields.py
  - src/pge/core/stream.py
  - src/pge/controllers/pointer_controller.py
  - src/pge/controllers/density_controller.py
  - src/pge/parameters/parameter.py
  - src/pge/parameters/parameter_curve.py
  - src/pge/envelopes/realized_curve.py
  - src/pge/rendering/envelope_extractor.py
last_synced_commit: 1a68fa9
entry_for: [chaotic-maps, expressions]
---

# Mappe caotiche: i parametri del grano letti da una mappa

**Documenti collegati:** [[INDEX]] · [[yaml]] (la sintassi: `maps:`, le
espressioni, `grain.iot`, `pointer.position`) · [[parameter-curve]] (come si
legge un parametro nel tempo) · [[multi-voice]] (lo stato per voce) ·
[[caching]] (il fingerprint) · [[errors]] · [[add-map]]

Il modello descritto qui è implementato (issue #307, sette fette: #308–#314).
È stato provato prima di scriverlo, in quattro pagine interattive che stanno
nel repo (`docs/plans/mappe-caotiche-pagine/`): l'ultima, «Banco del chirp», è
un granulatore di prova con lo stesso YAML.

---

## Problema

Misurato sul motore, con uno stream vero (sample di 4 s, `density: 20`):

| cosa | com'era | misura |
|---|---|---|
| posizione di lettura | `start + integrale di speed_ratio`, cioè un fasore | ogni grano cade sulla retta `p = speed·t`: scarto 0 |
| deviazione per-grano (`offset_range`) | rumore bianco attorno alla retta | autocorrelazione fra deviazioni successive −0.04 |
| attesa fra due grani | `avg·[(1−d) + d·U(0,2)]` | autocorrelazione fra attese successive +0.016 |

Tre cose — quando nasce un grano, quanto dura, da dove legge — erano una
retta più rumore bianco. **Fra un grano e il successivo non c'era memoria.**

Una mappa iterata è esattamente quello che mancava: una regola che calcola il
prossimo valore dal precedente, `x[n+1] = f(x[n], r)`, con una manopola sola
(`r`) che porta dall'ordine — un valore, poi cicli di 2, 4, 8 valori — al
disordine. La logistica a `r = 3.5` percorre quattro valori (0.827, 0.501,
0.875, 0.383); a `r = 3.9` non si ripete più.

Il puntatore di prima, del resto, era già una mappa, lineare:
`p[n+1] = p[n] + speed·IOT[n] (mod L)`.

## Modello

### Cosa fa una mappa

Uno stream dichiara le sue mappe in `maps:`. Una mappa **sa solo fare «un altro
passo»**: ha uno stato (`x`, o la coppia `x, y`), una regola e un parametro
`r`. Non sa niente dei grani. Il catalogo (`src/pge/maps/catalog.py`) ne ha sei
— `logistic`, `tent`, `sine`, `cubic`, `henon`, `circle` — e `type: custom`
lascia scrivere l'equazione nello YAML.

Un parametro la legge con un'**espressione**, valutata a ogni grano:

```yaml
maps:
  m1: {type: logistic, r: 3.5}
grain:
  iot: (0.020 + 0.180*m1)
  duration: (0.020 + 0.080*m1)
pointer:
  position: (m1)
```

L'espressione è il **terzo tipo di valore** di un parametro, accanto al numero
e all'envelope. Non è una curva: il suo valore dipende dallo stato della
mappa, che non è una funzione del tempo.

### I tre modi di avanzare

Quando una mappa fa il suo passo lo dice lo YAML, non la mappa.

| scrittura | quando fa un passo | stato |
|---|---|---|
| `clock: grain` (default) | ogni volta che nasce un grano | uno **per voce** |
| `clock: 8`, o un envelope | a orologio: il passo k cade dove l'integrale del clock vale k; il valore resta fermo fino al passo dopo | nessuno: è una funzione del tempo |
| `iterate: 7` | mai: a ogni lettura si riparte da `x0` e si fanno 7 passi con l'`r` di quell'istante | nessuno |

- **`clock: grain` è contato sui grani, non sul tempo.** A densità doppia la
  stessa sequenza scorre in metà tempo. Con `grain.iot` sulla stessa mappa è
  un anello chiuso: la mappa decide quanto aspettare, e l'attesa decide quando
  la mappa farà il passo successivo.
- **A orologio** la mappa è una funzione del tempo: tutte le voci leggono lo
  stesso valore allo stesso istante, e i grani nati dentro lo stesso passo
  leggono lo stesso numero.
- **`iterate`** è il modo dell'articolo di Di Scipio (DAFx99): il valore è
  l'n-esima iterata della stessa funzione, e a disegnare la curva è il
  movimento di `r`. Con `r` fermo il valore è fermo. `n` è la manopola della
  ruvidezza.

### Minimo e massimo sono la forma dell'espressione

Non ci sono chiavi `min` e `max`: `minimo + (massimo − minimo) * m1`. Il
minimo è il valore del parametro quando la mappa è in fondo al suo intervallo,
il massimo quando è in cima. Tre conseguenze, misurate:

- **la mappa non usa tutta la fascia scritta**: logistica a `r = 3.8`, scritto
  20–200 ms, usato 53–191; a `r = 3.2` due soli valori, 112 e 164 ms;
- **l'espressione dipende dall'intervallo della mappa**: la stessa fascia
  20–200 ms è `(0.020 + 0.180*m1)` sulla logistica, che vive in 0…1, e
  `(0.110 + 0.090*m1)` sul seno di Di Scipio, che vive in −1…1. Per questo
  l'intervallo di ogni tipo è un **dato** del catalogo (`value_range`), non
  solo prosa;
- **un valore che esce si riporta dentro scrivendolo**: `clip` appiattisce,
  `fold` riflette, `wrap` riparte dall'altro capo. Senza, valgono i limiti del
  parametro (taglio, con una riga sul clip log) e, per `pointer.position`, il
  rientro a capo della finestra.

### La densità che emerge

`grain.iot` è l'attesa fino al grano successivo: `onset[n+1] = onset[n] + iot`.
È il terzo modo di dire quando nasce un grano, e con lui `density` e
`fill_factor` non si scrivono: **la densità non si decide, emerge**, e si
legge a cose fatte. Con `r = 3.5` le attese percorrono 169, 110, 177, 89 ms:
7.3 grani al secondo in media, fra 5.6 e 11.2.

### La posizione dichiarata

`pointer.position` è la seconda legge di moto del puntatore: la posizione
scritta, da 0 a 1 **della finestra attiva** (la finestra di loop se c'è,
altrimenti il file). Prende il posto di `start` e `speed_ratio`. La finestra
resta, anche mobile, ed è il **vincolo**: la mappa muove la posizione dentro
la finestra, non la finestra.

### Vedere

Un parametro scritto come espressione non ha una curva nota in anticipo. La
partitura e la sessione Sonic Visualiser ne mostrano i **valori realizzati**:
il valore che il parametro ha dato a ogni grano della voce 0, a gradini, con
la sua escursione vera in legenda. Accanto, il valore di ogni mappa
(`map__m1`: a gradini per i modi a clock, continua per `iterate`) e la densità
emersa.

## Trade-off

**Un'espressione, non una chiave per mappa.** L'alternativa era dare a ogni
parametro una chiave `map:` con `min`/`max`. L'espressione costa un interprete
(senza `eval`: un parser a discesa ricorsiva, `src/pge/expressions/`), ma
compone: due mappe nello stesso parametro, `m1.y`, `t`, `fold`. E minimo e
massimo non diventano chiavi che in tre casi su quattro andrebbero spiegate.

**Si valuta a ogni grano, quindi non si valida al caricamento.** Un envelope
fuori dai limiti è un errore al parse; di un'espressione al parse si sa solo
che è scritta bene. I valori si tagliano grano per grano. Il prezzo è un clip
log che potrebbe scrivere una riga per grano: ha un limite di frequenza (una
riga ogni 5 s di stream, col conto dei tagli taciuti). Un `nan` va al limite
inferiore del parametro — tranne su `grain.iot`, dove un campione di attesa
sono 48000 grani al secondo, e va al tetto.

**Lo stato per voce.** Con più voci e `scatter` i cursori divergono e le
chiamate arrivano fuori ordine (misurato con 3 voci e `scatter: 1`: il 52%
torna indietro nel tempo). Uno stato condiviso verrebbe iterato in ordine
mescolato. La mappa avanza **una volta per grano e per voce, in un punto
solo** — in testa al giro della voce — e chi la legge non la muove: l'ordine
in cui i parametri la leggono non conta. Il prezzo: le voci partono tutte da
`x0` e percorrono la stessa sequenza, e con `grain.iot` `scatter` non sposta
niente (la formula è una media fra due attese uguali). Dare alle voci stati
iniziali diversi resta fuori.

**`x0` non dipende dal seed.** Una mappa è deterministica, ed è il suo punto:
lo stesso YAML dà la stessa sequenza con qualunque seed. Il transitorio (300
passi scartati) fa sì che il primo grano sia già sull'attrattore.

**La riproducibilità fra macchine non è totale.** Le mappe fatte di somme e
prodotti sono identiche bit per bit ovunque. `sine` e `circle` passano da
`sin`: una differenza di 10⁻¹² diventa di ordine 1 in una cinquantina di
passi, e fra due piattaforme i grani possono divergere.

**I valori realizzati sono della voce 0.** Un punto per ogni grano di ogni
voce sarebbe più onesto — fra due grani il valore non esiste — ma vorrebbe una
primitiva di disegno nuova e un tipo di layer nuovo in Sonic Visualiser. La
curva a gradini passa dalla corsia degli envelope com'è, e segue la
convenzione che la densità effettiva aveva già.

**Fuori da questo lavoro**: la mappa come sorgente al posto del generatore
casuale dentro le bande `_range`; la durata derivata da `grain.iot` e
`fill_factor`; mappe condivise fra stream; voci come mappe accoppiate; flussi
continui (Lorenz, Rössler); la lettura *dentro* il grano.

## Implicazioni codice

| cosa | dove |
|---|---|
| il catalogo dei tipi: passo, `x0`, `r_range`, `value_range` | `src/pge/maps/catalog.py` (`MAP_TYPES`, `MAP_KINDS`) |
| il blocco `maps:`, lo stato, chi muove e chi legge | `src/pge/maps/map_set.py` (`MapSet`) |
| l'interprete, e l'espressione come valore | `src/pge/expressions/expression.py` |
| dove un'espressione vale, e dove no | `src/pge/expressions/fields.py` (`EXPRESSION_FIELDS`, `EXPRESSION_REFUSALS`) |
| il terzo tipo di valore: compilazione, valutazione, taglio | `GranularParser._parse_input`, `resolve_param`, `Parameter._clamp` |
| il passo della mappa, in testa al giro della voce | `Stream.generate_grains` → `MapSet.advance` |
| `grain.iot` | `DensityController.calculate_inter_onset` |
| `pointer.position` | `PointerController.calculate` → `_active_window` |
| il riparo dalla valutazione al caricamento | `src/pge/engine/expression_shelter.py` |
| i valori realizzati e le curve delle mappe | `Stream.realized_curve`, `Stream.map_curves`, `RealizedCurve` |
| il caso «espressione» per chi legge le curve | `ParameterCurve.classify` (`EXPRESSION`) |

Quattro invarianti che il codice tiene, e i test con loro:

- **Uno stream che non scrive le chiavi nuove dà gli stessi grani e lo stesso
  fingerprint di prima**, bit per bit: `tests/core/test_stream_senza_mappe_invariato.py`
  e `test_stream_puntatore_invariato.py`, su istantanee prese prima del
  codice.
- **Una chiusura compilata non solleva mai**: fuori dominio dà un numero non
  finito, e a tagliarlo è il parametro. Gli errori sono tutti al parse.
- **Leggere una mappa non la muove**, e leggere le curve non cambia i grani.
- **Il riconoscimento dell'espressione sta in `ParameterCurve`**: chi legge le
  curve chiede `kind`, non il tipo del valore.

I tre backend (Csound, NumPy, SuperCollider) leggono solo `Grain`: tutto
questo sta a monte del grano e non li tocca. Il fingerprint della cache hasha
il dict grezzo dello stream: `maps:` e il testo delle espressioni ci entrano
da soli.

## Vedi anche

- [[yaml]] — `maps:`, le espressioni, `grain.iot`, `pointer.position`
- [[add-map]] — aggiungere un tipo di mappa al catalogo
- [[parameter-curve]] — il caso `expression` e le curve lette a cose fatte
- [[errors]] — `ExpressionError`, `MapConfigError`
- Origine: `docs/plans/done/2026-11-10-001-feat-mappe-caotiche-plan.md`
- A. Di Scipio, «Synthesis of Environmental Sound Textures by Iterated
  Nonlinear Functions», DAFx99: il modo `iterate` e la mappa `sin(r*x)`
