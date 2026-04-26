---
title: "feat: Dynamic strategy parameters via Envelope evaluation per-grain"
type: feat
status: active
date: 2026-04-25
---

# feat: Dynamic strategy parameters via Envelope evaluation per-grain

## Overview

Voice strategy params (pitch, onset, pointer, pan) currently scalar — computed once at `VoiceManager` init. Refactoring makes dynamic: each param can be `float` or `Envelope`, evaluated at grain onset time during `generate_grains`.

---

## Problem Frame

Multi-voice system pre-computes pitch/onset/pointer/pan offsets per voice at `VoiceManager.__init__`. O(1) per grain — intentional perf choice — but blocks any temporal evolution. Composer can't define pitch spread that widens over time or onset step driven by envelope.

---

## Requirements Trace

- R1. Each scalar param of strategy (e.g. `step`, `semitone_range`, `pointer_range`, `spread`) accepts `float` or `Envelope`.
- R2. Value evaluated at onset time of current grain — not at init, not once per stream.
- R3. All existing YAML configs (scalar values) remain valid without changes.
- R4. Voice-0 invariant (offset = 0.0 all dimensions) preserved regardless of `time`.
- R5. Stochastic strategies preserve fixed per-voice direction (seeded from `stream_id`); range can vary over time.
- R6. YAML supports existing envelope syntax for strategy params.

---

## Scope Boundaries

- No new strategy added — infrastructure refactoring only.
- `ChordPitchStrategy` and `SpectralPitchStrategy` have no time-varying float params — receive `time` but ignore it.
- `time_mode: normalized` for strategy params supported using `stream.duration` at parse time (known when `_init_voice_manager` runs).
- Csound and NumPy renderers untouched.
- `Grain` stays frozen dataclass, unchanged.

---

## Context & Research

### Relevant Code and Patterns

- `src/controllers/voice_manager.py` — `VoiceManager._compute()` pre-computes `voice_configs: List[VoiceConfig]`; `get_voice_config(voice_index: int)` returns cached offsets
- `src/strategies/voice_pitch_strategy.py` — ABC `VoicePitchStrategy.get_pitch_offset(voice_index, num_voices) -> float`; same pattern in onset/pointer/pan
- `src/strategies/voice_pan_strategy.py` — asymmetry already exists: `spread` passed to method, not constructor; precedent for injecting contextual params at call-time
- `src/parameters/parameter.py` — `_evaluate_input(time)` pattern: if value is `Envelope` → `envelope.evaluate(time)`, else `float(value)`; replicate in strategies
- `src/envelopes/envelope.py` — `Envelope.evaluate(time: float) -> float`; `create_scaled_envelope()` for `time_mode: normalized`
- `src/core/stream.py:145–241` — `_init_voice_manager`: parses `voices:` block, builds factory kwargs, `pan_spread = float(kw.pop('spread', 0.0))`
- `src/core/stream.py:301–349` — `generate_grains`: per-voice loop with `voice_cursors[voice_index]` as current time `t`

### Institutional Learnings

- `VoiceManager._compute` is O(max_voices) upfront, O(1) in `generate_grains`: deliberate choice. Refactoring shifts to O(1) per grain per voice — trivial compute (arithmetic + envelope evaluate), acceptable cost.
- `StochasticPitchStrategy._cache: Dict[int, float]` stores normalized random factor per voice. With time-varying range, cache keeps normalized factor; range resolved at call-time.
- Adding elements to `_get_module()` tuple in tests requires explicit positional unpacking — avoid mid-tuple insertions.
- OCP constraint on strategies: concrete impls open for extension; modifying ABC signature is breaking change managed internally (single caller = `VoiceManager`).

---

## Key Technical Decisions

