---
title: "feat: range_anchor — interruttore fra range centrato (base ± range/2) e range ancorato al minimo (base → base + range)"
type: feat
status: accepted
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

## Design proposto

### 1. Decisioni prese (grilling del 2026-07-29)

Il piano era esplicito nel non poter decidere da solo due cose. Sono chiuse:

| decisione | esito |
|---|---|
| gaussiana in `min` (§4 originale) | **(a) banda piena**: μ = `base + range/2`, σ = `range/6`, clamp ai bordi |
| nome della chiave (§Rischi 5) | **`range_anchor: center \| min`**, default `center` |

Sulla gaussiana i numeri hanno deciso: con σ = `range` il **30.8%** dei valori
cade sotto `base` (200k draw, base 300 / range 200), cioè la modalità
mentirebbe su un grano su tre. Con σ = `range/6` la quota è 0% e il clamp
tocca solo lo 0.28% dei campioni — le sole code oltre 3σ.

Sul nome è stata scelta la parola di `granulation-studies` (`min`) invece di
un nome che dichiarasse anche il cambio di σ (`range_mode: deviation | band`,
la raccomandazione respinta). `range_anchor` regge se lo si legge come "dove è
ancorata la **banda**": la banda `[base, base + range]` è rispettata da
entrambe le distribuzioni, e σ = `range/6` è la conseguenza del fatto che la
gaussiana deve starci dentro. Il costo accettato: chi flippa la chiave su uno
stream gaussiano vede la nuvola **stringersi** (σ 200 → 33), non solo
spostarsi. La reference lo dichiara esplicitamente.

### 2. Perché NON una nuova `distribution_mode`

Registrare `uniform_min` / `gaussian_min` via `DistributionFactory.register` è
tentante (il registry esiste già), ma confonde due assi ortogonali: la **forma**
della distribuzione e l'**ancora** del range. Ogni distribuzione futura
andrebbe scritta due volte, e gli enum di PGE-ls / PGE-ui crescerebbero come
prodotto cartesiano invece che come somma.

### 3. Correzione al design proposto: l'ancora vive NELLE distribuzioni

La prima stesura proponeva una funzione pura
`resolve(base, width) -> (center, spread)` chiamata in `Parameter.get_value`,
argomentando che toccare le distribuzioni fosse la strada sbagliata.

**Quel design non regge la decisione (a)**, che il piano stesso raccomandava:
la firma `(base, width) -> (center, spread)` non può esprimere né σ = `range/6`
(non sa quale distribuzione sta a valle) né il clamp ai bordi banda (che è
post-sample). Era compatibile solo con l'opzione (b), quella scartata.

Design implementato: **l'ancora è stato della `DistributionStrategy`**,
iniettata da `DistributionFactory.create(mode, rng, anchor)`.

```python
# UniformDistribution.sample
if self._anchor == ANCHOR_MIN:
    return self._rng.uniform(center, center + spread)
return center + self._rng.uniform(-0.5, 0.5) * spread     # invariato

# GaussianDistribution.sample
if self._anchor == ANCHOR_MIN:
    lo, hi = center, center + spread
    return min(max(self._rng.gauss((lo + hi) / 2.0, spread / 6.0), lo), hi)
return self._rng.gauss(center, spread)                     # invariato
```

Proprietà che lo rendono preferibile:

- il clamp di banda vive dove ha senso, nella distribuzione che conosce la
  propria forma;
- **`QuantizedVariation` non va toccata**: campiona attorno a 0 e somma dopo
  (`base + round(sample(0, range))`), quindi con l'ancora dentro la
  distribuzione il pitch quantizzato diventa "da `base` in su" da sé. La
  stesura precedente prevedeva invece di modificarla esplicitamente;
- `get_bounds()` resta coerente senza formule duplicate;
- i test esistenti delle distribuzioni **restano verdi senza modifiche**: il
  default `anchor='center'` lascia ogni formula identica riga per riga, e le
  sottoclassi registrate da terzi ereditano il costruttore.

Costo reale misurato sui test: **una riga** in `tests/conftest.py` (la fixture
`mock_config` usa `Mock(spec=StreamConfig)` e va istruita sul nuovo campo,
come per ogni campo aggiunto prima) più i due test sul conteggio dei campi
della dataclass. Nessun test di comportamento è stato toccato.

### 4. Il jitter implicito resta centrato

`ParameterBounds.default_jitter` è attivo solo quando l'utente **non** ha
dichiarato un range: è un tremolio simmetrico attorno al valore, non una banda.
Seguirlo darebbe a ogni parametro con jitter un bias sistematico verso l'alto
per il solo fatto di stare su uno stream in modalità `min`.

Il `Parameter` tiene quindi una seconda distribuzione sempre centrata, scelta
in `get_value` via `has_explicit_range` (property già esistente). Con
`anchor='center'` è la stessa istanza, quindi il default non paga nulla; le due
condividono l'RNG, quindi la sequenza dei draw non si sdoppia. Un test verifica
che con range implicito le due modalità producano valori identici.

