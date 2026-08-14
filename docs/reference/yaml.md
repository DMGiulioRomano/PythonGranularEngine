---
slug: yaml
type: reference
status: stable
tags: [yaml, syntax, parameters, envelopes]
sources:
  - src/pge/engine/generator.py
  - src/pge/core/stream.py
  - src/pge/parameters/
  - src/pge/strategies/
  - src/pge/envelopes/
  - src/pge/shared/seeding.py
  - src/pge/shared/distribution_strategy.py
last_synced_commit: 0e23016
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

Reference completa del formato YAML consumato da `main.py`: sintassi per stream, parametri, envelope, voci, finestre, deviation_probability. Copre solo il **formato di input**: la pipeline di rendering è in [[architecture]], le voice strategy in [[multi-voice]].

## Sintassi

Sezioni rilevanti in questo doc:

- [Minimal Stream](#minimal-stream) — schema minimo
- [Seed (Riproducibilità)](#seed-riproducibilità) — render NumPy riproducibili;
  `rng_group` per condividere la sequenza fra stream
- [Parameter Syntax](#parameter-syntax) — scalari, tuple, dict, envelope
- [Campi Obbligatori di Stream](#campi-obbligatori-di-stream)
- [Configurazione Processo (StreamConfig)](#configurazione-processo-streamconfig)
- [La banda dei `_range`](#la-banda-dei-_range-distribution_mode-e-range_anchor) —
  larghezza, forma (`distribution_mode`), ancora (`range_anchor`)
- [Blocco Grain](#blocco-grain), [Pointer](#blocco-pointer), [Pitch](#blocco-pitch), [DeviationProbability](#deviation_probability-variazione-stocastica)
- [Blocco Voices (Multi-Voice)](#blocco-voices-multi-voice)
- [Envelopes](#envelopes) — sintassi envelope completa

## Bounds

Tabella bounds per ogni parametro: [Tabella Bounds Parametri](#tabella-bounds-parametri). Per `clip_strategy` e `ParameterBoundError` vedi [[errors]].

## Esempi

Esempi runnable: [Esempi Completi](#esempi-completi). Casi envelope: sezione [Envelopes](#envelopes).

## Versionato da

- `src/yaml_parser/` — parser
- `src/pge/parameters/parameter_definitions.py`, `src/pge/parameters/parameter_schema.py` — bounds e schema
- `src/pge/shared/distribution_strategy.py` — banda dei `_range`: distribuzioni e `range_anchor`
- `src/pge/envelopes/` — sintassi envelope
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

## Seed (Riproducibilità)

Chiave **top-level** opzionale (sibling di `streams`) per render riproducibili
con il renderer NumPy.

```yaml
seed: 42        # opzionale; assente → comportamento attuale (non riproducibile)
streams:
  - stream_id: "s1"
    onset: 0.0
    duration: 30
    sample: "sample.wav"
```

- **Presente**: lo stesso YAML produce lo stesso render NumPy fra processi
  diversi.
- **Assente** (default): il Generator genera un **seed di sessione** dal
  timestamp e lo logga (`[SEED] ... seed di sessione N`). Il run resta non
  riproducibile a priori (ogni run ha un seed diverso), ma è **ricostruibile a
  posteriori**: aggiungendo `seed: N` allo YAML si riottiene lo stesso render.

Tutti i siti stocastici usano **RNG locali derivati per componente**
(`src/pge/shared/seeding.py`, issue #154): nessun random globale condiviso.

- **RNG per-componente** — ogni sito pesca dal proprio generatore derivato via
  `hashlib.sha256(f"{seed}:{stream_id}:{componente}")`, deterministico e
  indipendente da `PYTHONHASHSEED`. Componenti: il nome del parametro per la
  variazione `_range` (es. `grain_duration`, `pitch_semitones`),
  `gate:<chiave>` per i gate di probabilità (deviation_probability), `iot` per la
  distribuzione Truax async, `window` per la selezione finestra, `detune` per
  il detune implicito EDO.
- **RNG locale delle voci stocastiche** (`voices.{pitch,onset,pointer,pan}` con
  `strategy: stochastic`) — invariato (issue #81): seed derivato via
  `hashlib.sha256(f"{seed}:{stream_id}:{voice_index}")`.

Conseguenze della derivazione per-componente:

- `solo`/`mute` **non alterano** i grani degli stream superstiti: il solo fa
  ascoltare in isolamento esattamente quello che suona nel mix.
- La cache stems (`STEMS=true CACHE=true`) è coerente col seed: i grani di uno
  stream dirty non dipendono da quali altri stream sono clean in quel run.
- I render con seed sopravvivono ai refactor che non toccano il componente
  specifico (aggiungere un draw a un componente non shifta gli altri).
- Ogni componente è testabile in isolamento con gli stessi valori del render.

`seed: 0` è un valore valido e distinto da assente. Sono accettati interi (anche
negativi) e stringhe.

**Breaking (issue #154):** i render con `seed:` fissato prodotti col vecchio
schema (`random.seed` globale, issue #81) NON sono riproducibili dopo il
passaggio alla derivazione per-componente: i valori per-grano cambiano una
volta. I render senza seed non cambiano di natura.

**Limite (Csound):** `seed` governa solo il random di Python (renderer NumPy).
Csound ha un RNG proprio: con `--renderer csound` i due renderer NON sono
bit-identici nemmeno col seed. Le tendency mask restano stocastiche per natura —
l'obiettivo è riprodurre *lo stesso run*, non l'identità bit-a-bit.

### Condividere la sequenza fra stream: `rng_group`

Chiave **per-stream** opzionale (issue #169). Di default lo `stream_id` è
dentro l'hash di derivazione: due stream non possono pescare la stessa
sequenza nemmeno con lo stesso `seed` (isolamento voluto da #154).
`rng_group` sostituisce lo `stream_id` come **identità** della derivazione:
gli stream che dichiarano lo stesso gruppo condividono le sequenze
pseudo-casuali di tutti i componenti (variazioni `_range`, gate, `iot`,
`window`, `detune`) e delle voci stocastiche.

```yaml
seed: 1988
streams:
  - stream_id: "cugini_1"
    rng_group: "cugini"    # stessa identità RNG di cugini_2
    # ...
  - stream_id: "cugini_2"
    rng_group: "cugini"
    # ...
```

- **Assente** (default): identità = `stream_id`, hash **identico a prima di
  #169** — nessun render esistente cambia bit-per-bit.
- **Presente**: identità = valore del gruppo. La derivazione diventa
  `sha256(f"{seed}:{rng_group}:{componente}")` (e
  `...:{voice_index}` per le voci).
- Caso d'uso: stream "cugini" (spread su `pointer.start`/`pan`) letti come un
  unico oggetto verticale, con la stessa griglia stocastica di `distribution`.
- **Limite**: identità condivisa NON significa griglia temporale identica. Il
  draw dell'IOT async avviene per grano e dipende da `avg_iot`: con `density`
  o `distribution` diverse i due stream si desincronizzano subito pur
  condividendo l'RNG. Griglia identica solo con density e distribution
  identiche.
- `rng_group` **entra nel fingerprint** della cache stems
  (`StreamCacheManager.compute_fingerprint`): cambiarlo cambia i valori
  pescati, quindi l'audio, e lo stem viene giustamente marcato dirty. Le
  sole chiavi escluse dal fingerprint restano `solo`/`mute`, che non
  toccano l'audio del singolo stem (issue #108).
- L'invarianza di `solo`/`mute` garantita da #154 resta intatta: la
  condivisione riguarda l'identità di derivazione, non i draw a runtime —
  ogni stream materializza la propria copia della sequenza, quindi mettere
  un cugino in solo non sposta i grani degli altri.

---

## Parameter Syntax

Qualsiasi parametro numerico accetta le seguenti forme:

| Forma | Esempio | Comportamento |
|-------|---------|--------------|
| Scalare | `density: 10` | Valore fisso |
| Envelope lineare | `density: [[0, 10], [1, 50]]` | Interpolazione lineare tra breakpoint `[time, value]` |
| Envelope annidata | `density: [[[0, 5], [10, 50]], 1.0, 5]` | Envelope di envelope |
| Variazione | `grain: {duration: 0.05, duration_range: 0.01}` | banda larga `0.01` (default: `±0.005`) |
| Espressione math | `onset: (pi)`, `duration: (10/2)` | Valutato via `safe_eval` |
| Envelope normalizzato | `step: {points: [[0, 0], [1, 12]], time_mode: normalized}` | `[0, 1]` mappato su `duration` |
| Envelope per-punto interp | `density: [[0, 5, 'cubic'], [0.5, 30, 'step'], [1, 5]]` | `type` per-segmento, override del default globale (issue #54) |
| Envelope dict per-punto | `density: {points: [{t:0, v:5, type:cubic}, {t:1, v:5}]}` | Forma dict equivalente di per-punto interp |
| Envelope BP group | `density: [[[[0, 0], [0.4, 8]], 'cubic'], [[[0.75, 6], [1, 0]], 'step']]` | Macrozone di breakpoint con interp proprio (issue #64) |

---

## Campi Obbligatori di Stream

```yaml
streams:
  - stream_id: "nome_univoco"   # stringa identificativa
    onset: 0.0                  # tempo di inizio in secondi (assoluto)
    sample: "file.wav"          # nome file (cercato in Media/)
```

Le condizioni di esistenza di uno stream sono tre. `onset` resta obbligatorio:
la posizione in timeline non è deducibile da nulla.

### `duration` opzionale

`duration` è un campo **opzionale**: se assente vale la durata del file audio
dichiarato in `sample`.

```yaml
streams:
  - stream_id: "risintesi"      # dura quanto il sample
    onset: 0.0
    sample: "file.wav"

  - stream_id: "scelta"         # override compositivo esplicito
    onset: 0.0
    duration: 30.0
    sample: "file.wav"
```

A riposo lo stream risintetizza il sample, quindi l'unica durata non arbitraria
è quella del file: ogni altro valore è una scelta compositiva, e le scelte
compositive stanno bene come override espliciti.

| Dichiarazione | Durata dello stream |
|---------------|---------------------|
| chiave assente | durata del sample |
| `duration: null` | durata del sample (come chiave assente) |
| `duration: 30.0` | 30.0 s (l'esplicito vince sempre) |
| `duration: 0` | 0 s — nessun grano generato, il default **non** scatta |

Con `time_mode: normalized` l'asse `0.0`–`1.0` degli envelope è mappato sulla
durata risolta: senza `duration`, copre l'intero sample.

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

deviation_probability: false          # Controllo variazione stocastica (vedi sezione DeviationProbability)

range_always_active: false  # true: i _range sono sempre attivi anche senza deviation_probability

distribution_mode: uniform  # "uniform" (default) | "gaussian"
                            # COME la banda del range viene riempita

range_anchor: center    # "center" (default) | "min"
                        # DOVE cade il valore base dentro la banda

time_scale: 1.0         # fattore di scala temporale globale (default 1.0)

clip_strategy: overflow_margin  # "overflow_margin" (default) | "passthrough"
                                # Decide quali grain entrano in stream.voices
clip_margin: 0.0        # tolleranza in secondi per la coda dei grain (default 0.0)
```

### La banda dei `_range`: `distribution_mode` e `range_anchor`

Ogni parametro con un `_range` associato produce, per ogni grano, un valore
pescato dentro una **banda**. La banda si descrive con tre concetti ortogonali,
che vanno tenuti distinti:

| concetto | chiave | cosa decide |
|---|---|---|
| larghezza | il valore del `_range` stesso | quanto è larga la banda |
| forma | `distribution_mode` | come la banda viene riempita |
| ancora | `range_anchor` | dove cade `base` dentro la banda |

**`range` è sempre la larghezza della banda**, in ogni distribuzione e in
entrambe le ancore. Non è mai una deviazione standard, non è mai una semi-ampiezza.

```yaml
range_anchor: center   # default — banda [base - range/2, base + range/2]
range_anchor: min      # banda [base, base + range]: base è il MINIMO
```

Con `base: 300` e `range: 200`:

| `distribution_mode` | `range_anchor` | banda | dove si addensa |
|---|---|---|---|
| `uniform` | `center` | 200 … 400 | piatta |
| `uniform` | `min` | 300 … 500 | piatta |
| `gaussian` | `center` | 200 … 400 | picco a 300 |
| `gaussian` | `min` | 300 … 500 | picco a 400 |

La gaussiana è **troncata**: σ = larghezza/6, quindi i bordi della banda cadono
a 3σ dalla media, e la coda oltre i bordi (~0.3%) viene appiattita sull'estremo
invece di uscire. Nessun campione cade fuori dalla banda dichiarata.

**Cosa governa `range_anchor`.** Tutti e soli i `_range` che passano da
`Parameter`: `volume_range`, `pan_range`, `grain.duration_range`,
`pointer.offset_range`, `pitch.range`. Vale anche per il pitch quantizzato
(unità EDO): con `min` gli step interi partono da `base` e salgono.

**Cosa NON governa**, e resta simmetrico in ogni caso:

- il **jitter implicito** (`ParameterBounds.default_jitter`, attivo sotto
  deviation_probability quando *non* c'è un `_range` dichiarato) — è un tremolio attorno al
  valore, non una banda dichiarata: non c'è nessun `range` scritto da
  reinterpretare, e ancorarlo al minimo lo renderebbe un offset positivo
  sistematico;
- il **detune implicito del pitch** (`±12 cents`, vedi
  [Detune implicito](#detune-implicito-del-pitch-senza-range)) — stessa ragione;
- lo **spread delle voice strategy** (`spread`, `pitch_range`, `pointer_range`):
  non sono `_range` di un parametro, non hanno una `base` di cui essere il minimo.

**Bounds.** Con `range_anchor: min` la banda arriva a `base + range`, quindi il
tetto può sforare `max_val` dove la versione centrata (`base + range/2`) non lo
faceva. Il motore lo verifica **al parse** e solleva `ParameterBoundError`
invece di lasciare che il safety clamp schiacci la banda contro il tetto. Il
controllo scatta quando il massimo è calcolabile esattamente (scalare+scalare,
envelope+scalare, scalare+envelope); con base e range entrambi envelope il
massimo della somma non è la somma dei massimi, quindi resta il solo clamp.

> **Cambio di comportamento (post v5.2.0).** Fino alla v5.2.0 `gaussian` leggeva
> `range` come **σ**, con la campana illimitata richiusa solo dal clamp ai bounds
> del parametro: `range: 200` su `base: 300` produceva valori grosso modo fra 0 e
> 600. Ora produce 200…400. `uniform` non cambia. Chi usava `distribution_mode:
> gaussian` e vuole un'escursione paragonabile a prima deve moltiplicare il
> proprio `range` per circa 6.

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
volume_range: 3.0                  # banda larga 3 dB attorno al valore
                                   # (con range_anchor: min → da 0 a +3 dB)

pan: 0.0                           # gradi, 0 = centro, ±180 = estremi
pan: [[0, -90], [30, 90]]
pan_range: 30.0                    # banda larga 30° attorno al valore
```

I `_range` sono larghezze di banda: dove cade il valore base dentro la banda
lo decide `range_anchor` (default `center` → `±range/2`). Vedi
[La banda dei `_range`](#la-banda-dei-_range-distribution_mode-e-range_anchor).

Bounds: `volume` ∈ [-120, 12], `pan` ∈ [-3600, 3600].

---

## Blocco Grain

```yaml
grain:
  duration: 0.05           # secondi, default 0.05
  duration: [[0, 0.02], [30, 0.2]]
  duration_range: 0.01     # banda larga 0.01 s (default: ±0.005 s)

  # Unità di misura per duration e duration_range: seconds (default) |
  # samples | milliseconds. La conversione avviene al parse e vale per
  # scalari ed envelope (solo i valori, l'asse tempo resta invariato).

  # 'samples': campioni alla frequenza di output del motore (48000 Hz).
  duration_unit: samples
  duration: 512            # 512 campioni = 512/48000 s
  duration_range: 64       # banda larga 64 campioni (default: ±32)
  duration: [[0, 48], [30, 4800]]   # envelope: Y in campioni

  # 'milliseconds': fattore fisso 1e-3, indipendente dal sample rate.
  # È la scala comoda per la grana udibile, dove in secondi si scriverebbero
  # solo numeri molto piccoli.
  duration_unit: milliseconds
  duration: 50             # 50 ms = 0.05 s
  duration_range: 4.5      # banda larga 4.5 ms (default: ±2.25 ms)
  duration: [[0, 1], [30, 100]]     # envelope: Y in millisecondi

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

Con qualunque `duration_unit` diverso da `seconds` la `grain.duration` va
**sempre indicata esplicitamente**: il default `0.05` è in secondi e non
verrebbe convertito, per cui base (secondi) e `duration_range` (campioni o
millisecondi) finirebbero in domini diversi. Ometterla → `MissingFieldError`.
`output_sr` è una config globale del motore (48000 Hz), non impostabile
per-stream nello YAML — per questo `milliseconds`, che non lo usa, dà le stesse
durate a qualunque frequenza di rendering mentre `samples` no.

Bounds: `grain_duration` ∈ [1 campione (`1/48000` s), 10 s] — in `samples`:
[1, 480000]; in `milliseconds`: [1/48, 10000]. Valori frazionari sono ammessi
in ogni unità: il renderer arrotonda al campione più vicino
(`n_out = max(1, round(dur * sr))`).

Note sui grani a precisione di campione:

- **Finestre simmetriche su grani di 2-3 campioni**: `hanning`, `bartlett`,
  `blackman`, `half_sine`, `sinc` hanno estremi nulli — a 2 campioni il grano
  è silenzio, a 3 sopravvive solo il campione centrale. È la matematica della
  finestra, non un bug. Per grani ultra-corti usare `rectangle` (piatta),
  `hamming` (estremi 0.08) o la famiglia `expodec` (parte da 1.0).
- **Divergenza NumPy/Csound**: il renderer NumPy campiona la finestra a
  `n_out` punti (`hanning` a 1 campione = `[1.0]`, impulso pieno); Csound
  legge la tabella finestra con `poscil` a `1/p3` Hz e su un grano di 1
  campione ne legge solo il primo punto (per `hanning` = 0, grano silente).
  I due renderer non sono mai stati dichiarati bit-equivalenti; a queste
  durate la scelta della finestra domina il risultato.
- **Densità derivata**: con `fill_factor` e grani da 1 campione la density
  `fill_factor/duration` satura al bound massimo (4000 g/s).

---

## Blocco Pointer

Controlla la posizione di lettura nel sample sorgente.

```yaml
pointer:
  start: 0.0              # posizione iniziale in secondi (default 0.0)
                          # SCALARE: non accetta envelope — il pointer lo somma
                          # alla posizione calcolata, non lo valuta nel tempo
  speed_ratio: 1.0        # velocità di lettura (default 1.0)
                          # 1.0 = velocità normale, -1.0 = indietro, 2.0 = doppia
                          # supporta envelope: [[0, 1.0], [30, 2.0]]

  offset_range: 0.0       # deviazione per-grano: banda larga offset_range
                          # attorno a 0 (con range_anchor: min → da 0 in su,
                          # cioè sempre in avanti).
                          # scalata sulla finestra di loop attiva e CONFINATA al
                          # suo interno (wrap modulare). Senza loop: scala e wrap
                          # sull'intero file.

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

### Confinamento al loop

Con un loop attivo, la posizione finale di ogni grano — base + `offset_range` +
offset di pointer delle voci — è **confinata dentro la finestra di loop** tramite
wrap modulare: i grani leggono solo da `[loop_start, loop_end)`, mai dal resto del
file. Senza loop la finestra coincide con l'intero file (scala e wrap su
`sample_dur_sec`). La coda di un grano che parte vicino a `loop_end` può comunque
estendersi oltre il confine per la durata del grano: è confinato il punto di
lettura, non l'intervallo coperto.

**Loop a cavallo della fine del file:** si esprime solo con `loop_dur`. Se
`loop_start + loop_dur` supera `sample_dur_sec`, la finestra prosegue dall'inizio
del file (es. `loop_start: 0.9`, `loop_dur: 0.3`, `loop_unit: normalized` → legge
`[0.9·dur, dur) ∪ [0, 0.2·dur)`). Con `loop_end` non è possibile: il valore è
vincolato a `[0, sample_dur_sec]`.

**Validazione:** `loop_end <= loop_start` (bound statici) →
`InvalidFieldValueError`. Per un loop a cavallo usa `loop_dur`. I bound dinamici
(envelope) non sono validati sull'ordine, perché può variare nel tempo.

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
| `ratio` | ratio diretto | — | [0.001, 8] |

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
  range: 0.1              # larghezza della banda di variazione random
                          # (range_anchor: center → ±0.05 intorno a ratio)

  semitones: 0            # trasposizione in semitoni (intero o float)
  semitones: [[0, -12], [30, 12]]
  range: 6                # larghezza della banda in semitoni, step interi
                          # (range_anchor: min → da base a base+6 semitoni)

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

## DeviationProbability (Variazione Stocastica)

`deviation_probability` controlla la probabilità di applicare variazioni stocastiche per-grano.
Si applica a tutti i parametri che hanno un `_range` associato. Decide **se** la
variazione avviene; la banda dentro cui il valore viene pescato la decidono
`distribution_mode` e `range_anchor` (vedi
[La banda dei `_range`](#la-banda-dei-_range-distribution_mode-e-range_anchor)).

```yaml
# Disabilitato (default): range attivi solo se presenti
deviation_probability: false

# Implicito: usa probabilità di default (1%)
deviation_probability: null

# Globale: probabilità uniforme per tutti i parametri (0–100)
deviation_probability: 50

# Globale con envelope: probabilità che varia nel tempo
deviation_probability: [[0, 0], [30, 80]]

# Specifico per parametro: probabilità diverse per ciascuno
deviation_probability:
  volume: 30          # 30% probabilità di applicare volume_range
  pan: 50             # 50% probabilità di applicare pan_range
  duration: 20        # 20% probabilità di applicare duration_range
  pitch: 10           # 10% per pitch range
  pointer: 40         # 40% per pointer offset_range
  reverse: 5          # 5% probabilità di flip reverse
  envelope: 15        # 15% probabilità di cambiare finestra (se lista)

# Valore specifico come envelope
deviation_probability:
  volume: [[0, 0], [30, 80]]
  pan: 50
```

> **Default in modalità per-parametro.** Una chiave **assente** dal dict — o
> impostata esplicitamente a **`null`** — non riceve probabilità: si comporta come
> `deviation_probability: false` per quel parametro (*range-only*). Il suo `_range` esplicito,
> se presente, resta **sempre attivo** (100% dei grani); senza `_range` non c'è
> nessuna variazione (niente jitter implicito). Quindi nel dict per-parametro
> dichiari **solo** i parametri di cui vuoi *ridurre* la probabilità: gli altri
> applicano il loro range a piena ampiezza. Per ottenere l'1% implicito su un
> singolo parametro, scrivilo esplicito (es. `pan: 1`).
>
> Differisce dalla modalità **globale** (`deviation_probability: 50`), dove un'unica
> probabilità vale per tutti i parametri indistintamente.

```yaml
# Solo 'volume' ridotto al 30%. pan/duration/pitch/pointer/reverse/envelope:
# se hanno un _range dichiarato lo applicano al 100%, altrimenti restano fermi.
deviation_probability:
  volume: 30
```

### Detune implicito del pitch (senza `range`)

Quando il pitch è sotto deviation_probability **senza** `range` esplicito, ai grani che il
gate seleziona si applica un micro-detune continuo:

- unità EDO (`semitones`, `cents`, `quarter_tone`, `eighth_tone`, `edo: N`):
  ±12 cents uniformi per grano, applicati in ratio-space **dopo** la
  quantizzazione di griglia (il ratio risultante resta nei bounds ±3 ottave);
- `ratio`: jitter implicito ±0.005 sul moltiplicatore (comportamento storico).

```yaml
pitch:
  semitones: 7            # nessun range dichiarato
deviation_probability:
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

### voices.num_voices — fade frazionario

`num_voices` è uno scalare o un envelope (bounds `[1, 64]`). Quando il valore
interpolato è **frazionario**, la parte decimale diventa uno scaler di volume
sulla voce di confine (quella che si accende o si spegne), invece di un on/off
netto:

- `floor(value)` voci suonano a volume pieno;
- la voce di confine (indice `floor(value)`) riceve grani con gain pari alla
  parte frazionaria `frac = value − floor(value)`, applicato in dB come
  `volume += 20·log10(frac)` (clampato al floor del bound volume, −120 dB);
- `frac = 0` → nessuna voce di confine (comportamento storico).

`max_voices` è precomputato come `ceil(picco)` dei breakpoint, così la voce di
confine in cima ha sempre uno slot anche con picchi frazionari.

Con interpolazione `step` e breakpoint interi il valore è sempre intero
(`frac = 0`): le voci si accendono/spengono di colpo, come prima. Con
interpolazione `linear`/`cubic` la transizione tra due conteggi interi diventa
una dissolvenza graduale.

```yaml
# La 6ª voce sfuma a zero in 1 s (interpolazione lineare implicita)
voices:
  num_voices: [[0, 6], [1, 5]]

# Switch netto (nessun fade): interpolazione step
voices:
  num_voices:
    type: step
    points: [[0, 6], [1, 5]]

# Conteggio frazionario costante: 2 voci piene + 1 a metà volume
voices:
  num_voices: 2.5
```

Il fade è deterministico (guidato dall'envelope, nessun RNG). Nella partitura
grafica la voce in dissolvenza appare più trasparente, perché l'opacità del
grano segue il suo volume.

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

# chord_progression: accordo funzione del tempo (envelope di accordi)
voices:
  pitch:
    strategy: chord_progression
    progression:               # sequenza [tempo_secondi, accordo]
      - [0,  "maj7"]
      - [8,  "min7", 1]        # forma compatta [t, chord, inversion]
      - [16, {chord: "dom7", inversion: 0}]  # forma esplicita
    interp: linear             # linear|cubic = glissando · step = blocchi (default: linear)
    voice_leading: nearest     # nearest (default) | positional

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

- **Vincolo**: `chord`, `chord_progression` e `spectral` sono definiti
  intrinsecamente in semitoni (offset assoluti) e accettano solo
  `unit: semitones` (o `unit` assente). Altre unità → `InvalidStrategyConfigError`.

**`chord_progression` — progressioni armoniche.** Rende l'accordo una funzione
del tempo: per ogni voce un envelope di offset in semitoni interpola tra i
voicing della `progression`. Voce 0 → sempre identità (riferimento); il moto di
radice va messo nell'envelope `pitch` dello stream. Campi:

- `progression` — lista non vuota di `[tempo, accordo]`, tempi non
  decrescenti. L'accordo è un nome (vedi tabella sopra), opzionalmente con
  inversione in forma compatta `[t, chord, inversion]` o esplicita
  `[t, {chord: ..., inversion: ...}]`.
- `interp` — `linear`/`cubic` (glissando) · `step` (blocchi). Default `linear`.
- `voice_leading` — `positional` (voce i = i-esima nota) · `nearest` (default:
  riabbinamento a minimo movimento con octave-folding e note comuni tenute).

I tempi della `progression` seguono il `time_mode` dello stream, come gli
envelope: con `time_mode: normalized` i tempi vanno espressi in `0..1` e sono
mappati sulla `duration` dello stream; con `absolute` (default) sono secondi.

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

Nomi e parametri allineati alle altre dimensioni (pitch/onset/pointer):
`range` e `stochastic` usano `spread`; `step` usa `step`. Tutti i parametri
accettano scalare o envelope. Voce 0 → sempre offset 0.

```yaml
# range: voci distribuite equidistanti in [-spread/2, +spread/2]
voices:
  pan:
    strategy: range
    spread: 120.0         # gradi totali (scalare o envelope)

# stochastic: offset casuale stabile per voce in [-spread/2, +spread/2] (seeded)
voices:
  pan:
    strategy: stochastic
    spread: 180.0         # range totale in gradi (scalare o envelope)

# step: voce i → i × step gradi
voices:
  pan:
    strategy: step
    step: 15.0            # gradi per voce (scalare o envelope; può essere negativo)
```

> Per applicare un offset di pan uniforme a tutte le voci usa il parametro
> `pan` base dello stream (la vecchia strategy `additive` è stata rimossa
> perché ridondante con esso).

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
    deviation_probability:
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
> Sorgente di verità: `src/pge/envelopes/envelope.py`, `src/pge/envelopes/envelope_builder.py`, `src/pge/envelopes/envelope_interpolation.py`, `src/pge/envelopes/envelope_segment.py`, `src/pge/envelopes/time_distribution.py`.

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
- lista non vuota con almeno un elemento `[t, v]`, un formato compatto o un
  BP group `[points, interp]`
- dict contenente la chiave `points`

Tutti i parametri numerici dei seguenti blocchi accettano envelope:
`density`, `fill_factor`, `distribution`, `volume`, `pan`, `grain.duration`,
`grain.duration_range`, `pitch.ratio`, `pitch.semitones`, `pitch.range`,
`pointer.speed_ratio`, `pointer.offset_range`,
`pointer.loop_start`, `pointer.loop_end`, `pointer.loop_dur`, `deviation_probability` (globale
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

**Caso a 2 soli punti:** con due breakpoint l'unica informazione disponibile è
la pendenza del segmento; assegnarla a entrambe le tangenti degenererebbe in una
retta (indistinguibile da `linear`). Per questo le tangenti agli estremi vengono
forzate a zero e l'Hermite diventa lo smoothstep simmetrico
`v(s) = v0 + (v1 - v0)(3s² - 2s³)`: una S con ease-in-out visibile, monotòna e
senza overshoot. Quindi `type: cubic` su due punti produce sempre una curva, non
una retta — per la retta usare `type: linear`. Con tre o più punti il
comportamento Fritsch-Carlson agli estremi (tangente = pendenza del segmento
adiacente) resta invariato.

---

### 2. Forme di sintassi accettate

Le forme valide nel YAML sono sei. Tutte vengono ricondotte a una lista
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

#### 2.7 BP group per-macrozona (issue #64)

Un run di breakpoint puo' essere avvolto in un **BP group** compatto che
dichiara il tipo di interpolazione dell'intera macrozona, simmetrico ai loop
block. Sintassi: `[points, interp]` — lista a 2 elementi dove `points` e' una
lista di `[t, v]` / `[t, v, type]` (tempi **assoluti**, come i breakpoint
nudi — non percentuali) e `interp ∈ {linear, cubic, step}`.

```yaml
density: [
  [[[0.0, 0], [0.2, 12], [0.4, 8]], 'cubic'],           # zona A: cubic
  [[[0, 8], [50, 18], [100, 8]], 0.7, 4, 'linear'],     # loop block, invariato
  [[[0.75, 6], [0.9, 6], [1.0, 0]], 'step'],            # zona B: step
]
```

Forma diretta (envelope = una sola zona), simmetrica al compatto diretto:

```yaml
density: [[[0.0, 0], [0.5, 30], [1.0, 5]], 'cubic']
```

Regole:

- Il group interp governa i soli **segmenti interni** della zona: n punti →
  n−1 segmenti. Il segmento in uscita dall'ultimo punto del gruppo (gap verso
  l'item successivo) resta al default globale, come i breakpoint nudi.
- Desugar sui 3-tuple per-punto (§2.6): il gruppo equivale a taggare ogni
  punto tranne l'ultimo con il group interp. Un punto `[t, v, type]` dentro la
  zona fa **override** del group interp per il proprio segmento; un type
  esplicito sull'ultimo punto della zona governa il gap in uscita.
- L'interp del gruppo **non** diventa il tipo globale dell'envelope
  (`extract_interp_type` scansiona solo i loop block). I breakpoint nudi
  restano al default globale.
- Zone `cubic`: tangenti Fritsch-Carlson calcolate globalmente (PCHIP
  monotone), stessa regola di §2.6.
- Collisione al bordo zona: se il primo punto del gruppo ha `t <=` ultimo
  breakpoint precedente, viene traslato di `DISCONTINUITY_OFFSET` (salto
  verticale, stessa regola dei loop block §7.3). Nessuna traslazione senza
  collisione.
- `interp` non in `{linear, cubic, step}` → `InvalidFieldValueError`.
- Gruppo con meno di 2 punti → `ValueError` (zona senza segmenti interni).

Disambiguazione: il BP group e' l'unica lista a 2 elementi con `elem[0]`
lista di punti ed `elem[1]` stringa. Un breakpoint `[t, v]` ha `elem[0]`
numerico; un loop block ha 3–6 elementi.

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

I parametri `loop_start`, `loop_end`, `loop_dur` (e `start`, che è scalare ma
segue la stessa unità) hanno una semantica aggiuntiva: `loop_unit: normalized`
scala i **valori** (asse Y) da `[0, 1]` a `[0, sample_dur_sec]`. Non agisce
sull'asse X. È documentato nella sezione 10.

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

#### 3.4 Strategy envelope dei `voices.*`

Gli envelope dei parametri delle strategy voce
(`voices.{pitch,onset_offset,pointer,pan}.{step,spread,...}`) **ereditano** il
`time_mode` dello stream esattamente come gli envelope diretti (`density`,
`pan_range`, …). Una lista compatta di breakpoint su uno stream `normalized`
viene quindi scalata sulla `duration`:

```yaml
streams:
  - stream_id: s1
    duration: 40.0
    time_mode: normalized
    voices:
      num_voices: 5
      pan:
        strategy: step
        step: [[.6, 0], [.7, 60.0]]   # 0.6 → 24s, 0.7 → 28s (scalati su duration)
```

Come per gli envelope diretti, la forma dict con `time_mode` (o l'alias
`time_unit`) locale **sovrascrive** quello dello stream:

```yaml
    time_mode: normalized
    voices:
      pan:
        strategy: step
        step:                          # locale absolute → tempi in secondi
          points: [[.6, 0], [.7, 60.0]]
          time_mode: absolute
```

> Nota storica: fino all'issue #144 le strategy envelope in forma compatta
> restavano sempre in secondi assoluti anche su stream `normalized` (incoerenza
> silenziosa con gli envelope diretti). Dopo il fix il `time_mode` di stream è
> onorato — breaking change semantico per chi usava la forma compatta dentro
> `voices.*` su stream `normalized`.

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
`src/pge/envelopes/time_distribution.py` tramite `TimeDistributionFactory`.

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

Una lista di envelope può combinare breakpoint standard `[t, v]`, blocchi
compatti `[pattern, end_time, n_reps, ...]` e BP group `[points, interp]`
(§2.7). Il sistema calcola l'offset temporale di ciascun blocco compatto in
base all'ultimo breakpoint precedente.

#### 7.1 Regola di offset

Per ogni elemento iterato:

- se è un breakpoint `[t, v]`: aggiorna `current_time = max(current_time, t)`
- se è un formato compatto: la sua durata effettiva è `end_time - current_time`,
  e dopo l'espansione `current_time` diventa il tempo dell'ultimo punto generato.
- se è un BP group: i suoi punti hanno tempi assoluti, quindi nessun offset —
  ma il primo punto viene traslato di `DISCONTINUITY_OFFSET` se collide con
  `current_time` (§7.3); dopo l'espansione `current_time` diventa il tempo
  dell'ultimo punto della zona.

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

Per i BP group la traslazione avviene solo in caso di **collisione** (primo
punto della zona con `t <=` ultimo breakpoint precedente): i tempi del gruppo
sono assoluti, quindi un salto verticale intenzionale si scrive ripetendo lo
stesso `t` al bordo zona.

#### 7.4 Limiti

Il formato compatto **non può essere annidato dentro un altro formato compatto**.
Può comparire solo come elemento di primo livello in una lista mista. Lo stesso
vale per i BP group: niente gruppi dentro pattern compatti né viceversa.

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

`loop_start`, `loop_end`, `loop_dur` accettano envelope. `start` **no**: è un
valore scalare (vedi § Blocco Pointer). Condivide però con i tre parametri di
loop la semantica di unità controllata da `loop_unit`:

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

#### 10.2 `deviation_probability` come envelope

`deviation_probability` può essere booleano, numerico, envelope, o dict. Quando è envelope, la
probabilità di applicare la randomness al parametro varia nel tempo.

**Globale**:

```yaml
deviation_probability: [[0, 0], [30, 80]]          # probabilità: 0% all'inizio, 80% alla fine
```

**Per chiave**:

```yaml
deviation_probability:
  volume: [[0, 0], [30, 80]]
  pan: 50
  duration: {type: cubic, points: [[0, 0], [15, 100], [30, 0]]}
```

Vedi `GateFactory._classify_deviation_probability`: il dispatch usa
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
| BP group diretto                              | `[[[0, 0], [0.5, 30], [1, 5]], 'cubic']`           | Macrozona unica con interp proprio (§2.7) |
| BP group in misto                             | `[[[[0, 0], [0.4, 8]], 'cubic'], [[[0.75, 6], [1, 0]], 'step']]` | Macrozone con interp diversi; tempi assoluti |
| Loop pointer normalizzato (valori)            | `loop_unit: normalized` + `loop_start: 0.0`        | Scala Y per sample_dur_sec |
| Time mode globale                             | `time_mode: normalized` a livello stream           | Scala X per stream duration |
| Espressione matematica                        | `[[0, 0], [(pi*5), 1]]`                            | Valutata a parse-time |
| deviation_probability globale envelope                      | `deviation_probability: [[0, 0], [30, 80]]`                      | Probabilità time-varying |
| deviation_probability per chiave envelope                   | `deviation_probability: {volume: [[0, 0], [30, 80]]}`            | Override per parametro |
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
6. **Expansion**: `EnvelopeBuilder.parse` espande formati compatti, BP group
   (desugar in 3-tuple per-punto) e misti.
7. **Type extraction**: `EnvelopeBuilder.extract_interp_type` legge il tipo dal
   formato compatto se presente, altrimenti default `linear`. I BP group non
   partecipano: il loro interp resta confinato alla zona.
8. **Tangent computation**: `_compute_fritsch_carlson_tangents` solo per cubic.
9. **Segment construction**: `NormalSegment` con strategy e context (tangenti).
10. **Validation**: `_validate_and_clip` controlla ogni breakpoint contro i bounds.
11. **Runtime evaluation**: `Envelope.evaluate(t)` delega al segmento, che a sua
    volta delega alla strategy di interpolazione.

---

### Riferimenti sorgente

- `src/pge/envelopes/envelope.py` — classe `Envelope`, `is_envelope_like`,
  `create_scaled_envelope`, `_scale_raw_values_y`
- `src/pge/envelopes/envelope_builder.py` — `EnvelopeBuilder.parse`,
  `_is_compact_format`, `_expand_compact_format`, `_is_bp_group`,
  `_expand_bp_group`, `DISCONTINUITY_OFFSET`
- `src/pge/envelopes/envelope_interpolation.py` — `LinearInterpolation`,
  `StepInterpolation`, `CubicInterpolation`
- `src/pge/envelopes/envelope_segment.py` — `NormalSegment` con hold behavior
- `src/pge/envelopes/envelope_factory.py` — `InterpolationStrategyFactory`
- `src/pge/envelopes/time_distribution.py` — `TimeDistributionFactory` e le 5 strategie
- `src/pge/parameters/parser.py` — `GranularParser.parse_parameter` + validazione
- `src/pge/parameters/gate_factory.py` — uso di envelope per `deviation_probability`
- `src/pge/controllers/pointer_controller.py` — `loop_unit` e scaling dei valori loop
- `src/pge/controllers/window_selection_strategy.py` — `_validate_curve_range`
- `src/pge/core/stream.py` — `_parse_strategy_kwarg` per envelope nelle voice strategy

---

## Tabella Bounds Parametri

| Parametro | Min | Max | Default | Note |
|-----------|-----|-----|---------|------|
| `density` | 0.01 | 4000 | — | grani/secondo |
| `fill_factor` | 0.001 | 50 | 2.0 | priorità su density |
| `distribution` | 0 | 1 | 0.0 | 0=sync, 1=async |
| `grain_duration` | 1/48000 (1 campione) | 10 | 0.05 | secondi; `duration_unit` li porta in `samples` o `milliseconds` |
| `volume` | -120 | 12 | 0.0 | dB |
| `pan` | -3600 | 3600 | 0.0 | gradi |
| `pitch_ratio` | 0.001 | 8 | 1.0 | ratio diretto |
| `pitch_semitones` | -36 | 36 | 0 | ±3 ottave |
| `pointer_speed_ratio` | -100 | 100 | 1.0 | negativo = indietro |
| `pointer_deviation` | -1 | 1 | 0.0 | offset per-grano |
| `loop_start` | 0 | sample_dur | — | secondi |
| `loop_end` | 0 | sample_dur | — | secondi |
| `loop_dur` | 0.005 | sample_dur | — | secondi |
| `num_voices` | 1 | 256 | 1 | intero |
| `scatter` | 0 | 1 | 0.0 | 0=sync, 1=indip. |

Per la sintassi completa multi-voice, vedere [[multi-voice]].
Per la sintassi envelope (in ogni parametro che la accetta), vedere la sezione
[Envelopes](#envelopes) interna a questo doc.