- **`time: float` required in ABC signature** (no default): all internal callers updated in U3/U5; makes explicit every strategy is time-aware.
- **`_resolve_param` as module-level shared function** in `src/parameters/parameter.py`: zero nuove dipendenze — `parameters/` già importa `Envelope`; `shared/` resta senza dipendenze domain. Pattern: `isinstance(param, Envelope)` → `param.evaluate(time)`, else `float(param)`. Nessun file `_strategy_utils.py`.
- **`VoiceManager` becomes stateless re VoiceConfigs**: removes `voice_configs: List[VoiceConfig]` and `_compute()`; `get_voice_config(voice_index, time)` computes on-the-fly. `VoiceConfig` stays frozen dataclass, now ephemeral per call.
- **`pan_spread: Union[float, Envelope]`** in `VoiceManager`: extracted raw from YAML (U4), resolved with `_resolve_param` in `get_voice_config`.
- **YAML strategy kwargs parsing**: function `_parse_strategy_kwarg(value, duration)` — detect list/dict → `Envelope`, else `float`. Reuses `create_scaled_envelope()` if `time_mode: normalized`.
- **Stochastic strategies**: `_cache[voice_index]` stores normalized factor `[-1, 1]`; `get_offset` multiplies by `_resolve_param(self._range, time)`. Per-voice direction fixed, magnitude time-varying.

---

## Open Questions

### Resolved During Planning

- **`time` required or optional in ABC?** Required — all callers internal and updated; `time=0.0` default would hide errors.
- **VoiceConfig cached or ephemeral?** Ephemeral — recompute cost trivial; cache would need time-based invalidation.
- **`pan_spread`: resolved by VoiceManager or passed to strategy?** Resolved by VoiceManager (`_resolve_param(pan_spread, time)`) before passing to `get_pan_offset` — pan strategy signature unchanged except for `time`.

### Deferred to Implementation

- **Interpolation range for envelope on onset/pointer `step`**: verify negative value handling in integration tests.
- **Interaction with time-varying `num_voices`**: skipped voices (index >= active) produce no VoiceConfig — already handled by `if voice_index < active` check in `generate_grains`.

### Da ce-doc-review (2026-04-25)

**P1 — risolti nel piano**

- [P1, ✓ risolto in U2] **RandomPanStrategy stability:** aggiunta cache per-voce seeded in `RandomPanStrategy` (vedi U2 Approach).

- [P1, ✓ risolto in U2] **`StochasticPitchStrategy` guard:** guard riscritto con `_resolve_param` prima del check (vedi U2 Approach).

- [P1, ✓ risolto in U4] **`_parse_strategy_kwarg` ramo `str`:** aggiunto primo branch `isinstance(value, str) → return value` (vedi U4 Approach).

- [P1, ✓ risolto in U3] **Voice-0 invariant site:** guard lasciato ai strategy, non a VoiceManager (vedi U3 Approach).

**P2 — da valutare**

- [P2, ✓ risolto in U1] **`_resolve_param` duplica `_evaluate_input` da `parameter.py`:** `resolve_param` implementata come funzione module-level in `src/parameters/parameter.py` (non in `_strategy_utils.py`). `Parameter._evaluate_input` diventa delegato. Strategy importa da `parameters.parameter`. Zero nuove dipendenze — `parameters/` già importa `Envelope`; `shared/` resta senza dipendenze domain.

- [P2, ✓ risolto in U4] **`_parse_strategy_kwarg` reimplementa detection già in `Envelope.is_envelope_like()`:** `_parse_strategy_kwarg` usa `Envelope.is_envelope_like(value)` come branch condition invece di `isinstance(value, list/dict)`. Copre compact format e dict con `points` senza `time_mode`. OCP: nuovi formati aggiunti a `is_envelope_like` propagano automaticamente.

- [P2, ✓ risolto in U4] **`time_mode: normalized` — ordine inizializzazione verificato:** `_init_stream_context` (step 4) setta `self.duration` via `setattr` su tutti i field di `StreamContext`; `_init_voice_manager` è step 7. Garanzia strutturale — nessuna guardia runtime necessaria. Documentato in U4 Approach.

- [P2, ✓ risolto in U5] **Tempo per-voce vs globale — conseguenza musicale documentata:** U5 passa `voice_cursors[voice_index]`. Con `num_voices > 1`, voci diverse valutano envelope in momenti diversi simultaneamente — scelta intenzionale. Voce con onset più tardo ha posizione temporale più avanzata → envelope più avanzato fin dal primo grain. Documentato in U5 Approach. Edge case onset_offset grande (grain oltre duration) deferred a issue separata — divergenza renderer pre-esistente, fuori scope piano.

