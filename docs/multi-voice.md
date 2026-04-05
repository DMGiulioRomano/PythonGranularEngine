# Sistema Multi-Voice — PythonGranularEngine

> Documentazione tecnica del sistema multi-voice granulare.  
> Ispirato al DMX-1000 di Barry Truax (1988).

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
            │
            └─ Pre-computa voice_configs[0..N-1]  ← O(1) in seguito

Stream.generate_grains()
  └─ per ogni tick temporale:
       └─ per ogni voice_index in [0..N-1]:
            ├─ voice_config = voice_manager.get_voice_config(voice_index)
            └─ _create_grain(t, dur, voice_config)
                  ├─ pitch_ratio  *= 2^(pitch_offset / 12)
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
    ├─ Factory per ogni strategy  (VoicePitchStrategyFactory, ecc.)
    ├─ Auto-injection stream_id   (per riproducibilità stochastic)
    └─ VoiceManager(max_voices, strategy...)
              └─ [VoiceConfig(0,0,0,0), VoiceConfig(p1,o1,ptr1,pan1), ...]

    ▼
Stream.generate_grains()
    └─ voices: List[List[Grain]]   (indicizzati per voce)
         + grains: List[Grain]     (flat, ordinato per onset — backward compat)
```

---

## 3. Componenti principali

### 3.1 VoiceManager

**File:** `src/controllers/voice_manager.py`

Orchestratore centrale. Compone le quattro strategie e pre-calcola tutti i `VoiceConfig` all'inizializzazione, garantendo O(1) durante la sintesi.

```python
class VoiceManager:
    def __init__(
        self,
        max_voices: int,
        pitch_strategy:   Optional[VoicePitchStrategy]   = None,
        onset_strategy:   Optional[VoiceOnsetStrategy]   = None,
        pointer_strategy: Optional[VoicePointerStrategy] = None,
        pan_strategy:     Optional[VoicePanStrategy]     = None,
        pan_spread:       float = 0.0,
    ): ...

    def get_voice_config(self, voice_index: int) -> VoiceConfig: ...
```

- Strategy `None` → offset `0.0` per tutte le voci
- `voice_configs` è una lista pre-calcolata, non ricalcolata per ogni grano

---

### 3.2 VoiceConfig

```python
@dataclass(frozen=True)
class VoiceConfig:
    pitch_offset:   float   # semitoni
    pointer_offset: float   # normalizzato 0.0–1.0
    pan_offset:     float   # gradi
    onset_offset:   float   # secondi
```

Dataclass **immutabile** (`frozen=True`). Voce 0 è sempre `VoiceConfig(0.0, 0.0, 0.0, 0.0)`.

---

### 3.3 Strategie Pitch

**File:** `src/strategies/voice_pitch_strategy.py`

```python
class VoicePitchStrategy(ABC):
    @abstractmethod
    def get_pitch_offset(self, voice_index: int, num_voices: int) -> float:
        """Offset in semitoni. Voce 0 → sempre 0.0."""
```

L'offset prodotto da ogni strategia viene applicato in `_create_grain()` come moltiplicatore sul pitch_ratio del grano:

```python
pitch_ratio *= 2 ** (voice_config.pitch_offset / 12.0)
```

Questa è la formula standard dell'equi-temperamento: ogni semitone corrisponde a un fattore `2^(1/12) ≈ 1.0595`.

---

#### `StepPitchStrategy`

```
offset(i) = i × step
```

Progressione aritmetica pura. Lo step è costante e indipendente dal numero totale di voci: aggiungere voci non redistribuisce le esistenti, ma le estende.

```
step=3, 4 voci → [0, 3, 6, 9]  (terze minori)
step=7, 3 voci → [0, 7, 14]    (quinte, poi nona)
step=-2, 3 voci → [0, -2, -4]  (step negativo: voci sotto la voce 0)
```

**Effetto audio:** accordi per moto parallelo, scala cromatica o diatonica, strutture simmetriche con intervallo fisso tra voci.

---

#### `RangePitchStrategy`

```
offset(i) = i × range / (N - 1)    per N > 1
offset(i) = 0.0                     per N == 1
```

Distribuzione lineare che **normalizza il passo** rispetto al numero di voci per riempire sempre l'intervallo `[0, range]`. La differenza con `step` è che qui lo step varia con N.

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

#### `StochasticPitchStrategy`

```
seed  = hash(stream_id + str(voice_index))
offset(i) = Random(seed).uniform(-range, +range)
```

L'offset è calcolato una volta per voce con un generatore pseudo-casuale inizializzato da un seed deterministico. Il seed combina lo `stream_id` (identità dello stream nel YAML) con l'indice di voce, garantendo:
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

**File:** `src/strategies/voice_onset_strategy.py`

```python
class VoiceOnsetStrategy(ABC):
    @abstractmethod
    def get_onset_offset(self, voice_index: int, num_voices: int) -> float:
        """Offset in secondi. Sempre >= 0."""
