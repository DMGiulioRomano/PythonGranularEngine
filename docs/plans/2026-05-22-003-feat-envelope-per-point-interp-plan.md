---
title: "feat(envelopes): formato envelope con interp type per-punto (issue #54)"
type: feat
status: active
date: 2026-05-22
issue: 54
branch: feature/issue-54-envelope-interp-per-point
---

# feat(envelopes): formato envelope con interp type per-punto

## Overview

Supporto sintassi envelope dove ogni breakpoint dichiara il proprio tipo di interpolazione, applicato al segmento dal punto fino al successivo. Oggi `type` (`linear`/`cubic`/`step`) è globale per l'intero envelope. Per curve miste serve attualmente spezzare in envelope annidati — sintassi pesante. Issue #54 propone tupla 3-elem `[t, v, type]` e dict per-punto `{t, v, type}` come additivi al formato corrente.

---

## Problem Frame

`Envelope._parse_segments` crea **un solo `NormalSegment`** contenente tutti i breakpoint. La strategia è scelta una volta a livello `Envelope.__init__` da `extract_interp_type` o dal dict `type`. Quando il compositore vuole attacco cubic + decay lineare deve:

1. Spezzare in due Envelope annidati (verboso, perde leggibilità)
2. Approssimare con cubic+plateau (non equivalente)

Inoltre `_compute_fritsch_carlson_tangents` opera su tutti i breakpoint senza distinzione: cubic globale genera tangenti su segmenti che il compositore vorrebbe lineari, producendo overshoot indesiderato.

---

## Requirements Trace

- **R1.** Lista accetta breakpoint 3-elem `[t, v, type]` dove `type ∈ {linear, cubic, step}` — applicato a segmento `i → i+1`.
- **R2.** Dict accetta point come `{t, v, type}` in `points`, oltre a `[t, v]`.
- **R3.** Lista accetta mix 2-elem + 3-elem nello stesso envelope.
- **R4.** Globale (`dict.type` o wrapper compatto `interp`) fa da **default**; per-punto override.
- **R5.** Ultimo punto + `type` → warning a log, valore ignorato (no errore breaking).
- **R6.** `type` invalido → `InvalidFieldValueError` con `field_path`.
- **R7.** Backward compat assoluta: tutti gli YAML esistenti producono output bit-identico.
- **R8.** Wrapper compatto `[pattern, end_time, n_reps, ...]` con pattern contenente 3-tuple replica i type per-punto in ogni ciclo.
- **R9.** Stream cache fingerprint cambia se `type` per-punto cambia → cache invalidata correttamente.
- **R10.** `Envelope.evaluate(t)` e `Envelope.integrate(from, to)` restituiscono valori coerenti su envelope misto multi-tipo.

---

## Scope Boundaries

**In scope:**
- Parsing (`EnvelopeBuilder`)
- Modello segmenti (`Envelope._parse_segments`)
- Cubic Fritsch-Carlson boundary-aware
- Documentazione YAML

**Out of scope:**
- Nuove strategie di interpolazione (es. `quadratic`, `bezier`)
- Modifiche editor PGE-ls (saranno follow-up)
- Issue #64 (per-macrozone group) e #55 (cycle_mode wrap) — ortogonali
- Per-segmento dentro loop ciclico (gestito automaticamente dalla replica pattern)

---

## Disambiguazione parser — punto critico

**Problema:** distinguere a parsing time tra:

| Forma | Esempio | Riconoscimento |
|-------|---------|----------------|
| Breakpoint 2-elem | `[0.5, 1.0]` | len=2, elem[0]=num, elem[1]=num |
| Breakpoint 3-elem (NEW) | `[0.5, 1.0, 'cubic']` | len=3, elem[0]=num, elem[1]=num, elem[2]=str |
| Compact 3-elem | `[[[0,0],[100,1]], 0.4, 4]` | len=3, elem[0]=**list di liste**, elem[1]=num, elem[2]=**int** |
| Compact 4-elem | `[[[0,0],[100,1]], 0.4, 4, 'linear']` | len=4, elem[0]=list, elem[3]=str |
| Compact 5-elem | `[[[0,0],[100,1]], 0.4, 4, 'linear', 'exp']` | len=5, elem[0]=list |