---

## High-Level Technical Design

> *Directional guide for review, not implementation spec. Implementing agent treats as context, not code to reproduce.*

**Per-grain flow (post-refactoring):**

```
generate_grains(t)
  └─ voice_manager.get_voice_config(voice_index, t)
       ├─ pitch_offset   = pitch_strategy.get_pitch_offset(vi, nv, t)
       │    └─ _resolve_param(self._step, t)   # float o Envelope.evaluate(t)
       ├─ onset_offset   = onset_strategy.get_onset_offset(vi, nv, t)
       ├─ pointer_offset = pointer_strategy.get_pointer_offset(vi, nv, t)
       └─ pan_offset     = pan_strategy.get_pan_offset(
                               vi, nv,
                               spread=_resolve_param(pan_spread, t), t)
            └─ VoiceConfig(pitch_offset, onset_offset, pointer_offset, pan_offset)
```

**Stochastic strategy with time-varying range:**

```
_cache[vi]  ← hash-seeded normalized factor, calcolato una volta
get_offset(vi, nv, t) → _cache[vi] * _resolve_param(self._range, t)
```

---

## Implementation Units

- [x] U1. **Utility `_resolve_param` e type alias `StrategyParam`**

**Goal:** Shared primitive to resolve `Union[float, Envelope]` to `float` at time `t`.

**Requirements:** R1, R2

**Dependencies:** None

**Files:**
- Modify: `src/parameters/parameter.py` (aggiunge `resolve_param` come funzione module-level; `_evaluate_input` diventa delegato)
- Test: `tests/parameters/test_parameter.py` (nuova classe `TestResolveParam`)

**Approach:**
- `StrategyParam = Union[float, Envelope]` as type alias (definito in `parameters/parameter.py`)
- `resolve_param(param: StrategyParam, time: float) -> float`: branch `isinstance(param, Envelope)` → `param.evaluate(time)`, else `float(param)`. `None` → `0.0`.
- `Parameter._evaluate_input` diventa: `return resolve_param(self._value, time)`
- Strategy importa: `from parameters.parameter import resolve_param, StrategyParam`
- Nessun file `_strategy_utils.py` — `parameters/` già importa `Envelope`; `shared/` resta senza dipendenze domain

**Patterns to follow:**
- `src/parameters/parameter.py` method `_evaluate_input` — logica da estrarre, non duplicare

**Test scenarios:**
- Happy path: `resolve_param(2.5, 0.0)` → `2.5`
- Happy path envelope: `resolve_param(Envelope([[0,0],[1,10]]), 0.5)` → `5.0` (linear interpolation)
- Edge case: `resolve_param(0, 0.0)` → `0.0` (int cast to float)
- Edge case None: `resolve_param(None, 0.0)` → `0.0`
- Edge case envelope: `resolve_param(Envelope([[0,0],[1,10]]), 0.0)` → `0.0`
- Edge case envelope: `resolve_param(Envelope([[0,0],[1,10]]), 1.0)` → `10.0`
- Regressione: `Parameter._evaluate_input` delega correttamente (stesso risultato di `resolve_param`)

**Verification:**
- `tests/parameters/test_parameter.py` passes; no circular imports; `_strategy_utils.py` non creato

---

- [x] U2. **ABC signature extension and all concrete strategy implementations**

**Goal:** Add `time: float` to all `get_*_offset` method signatures (ABC + concrete); strategies with scalar params accept `StrategyParam`; stochastic strategies separate normalized factor (cached) from scale (time-varying).

**Requirements:** R1, R2, R4, R5

**Dependencies:** U1

**Files:**
- Modify: `src/strategies/voice_pitch_strategy.py`
- Modify: `src/strategies/voice_onset_strategy.py`
- Modify: `src/strategies/voice_pointer_strategy.py`
- Modify: `src/strategies/voice_pan_strategy.py`
- Test: `tests/strategies/test_voice_pitch_strategy.py`
- Test: `tests/strategies/test_voice_onset_strategy.py`
- Test: `tests/strategies/test_voice_pointer_strategy.py`
- Test: `tests/strategies/test_voice_pan_strategy.py`