### 4b. Bounds: avviso, non errore

In `min` la banda arriva a `base + range` e può sforare il tetto. Scelta:
**warning al parse** (`[BANDA]` nel log dei clip), non `ParameterBoundError`.

Un errore duro sarebbe asimmetrico: da centrata la stessa coppia sfora già
oggi e viene solo clampata in silenzio, quindi flippare una chiave
trasformerebbe un render che funziona in un fallimento fatale. Il safety clamp
resta la rete; il warning evita solo che lo sforamento si scopra dal log
per-grano. Con base o range a envelope conta il picco dei breakpoint.

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

## File coinvolti (implementato)

| File | Modifica |
|---|---|
| `src/pge/shared/distribution_strategy.py` | costanti `ANCHOR_CENTER`/`ANCHOR_MIN`/`VALID_RANGE_ANCHORS`; kwarg `anchor` su `DistributionStrategy.__init__` (validato) e su `DistributionFactory.create`; ramo `min` in `sample`/`get_bounds` di Uniform e Gaussian |
| `src/pge/core/stream_config.py` | campo `range_anchor: str = 'center'` accanto a `distribution_mode` |
| `src/pge/parameters/parser.py` | legge `config.range_anchor`, lo passa a `Parameter`, e avvisa se la banda `min` sfora il tetto (`_warn_if_band_exceeds_bounds`, `_peak`) |
| `src/pge/parameters/parameter.py` | kwarg `range_anchor`; seconda distribuzione sempre centrata per il jitter implicito; scelta in `get_value` via `has_explicit_range` |
| `src/pge/shared/logger.py` | `log_band_warning` — avviso `[BANDA]` al parse |
| `docs/reference/yaml.md` | §Ancora del range: tabella bande, gaussiana, inventario di cosa governa, bounds, cache |
| `CHANGELOG.md` | voce sotto Unreleased |

**Non** toccati, contrariamente alla prima stesura:

- `src/pge/strategies/variation_strategy.py` — `QuantizedVariation` segue
  l'ancora da sé (vedi Design §3);
- `src/pge/rendering/stream_cache_manager.py` — `compute_fingerprint` esclude
  solo `FINGERPRINT_IGNORE_KEYS` (`solo`/`mute`), quindi una chiave per-stream
  nuova entra nel fingerprint automaticamente. Aggiunti solo test che blindano
  la proprietà.

Verifiche che il piano lasciava in sospeso:

- **`rendering/score_visualizer.py`**: nessun impatto. Le serie `<param>_range`
  esportate da `envelope_extractor` sono disegnate come **curve indipendenti**
  (legenda `… rng`), non come banda composta attorno alla base: il visualizer
  non calcola mai `base ± range/2`, quindi la partitura non mente in modalità
  `min`. Resta impreciso solo il testo della legenda ("deviazione per-grano",
  issue #141), che in `min` è un'apertura verso l'alto: cosmetico, fuori scope.
- **`shared/distribution_strategy.py` come sorgente per PGE-ls**: le costanti
  dell'ancora sono esportabili come i nomi delle distribuzioni.

## Test (implementati)

Nuovi:

- `tests/shared/test_range_anchor.py` (30) — l'ancora nelle distribuzioni:
  default `center` bit-identico alla formula storica (confronto con RNG
  gemello), banda `min` per uniform e gaussian, fedeltà a `_draw` di
  granstudies, σ = `range/6` verificata sul 68%, `get_bounds`, validazione
  dell'ancora sconosciuta, no-op con spread ≤ 0.
- `tests/parameters/test_range_anchor_wiring.py` (19) — il cablaggio: campo in
  `StreamConfig`, inoltro alla distribuzione, banda `[base, base+range]`, lo
  scarto `range/2` fra le due modalità, **jitter implicito identico nelle due
  modalità**, pitch quantizzato mai sotto `base`, propagazione dal parser.
- `tests/parameters/test_range_anchor_regression.py` (16) — golden bit-per-bit
  contro il motore pre-feature (vedi sotto).
- `tests/parameters/test_range_anchor_band_warning.py` (10) — l'avviso
  `[BANDA]`: emesso solo in `min`, solo con range esplicito, mai fatale.
- `tests/rendering/test_stream_cache_manager.py` (+3) — `range_anchor` marca
  lo stem dirty, anche end-to-end.

Il **golden** (`tests/fixtures/range_anchor_center_golden.json`) non è una
fotografia del codice nuovo: i valori attesi sono stati generati eseguendo lo
stesso percorso su un worktree al commit `9ce7976`, prima che `range_anchor`
esistesse. Copre range scalare (uniform e gaussian), range a envelope, jitter
implicito e valori che finiscono nel safety clamp. Verifica extra fuori suite:
1440 valori (12 serie × 120 punti) identici **byte per byte** fra il worktree
pre-feature e il codice nuovo.

Rimasti verdi **senza modifiche**, come previsto:
`tests/shared/test_distribution_strategy.py` e tutti i test che nominano
`_range`. Aggiornati solo: la fixture `mock_config` in `tests/conftest.py`
(una riga) e i due test sul conteggio campi di `StreamConfig`.

Suite completa: **5113 passed, 2 skipped** (baseline pre-feature: 5039).

`make e2e-tests` **non gira in ambiente pulito**: il corpus audio in `refs/`
non è versionato e ogni render fallisce con `SampleNotFoundError`. Non è una
regressione introdotta da questo lavoro.

## Rischi architetturali (stato finale)

1. **Superficie che sembra piccola e non lo è.** Mitigato: la reference
   elenca esplicitamente cosa la chiave governa (i `_range` via `Parameter` e
   il pitch quantizzato) e cosa no (jitter implicito, detune implicito, spread
   per-voce, `iot` asincrono), con la ragione per ciascuno.
2. **Render esistenti.** Chiuso: dimostrato dal golden generato sul codice
   pre-feature, non asserito.
3. **Cache stems.** Chiuso: `range_anchor` entra nel fingerprint (denylist), e
   tre test lo blindano contro una futura aggiunta a `FINGERPRINT_IGNORE_KEYS`.
4. **Bounds.** Chiuso con un avviso al parse, non un errore (Design §4b).
5. **Il nome.** Deciso: `range_anchor: center | min` (Design §1), con il costo
   documentato nella reference.

## Sequenza di implementazione (eseguita)

Cinque commit, `make tests` verde su ognuno:

1. `feat(distribution)` — ancora nelle `DistributionStrategy`.
2. `feat(parameters)` — chiave YAML cablata fino al `Parameter`; jitter
   implicito sempre centrato.
3. `test(range_anchor)` — golden bit-per-bit contro il motore pre-feature.
4. `feat(parser)` — avviso `[BANDA]` quando la banda ancorata sfora il tetto.
5. `test(cache)` — `range_anchor` nel fingerprint degli stem.

## Impatto cross-repo (regola `cross-repo-impact`)

Verificato leggendo i due repo, non dedotto.

**PGE-ls** — impatto reale, issue da aprire.
`range_anchor` è una chiave per-stream con enum a due valori, esattamente la
forma che il language server già gestisce per `distribution_mode`
(`providers/completion_provider.py:176,198,266` la elenca in
`_VALUE_TRIGGER_KEYS` con completions dedicate; `diagnostic_provider.py:374`
la valida). Da aggiungere: completamento dei valori `center`/`min`, hover con
la tabella delle bande e la nota sulla gaussiana, diagnostica del valore non
ammesso.

**PGE-ui** — impatto reale, issue da aprire. Nulla si rompe:
`src/lib/yaml-bridge.js:92-93` elenca le chiavi per-stream modellate
(`time_mode`, `distribution_mode`, `range_always_active`, …) e `range_anchor`
non c'è, quindi finisce in `_extra` ed è preservata verbatim dal round-trip.
Ma:

- non è editabile né visibile nell'editor (serve un controllo accanto a
  `distribution_mode`);
- l'Inspector descrive i range come simmetrici — `Inspector.jsx:946`:
  `"± randomization on grain duration"` — etichetta che in modalità `min` è
  falsa; stessa cosa per le hint delle voice strategy che nominano `±`;
- il fingerprint JS (`backend.js`, denylist `color/mute/solo/onset`) dovrebbe
  includere la chiave da sé, ma va confermato che `_extra` finisca nel JSON
  canonico: se non ci finisse, flipparla lascerebbe lo stem verde invece che
  stale, con audio sbagliato in silenzio.

**gl-ls** — nessuna issue da questo lavoro. La regola `gl-ls-impact` scatta
sulle modifiche alla sintassi di `study.yml`, che qui non è toccata. Vale però
la pena notarlo per il futuro: se `granulation-studies` adotterà
`range_anchor: min`, le due semantiche di `range` coincideranno e gl-ls potrà
descriverne **una** invece di spiegare che `axes.*.range` e `base.*_range` sono
cose diverse.

**granulation-studies** — fuori dallo scope di questa PR, per scelta esplicita.
Adottare la modalità là non è gratis: i `base.*_range` esistenti vanno
**riletti** uno per uno, perché la stessa cifra cambia banda. Esempio concreto:
`studies/stack_300-1000ms/study.yml` ha `duration_range` fino a 350 su base
300 → oggi `[125, 475]`, con `min` diventerebbe `[300, 650]`. I quattro study
in ms e `stack_1-50smp` vanno ripassati. Annotato, non fatto.

## Sync paper CIM 2026 (regola `submodule-sync-cim`)

Nessun bump. Gli esempi del paper non attivano la chiave e il default non
cambia un bit del rendering (dimostrato dal golden), quindi il commit pinnato
in `raw/PythonGranularEngine` produce esattamente lo stesso audio e le stesse
partiture. Il bump resta opportuno solo se lo si vuole per altri motivi.
