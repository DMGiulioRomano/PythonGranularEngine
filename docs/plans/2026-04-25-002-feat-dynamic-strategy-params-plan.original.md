---
title: "feat: Dynamic strategy parameters via Envelope evaluation per-grain"
type: feat
status: active
date: 2026-04-25
---

# feat: Dynamic strategy parameters via Envelope evaluation per-grain

## Overview

Attualmente i parametri delle voice strategies (pitch, onset, pointer, pan) sono valori scalari fissi calcolati una sola volta all'init di `VoiceManager`. Questo refactoring li rende dinamici: ogni parametro di una strategy può essere un `float` statico oppure un oggetto `Envelope`, valutato al tempo di onset di ciascun grain durante `generate_grains`.

---

## Problem Frame

Il sistema multi-voce pre-calcola gli offset di pitch/onset/pointer/pan per ogni voce all'`__init__` di `VoiceManager`. Questo approccio O(1) per grain era una scelta intenzionale di performance, ma impedisce qualsiasi evoluzione temporale degli offset. Un compositore non può, ad esempio, definire un pitch spread che si allarga nel tempo o un onset step che varia in base a un'inviluppo.

---

## Requirements Trace

- R1. Ogni parametro scalare di una strategy (es. `step`, `semitone_range`, `pointer_range`, `spread`) può accettare un `float` o un `Envelope`.
- R2. Il valore viene valutato al tempo di onset del grain corrente — non all'init e non una volta per stream.
- R3. Tutti i config YAML esistenti (valori scalari) restano validi senza modifiche.
- R4. L'invariante voce-0 (offset = 0.0 per tutte le dimensioni) è preservato indipendentemente da `time`.
- R5. Le strategy stochastiche preservano la direzione casuale per-voce fissa (seeded da `stream_id`), ma il range può variare nel tempo.
- R6. Il YAML supporta la sintassi envelope esistente per i parametri delle strategy.

---

## Scope Boundaries

- Non si aggiunge una nuova strategy: questo è un refactoring dell'infrastruttura esistente.
- `ChordPitchStrategy` e `SpectralPitchStrategy` non hanno parametri float time-varying — ricevono `time` ma lo ignorano.
- `time_mode: normalized` per i parametri delle strategy è supportato usando `stream.duration` al momento del parsing (già noto quando `_init_voice_manager` viene eseguito).
- Renderer Csound e NumPy non sono toccati.
- `Grain` rimane un frozen dataclass invariato.

---

## Context & Research

### Relevant Code and Patterns

- `src/controllers/voice_manager.py` — `VoiceManager._compute()` pre-calcola `voice_configs: List[VoiceConfig]`; `get_voice_config(voice_index: int)` restituisce offset cached
- `src/strategies/voice_pitch_strategy.py` — ABC `VoicePitchStrategy.get_pitch_offset(voice_index, num_voices) -> float`; pattern identico in onset/pointer/pan
- `src/strategies/voice_pan_strategy.py` — asimmetria già esistente: `spread` è passato al metodo, non al costruttore; precedente per iniettare parametri contestuali a call-time
- `src/parameters/parameter.py` — pattern `_evaluate_input(time)`: se valore è `Envelope` → `envelope.evaluate(time)`, else `float(value)`; da replicare nelle strategy
- `src/envelopes/envelope.py` — `Envelope.evaluate(time: float) -> float`; `create_scaled_envelope()` per `time_mode: normalized`
- `src/core/stream.py:145–241` — `_init_voice_manager`: parsing blocco `voices:`, costruzione factory kwargs, `pan_spread = float(kw.pop('spread', 0.0))`
- `src/core/stream.py:301–349` — `generate_grains`: loop per-voce con `voice_cursors[voice_index]` come tempo corrente `t`

### Institutional Learnings

- `VoiceManager._compute` è O(max_voices) upfront, O(1) in `generate_grains`: scelta consapevole. Il refactoring sposta il calcolo a O(1) per grain per voce — computazione triviale (aritmetica + evaluate envelope), costo accettabile.
- `StochasticPitchStrategy._cache: Dict[int, float]` memorizza il fattore random normalizzato per voce. Con range time-varying, il cache conserva il fattore normalizzato; il range viene risolto a call-time.
- Aggiungere elementi al tuple di `_get_module()` nei test richiede unpacking posizionale esplicito — evitare inserimenti in mezzo.
- Vincolo OCP delle strategy: le implementazioni concrete sono open for extension; modificare la firma ABC è breaking change gestito internamente (unico caller = `VoiceManager`).

---

## Key Technical Decisions