**Approach:**
- ABC: `get_pitch_offset(self, voice_index: int, num_voices: int, time: float) -> float` (and analogues)
- Float-param strategies (`step`, `semitone_range`, `pointer_range`, `base`): type becomes `StrategyParam`; body uses `_resolve_param(self._param, time)`
- `StochasticPitchStrategy`: `_cache[vi]` stores normalized factor; `get_pitch_offset` body:
  ```python
  resolved = _resolve_param(self._semitone_range, time)
  if voice_index == 0 or resolved == 0.0:
      return 0.0
  return self._cache[voice_index] * resolved
  ```
- `ChordPitchStrategy`, `SpectralPitchStrategy`: receive `time`, ignore it
- `VoicePanStrategy.get_pan_offset(vi, nv, spread, time)`: `spread` still passed by VoiceManager; concrete pan strategies receive `time`
- `RandomPanStrategy`: add per-voice seeded cache `_cache: Dict[int, float]`; seed `hash(stream_id + str(voice_index))` per generare valore fisso `[-1, 1]` per voce; primo accesso popola, successivi restituiscono valore cached. `stream_id` passato al costruttore (stesso pattern `StochasticPitchStrategy`).

**Execution note:** Test-first — update existing tests first (red for wrong signature), then implement new signature.

**Patterns to follow:**
- `_resolve_param` from U1
- Existing stochastic pattern: `hash(stream_id + str(vi))` as seed

**Test scenarios:**
- Happy path: `StepPitchStrategy(step=2.0).get_pitch_offset(1, 4, time=0.0)` → `2.0`
- Happy path envelope: `StepPitchStrategy(step=Envelope([[0,0],[1,12]])).get_pitch_offset(1, 4, time=0.5)` → `6.0`
- Voice-0 invariant static: all strategies, any `time`, `get_*_offset(0, nv, time)` → `0.0`
- Voice-0 invariant envelope: `StepPitchStrategy(Envelope([[0,0],[1,12]])).get_pitch_offset(0, 4, 0.5)` → `0.0`
- Stochastic fixed range: `get_pitch_offset(vi, nv, 0.0)` == `get_pitch_offset(vi, nv, 1.0)` if `semitone_range` is float
- Stochastic envelope range: `get_pitch_offset(1, 4, 0.0)` ≠ `get_pitch_offset(1, 4, 1.0)` if range varies
- Stochastic direction invariance: `sign(get_pitch_offset(1, 4, 0.0))` == `sign(get_pitch_offset(1, 4, 1.0))`
- Pan: `LinearPanStrategy().get_pan_offset(1, 4, spread=120.0, time=0.5)` == current result with `spread=120.0`

**Verification:**
- `make tests` green; `TestVoiceZeroInvariant` passes on all strategies with `time=0.0`

---

- [x] U3. **VoiceManager refactoring: remove pre-computation, add per-call dispatch**

**Goal:** `get_voice_config(voice_index, time)` computes on-the-fly; remove `voice_configs: List[VoiceConfig]` and `_compute()`.

**Requirements:** R2, R4

**Dependencies:** U2

**Files:**
- Modify: `src/controllers/voice_manager.py`
- Modify: `src/core/stream.py` (riga 329: `get_voice_config(voice_index, t)` — anticipato da U5 per mantenere `make tests` green)
- Modify: `src/strategies/voice_pan_strategy.py` (guard voice_index==0 in `LinearPanStrategy` e `AdditivePanStrategy` — gap U2 rilevato durante U3)
- Test: `tests/controllers/test_voice_manager.py` (riscritta: sezione 7 rimpiazza TestPrecomputedConfigs, aggiunta sezione 8 TestVoiceManagerTimeVarying)
- Test: `tests/strategies/test_voice_pan_strategy.py` (aggiornati valori voice_index=0, aggiunta TestVoiceZeroInvariant per linear/additive)
- Test: `tests/core/test_stream_voices_yaml.py` (tutte le chiamate `get_voice_config(i)` → `get_voice_config(i, 0.0)`)

