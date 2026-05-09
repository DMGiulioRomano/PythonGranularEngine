---
title: "fix: NumPy renderer passthrough — buffer dinamico, rimozione guard ortogonali (issue #27)"
type: fix
status: done
date: 2026-05-03
---

# fix: NumPy renderer passthrough — buffer dinamico, rimozione guard ortogonali

## Overview

NumPy renderer contiene guard e troncamenti in `_add_grain_at_position` che costituiscono una **seconda superficie di controllo ortogonale** rispetto a `GrainClipStrategy` (piano 001). Questo piano le rimuove, rendendo il renderer un passthrough puro: dimensiona il buffer sull'extent reale dei grain ricevuti da `stream.voices` e li renderizza integralmente, senza giudizi propri sui bounds.

Questo piano **dipende concettualmente da piano 001**: la rimozione delle guard ha senso solo se `stream.voices` è già la fonte di verità controllata da una strategy. Le guard non vengono rimosse perché "non si attivano mai" — vengono rimosse perché **non devono esistere nel renderer**.

---

## Vincolo architetturale

**Il renderer non ha opinioni sui bounds dei grain.** Riceve `stream.voices`, alloca un buffer che contiene tutti i grain che trova, li renderizza. Il comportamento del buffer (durata, extent) è una conseguenza della strategy scelta in piano 001, non un parametro indipendente del renderer.

Mantenere le guard sarebbe accoppiare il renderer alla semantica dei bounds dello stream — responsabilità che appartiene a `GrainClipStrategy`.

---

## Problem Frame

In `_add_grain_at_position` esistono tre comportamenti di clamp:

| Linea | Condizione | Comportamento | Decisione |
|-------|-----------|---------------|-----------|
| 227 | `onset_sample < 0` | Taglia inizio grain (grain inizia prima del buffer) | **Preservare** — difesa legittima, indipendente dai bounds dello stream |
| 234–237 | `end_sample > n_total` | Tronca coda del grain — artefatto silenzioso | **Rimuovere** — responsabilità della strategy, non del renderer |
| 240 | `onset_sample >= n_total` | Scarta grain intero — divergenza con Csound | **Rimuovere** — responsabilità della strategy, non del renderer |

Il buffer è fisso a `stream.duration * sr`. Con grain che sforano (consentiti da `PassthroughClipStrategy`), questo produce:

- **Caso A** (onset fuori bounds): grain scartato silenziosamente. Il renderer ignora una scelta semantica esplicita della strategy.
- **Caso B** (coda fuori bounds): grain troncato. Il renderer modifica un grain che la strategy ha deliberatamente lasciato passare.

Entrambi i casi violano il vincolo architetturale: il renderer non deve sovrascrivere la decisione della strategy.

---

## Requirements Trace

- R1. `render_single_stream` dimensiona il buffer sull'extent reale: `max(g.onset + g.duration - stream.onset)` per tutti i grain in `stream.voices`.
- R2. `render_merged_streams` dimensiona il buffer sull'extent reale: `max(g.onset + g.duration)` per tutti i grain di tutti gli stream.
- R3. I clamp `end_sample > n_total` (riga 234) e `onset_sample >= n_total` (riga 240) sono rimossi.
- R4. Il clamp negativo (riga 227, `onset_sample < 0`) rimane — non riguarda i bounds dello stream.
- R5. Stream senza grain: fallback a `stream.duration` (comportamento invariato).
- R6. Con `OverflowMarginClipStrategy` (default): grain filtrati da piano 001 → `max(g.onset + g.duration)` ≤ `stream_end` → buffer == `stream.duration` emerge naturalmente, senza hardcode.
- R7. Con `PassthroughClipStrategy`: grain che sforano presenti in `stream.voices` → buffer esteso → grain renderizzati integralmente.
- R8. Tutti i test esistenti restano verdi o aggiornati al nuovo comportamento.

---

## Scope Boundaries

- Solo `numpy_audio_renderer.py` — nessuna modifica a Stream, ScoreWriter, Csound renderer.
- Nessuna nuova strategia, nessun nuovo parametro YAML.
- `Grain`, `Stream`, `stream.voices` invariati in questo piano.
- Il renderer non importa né conosce `GrainClipStrategy` — si adatta implicitamente al contenuto di `stream.voices`.

---

## Context & Research

### I tre clamp in `_add_grain_at_position` (righe 227–241)

