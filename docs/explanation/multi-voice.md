---
slug: multi-voice
type: explanation
status: stable
tags: [voices, strategy, dmx-1000, granular]
sources:
  - src/pge/strategies/
  - src/pge/core/stream.py
last_synced_commit: 8a8029c
---

# Sistema Multi-Voice — PythonGranularEngine

> Documentazione tecnica del sistema multi-voice granulare.
> Ispirato al DMX-1000 di Barry Truax (1988).

**Documenti collegati:** [[INDEX]] · [[yaml]] § "Blocco Voices" · [[yaml]] § Envelopes
(parametri strategy come envelope) · [[architecture]] · [[add-voice-strategy]] ·
[[errors]] (`StrategyNotFoundError`, `InvalidStrategyConfigError`).

---

## Problema

Truax DMX-1000 (1988) componeva per "voci" parallele indipendenti: ogni stream granulare può sdoppiarsi in N voci con offset di pitch, onset, pointer, pan. Implementare questo in un engine moderno significa decidere: dove vivono le offset? Come si compongono? Come si testano? Come si estendono?

## Modello

`VoiceManager` per stream + `VoiceConfig` per asse + ABC per ogni axis-strategy. Quattro assi ortogonali: pitch, onset, pointer, pan. Invariante centrale: **voice 0 è sempre la voce neutra** (offset zero su ogni asse) — ogni nuova strategy deve rispettarla.

