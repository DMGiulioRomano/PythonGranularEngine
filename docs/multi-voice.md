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

Stream.generate_grains()
  └─ per ogni tick temporale t = voice_cursors[voice_index]:
       └─ per ogni voice_index in [0..N-1]:
            ├─ voice_config = voice_manager.get_voice_config(voice_index, t)
            │    ├─ pitch_offset   = pitch_strategy.get_pitch_offset(vi, nv, t)
            │    ├─ onset_offset   = onset_strategy.get_onset_offset(vi, nv, t)
            │    ├─ pointer_offset = pointer_strategy.get_pointer_offset(vi, nv, t)
            │    └─ pan_offset     = pan_strategy.get_pan_offset(vi, nv, resolve_param(pan_spread, t), t)
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
    ├─ _parse_strategy_kwarg(): list/dict → Envelope, altrimenti float
    ├─ Factory per ogni strategy  (VoicePitchStrategyFactory, ecc.)
    ├─ Auto-injection stream_id   (per riproducibilità stochastic)
    └─ VoiceManager(max_voices, strategy..., pan_spread: Union[float, Envelope])

    ▼
Stream.generate_grains()
    └─ voices: List[List[Grain]]   (indicizzati per voce)
         + grains: List[Grain]     (flat, ordinato per onset — backward compat)
```

---

## 3. Componenti principali

### 3.1 VoiceManager

**File:** `src/controllers/voice_manager.py`

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
    def get_pitch_offset(self, voice_index: int, num_voices: int, time: float) -> float:
        """Offset in semitoni. Voce 0 → sempre 0.0."""
```

I parametri scalari di ogni strategia (`step`, `semitone_range`, ecc.) accettano `Union[float, Envelope]`. Con un `Envelope`, il valore viene valutato a `time` tramite `resolve_param(param, time)` — il che consente evoluzione temporale per-grain.

L'offset prodotto da ogni strategia viene applicato in `_create_grain()` come moltiplicatore sul pitch_ratio del grano:

```python
pitch_ratio *= 2 ** (voice_config.pitch_offset / 12.0)
```

Questa è la formula standard dell'equi-temperamento: ogni semitone corrisponde a un fattore `2^(1/12) ≈ 1.0595`.

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

Distribuzione lineare che **normalizza il passo** rispetto al numero di voci per riempire sempre l'intervallo `[0, range(t)]`. `semitone_range` accetta `float` o `Envelope`. La differenza con `step` è che qui lo step varia con N.

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
seed         = hash(stream_id + str(voice_index))
direction(i) = Random(seed).uniform(-1.0, +1.0)   ← calcolato una volta, cached
offset(i, t) = direction(i) × semitone_range(t)
```

La **direzione** per voce è fissa (seeded, cached); la **magnitudine** è `semitone_range(t)` — può variare nel tempo se `semitone_range` è un `Envelope`. Questo garantisce che ogni voce non cambi mai segno durante lo stream. Il seed combina lo `stream_id` (identità dello stream nel YAML) con l'indice di voce, garantendo:
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

**File:** `src/strategies/voice_pointer_strategy.py`

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

**File:** `src/strategies/voice_pan_strategy.py`

```python
class VoicePanStrategy(ABC):
    @abstractmethod
    def get_pan_offset(self, voice_index: int, num_voices: int, spread: float, time: float) -> float:
        """Offset in gradi rispetto al pan base dello stream."""
```

La firma di pan è diversa dalle altre strategie: `spread` è un parametro diretto del metodo (non dell'`__init__`), perché `VoiceManager` lo risolve con `resolve_param(pan_spread, time)` prima di passarlo — consentendo `pan_spread: Envelope` nel YAML. L'offset viene sommato al `pan_base` dello stream per ottenere il pan finale del grano.

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
seed         = hash(stream_id + str(voice_index))
direction(i) = Random(seed).uniform(-1.0, +1.0)   ← cached
offset(i, t) = direction(i) × spread(t) / 2
```

La **direzione** per voce è fissa (seeded, cached al primo accesso); la **magnitudine** dipende da `spread(t)` — risolto per ogni grain da `VoiceManager`. Con `spread: Envelope`, la posizione spaziale per voce mantiene segno fisso ma scala nel tempo.

```
stream_id="pad", spread=60, 4 voci → es. [0.0, +18.6, -10.8, +28.2]
                                          (deterministici, proporzionali a spread)
```

**Effetto audio:** posizionamento "random but bounded" — le voci cadono in punti casuali fissi all'interno dello spread, senza pattern prevedibile. Con spread envelope, l'ampiezza spaziale evolve mantenendo le posizioni relative stabili.

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
    strategy: <nome>          # linear | additive | random
    spread: <float|envelope>  # ampiezza distribuzione stereo in gradi
```

Tutti i parametri scalari (`step`, `semitone_range`, `pointer_range`, `max_offset`, `base`, `spread`) accettano:
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
    semitone_range:
      points: [[0, 0.0], [1, 8.0]]
      time_mode: normalized
```
Risultato: range cresce da 0 a 8 semitoni nella durata dello stream, indipendentemente dalla durata in secondi.

---

## 6. Invarianti di design

| Invariante | Garanzia |
|---|---|
| Voce 0 = riferimento | Sempre `VoiceConfig(0, 0, 0, 0)` a qualsiasi `time`, indipendentemente dalle strategy |
| Onset offset ≥ 0 | Le voci secondarie non precedono mai la voce 0 |
| Valutazione per-grain | `get_voice_config(voice_index, t)` riceve `voice_cursors[voice_index]` — tempo reale della voce |
| Direzione stochastic fissa | Per le strategy stochastiche la direzione per-voce è calcolata una volta (seeded cache); solo la magnitudine varia con l'envelope |
| Riproducibilità stochastic | Seed = `hash(stream_id + voice_index)` → stesso YAML → stesso output |
| Pitch moltiplicativo | `pitch_ratio *= 2^(offset/12)` → compatibile con ratio audio standard |
| Backward compatibility | `self.grains` rimane piatto e ordinato per tutti i consumer esistenti; config scalari esistenti validi senza modifiche |

---

## 7. Test coverage

| File test | Cosa copre |
|---|---|
| `tests/parameters/test_parameter.py` | `resolve_param`: float, Envelope, int, None; regressione `_evaluate_input` |
| `tests/controllers/test_voice_manager.py` | VoiceManager stateless, `get_voice_config(vi, t)`, time-varying, strategy opzionali, voice-0 invariant |
| `tests/strategies/test_voice_pitch_strategy.py` | Tutte le pitch strategy con `time` arg, voice-0 invariant, stochastic direction invariance, envelope range |
| `tests/strategies/test_voice_onset_strategy.py` | Linear, geometric, stochastic onset con `time` arg e envelope |
| `tests/strategies/test_voice_pointer_strategy.py` | Linear, stochastic pointer con `time` arg e envelope |
| `tests/strategies/test_voice_pan_strategy.py` | Tutte le pan strategy con `time` arg, voice-0 invariant per linear/additive, spread envelope |
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