```python
# CLAMP 1 — onset negativo (legittimo, preservare)
if onset_sample < 0:
    grain_buffer = grain_buffer[-onset_sample:]
    onset_sample = 0

end_sample = onset_sample + grain_len

# CLAMP 2 — coda oltre fine buffer (RIMUOVERE)
if end_sample > n_total:
    grain_buffer = grain_buffer[:n_total - onset_sample]
    end_sample = n_total

# CLAMP 3 — onset oltre fine buffer (RIMUOVERE)
if onset_sample < n_total and grain_buffer.shape[0] > 0:
    buffer[onset_sample:end_sample] += grain_buffer
```

### Buffer dinamico elimina entrambe le guard

Con `n_total = max(g.onset + g.duration - stream.onset) * sr` per tutti i grain in `stream.voices`:
- `end_sample <= n_total` per tutti i grain — CLAMP 2 non si attiva mai
- `onset_sample < n_total` per tutti i grain — CLAMP 3 sempre vero

Le guard non vanno rimosse perché "non si attivano" — vanno rimosse perché la loro esistenza presuppone che il renderer abbia responsabilità sui bounds. Con il buffer dinamico, questa presupposizione scompare strutturalmente.

### Adattamento implicito alla strategy

Il renderer non conosce quale strategy è stata usata. Vede solo i grain in `stream.voices`:

| Strategy (piano 001) | grain in `stream.voices` | buffer size (piano 002) |
|---------------------|--------------------------|------------------------|
| `OverflowMarginClipStrategy(margin=0.0)` | tutti entro `stream_end` | == `stream.duration` (naturale) |
| `OverflowMarginClipStrategy(margin=0.5)` | coda fino a `stream_end + 0.5` | esteso fino a `stream_end + 0.5` |
| `PassthroughClipStrategy` | tutti, inclusi quelli che sforano | esteso all'extent reale |

Il renderer si adatta senza conoscere la strategy — il risultato emerge dal contenuto di `stream.voices`.

---

## High-Level Technical Design

### `render_single_stream` (STEMS) — buffer sizing

```python
# PRIMA
n_total = int(stream.duration * self.output_sr)

# DOPO
all_grains = [g for voice in stream.voices for g in voice]
if all_grains:
    max_end_rel = max(g.onset + g.duration for g in all_grains) - stream.onset
else:
    max_end_rel = stream.duration
n_total = max(1, int(max_end_rel * self.output_sr))
```

### `render_merged_streams` (MIX) — buffer sizing

```python
# PRIMA
max_end_time = max(s.onset + s.duration for s in streams)

# DOPO
all_grains = [g for s in streams for v in s.voices for g in v]
if all_grains:
    max_end_time = max(g.onset + g.duration for g in all_grains)
else:
    max_end_time = max(s.onset + s.duration for s in streams)
n_total = max(1, int(max_end_time * self.output_sr))
```

### `_add_grain_at_position` — rimozione CLAMP 2 e 3

```python
# PRIMA
end_sample = onset_sample + grain_len
if end_sample > n_total:
    grain_buffer = grain_buffer[:n_total - onset_sample]
    end_sample = n_total
if onset_sample < n_total and grain_buffer.shape[0] > 0:
    buffer[onset_sample:end_sample] += grain_buffer

# DOPO
end_sample = onset_sample + grain_len
if grain_buffer.shape[0] > 0:
    buffer[onset_sample:end_sample] += grain_buffer
```

`n_total` viene rimosso dalla firma di `_add_grain_at_position` in U2 (nessun chiamante esterno — entrambi i caller sono metodi privati della stessa classe). Rimandarlo a un piano successivo lascerebbe un parametro inutilizzato nel corpo, che è peggio della rimozione immediata.

---

## Implementation Units

---

### U1. Buffer sizing dinamico in `render_single_stream` e `render_merged_streams`

**Goal:** Calcolare `n_total` sull'extent reale dei grain invece di `stream.duration`.

**Requirements:** R1, R2, R5, R6, R7

**Dependencies:** Piano 001 U2 (stream.voices come fonte di verità)

**Files:**
- Modifica: `src/rendering/numpy_audio_renderer.py` (righe ~101 e ~140)
- Modifica: `tests/rendering/test_numpy_audio_renderer.py`

**Test scenarios:**