Vedi [Architettura](#2-architettura) per il modello completo, [Componenti principali](#3-componenti-principali) per le ABC e factory.

## Trade-off

| Scelta | Alternativa | Perché questa |
|--------|-------------|---------------|
| Quattro ABC separate (per asse) | Una `VoiceStrategy` unica | Ortogonalità → ogni asse evolve indipendentemente; combinazioni gratis |
| `VoiceManager` per stream | Stream contiene direttamente voce_i | Decoupling: lifecycle voci ≠ lifecycle stream; precompute facile |
| Strategy parameters come envelope | Solo scalari | Pattern compositivi tempo-varying (cluster→spread) senza re-design API |
| Determinismo da `stream_id` (stocastiche) | Random globale | Riproducibilità: stessa composizione → stesso suono |

## Implicazioni codice

- `src/pge/strategies/` — un file per strategy + factory per asse
- `src/pge/core/stream.py` — `_init_voice_manager`, `_parse_strategy_kwarg` (envelope auto-detect)
- `src/pge/core/voice_manager.py` — `VoiceManager`, `VoiceConfig`
- Estensione: vedi [[add-voice-strategy]]
- Errori specifici: `StrategyNotFoundError`, `InvalidStrategyConfigError` (vedi [[errors]])

## Vedi anche

- [[yaml]] § Blocco Voices — sintassi YAML
- [[yaml]] § Envelopes — parametri strategy come envelope
- [[architecture]] — integrazione con renderer
- [[add-voice-strategy]] — workflow estensione

---

## Indice

1. [Panoramica](#1-panoramica)
2. [Architettura](#2-architettura)
3. [Componenti principali](#3-componenti-principali)
   - [VoiceManager](#31-voicemanager)
   - [VoiceConfig](#32-voiceconfig)
   - [Strategie Pitch](#33-strategie-pitch)
   - [Strategie Onset](#34-strategie-onset)
   - [Strategie Pointer](#35-strategie-pointer)
   - [Strategie Pan](#36-strategie-pan)
4. [Integrazione con Stream](#4-integrazione-con-stream)
5. [Configurazione YAML](#5-configurazione-yaml)
6. [Invarianti di design](#6-invarianti-di-design)
7. [Test coverage](#7-test-coverage)

---

## 1. Panoramica

Il sistema multi-voice consente a ogni `Stream` di generare grani su **N voci parallele**, ciascuna con offset indipendenti su quattro dimensioni parametriche:

| Dimensione | Unità | Effetto audio |
|---|---|---|
| **Pitch** | semitoni | Trasposizione per voce |
| **Onset** | secondi | Ritardo temporale |
| **Pointer** | normalizzato 0–1 | Posizione nel sample sorgente |
| **Pan** | gradi | Posizione stereo |

La voce `0` è sempre il **riferimento immutabile** (tutti gli offset a zero). Le voci successive ricevono gli offset calcolati dalla strategy corrispondente.

---

## 2. Architettura

```
Stream
  └─ _init_voice_manager()          ← parsing YAML blocco 'voices:'
       └─ VoiceManager
            ├─ VoicePitchStrategy
            ├─ VoiceOnsetStrategy
            ├─ VoicePointerStrategy
            └─ VoicePanStrategy

Stream.generate_grains()
  └─ per ogni tick temporale t = voice_cursors[voice_index]:
       └─ per ogni voice_index in [0..N-1]:
            ├─ voice_config = voice_manager.get_voice_config(voice_index, t)
            │    ├─ pitch_factor   = pitch_strategy.get_pitch_factor(vi, nv, t, unit)
            │    ├─ onset_offset   = onset_strategy.get_onset_offset(vi, nv, t)
            │    ├─ pointer_offset = pointer_strategy.get_pointer_offset(vi, nv, t)
            │    └─ pan_offset     = pan_strategy.get_pan_offset(vi, nv, t)
            └─ _create_grain(t, dur, voice_config)
                  ├─ pitch_ratio  *= pitch_factor
                  ├─ pointer_pos  += pointer_offset
                  ├─ pan          += pan_offset
                  └─ onset        += onset_offset
```

**Flusso dati completo:**

```
YAML 'voices:'
    │
    ▼
Stream._init_voice_manager()
    ├─ _parse_strategy_kwarg(): list/dict → Envelope, altrimenti float
    ├─ Factory per ogni strategy  (VoicePitchStrategyFactory, ecc.)
    ├─ Auto-injection stream_id   (per riproducibilità stochastic)
    └─ VoiceManager(max_voices, strategy...)  # ogni strategy possiede il proprio param (Union[float, Envelope])

    ▼
Stream.generate_grains()
    └─ voices: List[List[Grain]]   (indicizzati per voce — unica fonte di verità)
```

---

## 3. Componenti principali

### 3.1 VoiceManager

**File:** `src/pge/controllers/voice_manager.py`

Orchestratore centrale. Compone le quattro strategie e calcola `VoiceConfig` on-the-fly per ogni grain al tempo reale della voce.

```python
class VoiceManager:
    def __init__(
        self,
        max_voices: int,
        pitch_strategy:   Optional[VoicePitchStrategy]   = None,
        onset_strategy:   Optional[VoiceOnsetStrategy]   = None,
        pointer_strategy: Optional[VoicePointerStrategy] = None,
        pan_strategy:     Optional[VoicePanStrategy]     = None,
        pan_spread:       Union[float, Envelope] = 0.0,
    ): ...

    def get_voice_config(self, voice_index: int, time: float) -> VoiceConfig: ...
```

- Strategy `None` → offset `0.0` per tutte le voci
- `VoiceConfig` è efimero: ricalcolato per ogni grain al `time` passato dal chiamante
- `pan_spread` accetta `float` o `Envelope`; risolto con `resolve_param(pan_spread, time)` prima di passarlo alla pan strategy

---

### 3.2 VoiceConfig

```python
@dataclass(frozen=True)
class VoiceConfig:
    pitch_factor:   float   # fattore di ratio (1.0 = identità)
    pointer_offset: float   # normalizzato 0.0–1.0
    pan_offset:     float   # gradi
    onset_offset:   float   # secondi
```

Dataclass **immutabile** (`frozen=True`). Voce 0 è sempre `VoiceConfig(1.0, 0.0, 0.0, 0.0)`
(pitch all'identità, gli altri offset a zero).

> **Modello unit-driven (PR #84).** Il pitch di voce non è più un offset in
> semitoni applicato con la formula hardcoded `2^(offset/12)`: la strategy
> restituisce direttamente un **fattore di ratio** già materializzato dalla
> `PitchUnit` attiva (`voices.pitch.unit`, default `semitones` = `EdoUnit(12)`).
> L'unità possiede la geometria (`materialize`/`to_ratio`); `_create_grain` si
> limita a `pitch_ratio *= voice_config.pitch_factor`. Le unità disponibili sono
> `semitones`, `cents`, `quarter_tone`, `eighth_tone`, `edo` (EDO arbitrario),
> `ratio`. Gli esempi numerici qui sotto valgono per l'unità di default
> (`semitones`); con un'altra unità lo stesso valore di `step`/`pitch_range` è
> reinterpretato dalla relativa geometria.

---

### 3.3 Strategie Pitch

**File:** `src/pge/strategies/voice_pitch_strategy.py`

```python
class VoicePitchStrategy(ABC):
    @abstractmethod
    def get_pitch_factor(
        self, voice_index: int, num_voices: int, time: float, unit: 'PitchUnit'
    ) -> float:
        """Fattore di ratio sul pitch base. Voce 0 → sempre 1.0."""
```

I parametri scalari di ogni strategia (`step`, `pitch_range`, ecc.) accettano `Union[float, Envelope]`. Con un `Envelope`, il valore viene valutato a `time` tramite `resolve_param(param, time)` — il che consente evoluzione temporale per-grain.

La strategy non emette più un offset in semitoni: riceve la `PitchUnit` attiva e restituisce un **fattore di ratio** già materializzato dall'unità (`unit.materialize(position, amount)` o `unit.to_ratio(value)`). `_create_grain()` lo applica come semplice moltiplicatore sul pitch_ratio del grano:

```python
pitch_ratio *= voice_config.pitch_factor
```

La geometria dell'equi-temperamento (`2^(v/12)` per `semitones`) vive dentro la `PitchUnit`, non più in `_create_grain`: con `unit: cents` la stessa posizione usa `2^(v/1200)`, con `unit: ratio` il valore è un moltiplicatore diretto, e così via. **Vincolo v1:** `chord` e `spectral` sono definiti intrinsecamente in semitoni e accettano solo `unit: semitones` (altre unità → `InvalidStrategyConfigError`).

---

#### `StepPitchStrategy`

```
offset(i) = i × step(t)
```

Progressione aritmetica pura. `step` accetta `float` o `Envelope`: con un envelope lo step varia nel tempo, espandendo o contraendo l'intervallo tra le voci grain per grain. Aggiungere voci non redistribuisce le esistenti, ma le estende.

```
step=3, 4 voci → [0, 3, 6, 9]  (terze minori)
step=7, 3 voci → [0, 7, 14]    (quinte, poi nona)
step=-2, 3 voci → [0, -2, -4]  (step negativo: voci sotto la voce 0)
```

**Effetto audio:** accordi per moto parallelo, scala cromatica o diatonica, strutture simmetriche con intervallo fisso tra voci.

---

#### `RangePitchStrategy`

```
offset(i) = i × range(t) / (N - 1)    per N > 1
offset(i) = 0.0                        per N == 1
```

Distribuzione lineare che **normalizza il passo** rispetto al numero di voci per riempire sempre l'intervallo `[0, range(t)]`. `pitch_range` accetta `float` o `Envelope`. La differenza con `step` è che qui lo step varia con N.

```
range=12, 4 voci → [0, 4, 8, 12]   step effettivo = 4
range=12, 7 voci → [0, 2, 4, 6, 8, 10, 12]  step effettivo = 2
range=12, 2 voci → [0, 12]          step effettivo = 12
```

**Effetto audio:** distribuzione uniforme di N voci in un intervallo fisso. Utile quando si vuole controllare l'estensione armonica totale senza calcolare manualmente lo step per ogni configurazione di voci.

---

#### `ChordPitchStrategy`

```
offset(i) = intervals[i % n] + (i // n) × 12
```

dove `n = len(chord_intervals)` e `intervals` è la tavola predefinita dell'accordo.

Quando le voci superano il numero di note dell'accordo, il pattern ricomincia dall'ottava superiore (modulo sugli intervalli, divisione intera per il numero di ottave da aggiungere):

```
dom7 = [0, 4, 7, 10],  n=4

i=0 → 0%4=0, 0//4=0  →  intervals[0] + 0×12 = 0
i=1 → 1%4=1, 1//4=0  →  intervals[1] + 0×12 = 4
i=2 → 2%4=2, 2//4=0  →  intervals[2] + 0×12 = 7
i=3 → 3%4=3, 3//4=0  →  intervals[3] + 0×12 = 10
i=4 → 4%4=0, 4//4=1  →  intervals[0] + 1×12 = 12  ← ottava
i=5 → 5%4=1, 5//4=1  →  intervals[1] + 1×12 = 16
```

**Accordi disponibili:**

| Nome YAML | Intervalli | Struttura |
|---|---|---|
| `maj` | [0, 4, 7] | maggiore |
| `min` | [0, 3, 7] | minore |
| `dom7` | [0, 4, 7, 10] | settima di dominante |
| `maj7` | [0, 4, 7, 11] | settima maggiore |
| `min7` | [0, 3, 7, 10] | settima minore |
| `dim` | [0, 3, 6] | diminuito |
| `aug` | [0, 4, 8] | aumentato |
| `sus2` | [0, 2, 7] | sospesa seconda |
| `sus4` | [0, 5, 7] | sospesa quarta |
| `dim7` | [0, 3, 6, 9] | settima diminuita |
| `minmaj7` | [0, 3, 7, 11] | minore con settima maggiore |

**Effetto audio:** armonia tonale precisa. Le voci riproducono esattamente le note di un accordo, estendendo verso l'acuto quando le voci eccedono la cardinalità dell'accordo.

---

#### `ChordProgressionPitchStrategy`

Rende l'accordo una **funzione del tempo** (envelope di accordi): le voci si muovono lungo una sequenza di voicing con glissando continuo o cambi a blocchi. Per ogni voce si costruisce un `Envelope` di offset in semitoni i cui breakpoint sono i target del voicing a ciascun istante della progressione; `get_pitch_factor(i, nv, t)` restituisce `unit.to_ratio(voice_env[i].evaluate(t))`, riusando integralmente l'interpolazione `Envelope` (linear/cubic/step). Gli envelope per-voce sono costruiti **lazy** alla prima chiamata (con `num_voices` noto a runtime) e messi in cache.

**Modello voicing-relativo:** voce 0 → sempre `0.0` (riferimento; il moto di radice vive nell'envelope `pitch` dello stream). La progressione codifica solo la **qualità/voicing** relativo alla voce 0. Una progressione di sole triadi maggiori (I-IV-V) ha offset di voicing costanti `[0,4,7]`: tutto il moto sta nel base pitch (moto parallelo). Il voicing cambia quando cambia la qualità (maj→min7→dom7…).

**Transizione (`interp`):**

- `linear`/`cubic` → **glissando**: le voci scivolano con continuità tra i voicing (interpolazione lineare in semitoni → esponenziale in frequenza).
- `step` → **blocchi**: cambio d'accordo istantaneo all'onset di ogni accordo. Prima del primo / dopo l'ultimo accordo: hold (comportamento `Envelope.evaluate`).

**Voice leading (`voice_leading`):**

- `positional` — voce i → i-esima nota dell'accordo (extend/inversion come `ChordPitchStrategy`).
- `nearest` (default) — le voci 1..N-1 sono riabbinate per minimizzare il movimento totale in semitoni tra voicing consecutivi, con **octave-folding** (ogni slot può essere preso nell'ottava più vicina) e **note comuni tenute**. Voce 0 resta pinned a 0. `nearest` non fa mai peggio di `positional`; per voicing ascendenti spesso coincide con `positional` — il valore distintivo emerge con octave-folding e inversioni. Riabbinamento brute-force sulle permutazioni (N piccolo; oltre 8 voci ripiega su positional).

```
maj7 [0,4,7,11] → min7 [0,3,7,10], 4 voci, voice_leading: nearest
  v0: 0  → 0    (riferimento)
  v1: 4  → 3    (glissa di 1 semitono con interp linear)
  v2: 7  → 7    (nota comune tenuta)
  v3: 11 → 10   (glissa di 1 semitono)
```

**Time mode:** i tempi della `progression` seguono il `time_mode` dello stream, esattamente come gli envelope. Con `time_mode: normalized` i tempi si esprimono in `0..1` e Stream li scala sulla `duration` prima di costruire gli envelope per-voce; con `absolute` (default) sono secondi.

`chord_progression` è **SEMITONE_LOCKED**: accetta solo l'unità `semitones`.

**Effetto audio:** progressioni armoniche evolutive — glissandi corali tra accordi (interp continuo) o armonia a blocchi (step), con voice leading parsimonioso.

---

#### `StochasticPitchStrategy`

```
seed         = hash(stream_id + str(voice_index))
direction(i) = Random(seed).uniform(-1.0, +1.0)   ← calcolato una volta, cached
offset(i, t) = direction(i) × pitch_range(t)
```

La **direzione** per voce è fissa (seeded, cached); la **magnitudine** è `pitch_range(t)` — può variare nel tempo se `pitch_range` è un `Envelope`. Questo garantisce che ogni voce non cambi mai segno durante lo stream. Il seed combina lo `stream_id` (identità dello stream nel YAML) con l'indice di voce, garantendo:
- voci diverse dello stesso stream → offset diversi
- stream diversi → distribuzioni indipendenti
- stesso YAML tra sessioni → stesso output audio

Un dizionario `_cache` evita di ricalcolare il valore alla seconda chiamata.

L'intervallo è **bidirezionale** `[-range, +range]`: le voci possono essere sopra o sotto la voce 0.

```
stream_id="pad", range=0.5, 4 voci → es. [0.0, +0.31, -0.18, +0.47]
                                            (valori deterministici, non casuali a runtime)
```

**Effetto audio:** micro-detuning per voce — ogni voce è leggermente stonata rispetto alle altre in modo fisso, creando il battimento e il "coro naturale" tipico degli ensemble acustici.

---

### 3.4 Strategie Onset

**File:** `src/pge/strategies/voice_onset_strategy.py`

```python
class VoiceOnsetStrategy(ABC):
    @abstractmethod
    def get_onset_offset(self, voice_index: int, num_voices: int, time: float) -> float:
        """Offset in secondi. Sempre >= 0."""
```

> Gli offset di onset sono **sempre ≥ 0**: le voci secondarie seguono la voce di riferimento nel tempo, non la precedono. Questo è un invariante di design — la causalità non può essere invertita.

---

#### `LinearOnsetStrategy`

```
offset(i) = i × step(t)
```

Spaziatura aritmetica uniforme in secondi. `step` accetta `float` o `Envelope`. Ogni voce entra esattamente `step` secondi dopo la precedente.

```
step=0.05, 4 voci → [0.0, 0.05, 0.10, 0.15]
step=0.08, 4 voci → [0.0, 0.08, 0.16, 0.24]
```

**Effetto audio:** phasing regolare stile Truax — le voci si sovrappongono formando un canone a distanza costante. Con step piccoli (< durata grano) si ottiene densificazione, con step grandi si percepisce l'eco.

---

#### `GeometricOnsetStrategy`

```
offset(1, t) = step(t)
offset(2, t) = step(t) × base(t)
offset(3, t) = step(t) × base(t)²
offset(i, t) = step(t) × base(t)^(i-1)
```

`step` e `base` accettano entrambi `float` o `Envelope`.

Spaziatura **esponenziale**: ogni voce successiva è `base` volte più distante dalla precedente rispetto alla voce che la precede.

```
step=0.05, base=2.0, 4 voci:
  voce 1 → 0.05 × 2^0 = 0.050
  voce 2 → 0.05 × 2^1 = 0.100
  voce 3 → 0.05 × 2^2 = 0.200

step=0.1, base=1.5, 5 voci:
  [0.0, 0.100, 0.150, 0.225, 0.338]
```

Caso limite: `base=1` → tutte le voci non-zero hanno lo stesso offset (`step`), indipendente da `i`. Non equivale a `linear` ma a uno step costante su tutte le voci secondarie.

**Effetto audio:** simula l'acustica delle riflessioni — le prime riflessioni sono ravvicinate, quelle successive si diradano. Utile per effetti di riverbero early-reflections o eco che rallentano progressivamente.

---

#### `StochasticOnsetStrategy`

```
seed         = hash(stream_id + str(voice_index))
direction(i) = Random(seed).uniform(0.0, 1.0)   ← cached
offset(i, t) = direction(i) × max_offset(t)
```

Come `StochasticPitchStrategy` ma **unidirezionale** `[0, max_offset(t)]`. `max_offset` accetta `float` o `Envelope`. L'intervallo positivo è un requisito architetturale: le voci non possono precedere la voce 0 nel tempo.

```
stream_id="pad", max_offset=0.1, 4 voci → es. [0.0, 0.073, 0.021, 0.089]
                                                (deterministici, non casuali a runtime)
```

**Effetto audio:** ensemble con attacchi "umani" — le voci partono in ordine non prevedibile ma contenuto, senza la rigidità della distribuzione lineare. Ideale per simulare un ensemble acustico che suona insieme senza essere sincronizzato metronomicamente.

---

### 3.5 Strategie Pointer

**File:** `src/pge/strategies/voice_pointer_strategy.py`

```python
class VoicePointerStrategy(ABC):
    @abstractmethod
    def get_pointer_offset(self, voice_index: int, num_voices: int, time: float) -> float:
        """Offset normalizzato sulla posizione nel sample."""
```

L'offset di pointer si somma in modo additivo con gli altri livelli di posizionamento nel sample:

```
pointer_finale = base_pointer(t)         # PointerController (loop, jitter, speed)
               + voice_pointer_offset    # VoicePointerStrategy  ← qui
               + grain_jitter(t)         # mod_range per-grano
```

Il valore è normalizzato `0.0–1.0` dove `0.0` = inizio del sample, `1.0` = fine.

---

#### `LinearPointerStrategy`

```
offset(i) = i × step(t)
```

Crea N **teste di lettura equidistanti** nel sample. `step` accetta `float` o `Envelope`. Ogni voce legge da un punto diverso, sfasato di `step` rispetto alla precedente.

```
step=0.1, 4 voci → [0.0, 0.1, 0.2, 0.3]
                    voce 0 legge da 0%
                    voce 1 legge da 10%
                    voce 2 legge da 20%
                    voce 3 legge da 30%
```

`step` può essere negativo: le voci secondarie leggono *indietro* rispetto alla voce 0.

```
step=-0.05, 3 voci → [0.0, -0.05, -0.10]
```

**Effetto audio:** ogni voce porta materiale timbrico diverso estratto da punti distinti del sample. Con sample ricchi di variazione spettrale, si ottiene un arricchimento timbrico "geografico" — ogni voce è un'altra zona del suono sorgente.

---

#### `StochasticPointerStrategy`

```
seed         = hash(stream_id + str(voice_index))
direction(i) = Random(seed).uniform(-1.0, +1.0)   ← cached
offset(i, t) = direction(i) × pointer_range(t)
```

Bidirezionale `[-pointer_range(t), +pointer_range(t)]`. `pointer_range` accetta `float` o `Envelope`. Ogni voce legge da un punto casuale ma fisso nel sample, determinato al momento della costruzione.

```
stream_id="texture", range=0.02, 4 voci → es. [0.0, +0.013, -0.007, +0.019]
```

Con `range` piccolo (0.01–0.05) le voci rimangono nella stessa zona del sample ma con micro-variazioni di posizione.

**Effetto audio:** thickening timbrico — le voci condividono il movimento globale nel sample (determinato dal `PointerController`) ma leggono da punti leggermente diversi, introducendo micro-variazioni di timbro senza pattern strutturati.

---

### 3.6 Strategie Pan

**File:** `src/pge/strategies/voice_pan_strategy.py`

```python
class VoicePanStrategy(ABC):
    @abstractmethod
    def get_pan_offset(self, voice_index: int, num_voices: int, spread: float, time: float) -> float:
        """Offset in gradi rispetto al pan base dello stream."""
```

La firma di pan è ora uniforme alle altre dimensioni: `get_pan_offset(voice_index, num_voices, time)`. Ogni strategy possiede il proprio parametro come `StrategyParam` (`spread` per `range`/`stochastic`, `step` per `step`) e lo risolve internamente con `resolve_param(param, time)` — consentendo parametri envelope nel YAML. L'offset viene sommato al `pan_base` dello stream per ottenere il pan finale del grano.

---

#### `RangePanStrategy`

```
offset(i) = -spread/2 + i × spread / (N - 1)    per N > 1
offset(i) = 0.0                                   per i == 0, N == 1 o spread == 0
```

Distribuzione **equidistante** che riempie il range `[-spread/2, +spread/2]`. Voce 0 → sempre 0.0 (Voice-0 invariant), come per `pitch.range`.

```
spread=120, 4 voci → [0, -20, +20, +60]
spread=180, 3 voci → [0, 0, +90]
spread=60,  2 voci → [0, +30]
```

**Effetto audio:** ensemble distribuito uniformemente nel panorama stereo con posizioni fisse e definite. Adatto per texture dove ogni voce deve occupare uno spazio preciso.

---

#### `StochasticPanStrategy`

```
seed         = hash(stream_id + str(voice_index))   # o hashlib se seed esplicito
direction(i) = Random(seed).uniform(-1.0, +1.0)     ← cached
offset(i, t) = direction(i) × spread(t) / 2
```

La **direzione** per voce è fissa (seeded, cached al primo accesso); la **magnitudine** dipende da `spread(t)` — risolto internamente per ogni grain. Con `spread: Envelope`, la posizione spaziale per voce mantiene segno fisso ma scala nel tempo. Voce 0 → sempre 0.0.

```
stream_id="pad", spread=60, 4 voci → es. [0.0, +18.6, -10.8, +28.2]
                                          (deterministici, proporzionali a spread)
```

**Effetto audio:** posizionamento "random but bounded" — le voci cadono in punti casuali fissi all'interno dello spread, senza pattern prevedibile. Con spread envelope, l'ampiezza spaziale evolve mantenendo le posizioni relative stabili.

---

#### `StepPanStrategy`

```
offset(i, t) = i × step(t)     # proporzionale all'indice voce; offset(0) = 0.0
```

Distribuisce le voci con passo costante a partire dalla voce 0 (riferimento). Coerente con `onset.linear` (`i × step`) e `pitch.step`. `step` può essere negativo (pan verso sinistra) e accetta scalare o envelope.

```
step=15, 4 voci → [0, 15, 30, 45]
```

**Effetto audio:** ventaglio stereo che si apre progressivamente dalla voce 0. Per spostare l'intero gruppo di una quantità fissa (la vecchia strategy `additive`) usa invece il parametro `pan` base dello stream.

---

## 4. Integrazione con Stream

### Parsing YAML → `_init_voice_manager()`

`src/pge/core/stream.py` legge il blocco `voices:` e costruisce il `VoiceManager`:

```python
def _init_voice_manager(self, params: dict) -> None:
    v = params.get('voices', {})
    if not v:
        self._voice_manager = VoiceManager(max_voices=1)
        return

    # num_voices è un Parameter (scalare o envelope). max_voices = ceil del picco
    # dei breakpoint (o dello scalare): così la voce di confine frazionaria (fade)
    # ha sempre uno slot.
    max_voices = ceil(max_value_of(self._num_voices))

    # Per le strategie stochastiche, stream_id viene auto-iniettato
    # per garantire riproducibilità tra sessioni con lo stesso YAML
    pitch_strategy   = _build_pitch_strategy(v, self.stream_id)
    onset_strategy   = _build_onset_strategy(v, self.stream_id)
    pointer_strategy = _build_pointer_strategy(v, self.stream_id)
    pan_strategy     = _build_pan_strategy(v, self.stream_id)

    self._voice_manager = VoiceManager(
        max_voices       = max_voices,
        pitch_strategy   = pitch_strategy,
        onset_strategy   = onset_strategy,
        pointer_strategy = pointer_strategy,
        pan_strategy     = pan_strategy,
    )
```

### Output di `generate_grains()`

```python
# Struttura restituita
self.voices: List[List[Grain]]   # voices[voice_idx][grain_idx]
```

Con N voci e densità costante, `len(voices[i])` è uguale per ogni voce attiva:
il totale dei grani è `N × len(singola_voce)`.

`Stream.grains` esiste ancora — vista flat e ordinata per onset — ma è
**derivata** da `voices` e **deprecata** (issue #201): sarà rimossa in 9.0.0.
Non è memorizzata e non ha una setter: assegnarla lasciava `voices` vuoto e lo
stream renderizzava silenzio senza segnalare nulla. Chi ha bisogno della lista
piatta la costruisce dove serve:

```python
[g for voice in stream.voices for g in voice]                    # voice-major
sorted(_, key=lambda g: g.onset)                                 # per onset
```

I due ordini non sono intercambiabili: `Grain` non porta l'indice di voce
(la vista flat è lossy) e i renderer sommano in ordine voice-major, che è
quel che rende un rendering riproducibile.

### Fade frazionario di `num_voices`

`num_voices` time-varying viene valutato a ogni tick. La parte frazionaria del
valore interpolato non viene troncata ma diventa il **gain della voce di
confine** (quella che si accende o si spegne):

```python
value  = min(max_v, self.num_voices.get_value(t))
n_full = floor(value)        # voci 0..n_full-1 a volume pieno (gain 1.0)
frac   = value - n_full      # gain della voce di confine (indice n_full)
# voce di confine: volume += 20*log10(frac), clamp a -120 dB; frac==0 → nessun grano
```

Con interpolazione `step` (breakpoint interi) `frac` è sempre 0 → on/off netto
come prima. Con `linear`/`cubic` la transizione tra due conteggi interi diventa
una dissolvenza graduale e deterministica (nessun RNG). Il gain è applicato in
dB sul campo `volume` del grano, quindi si propaga sia al renderer NumPy sia a
Csound senza nuovi campi su `Grain`; nella partitura grafica la voce in
dissolvenza appare più trasparente perché l'opacità segue il volume.

---

## 5. Configurazione YAML

### Struttura del blocco `voices:`

```yaml
voices:
  num_voices: <int>           # numero totale di voci (inclusa voce 0)

  pitch:
    strategy: <nome>          # step | range | chord | chord_progression | stochastic | spectral
    # parametri specifici della strategy

  onset_offset:
    strategy: <nome>          # linear | geometric | stochastic
    # parametri specifici della strategy

  pointer:
    strategy: <nome>          # linear | stochastic
    # parametri specifici della strategy

  pan:
    strategy: <nome>          # linear | additive | random
    spread: <float|envelope>  # ampiezza distribuzione stereo in gradi
```

Tutti i parametri scalari (`step`, `pitch_range`, `pointer_range`, `max_offset`, `base`, `spread`) accettano:
- `float` — valore costante per tutta la durata dello stream
- lista di punti `[[t, v], ...]` — envelope lineare in secondi
- dizionario `{points: [...], time_mode: normalized}` — envelope in coordinate 0.0–1.0 scalate su `stream.duration`

### Esempi

**Accordo dom7 su 4 voci:**
```yaml
voices:
  num_voices: 4
  pitch:
    strategy: chord
    chord: "dom7"
```
Risultato pitch (unità di default `semitones`): voce 0→1.0, voce 1→2^(4/12)≈1.26, voce 2→2^(7/12)≈1.50, voce 3→2^(10/12)≈1.78 — fattori prodotti da `unit.to_ratio`. `chord` è semitone-locked.

---

**Progressione armonica con glissando (chord_progression):**
```yaml
voices:
  num_voices: 4
  pitch:
    strategy: chord_progression
    progression:                 # sequenza [tempo_secondi, accordo]
      - [0,  "maj7"]
      - [8,  "min7"]
      - [16, "dom7"]
      - [24, "maj7"]
    interp: linear               # linear|cubic = glissando · step = blocchi (default: linear)
    voice_leading: nearest       # nearest (default) | positional
```
Le voci scivolano (glissando) tra i voicing; voce 0 resta riferimento (offset 0). Inversione per-accordo: `[8, "min7", 1]` oppure `[8, {chord: "min7", inversion: 1}]`. Combinando con l'envelope `pitch` dello stream (moto di radice) si ottengono progressioni I–IV–V complete.

---

**Phasing regolare (stile Truax):**
```yaml
voices:
  num_voices: 4
  pitch:
    strategy: step
    step: 3.0
  onset_offset:
    strategy: linear
    step: 0.08
```
Risultato: 4 voci a terze minori, ognuna ritardata di 80ms.

---

**Thickening stochastico:**
```yaml
voices:
  num_voices: 6
  pitch:
    strategy: stochastic
    pitch_range: 0.5
  pointer:
    strategy: stochastic
    pointer_range: 0.02
  pan:
    strategy: linear
    spread: 60.0
```
Risultato: 6 voci con leggere variazioni di pitch e posizione nel sample, distribuite nello spazio stereo.

---

**Distribuzione nel sample:**
```yaml
voices:
  num_voices: 3
  pointer:
    strategy: linear
    step: 0.1
```
Risultato: 3 letture parallele del sample a distanza di 10% l'una dall'altra.

---

**Spreading progressivo — pitch che si apre nel tempo:**
```yaml
voices:
  num_voices: 4
  pitch:
    strategy: step
    step: [[0, 0.0], [10, 12.0]]
```
Risultato: 4 voci partono all'unisono, lo step cresce linearmente da 0 a 12 semitoni in 10s.

---

**Canone che si allarga — onset + pitch con envelope:**
```yaml
voices:
  num_voices: 4
  pitch:
    strategy: step
    step: [[0, 0.0], [30, 7.0]]
  onset_offset:
    strategy: linear
    step: [[0, 0.0], [30, 0.15]]
  pan:
    strategy: linear
    spread: [[0, 0.0], [30, 120.0]]
```
Risultato: tutte e tre le dimensioni si aprono in 30s — da cluster monofonico a ensemble distribuito.

---

**time_mode: normalized — stessa forma in qualsiasi durata:**
```yaml
voices:
  num_voices: 4
  pitch:
    strategy: stochastic
    pitch_range:
      points: [[0, 0.0], [1, 8.0]]
      time_mode: normalized
```
Risultato: range cresce da 0 a 8 semitoni nella durata dello stream, indipendentemente dalla durata in secondi.

---

## 6. Invarianti di design

| Invariante | Garanzia |
|---|---|
| Voce 0 = riferimento | Sempre `VoiceConfig(1.0, 0, 0, 0)` a qualsiasi `time` (pitch_factor all'identità), indipendentemente dalle strategy |
| Onset offset ≥ 0 | Le voci secondarie non precedono mai la voce 0 |
| Valutazione per-grain | `get_voice_config(voice_index, t)` riceve `voice_cursors[voice_index]` — tempo reale della voce |
| Direzione stochastic fissa | Per le strategy stochastiche la direzione per-voce è calcolata una volta (seeded cache); solo la magnitudine varia con l'envelope |
| Riproducibilità stochastic | Seed = `hash(stream_id + voice_index)` → stesso YAML → stesso output |
| Pitch moltiplicativo | `pitch_ratio *= pitch_factor` (fattore materializzato dalla `PitchUnit`) → compatibile con ratio audio standard |
| Fade frazionario voci | La parte decimale di `num_voices` interpolato attenua la voce di confine (`volume += 20·log10(frac)`); `step` con breakpoint interi → on/off netto come prima |
| Backward compatibility | `voices` è l'unica fonte di verità; `stream.grains` resta leggibile come vista derivata ma è deprecata (#201). Config scalari esistenti e `step` con breakpoint interi invariati |

---

## 7. Test coverage

| File test | Cosa copre |
|---|---|
| `tests/parameters/test_parameter.py` | `resolve_param`: float, Envelope, int, None; regressione `_evaluate_input` |
| `tests/controllers/test_voice_manager.py` | VoiceManager stateless, `get_voice_config(vi, t)`, time-varying, strategy opzionali, voice-0 invariant |
| `tests/strategies/test_voice_pitch_strategy.py` | Tutte le pitch strategy con `time` arg, voice-0 invariant, stochastic direction invariance, envelope range |
| `tests/strategies/test_voice_onset_strategy.py` | Linear, geometric, stochastic onset con `time` arg e envelope |
| `tests/strategies/test_voice_pointer_strategy.py` | Linear, stochastic pointer con `time` arg e envelope |
| `tests/strategies/test_voice_pan_strategy.py` | Range, stochastic, step pan con `time` arg, voice-0 invariant, spread/step envelope |
| `tests/core/test_stream_multivoice.py` | Integrazione Stream+VoiceManager; `TestGenerateGrainsEnvelopePerGrain`: verifica valore esatto pitch_ratio per grain a `voice_cursors[vi]` |
| `tests/core/test_stream_voices_yaml.py` | Parsing YAML → strategy corrette; envelope su strategy params; `time_mode: normalized` |

**Esecuzione test multi-voice:**
```bash
make TEST_FILE=tests/controllers/test_voice_manager.py tests
make TEST_FILE=tests/strategies/test_voice_pitch_strategy.py tests
make TEST_FILE=tests/core/test_stream_multivoice.py tests
make TEST_FILE=tests/core/test_stream_voices_yaml.py tests
```

**O tutto insieme:**
```bash
make tests
```
