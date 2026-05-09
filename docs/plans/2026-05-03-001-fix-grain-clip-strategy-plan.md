---
title: "fix: GrainClipStrategy — controllo dichiarativo dei grain out-of-bounds (issue #27)"
type: fix
status: active
date: 2026-05-03
---

# fix: GrainClipStrategy — controllo dichiarativo dei grain out-of-bounds

## Overview

Quando `onset_offset` di una voce spinge l'onset di un grain oltre `stream.onset + stream.duration`, il comportamento dipende dal renderer. La fix introduce `GrainClipStrategy` — applicata in post-process dentro `generate_grains` — che rende `stream.voices` la **unica fonte di verità** su quali grain esistono. Il renderer non ha più opinioni proprie sui bounds: si limita a renderizzare fedelmente ciò che riceve.

---

## Vincolo architetturale

**Il renderer è un passthrough puro.** Non filtra, non tronca, non ha logica sui bounds. L'unica superficie di controllo per decidere quali grain esistono è `GrainClipStrategy`. Il comportamento del renderer (durata buffer, campioni scritti) emerge da `stream.voices` — non da parametri indipendenti nel renderer.

Conseguenza diretta: la guard `onset_sample < n_total` in `numpy_audio_renderer.py:240` e il troncamento coda (righe 234–237) **devono essere rimossi** — piano 002. Lasciarli sarebbe una seconda superficie di controllo ortogonale alla strategy.

---

## Problem Frame

`stream.voices` contiene attualmente grain non validati — il filtro avviene (parzialmente, solo per onset) a livello renderer NumPy. Questo significa:

- Renderer NumPy e Csound ricevono grain diversi per lo stesso stream → divergenza output
- Il renderer ha conoscenza dei bounds dello stream — accoppiamento indesiderato
- Aggiungere una nuova strategy (es. `FadeMarginClipStrategy`) richiederebbe modificare anche il renderer

Radice: responsabilità di filtraggio nel posto sbagliato (renderer invece di modello).

---

## Requirements Trace

- R1. Grain con `onset >= stream.onset + stream.duration` non entrano mai in `stream.voices`.
- R2. Grain con `onset < stream_end` ma `onset + grain.duration > stream_end + margin` sono esclusi (margin default = 0.0).
- R3. La strategia di clipping è pluggabile via Strategy pattern — OCP: nuove strategie senza toccare Stream o i renderer.
- R4. Default: `OverflowMarginClipStrategy(margin=0.0)` — nessuna coda può sforare.
- R5. `PassthroughClipStrategy` lascia passare tutti i grain — il renderer li riceve e li renderizza integralmente (richiede piano 002 per buffer corretto).
- R6. NumPy e Csound ricevono le stesse `stream.voices` → parità garantita strutturalmente.
- R7. Il parametro `margin` è predisposto per futura configurazione YAML per-stream (fuori scope di questo piano).
- R8. Tutti i test esistenti restano verdi senza modifiche.

---

## Scope Boundaries

- Nessuna modifica a NumPy renderer, Csound renderer, ScoreWriter — quelli sono piano 002.
- Nessuna nuova sintassi YAML in questo piano — `margin` è hardcoded a `0.0`.
- `Grain` rimane frozen dataclass, invariato.
- `_create_grain` rimane invariato — il filtro è post-process, non inline nel loop.
- Csound: nessun troncamento della durata del grain (il grain è escluso o incluso intero).

---

## Context & Research

### Codice rilevante

- `src/core/stream.py:307–366` — `generate_grains`: loop cursor-based; assegna `self.voices` e `self.grains` dopo il loop. Il post-process si inserisce tra fine loop (riga 359) e assegnazione (righe 359–363).
- `src/core/grain.py:9–10` — `Grain` ha `onset: float` e `duration: float` come campi frozen dataclass.
- `src/core/stream.py:410` — `absolute_onset = self.onset + elapsed_time + voice_config.onset_offset` — il grain conosce già l'onset assoluto quando viene creato.
- `src/strategies/voice_pitch_strategy.py` — pattern ABC + registry + factory da replicare per `GrainClipStrategy`.
- `src/rendering/numpy_audio_renderer.py:234–241` — guard e troncamento che diventano obsoleti dopo piano 002 (buffer dinamico + passthrough).

