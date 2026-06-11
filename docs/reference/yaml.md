---
slug: yaml
type: reference
status: stable
tags: [yaml, syntax, parameters, envelopes]
sources:
  - src/engine/generator.py
  - src/parameters/
  - src/strategies/
  - src/envelopes/
last_synced_commit: 836a236
entry_for: [yaml-syntax, envelope-syntax]
---

# YAML Reference — PythonGranularEngine

**Documenti collegati:** [[INDEX]] · [[multi-voice]] (sistema voci, strategy
dettagliate) · [[architecture]] (cosa fa il renderer con questi parametri) ·
[[errors]] (errori YAML: `MissingFieldError`, `InvalidFieldValueError`,
`ParameterBoundError`, `InvalidWindowError`) · [[reaper]] (workflow REAPER) ·
sezione [Envelopes](#envelopes) interna per la sintassi degli envelope.

---

## Scope

Reference completa del formato YAML consumato da `main.py`: sintassi per stream, parametri, envelope, voci, finestre, dephase. Copre solo il **formato di input**: la pipeline di rendering è in [[architecture]], le voice strategy in [[multi-voice]].

## Sintassi

Sezioni rilevanti in questo doc:

- [Minimal Stream](#minimal-stream) — schema minimo
- [Parameter Syntax](#parameter-syntax) — scalari, tuple, dict, envelope
- [Campi Obbligatori di Stream](#campi-obbligatori-di-stream)
- [Configurazione Processo (StreamConfig)](#configurazione-processo-streamconfig)
- [Blocco Grain](#blocco-grain), [Pointer](#blocco-pointer), [Pitch](#blocco-pitch), [Dephase](#dephase-variazione-stocastica)
- [Blocco Voices (Multi-Voice)](#blocco-voices-multi-voice)
- [Envelopes](#envelopes) — sintassi envelope completa

## Bounds

Tabella bounds per ogni parametro: [Tabella Bounds Parametri](#tabella-bounds-parametri). Per `clip_strategy` e `ParameterBoundError` vedi [[errors]].

## Esempi

Esempi runnable: [Esempi Completi](#esempi-completi). Casi envelope: sezione [Envelopes](#envelopes).

## Versionato da

- `src/yaml_parser/` — parser
- `src/parameters/parameter_definitions.py`, `src/parameters/parameter_schema.py` — bounds e schema
- `src/envelopes/` — sintassi envelope
- Ultimo allineamento: vedi `last_synced_commit` in frontmatter

---

## Minimal Stream

```yaml
streams:
  - stream_id: "stream1"
    onset: 0.0
    duration: 30
    sample: "sample.wav"
    grain:
      duration: 0.05
```

---

## Parameter Syntax

Qualsiasi parametro numerico accetta le seguenti forme:

| Forma | Esempio | Comportamento |
|-------|---------|--------------|
| Scalare | `density: 10` | Valore fisso |
| Envelope lineare | `density: [[0, 10], [1, 50]]` | Interpolazione lineare tra breakpoint `[time, value]` |
| Envelope annidata | `density: [[[0, 5], [10, 50]], 1.0, 5]` | Envelope di envelope |
| Variazione | `grain: {duration: 0.05, duration_range: 0.01}` | `±0.01` randomizzazione |
| Espressione math | `onset: (pi)`, `duration: (10/2)` | Valutato via `safe_eval` |
| Envelope normalizzato | `step: {points: [[0, 0], [1, 12]], time_mode: normalized}` | `[0, 1]` mappato su `duration` |
| Envelope per-punto interp | `density: [[0, 5, 'cubic'], [0.5, 30, 'step'], [1, 5]]` | `type` per-segmento, override del default globale (issue #54) |
| Envelope dict per-punto | `density: {points: [{t:0, v:5, type:cubic}, {t:1, v:5}]}` | Forma dict equivalente di per-punto interp |

---

## Campi Obbligatori di Stream

```yaml
streams:
  - stream_id: "nome_univoco"   # stringa identificativa
    onset: 0.0                  # tempo di inizio in secondi (assoluto)
    duration: 30.0              # durata dello stream in secondi
    sample: "file.wav"          # nome file (cercato in Media/)
```

---

## Flag di Stream

```yaml
solo:   # solo gli stream con questo flag vengono renderizzati
mute:   # stream ignorato (a meno che non sia attivo solo mode)
```

---

## Configurazione Processo (StreamConfig)

Campi opzionali a livello stream che controllano il comportamento interno:

```yaml
time_mode: normalized   # "absolute" (default) | "normalized"
                        # normalized: coordinate temporali envelope in [0, 1]
                        #             mappate su duration al momento della generazione

dephase: false          # Controllo variazione stocastica (vedi sezione Dephase)

range_always_active: false  # true: i _range sono sempre attivi anche senza dephase

distribution_mode: uniform  # (riservato, non usato correntemente)

time_scale: 1.0         # fattore di scala temporale globale (default 1.0)

clip_strategy: overflow_margin  # "overflow_margin" (default) | "passthrough"
                                # Decide quali grain entrano in stream.voices
clip_margin: 0.0        # tolleranza in secondi per la coda dei grain (default 0.0)
```

### clip_strategy — Controllo grain out-of-bounds

`GrainClipStrategy` filtra i grain in post-process dentro `Stream.generate_grains`. È l'**unica fonte di verità** su quali grain esistono — Csound e NumPy ricevono esattamente la stessa `stream.voices`.

| Valore | Comportamento |
|--------|---------------|
| `overflow_margin` (default) | Grain valido iff `grain.onset < stream_end AND grain.onset + grain.duration <= stream_end + clip_margin`. Con `clip_margin=0.0` il grain deve stare interamente dentro lo stream. |
| `passthrough` | Nessun filtro — tutti i grain passano al renderer, che li renderizza integralmente (il buffer si estende sull'extent reale). |

`stream_end = stream.onset + stream.duration`.

```yaml
# Default — grain interi dentro lo stream
streams:
  - stream_id: "s1"
    onset: 0.0
    duration: 10.0
    sample: "sample.wav"

# Tollera 0.5s di coda oltre stream_end
streams:
  - stream_id: "s2"
    onset: 0.0
    duration: 10.0
    sample: "sample.wav"
    clip_strategy: overflow_margin
    clip_margin: 0.5

# Passthrough — grain con onset/coda oltre stream_end vengono renderizzati;
# la durata del file di output puo' essere > stream.duration
streams:
  - stream_id: "s3"
    onset: 0.0
    duration: 10.0
    sample: "sample.wav"
    clip_strategy: passthrough
```

Note:
- Con `passthrough` il renderer NumPy alloca un buffer esteso sull'extent reale dei grain (`max(g.onset + g.duration)`), quindi il file `.aif` può superare `stream.duration`.
- Csound: stesso filtraggio a monte → SCO contiene solo i grain validi. Il grain non viene mai troncato (incluso intero o escluso).
- `clip_margin` è un float fisso, non un Parameter con envelope (coerente con `time_scale`).

---

## Densità

`density` e `fill_factor` sono mutuamente esclusivi. `fill_factor` ha priorità.

```yaml
# Modalità density: grani al secondo (fisso o envelope)
density: 20
density: [[0, 5], [30, 80]]

# Modalità fill_factor: density = fill_factor / grain_duration
# La densità si adatta automaticamente alla durata del grano.
fill_factor: 2.0

# Distribuzione temporale (modello Truax)
# 0.0 = sincrono (metronomo perfetto)
# 1.0 = asincrono (random uniform 0..2×avg_iot)
# valori intermedi = blend lineare
distribution: 0.0
distribution: [[0, 0.0], [30, 1.0]]
```

Bounds: `density` ∈ [0.01, 4000], `fill_factor` ∈ [0.001, 50], `distribution` ∈ [0, 1].

---

## Volume e Pan

```yaml
volume: 0.0                        # dB, default 0.0
volume: [[0, -12], [30, 0]]
volume_range: 3.0                  # ±3 dB randomizzazione per grano

pan: 0.0                           # gradi, 0 = centro, ±180 = estremi
pan: [[0, -90], [30, 90]]
pan_range: 30.0                    # ±30° randomizzazione per grano
```

Bounds: `volume` ∈ [-120, 12], `pan` ∈ [-3600, 3600].

---

## Blocco Grain

```yaml
grain:
  duration: 0.05           # secondi, default 0.05
  duration: [[0, 0.02], [30, 0.2]]
  duration_range: 0.01     # ±0.01s randomizzazione

  envelope: hanning        # finestra per shape del grano (default: hanning)
  # Vedi sezione "Finestre Disponibili" per tutti i valori validi.

  # Modalità lista: selezione casuale tra finestre
  envelope: [hanning, expodec, gaussian]

  # Modalità transizione: morphing probabilistico da→a
  envelope:
    from: hanning
    to: bartlett
    curve: [[0, 0], [30, 1]]   # 0=100% from, 1=100% to

  # Modalità multi-stato: percorso attraverso N finestre
  envelope:
    states:
      - [0.0, hanning]
      - [0.3, bartlett]
      - [0.7, expodec]
      - [1.0, gaussian]
    curve: [[0, 0], [30, 1]]

  # Reverse: chiave assente = auto (segue pointer_speed_ratio)
  #          chiave presente vuota = reverse forzato
  reverse:          # forza reverse per tutti i grani
  # ERRORE: reverse: true / reverse: false / reverse: auto
```

Bounds: `grain_duration` ∈ [0.001, 10].

---

## Blocco Pointer

Controlla la posizione di lettura nel sample sorgente.

```yaml
pointer:
  start: 0.0              # posizione iniziale in secondi (default 0.0)
  speed_ratio: 1.0        # velocità di lettura (default 1.0)
                          # 1.0 = velocità normale, -1.0 = indietro, 2.0 = doppia
                          # supporta envelope: [[0, 1.0], [30, 2.0]]

  offset_range: 0.0       # deviazione per-grano ∈ [-offset_range, +offset_range]
                          # scalata rispetto alla finestra di loop attiva

  # Loop (opzionale) — richiede almeno loop_start
  loop_start: 1.0         # inizio loop in secondi
  loop_end: 3.0           # fine loop in secondi  ──┐ mutuamente esclusivi
  loop_dur: 2.0           # durata loop in secondi ──┘ (loop_end ha priorità)

  # loop_start e loop_end/loop_dur supportano envelope:
  loop_start: [[0, 1.0], [30, 5.0]]   # finestra di loop mobile
  loop_dur: [[0, 0.5], [30, 3.0]]

  # Unità per i valori loop (opzionale)
  loop_unit: normalized   # "normalized": valori [0,1] scalati su sample_dur_sec
                          # default: eredita da time_mode dello stream
```

Bounds: `pointer_speed_ratio` ∈ [-100, 100], `pointer_deviation` ∈ [-1, 1].

---

## Blocco Pitch

Una sola chiave-unità di trasposizione per blocco (modello unit-driven:
ogni unità è una `PitchUnit`, unica fonte di verità per conversione e bounds).
La famiglia EDO (Equal Division of the Octave) converte in ratio con
`2^(valore / N)`; `ratio` è invece un moltiplicatore diretto.

| Chiave | Unità | N (divisioni/ottava) | Bounds |
|--------|-------|----------------------|--------|
| `semitones` | semitoni | 12 | [-36, 36] |
| `quarter_tone` | quarti di tono | 24 | [-72, 72] |
| `eighth_tone` | ottavi di tono | 48 | [-144, 144] |
| `cents` | cents | 1200 | [-3600, 3600] |
| `edo` (+ `value`) | EDO arbitrario | N | [-3·N, 3·N] |
| `ratio` | ratio diretto | — | [0.125, 8] |

Più chiavi-unità nello stesso blocco → errore (`InvalidFieldValueError`):
niente più priorità implicita. Senza alcuna chiave-unità: default `semitones`
con valore neutro `0` (ratio 1.0).

Chiavi sconosciute nel blocco (refusi tipo `semitone:` invece di `semitones:`)
→ errore (`InvalidFieldValueError`), non vengono ignorate silenziosamente.
Chiavi valide del blocco: le 6 unità più `range` e `value`. `value` è ammesso
**solo** con `edo: N` (per i preset il valore sta nella chiave); usarlo altrove
→ errore.

```yaml
pitch:
  ratio: 1.0              # rapporto di trasposizione (default 1.0 = no trasposizione)
  ratio: [[0, 0.5], [30, 2.0]]
  range: 0.1              # ±variazione random intorno a ratio

  semitones: 0            # trasposizione in semitoni (intero o float)
  semitones: [[0, -12], [30, 12]]
  range: 6                # ±variazione random in semitoni (intera)

  quarter_tone: 3         # quarti di tono (24-EDO)
  eighth_tone: 6          # ottavi di tono (48-EDO)
  cents: 50               # cents (1200-EDO)

  edo: 31                 # griglia EDO arbitraria (es. 31-EDO), divisioni/ottava
  value: 18               # 18 gradi di 31-EDO (scalare o envelope)
```

> `edo` ha una sola grammatica su tutta la superficie YAML: intero scalare. Su
> base si abbina a `value:` a fianco; nelle voci è `unit: {edo: N}` (il valore
> arriva dalla strategy). La vecchia forma annidata `edo: {divisions, value}`
> non è più valida (`InvalidFieldValueError` con hint di migrazione).

---

## Dephase (Variazione Stocastica)

`dephase` controlla la probabilità di applicare variazioni stocastiche per-grano.
Si applica a tutti i parametri che hanno un `_range` associato.

```yaml
# Disabilitato (default): range attivi solo se presenti
dephase: false

# Implicito: usa probabilità di default (1%)
dephase: null

# Globale: probabilità uniforme per tutti i parametri (0–100)
dephase: 50

# Globale con envelope: probabilità che varia nel tempo
dephase: [[0, 0], [30, 80]]

# Specifico per parametro: probabilità diverse per ciascuno
dephase:
  volume: 30          # 30% probabilità di applicare volume_range
  pan: 50             # 50% probabilità di applicare pan_range
  duration: 20        # 20% probabilità di applicare duration_range
  pitch: 10           # 10% per pitch range
  pointer: 40         # 40% per pointer offset_range
  reverse: 5          # 5% probabilità di flip reverse
  envelope: 15        # 15% probabilità di cambiare finestra (se lista)

# Valore specifico come envelope
dephase:
  volume: [[0, 0], [30, 80]]
  pan: 50
```

### Detune implicito del pitch (senza `range`)

Quando il pitch è sotto dephase **senza** `range` esplicito, ai grani che il
gate seleziona si applica un micro-detune continuo:

- unità EDO (`semitones`, `cents`, `quarter_tone`, `eighth_tone`, `edo: N`):
  ±12 cents uniformi per grano, applicati in ratio-space **dopo** la
  quantizzazione di griglia (il ratio risultante resta nei bounds ±3 ottave);
- `ratio`: jitter implicito ±0.005 sul moltiplicatore (comportamento storico).

```yaml
pitch:
  semitones: 7            # nessun range dichiarato
dephase:
  pitch: 50               # 50% dei grani: 7 st ± max 12 cents (continuo)
```

Con `range` esplicito (anche `range: 0`) il detune implicito non si applica:
vale la variazione quantizzata di griglia dichiarata dall'utente. Il path
voci (`voices.pitch`) non è mai interessato dal detune.

---

## Blocco Voices (Multi-Voice)

```yaml
voices:
  num_voices: 4           # numero di voci (int), default 1
                          # supporta envelope: [[0, 1], [30, 8]]
  scatter: 0.0            # 0.0 = tutte le voci sincrone sullo stesso IOT
                          # 1.0 = ogni voce ha IOT indipendente
                          # blend lineare tra i due estremi
  pitch: ...              # strategia distribuzione pitch (vedi sotto)
  onset_offset: ...       # strategia distribuzione onset (vedi sotto)
  pointer: ...            # strategia distribuzione pointer (vedi sotto)
  pan: ...                # strategia distribuzione pan (vedi sotto)
```

La voce 0 è sempre il riferimento: non riceve offset da nessuna strategia.

---

### voices.pitch — Strategie Pitch

```yaml
# step: voce i → i × step semitoni
voices:
  pitch:
    strategy: step
    step: 3.0             # semitoni per passo (scalare o envelope)

# range: voci distribuite linearmente in [0, pitch_range]
voices:
  pitch:
    strategy: range
    pitch_range: 12.0  # ampiezza totale nell'unità attiva (scalare o envelope)

# chord: offsets da accordo nominale
voices:
  pitch:
    strategy: chord
    chord: "dom7"         # nome accordo (vedi lista sotto)
    inversion: 0          # rivolto (0 = root position, default)

# stochastic: offset per voce fisso (seeded), magnitudine time-varying
voices:
  pitch:
    strategy: stochastic
    pitch_range: 6.0   # magnitudine massima (scalare o envelope)

# spectral: voci sui parziali della serie armonica naturale
voices:
  pitch:
    strategy: spectral
    # voce i → round(12 × log₂(i+1)) semitoni
    # [0, 12, 19, 24, 28, 31, ...] per le prime voci
```

**Accordi disponibili (`chord`):**

| 3 voci | 4 voci | 5 voci | 6 voci | 7 voci |
|--------|--------|--------|--------|--------|
| `maj` | `dom7` | `dom9` | `dom9s11` | `dom13` |
| `min` | `maj7` | `maj9` | `maj9s11` | `min13` |
| `dim` | `min7` | `min9` | `min11` | `maj13s11` |
| `aug` | `dim7` | `9sus4` | | `altered` |
| `sus2` | `minmaj7` | | | |
| `sus4` | | | | |

**`unit` — geometria della distribuzione pitch.** Le strategie scalate
(`step`/`range`/`stochastic`) emettono una posizione adimensionale; `unit`
possiede la geometria con cui diventa un fattore di ratio. Default `semitones`.
Valori: `semitones`, `cents`, `quarter_tone`, `eighth_tone`, `{edo: N}`,
`ratio` (stesse unità del [Blocco Pitch](#blocco-pitch)). La voce 0 resta
sempre all'identità (ratio 1.0) per ogni unità.

- famiglia **EDO** → additiva nel log: `2^(position·amount/N)`. La
  distribuzione è equidistante in semitoni/cents/gradi.
- **`ratio`** → **geometrica**: `amount^position`. La distribuzione compone
  moltiplicativamente (le frequenze si moltiplicano), sempre positiva. Esempi:
  `step: 2` → voci a ratio `1, 2, 4, 8` (ottave pulite); `range: 2` con 4 voci
  → `1, 1.26, 1.59, 2`; `stochastic` con `pitch_range: 2` → fattori in
  `[0.5, 2]`. Con `ratio` l'ampiezza (`step`/`pitch_range`) dev'essere `> 0`.

```yaml
voices:
  pitch:
    strategy: range
    pitch_range: 12.0
    unit: {edo: 31}        # i gradi distribuiti sono interpretati in 31-EDO
```

- **Vincolo**: `chord` e `spectral` sono definiti intrinsecamente in semitoni
  (offset assoluti) e accettano solo `unit: semitones` (o `unit` assente).
  Altre unità → `InvalidStrategyConfigError`.

---

### voices.onset_offset — Strategie Onset

```yaml
# linear: voce i → i × step secondi
voices:
  onset_offset:
    strategy: linear
    step: 0.08            # secondi per passo (scalare o envelope)

# geometric: voce i → step × base^(i-1) secondi
voices:
  onset_offset:
    strategy: geometric
    step: 0.05            # passo iniziale (scalare o envelope)
    base: 2.0             # base esponenziale (scalare o envelope)

# stochastic: offset per voce in [0, max_offset] (seeded)
voices:
  onset_offset:
    strategy: stochastic
    max_offset: 0.2       # offset massimo in secondi (scalare o envelope)
```

---

### voices.pointer — Strategie Pointer

```yaml
# linear: voce i → i × step (offset su posizione campione)
voices:
  pointer:
    strategy: linear
    step: 0.1             # scalare o envelope. Negativo = voci leggono indietro.

# stochastic: offset per voce in [-pointer_range, +pointer_range] (seeded)
voices:
  pointer:
    strategy: stochastic
    pointer_range: 0.2    # range massimo (scalare o envelope)
```

**Unità dell'offset (`normalized`).** Di default l'offset di pointer è in
**secondi** nel sample (coerente con `onset_offset`). Aggiungendo `normalized: true`
al blocco `pointer`, lo stesso valore è interpretato come **frazione di
`sample_dur_sec`** (es. `step: 0.12` → 12% del buffer):

```yaml
voices:
  pointer:
    strategy: linear
    step: 0.12
    normalized: true      # 0.12 = 12% del buffer (default: 0.12 secondi)
```

Il flag è opzionale e vale per `linear` e `stochastic`. Lo scaling avviene in
`Stream._create_grain`; le strategy restituiscono il valore raw. Accetta solo
`true`/`false`: un valore non booleano solleva `InvalidFieldValueError`. Risolve
l'ambiguità di unità storica (issue #80).

---

### voices.pan — Strategie Pan

```yaml
# linear: voci distribuite in [-spread/2, +spread/2]
voices:
  pan:
    strategy: linear
    spread: 120.0         # gradi totali (scalare o envelope)

# additive: offset fisso identico per tutte le voci (non voce 0)
voices:
  pan:
    strategy: additive
    spread: 45.0          # offset in gradi (scalare o envelope)

# random: offset per voce in [-spread/2, +spread/2] (seeded)
voices:
  pan:
    strategy: random
    spread: 180.0         # range totale in gradi (scalare o envelope)
```

---

## Finestre Disponibili (`grain.envelope`)

| Nome | Famiglia | Descrizione |
|------|----------|-------------|
| `hanning` | window | Hanning/von Hann (default) |
| `hamming` | window | Hamming |
| `bartlett` | window | Bartlett/Triangle (alias: `triangle`) |
| `blackman` | window | Blackman |
| `blackman_harris` | window | Blackman-Harris |
| `gaussian` | window | Gaussiana |
| `kaiser` | window | Kaiser-Bessel |
| `rectangle` | window | Rettangolare/Dirichlet |
| `sinc` | window | Sinc |
| `half_sine` | custom | Semi-sinusoide |
| `expodec` | asymmetric | Decadimento esponenziale (Roads-style) |
| `expodec_strong` | asymmetric | Decadimento esponenziale forte |
| `exporise` | asymmetric | Salita esponenziale |
| `exporise_strong` | asymmetric | Salita esponenziale forte |
| `rexpodec` | asymmetric | Decadimento esponenziale inverso |
| `rexporise` | asymmetric | Salita esponenziale inversa |
| `all` | — | Espande a tutte le finestre disponibili |

---

## Esempi Completi

### Stream con loop e pitch in semitoni

```yaml
streams:
  - stream_id: "loop_pitch"
    onset: 0.0
    duration: 60.0
    sample: "sample.wav"
    density: [[0, 5], [30, 40], [60, 5]]
    volume: -9.0
    volume_range: 6.0
    pan: 0.0
    dephase:
      volume: 50
      pan: 30
    grain:
      duration: 0.08
      duration_range: 0.02
      envelope: hanning
    pointer:
      speed_ratio: 1.0
      loop_start: 2.0
      loop_dur: 4.0
    pitch:
      semitones: 0
      range: 2
```

### Stream multi-voice con chord e onset phasing

```yaml
streams:
  - stream_id: "chord_phasing"
    onset: 0.0
    duration: 30.0
    sample: "sample.wav"
    density: 12
    grain:
      duration: 0.1
    pitch:
      semitones: 0
    voices:
      num_voices: 4
      pitch:
        strategy: chord
        chord: "maj7"
      onset_offset:
        strategy: linear
        step: 0.05
      pan:
        strategy: linear
        spread: 90.0
```

### Envelope normalizzata per strategia voice

```yaml
streams:
  - stream_id: "voice_pitch_normalized"
    onset: 0.0
    duration: 10.0
    sample: "sample.wav"
    time_mode: normalized
    density: 8
    grain:
      duration: 0.08
    voices:
      num_voices: 4
      pitch:
        strategy: step
        step:
          points: [[0, 0.0], [1, 12.0]]
          time_mode: normalized
```

### Transizione finestra con multi-stato

```yaml
streams:
  - stream_id: "window_morph"
    onset: 0.0
    duration: 30.0
    sample: "sample.wav"
    density: 20
    grain:
      duration: 0.05
      envelope:
        states:
          - [0.0, hanning]
          - [0.4, bartlett]
          - [1.0, expodec]
        curve: [[0, 0], [30, 1]]
```

---

## Envelopes

> Sintassi completa del sistema envelope (sostituisce il vecchio `envelopes-reference.md`).
>
> Sorgente di verità: `src/envelopes/envelope.py`, `src/envelopes/envelope_builder.py`, `src/envelopes/envelope_interpolation.py`, `src/envelopes/envelope_segment.py`, `src/envelopes/time_distribution.py`.

### Indice envelopes

1. [Modello concettuale](#1-modello-concettuale)
2. [Forme di sintassi accettate](#2-forme-di-sintassi-accettate)
3. [Time mode: absolute vs normalized](#3-time-mode-absolute-vs-normalized)
4. [Tipi di interpolazione](#4-tipi-di-interpolazione)
5. [Formato compatto](#5-formato-compatto-cicli-ripetuti)
6. [Distribuzioni temporali](#6-distribuzioni-temporali-nei-cicli)
7. [Formato misto](#7-formato-misto-breakpoint--cicli)
8. [Comportamento ai bordi](#8-comportamento-ai-bordi-hold)
9. [Espressioni matematiche](#9-espressioni-matematiche-nei-valori)
10. [Casi speciali per dominio](#10-casi-speciali-per-dominio)
11. [Validazione e bounds](#11-validazione-e-bounds)
12. [Tabella riassuntiva](#12-tabella-riassuntiva-delle-sintassi)

### 1. Modello concettuale

Un Envelope è una funzione `f(t) → v` definita a tratti su breakpoint. Sostituisce
qualunque valore scalare ovunque il parser lo accetti. Il sistema riconosce un
envelope tramite `Envelope.is_envelope_like(value)`:

- istanza di `Envelope`
- lista non vuota con almeno un elemento `[t, v]` o un formato compatto
- dict contenente la chiave `points`

Tutti i parametri numerici dei seguenti blocchi accettano envelope:
`density`, `fill_factor`, `distribution`, `volume`, `pan`, `grain.duration`,
`grain.duration_range`, `pitch.ratio`, `pitch.semitones`, `pitch.range`,
`pointer.start`, `pointer.speed_ratio`, `pointer.offset_range`,
`pointer.loop_start`, `pointer.loop_end`, `pointer.loop_dur`, `dephase` (globale
o per chiave), `voices.num_voices`, `voices.scatter`, i parametri scalari di
ciascuna voice strategy (`step`, `pitch_range`, `pointer_range`,
`max_offset`, `base`, `spread`), e il campo `curve` di
`grain.envelope.transition` e `grain.envelope.multistate`.

Internamente l'envelope è composto da:

- **breakpoints**: lista normalizzata `[[t, v], …]` in tempi assoluti, ordinata.
- **strategy**: `InterpolationStrategy` selezionata da `type` (linear/cubic/step).
- **segments**: lista di `NormalSegment` con metodi `evaluate(t)` e `integrate(a, b)`.

Per cubic, il sistema pre-calcola le tangenti con l'algoritmo Fritsch-Carlson,
che garantisce monotonia e previene overshoot tra breakpoint adiacenti.

---

### 2. Forme di sintassi accettate

Le forme valide nel YAML sono cinque. Tutte vengono ricondotte a una lista
piatta di breakpoint `[[t, v], …]` durante il parsing (`EnvelopeBuilder.parse`).

#### 2.1 Scalare

Non è un envelope: è un valore costante.

```yaml
density: 20
volume: -6.0
```

#### 2.2 Lista di breakpoint standard

Forma più comune. Lista di coppie `[time, value]`. Il tipo di interpolazione
implicito è `linear`.

```yaml
density: [[0, 5], [10, 40], [30, 5]]
volume: [[0, -12], [30, 0]]
```

Vincoli:

- ogni elemento deve essere una lista di esattamente 2 numeri
- l'ordine non deve essere garantito dall'utente: i breakpoint vengono ordinati
  automaticamente per tempo crescente in `Segment.__init__`
- almeno un breakpoint è richiesto (zero solleva `InvalidFieldValueError`)

#### 2.3 Dict `{type, points}`

Permette di selezionare esplicitamente l'interpolazione e supporta una chiave
opzionale per il time mode locale.

```yaml
density:
  type: cubic
  points: [[0, 5], [10, 40], [30, 5]]
```

Campi:

| Chiave      | Tipo            | Default      | Significato                                |
|-------------|-----------------|--------------|--------------------------------------------|
| `type`      | str             | `'linear'`   | `'linear'`, `'cubic'`, `'step'`            |
| `points`    | lista           | richiesto    | breakpoint o formati compatti              |
| `time_mode` | str (opzionale) | ereditato    | `'absolute'` o `'normalized'`              |
| `time_unit` | str (opzionale) | come `time_mode` | alias locale per `time_mode` (vedi §3) |

#### 2.4 Formato compatto

Forma sintetica per generare N ripetizioni di un pattern definito in percentuale.
Sintassi: `[pattern_points, end_time, n_reps, interp?, time_dist?]`. Dettagliato in §5.

```yaml
grain:
  duration: [[[0, 0.01], [100, 0.2]], 30, 4]
```

#### 2.5 Formato misto

Lista che contiene insieme breakpoint standard e formati compatti. Il sistema
calcola un offset automatico in modo che ogni parte compatta inizi dall'ultimo
breakpoint scritto prima di essa. Dettagliato in §7.

```yaml
density: [
  [0, 10],
  [5, 10],
  [[[0, 30], [100, 50]], 25, 4]
]
```

#### 2.6 Interp type per-punto (issue #54)

> Origine: [plans/done/2026-05-22-003-feat-envelope-per-point-interp-plan.md](../plans/done/2026-05-22-003-feat-envelope-per-point-interp-plan.md)

Ogni breakpoint puo' dichiarare il proprio tipo di interpolazione applicato al
**segmento dal punto fino al successivo**. Due forme equivalenti:

**Tupla 3-elem:** `[t, v, type]`

```yaml
density: [[0, 5, 'cubic'], [0.3, 30, 'linear'], [0.7, 10, 'step'], [1, 5]]
# Seg 0->1: cubic. Seg 1->2: linear. Seg 2->3: step.
```

**Dict per-punto:** `{t, v, type}`

```yaml
density:
  type: linear     # default per i punti senza 'type' esplicito
  points:
    - {t: 0,   v: 5,  type: cubic}
    - {t: 0.3, v: 30, type: linear}
    - {t: 0.7, v: 10, type: step}
    - {t: 1,   v: 5}
```

Regole:

- `type` su punto `i` = strategia segmento `i -> i+1`
- Ultimo punto: `type` ignorato (warning a log, no errore)
- Punto senza `type` (2-elem o dict senza chiave): eredita default globale
  (`dict.type`, wrapper compact `interp`, oppure `'linear'`)
- Mix 2-elem + 3-elem nella stessa lista accettato
- `type` non in `{linear, cubic, step}` -> `InvalidFieldValueError`
- Tangenti Fritsch-Carlson per segmenti `cubic`: calcolate globalmente sull'
  intera lista breakpoint, applicate solo ai segmenti `cubic` (coerenza
  boundary tra strategy diverse)

Backward compat: tutti i formati 2-elem `[t, v]` continuano a funzionare
invariati.

---

### 3. Time mode: `absolute` vs `normalized`

Il `time_mode` controlla l'unità di misura dell'asse X dell'envelope.

#### 3.1 `absolute` (default)

I tempi sono in secondi. Un breakpoint `[10, 40]` vale "al secondo 10 il valore
è 40", indipendentemente dalla durata dello stream.

```yaml
streams:
  - stream_id: s1
    duration: 30.0
    density: [[0, 5], [10, 40], [30, 5]]
    # picco a t=10s
```

#### 3.2 `normalized`

I tempi sono in `[0, 1]` e vengono moltiplicati per la `duration` dello stream
al momento del parsing (`create_scaled_envelope` in `envelope.py`).

Tre modi per attivarlo:

**(a) Globale a livello stream**

```yaml
streams:
  - stream_id: s1
    duration: 30.0
    time_mode: normalized          # vale per tutti gli envelope dello stream
    density: [[0, 5], [0.5, 40], [1, 5]]
    # picco a t=15s (50% di 30s)
```

**(b) Locale all'envelope (forma dict)**

```yaml
density:
  type: linear
  points: [[0, 5], [0.5, 40], [1, 5]]
  time_mode: normalized
```

`time_unit` è un alias accettato per `time_mode` quando si scrive in forma dict:

```yaml
density:
  points: [[0, 5], [1, 50]]
  time_unit: normalized
```

**(c) Solo per i parametri loop del pointer: `loop_unit`**

I parametri `loop_start`, `loop_end`, `loop_dur` (e `start`) hanno una semantica
aggiuntiva: `loop_unit: normalized` scala i **valori** (asse Y) da `[0, 1]` a
`[0, sample_dur_sec]`. Non agisce sull'asse X. È documentato nella sezione 10.

#### 3.3 Scaling del formato compatto

Quando `time_mode: normalized` è attivo, anche `end_time` di un formato compatto
viene scalato per `duration`. Vedere `_scale_time_recursive` in `envelope.py`.

```yaml
duration: 30.0
time_mode: normalized
density: [[[0, 0], [100, 50]], 0.5, 4]
# end_time effettivo: 0.5 * 30 = 15s
# 4 ripetizioni distribuite tra 0 e 15s
```

---

### 4. Tipi di interpolazione

Tre strategie, selezionabili tramite `type` (in forma dict), come quarto
elemento opzionale di un formato compatto, oppure per-singolo-punto via
tupla 3-elem o dict per-punto (vedi §2.6).

#### 4.1 `linear` (default)

Interpolazione lineare tra breakpoint consecutivi. Integrale calcolato come area
di trapezio.

```yaml
density:
  type: linear
  points: [[0, 5], [10, 40], [30, 5]]
```

#### 4.2 `cubic`

Hermite cubic con tangenti calcolate dall'algoritmo **Fritsch-Carlson**.
Garantisce monotonia: se tre breakpoint sono monotoni, la curva interpolante non
ne esce. Nei punti critici (cambio di pendenza) la tangente è forzata a zero.
L'integrale è calcolato con regola di Simpson composita su 10 sotto-intervalli
per ogni segmento.

```yaml
volume:
  type: cubic
  points: [[0, -60], [5, -6], [25, -6], [30, -60]]
```

Quando preferirlo:

- attacchi e rilasci morbidi senza overshoot
- fade di parametri continui (volume, density)
- traiettorie di pointer dove la derivata seconda continua è udibile

#### 4.3 `step`

Hold-left: il valore di ogni segmento è quello del breakpoint sinistro fino al
breakpoint successivo. L'integrale è area di rettangolo.

```yaml
density:
  type: step
  points: [[0, 5], [10, 40], [20, 10], [30, 0]]
```

Utile per cambi discontinui di sezione, automazioni "a quantità fisse",
modulazioni di parametri categorici (es. numero di voci).

#### 4.4 Discontinuità con formato compatto

Quando si concatenano cicli, il `BUILDER` inserisce automaticamente un offset
infinitesimale di `1e-6` secondi (`DISCONTINUITY_OFFSET` in `envelope_builder.py`)
tra il primo punto di un nuovo ciclo e il punto precedente, in modo che due
breakpoint non coincidano sullo stesso tempo. Questo permette discontinuità
intenzionali senza degenerare gli algoritmi di interpolazione.

---

### 5. Formato compatto (cicli ripetuti)

Sintassi per generare N ripetizioni di un pattern espresso in percentuale.

#### 5.1 Sintassi

```
[pattern_points, end_time, n_reps, interp?, time_dist?, wrap?]
```

| Posizione | Nome             | Tipo                       | Obbligatorio | Significato |
|-----------|------------------|----------------------------|--------------|-------------|
| 0         | `pattern_points` | lista di `[x%, y]` o `[x%, y, type]` | sì | pattern del ciclo, `x` in `[0, 100]`. Pattern points possono essere 3-tuple (vedi §2.6) |
| 1         | `end_time`       | numero                     | sì           | **tempo assoluto finale** del blocco compatto |
| 2         | `n_reps`         | intero `>= 1`              | sì           | numero di ripetizioni |
| 3         | `interp_type`    | str                        | no           | `'linear'` / `'cubic'` / `'step'`. Fa da default per i segmenti interni e per il gap inter-ciclo |
| 4         | `time_dist`      | str o dict                 | no           | distribuzione delle durate dei cicli |
| 5         | `wrap`           | bool                       | no           | se `True`, il gap inter-ciclo interpola da `v_finale` al primo `y` del ciclo successivo (loop chiuso). Default `False` (hold). Vedi §5.3.2 |

**Pattern con 3-tuple (issue #54):** ogni `seg_type` per-punto viene replicato in
ogni ciclo. Il gap tra fine ciclo N e inizio ciclo N+1 segue l'`interp_type`
globale (posizione 3), non il `seg_type` dell'ultimo punto pattern.

Punto cruciale di semantica: **`end_time` è il tempo assoluto finale, non la
durata del blocco**. Quando il formato compatto è usato in forma mista, la
durata effettiva è `end_time - time_offset`, dove `time_offset` è il tempo
dell'ultimo breakpoint scritto prima del blocco.

#### 5.2 Forme valide

**Tre elementi** (interp e distribuzione di default):

```yaml
volume: [[[0, -12], [50, 0], [100, -12]], 30, 6]
# 6 ripetizioni del pattern -12 -> 0 -> -12, distribuite uniformemente tra 0 e 30s
```

**Quattro elementi** (interp esplicita):

```yaml
volume: [[[0, -12], [50, 0], [100, -12]], 30, 6, 'cubic']
```

**Cinque elementi** (interp + distribuzione temporale):

```yaml
density: [[[0, 5], [100, 50]], 30, 8, 'linear', 'exponential']
```

**Sei elementi** (con `wrap` per loop chiuso):

```yaml
# Sawtooth ciclico: rampa continua da 0 a 1 in ogni ciclo, poi salta indietro
volume: [[[0, 0]], 30, 8, 'linear', null, true]
# pattern = un solo punto a (0, 0); wrap=true ricostruisce la rampa
# perche' a fine ciclo iniettiamo y=first_y=0 (no-op qui), ma il pattern
# minimale piu utile e [[0, 0], [50, 1]] con wrap=true:
density: [[[0, 0], [50, 1]], 30, 8, 'linear', null, true]
# ciclo: 0 -> 1 (meta ciclo) -> 0 (fine ciclo via wrap)
```

#### 5.3 Pattern percentuale

Le coordinate `x` del pattern sono in `[0, 100]` e rappresentano la posizione
relativa **all'interno del singolo ciclo**. Il sistema le mappa al tempo
assoluto al momento dell'espansione.

```yaml
# pattern triangolare con vertice al 25%
grain:
  duration: [[[0, 0.01], [25, 0.2], [100, 0.01]], 30, 10]
```

#### 5.3.1 Ultimo punto e copertura del ciclo

L'ultimo punto del pattern **non deve obbligatoriamente** essere `x = 100`. Il
sistema non valida questo vincolo: `x_pct` è interpretato letteralmente come
percentuale di `cycle_duration`.

Conseguenze:

- `x_finale = 100` → il pattern riempie l'intero ciclo, il primo punto del ciclo
  successivo segue immediatamente (a meno di `DISCONTINUITY_OFFSET`).
- `x_finale < 100` (es. `80`) → il pattern termina all'80% del ciclo. I
  rimanenti `20%` di `cycle_duration` mantengono per **hold** l'ultimo valore
  del pattern, fino al primo punto del ciclo successivo. Crea un gap costante
  intenzionale tra ripetizioni.
- `x_finale > 100` → il punto cade **oltre** la fine del ciclo, sovrapponendosi
  al ciclo successivo. Nessun guard: comportamento indefinito, ordine temporale
  dei breakpoint può rompersi. Da evitare.

```yaml
# pattern continuo: nessun gap tra cicli
density: [[[0, 0], [50, 50], [100, 0]], 30, 4]

# pattern con gap intenzionale: 20% di hold a 0 tra cicli
density: [[[0, 0], [50, 50], [80, 0]], 30, 4]
```

#### 5.3.2 `wrap` mode (loop chiuso)

Il sesto elemento `wrap` (bool, default `False`) controlla il **comportamento
del gap** quando `x_finale < 100`.

| Modo | Comportamento gap `[x_finale, 100%]` |
|------|--------------------------------------|
| `wrap=False` (default, hold) | Mantiene `v_finale` fino a inizio ciclo successivo |
| `wrap=True` (loop chiuso) | Interpola da `v_finale` al primo `y` del ciclo (`first_y`) seguendo `interp_type` globale. Applicato anche all'ultimo ciclo. |

Implementazione: iniezione di un breakpoint sintetico a `t = cycle_end -
DISCONTINUITY_OFFSET` con `y = first_y`. L'interpolazione del segmento
`[ultimo_pattern, sintetico]` segue `interp_type` (posizione 3).

**Esempio** — pattern `[[0, 0], [50, 1]]`, `n_reps=2`, `end_time=2`:

```
wrap=False (hold):                wrap=True (loop chiuso):
    1 ____                            1     /\        /\
       \                                   /  \      /  \
    0   \_____.____                    0  /    \____/    \____
       0  .5  1   1.5  2                 0  .5  1   1.5  2

ciclo 0: 0 -> 1 (a t=.5)         ciclo 0: 0 -> 1 (a t=.5)
         hold 1 fino t=1                  -> 0 (a t≈1, wrap)
ciclo 1: 0 -> 1 (a t=1.5)        ciclo 1: 0 -> 1 (a t=1.5)
         hold 1 fino t=2                  -> 0 (a t≈2, wrap)
```

**Use case tipici:**

- Sawtooth / ramp ciclici senza duplicare il primo punto come ultimo
- Modulazioni LFO-like continue tra ripetizioni
- Pattern minimali: `[[0, 0]]` + `wrap=true` genera una rampa che riparte ogni ciclo

**Edge cases:**

- `x_finale == 100`: nessun gap → nessun sintetico iniettato (no-op)
- `n_reps == 1` + `wrap=True`: un sintetico a fine ciclo unico (fade verso `first_y`)
- `time_dist != linear`: la pendenza del wrap varia per ciclo seguendo
  `cycle_durations` corrente (comportamento coerente)
- `interp='cubic'`: i breakpoint sintetici partecipano al calcolo Fritsch-Carlson
  → tangenti coerenti

#### 5.4 Comportamento ai bordi del ciclo

Il primo punto di ogni ciclo successivo al primo è traslato di
`DISCONTINUITY_OFFSET = 1e-6` secondi per evitare collisioni temporali tra
l'ultimo punto del ciclo precedente e il primo del successivo. È invisibile
all'orecchio ma garantisce che gli algoritmi di interpolazione operino su tempi
strettamente crescenti.

#### 5.5 Validazioni

- `n_reps < 1` → `ValueError` ("n_reps deve essere >= 1")
- `end_time <= time_offset` → `ValueError`
- `pattern_points` vuoto → `ValueError`

---

### 6. Distribuzioni temporali nei cicli

Il quinto elemento del formato compatto controlla come le durate dei cicli sono
distribuite all'interno del blocco. Definito in
`src/envelopes/time_distribution.py` tramite `TimeDistributionFactory`.

Vincolo invariante: `sum(cycle_durations) == total_duration`.

#### 6.1 Forme di specifica

**Default (omesso)** → equivale a `'linear'`.

**Stringa** (parametri di default):

```yaml
density: [[[0, 5], [100, 50]], 30, 8, 'linear', 'exponential']
```

**Dict** (parametri custom):

```yaml
density: [[[0, 5], [100, 50]], 30, 8, 'linear', {type: geometric, ratio: 1.5}]
```

#### 6.2 Distribuzioni disponibili

| Nome           | Alias       | Parametri        | Effetto musicale         |
|----------------|-------------|------------------|--------------------------|
| `linear`       | —           | nessuno          | durate uguali (default)  |
| `exponential`  | `exp`       | `rate=2.0`       | accelerando: cicli sempre più brevi |
| `logarithmic`  | `log`       | `base=2.0`       | ritardando: cicli sempre più lunghi |
| `geometric`    | `geo`       | `ratio=1.5`      | progressione geometrica; `ratio>1` ritardando, `ratio<1` accelerando |
| `power`        | —           | `exponent=2.0`   | power law configurabile  |

#### 6.3 Formule

Date `total_duration = T` e `n_reps = N`:

- **linear**: `cycle_i = T / N` per ogni `i`.
- **exponential** (rate `r`): pesi `w_i = r^(-i)`, normalizzati su `T`.
  Con `r>1` i pesi decrescono → cicli più brevi all'avanzare del tempo.
- **logarithmic** (base `b`): pesi `w_i = log_b(i+1) + 1`, normalizzati.
  I pesi crescono → cicli più lunghi nel tempo.
- **geometric** (ratio `r`): `dur_i = dur_0 * r^i`. Con `r ≈ 1` ricade in `linear`.
  Somma di progressione geometrica `dur_0 = T * (1-r) / (1 - r^N)`.
- **power** (esponente `e`): pesi `w_i = (i+1)^e`, normalizzati.

#### 6.4 Esempi parametrici

```yaml
# 8 cicli accelerando
density: [[[0, 5], [100, 50]], 30, 8, 'linear', 'exponential']

# 6 cicli ritardando con base 3
density: [[[0, 5], [100, 50]], 30, 6, 'linear', {type: logarithmic, base: 3}]

# 5 cicli progressivi: ogni ciclo dura 1.8 volte il precedente
grain:
  duration: [[[0, 0.01], [100, 0.2]], 30, 5, 'linear', {type: geometric, ratio: 1.8}]

# 10 cicli con power law forte: i cicli più tardi sono molto più lunghi
volume: [[[0, -12], [50, 0], [100, -12]], 30, 10, 'cubic', {type: power, exponent: 3.0}]
```

#### 6.5 Validazioni

- `n_reps < 1` → `ValueError`
- `total_duration <= 0` → `ValueError`
- `exponential.rate <= 0` → `ValueError`
- `logarithmic.base <= 1` → `ValueError`
- `geometric.ratio <= 0` → `ValueError`

---

### 7. Formato misto (breakpoint + cicli)

Una lista di envelope può combinare breakpoint standard `[t, v]` e blocchi
compatti `[pattern, end_time, n_reps, ...]`. Il sistema calcola l'offset
temporale di ciascun blocco compatto in base all'ultimo breakpoint precedente.

#### 7.1 Regola di offset

Per ogni elemento iterato:

- se è un breakpoint `[t, v]`: aggiorna `current_time = max(current_time, t)`
- se è un formato compatto: la sua durata effettiva è `end_time - current_time`,
  e dopo l'espansione `current_time` diventa il tempo dell'ultimo punto generato.

#### 7.2 Esempio commentato

```yaml
density: [
  [0, 10],                                # plateau iniziale
  [5, 10],
  [[[0, 30], [100, 50]], 25, 4],          # 4 cicli da t=5 a t=25
  [30, 5]                                 # discesa finale
]
```

Linea per linea:

1. `[0, 10]` e `[5, 10]`: plateau a 10 da t=0 a t=5
2. Blocco compatto: `end_time = 25`, `current_time = 5`, quindi durata
   effettiva `25 - 5 = 20s`, divisa in 4 cicli uniformi da 5s ciascuno; cicli
   centrati su `[5, 10]`, `[10, 15]`, `[15, 20]`, `[20, 25]`. Ogni ciclo
   ricalcola il pattern `[0%→30, 100%→50]` nella propria finestra.
3. `[30, 5]`: rampa finale da `(25, 50)` (ultimo punto compatto) a `(30, 5)`.

#### 7.3 Discontinuità al passaggio mista → compatto

Il primo punto del primo ciclo viene anch'esso traslato di
`DISCONTINUITY_OFFSET` se `time_offset > 0`, per separarlo dall'ultimo
breakpoint standard. Anche in questo caso è subaudio e necessaria per la
correttezza degli algoritmi.

#### 7.4 Limiti

Il formato compatto **non può essere annidato dentro un altro formato compatto**.
Può comparire solo come elemento di primo livello in una lista mista.

---

### 8. Comportamento ai bordi (hold)

Implementato in `NormalSegment` (`envelope_segment.py`).

- Per `t < start_time`: ritorna il valore del primo breakpoint.
- Per `t > end_time`: ritorna il valore dell'ultimo breakpoint.

L'integrazione su intervalli che eccedono i bordi somma:

1. il rettangolo `(first_value) × (start_time - from_t)` se `from_t < start_time`
2. l'integrale interpolato sul segmento attivo
3. il rettangolo `(last_value) × (to_t - end_time)` se `to_t > end_time`

Questo comportamento garantisce che un envelope definito su `[0, 30]` ma valutato
a `t = 45` ritorni semplicemente l'ultimo valore, senza errori. È un design
deliberato: gli stream con `duration > envelope.end_time` non vanno in errore.

---

### 9. Espressioni matematiche nei valori

Il loader YAML (`Generator._eval_math_expressions`) valuta espressioni racchiuse
tra parentesi prima di passare il dato al parser envelope. Funzioni e costanti
ammesse: `abs`, `int`, `float`, `min`, `max`, `pow`, `pi`, `e`.

Sintassi:

```yaml
volume: [[0, -12], [(pi*5), 0], [(10*3), -12]]
grain:
  duration: (1/20)
  duration_range: (pi/100)
pitch:
  ratio: (2**(7/12))                 # ratio del semitono x7
```

L'espressione è valutata a parse-time, non a run-time: il risultato è un numero
che diventa parte del breakpoint. Non è quindi modulabile dinamicamente.

---

### 10. Casi speciali per dominio

#### 10.1 Loop pointer e `loop_unit`

`loop_start`, `loop_end`, `loop_dur`, e `start` accettano envelope. In più,
hanno una semantica di unità separata controllata da `loop_unit`:

```yaml
pointer:
  loop_unit: normalized              # i VALORI Y vengono scalati per sample_dur_sec
  loop_start: 0.0                    # = 0.0 * sample_dur_sec
  loop_dur:   0.5                    # = 0.5 * sample_dur_sec
```

Con envelope normalizzato sui valori:

```yaml
pointer:
  loop_unit: normalized
  loop_start: [[0, 0.0], [30, 0.8]]  # da 0% a 80% della durata del sample
```

Internamente `PointerController._pre_normalize_loop_params` usa
`Envelope._scale_raw_values_y` per moltiplicare ogni Y dei breakpoint per
`sample_dur_sec` prima di costruire l'`Envelope`. Funziona anche su formati
compatti: il pattern `[x%, y]` viene scalato sul valore.

Differenza chiave da `time_mode`:

- `time_mode: normalized` scala l'asse **X** (tempo) usando la `duration` dello stream
- `loop_unit: normalized` scala l'asse **Y** (valore) usando la `sample_dur_sec`
  del file audio caricato

I due possono coesistere.

#### 10.2 `dephase` come envelope

`dephase` può essere booleano, numerico, envelope, o dict. Quando è envelope, la
probabilità di applicare la randomness al parametro varia nel tempo.

**Globale**:

```yaml
dephase: [[0, 0], [30, 80]]          # probabilità: 0% all'inizio, 80% alla fine
```

**Per chiave**:

```yaml
dephase:
  volume: [[0, 0], [30, 80]]
  pan: 50
  duration: {type: cubic, points: [[0, 0], [15, 100], [30, 0]]}
```

Vedi `GateFactory._classify_dephase`: il dispatch usa
`Envelope.is_envelope_like` per riconoscere il formato e crea un
`EnvelopeGate` invece di un `RandomGate` scalare.

#### 10.3 `voices.*.curve` per window transition

Il campo `curve` dentro `grain.envelope.transition` e `grain.envelope.multistate`
è un envelope a tutti gli effetti. Il valore mappa il tempo `[0, T]` a un blend
`[0, 1]` che guida la transizione tra le finestre. Accetta tutte le forme
documentate qui.

```yaml
grain:
  envelope:
    from: hanning
    to: expodec
    curve: [[0, 0], [15, 0.3], [30, 1]]
```

Validazione specifica (`_validate_curve_range` in `window_selection_strategy.py`):
se `time_mode = normalized` il curve deve coprire `[0, 1]`; se assoluto, deve
coprire `[0, duration]`. Eccedenze sollevano `InvalidStrategyConfigError`.
Curve più corte del range valido emettono solo un warning: l'ultimo valore viene
mantenuto fino alla fine (hold).

#### 10.4 Voice strategy parameters

> Origine: [plans/done/2026-04-25-002-feat-dynamic-strategy-params-plan.md](../plans/done/2026-04-25-002-feat-dynamic-strategy-params-plan.md)

Tutti i parametri scalari delle voice strategy (`step`, `pitch_range`,
`pointer_range`, `max_offset`, `base`, `spread`) accettano envelope. Il parsing
avviene in `Stream._init_voice_manager` via `_parse_strategy_kwarg`, che usa
`Envelope.is_envelope_like` per discriminare.

```yaml
voices:
  num_voices: 4
  pitch:
    strategy: step
    step: [[0, 0], [30, 12]]         # cluster monofonico → ottava aperta
  pan:
    strategy: linear
    spread: [[0, 0], [30, 120]]      # tutte centrate → spread ampio
```

#### 10.5 `num_voices` come envelope

`num_voices` è un caso particolare: viene parsato come `Parameter` che ammette
envelope, ma il `VoiceManager` pre-alloca `max_voices` pari al picco massimo dei
breakpoint (vedere `Stream._init_voice_manager`). Le voci eccedenti il valore
istantaneo di `num_voices(t)` non vengono renderizzate al tempo `t`.

```yaml
voices:
  num_voices: [[0, 1], [30, 8]]      # da 1 a 8 voci linearmente
```

---

### 11. Validazione e bounds

Dopo il parsing, ogni envelope passa attraverso `GranularParser._validate_and_clip`.
Il sistema valida ciascun breakpoint Y contro i bounds del parametro (definiti
in `parameter_definitions.py`).

Due modalità (`CLIP_LOG_CONFIG['validation_mode']`):

- **strict** (default): qualsiasi breakpoint fuori bounds solleva
  `ParameterBoundError` con elenco delle violazioni. Build interrotta.
- **permissive**: i valori vengono clippati, ogni violazione produce un warning
  nel log clip.

Esempio di errore con envelope su `pitch.semitones` (bounds `[-36, 36]`):

```yaml
pitch:
  semitones: [[0, 0], [10, 48], [30, -42]]
```

```
[ERRORE] Envelope 'pitch_semitones' fuori bounds
  Bounds:       [-36, 36]
  t=10: value=48
  t=30: value=-42
  Stream:       s1
  Config:       configs/PGE_test.yml
```

Per i parametri con `max_val=None` nel registro (es. `loop_start`, `loop_dur`),
il bound effettivo è risolto dinamicamente a `sample_dur_sec` quando l'envelope
viene istanziato.

---

### 12. Tabella riassuntiva delle sintassi

Sintesi di tutte le forme accettate. `T` indica il tempo, `V` il valore.

| Forma                                         | Esempio                                            | Note |
|-----------------------------------------------|----------------------------------------------------|------|
| Scalare                                       | `density: 10`                                      | Valore costante, non è envelope |
| Lista breakpoint                              | `[[0, 5], [10, 40], [30, 5]]`                      | Linear di default |
| Dict completo                                 | `{type: cubic, points: [[0, 0], [1, 1]]}`          | Selezione esplicita di interpolazione |
| Dict con time_mode locale                     | `{type: linear, points: [...], time_mode: normalized}` | Override del time_mode dello stream |
| Dict con `time_unit` (alias)                  | `{points: [...], time_unit: normalized}`           | Sinonimo di `time_mode` |
| Formato compatto 3 elem                       | `[[[x%, y], ...], end_time, n_reps]`               | Default linear, distribuzione linear |
| Formato compatto 4 elem                       | `[[[x%, y], ...], end_time, n_reps, interp]`       | `interp ∈ {linear, cubic, step}` |
| Formato compatto 5 elem                       | `[[[x%, y], ...], end_time, n_reps, interp, dist]` | `dist`: stringa o dict |
| Distribuzione dist come stringa               | `..., 'exponential']`                              | Parametri di default |
| Distribuzione dist come dict                  | `..., {type: geometric, ratio: 1.5}]`              | Parametri custom |
| Formato misto                                 | `[[0, 10], [5, 10], [[[0, 30], [100, 50]], 25, 4]]`| Offset automatico |
| Loop pointer normalizzato (valori)            | `loop_unit: normalized` + `loop_start: 0.0`        | Scala Y per sample_dur_sec |
| Time mode globale                             | `time_mode: normalized` a livello stream           | Scala X per stream duration |
| Espressione matematica                        | `[[0, 0], [(pi*5), 1]]`                            | Valutata a parse-time |
| dephase globale envelope                      | `dephase: [[0, 0], [30, 80]]`                      | Probabilità time-varying |
| dephase per chiave envelope                   | `dephase: {volume: [[0, 0], [30, 80]]}`            | Override per parametro |
| curve in window transition                    | `envelope: {from: ..., to: ..., curve: [...]}`     | Curve è envelope a tutti gli effetti |

---

### Appendice: ordine di elaborazione

Per chi volesse ispezionare il pipeline interno, l'ordine di trasformazione di
un envelope dal YAML al runtime è:

1. **YAML loader**: `yaml.safe_load`
2. **Math eval**: `Generator._eval_math_expressions` valuta `(pi)`, `(10/3)`, ecc.
3. **Detection**: `Envelope.is_envelope_like` decide se è un envelope o scalare.
4. **Time scaling**: `create_scaled_envelope` applica `time_mode` (se normalized).
5. **Value scaling**: `Envelope._scale_raw_values_y` per `loop_unit` (asse Y).
6. **Expansion**: `EnvelopeBuilder.parse` espande formati compatti e misti.
7. **Type extraction**: `EnvelopeBuilder.extract_interp_type` legge il tipo dal
   formato compatto se presente, altrimenti default `linear`.
8. **Tangent computation**: `_compute_fritsch_carlson_tangents` solo per cubic.
9. **Segment construction**: `NormalSegment` con strategy e context (tangenti).
10. **Validation**: `_validate_and_clip` controlla ogni breakpoint contro i bounds.
11. **Runtime evaluation**: `Envelope.evaluate(t)` delega al segmento, che a sua
    volta delega alla strategy di interpolazione.

---

### Riferimenti sorgente

- `src/envelopes/envelope.py` — classe `Envelope`, `is_envelope_like`,
  `create_scaled_envelope`, `_scale_raw_values_y`
- `src/envelopes/envelope_builder.py` — `EnvelopeBuilder.parse`,
  `_is_compact_format`, `_expand_compact_format`, `DISCONTINUITY_OFFSET`
- `src/envelopes/envelope_interpolation.py` — `LinearInterpolation`,
  `StepInterpolation`, `CubicInterpolation`
- `src/envelopes/envelope_segment.py` — `NormalSegment` con hold behavior
- `src/envelopes/envelope_factory.py` — `InterpolationStrategyFactory`
- `src/envelopes/time_distribution.py` — `TimeDistributionFactory` e le 5 strategie
- `src/parameters/parser.py` — `GranularParser.parse_parameter` + validazione
- `src/parameters/gate_factory.py` — uso di envelope per `dephase`
- `src/controllers/pointer_controller.py` — `loop_unit` e scaling dei valori loop
- `src/controllers/window_selection_strategy.py` — `_validate_curve_range`
- `src/core/stream.py` — `_parse_strategy_kwarg` per envelope nelle voice strategy

---

## Tabella Bounds Parametri

| Parametro | Min | Max | Default | Note |
|-----------|-----|-----|---------|------|
| `density` | 0.01 | 4000 | — | grani/secondo |
| `fill_factor` | 0.001 | 50 | 2.0 | priorità su density |
| `distribution` | 0 | 1 | 0.0 | 0=sync, 1=async |
| `grain_duration` | 0.001 | 10 | 0.05 | secondi |
| `volume` | -120 | 12 | 0.0 | dB |
| `pan` | -3600 | 3600 | 0.0 | gradi |
| `pitch_ratio` | 0.125 | 8 | 1.0 | 3 ottave ↓/↑ |
| `pitch_semitones` | -36 | 36 | 0 | ±3 ottave |
| `pointer_speed_ratio` | -100 | 100 | 1.0 | negativo = indietro |
| `pointer_deviation` | -1 | 1 | 0.0 | offset per-grano |
| `loop_start` | 0 | sample_dur | — | secondi |
| `loop_end` | 0 | sample_dur | — | secondi |
| `loop_dur` | 0.005 | sample_dur | — | secondi |
| `num_voices` | 1 | 64 | 1 | intero |
| `scatter` | 0 | 1 | 0.0 | 0=sync, 1=indip. |

Per la sintassi completa multi-voice, vedere [[multi-voice]].
Per la sintassi envelope (in ogni parametro che la accetta), vedere la sezione
[Envelopes](#envelopes) interna a questo doc.
