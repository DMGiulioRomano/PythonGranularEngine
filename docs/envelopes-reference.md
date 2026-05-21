# Envelopes — Reference completa

> Riferimento esaustivo del sistema envelope di PythonGranularEngine.
> Documenta ogni forma sintattica accettata nel YAML, le regole di parsing,
> l'interpolazione, il comportamento ai bordi, le ripetizioni cicliche e
> le distribuzioni temporali.
>
> Sorgente di verità: `src/envelopes/envelope.py`, `src/envelopes/envelope_builder.py`,
> `src/envelopes/envelope_interpolation.py`, `src/envelopes/envelope_segment.py`,
> `src/envelopes/time_distribution.py`.

**Documenti collegati:** [[INDEX]] · [[yaml-reference]] (dove gli envelope sono
accettati nel YAML) · [[multi-voice]] (envelope sui parametri scalari delle
voice strategy) · [[ARCHITECTURE]] (valutazione runtime in `Stream` /
controller) · [[workflows]] § "Making a Parameter Envelope-Aware".

---

## Indice

1. [Modello concettuale](#1-modello-concettuale)
2. [Forme di sintassi accettate](#2-forme-di-sintassi-accettate)
3. [Time mode: `absolute` vs `normalized`](#3-time-mode-absolute-vs-normalized)
4. [Tipi di interpolazione](#4-tipi-di-interpolazione)
5. [Formato compatto (cicli ripetuti)](#5-formato-compatto-cicli-ripetuti)
6. [Distribuzioni temporali nei cicli](#6-distribuzioni-temporali-nei-cicli)
7. [Formato misto (breakpoint + cicli)](#7-formato-misto-breakpoint--cicli)
8. [Comportamento ai bordi (hold)](#8-comportamento-ai-bordi-hold)
9. [Espressioni matematiche nei valori](#9-espressioni-matematiche-nei-valori)
10. [Casi speciali per dominio](#10-casi-speciali-per-dominio)
11. [Validazione e bounds](#11-validazione-e-bounds)
12. [Tabella riassuntiva delle sintassi](#12-tabella-riassuntiva-delle-sintassi)

---

## 1. Modello concettuale

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
ciascuna voice strategy (`step`, `semitone_range`, `pointer_range`,
`max_offset`, `base`, `spread`), e il campo `curve` di
`grain.envelope.transition` e `grain.envelope.multistate`.

Internamente l'envelope è composto da:

- **breakpoints**: lista normalizzata `[[t, v], …]` in tempi assoluti, ordinata.
- **strategy**: `InterpolationStrategy` selezionata da `type` (linear/cubic/step).
- **segments**: lista di `NormalSegment` con metodi `evaluate(t)` e `integrate(a, b)`.

Per cubic, il sistema pre-calcola le tangenti con l'algoritmo Fritsch-Carlson,
che garantisce monotonia e previene overshoot tra breakpoint adiacenti.

---

## 2. Forme di sintassi accettate

Le forme valide nel YAML sono cinque. Tutte vengono ricondotte a una lista
piatta di breakpoint `[[t, v], …]` durante il parsing (`EnvelopeBuilder.parse`).

### 2.1 Scalare

Non è un envelope: è un valore costante.

```yaml
density: 20
volume: -6.0
```

### 2.2 Lista di breakpoint standard

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

### 2.3 Dict `{type, points}`

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

### 2.4 Formato compatto

Forma sintetica per generare N ripetizioni di un pattern definito in percentuale.
Sintassi: `[pattern_points, end_time, n_reps, interp?, time_dist?]`. Dettagliato in §5.

```yaml
grain:
  duration: [[[0, 0.01], [100, 0.2]], 30, 4]
```

### 2.5 Formato misto

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

---

## 3. Time mode: `absolute` vs `normalized`

Il `time_mode` controlla l'unità di misura dell'asse X dell'envelope.

### 3.1 `absolute` (default)

I tempi sono in secondi. Un breakpoint `[10, 40]` vale "al secondo 10 il valore
è 40", indipendentemente dalla durata dello stream.

```yaml
streams:
  - stream_id: s1
    duration: 30.0
    density: [[0, 5], [10, 40], [30, 5]]
    # picco a t=10s
```

### 3.2 `normalized`

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

### 3.3 Scaling del formato compatto

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

## 4. Tipi di interpolazione

Tre strategie, selezionabili tramite `type` (in forma dict) o come quarto
elemento opzionale di un formato compatto.

### 4.1 `linear` (default)

Interpolazione lineare tra breakpoint consecutivi. Integrale calcolato come area
di trapezio.

```yaml
density:
  type: linear
  points: [[0, 5], [10, 40], [30, 5]]
```

### 4.2 `cubic`

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

### 4.3 `step`

Hold-left: il valore di ogni segmento è quello del breakpoint sinistro fino al
breakpoint successivo. L'integrale è area di rettangolo.

```yaml
density:
  type: step
  points: [[0, 5], [10, 40], [20, 10], [30, 0]]
```

Utile per cambi discontinui di sezione, automazioni "a quantità fisse",
modulazioni di parametri categorici (es. numero di voci).

### 4.4 Discontinuità con formato compatto

Quando si concatenano cicli, il `BUILDER` inserisce automaticamente un offset
infinitesimale di `1e-6` secondi (`DISCONTINUITY_OFFSET` in `envelope_builder.py`)
tra il primo punto di un nuovo ciclo e il punto precedente, in modo che due
breakpoint non coincidano sullo stesso tempo. Questo permette discontinuità
intenzionali senza degenerare gli algoritmi di interpolazione.

---

## 5. Formato compatto (cicli ripetuti)

Sintassi per generare N ripetizioni di un pattern espresso in percentuale.

### 5.1 Sintassi

```
[pattern_points, end_time, n_reps, interp?, time_dist?]
```

| Posizione | Nome             | Tipo                  | Obbligatorio | Significato |
|-----------|------------------|-----------------------|--------------|-------------|
| 0         | `pattern_points` | lista di `[x%, y]`    | sì           | pattern del ciclo, `x` in `[0, 100]` |
| 1         | `end_time`       | numero                | sì           | **tempo assoluto finale** del blocco compatto |
| 2         | `n_reps`         | intero `>= 1`         | sì           | numero di ripetizioni |
| 3         | `interp_type`    | str                   | no           | `'linear'` / `'cubic'` / `'step'` |
| 4         | `time_dist`      | str o dict            | no           | distribuzione delle durate dei cicli |

Punto cruciale di semantica: **`end_time` è il tempo assoluto finale, non la
durata del blocco**. Quando il formato compatto è usato in forma mista, la
durata effettiva è `end_time - time_offset`, dove `time_offset` è il tempo
dell'ultimo breakpoint scritto prima del blocco.

### 5.2 Forme valide

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

### 5.3 Pattern percentuale

Le coordinate `x` del pattern sono in `[0, 100]` e rappresentano la posizione
relativa **all'interno del singolo ciclo**. Il sistema le mappa al tempo
assoluto al momento dell'espansione.

```yaml
# pattern triangolare con vertice al 25%
grain:
  duration: [[[0, 0.01], [25, 0.2], [100, 0.01]], 30, 10]
```

### 5.3.1 Ultimo punto e copertura del ciclo

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

### 5.4 Comportamento ai bordi del ciclo

Il primo punto di ogni ciclo successivo al primo è traslato di
`DISCONTINUITY_OFFSET = 1e-6` secondi per evitare collisioni temporali tra
l'ultimo punto del ciclo precedente e il primo del successivo. È invisibile
all'orecchio ma garantisce che gli algoritmi di interpolazione operino su tempi
strettamente crescenti.

### 5.5 Validazioni

- `n_reps < 1` → `ValueError` ("n_reps deve essere >= 1")
- `end_time <= time_offset` → `ValueError`
- `pattern_points` vuoto → `ValueError`

---

## 6. Distribuzioni temporali nei cicli

Il quinto elemento del formato compatto controlla come le durate dei cicli sono
distribuite all'interno del blocco. Definito in
`src/envelopes/time_distribution.py` tramite `TimeDistributionFactory`.

Vincolo invariante: `sum(cycle_durations) == total_duration`.

### 6.1 Forme di specifica

**Default (omesso)** → equivale a `'linear'`.

**Stringa** (parametri di default):

```yaml
density: [[[0, 5], [100, 50]], 30, 8, 'linear', 'exponential']
```

**Dict** (parametri custom):

```yaml
density: [[[0, 5], [100, 50]], 30, 8, 'linear', {type: geometric, ratio: 1.5}]
```

### 6.2 Distribuzioni disponibili

| Nome           | Alias       | Parametri        | Effetto musicale         |
|----------------|-------------|------------------|--------------------------|
| `linear`       | —           | nessuno          | durate uguali (default)  |
| `exponential`  | `exp`       | `rate=2.0`       | accelerando: cicli sempre più brevi |
| `logarithmic`  | `log`       | `base=2.0`       | ritardando: cicli sempre più lunghi |
| `geometric`    | `geo`       | `ratio=1.5`      | progressione geometrica; `ratio>1` ritardando, `ratio<1` accelerando |
| `power`        | —           | `exponent=2.0`   | power law configurabile  |

### 6.3 Formule

Date `total_duration = T` e `n_reps = N`:

- **linear**: `cycle_i = T / N` per ogni `i`.
- **exponential** (rate `r`): pesi `w_i = r^(-i)`, normalizzati su `T`.
  Con `r>1` i pesi decrescono → cicli più brevi all'avanzare del tempo.
- **logarithmic** (base `b`): pesi `w_i = log_b(i+1) + 1`, normalizzati.
  I pesi crescono → cicli più lunghi nel tempo.
- **geometric** (ratio `r`): `dur_i = dur_0 * r^i`. Con `r ≈ 1` ricade in `linear`.
  Somma di progressione geometrica `dur_0 = T * (1-r) / (1 - r^N)`.
- **power** (esponente `e`): pesi `w_i = (i+1)^e`, normalizzati.

### 6.4 Esempi parametrici

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

### 6.5 Validazioni

- `n_reps < 1` → `ValueError`
- `total_duration <= 0` → `ValueError`
- `exponential.rate <= 0` → `ValueError`
- `logarithmic.base <= 1` → `ValueError`
- `geometric.ratio <= 0` → `ValueError`

---

## 7. Formato misto (breakpoint + cicli)

Una lista di envelope può combinare breakpoint standard `[t, v]` e blocchi
compatti `[pattern, end_time, n_reps, ...]`. Il sistema calcola l'offset
temporale di ciascun blocco compatto in base all'ultimo breakpoint precedente.

### 7.1 Regola di offset

Per ogni elemento iterato:

- se è un breakpoint `[t, v]`: aggiorna `current_time = max(current_time, t)`
- se è un formato compatto: la sua durata effettiva è `end_time - current_time`,
  e dopo l'espansione `current_time` diventa il tempo dell'ultimo punto generato.

### 7.2 Esempio commentato

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

### 7.3 Discontinuità al passaggio mista → compatto

Il primo punto del primo ciclo viene anch'esso traslato di
`DISCONTINUITY_OFFSET` se `time_offset > 0`, per separarlo dall'ultimo
breakpoint standard. Anche in questo caso è subaudio e necessaria per la
correttezza degli algoritmi.

### 7.4 Limiti

Il formato compatto **non può essere annidato dentro un altro formato compatto**.
Può comparire solo come elemento di primo livello in una lista mista.

---

## 8. Comportamento ai bordi (hold)

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

## 9. Espressioni matematiche nei valori

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

## 10. Casi speciali per dominio

### 10.1 Loop pointer e `loop_unit`

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

### 10.2 `dephase` come envelope

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

### 10.3 `voices.*.curve` per window transition

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

### 10.4 Voice strategy parameters

Tutti i parametri scalari delle voice strategy (`step`, `semitone_range`,
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

### 10.5 `num_voices` come envelope

`num_voices` è un caso particolare: viene parsato come `Parameter` che ammette
envelope, ma il `VoiceManager` pre-alloca `max_voices` pari al picco massimo dei
breakpoint (vedere `Stream._init_voice_manager`). Le voci eccedenti il valore
istantaneo di `num_voices(t)` non vengono renderizzate al tempo `t`.

```yaml
voices:
  num_voices: [[0, 1], [30, 8]]      # da 1 a 8 voci linearmente
```

---

## 11. Validazione e bounds

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

## 12. Tabella riassuntiva delle sintassi

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

## Appendice: ordine di elaborazione

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

## Riferimenti sorgente

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
