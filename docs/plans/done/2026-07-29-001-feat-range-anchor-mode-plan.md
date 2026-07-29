---
title: "feat: range_anchor — interruttore fra range centrato (base ± range/2) e range ancorato al minimo (base → base + range)"
type: feat
status: done
date: 2026-07-29
issue: null
---

# feat: `range_anchor` — range centrato vs range ancorato al minimo

## Overview

PGE e `granulation-studies` usano la stessa parola — `range` — per due cose
diverse:

| | banda risultante | `base` è |
|---|---|---|
| **PGE** (`UniformDistribution.sample`) | `[base - range/2, base + range/2]` | il **centro** |
| **granulation-studies** (`value_generators._band_at`) | `[base, base + range]` | il **minimo** |

Chi scrive uno `study.yml` incontra le due semantiche a poche righe di
distanza, perché granstudies risolve le proprie bande in breakpoint espliciti
prima di emettere, ma il blocco `base:` passa **intatto** all'engine:

```yaml
axes:
  grain.duration: {base: 300, range: 200}   # granstudies: [300, 500] ms
base:
  grain:
    duration_range: 200                      # PGE, su base 300: [200, 400] ms
```

Obiettivo: un interruttore che faccia funzionare i range di PGE come in
granstudies — `base` è il minimo, `range` è la forbice di apertura verso
l'alto — lasciando il comportamento storico come default.

Questo documento è **solo il piano**: nessuna riga di produzione è stata
scritta. La domanda a cui risponde è *dove* va inserito l'interruttore.

---

## Stato attuale (analisi d'impatto)

### 1. Dove vive davvero il `± range/2`

Non nel parametro né nella variazione, ma nelle **distribuzioni**
(`shared/distribution_strategy.py`):

```python
# UniformDistribution.sample  (riga 94)
return center + self._rng.uniform(-0.5, 0.5) * spread

# UniformDistribution.get_bounds  (riga 100)
half_spread = spread / 2
return (center - half_spread, center + half_spread)

# GaussianDistribution.sample  (riga 133)
return self._rng.gauss(center, spread)
```

La catena completa di un range esplicito:

```
YAML  <param>_range
  → ParameterParser (parser.py:131, passa distribution_mode)
    → Parameter.__init__ (parameter.py:71-72)
        _distribution        = DistributionFactory.create(distribution_mode)
        _variation_strategy  = VariationFactory.create(bounds.variation_mode)
    → Parameter.get_value (parameter.py:94-115)
        base_val      = _evaluate_input(...)      # envelope o scalare
        current_range = _calculate_range(time)    # envelope o scalare
        final_val     = _variation_strategy.apply(base_val, current_range, _distribution)
        return _clamp(final_val, time)            # clamp ai bounds del parametro
```

`VariationStrategy` (`strategies/variation_strategy.py`) è un passacarte:

- `AdditiveVariation` → `distribution.sample(base, mod_range)`;
- `QuantizedVariation` → `base + round(distribution.sample(0.0, mod_range))`
  — nota che campiona **attorno a 0** e somma dopo: l'ancora qui è implicita
  in una formula diversa;
- `InvertVariation` / `ChoiceVariation` → non usano il range come banda.

### 2. La seconda divergenza, meno visibile: la gaussiana

L'ancora non è l'unica differenza. `range` significa due cose diverse anche
*dentro* la modalità gaussiana:

| | `range` è | coda |
|---|---|---|
| PGE (`GaussianDistribution.sample`) | **σ** (deviazione standard) | illimitata, richiusa solo dal clamp ai bounds del parametro |
| granstudies (`value_generators._draw:167-180`) | **larghezza piena** della banda, con `σ = (hi-lo)/6` | clampata ai bordi banda (i bordi cadono a 3σ) |

Un `range_anchor` che sistemasse solo il centro lascerebbe la gaussiana
divergente: con `range: 200` PGE oggi produce σ=200 (banda utile ~±600),
granstudies una banda larga 200 con σ≈33. **Va deciso esplicitamente** cosa fa
la gaussiana in modalità `min` — vedi Design, punto 4.

### 3. Cosa vuol dire "tutti i range": inventario

"Tutti i range di PGE" non è un solo percorso di codice. Oggi convivono
**quattro** convenzioni diverse:

| # | dove | formula | è un `_range` YAML? |
|---|---|---|---|
| 1 | `_range` via `Parameter` → distribuzione | `center ± spread/2` | **sì** — `volume_range`, `pan_range`, `grain.duration_range`, `offset_range` (`parameter_schema.py:69,76,87,134`), più il range di pitch via `pitch_unit` |
| 2 | `QuantizedVariation` (pitch in semitoni) | `base + round(sample(0, range))` | sì, stesso `_range` |
| 3 | detune implicito (`strategies/strategie.py:76`) | `uniform(-cents, +cents)` — ±**pieno**, non /2 | no: nasce da `implicit_detune_cents`, attivo solo *senza* range esplicito |
| 4 | spread per-voce (`voice_pan_strategy.py:185`, e i gemelli pointer/pitch) | `uniform(-1, 1) * spread / 2`, cached per voce | no: è `spread` di una strategy |

Fuori inventario ma citabile: l'`iot` async del `DensityController`
(`density_controller.py:129`) usa `uniform(0, 2*avg)` — già ancorato al minimo,
per ragioni sue.

**Proposta di scope:** l'interruttore governa **(1) e (2)**, cioè tutto ciò che
passa da `Parameter.get_value`. (3) e (4) restano invariati: non sono `_range`,
non hanno una `base` di cui essere il minimo, e piegarli alla stessa regola
cambierebbe il significato di `spread` delle voci senza che nessuno l'abbia
chiesto. Va detto nella doc, altrimenti "tutti i range" resta una promessa
ambigua.

---

## Revisione del piano — decisioni prese e correzioni

> Questa sezione è stata aggiunta in fase di implementazione. Tutto quello che
> segue sotto "Design proposto" è la **proposta originale**, conservata come
> archivio: due suoi punti si sono rivelati sbagliati e sono stati sostituiti.
> Quello che è stato implementato è descritto qui.

### Le due decisioni aperte, chiuse

**(a) La gaussiana in modalità `min`.** Deciso: **banda piena**, come
granulation-studies — μ = centro banda, σ = larghezza/6 (i bordi cadono a 3σ),
clamp ai bordi. Ma la decisione è andata oltre la modalità `min`: il vero
problema è che `range` significava larghezza con `uniform` e σ con `gaussian`,
e chi scrive `range: 200` si aspetta una banda larga 200 in entrambi i casi.
Quindi **la gaussiana legge `range` come larghezza in ogni modalità**, anche
in `center`, dove prima era σ.

È un **cambio di comportamento non retrocompatibile del default** per chi usa
`distribution_mode: gaussian`. È stato accettato consapevolmente dall'utente
dopo che il costo è stato messo sul tavolo (vedi "Il rischio della cache" qui
sotto), scavalcando il vincolo iniziale "default identico bit per bit" — che
resta valido e verificato per `uniform`.

**(b) Il nome.** Deciso: **`range_anchor: center | min`**, per-stream, default
`center`. L'obiezione al nome nel piano originale (§Rischi 5: "dice l'ancora
ma non che `range` apre verso l'alto") **decade** con la decisione (a): una
volta che `range` è la larghezza della banda in ogni distribuzione e in ogni
modalità, l'unica cosa che l'interruttore muove è dove cade `base` dentro la
banda. È letteralmente un'ancora. `range_anchor` si estende inoltre a un terzo
valore `max` senza rifare niente, cosa che `range_mode: centered | upward` non
farebbe (servirebbe `downward`, e il default `centered` non sarebbe una
direzione come gli altri due).

### Il modello finale: tre concetti ortogonali

| concetto | chiave | cosa decide |
|---|---|---|
| larghezza | il valore del `_range` | quanto è larga la banda |
| forma | `distribution_mode` | come la banda viene riempita |
| ancora | `range_anchor` | dove cade `base` dentro la banda |

Con `base: 300`, `range: 200`:

| forma | ancora | banda | picco |
|---|---|---|---|
| `uniform` | `center` | 200…400 | — (piatta) |
| `uniform` | `min` | 300…500 | — (piatta) |
| `gaussian` | `center` | 200…400 | 300 |
| `gaussian` | `min` | 300…500 | 400 |

### Correzione 1 — l'interruttore VA dentro le distribuzioni

Il §1 del design originale ("Perché NON toccare le distribuzioni") è
**sbagliato in tutti e tre i suoi argomenti**:

- *«`sample(center, spread)` è usato da `QuantizedVariation` con `center=0`,
  dove "minimo" non vuol dire niente»* — al contrario. `variation_strategy.py`
  fa `base + round(sample(0.0, mod_range))`: sotto ancora `min`, `sample(0, r)`
  pesca in `[0, r]` e la somma cade in `[base, base+r]`, che è esattamente il
  comportamento voluto, **gratis**. Il design originale doveva invece applicare
  l'offset una seconda volta dentro `QuantizedVariation`, duplicando la logica
  dentro quello che lui stesso chiama un passacarte.
- *«`get_bounds()` è documentazione/debug e va tenuto coerente»* — è un
  argomento **a favore**: `get_bounds` vive nelle distribuzioni, e con l'ancora
  lì dentro `sample` e `get_bounds` condividono una sola definizione della
  banda (`_band`), senza possibilità che divergano.
- *«tutti i test delle distribuzioni diventano rossi in blocco»* — falso.
  Con l'ancora come **stato dell'istanza** e default `center`, il ramo di
  default resta la stessa identica espressione. Verificato: gli unici rossi
  della suite sono stati i 10 test che asserivano la vecchia semantica σ della
  gaussiana, cioè esattamente ciò che la decisione (a) sostituisce.

### Correzione 2 — la funzione pura `resolve` non può funzionare

Il §3 proponeva una funzione pura `resolve(base, width, anchor) -> (center,
spread)` chiamata in `Parameter.get_value`. È **incompatibile con la
raccomandazione del §4 dello stesso documento**: una coppia `(center, spread)`
non può esprimere σ = larghezza/6 per la gaussiana e σ = larghezza per
l'uniforme senza sapere quale distribuzione sta alimentando (diventerebbe una
tabella di dispatch sul nome della distribuzione), e non può in nessun caso
esprimere il **clamp ai bordi**, che è un'operazione dopo il sample.

### Il design implementato

L'ancora è **stato dell'istanza della distribuzione**, legata alla
costruzione:

```python
DistributionStrategy.__init__(self, rng=None, anchor=ANCHOR_CENTER)
DistributionFactory.create(mode, rng=None, anchor=ANCHOR_CENTER)
```

Conseguenze:

- la firma `sample(center, spread)` **non cambia** — nessun rosso gratuito, e
  13 test che la chiamano a keyword (`sample(center=..., spread=...)`) restano
  intatti (il parametro `center` non poteva essere rinominato);
- `VariationStrategy` **non cambia**: resta il passacarte che è, e
  `QuantizedVariation` diventa corretto senza una riga di modifica;
- ogni distribuzione sa come la propria forma riempie una banda — il posto
  giusto per quella conoscenza in uno Strategy pattern;
- gli assi restano una **somma**, non un prodotto cartesiano: una nuova
  distribuzione non va scritta due volte, e una terza ancora (`max`) è un ramo
  per distribuzione, non un raddoppio del registro.

Il jitter implicito si risolve in una riga, in `Parameter.__init__`:

```python
effective_anchor = range_anchor if mod_range is not None else ANCHOR_CENTER
```

`has_explicit_range` è costante per tutta la vita del Parameter, quindi la
scelta si fa una volta invece che a ogni `get_value`.

### Il rischio della cache, e come è stato chiuso

Il §Rischi 3 del piano originale si preoccupava che `range_anchor` entrasse nel
fingerprint. **Ci entra per costruzione**: `compute_fingerprint` hashea il dict
YAML per-stream (`generator.stream_data_map`) escludendo solo `solo`/`mute`,
quindi qualsiasi chiave per-stream vi rientra. Una chiave **top-level** invece
non ci entrerebbe — è il buco che ha già `seed`. Questo, non la simmetria con
`distribution_mode`, è la ragione per cui la chiave è per-stream.

Il rischio vero era un altro, e il piano non lo vedeva: il fingerprint copriva
il **testo** YAML ma non la **semantica** con cui il motore lo interpreta. Col
cambio di significato della gaussiana a YAML invariato, ogni stem già
renderizzato sarebbe rimasto `clean` — audio vecchio, nessun errore. Risolto
con `VARIATION_SEMANTICS_VERSION` dentro l'hash: un re-render completo al primo
run dopo l'aggiornamento, poi la cache incrementale riparte.

### Punti che il piano lasciava "da verificare"