### Decisioni architetturali

- **Post-process, non inline**: il loop `generate_grains` gestisce avanzamento cursore temporale — responsabilità singola. Il clipping è responsabilità separata, applicata dopo che tutti i grain sono stati generati. SRP e OCP entrambi rispettati.
- **Condition: onset + coda**: `grain.onset < stream_end AND grain.onset + grain.duration <= stream_end + margin`. Con `margin=0.0`: il grain deve essere completamente contenuto nello stream.
- **`PassthroughClipStrategy` è una scelta semantica**: lasciare passare grain che sforano non è un "opt-out di sicurezza" — è una scelta esplicita che il renderer deve onorare renderizzando completamente quei grain. Richiede piano 002.
- **Stream tiene il riferimento alla strategy**: `self._clip_strategy: GrainClipStrategy` — inizializzata a `OverflowMarginClipStrategy(margin=0.0)` in `__init__`.
- **`stream_end` = `stream.onset + stream.duration`**: onset assoluto — coerente con `absolute_onset` in `_create_grain`.

---

## High-Level Technical Design

```
generate_grains()
  └─ [loop esistente, invariato]
       └─ all_voice_grains[voice_index].append(grain)

  └─ [POST-PROCESS — nuovo]
       └─ self._clip_strategy.apply(all_voice_grains, stream=self)
            └─ OverflowMarginClipStrategy(margin=0.0)  [default]
                 stream_end = stream.onset + stream.duration
                 grain valido iff:
                   grain.onset < stream_end
                   AND grain.onset + grain.duration <= stream_end + margin

            └─ PassthroughClipStrategy  [opt-in esplicito]
                 tutti i grain passano → renderer li riceve e li renderizza integralmente

  └─ self.voices = filtered_voice_grains  ← unica fonte di verità
  └─ self.grains = flatten + sort
```

Il renderer (piano 002) riceve `stream.voices` e alloca buffer su `max(g.onset + g.duration)` sui grain ricevuti — senza logica di bounds propria.

---

## Implementation Units

---

### U1. `GrainClipStrategy` — ABC + implementazioni + registry + factory

**Goal:** Definire l'interfaccia pluggabile e le due implementazioni concrete iniziali.

**Requirements:** R1, R2, R3, R4, R5

**Dependencies:** None

**Files:**
- Crea: `src/strategies/grain_clip_strategy.py`
- Crea: `tests/strategies/test_grain_clip_strategy.py`

**Approach:**

```python
# src/strategies/grain_clip_strategy.py

class GrainClipStrategy(ABC):
    @abstractmethod
    def apply(self, voices: List[List[Grain]], stream) -> List[List[Grain]]:
        """Filtra grain invalidi da ogni voice. Restituisce nuova struttura."""
        ...

class OverflowMarginClipStrategy(GrainClipStrategy):
    """Esclude grain la cui coda sfora stream_end + margin."""
    def __init__(self, margin: float = 0.0):
        self.margin = margin

    def apply(self, voices, stream):
        stream_end = stream.onset + stream.duration
        limit = stream_end + self.margin
        return [
            [g for g in voice if g.onset < stream_end and g.onset + g.duration <= limit]
            for voice in voices
        ]

class PassthroughClipStrategy(GrainClipStrategy):
    """Nessun filtro — tutti i grain passano al renderer che li renderizza integralmente."""
    def apply(self, voices, stream):
        return voices

GRAIN_CLIP_STRATEGIES = {
    'overflow_margin': OverflowMarginClipStrategy,
    'passthrough': PassthroughClipStrategy,
}

class GrainClipStrategyFactory:
    @staticmethod
    def create(name: str, **kwargs) -> GrainClipStrategy:
        if name not in GRAIN_CLIP_STRATEGIES:
            raise ValueError(f"GrainClipStrategy sconosciuta: '{name}'")
        return GRAIN_CLIP_STRATEGIES[name](**kwargs)
```

**Test scenarios (`test_grain_clip_strategy.py`):**