**Approach:**
- Remove `self.voice_configs` e `_compute(voice_index)`
- Signature: `get_voice_config(self, voice_index: int, time: float) -> VoiceConfig`
- Body calls `strategy.get_*_offset(vi, nv, time)` directly
- **Voice-0 invariant:** garantito dalle strategy. Gap U2: `LinearPanStrategy` e `AdditivePanStrategy` non avevano guard voice_index==0 — aggiunto in questa unit. I test pan aggiornati di conseguenza.
- `self._pan_spread: Union[float, Envelope]` — resolved with `_resolve_param(self._pan_spread, time)` before passing to `get_pan_offset`
- `pan_spread` in `VoiceManager` constructor: type `Union[float, Envelope]`
- `VoiceConfig` stays frozen dataclass, ephemeral per call
- **stream.py anticipato:** `generate_grains` già aggiornato (`get_voice_config(voice_index, t)`) per non rompere la suite. U5 rimane aperto per la documentazione del comportamento musicale per-voce.

**Patterns to follow:**
- `_resolve_param` from U1

**Test scenarios:**
- Happy path: `VoiceManager(max_voices=4, pitch_strategy=StepPitchStrategy(2.0)).get_voice_config(1, 0.0).pitch_offset` → `2.0`
- Time-varying: `StepPitchStrategy(Envelope(...))` → `get_voice_config(1, 0.0).pitch_offset` ≠ `get_voice_config(1, 1.0).pitch_offset`
- Voice-0 invariant: `get_voice_config(0, any_time).pitch_offset` → `0.0`
- pan_spread envelope: `VoiceManager(pan_strategy=LinearPanStrategy(), pan_spread=Envelope([[0,0],[1,120]]))` → pan_offset at time 0 < pan_offset at time 1 (voice > 0)
- Strategy None: all offsets → `0.0` for any `time`

**Verification:**
- `voice_configs` no longer public attribute; `get_voice_config` requires `time`; `make tests` green

---

- [ ] U4. **YAML strategy kwargs parsing with Envelope support**

**Goal:** In `stream._init_voice_manager`, detect if strategy kwarg is envelope value (list or dict) and build `Envelope` object before passing to factory.

**Requirements:** R3, R6

**Dependencies:** U2, U3

**Files:**
- Modify: `src/core/stream.py` (method `_init_voice_manager`)
- Test: `tests/core/test_stream.py` or existing integration file

**Approach:**
- Helper function `_parse_strategy_kwarg(value, duration) -> Union[float, Envelope, str]`:
  - `isinstance(value, str)` → `return value` (chord name e simili — non convertire)
  - `isinstance(value, (int, float))` → `float(value)`
  - `Envelope.is_envelope_like(value)` → se `dict` con `time_mode: normalized`: `create_scaled_envelope(value, duration)`; altrimenti `Envelope(value)`. Copre list, compact format, dict con `points`.
- Apply to all non-special kwargs (not `strategy`, not `stream_id`) before passing to factory
- `pan_spread`: same parsing — `_parse_strategy_kwarg(kw.pop('spread', 0.0), self.duration)`
- **`self.duration` disponibile:** `_init_stream_context` (step 4 in `__init__`) setta tutti i field di `StreamContext` — incluso `duration: float` — come attributi `self` via `setattr`. `_init_voice_manager` è step 7. Nessuna guardia necessaria: l'ordine è garantito dalla sequenza in `__init__`.

**Patterns to follow:**
- `stream._init_voice_manager` lines 198–241
- `create_scaled_envelope()` in `src/envelopes/envelope.py`

**Test scenarios:**
- Happy path scalar: YAML `step: 2` → strategy receives `step=2.0`; offset constant over time
- Happy path list envelope: YAML `step: [[0, 0], [1, 12]]` → strategy receives `Envelope`; offset varies
- Happy path normalized dict envelope: YAML `step: {points: [[0,0],[1,12]], time_mode: normalized}` → envelope scaled to `stream.duration`
- Backward compat: all existing YAML configs in `configs/` parse without errors
- `pan_spread` envelope: `spread: [[0, 0], [1, 120]]` → VoiceManager receives `Envelope` as `pan_spread`
- Strategies without float params (Chord, Spectral): kwargs passed unchanged

**Verification:**
- `make tests` green; integration test with YAML envelope strategy produces grains with varying offsets

---