- **`score_visualizer`**: nessun impatto, verificato. Non disegna nessuna banda
  `base ± range/2`; `envelope_extractor` emette `<param>_range` come curva a sé
  con la larghezza grezza, e il visualizer la scala data-driven (issue #114).
  L'impatto grafico è su PGE-ui, dove `primitives.jsx:271` renderizza
  letteralmente `±{range/2}`.
- **Jitter implicito**: confermato, resta centrato in ogni modalità.

### Bounds: validazione al parse (Rischi §4)

Implementata, ma **solo per l'ancora `min`**: la banda arriva a `base + range`
e può sforare `max_val` dove la centrata non lo faceva. La modalità `min`
promette una banda esatta; se non è realizzabile lo si dice al parse invece di
prometterla e poi tagliarla col safety clamp. Solo il tetto (il pavimento è
`base`, già validato) e solo quando il massimo è **esatto**: scalare+scalare,
envelope+scalare, scalare+envelope. Con due envelope il massimo della somma non
è la somma dei massimi, e un falso positivo che blocca un render valido sarebbe
peggio del clamp. L'ancora `center` non guadagna nessuna validazione nuova.

### Scope: cosa l'interruttore NON governa

Confermato l'inventario del §3 originale. `range_anchor` governa (1) e (2) —
tutto ciò che passa da `Parameter.get_value`, cioè `volume_range`, `pan_range`,
`grain.duration_range`, `pointer.offset_range`, `pitch.range` e il pitch
quantizzato EDO. Restano **fuori e simmetrici**: il detune implicito del pitch
(±12 cents, `strategie.py`), lo spread per-voce delle voice strategy
(`spread`, `pitch_range`, `pointer_range`), l'`iot` async del
`DensityController` (già ancorato al minimo, per ragioni sue) e il jitter
implicito. Nessuno di questi è un `_range` dichiarato con una `base` di cui
essere il minimo.

### granulation-studies: nulla in questa PR

L'adozione della modalità è lavoro a parte e comporta **rileggere i valori
esistenti**: in `studies/stack_300-1000ms/study.yml` il `duration_range` arriva
a 350 su base 300, cioè oggi `[125, 475]` e con `range_anchor: min`
`[300, 650]`. I quattro study in ms vanno ripassati, e `stack_1-50smp` pure.

---

## Design proposto

### 1. Perché NON toccare le distribuzioni

La strada più corta — riscrivere `UniformDistribution.sample` — è la sbagliata:

- il contratto `sample(center, spread)` è usato anche da `QuantizedVariation`
  con `center=0`, dove "minimo" non vuol dire niente: la variazione diventerebbe
  silenziosamente monodirezionale sul pitch;
- `get_bounds()` è documentazione/debug e va tenuto coerente;
- **tutti i test delle distribuzioni** (`tests/shared/test_distribution_strategy.py`)
  fissano la formula attuale: cambiarla li rende rossi in blocco senza che il
  comportamento di default sia cambiato per l'utente.

### 2. Perché NON una nuova `distribution_mode`

Registrare `uniform_min` / `gaussian_min` via `DistributionFactory.register` è
tentante (il registry esiste già), ma confonde due assi ortogonali: la **forma**
della distribuzione e l'**ancora** del range. Ogni distribuzione futura
andrebbe scritta due volte, e gli enum di PGE-ls / PGE-ui crescerebbero come
prodotto cartesiano invece che come somma.

### 3. La proposta: `range_anchor`, asse separato in `StreamConfig`

Fratello di `distribution_mode`, che vive già lì
(`core/stream_config.py:78`, default `'uniform'`) e viaggia già fino a ogni
`Parameter` (`parser.py:50,131`):

```yaml
# per-stream, default 'center' → nessuno YAML esistente cambia
range_anchor: center | min
```

L'implementazione è **una funzione pura** che traduce `(base, range)` nella
coppia `(center, spread)` che le distribuzioni già sanno consumare, chiamata in
`Parameter.get_value` fra il calcolo del range e la delega alla
`VariationStrategy` (`parameter.py:99-112`):

```python
# center: identico a oggi, bit-per-bit
center, spread = base, rng_width

# min: la banda diventa [base, base + rng_width]
center, spread = base + rng_width / 2.0, rng_width
```

Proprietà che rendono questa la strada giusta:

- le distribuzioni **non cambiano**: contratto e test restano validi;
- `QuantizedVariation` continua a campionare attorno a 0 e a sommare — l'offset
  `+range/2` va applicato lì con la stessa funzione, così anche il pitch
  quantizzato diventa "da base in su" senza formule duplicate;
- il default `center` è un no-op dimostrabile: `base + 0/2 == base`;
- un solo punto da documentare, un solo punto da testare.

Collocazione del modulo: `pge/parameters/range_anchor.py` (accanto a chi lo usa)
oppure `pge/shared/` se si vuole riusarlo dalle strategy. Preferenza:
`parameters/`, finché lo scope resta (1)+(2).

### 4. La gaussiana in modalità `min` — decisione da prendere

Due opzioni, non equivalenti:

- **(a) allineare a granstudies**: `μ = base + range/2`, `σ = range/6`, **clamp
  ai bordi banda**. `range` diventa una larghezza in entrambe le modalità e la
  promessa "mai sotto `base`" è vera. Costo: in modalità `min` la gaussiana
  cambia significato rispetto a `center` (dove `range` è σ), quindi `range_anchor`
  non è più *solo* un'ancora.
- **(b) spostare solo il centro**: `μ = base + range/2`, `σ = range`, nessun
  clamp di banda. `range_anchor` resta ortogonale, ma "min" è una bugia: metà
  dei valori cade sotto `base`.

**Raccomandazione: (a)**, con il nome della modalità che lo dichiara. Se `min`
non garantisce il minimo non serve a niente, ed è esattamente la garanzia che
serve a granulation-studies. Va scritto in `docs/reference/yaml.md` che in
modalità `min` la gaussiana legge `range` come larghezza.

### 5. Superficie YAML

```yaml
streams:
  - stream_id: s1
    range_anchor: min        # NUOVA chiave per-stream: center (default) | min
    volume: -6
    volume_range: 12         # center: [-12, 0] · min: [-6, 6]
```

Non per-parametro. Un override tipo `volume_range_anchor` moltiplicherebbe la
superficie per il numero di parametri e non risolve nessun caso reale noto: gli
studi vogliono flippare il documento intero. Se servirà, si aggiunge dopo — il
contrario non è vero.

Da valutare: un default globale a livello di documento, come per altre config
di processo. Non necessario in v1.

---

## File coinvolti

| File | Modifica |
|---|---|
| `src/pge/parameters/range_anchor.py` | **nuovo**: enum/costanti + `resolve(base, width, anchor) -> (center, spread)` |
| `src/pge/core/stream_config.py` | campo `range_anchor: str = 'center'` in `StreamConfig` (riga ~78, accanto a `distribution_mode`) |
| `src/pge/parameters/parser.py` | legge `config.range_anchor` (come riga 50) e lo passa a `Parameter` (come riga 131) |
| `src/pge/parameters/parameter.py` | kwarg `range_anchor`; applica `resolve` in `get_value` fra riga 99 e 105 |
| `src/pge/strategies/variation_strategy.py` | `QuantizedVariation` riceve l'offset dell'ancora (o lo riceve già risolto, da decidere in TDD) |
| `src/pge/rendering/stream_cache_manager.py` | verificare che la chiave entri nel fingerprint (non è fra le escluse, riga 27) |
| `docs/reference/yaml.md` | nuova chiave, tabella delle bande, nota sulla gaussiana |
| `CHANGELOG.md` | voce sotto Unreleased/Aggiunto |

Da **verificare** in implementazione, non ancora accertati:

- `rendering/envelope_extractor.py:181-191` esporta la serie `<param>_range` con
  la larghezza grezza (`param._mod_range`). Chi la interpreta per disegnare la
  banda — `score_visualizer`, e l'editor envelope di PGE-ui — deve conoscere
  l'ancora, altrimenti la partitura grafica mente. Non ho trovato un disegno
  esplicito `base ± range/2` nel visualizer: va cercato prima di dichiarare
  l'impatto nullo.
- il **jitter implicito** (`ParameterBounds.default_jitter`, attivo quando
  `has_explicit_range` è falso): è un tremolio simmetrico attorno al valore, non
  una banda. **Proposta: resta sempre centrato**, anche con `range_anchor: min`.
  È la trappola più facile del piano.

---

## Test coinvolti

Nuovi:

- `tests/parameters/test_range_anchor.py` — la funzione pura: `center` è
  identità; `min` porta la banda a `[base, base+range]`; `range=0` è no-op in
  entrambe; range negativo → errore.
- `tests/parameters/test_parameter.py` — con RNG seedato: stesso seed e stesso
  `range`, `center` e `min` producono due valori il cui scarto è esattamente
  `range/2`; in `min` nessun campione cade sotto `base` su N draw (uniform e,
  se si sceglie (a), gaussian).
- gaussiana in `min`: i bordi a 3σ e il clamp di banda.
- pitch quantizzato in `min`: nessuno step sotto `base`.
- fingerprint: due stream identici salvo `range_anchor` sono dirty.

Da tenere **verdi senza modifiche** — è il criterio di successo del design:

- `tests/shared/test_distribution_strategy.py` (le distribuzioni non cambiano);
- gli 82 file di test che nominano `_range`: col default `center` nessuno di
  loro deve accorgersi della modifica.

---

## Rischi architetturali

1. **Superficie che sembra piccola e non lo è.** Una chiave sola cambia il
   significato di ogni `_range` dello stream. Serve che la reference dica
   esplicitamente *quali* range governa (inventario, punto 3) e quali no.
2. **Render esistenti.** Col default `center` nessun render cambia
   bit-per-bit — va verificato con un golden test, non asserito.
3. **Cache stems.** Se `range_anchor` non entra nel fingerprint, cambiarlo
   lascia stem vecchi in cache: audio sbagliato senza nessun errore. Stessa
   attenzione riservata a `rng_group`.
4. **Bounds.** In `min` la banda utile arriva a `base + range`: un valore che
   passava la validazione centrato può sforare il tetto. Valutare una
   validazione al parse (`base + range` dentro i bounds) invece del solo
   safety clamp a valle.
5. **Il nome.** `range_anchor: min` dice l'ancora ma non che `range` è
   un'apertura verso l'alto. Alternative da discutere: `range_mode: centered |
   upward`, oppure `range_from: center | base`.

---

## Impatto cross-repo (regola `cross-repo-impact`)

- **PGE-ls**: nuova chiave per-stream con enum a due valori — completamento,
  hover, diagnostica del valore non valido. È lo stesso lavoro già mappato per
  `duration_unit` in DMGiulioRomano/PGE-ls#36.
- **PGE-ui**: l'Inspector mostra i `_range` come "± valore"; con `min` l'etichetta
  e la banda disegnata nell'editor envelope cambiano. Serve anche il controllo
  per la nuova chiave.
- **gl-ls**: `study.yml` eredita la chiave nel blocco `base:` (passthrough
  engine). Ma soprattutto: se granulation-studies adotta `range_anchor: min`,
  le due semantiche di `range` coincidono e gl-ls può finalmente descriverne
  **una** — oggi deve spiegare che `axes.*.range` e `base.*_range` sono cose
  diverse.
- **granulation-studies**: adottare la modalità non è gratis. I valori dei
  `base.*_range` esistenti vanno **riletti**: p.es. `stack_300-1000ms` ha
  `duration_range` fino a 350 ms su base 300 → oggi la banda è `[125, 475]`,
  con `min` diventa `[300, 650]`. I quattro study in ms vanno ripassati, e
  `stack_1-50smp` pure.

## Sync paper CIM 2026 (regola `submodule-sync-cim`)

Il rendering cambia solo per chi attiva la chiave, e gli esempi del paper non la
useranno. Nessun bump necessario, salvo che si voglia allineare il submodule per
altri motivi.

---

## Sequenza di implementazione (commit atomici, test gate su ognuno)

1. `test`: la funzione pura `resolve` (rossi) — fissa la semantica prima del
   codice.
2. `feat`: `range_anchor.py` + campo in `StreamConfig`, non ancora cablato.
3. `test` + `feat`: cablaggio in `Parameter.get_value`, uniform, modalità
   `center` dimostrata identità.
4. `test` + `feat`: modalità `min` su `AdditiveVariation`.
5. `test` + `feat`: `QuantizedVariation` (pitch).
6. `test` + `feat`: gaussiana secondo la decisione del punto 4 del Design.
7. `test` + `fix`: fingerprint della cache.
8. `docs`: reference + CHANGELOG.
9. Issue cross-repo su PGE-ls e PGE-ui.

**Prima di partire dal punto 1 servono due decisioni** che non spettano a questo
documento: la semantica della gaussiana in `min` (Design §4) e il nome della
chiave (Rischi §5).