```

> Gli offset di onset sono **sempre ≥ 0**: le voci secondarie seguono la voce di riferimento nel tempo, non la precedono. Questo è un invariante di design — la causalità non può essere invertita.

---

#### `LinearOnsetStrategy`

```
offset(i) = i × step
```

Spaziatura aritmetica uniforme in secondi. Ogni voce entra esattamente `step` secondi dopo la precedente.

```
step=0.05, 4 voci → [0.0, 0.05, 0.10, 0.15]
step=0.08, 4 voci → [0.0, 0.08, 0.16, 0.24]
```

**Effetto audio:** phasing regolare stile Truax — le voci si sovrappongono formando un canone a distanza costante. Con step piccoli (< durata grano) si ottiene densificazione, con step grandi si percepisce l'eco.

---

#### `GeometricOnsetStrategy`

```
offset(1) = step
offset(2) = step × base
offset(3) = step × base²
offset(i) = step × base^(i-1)
```

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
seed  = hash(stream_id + str(voice_index))
offset(i) = Random(seed).uniform(0.0, max_offset)
```

Come `StochasticPitchStrategy` ma **unidirezionale** `[0, max_offset]`. L'intervallo positivo è un requisito architetturale: le voci non possono precedere la voce 0 nel tempo.

```
stream_id="pad", max_offset=0.1, 4 voci → es. [0.0, 0.073, 0.021, 0.089]
                                                (deterministici, non casuali a runtime)
```

**Effetto audio:** ensemble con attacchi "umani" — le voci partono in ordine non prevedibile ma contenuto, senza la rigidità della distribuzione lineare. Ideale per simulare un ensemble acustico che suona insieme senza essere sincronizzato metronomicamente.

---

### 3.5 Strategie Pointer

**File:** `src/strategies/voice_pointer_strategy.py`

```python
class VoicePointerStrategy(ABC):
    @abstractmethod
    def get_pointer_offset(self, voice_index: int, num_voices: int) -> float:
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
offset(i) = i × step
```

Crea N **teste di lettura equidistanti** nel sample. Ogni voce legge da un punto diverso, sfasato di `step` rispetto alla precedente.

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
seed  = hash(stream_id + str(voice_index))
offset(i) = Random(seed).uniform(-range, +range)
```

Bidirezionale `[-range, +range]`. Ogni voce legge da un punto casuale ma fisso nel sample, determinato al momento della costruzione.

```
stream_id="texture", range=0.02, 4 voci → es. [0.0, +0.013, -0.007, +0.019]
```

Con `range` piccolo (0.01–0.05) le voci rimangono nella stessa zona del sample ma con micro-variazioni di posizione.

**Effetto audio:** thickening timbrico — le voci condividono il movimento globale nel sample (determinato dal `PointerController`) ma leggono da punti leggermente diversi, introducendo micro-variazioni di timbro senza pattern strutturati.

---

### 3.6 Strategie Pan

**File:** `src/strategies/voice_pan_strategy.py`

```python
class VoicePanStrategy(ABC):
    @abstractmethod
    def get_pan_offset(self, voice_index: int, num_voices: int, spread: float) -> float:
        """Offset in gradi rispetto al pan base dello stream."""
```

La firma di pan è diversa dalle altre strategie: `spread` è un parametro diretto del metodo (non dell'`__init__`), perché è un parametro di sistema passato dal `VoiceManager` alla chiamata. L'offset viene sommato al `pan_base` dello stream per ottenere il pan finale del grano.

---

#### `LinearPanStrategy`

```
offset(i) = -spread/2 + i × spread / (N - 1)    per N > 1
offset(i) = 0.0                                   per N == 1 o spread == 0
```

Distribuzione **simmetrica centrata in zero** che riempie sempre l'intero range `[-spread/2, +spread/2]` indipendentemente da N.

```
spread=120, 4 voci → [-60, -20, +20, +60]
spread=180, 3 voci → [-90, 0, +90]
spread=60,  2 voci → [-30, +30]
```

**Differenza rispetto alle strategie lineari di pitch/onset:** qui c'è simmetria — la voce 0 va all'estremo sinistro (`-spread/2`), non rimane a zero. Il centramento è sull'insieme delle voci, non sulla voce 0. Questo è intenzionale: la voce 0 fa parte della distribuzione spaziale come tutte le altre.

**Effetto audio:** ensemble distribuito uniformemente nel panorama stereo con posizioni fisse e definite. Adatto per texture dove ogni voce deve occupare uno spazio preciso.

---

#### `RandomPanStrategy`

```
offset(i) = uniform(-spread/2, +spread/2)   # campionato ad ogni chiamata
```

**Non deterministico** — l'unica strategia pan senza seed fisso. Il valore varia ad ogni invocazione del metodo.

La stabilità dell'offset per-voce per tutta la durata dello stream è garantita dal `VoiceManager`: chiama `get_pan_offset` **una sola volta** alla costruzione per ciascuna voce e memorizza il risultato nel `VoiceConfig` (frozen dataclass). Dopo quell'unica chiamata, la posizione rimane fissa.

```
VoiceManager.__init__:
    for i in range(N):
        pan_off = pan_strategy.get_pan_offset(i, N, spread)  # unica chiamata
        voice_configs[i] = VoiceConfig(..., pan_offset=pan_off)
