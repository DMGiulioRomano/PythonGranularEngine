---
title: "feat(envelopes): BP group [points, interp] per-macrozona (issue #64)"
type: feat
status: active
date: 2026-07-17
issue: 64
branch: claude/issue-64-feasibility-etbjpa
---

# feat(envelopes): BP group [points, interp] per-macrozona

## Overview

Supporto per l'Option 2 della issue #64: un run di breakpoint puo' essere
avvolto in un "BP group" compatto `[points, interp]` che dichiara il tipo di
interpolazione della macrozona, simmetrico al loop block. Due macrozone BP
nello stesso envelope possono cosi' interpolare in modo diverso (es. fade-in
`cubic`, scala `step`, coda `linear`), anche con loop block in mezzo.

```yaml
density_env:
  - [[[0.0, 0], [0.2, 12], [0.4, 8]], 'cubic']              # zona A
  - [[[0, 8], [50, 18], [100, 8]], 0.7, 4, 'linear']        # loop, invariato
  - [[[0.75, 6], [0.9, 6], [1.0, 0]], 'step']               # zona B
```

---

## Problem Frame

Dopo la issue #54 l'interp per-segmento esiste gia' (`[t, v, type]`), ma
dichiarare una zona omogenea richiede di ripetere il type su ogni punto.
Inoltre in formato misto l'interp del **primo** loop block diventa il default
globale (`extract_interp_type`) e contamina anche i run di BP nudi: verificato
sperimentalmente, `[[0,0],[0.3,30],[loop 'step']]` valuta il tratto 0→0.3 come
`step` (hold a 0) invece che `linear`. Non esiste una forma per dire "questa
zona di breakpoint interpola X" senza effetti collaterali sul resto.

---

## Requirements Trace (dalla issue #64)

- **R1.** Item `[points, interp]` accettato dentro lista mista: `points` lista
  di `[t, v]` / `[t, v, type]` (tempi assoluti, come i BP nudi), `interp ∈
  {linear, cubic, step}`.
- **R2.** Forma diretta `Envelope([points, interp])` accettata (simmetria col
  formato compatto diretto).
- **R3.** Tuple length discrimina: BP group = 2 elementi, loop block = 3–6.
  Nuovo check `_is_bp_group` accanto a `_is_compact_format`.