`render_single_stream`:
- Grain tutti dentro `stream.duration` → buffer == `stream.duration * sr` (R6 — emerge naturalmente)
- Grain con onset ok, coda che sfora (`PassthroughClipStrategy` iniettata in stream) → buffer esteso, grain non troncato (R7)
- Grain con onset fuori bounds (`PassthroughClipStrategy`) → buffer esteso, grain renderizzato correttamente (R7)
- Stream senza grain → buffer == `stream.duration * sr` (fallback R5)
- `stream.onset != 0`: extent calcolato con offset assoluto corretto

`render_merged_streams`:
- Grain tutti dentro bounds → buffer == `max(s.onset + s.duration) * sr` (invariato)
- Grain con coda che sfora in uno stream (`PassthroughClipStrategy`) → buffer esteso
- Tutti gli stream senza grain → fallback corretto

**Verification:**
- `pytest tests/rendering/test_numpy_audio_renderer.py` green

---

### U2. Rimozione CLAMP 2 e 3 in `_add_grain_at_position`

**Goal:** Rimuovere le guard che presuppongono responsabilità del renderer sui bounds.

**Requirements:** R3, R4

**Dependencies:** U1

**Files:**
- Modifica: `src/rendering/numpy_audio_renderer.py` (righe 233–241)
- Modifica: `tests/rendering/test_numpy_audio_renderer.py`

**Firma aggiornata** (rimuove `n_total` da tutti e tre i metodi privati):
```python
# _add_grain_at_position — rimuove n_total
def _add_grain_at_position(self, buffer, grain, onset_sample):
    ...

# _add_grain_relative — aggiorna call
self._add_grain_at_position(buffer, grain, onset_sample)

# _add_grain_absolute — aggiorna call
self._add_grain_at_position(buffer, grain, onset_sample)
```

**Test scenarios:**
- Grain con coda che sfora il vecchio `stream.duration` → overlap-add completo, nessun troncamento
- Grain con onset al boundary → renderizzato correttamente
- Grain con `grain_buffer` vuoto → nessun overlap-add (guard `shape[0] > 0` preservata)
- CLAMP 1 (onset < 0) ancora attivo: grain che inizia prima del buffer → taglia inizio correttamente

**Verification:**
- `pytest tests/rendering/test_numpy_audio_renderer.py` green
- `_add_grain_at_position` senza parametro `n_total`, senza rami `end_sample > n_total` e senza `onset_sample < n_total`

---

## System-Wide Impact

| Componente | Impatto |
|------------|---------|
| `numpy_audio_renderer.py` | Buffer sizing dinamico; CLAMP 2 e 3 rimossi |
| `stream.voices` / `stream.grains` | Invariati — fonte di verità gestita da piano 001 |
| ScoreWriter / Csound renderer | Invariati |
| Output STEMS con `OverflowMarginClipStrategy` | Invariato — buffer == `stream.duration` emerge naturalmente |
| Output STEMS con `PassthroughClipStrategy` | Può essere > `stream.duration` se grain sfondano — comportamento semanticamente corretto |
| Output MIX | Analogo |
| Cache (`StreamCacheManager`) | Fingerprint YAML invariato — nessun impatto |

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Test `test_output_duration_matches_stream` verifica `len(data)/sr ≈ stream.duration` | I grain di test hanno onset=0.0, duration=0.1, stream.duration=0.5 — tutti in-bounds → buffer == stream.duration naturale → test passa senza modifiche |
| Applicare piano 002 senza piano 001: grain out-of-bounds raggiungono il renderer | Comportamento definito: il renderer li renderizza integralmente. È la scelta corretta se si vuole il passthrough puro. Il rischio semantico (output più lungo del previsto) è responsabilità di chi non ha applicato piano 001. |
| Buffer overflow NumPy se `max_end_rel` negativo | Guard `max(1, int(...))` in U1; CLAMP 1 (onset < 0) in U2 gestisce onset negativi |
| Performance: iterazione grain per `max()` in hot path | O(N_grains) una tantum prima dell'allocazione — trascurabile |
| Troncamento float→int: `int(onset * sr) + int(duration * sr)` può essere < `int((onset + duration) * sr)` | `floor(a) + floor(b) <= floor(a+b)` → `end_sample <= n_total` sempre, nessun overflow. Assunzione: grain renderer produce esattamente `int(grain.duration * sr)` sample. Se il renderer usa resampling o arrotondamento diverso, `grain_len` può sforare di 1 sample → aggiungere test esplicito che `grain_len == int(grain.duration * sr)` nel grain renderer. |