```

**Effetto audio:** posizionamento "random but bounded" — le voci cadono in punti casuali all'interno dello spread, senza pattern prevedibile. Ideale per texture dove la distribuzione spaziale deve sembrare naturale e non strutturata.

---

#### `AdditivePanStrategy`

```
offset(i) = spread    # costante per tutte le voci, indipendente da i e N
```

Non distribuisce le voci nello spazio — sposta **tutte uniformemente** di `spread` gradi rispetto al `pan_base`. Il parametro `spread` è interpretato come offset assoluto, non come ampiezza di distribuzione.

```
spread=30, 4 voci → [30, 30, 30, 30]
```

**Effetto audio:** spostare l'intero gruppo di voci di una quantità fissa rispetto al pan base dello stream (es. "tutta questa texture 30° a sinistra"). Utile per bilanciamento manuale di sezioni sonore senza alterare la distribuzione relativa tra le voci.

---

## 4. Integrazione con Stream

### Parsing YAML → `_init_voice_manager()`

`src/core/stream.py` legge il blocco `voices:` e costruisce il `VoiceManager`:

```python
def _init_voice_manager(self, params: dict) -> None:
    v = params.get('voices', {})
    if not v:
        self._voice_manager = VoiceManager(max_voices=1)
        return

    max_voices = int(v.get('num_voices', 1))

    # Per le strategie stochastiche, stream_id viene auto-iniettato
    # per garantire riproducibilità tra sessioni con lo stesso YAML
    pitch_strategy   = _build_pitch_strategy(v, self.stream_id)
    onset_strategy   = _build_onset_strategy(v, self.stream_id)
    pointer_strategy = _build_pointer_strategy(v, self.stream_id)
    pan_strategy, pan_spread = _build_pan_strategy(v)

    self._voice_manager = VoiceManager(
        max_voices       = max_voices,
        pitch_strategy   = pitch_strategy,
        onset_strategy   = onset_strategy,
        pointer_strategy = pointer_strategy,
        pan_strategy     = pan_strategy,
        pan_spread       = pan_spread,
    )
```

### Output di `generate_grains()`

```python
# Struttura restituita
self.voices: List[List[Grain]]   # voices[voice_idx][grain_idx]
self.grains: List[Grain]         # flat, ordinato per onset (backward compat)
```

Con N voci e densità costante, `len(self.grains) == N × len(singola_voce)`.

---

## 5. Configurazione YAML

### Struttura del blocco `voices:`

```yaml
voices:
  num_voices: <int>           # numero totale di voci (inclusa voce 0)

  pitch:
    strategy: <nome>          # step | range | chord | stochastic
    # parametri specifici della strategy

  onset_offset:
    strategy: <nome>          # linear | geometric | stochastic
    # parametri specifici della strategy

  pointer:
    strategy: <nome>          # linear | stochastic
    # parametri specifici della strategy

  pan:
    strategy: <nome>          # linear | additive
    spread: <float>           # ampiezza distribuzione stereo in gradi
```

### Esempi

**Accordo dom7 su 4 voci:**
```yaml
voices:
  num_voices: 4
  pitch:
    strategy: chord
    chord: "dom7"
```
Risultato pitch: voce 0→1.0, voce 1→2^(4/12)≈1.26, voce 2→2^(7/12)≈1.50, voce 3→2^(10/12)≈1.78

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
    range: 0.5
  pointer:
    strategy: stochastic
    range: 0.02
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

## 6. Invarianti di design

| Invariante | Garanzia |
|---|---|
| Voce 0 = riferimento | Sempre `VoiceConfig(0, 0, 0, 0)`, indipendentemente dalle strategy |
| Onset offset ≥ 0 | Le voci secondarie non precedono mai la voce 0 |
| Pre-computazione | `voice_configs` calcolati all'init → O(1) per ogni grano |
| Riproducibilità stochastic | Seed = `hash(stream_id + voice_index)` → stesso YAML → stesso output |
| Pitch moltiplicativo | `pitch_ratio *= 2^(offset/12)` → compatibile con ratio audio standard |
| Backward compatibility | `self.grains` rimane piatto e ordinato per tutti i consumer esistenti |

---

## 7. Test coverage

| File test | Cosa copre |
|---|---|
| `tests/controllers/test_voice_manager.py` | VoiceManager, VoiceConfig, delega strategy, strategy opzionali, out-of-range |
| `tests/strategies/test_voice_pitch_strategy.py` | Tutte le pitch strategy, accordi, estensione ottave, stocasticità |
| `tests/strategies/test_voice_onset_strategy.py` | Linear, geometric, stochastic onset |
| `tests/strategies/test_voice_pointer_strategy.py` | Linear, stochastic pointer |
| `tests/core/test_stream_multivoice.py` | Integrazione Stream+VoiceManager, conteggio grani, offset applicati |
| `tests/core/test_stream_voices_yaml.py` | Parsing YAML → strategy corrette, valori nei grani generati |

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