`OverflowMarginClipStrategy.apply`:
- Grain completamente dentro stream → incluso
- Grain con onset >= stream_end → escluso (R1)
- Grain con onset < stream_end ma coda sfora con margin=0 → escluso (R2)
- Grain con onset < stream_end e coda sfora ma dentro margin=0.5 → incluso
- Grain con onset == stream_end - ε → incluso
- Grain con onset == stream_end → escluso (strict `<`)
- Grain con onset + duration == stream_end → incluso (`<=` su limit)
- Voice vuota → restituita vuota
- Tutte le voice filtrate correttamente (non solo voice 0)
- stream.onset != 0: offset assoluto calcolato correttamente

`PassthroughClipStrategy.apply`:
- Tutti i grain restituiti invariati — inclusi grain con onset >= stream_end e grain con coda che sfora
- Struttura voices preservata (stessa lista di liste)

`GrainClipStrategyFactory.create`:
- `'overflow_margin'` → istanza `OverflowMarginClipStrategy`
- `'passthrough'` → istanza `PassthroughClipStrategy`
- Nome sconosciuto → `ValueError`
- `create('overflow_margin', margin=1.0)` → `strategy.margin == 1.0`

**Verification:**
- `pytest tests/strategies/test_grain_clip_strategy.py` green
- Nessun import circolare: `grain_clip_strategy.py` importa da `core.grain` — verificare che `core.grain` non importi da `strategies`

---

### U2. Integrazione in `Stream.generate_grains`

**Goal:** Applicare `_clip_strategy` come post-process in `generate_grains`, prima dell'assegnazione a `self.voices`.

**Requirements:** R1, R2, R5, R6, R8

**Dependencies:** U1

**Files:**
- Modifica: `src/core/stream.py`
- Modifica: `tests/core/test_stream_multivoice.py` (nuovi test, esistenti invariati)

**Approach:**

In `__init__` (dopo `_init_voice_manager`):
```python
from strategies.grain_clip_strategy import GrainClipStrategyFactory
self._clip_strategy = GrainClipStrategyFactory.create(
    self._config.clip_strategy,
    margin=self._config.clip_margin,
)
```

In `generate_grains`, sostituire **riga 359** (`self.voices = all_voice_grains`) con:
```python
# PRIMA (riga 359)
self.voices = all_voice_grains

# DOPO
self.voices = self._clip_strategy.apply(all_voice_grains, self)
```

Il post-process va inserito **prima** della riga 359 — quella riga è già l'assegnazione, non c'è codice intermedio. Il resto del metodo (flatten + sort per `self.grains`, righe 361–363) rimane invariato — opera su `self.voices` già filtrate.

**Test scenarios (`test_stream_multivoice.py` — nuova sezione):**

- Stream con `onset_offset` fisso che spinge grain oltre duration: grain esclusi da `stream.voices`
- Stream con 2 voci: voice 0 grain tutti dentro bounds, voice 1 grain alcuni fuori → solo voice 1 filtrata
- `stream.grains` (flat) non contiene grain fuori bounds
- `len(stream.voices[i])` riflette solo grain validi
- Con `PassthroughClipStrategy` iniettata: grain con onset >= stream_end presenti in `stream.voices` (il renderer li riceverà integralmente — validato in test piano 002)
- Grain con coda che sfora di esattamente 0 (`onset + duration == stream_end`): incluso
- Grain con coda che sfora di ε oltre `stream_end`: escluso

**Regressione su test esistenti:**
- Tutti i test esistenti in `test_stream.py`, `test_stream_multivoice.py`, `test_stream_voices_yaml.py` rimangono verdi senza modifiche — i grain di test hanno onset piccoli (< 1.0s) e duration standard (es. 0.05s), ben dentro la durata dei mock stream.

**Verification:**
- `make tests` green
- `stream.voices` e `stream.grains` non contengono mai grain con `onset >= stream.onset + stream.duration` (con strategy default)
- ScoreWriter e NumPy renderer non modificati in questo piano

---

## System-Wide Impact

| Componente | Impatto |
|------------|---------|
| `generate_grains` | Aggiunge post-process — loop invariato |
| `stream.voices` / `stream.grains` | Unica fonte di verità: contengono esattamente i grain decisi dalla strategy |
| NumPy renderer | Invariato in questo piano — le guard esistenti diventano obsolete con piano 002 |
| ScoreWriter / Csound renderer | Invariati — ricevono stream già filtrate |
| VoiceManager / Strategy voice | Invariati |
| `StreamConfig` | Aggiunge `clip_strategy: str` e `clip_margin: float` — `from_yaml` invariato |
| YAML parsing | `clip_strategy` e `clip_margin` leggibili come campi piatti nel blocco stream |