- **`time: float` obbligatorio nella firma ABC** (non default): tutti i caller interni vengono aggiornati in U3/U5; rende esplicito che ogni strategy è time-aware.
- **`_resolve_param` come funzione modulo-level condivisa** in `src/strategies/_strategy_utils.py`: più semplice di un mixin, facile da importare. Pattern: `isinstance(param, Envelope)` → `param.evaluate(time)`, else `float(param)`.
- **`VoiceManager` diventa stateless rispetto ai VoiceConfig**: rimuove `voice_configs: List[VoiceConfig]` e `_compute()`; `get_voice_config(voice_index, time)` calcola on-the-fly. `VoiceConfig` rimane frozen dataclass, ora ephemero per call.
- **`pan_spread: Union[float, Envelope]`** in `VoiceManager`: estratto come valore grezzo dal YAML (U4) e risolto con `_resolve_param` in `get_voice_config`.
- **Parsing YAML strategy kwargs**: funzione `_parse_strategy_kwarg(value, duration)` — detect list/dict → `Envelope`, else `float`. Riusa `create_scaled_envelope()` se `time_mode: normalized`.
- **Strategy stochastiche**: `_cache[voice_index]` conserva il fattore normalizzato `[-1, 1]`; `get_offset` moltiplica per `_resolve_param(self._range, time)`. Direzione per-voce fissa, magnitudine time-varying.

---

## Open Questions

### Resolved During Planning

- **`time` obbligatorio o opzionale nella firma ABC?** Obbligatorio — tutti i caller sono interni e vengono aggiornati; un default `time=0.0` nasconderebbe errori.
- **VoiceConfig cached o ephemero?** Ephemero — costo di ricalcolo triviale; cache richiederebbe invalidazione per tempo.
- **`spread` di pan: risolto da VoiceManager o passato alla strategy?** Risolto da VoiceManager (`_resolve_param(pan_spread, time)`) prima di passarlo a `get_pan_offset` — signature pan strategy rimane invariata tranne per `time`.

### Deferred to Implementation

- **Range di interpolazione per envelope su `step` onset/pointer**: verificare gestione valori negativi nei test di integrazione.
- **Interaction con `num_voices` time-varying**: voci saltate (indice >= active) non producono VoiceConfig — già gestito dal check `if voice_index < active` in `generate_grains`.

---

## High-Level Technical Design

> *Guida direzionale per la revisione, non specifica di implementazione. L'agente implementatore deve trattarlo come contesto, non come codice da riprodurre.*

**Flusso per-grain (dopo il refactoring):**

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

**Strategy stochastic con range time-varying:**

```
_cache[vi]  ← hash-seeded normalized factor, calcolato una volta
get_offset(vi, nv, t) → _cache[vi] * _resolve_param(self._range, t)
```

---

## Implementation Units

- [ ] U1. **Utility `_resolve_param` e type alias `StrategyParam`**

**Goal:** Fornire la primitiva condivisa per risolvere `Union[float, Envelope]` a un `float` al tempo `t`.

**Requirements:** R1, R2

**Dependencies:** None

**Files:**
- Create: `src/strategies/_strategy_utils.py`
- Test: `tests/strategies/test_strategy_utils.py`

**Approach:**
- `StrategyParam = Union[float, Envelope]` come type alias
- `_resolve_param(param: StrategyParam, time: float) -> float`: branch `isinstance(param, Envelope)` → `param.evaluate(time)`, else `float(param)`
- Nessuna altra logica in questo file

**Patterns to follow:**
- `src/parameters/parameter.py` metodo `_evaluate_input` per il pattern branch float/Envelope

**Test scenarios:**
- Happy path: `_resolve_param(2.5, 0.0)` → `2.5`
- Happy path envelope: `_resolve_param(Envelope([[0,0],[1,10]]), 0.5)` → `5.0` (interpolazione lineare)
- Edge case: `_resolve_param(0, 0.0)` → `0.0` (int convertito a float)
- Edge case envelope: `_resolve_param(Envelope([[0,0],[1,10]]), 0.0)` → `0.0`
- Edge case envelope: `_resolve_param(Envelope([[0,0],[1,10]]), 1.0)` → `10.0`

**Verification:**
- `test_strategy_utils.py` passa; nessun import circolare

---

- [ ] U2. **Estensione firma ABC e implementazioni concrete di tutte le strategy**

**Goal:** Aggiungere `time: float` alla firma di tutti i metodi `get_*_offset` (ABC + concrete); le strategy con parametri scalari accettano `StrategyParam`; le strategy stochastiche separano fattore normalizzato (cached) dalla scala (time-varying).

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
- ABC: `get_pitch_offset(self, voice_index: int, num_voices: int, time: float) -> float` (e analoghi)
- Strategy con parametri float (`step`, `semitone_range`, `pointer_range`, `base`): tipo diventa `StrategyParam`; corpo usa `_resolve_param(self._param, time)`
- `StochasticPitchStrategy`: `_cache[vi]` memorizza fattore normalizzato; `get_pitch_offset` restituisce `_cache[vi] * _resolve_param(self._semitone_range, time)`
- `ChordPitchStrategy`, `SpectralPitchStrategy`: ricevono `time` ma lo ignorano
- `VoicePanStrategy.get_pan_offset(vi, nv, spread, time)`: `spread` rimane passato da VoiceManager; pan strategies concrete ricevono `time`