**Regola discriminante (in ordine):**

1. **Tipo di `elem[0]`**: se è `list` → candidato compact format. Se è `int|float` → candidato breakpoint.
2. **Compact format check** (`_is_compact_format`): richiede `elem[0]` list di `[x,y]`, `elem[1]` numerico, `elem[2]` `int`.
3. **3-tuple breakpoint check** (`_is_3tuple_breakpoint`, **nuovo**): `len(item)==3`, `elem[0]` numerico, `elem[1]` numerico, `elem[2]` stringa in whitelist `{linear, cubic, step}`.

**Conflitto da neutralizzare:** entrambe le forme hanno `len==3`. Già differenziate da `type(elem[0])`:
- Compact: `elem[0]: list[list]` (pattern points)
- 3-tuple: `elem[0]: int|float` (tempo)

Il check esistente `_is_compact_format` su `[0.5, 1.0, 'cubic']` ritorna `False` perché `elem[0]=0.5` non è lista → safe.

Il rischio inverso: `[[[0,0],[100,1]], 0.4, 4]` (compact) deve **non** essere riconosciuto come 3-tuple breakpoint. Già safe perché nuovo check richiede `elem[0]` numerico.

**Edge case YAML particolarmente subdolo:**

```yaml
# Compositore scrive per errore
parametro: [0.5, 'cubic']    # 2-elem con stringa → cosa fa parser?
```

Comportamento attuale: `parse` solleva `ValueError("Elemento non valido")` su `[0.5, 'cubic']` perché non è `[time, value]` con 2 numerici (check esiste in `_parse_segments`). Nuovo parser deve preservare quest'errore — `'cubic'` non è numerico → no confusione con 3-tuple.

**Forma vietata da specificare in test:**
- `[0.5, 'cubic', 1.0]` → elem[1] non numerico → errore esplicito (no ambiguità con 3-tuple che richiede elem[2]=str).

---

## Context & Research

### File toccati

| File | Modifica | Rischio |
|------|----------|---------|
| `src/envelopes/envelope_builder.py` | Nuovi metodi `_is_3tuple_breakpoint`, `_normalize_point`, `_validate_interp_type`. Estensione `parse` per accettare 3-tuple e dict per-punto. | medio |
| `src/envelopes/envelope.py` | `_parse_segments` ritorna **N segmenti** (uno per coppia bp). `_create_context_for_segment` calcola tangenti globali condivise. `evaluate` / `integrate` con lookup multi-segmento. | alto |
| `src/envelopes/envelope_segment.py` | `NormalSegment` invariato a livello API. Possibile fix `evaluate`/`integrate` per overlap range tra segmenti consecutivi (hold pre/post solo su estremi globali). | medio |
| `src/envelopes/envelope_interpolation.py` | Nessuna modifica strategy. Cubic Fritsch-Carlson resta in `Envelope`, ma scope: tangenti sui soli segmenti cubic con vicini come boundary. | basso |
| `src/parameters/parser.py`, `gate_factory.py` | Già accettano lista/dict. Nessuna modifica. | nullo |
| `docs/yaml-reference.md` | Documenta formato 3-elem + dict per-punto + (gap pre-esistente) dict globale `{type, points}`. | nullo |
| `docs/envelopes-reference.md` | Nuova sezione per-punto interp con esempi. | nullo |
| Test suite envelope | Nuovi test (vedi sezione Test). Tutti i test esistenti invariati. | medio |

### Modello interno proposto

Dopo `EnvelopeBuilder.parse`, lista normalizzata di 3-tuple:

```python
[
  [0.0, 0.0, 'cubic'],     # seg 0→1 cubic
  [0.2426, 0.21, 'linear'], # seg 1→2 linear
  [0.5, 1.0, 'step'],       # seg 2→3 step
  [1.0, 0.0, None],         # ultimo, type ignorato
]
```

`Envelope._parse_segments` itera coppie consecutive `(bp[i], bp[i+1])`, crea un `NormalSegment` per coppia con:
- `breakpoints=[bp[i], bp[i+1]]` (2 punti)
- `strategy = InterpolationStrategyFactory.create(bp[i].seg_type)`
- `context = {'tangents': [tangent[i], tangent[i+1]]}` (calcolate globalmente)