- **R4.** Il renderer legge la forma BP group senza rompere le fixture
  esistenti (backward compat totale: oggi entrambe le forme sollevano
  `ValueError`, quindi la sintassi e' puramente additiva).
- **R5.** Zone `cubic` usano PCHIP (Fritsch–Carlson monotone), identico al
  cubic esistente.
- **R6.** Le discontinuita' ai bordi zona seguono la regola
  `DISCONTINUITY_OFFSET` esistente.
- **R7.** Interp invalido → `InvalidFieldValueError` con hint dei tipi validi
  (stesso stile della validazione per-punto #54).
- **R8.** `time_mode: normalized` scala i tempi dei punti del gruppo;
  lo scaling Y (pointer normalized, grain.duration samples) scala i valori
  del gruppo; `is_envelope_like` riconosce la forma.

Fuori scope (dalla issue): interp per-segmento dentro una zona (gia' coperto
da #54 coi 3-tuple), interp per-ciclo dentro un loop, emitter/round-trip YAML
(`fmtEnvInline` / `parseEnvLiteral` sono superficie PGE-ls/PGE-ui).

---

## Design

### Desugar, non nuovo modello

Il BP group e' **sugar sintattico** risolto da `EnvelopeBuilder`: ogni punto
del gruppo tranne l'ultimo viene emesso come 3-tuple `[t, v, group_interp]`
(infrastruttura #54). Il modello a segmenti, `evaluate`, `integrate`, le
tangenti Fritsch-Carlson globali e la property `breakpoints` restano invariati.

### Semantica della zona

- La zona possiede i suoi **segmenti interni**: n punti → n−1 segmenti col
  group interp. Il segmento in uscita dall'ultimo punto del gruppo (gap verso
  l'item successivo) resta al default globale, come i BP nudi oggi.
- Un punto 3-tuple dentro il gruppo fa **override** del group interp per il
  proprio segmento (simmetrico all'override per-punto dentro i loop block).
- L'interp del gruppo **non** diventa tipo globale dell'envelope:
  `extract_interp_type` resta invariato (scansiona solo i loop block). Il leak
  esistente dei loop block resta invariato per backward compat.
- Ultimo punto del gruppo non taggato → nessun warning spurio "type su ultimo
  punto ignorato" quando il gruppo chiude l'envelope. Se l'utente scrive un
  3-tuple esplicito sull'ultimo punto del gruppo, viene preservato (e il
  warning esistente scatta solo se e' anche l'ultimo punto dell'envelope).
- Collisione temporale al bordo: se il primo punto del gruppo ha `t <=
  current_time` (ultimo breakpoint precedente), viene spostato a
  `current_time + DISCONTINUITY_OFFSET` — stessa regola dei loop block. Nessuno
  shift se non c'e' collisione (i tempi del gruppo sono assoluti).
- Gruppo con meno di 2 punti → `ValueError` (una zona senza segmenti interni
  non ha senso; stesso spirito di "pattern_points non puo' essere vuoto").

### Disambiguazione shape

| Forma | len | elem[0] | elem[1] | Riconoscimento |
|-------|-----|---------|---------|----------------|
| BP nudo `[t, v]` | 2 | num | num | non group (elem[0] non lista) |
| 3-tuple `[t, v, type]` | 3 | num | num | non group (len 3) |
| Loop block | 3–6 | lista punti | num | non group (len ≥ 3) |
| **BP group** `[points, interp]` | **2** | **lista di punti** | **str** | `_is_bp_group` |

`_is_bp_group` e' strutturale (come `_is_3tuple_breakpoint`): richiede lista a
2 elementi, `elem[1]` stringa, `elem[0]` lista i cui elementi sono tutti punti
`[num, num]` o `[num, num, str]` (bool esclusi). La validazione del valore di
interp avviene in espansione → `InvalidFieldValueError` con hint. Il vincolo
"almeno 2 punti" e' anch'esso in espansione, per dare errori precisi.

Collisioni verificate: `[[0,5], 'cycle']` non e' un group (elem[0] e' un punto,
non una lista di punti); un envelope nudo a 2 breakpoint `[[0,0],[1,1]]` non e'
un group (elem[1] non stringa).

### File toccati

| File | Modifica | Rischio |
|------|----------|---------|
| `src/pge/envelopes/envelope_builder.py` | `_is_bp_group`, `_expand_bp_group`; hook in `parse` (forma diretta + item misto); conteggio group in `_log_final_envelope` | medio |
| `src/pge/envelopes/envelope.py` | branch group in `is_envelope_like`, `_scale_raw_values_y`, `_scale_time_recursive`; docstring | basso |
| `tests/envelopes/test_envelope_bp_group.py` | nuova suite (riconoscimento, semantica, integrate, offset, scaling, envelope-like, warning) | — |
| `docs/reference/yaml.md` | nuova §2.7 + aggiornamento tabelle riepilogo | nullo |
| `CHANGELOG.md` | voce Unreleased/Aggiunto | nullo |

Non toccati: `envelope_segment.py`, `envelope_interpolation.py`,
`envelope_factory.py`, `time_distribution.py`, `parameters/*` (il routing
lista/dict → `create_scaled_envelope` copre gia' la nuova forma),
`extract_interp_type`.

---

## Piano TDD

1. **Fase rossa** — `tests/envelopes/test_envelope_bp_group.py`:
   riconoscimento e disambiguazione; acceptance (diretta, mista, dentro dict
   points); validazione interp e "almeno 2 punti"; semantica evaluate (zona
   step + gap linear, due zone diverse, override 3-tuple, nessun leak sul
   globale ne' sui BP nudi, equivalenza cubic diretto ↔ dict cubic);
   integrate analitico; DISCONTINUITY_OFFSET su collisione (dopo BP nudo,
   dopo loop, dopo altro gruppo) e nessuno shift senza collisione; scaling X
   normalized e scaling Y con type preservato; `is_envelope_like`; nessun
   warning con gruppo in coda. Conferma del fallimento.
2. **Fase verde** — implementazione minima in `envelope_builder.py` +
   `envelope.py` fino a suite verde; `make tests` completo (gate).
3. **Documentazione** — §2.7 in `docs/reference/yaml.md`, tabelle, CHANGELOG,
   `make docs-index && make docs-lint`.

Commit: tests+impl insieme (il test gate `make tests` richiede exit 0 a ogni
commit, quindi niente commit rosso intermedio), poi docs+changelog+plan→done.

---

## Impatti cross-repo (dichiarazione)

- **PGE-ls**: nuova shape da validare/autocompletare (`isBPGroup` accanto a
  `isCompactBlock`, diagnostica su interp invalido e su gruppo < 2 punti,
  round-trip `parseEnvLiteral`/`fmtEnvInline`). Issue da aprire sul repo
  `PGE-ls` (non raggiungibile da questa sessione).
- **PGE-ui**: selettore interp per-macrozona, rimozione selettore globale con
  piu' macrozone, `expandMixed` con interp per-zona — gia' enumerati nella
  sezione "UI consequences" della issue #64. Issue da aprire sul repo `PGE-ui`
  (non raggiungibile da questa sessione).
- **Paper CIM 2026**: nessun bump submodule necessario — la sintassi e'
  additiva, gli esempi `exN.yml` esistenti non la usano e il rendering delle
  forme esistenti e' bit-invariato (suite di regressione verde).

---

## Riferimenti

- Issue: https://github.com/DMGiulioRomano/PythonGranularEngine/issues/64
- Plan gemello: `2026-05-22-003-feat-envelope-per-point-interp-plan.md` (#54)
- Codice: `src/pge/envelopes/envelope_builder.py`, `src/pge/envelopes/envelope.py`
- Doc: `docs/reference/yaml.md` §2, §5, §7