**Execution note:** Test-first — aggiorna prima i test esistenti (rossi per firma errata), poi implementa la nuova firma.

**Patterns to follow:**
- `_resolve_param` da U1
- Pattern stochastic esistente: `hash(stream_id + str(vi))` come seed

**Test scenarios:**
- Happy path: `StepPitchStrategy(step=2.0).get_pitch_offset(1, 4, time=0.0)` → `2.0`
- Happy path envelope: `StepPitchStrategy(step=Envelope([[0,0],[1,12]])).get_pitch_offset(1, 4, time=0.5)` → `6.0`
- Invariante voce-0 statica: per tutte le strategy e qualsiasi `time`, `get_*_offset(0, nv, time)` → `0.0`
- Invariante voce-0 envelope: `StepPitchStrategy(Envelope([[0,0],[1,12]])).get_pitch_offset(0, 4, 0.5)` → `0.0`
- Stochastic range fisso: `get_pitch_offset(vi, nv, 0.0)` == `get_pitch_offset(vi, nv, 1.0)` se `semitone_range` è float
- Stochastic range envelope: `get_pitch_offset(1, 4, 0.0)` ≠ `get_pitch_offset(1, 4, 1.0)` se range varia
- Stochastic direction invariance: `sign(get_pitch_offset(1, 4, 0.0))` == `sign(get_pitch_offset(1, 4, 1.0))`
- Pan: `LinearPanStrategy().get_pan_offset(1, 4, spread=120.0, time=0.5)` == risultato attuale con `spread=120.0`

**Verification:**
- `make tests` verde; `TestVoiceZeroInvariant` passa su tutte le strategy con `time=0.0`

---

- [ ] U3. **Refactoring VoiceManager: rimuovere pre-computazione, aggiungere per-call dispatch**

**Goal:** `get_voice_config(voice_index, time)` calcola on-the-fly; rimuove `voice_configs: List[VoiceConfig]` e `_compute()`.

**Requirements:** R2, R4

**Dependencies:** U2

**Files:**
- Modify: `src/controllers/voice_manager.py`
- Test: test esistenti del voice manager o sezione dedicata nei test delle strategy

**Approach:**
- Rimuovi `self.voice_configs` e `_compute(voice_index)`
- Signature: `get_voice_config(self, voice_index: int, time: float) -> VoiceConfig`
- Corpo chiama `strategy.get_*_offset(vi, nv, time)` direttamente
- `self._pan_spread: Union[float, Envelope]` — risolto con `_resolve_param(self._pan_spread, time)` prima di passarlo a `get_pan_offset`
- `pan_spread` nel costruttore di `VoiceManager`: tipo `Union[float, Envelope]`
- `VoiceConfig` rimane frozen dataclass, ephemero per call

**Patterns to follow:**
- `_resolve_param` da U1

**Test scenarios:**
- Happy path: `VoiceManager(max_voices=4, pitch_strategy=StepPitchStrategy(2.0)).get_voice_config(1, 0.0).pitch_offset` → `2.0`
- Time-varying: `StepPitchStrategy(Envelope(...))` → `get_voice_config(1, 0.0).pitch_offset` ≠ `get_voice_config(1, 1.0).pitch_offset`
- Invariante voce-0: `get_voice_config(0, any_time).pitch_offset` → `0.0`
- pan_spread envelope: `VoiceManager(pan_strategy=LinearPanStrategy(), pan_spread=Envelope([[0,0],[1,120]]))` → pan_offset al tempo 0 < pan_offset al tempo 1 (voice > 0)
- Strategy None: tutti offset → `0.0` per qualsiasi `time`

**Verification:**
- `voice_configs` non più attributo pubblico; `get_voice_config` richiede `time`; `make tests` verde

---

- [ ] U4. **Parsing YAML strategy kwargs con supporto Envelope**

**Goal:** In `stream._init_voice_manager`, rilevare se un kwarg della strategy è valore envelope (lista o dict) e costruire l'oggetto `Envelope` prima di passarlo alla factory.

**Requirements:** R3, R6

**Dependencies:** U2, U3

**Files:**
- Modify: `src/core/stream.py` (metodo `_init_voice_manager`)
- Test: `tests/core/test_stream.py` o file integrazione esistente