### Cubic boundary semantics

Tangenti Fritsch-Carlson calcolate **sull'intera lista breakpoint** indipendentemente da `seg_type` per-punto. Questo garantisce che segmento `cubic` adiacente a `linear` abbia tangente coerente coi vicini (la slope locale).

Segmenti con strategy `LinearInterpolation` o `StepInterpolation` ignorano `tangents` in context (le strategy non leggono `context['tangents']`).

**Trade-off considerato:** alternativa = tangenti = 0 ai boundary tra cubic e non-cubic. Più semplice, ma produce flat-at-boundary visivo. Scelto Fritsch-Carlson globale per qualità visiva, accettando minor overshoot teorico (mitigato da Fritsch-Carlson stesso che è monotone-preserving).

### Multi-segmento `evaluate` / `integrate`

`Envelope.evaluate(t)`:
1. Binary search del segmento contenente `t` (`segment.start_time <= t <= segment.end_time`).
2. Se `t < segments[0].start_time` → hold primo valore.
3. Se `t > segments[-1].end_time` → hold ultimo valore.
4. Altrimenti delega a `segment.evaluate(t)`.

`Envelope.integrate(from, to)`:
1. Itera segmenti che overlappano `[from, to]`.
2. Per ciascuno: `seg.integrate(max(from, seg.start), min(to, seg.end))`.
3. Aggiunge hold pre-`segments[0].start` e post-`segments[-1].end` se richiesto.

**Attenzione:** `NormalSegment.integrate` oggi include già hold pre/post sul singolo segmento. Con N segmenti, l'hold tra `seg[i].end` e `seg[i+1].start` (idealmente coincidenti) NON deve essere doppio-contato. Soluzione: passare range strettamente interni a ogni segmento, escludendo hold sue interne. **Test esplicito** su questo edge case.

---

## Backward compatibility

### Casi invariati

| YAML originale | Forma post-parsing | Garanzia |
|----------------|-------------------|----------|
| `[[0,0],[1,1]]` | 1 seg linear, identico a oggi | test esistenti |
| `{type: cubic, points: [[0,0],[1,1]]}` | 1 seg cubic | test esistenti |
| `[[[0,0],[100,1]], 0.4, 4]` | espansione N ciclica, 1 seg linear | test esistenti |
| `[[[0,0],[100,1]], 0.4, 4, 'cubic']` | espansione N, 1 seg cubic | test esistenti |

**Implementazione:** quando tutti i breakpoint hanno stesso `seg_type` (o `None`), il risultato semantico è equivalente a oggi (1 strategy applicata a tutti i segmenti). N segmenti vs 1 segmento — comportamento osservabile (evaluate/integrate output) identico **modulo floating-point** sui boundary.

**Verifica empirica obbligatoria:** test che confronta output `evaluate` su 1000 punti random tra Envelope nuovo e baseline pre-refactor per tutti i fixture esistenti.

### Wrapper compatto + 3-tuple

Pattern compatto può contenere 3-tuple:

```yaml
parametro: [[[0, 0, 'cubic'], [50, 1, 'linear'], [100, 0]], 0.4, 4]
```

Espansione: 4 cicli, ognuno replica `cubic` su segmento 1, `linear` su segmento 2. Tra cicli (gap dovuto a `DISCONTINUITY_OFFSET`): interp segue il **wrapper `interp_type` globale** (elem[3], default linear). Logica: gap inter-ciclo non è "dentro il pattern", quindi `seg_type` per-punto non si applica.

---

## Edge case da testare

