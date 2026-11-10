---
title: "feat(yaml): mappe caotiche — onset, durata e posizione dei grani letti da una mappa"
type: feat
status: active
date: 2026-11-10
issue: 307
---

# feat(yaml): mappe caotiche

## Overview

Lo stream può dichiarare una **mappa iterata** (logistica e altre) e far leggere
i parametri del grano da quella, attraverso un'**espressione**. La mappa prende
il posto di tre cose che oggi sono una retta più rumore bianco: l'attesa fra due
grani, la durata del grano, la posizione di lettura nel buffer.

Il modello è stato provato prima di scriverlo qui, in quattro pagine
interattive (vedi *Riferimenti*): l'ultima, «Banco del chirp», è un granulatore
di prova con lo stesso YAML di questo plan. Quando un punto di questo documento
sembra ambiguo, il banco è la lettura di riferimento.

Nessun breaking change: tutte le chiavi sono nuove, uno stream che non le
scrive produce gli stessi grani di prima e `VARIATION_SEMANTICS_VERSION` non si
muove.

---

## Problem Frame

Misurato sul motore, con uno stream vero (sample di 4 s, `density: 20`):

| cosa | oggi | misura |
|---|---|---|
| posizione di lettura | `start + integrale di speed_ratio`, cioè un fasore | con `distribution` a 0 e a 1 ogni grano cade sulla retta `p = speed·t`: scarto 0 |
| deviazione per-grano (`offset_range`) | rumore bianco attorno alla retta | autocorrelazione fra deviazioni successive −0.04 |
| attesa fra due grani | `avg·[(1−d) + d·U(0,2)]` | autocorrelazione fra attese successive +0.016 |

Fra un grano e il successivo non c'è memoria. Una mappa è esattamente quello:
una regola che calcola il prossimo valore dal precedente, con una manopola
(`r`) che va dall'ordine (un valore, poi cicli di 2, 4, 8, 3 valori) al
disordine.

La forma iterata del puntatore di oggi è già una mappa, lineare:
`p[n+1] = p[n] + speed·IOT[n] (mod L)`, con passo
`Ω = speed / (density·L)` (misurato 0.025 con speed 1, density 20, loop 2 s).

---

## Design

### La superficie

```yaml
- stream_id: s1
  sample: x.wav
  maps:
    m1:
      type: logistic        # logistic | tent | sine | cubic | henon | circle | custom
      r: 3.8                # numero o envelope
      clock: grain          # grain | passi al secondo (numero o envelope)
      # iterate: 7          # in alternativa a clock: modo alla Di Scipio
      # x0: 0.1
  grain:
    iot: (0.020 + 0.180*m1)        # al posto di density, fill_factor e distribution
    duration: (0.020 + 0.080*m1)
  pointer:
    position: (m1)                  # al posto di speed_ratio e start
```

I nomi (`maps`, `clock`, `iterate`, `position`, `iot`) sono quelli delle pagine
di prova. `iot` e la sua posizione dentro `grain:` sono una scelta esplicita;
gli altri sono provvisori e si fissano nella issue che li introduce.

`maps:` sta **dentro lo stream** e non in testa al documento: con `file:` la
testa del file importato viene ignorata (`engine/stream_files.py`), e accanto a
`file:` il master ammette solo le chiavi di piazzamento. Dentro lo stream la
mappa viaggia col file.

### Le mappe

| `type` | passo | `r` | intervallo di `m1` | `x0` |
|---|---|---|---|---|
| `logistic` | `r*x*(1-x)` | 2.5 – 4 | 0 … 1 | 0.3 |
| `tent` | `r/2*min(x, 1-x)` | 2.5 – 3.999 | 0 … 1 | 0.3 |
| `sine` (Di Scipio 1999) | `sin(r*x)` | 0 – 4 | −1 … 1 | 0.1 |
| `cubic` | `r*x*(1-x*x)` | 1.5 – 3 | −1.2 … 1.2 | 0.3 |
| `henon` | `x: 1 - r*x*x + y`, `y: 0.3*x` | 0.8 – 1.4 | −1.3 … 1.4 | 0.1, 0.1 |
| `circle` | `frac(x + r - 0.3*sin(2*pi*x))` | 0 – 1 | 0 … 1 | 0.2 |
| `custom` | `x:` (e `y:`) scritte nello YAML | libero | — | `x0` |