- [ ] U5. **Update `generate_grains` to pass `t` to `get_voice_config`**

**Goal:** `generate_grains` passes current voice time to `VoiceManager.get_voice_config`.

**Requirements:** R2

**Dependencies:** U3

**Files:**
- Modify: `src/core/stream.py` (method `generate_grains`, line ~329)
- Test: `tests/core/test_stream.py`

**Approach:**
- One line: `self._voice_manager.get_voice_config(voice_index)` → `self._voice_manager.get_voice_config(voice_index, t)`
- `t = voice_cursors[voice_index]` already available in loop
- **Tempo per-voce — scelta intenzionale:** `voice_cursors[voice_index]` rappresenta il tempo musicale reale di quella voce. Con `num_voices > 1`, voci con onset offset diversi si trovano in posizioni temporali diverse durante lo stesso ciclo di rendering → valutano l'envelope in momenti diversi simultaneamente. Conseguenza musicale: una voce con onset più tardo ha già un envelope più avanzato fin dal suo primo grain. Questo è il comportamento corretto — rispecchia la posizione temporale effettiva di ciascuna voce. L'alternativa (global `t`) eliminerebbe questo senso di posizione e renderebbe l'envelope indipendente dall'offset per-voce.
- **Edge case deferred — onset_offset envelope con valori grandi:** se `onset_offset` è envelope con valori che si avvicinano a `stream.duration`, grain finali di voci N>0 possono avere `onset > stream_onset + duration`. Comportamento diverge tra renderer: NumPy li ignora silenziosamente (guard `onset_sample < n_total`); Csound li scrive nel `.sco` e l'output audio si estende oltre la durata prevista. Questo è comportamento pre-esistente (stesso con offset statico grande) — non introdotto da questa refactoring. Tracking separato: issue #27.

**Test scenarios:**
- Integration: stream with `pitch.strategy: step, step: [[0,0],[1,12]]` and `num_voices: 4` → early grains have smaller pitch_offset than late grains (same voice)
- Regression: stream with scalar strategies → output identical to pre-refactoring behavior

**Verification:**
- `make tests` green; `make e2e-tests` green

---

## System-Wide Impact

- **Interaction graph:** Only `VoiceManager` → strategies; only `Stream.generate_grains` → `VoiceManager.get_voice_config`. No renderers, no controllers touched.
- **Error propagation:** If `Envelope` in strategy receives `t` out of range, behavior = `Envelope.evaluate` (clamp or extrapolation — verify in U2).
- **State lifecycle risks:** `StochasticPitchStrategy._cache` not invalidated between runs of same stream — already current behavior; normalized factor stays stable.
- **API surface parity:** `get_voice_config(voice_index)` without `time` no longer works — internal breaking change to `stream.py`. No public API exposed.
- **Integration coverage:** Test in U5 is critical case: verifies envelope evaluated per-grain, not once per stream.
- **Unchanged invariants:** `VoiceConfig` stays frozen dataclass. `Grain` unchanged. Strategy factory and registry unchanged.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Existing tests break on ABC signature change | U2 updates tests before impl (test-first); all tests pass `time=0.0` as baseline |
| Performance regression with per-grain envelope evaluate | O(1) cost per evaluate (segment lookup + interpolation); measure only if issues on >8 voices and duration >60s |
| `pan_spread` Envelope not scaled correctly with `time_mode: normalized` | Explicit test in U4 with `create_scaled_envelope`; verify `duration` available at parse time |
| Stochastic direction invariance broken if `_cache` refactored incorrectly | Explicit test scenario in U2: same sign of offset for `time=0` and `time=1` |

---

## Documentation / Operational Notes

- `docs/yaml-reference.md` `voices:` section: add envelope syntax for strategy params after merge.
- `docs/multi-voice.md`: update strategy description with note on envelope support.

---

## Sources & References

- Related code: `src/controllers/voice_manager.py`, `src/strategies/`, `src/core/stream.py:145–241`, `src/parameters/parameter.py`
- Related plan: `docs/plans/2026-04-25-001-feat-spectral-pitch-strategy-plan.md`
- Architecture: `docs/multi-voice.md`, `docs/ARCHITECTURE.md`