1. **Mix 2-elem + 3-elem nella stessa lista**: `[[0,0,'cubic'],[1,1]]` → seg cubic, ultimo ha `seg_type=None` (corretto, ultimo punto).
2. **Type su ultimo punto**: `[[0,0],[1,1,'cubic']]` → warning, `cubic` ignorato (no segmento successivo).
3. **Type invalido per-punto**: `[[0,0,'foo'],[1,1]]` → `InvalidFieldValueError` con messaggio chiaro.
4. **Step + linear contiguo**: `[[0,0,'step'],[0.5,1,'linear'],[1,0]]` → `evaluate(0.25) == 0` (step), `evaluate(0.75) == 0.5` (linear).
5. **Cubic singolo segmento isolato**: stessa tangente del cubic globale equivalente.
6. **Integrate cross-boundary**: `integrate(0,1)` su envelope misto = somma integrali per-segmento (verificato analiticamente con linear+step).
7. **Wrapper compatto con 3-tuple pattern**: cicli replicano correttamente i seg_type.
8. **Dict per-punto**: `{type: linear, points: [{t:0,v:0,type:cubic},{t:1,v:1}]}` → equivalente a 3-tuple list.
9. **Mix dict + tupla in `points`**: vietato? Permesso? **Scelta:** permesso, normalize in builder.
10. **Cache fingerprint**: cambio `type` per-punto cambia hash YAML → cache invalida.
11. **Time normalized + 3-tuple**: `_scale_time_recursive` deve preservare elem[2] (`seg_type`) mentre scala elem[0] (`t`).
12. **Scale Y values + 3-tuple**: `_scale_raw_values_y` deve preservare elem[2] mentre scala elem[1] (`v`).

---

## Plan (TDD)

### Fase 1 — Test rossi (parser + disambiguazione)

1. Test: `EnvelopeBuilder._is_3tuple_breakpoint([0.5, 1.0, 'cubic'])` → `True`
2. Test: `EnvelopeBuilder._is_3tuple_breakpoint([0.5, 1.0])` → `False`
3. Test: `EnvelopeBuilder._is_3tuple_breakpoint([0.5, 1.0, 'foo'])` → `False`
4. Test: `EnvelopeBuilder._is_3tuple_breakpoint([[0,0],[100,1]], 0.4, 4)` → `False` (non passare lista, ma item)
5. Test: `_is_compact_format([0.5, 1.0, 'cubic'])` → `False` (regression check)
6. Test: `_is_compact_format([[[0,0],[100,1]], 0.4, 4])` → `True` (regression)
7. Test: `Envelope([[0,0,'cubic'],[1,1]])` non solleva
8. Test: `Envelope([[0,0,'foo'],[1,1]])` → `InvalidFieldValueError`
9. Test: mix 2/3-elem accettato: `Envelope([[0,0,'cubic'],[0.5,1],[1,0,'step']])`
10. Test: dict per-punto `{type: linear, points: [{t:0,v:0,type:cubic},{t:1,v:1}]}` accettato
11. Test: forma vietata `[0.5, 'cubic']` (2-elem con stringa al posto di valore) → errore chiaro

### Fase 2 — Test rossi (semantica evaluate)

12. Test: `[[0,0,'step'],[0.5,1,'linear'],[1,0]]`:
    - `evaluate(0.0) == 0`
    - `evaluate(0.25) == 0` (step: hold)
    - `evaluate(0.5) == 1`
    - `evaluate(0.75) == 0.5` (linear)
    - `evaluate(1.0) == 0`
13. Test: cubic per-segmento isolato `[[0,0,'cubic'],[1,1]]` ha output equivalente a `Envelope({'type':'cubic','points':[[0,0],[1,1]]})` su 100 punti.
14. Test: `[[0,0,'linear'],[1,1,'linear']]` → output identico a `[[0,0],[1,1]]` (entrambi linear) — verifica backward compat semantica.

### Fase 3 — Test rossi (integrate)

15. Test: `integrate(0,1)` su `[[0,0,'step'],[0.5,1,'linear'],[1,0]]` = `0*0.5 + 0.5*1*0.5` = `0.25` (step area + triangolo).
16. Test: `integrate` cross-boundary tra cubic e linear: somma analitica per-segmento.
17. Test: `integrate(0,1)` su envelope all-linear identico a baseline pre-refactor (regression).

### Fase 4 — Test rossi (edge case)

18. Test: ultimo punto con `type` → warning emesso a logger, no errore.
19. Test: wrapper compatto con 3-tuple pattern: `Envelope([[[0,0,'cubic'],[50,1,'linear'],[100,0]], 0.4, 4])` espande mantenendo `seg_type` per-punto.
20. Test: `time_mode: normalized` + 3-tuple preserva `seg_type` dopo `_scale_time_recursive`.
21. Test: `_scale_raw_values_y` + 3-tuple preserva `seg_type` dopo scaling Y.
22. Test: `Envelope.breakpoints` property con N segmenti restituisce concatenazione senza duplicare giunzioni.