- L'**intervallo di `m1`** è un fatto della mappa, e chi scrive un'espressione
  deve conoscerlo: la stessa fascia 20–200 ms è `(0.020 + 0.180*m1)` sulla
  logistica e `(0.110 + 0.090*m1)` sul seno di Di Scipio. Va documentato per
  ogni tipo e, se serve a un editor, esposto come dato leggibile.
- Le mappe a due variabili espongono la seconda come `m1.y`.
- `type: custom` usa le equazioni `x:` (obbligatoria) e `y:` (opzionale),
  scritte nello stesso linguaggio delle espressioni, con le variabili `x`, `y`,
  `r`. Un `type` di catalogo con accanto un `x:` è un errore: non si capirebbe
  quale delle due vale.
- La `tent` a `r = 4` esatto (pendenza 2) in float64 collassa a zero in una
  cinquantina di passi (misurato: 50). Il tetto del suo `r` sta sotto 4 per
  questo.

### Come avanza una mappa

Una mappa sa solo fare «un altro passo». Lo YAML dice quando.

| scrittura | quando fa un passo | stato |
|---|---|---|
| `clock: grain` (default) | ogni volta che nasce un grano | uno **per voce** |
| `clock: 8` | 8 passi al secondo, a intervalli fissi; il valore resta fino al passo dopo | uno per stream: è una funzione del tempo |
| `clock: [[0, 2], [12, 20]]` | il passo k cade quando l'integrale del clock vale k | come sopra |
| `iterate: 7` (+ `x0`) | mai: a ogni lettura si riparte da `x0` e si fanno 7 passi con l'`r` di quell'istante | nessuno |

- **`clock: grain` è contato sui grani, non sul tempo.** A densità doppia la
  stessa sequenza scorre in metà tempo. Con `grain.iot` sulla stessa mappa è un
  anello chiuso: la mappa decide quanto aspettare, e l'attesa decide quando la
  mappa farà il passo successivo.
- **Stato per voce.** Con più voci e `scatter` i cursori divergono e le
  chiamate arrivano fuori ordine: misurato con 3 voci e `scatter: 1`, il 52%
  delle chiamate a `PointerController.calculate` ha il tempo che torna
  indietro. Uno stato condiviso verrebbe iterato in ordine mescolato. La mappa
  avanza quindi **una volta per grano e per voce**, in un punto solo (in testa
  al giro della voce in `Stream.generate_grains`), e chi la legge non la muove:
  l'ordine in cui i parametri la leggono non conta.
- **Clock a envelope.** Il conto dei passi fino a `t` è
  `floor(integrale del clock da 0 a t)`: `Envelope.integrate` c'è già, ed è il
  meccanismo con cui il puntatore integra `speed_ratio`. Da 2 a 20 passi/s
  lineari in 12 s fanno 132 passi.
- **`r` a envelope** si legge all'istante del passo (o della lettura, in
  `iterate`). Segue il `time_mode` dello stream come ogni altro envelope.
- **`iterate`** è il modo d'uso dell'articolo di Di Scipio (DAFx99): il valore è
  l'n-esima iterata della stessa funzione, e a disegnare la curva è il
  movimento di `r` (e, volendo, di `x0`). Con `r` fermo il valore è fermo.
  `n` è la manopola della ruvidezza: misurato a 20 grani/s con `sin(r*x)` e `r`
  da 3 a 4 in 60 s, le inversioni di direzione su 1200 grani sono 0 (n = 3),
  29 (n = 7), 168 (n = 9), 630 (n = 12).
