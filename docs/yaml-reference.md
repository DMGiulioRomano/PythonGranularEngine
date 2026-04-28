# YAML Reference — PythonGranularEngine

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
```

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
volume: -6.0                       # dB, default -6.0
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

`semitones` e `ratio` sono mutuamente esclusivi. `semitones` ha priorità.

```yaml
pitch:
  ratio: 1.0              # rapporto di trasposizione (default 1.0 = no trasposizione)
  ratio: [[0, 0.5], [30, 2.0]]
  range: 0.1              # ±variazione random intorno a ratio

  semitones: 0            # trasposizione in semitoni (intero o float)
  semitones: [[0, -12], [30, 12]]
  range: 6                # ±variazione random in semitoni (intera)
```

Bounds: `pitch_ratio` ∈ [0.125, 8], `pitch_semitones` ∈ [-36, 36].

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

# range: voci distribuite linearmente in [0, semitone_range]
voices:
  pitch:
    strategy: range
    semitone_range: 12.0  # range totale in semitoni (scalare o envelope)

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
    semitone_range: 6.0   # magnitudine massima (scalare o envelope)

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

## Tabella Bounds Parametri

| Parametro | Min | Max | Default | Note |
|-----------|-----|-----|---------|------|
| `density` | 0.01 | 4000 | — | grani/secondo |
| `fill_factor` | 0.001 | 50 | 2.0 | priorità su density |
| `distribution` | 0 | 1 | 0.0 | 0=sync, 1=async |
| `grain_duration` | 0.001 | 10 | 0.05 | secondi |
| `volume` | -120 | 12 | -6.0 | dB |
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

Per la sintassi completa multi-voice, vedere `docs/multi-voice.md`.