### Fase 5 — Implementazione

23. `EnvelopeBuilder._is_3tuple_breakpoint(item)`: helper di disambiguazione.
24. `EnvelopeBuilder._validate_interp_type(t, context)`: solleva `InvalidFieldValueError` su tipo non in whitelist.
25. `EnvelopeBuilder._normalize_point(item, default_type)`: converte 2-elem, 3-elem, dict in tupla canonica 3-elem `(t, v, seg_type_or_None)`.
26. `EnvelopeBuilder.parse`: estesa per produrre lista normalizzata 3-tuple. Backward compat: se input è 2-elem only, output preserva 2-elem (per non rompere consumer downstream che fanno unpacking).
    - **Decisione tecnica:** output di `parse` rimane lista `[t, v]` (2-elem) per backward compat. La 3a colonna `seg_type` viaggia in lista parallela `seg_types: List[Optional[str]]` ritornata insieme oppure attaccata come attributo. **Scelta:** ritornare tupla `(breakpoints_2elem, seg_types)`. Refactor `Envelope.__init__` per consumare entrambi.
    - **Alternativa:** ritornare sempre 3-elem; consumer downstream (`_scale_time_recursive`, `_scale_raw_values_y`, `_log_*`) tutti aggiornati per gestire 3-elem. **Più clean.**
    - **Decisione finale:** prima alternativa (ritornare 3-elem) — meno punti di attrito.
27. `Envelope.__init__`: estrae `seg_types` dalla lista parsed.
28. `Envelope._parse_segments`: itera coppie, crea N `NormalSegment` con strategy per-segmento.
29. `Envelope._compute_fritsch_carlson_tangents`: invariato (opera su lista 2-elem proiettata).
30. `Envelope.evaluate`: binary search segmento + delega.
31. `Envelope.integrate`: somma per-segmento su range overlap, gestisce hold globali.
32. `Envelope.breakpoints` property: ricostruisce concatenazione senza duplicare punti giunzione.
33. `EnvelopeBuilder._log_compact_transformation` e `_log_final_envelope`: aggiornati per loggare 3-elem se presenti.
34. `Envelope._scale_raw_values_y`: preserva elem[2] su 3-tuple.
35. `_scale_time_recursive`: preserva elem[2] su 3-tuple.

### Fase 6 — Verifica integrazione

36. `make tests` verde.
37. `make e2e-tests` verde.
38. YAML reale con envelope misto su `density`, `pitch`, `amp`: render NumPy + Csound producono output coerente.
39. Stream cache: cambio `type` per-punto in YAML invalida cache (test ad hoc + verifica con `STEMS=true CACHE=true`).
40. Snapshot test: confronto bit-identico output WAV su 5 fixture esistenti pre/post refactor (`tests/e2e/fixtures/*.yaml`).

### Fase 7 — Documentazione

41. `docs/yaml-reference.md`: nuova sezione "Envelope per-point interpolation" con esempi tupla e dict.
42. `docs/envelopes-reference.md`: aggiornare §2 + §5 con nuovo formato e regola di disambiguazione (riportare tabella di questo plan).
43. `docs/yaml-reference.md`: documentare gap pre-esistente (dict format `{type, points}` non documentato).

---

## Decisioni risolte

- **Ultimo punto + type:** warning a log, valore ignorato.
- **Tupla vs dict:** entrambe supportate.
- **Type globale + per-punto:** globale = default, per-punto override.
- **Output `parse`:** 3-elem normalizzato (refactor consumer downstream).
- **Cubic boundary:** tangenti Fritsch-Carlson globali, applicate solo a segmenti cubic.
- **Gap inter-ciclo in wrapper compatto:** interp seguita = wrapper globale, no per-punto.

---

## Decisioni aperte (richiedono conferma utente)

Nessuna. Tutto risolto in fase di analisi.

---

## Riferimenti

- Issue: `gh issue view 54`
- Codice: `src/envelopes/envelope.py:80-110`, `src/envelopes/envelope_builder.py:125-176`
- Doc esistente: `docs/envelopes-reference.md` §2, §5
- Issue correlate (ortogonali): #55 (cycle_mode wrap), #64 (per-macrozone group)