---

## Relazione con piano 002

Piano 002 rimuove le guard nel renderer NumPy (`onset_sample < n_total`, `end_sample > n_total`) e dimensiona il buffer sull'extent reale dei grain. Questo è **necessario** per onorare `PassthroughClipStrategy`: se la strategy lascia passare grain che sforano, il renderer deve renderizzarli integralmente.

L'ordine di implementazione raccomandato: **001 → 002**. Piano 001 stabilizza `stream.voices` come fonte di verità; piano 002 rende il renderer fedele a quella fonte.

---

## Configurazione YAML via StreamConfig

`clip_strategy` e `clip_margin` vivono in `StreamConfig` — non in `StreamContext`. Motivazione: sono regole di processo (come `time_mode`, `dephase`), non identità dello stream.

### Modifiche a `StreamConfig`

```python
# src/core/stream_config.py
@dataclass(frozen=True)
class StreamConfig:
    dephase: ...
    range_always_active: bool = False
    distribution_mode: str = 'uniform'
    time_mode: str = 'absolute'
    time_scale: float = 1.0
    clip_strategy: str = 'overflow_margin'  # nuovo
    clip_margin: float = 0.0               # nuovo
    context: Optional[StreamContext] = None
```

`StreamConfig.from_yaml` non richiede modifiche — legge dinamicamente i `field_names` noti.

### Sintassi YAML

```yaml
# default — omettere equivale a overflow_margin + margin 0.0
streams:
  - stream_id: "s1"
    onset: 0.0
    duration: 10.0
    sample: "sample.wav"

# clip con margine
streams:
  - stream_id: "s2"
    clip_strategy: overflow_margin
    clip_margin: 0.5

# passthrough — tutti i grain raggiungono il renderer
streams:
  - stream_id: "s3"
    clip_strategy: passthrough
```

`clip_margin` è un float fisso — non un Parameter con envelope. Coerente con `time_scale`.

### File aggiuntivi coinvolti

- Modifica: `src/core/stream_config.py` — aggiunge i due campi
- Modifica: `tests/core/test_stream_config.py` — verifica default e parsing YAML
- Modifica: `docs/yaml-reference.md` — documenta `clip_strategy` e `clip_margin` nella sezione "Configurazione Processo"

### Test scenarios aggiuntivi (`test_stream_config.py`)

- Default: `StreamConfig()` → `clip_strategy == 'overflow_margin'`, `clip_margin == 0.0`
- `from_yaml({'clip_strategy': 'passthrough'})` → `clip_strategy == 'passthrough'`
- `from_yaml({'clip_margin': 0.5})` → `clip_margin == 0.5`
- YAML senza `clip_strategy`: default preservato

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Mock stream in test senza `onset`/`duration` espliciti: `stream.onset + stream.duration` fallisce | Verificare in U2 che tutti i mock in `test_stream_multivoice.py` abbiano questi attributi numerici. |
| Import circolare `grain_clip_strategy` ↔ `core.grain` | `grain_clip_strategy.py` importa `Grain` da `core.grain`. `core.grain` non importa da `strategies` — no ciclo. Verificare con `pytest --import-mode=importlib`. |
| Behavioral change su stream con grain onset < stream_end ma coda che sfora | Con `margin=0.0`, questi grain ora esclusi — più restrittivo del comportamento precedente NumPy. Scelta intenzionale, documentata in Requirements. |
| `PassthroughClipStrategy` usata senza piano 002: grain che sforano vengono troncati silenziosamente dal renderer | Questo è il comportamento pre-002 — non peggiora nulla. Il troncamento sparisce quando piano 002 è applicato. |

---

## Documentation / Operational Notes

- Dopo merge: aggiornare `docs/ARCHITECTURE.md` sezione "Implementation Notes" con nota su `GrainClipStrategy` come unica superficie di controllo per i bounds dei grain.
- Chiudere issue #27 con riferimento a questo plan e al PR.
- `docs/workflows.md`: aggiungere `grain_clip_strategy.py` alla lista file da toccare quando si aggiunge logica di generazione grain.