**Approach:**
- Funzione helper `_parse_strategy_kwarg(value, duration) -> Union[float, Envelope]`:
  - `isinstance(value, (int, float))` → `float(value)`
  - `isinstance(value, list)` → `Envelope(value)` (tempo assoluto)
  - `isinstance(value, dict)` con `time_mode: normalized` → `create_scaled_envelope(value, duration)`
- Applicare a tutti i kwargs non-speciali (non `strategy`, non `stream_id`) prima di passarli alla factory
- `pan_spread`: stesso parsing — `_parse_strategy_kwarg(kw.pop('spread', 0.0), self.duration)`

**Patterns to follow:**
- `stream._init_voice_manager` righe 198–241
- `create_scaled_envelope()` in `src/envelopes/envelope.py`

**Test scenarios:**
- Happy path scalare: YAML `step: 2` → strategy riceve `step=2.0`; offset costante nel tempo
- Happy path envelope lista: YAML `step: [[0, 0], [1, 12]]` → strategy riceve `Envelope`; offset varia
- Happy path envelope dict normalizzato: YAML `step: {points: [[0,0],[1,12]], time_mode: normalized}` → envelope scalata su `stream.duration`
- Backward compat: tutti i config YAML esistenti in `configs/` parsano senza errori
- `pan_spread` envelope: `spread: [[0, 0], [1, 120]]` → VoiceManager riceve `Envelope` come `pan_spread`
- Strategy senza parametri float (Chord, Spectral): kwargs passati invariati

**Verification:**
- `make tests` verde; test integrazione con YAML envelope strategy produce grains con offset variabili

---

- [ ] U5. **Aggiornamento `generate_grains` per passare `t` a `get_voice_config`**

**Goal:** `generate_grains` passa il tempo corrente della voce a `VoiceManager.get_voice_config`.

**Requirements:** R2

**Dependencies:** U3

**Files:**
- Modify: `src/core/stream.py` (metodo `generate_grains`, riga ~329)
- Test: `tests/core/test_stream.py`

**Approach:**
- Una riga: `self._voice_manager.get_voice_config(voice_index)` → `self._voice_manager.get_voice_config(voice_index, t)`
- `t = voice_cursors[voice_index]` è già disponibile nel loop

**Test scenarios:**
- Integration: stream con `pitch.strategy: step, step: [[0,0],[1,12]]` e `num_voices: 4` → grains early hanno pitch_offset minore di grains late (stessa voce)
- Regression: stream con strategy scalari → output identico al comportamento pre-refactoring

**Verification:**
- `make tests` verde; `make e2e-tests` verde

---

## System-Wide Impact

- **Interaction graph:** Solo `VoiceManager` → strategy; solo `Stream.generate_grains` → `VoiceManager.get_voice_config`. Nessun renderer, nessun controller toccato.
- **Error propagation:** Se `Envelope` nella strategy riceve `t` fuori range, comportamento = `Envelope.evaluate` (clamp o extrapolation — verificare in U2).
- **State lifecycle risks:** `StochasticPitchStrategy._cache` non è invalidato tra run dello stesso stream — già il caso attuale; fattore normalizzato rimane stabile.
- **API surface parity:** `get_voice_config(voice_index)` senza `time` non funziona più — breaking change interno a `stream.py`. Nessuna API pubblica esposta.
- **Integration coverage:** Test in U5 è il case critico: verifica che envelope sia valutata per-grain, non una volta per stream.
- **Unchanged invariants:** `VoiceConfig` resta frozen dataclass. `Grain` invariato. Factory e registry delle strategy non cambiano.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Rottura test esistenti per cambio firma ABC | U2 aggiorna test prima dell'impl (test-first); tutti i test passano `time=0.0` come baseline |
| Performance regression con envelope evaluate per ogni grain | Costo O(1) per evaluate (lookup segment + interpolazione); misurare solo se problemi su >8 voci e durata >60s |
| `pan_spread` Envelope non scalata correttamente con `time_mode: normalized` | Test esplicito in U4 con `create_scaled_envelope`; verificare che `duration` sia disponibile al parsing |
| Stochastic direction invariance rotta se `_cache` refactored erroneamente | Test scenario esplicito in U2: stesso segno di offset per `time=0` e `time=1` |

---

## Documentation / Operational Notes

- `docs/yaml-reference.md` sezione `voices`: aggiungere sintassi envelope per parametri strategy dopo merge.
- `docs/multi-voice.md`: aggiornare descrizione delle strategy con nota su supporto envelope.

---

## Sources & References

- Related code: `src/controllers/voice_manager.py`, `src/strategies/`, `src/core/stream.py:145–241`, `src/parameters/parameter.py`
- Related plan: `docs/plans/2026-04-25-001-feat-spectral-pitch-strategy-plan.md`
- Architecture: `docs/multi-voice.md`, `docs/ARCHITECTURE.md`
