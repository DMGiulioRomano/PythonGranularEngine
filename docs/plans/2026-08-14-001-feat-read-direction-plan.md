---
title: "feat(yaml): grain.read_direction — il verso di lettura del grano diventa dichiarativo"
type: feature
status: active
date: 2026-08-14
issue: 207
---

# feat(yaml): `grain.read_direction`

## Overview

Il verso di lettura **interno al grano** oggi ha una sola superficie
dichiarativa, `grain.reverse`: una chiave che deve essere presente e vuota, ha
due soli stati (`auto` / sempre indietro) e non è esprimibile come funzione del
tempo. Il caso deterministico più ovvio — testina che percorre il buffer
all'indietro, grani letti in avanti — si ottiene oggi saturando un gate
stocastico (`deviation_probability: {reverse: 100}`).

Questo plan introduce `grain.read_direction`: dominio `[-1, +1]`, scalare o
envelope, interpolazione `step` imposta, in exclusivity group con
`grain.reverse`. Nessun breaking change: `grain.reverse` resta identica e con
entrambe le chiavi assenti il comportamento resta `'auto'`.

---

## Problem Frame

Quattro varianti minime dello stesso YAML (issue #207), osservate sul segno di
`Grain.pitch_ratio` — l'unica grandezza che decide il verso di lettura interno:

| YAML | percorrenza buffer | lettura nel grano |
|---|---|---|
| `speed_ratio: -1`, `reverse` assente | indietro | indietro |
| `speed_ratio: -1` + `reverse:` | indietro | indietro (la dichiarazione non cambia nulla) |
| `speed_ratio: +1` + `reverse:` | avanti | indietro |
| `speed_ratio: -1` + `reverse:` + `deviation_probability: {reverse: 100}` | indietro | avanti |

La riga 4 è il difetto che genera la issue: un comportamento deterministico
ottenuto saturando un meccanismo stocastico.

Tre grandezze da non confondere, e che questo plan tiene separate:

- `pointer.speed_ratio` — verso della **testina** sul buffer;
- il blocco `pitch` — **altezza percepita**, bounds positivi per costruzione,
  fuori da questa modifica;
- `Grain.pitch_ratio` — incremento di fasore interno, porta modulo **e** segno.
  Non è una chiave YAML e non viene rinominato.

---

## Design

### La chiave

```yaml
grain:
  read_direction: 1                       # scalare: +1 avanti, -1 indietro
  read_direction: [[0, 1], [12, -1]]      # envelope: il verso cambia a t=12
```

- dominio `[-1, +1]`, `-1` indietro, `+1` avanti — allineato alla convenzione
  del progetto, dove il negativo significa già "indietro" ovunque;
- scalare o envelope, come ogni altro parametro;
- `step` è **la natura della chiave**, non un'opzione: il verso è discreto, un
  valore intermedio fra -1 e +1 non significa nulla.

### Decisione 1 — interazione con `deviation_probability`

**Scelta: chiave dedicata `deviation_probability.read_direction`.**

`deviation_probability.reverse` continua a governare **solo** `grain.reverse`,
esattamente com'è oggi. La nuova chiave ha la propria voce nel blocco
`deviation_probability`, come ogni altro parametro dello schema:

```yaml
grain:
  read_direction: 1        # base: avanti
deviation_probability:
  read_direction: 30       # il 30% dei grani legge all'indietro
```

Perché non le altre due opzioni:

- *far flippare `deviation_probability.reverse` anche il valore dichiarato*
  lascerebbe una chiave chiamata `reverse` a governare un parametro chiamato
  `read_direction`, e un vecchio `reverse: 100` rimasto nello YAML
  ribalterebbe in silenzio il verso appena dichiarato;
- *ignorare il gate quando la chiave è presente* toglierebbe il verso
  stocastico a chi lo vuole, senza dargli una via dichiarativa.

Con la chiave dedicata il default è **deterministico** (chiave assente dal
dict → `NeverGate`), che è il punto della issue, e lo stocastico resta
raggiungibile con la sintassi che tutti gli altri parametri già usano.
Il comportamento sotto `deviation_probability` **globale** (numero o envelope
per tutte le chiavi) resta quello di ogni parametro dello schema, `reverse`
compresa: nessuna eccezione inventata per questa chiave.

Implementazione: `variation_mode='negate'` (nuova `NegateVariation`,
`base → -base`). Così il flip per-grano è dentro `Parameter.get_value()` e non
serve rubare il gate dall'esterno: `is_reverse = read_direction.get_value(t) < 0`
è tutta la lettura. `InvertVariation` (`1.0 - base`) non è riusabile: su un
dominio `-1/+1` produrrebbe `0` e `2`.

### Decisione 2 — valori fuori da `{-1, +1}`

**Scelta: rifiuto esplicito a parse-time, `y = 0` compreso.**

Con `step` imposto l'envelope emette solo i valori scritti ai breakpoint,
quindi arrotondare al segno significherebbe accettare una scrittura
(`read_direction: 0.3`) e renderizzarne un'altra (`+1`). Lo `0` non ha un segno
e non ha una risposta non arbitraria: rifiutarlo è l'unica lettura onesta.
Coerente con il rifiuto degli interp non-`step`: la chiave ha due stati, e li
pretende scritti.

Il rifiuto avviene **prima** del clamp dei bounds, così `read_direction: 0.5`
dà un errore che parla del dominio a due valori invece di passare silenziosamente
il clamp `[-1, 1]`.

### Dove vive la validazione

Nuovo modulo `src/pge/parameters/read_direction.py`, unico punto che legge il
valore grezzo di `grain.read_direction`. Precedente diretto:
`Stream._pre_normalize_grain_params` per `duration_unit` — un meta-parametro che
governa l'interpretazione degli altri, letto una volta sul dizionario grezzo.

Due responsabilità:

1. **rifiutare** ogni interp diverso da `step` in tutte le forme (dict `type`,
   3-tuple per-punto, BP group, formato compatto) e ogni `y` fuori da
   `{-1, +1}`;
2. **normalizzare** in `{'type': 'step', 'points': <raw>}`, così l'envelope
   costruito a valle è `step` senza che l'utente debba scriverlo.

Il wrapping preserva la semantica temporale: `create_scaled_envelope` sul dict
legge `time_unit` con fallback su `time_mode`, cioè esattamente quello che fa
sulla lista nuda.

### Exclusivity group

`grain.reverse` e `grain.read_direction` entrambe presenti → `InvalidFieldValueError`
esplicito, sollevato in `Stream._init_grain_reverse` prima che l'orchestratore
costruisca i parametri. Divergenza voluta dal precedente `loop_end`/`loop_dur`,
che risolve per priorità: qui le due chiavi hanno semantiche opposte e una
priorità silenziosa nasconderebbe l'errore invece di segnalarlo.

Nello schema le due spec condividono `exclusive_group='grain_direction'`: serve
a garantire che esattamente **uno** dei due `Parameter` esista (l'altro è
`None`), così il discriminante a valle è `self.read_direction is not None`. Il
tie-break per priorità del selettore resta irraggiungibile per questo gruppo —
va commentato, non subito.

### Codice morto

In `_calculate_grain_reverse` il ramo forzato legge `self.reverse._value` e
gestisce un `Envelope` con `hasattr(val, 'evaluate')`. È morto: `_init_grain_reverse`
rifiuta ogni valore non-`None`, quindi in quel ramo `_value` è sempre `None` e
`is_reverse_base` è sempre `True`. Con `read_direction` il ramo non diventa
raggiungibile — la chiave nuova ha un ramo proprio — quindi si elimina, e il
ramo forzato diventa `is_reverse_base = True`. Due test che lo pinnavano
(`test_forced_mode_with_envelope`, `test_forced_mode_envelope_below_threshold`)
vengono sostituiti da un test che verifica l'irraggiungibilità alla fonte.

---

## Steps

| # | Passo | Test rossi prima |
|---|---|---|
| 1 | `read_direction.py`: validazione + normalizzazione | `tests/parameters/test_read_direction.py` |
| 2 | Bounds + `NegateVariation` + registry | `test_parameter_definitions.py`, `test_variation_registry.py`, `test_variation_strategy.py` |
| 3 | `ParameterSpec` + exclusive group | `test_parameter_schema.py` |
| 4 | Wiring in `Stream` (init, exclusivity, `_calculate_grain_reverse`) | `tests/core/test_stream_read_direction.py`, `test_stream.py` |
| 5 | Colori envelope + range visualizer | `test_envelope_extractor.py` |
| 6 | Docs (`docs/reference/yaml.md`), `make docs-index`, `make docs-lint` | — |
| 7 | CHANGELOG `Unreleased / Aggiunto` | — |

## Copertura test richiesta

- i quattro casi della tabella restano invariati (regressione su `grain.reverse`);
- `read_direction` scalare `-1` / `+1` con `speed_ratio` concorde e discorde;
- `read_direction` envelope: il verso cambia ai breakpoint e **solo** lì;
- interp diverso da `step` nelle tre forme (dict, per-punto, BP group) → errore
  con hint leggibile;
- `grain.reverse` + `read_direction` insieme → errore di exclusivity;
- `deviation_probability.read_direction` flippa; `deviation_probability.reverse`
  non tocca `read_direction`;
- `y` fuori da `{-1, +1}`, `y = 0` e chiave vuota → errore.

Osservabile: il segno di `Grain.pitch_ratio`.

## Fuori scope

- Rinominare `Grain.pitch_ratio` o toccare il blocco `pitch`.
- Modificare la map: `grain_visuals.arrow_vertices` / `window_vertices`
  decidono il verso sul solo `sign(pitch_ratio)` — verificato, non riscritto.
- Cambiare `grain.reverse` o la modalità `'auto'`.

## Impatto cross-repo

Superficie YAML pubblica: issue su `PGE-ls` (autocomplete, dominio, exclusivity,
rifiuto interp, hover/snippet) e su `PGE-ui` (controllo a due stati, envelope,
default).