- `clock` e `iterate` insieme sono un errore.

### Le espressioni

Un parametro che legge una mappa si scrive come un'espressione fra parentesi,
dove oggi stanno un numero o un envelope.

- **Linguaggio.** `+ - * / **`, parentesi, numeri; funzioni `sin cos tan abs
  sqrt exp log floor round sign min max pow frac clip fold wrap`; costanti
  `pi`, `e`; nomi: le mappe dichiarate (`m1`), la loro seconda variabile
  (`m1.y`), `t` (secondi dall'inizio dello stream). Dentro le equazioni di una
  mappa `custom` i nomi sono `x`, `y`, `r`. Precedenze come in Python
  (`-x**2` è `-(x**2)`, `**` associa a destra).
- **Niente `eval`.** L'interprete è un parser a discesa ricorsiva che compila
  in chiusure; il banco ne ha una versione di riferimento in JavaScript, da
  portare. Un nome sconosciuto, una parentesi mancante o un numero sbagliato
  di argomenti sono errori al parse, nella gerarchia `EngineError`, col path
  YAML del campo e lo stream.
- **Si valuta a ogni grano**, non al caricamento. Oggi
  `Generator._eval_math_expressions` valuta al caricamento ogni `( … )` in una
  costante, con una regex e `eval`. Un'espressione che nomina una mappa
  dichiarata nello stesso stream va lasciata com'è e compilata dal parser dei
  parametri. Oggi verrebbe lasciata com'è lo stesso, ma dopo aver stampato su
  stdout `⚠️ Warning: impossibile valutare…`: quella riga non deve uscire
  (stdout è un contratto, e PGE-ui lo legge).
- **Dove entra.** `GranularParser._parse_input` oggi distingue numero ed
  envelope e rifiuta una stringa: l'espressione è il terzo caso. Il valore di
  un `Parameter` diventa numero, `Envelope` o espressione, e
  `resolve_param` lo valuta. Clamp ai bounds e riga di clip log
  (`Parameter._clamp`) restano com'erano e sono l'unica validazione dei valori:
  un envelope fuori bounds è un errore al parse, un'espressione no.
- **`_range` sopra un'espressione** resta lecito: è un tremolio casuale attorno
  al valore dato dalla mappa. La mappa **non** sostituisce il generatore
  casuale dentro la banda.
- **Unità.** `grain.duration_unit` oggi riscala i valori grezzi prima del
  parser (`Stream._pre_normalize_grain_params`); una stringa non si riscala.
  Per un'espressione il fattore si applica al **risultato**.

### Minimo e massimo

Non sono chiavi: sono la forma dell'espressione.

`minimo + (massimo − minimo) * m1` — il minimo è il valore del parametro quando
la mappa è in fondo al suo intervallo, il massimo quando è in cima. Tre fatti,
misurati sul banco con `(0.020 + 0.180*m1)`:

- la mappa non usa tutta la fascia scritta: logistica a `r = 3.8`, scritto
  20–200 ms, usato 53–191; a `r = 3.2` due soli valori, 112 e 164 ms;
- l'espressione dipende dall'intervallo della mappa (vedi la tabella);
- un valore che esce si riporta dentro scrivendolo: `clip(v, lo, hi)`
  appiattisce, `fold(v, lo, hi)` riflette, `wrap(v, lo, hi)` riparte dall'altro
  capo. Senza, valgono i limiti del parametro (clamp) e, per la posizione, il
  rientro a capo della finestra.

### `grain.iot` — gli onset e la densità che emerge

`onset[n+1] = onset[n] + iot`. È il cursore per voce che c'è già
(`voice_cursors[voice_index] += iot` in `Stream.generate_grains`), con l'attesa
presa dall'espressione invece che da `1/density`.

- Con `grain.iot` scritta, `density`, `fill_factor` e `distribution` non si
  scrivono: la densità **emerge**. Scritte insieme sono un **errore**, non una
  priorità (stessa regola di `reverse` / `read_direction`: dicono cose
  diverse). Attenzione al default: oggi senza chiavi vince `fill_factor: 2`
  (`ExclusiveGroupSelector`), quindi il modo nuovo si sceglie per **presenza**
  della chiave.
- Sta dentro `grain:` e segue `grain.duration_unit`, come `grain.duration`.
- Il ciclo deve avanzare: un'attesa nulla, negativa o non finita è un render
  che non finisce. Servono bounds propri (proposta: da un campione a 100 s,
  l'inverso del pavimento di `density`), col clamp che scrive sul clip log.
- La soglia `DENSITY_NOTICE_THRESHOLD` deve continuare a parlare (attesa sotto
  0.25 ms).
- La densità emersa va **mostrata**: una curva pubblicata come oggi
  `effective_density_curve` in modalità `fill_factor`.
- `fill_factor` è già una connessione fra parametri: in quella modalità
  `durata / IOT` vale 2.0000 su ogni grano (misurato). Con `grain.iot` e
  `fill_factor` insieme si potrebbe derivare la **durata** (`fill × iot`):
  combinazione oggi non scrivibile. È fuori da questo plan (vedi *Fuori scope*).

### `pointer.position`

La legge di moto del puntatore oggi è una funzione sola
(`_calculate_linear_position`); il resto di `PointerController.calculate` è
confinamento: finestra di loop, wrap, offset di voce, reverse.

- `pointer.position` è la posizione **nella finestra attiva**, da 0 a 1: la
  finestra di loop se c'è, altrimenti il file intero. Il confinamento resta
  quello di oggi (wrap modulare).
- Prende il posto di `speed_ratio` e `start`: scritte insieme sono un errore.
- `offset_range` e gli offset di pointer delle voci si sommano come oggi.
- La finestra di loop resta, anche mobile: è il **vincolo** del puntatore.
- Il reverse `auto` oggi segue il segno di `speed_ratio` dichiarato
  (`Stream._calculate_grain_reverse`): con `position` non c'è una velocità
  dichiarata. Proposta: `auto` vale «avanti», e il verso si dichiara con
  `grain.read_direction`. Da decidere nella sua issue.

### Stato iniziale, transitorio, mappa che scappa

- **`x0`.** Default del tipo (tabella), sovrascrivibile. Non dipende dal seed:
  una mappa è deterministica, ed è il suo punto. (Decisione da confermare:
  l'alternativa è derivarlo da `(seed, rng_id, nome)` come gli RNG.)
- **Transitorio.** Nei modi a clock il banco scarta 300 passi a `r(0)` prima
  di cominciare, così il primo grano è già sull'attrattore. Va tenuto come
  default e reso esplicito con una chiave (nome da decidere).
- **Mappa che scappa.** Un valore non finito o oltre 10³ in modulo: la mappa
  riparte da `x0` e lo si scrive sul clip log, con rate limit. In `iterate`,
  dopo la fuga non si itera oltre.
- **Riproducibilità fra macchine.** Una differenza di 10⁻¹² diventa di ordine 1
  in una cinquantina di passi (misurato sulla logistica a `r = 3.9`). Le mappe
  con sole somme e prodotti (`logistic`, `tent`, `cubic`, `henon`) sono
  identiche bit per bit ovunque. Quelle con `sin` (`sine`, `circle`) dipendono
  dall'ultimo bit della libreria matematica: fra macOS e Linux i grani possono
  divergere. Va detto in reference, e i test di quelle due non confrontano
  grani fra piattaforme.

---

## Punti di innesto nel codice

| cosa | dove |
|---|---|
| terzo tipo di valore | `GranularParser._parse_input` (`parameters/parser.py`) |
| valutazione | `resolve_param`, `Parameter.get_value`, `Parameter._clamp` (`parameters/parameter.py`) |
| espressioni al caricamento | `Generator._eval_math_expressions` (`engine/generator.py`): regex `\(([a-zA-Z0-9+\-*/.() ]+)\)`, `eval`, avviso su stdout. PGE-ls ne specchia la regex carattere per carattere (`tests/test_downstream_surface_pge_ls.py`) |
| giro dei grani, cursori per voce | `Stream.generate_grains` (`core/stream.py`); la durata del grano si legge **prima** di `_create_grain`, quindi il passo della mappa va fatto prima di quella lettura |
| attesa fra grani | `DensityController.calculate_inter_onset`, `_apply_truax_distribution`; gruppo esclusivo `density_mode` in `DENSITY_PARAMETER_SCHEMA` |
| legge di moto del puntatore | `PointerController._calculate_linear_position`; confinamento in `calculate` |
| reverse `auto` | `Stream._calculate_grain_reverse` |
| unità della durata | `Stream._pre_normalize_grain_params`, `GRAIN_DURATION_UNITS` (PGE-ls li legge dall'AST) |
| curve per partitura ed export | `ParameterCurve.classify` (`parameters/parameter_curve.py`), `rendering/envelope_extractor.py`, `Stream.effective_density_curve` |
| chi distingue `Envelope` per tipo | 14 punti in 9 file: parser (3), parameter (3), pointer_controller (2), score_writer, parameter_curve, gate_factory, envelope, voices_controller, voice_manager |
| cache | `StreamCacheManager._payload` hasha il dict grezzo dello stream: le chiavi nuove entrano da sole |

I tre backend (Csound, NumPy, SuperCollider) leggono solo `Grain`: tutto questo
lavoro sta a monte del grano e non li tocca.

---

## Numeri di riferimento per i test

- Logistica: `r = 2.8` un valore (0.643); `r = 3.2` due (0.513, 0.799);
  `r = 3.5` quattro (0.827, 0.501, 0.875, 0.383); `r = 3.83` tre.
- `r = 3.5`, `clock: grain`, `duration: (0.02 + 0.08*m1)`: durate 86, 60, 90,
  51 ms in ciclo.
- `r = 3.5`, `clock: grain`, `iot: (0.02 + 0.18*m1)`: attese 169, 110, 177,
  89 ms in ciclo (546 ms per quattro grani), densità media 7.3 grani/s, fra 5.6
  e 11.2.
- Clock da 2 a 20 passi/s lineare su 12 s: 132 passi.
- Con transitorio diverso cambia la **fase** del ciclo, non l'insieme dei
  valori: i test confrontano il ciclo a meno di rotazione, oppure fissano il
  transitorio.
- Interprete: `-m1**2` con `m1 = 0.5` dà −0.25; `2**3**2` dà 512;
  `fold(1.3, 0, 1)` dà 0.7; `wrap(-0.25, 0, 1)` dà 0.75.

---

## Steps

Una issue per fetta verticale, sotto la #307. «Decisione» vuol dire che la
issue elenca scelte da prendere prima di scrivere codice; le altre si possono
eseguire di seguito.

| | issue | cosa | bloccata da | |
|---|---|---|---|---|
| 1/7 | #308 | la fetta di prova: `maps:` con la logistica e un'espressione su `grain.duration` (`clock: grain`, `r` scalare). Fissa l'architettura: l'interprete, il terzo tipo di valore, lo stato per voce, gli errori | — | decisione |
| 2/7 | #310 | come avanza la mappa: `r` a envelope, clock a orologio, modo alla Di Scipio (`iterate`, `x0`) | #308 | |
| 3/7 | #311 | `grain.iot`: gli onset dalla mappa e la densità che emerge | #308 | decisione |
| 4/7 | #312 | `pointer.position`: la posizione di lettura dalla mappa | #308 | decisione |
| 5/7 | #313 | le altre mappe (`tent`, `sine`, `cubic`, `henon`, `circle`), l'equazione modificabile (`custom`), le espressioni sugli altri parametri e i rifiuti dove non valgono | #308 | |
| 6/7 | #314 | la partitura e gli export mostrano le mappe; explanation e how-to | #311, #312, #313 | |
| 7/7 | #309 | le espressioni di oggi: le funzioni a due argomenti non si valutano (la virgola non è nella regex) e un'espressione deve stare tutta dentro le parentesi esterne | — | decisione |

---

## Copertura test richiesta

- L'interprete, da solo: precedenze, funzioni, nomi, ogni errore col suo
  messaggio.
- Ogni tipo di mappa: i cicli noti (tabella sopra) e l'intervallo dichiarato.
- I tre modi di avanzare, con una e con più voci; con `scatter`.
- Ogni chiave nuova: presente, assente, malformata; i gruppi esclusivi.
- Uno stream senza `maps:` dà gli stessi grani di prima (fingerprint e grani).
- Il fingerprint della cache cambia al cambiare di `maps:` o di un'espressione.
- Nessuna riga nuova su stdout al caricamento di un'espressione valida.
- La partitura e gli export non si rompono su un parametro a espressione.

---

## Fuori scope

- La mappa come sorgente al posto del generatore casuale dentro le bande
  `_range` (scartata).
- La durata derivata da `grain.iot` e `fill_factor`.
- Mappe condivise fra stream diversi (l'analogo di `rng_group`).
- Voci come mappe accoppiate; il buffer come non linearità; flussi continui
  (Lorenz, Rössler).
- La lettura **dentro** il grano: oggi è lineare a pitch costante
  (`rendering/grain_renderer.py`) e toccarla vuol dire cambiare `Grain` e i tre
  backend.

---

## Impatto cross-repo

Ogni issue che cambia la superficie apre le sue, una per repo, quando viene
implementata (`.claude/rules/cross-repo-impact.md`). In sintesi:

- **PGE-ls**: completamento, hover e diagnostica di `maps:`, `grain.iot`,
  `pointer.position`; un valore-stringa dove oggi si aspetta numero o envelope;
  la regex di `_eval_math_expressions`, che specchia carattere per carattere.
- **PGE-ui**: un terzo tipo di valore accanto a scalare ed envelope (oggi due
  campi paralleli per parametro); i pallini di staleness seguono già il
  fingerprint.
- **gl-ls**: `grain` e `pointer` hanno vocabolario chiuso: `iot` e `position`
  sono subito un falso rosso su YAML valido.
- **I laboratori** (mare-nostrum, granulation-studies) conservano le chiavi che
  non conoscono, ma leggono i valori come numeri o envelope.

---

## Riferimenti

- Pagine di prova (private): [Mappa logistica e grani](https://claude.ai/artifact/N8SKBGvS2ftqRmzbHW6RMk),
  [Onset dalla mappa](https://claude.ai/artifact/XAuWGWr3Ski9dW3tLF9N32),
  [Clock e r nel tempo](https://claude.ai/artifact/8qRF82k5Ze7SKxNydbDnwS),
  [Banco del chirp](https://claude.ai/artifact/HCRgdxeuruWANe2vsNwNQV).
- A. Di Scipio, «Synthesis of Environmental Sound Textures by Iterated
  Nonlinear Functions», DAFx99: il modo `iterate` e la mappa `sin(r*x)`.
- J. Pressing, «Nonlinear Maps as Generators of Musical Design», *Computer
  Music Journal* 12(2), 1988; B. Truax, «Chaotic Non-Linear Systems and Digital
  Synthesis: An Exploratory Study», ICMC 1990; A. Di Scipio, «Composition by
  Exploration of Non-Linear Dynamic Systems», ICMC 1990. Di questi tre sono
  state lette solo fonti secondarie.
