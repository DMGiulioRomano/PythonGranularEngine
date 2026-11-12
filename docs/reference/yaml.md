---
slug: yaml
type: reference
status: stable
tags: [yaml, syntax, parameters, envelopes]
sources:
  - src/pge/engine/generator.py
  - src/pge/engine/stream_files.py
  - src/pge/export/depfile_writer.py
  - src/pge/core/stream.py
  - src/pge/controllers/
  - src/pge/parameters/
  - src/pge/expressions/
  - src/pge/maps/
  - src/pge/strategies/
  - src/pge/envelopes/
  - src/pge/shared/seeding.py
  - src/pge/shared/distribution_strategy.py
  - src/pge/rendering/numpy_window_registry.py
last_synced_commit: 93d326b
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
- [Campi Obbligatori di Stream](#campi-obbligatori-di-stream) — `stream_id`, `sample`
- [Posizione dello Stream](#posizione-dello-stream-onset-opzionale) — `onset` opzionale,
  assente = origine della timeline
- [Durata dello Stream](#durata-dello-stream-duration-opzionale) — `duration` opzionale,
  assente = durata del sample
- [Stream come file](#stream-come-file-file) — `- file: <path>` in `streams:`
  importa uno stream scritto in un altro documento; il master ne tiene il
  piazzamento
- [Configurazione Processo (StreamConfig)](#configurazione-processo-streamconfig)
- [La banda dei `_range`](#la-banda-dei-_range-distribution_mode-e-range_anchor) —
  larghezza, forma (`distribution_mode`), ancora (`range_anchor`), unità
  (`_range_unit`: assoluta o frazione della base)
- [Blocco Grain](#blocco-grain), [Pointer](#blocco-pointer), [Pitch](#blocco-pitch), [DeviationProbability](#deviation_probability-variazione-stocastica)
- [`pointer.position`](#pointerposition--la-posizione-dichiarata) — la
  posizione di lettura scritta, da 0 a 1 della finestra attiva, al posto di
  `speed_ratio` e `start`
- [Mappe ed espressioni](#mappe-ed-espressioni-maps) — `maps:` dichiara una
  mappa iterata, e un parametro la legge con un'espressione
  (`duration: (0.02 + 0.08*m1)`), valutata a ogni grano
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
- `src/pge/engine/stream_files.py` — `file:` negli stream del master (issue #290)
- `src/pge/maps/`, `src/pge/expressions/` — `maps:` e le espressioni che le leggono (issue #307)
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

In un brano che importa stream con `file:` il seed è **uno solo, quello del
master**: il `seed` del file importato è ignorato, con un avviso su stderr se
differisce. Vedi [Stream come file](#stream-come-file-file) e la sua
[identità del suono](#identità-del-suono).

**La cache stems vede il seed** (issue #297). Con `--cache`
(`STEMS=true CACHE=true`) il seed dichiarato entra nel fingerprint di ogni
stream: cambiarlo rifà tutti gli stem al render seguente, invece di lasciarli
`clean` con in output la realizzazione del seed di prima. Conta il seed del
master, non quello di un file importato. Due seed sono lo stesso seed quando
la derivazione li scrive uguali (`1441` e `'1441'` sì, `1441` e `1441.0` no).
Senza `seed:` il fingerprint resta quello di prima: il seed di sessione,
diverso a ogni run, non invalida gli stem già resi.

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
| Variazione relativa | `grain: {duration: 0.05, duration_range: 0.5, duration_range_unit: relative}` | banda larga `0.5 × duration` (default: `±25%`) |
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
    sample: "file.wav"          # nome file (cercato in Media/)
```

Le condizioni di esistenza di uno stream sono due. Uno stream a riposo **è il
sample**: stessa origine, stessa durata, contenuto risintetizzato. Tutto il
resto è override compositivo — vedi
[Posizione dello Stream](#posizione-dello-stream-onset-opzionale) e
[Durata dello Stream](#durata-dello-stream-duration-opzionale).

```yaml
streams:
  - stream_id: "risintesi"      # parte da 0, dura quanto il sample
    sample: "file.wav"
```

---

## Posizione dello Stream (`onset` opzionale)

`onset` è un campo **opzionale**: se assente lo stream comincia all'origine
della timeline, cioè a `0.0` secondi.

```yaml
streams:
  - stream_id: "dall_origine"   # parte da 0
    sample: "file.wav"

  - stream_id: "spostato"       # override compositivo esplicito
    onset: 12.5
    sample: "file.wav"
```

0 non è "nulla", è l'origine: uno stream che non dichiara una posizione non ha
una posizione indeterminata, ne ha una neutra. Dichiararla è una scelta
compositiva, e le scelte compositive stanno bene come override espliciti.

| Dichiarazione | Posizione dello stream |
|---------------|------------------------|
| chiave assente | `0.0` s (origine della timeline) |
| `onset: null` | `0.0` s (come chiave assente) |
| `onset: 12.5` | 12.5 s (l'esplicito vince sempre) |
| `onset: 0` | `0.0` s — dichiarazione esplicita, stesso risultato del default |

`onset` è **sempre assoluto in secondi**: `time_mode: normalized` riguarda
l'asse degli envelope dentro lo stream, non la posizione dello stream nella
timeline.

**Costo del default.** Un `onset` cancellato per sbaglio non produce più un
errore: lo stream si impila silenziosamente a `t=0`. È lo stesso prezzo già
accettato per `duration`.

**Asimmetria con `duration`.** Il default di `duration` è derivato da un dato
(la lunghezza del file audio), quello di `onset` è la costante `0.0`. Stesso
gesto, natura diversa: è il motivo per cui la durata risolta entra nel
fingerprint della cache e la posizione risolta no.

---

## Durata dello Stream (`duration` opzionale)

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

## Stream come file (`file:`)

Issue #290. Una voce della lista `streams:` può essere un **riferimento a un
altro documento YAML** invece di uno stream scritto per intero. Il documento
importato è un documento a sé — tipicamente quello del laboratorio, che si apre
e si rende anche da solo — e il documento del brano, il **master**, ne decide
soltanto il piazzamento.

```yaml
# brano.yml — il master
seed: 1441
streams:
  - file: streams/risacca.yml   # un documento del laboratorio
    onset: 12.5
    mute: true
  - stream_id: stream2          # gli stream scritti nel master restano validi
    sample: pino.wav
```

```yaml
# streams/risacca.yml — si rende anche da solo
seed: 1441
duration: 30
bpm: 60
streams:
  - stream_id: risacca
    onset: 0
    duration: 30
    sample: mare.wav
    density: 40
```

### Le regole

| # | Regola |
|---|--------|
| 1 | `file:` si risolve in `Generator.load_yaml`, **prima di tutto il resto**, espressioni matematiche comprese. Da lì in poi il motore vede una lista di stream come prima: cache, fingerprint e solo/mute lavorano sullo stream già risolto. |
| 2 | Il path è **relativo alla cartella del master**, non alla directory da cui si lancia. Un path assoluto vale com'è. |
| 3 | Il file importato contiene **un solo stream**: una lista `streams:` con un mapping dentro. Un `file:` dentro il file importato è un errore: niente catene, quindi niente cicli. |
| 4 | **Ogni chiave ha una sola casa.** Accanto a `file:` il master tiene solo il piazzamento: `stream_id`, `onset`, `mute`, `solo`. Qualunque altra chiave è un errore (`StreamFileKeyError`) che nomina il master, la voce e la chiave. Il default di `stream_id` è il nome del file senza estensione (`risacca`); `stream_id: null` vale come assente. |
| 5 | Del file importato si legge **lo stream**, e il `seed` top-level solo per l'avviso della regola 6. Si ignorano gli altri top-level (`duration`, `bpm`, `seed`, e ogni altro) e le chiavi di piazzamento dentro lo stream: il laboratorio scrive `onset: 0` e il proprio `stream_id` perché il file si renda da solo, ma nel brano decide il master. Tutto il resto viene dal file, compresa la `duration` dello stream. |
| 6 | Se il file importato dichiara un `seed` diverso da quello del master, il render procede col seed del master e il motore scrive un **avviso su stderr** (`[SEED] Il file importato ...`) con il file, la voce, il seed del file e quello del master. Un master senza `seed` usa un seed di sessione, che non è quello del file: l'avviso parla anche lì. |
| 7 | Due stream con lo stesso `stream_id` **effettivo**, se almeno uno viene da `file:`, sono un errore (`StreamFileDuplicateIdError`) che li nomina tutti. L'id effettivo è quello dello stem: l'id dopo le espressioni matematiche, come stringa — `1`, `'1'` e `'01'` sono lo stesso stem, e così due file `1.yml` e `01.yml` importati senza `stream_id` (il math eval converte in numero ogni stringa che lo sembra). I duplicati fra stream scritti nel master restano fuori, come prima. |
| 8 | Gli errori stanno nella gerarchia `EngineError` e nominano **sia il master sia il file importato**: file mancante, illeggibile, malformato, senza stream o con più di uno. Vedi [[errors]], sezione «Lo stream come file». |

Il confronto dei seed della regola 6 è quello della derivazione degli RNG, che
scrive il seed in una stringa dopo le espressioni matematiche: `seed:
(1000 + 441)` e `seed: '1441'` sono `1441`, e non producono un avviso.

Il `sample` di uno stream importato si cerca come quello di ogni altro stream
(`--samples-dir`, default `refs/`), **non** relativo al file importato: il path
di `file:` dice dove sta il documento, non dove stanno i suoi sample.

### Lo stream risolto

Per il master dell'esempio, `load_yaml` vede:

```yaml
streams:
  - stream_id: risacca      # dal nome del file: il master non ne scrive uno
    onset: 12.5             # dal master; l'onset: 0 del file e' ignorato
    mute: true              # dal master
    duration: 30            # dallo stream del file; la duration top-level no
    sample: mare.wav
    density: 40
  - stream_id: stream2
    sample: pino.wav
```

È lo stesso dict dello stream scritto per intero nel master, e la cache lo
tratta come tale: il fingerprint è quello del dict risolto, quindi **spostare
uno stream dal master a un file non lo marca dirty**, e modificare il file
importato marca dirty quello stream e nessun altro. Il GC della cache legge gli
id dal documento risolto, quindi non scambia uno stream importato per un
orfano. `Generator.stream_origins` conserva, per id effettivo, la voce del
master che ha importato ogni stream (`StreamFileOrigin`: master, posizione,
`file:` come scritto, path risolto): dopo la risoluzione è la sola traccia di
dove lo stream è scritto.

Fuori dalla cache, a vedere il file importato deve essere **make**. In MIX
(`STEMS=false`) la regola che rende il brano dipende dal master, e
modificare soltanto uno stream importato non rifaceva l'audio. Le ricette MIX
di `make/build.mk` passano `--depfile`: il motore scrive in `$(GENDIR)` le
dipendenze del render — `Generator.source_files`, il master e i file
importati — e il Makefile le include. Vedi [[cli]], `--depfile`.

### Identità del suono

L'RNG di ogni componente è derivato da `(seed, rng_group o stream_id,
componente)` — vedi [Seed](#seed-riproducibilità). Il file non aggiunge niente a
nessuno dei tre, quindi:

- uno stream importato **suona come nel laboratorio solo con lo stesso seed e
  lo stesso id**: lo stesso `seed` nel master e nel file, e lo stesso
  `stream_id` effettivo;
- uno `stream_id` diverso dà **un'altra realizzazione** dello stesso stream, e
  questo è accettato. Succede di default quando il laboratorio scrive uno
  `stream_id` diverso dal nome del file: il master che non ne scrive uno usa
  `risacca`, non lo `stream1` del laboratorio. Chi vuole la realizzazione del
  laboratorio scrive quell'id accanto a `file:`, oppure dichiara nel file un
  `rng_group`, che sostituisce lo `stream_id` nella derivazione e quindi non
  dipende da come il master chiama lo stream;
- importare **due volte lo stesso file** con due `stream_id` dà due
  realizzazioni distinte dello stesso stream — senza `stream_id` è un errore
  (regola 7), perché i due stem avrebbero lo stesso nome.

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
pescato dentro una **banda**. La banda si descrive con quattro concetti
ortogonali, che vanno tenuti distinti:

| concetto | chiave | cosa decide |
|---|---|---|
| larghezza | il valore del `_range` stesso | quanto è larga la banda |
| unità | `<param>_range_unit` | in che cosa quella larghezza è misurata |
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

#### Banda relativa: `<param>_range_unit`

Il `_range` è per default una **quantità assoluta**, nell'unità del parametro:
`volume_range: 3` sono 3 dB, `duration_range: 0.01` sono 0.01 secondi. Con
`_range_unit: relative` il numero diventa invece una **frazione del valore
base**, letta istante per istante — quindi *dopo* l'envelope della base:

```yaml
grain:
  duration: [[0, 0.001], [60, 0.5]]   # sweep su tre ordini di grandezza
  duration_range: 0.5                 # banda larga metà della durata corrente
  duration_range_unit: relative       # "absolute" (default) | "relative"
```

| `duration` in quell'istante | banda (`range_anchor: center`) |
|---|---|
| 1 ms | 0.75 … 1.25 ms (±25%) |
| 100 ms | 75 … 125 ms (±25%) |
| 500 ms | 375 … 625 ms (±25%) |

Serve dove la base spazia su più ordini di grandezza. Con una banda assoluta
la stessa `duration_range` è molte volte la durata sui grani corti (dove il
clamp a 1 campione la taglia) e percentualmente trascurabile sui lunghi: lungo
lo sweep il *carattere* della dispersione cambia da solo, e all'ascolto
l'effetto dell'asse si confonde con l'effetto collaterale del range. Relativa,
resta quello che è stato scritto.

**Quale `_range` la ammette.** Oggi solo `grain.duration_range`, via
`grain.duration_range_unit`. È l'unico parametro la cui base spazia per
costruzione da 1 campione a 10 secondi; su `volume` (dB) e `pan` (gradi) la
scala è già logaritmica o ciclica, e una frazione della base non direbbe la
stessa cosa. Il meccanismo è però dichiarativo (`ParameterSpec.range_unit_path`,
vedi [[add-parameter]]) e cablarne altri è aggiungere una riga.

Da non confondere con `pointer.offset_range`, che è relativo per costruzione e
per un altro meccanismo: è già una frazione della finestra di loop attiva, non
del proprio valore base — che infatti non ha.

**Dominio.** La frazione vive in `[0, 1]`, che è un dominio proprio della
modalità e non del parametro: 1.0 significa «banda larga quanto la base», e le
due ancore la consumano in modi diversi.

| `range_anchor` | banda con frazione `r` | massimo a `r = 1` |
|---|---|---|
| `center` | `[base·(1 − r/2), base·(1 + r/2)]` | ±50% |
| `min` | `[base, base·(1 + r)]` | +100% |

Sotto `center` il pavimento della banda è `base·(1 − r/2)`, quindi **si muove
con la base** invece di restare fermo dove lo mette una banda assoluta: è la
ragione per cui la modalità esiste. Non è però una garanzia di stare sopra il
minimo del parametro, che resta fisso: il pavimento ci finisce sotto appena
`base < min_val / (1 − r/2)` — per `grain_duration`, con `r = 1`, sotto i **2
campioni**. Lì il safety clamp riporta al minimo la metà bassa dei draw, con un
warning per grano; è l'estremo esatto dello sweep da cui l'issue nasce
(`0.021 ms` è un campione a 48 kHz). Sotto `min` vale invece il controllo del
tetto descritto sopra, con la formula `base + range · |base|` al posto della
somma — su una base positiva, cioè `base · (1 + range)`. La larghezza si misura
sul modulo perché è la stessa che il motore usa a ogni grano: il tetto al parse
e la banda a runtime sono due letture della stessa banda, e vengono dalla stessa
funzione.

**Cosa non tocca.** Il jitter implicito resta assoluto, per la stessa ragione
per cui `range_anchor` non lo tocca: non c'è nessuna frazione dichiarata da
reinterpretare. E proprio perché il jitter prenderebbe il suo posto in
silenzio, dichiarare `relative` **senza** il `_range` che governa è un
`MissingFieldError` al parse, non una chiave inerte.

**Assente non è vuota.** Senza la chiave la banda è assoluta, che è il default.
La chiave scritta e lasciata vuota (`duration_range_unit:`, cioè `null`) è
invece un `InvalidFieldValueError`: qualcuno l'ha scritta, e leggerla come
`absolute` non lascerebbe nel file niente da cui accorgersi che quella riga non
è stata letta. È la stessa regola della chiave gemella `grain.duration_unit`.

**Dove la curva si vede** il valore mostrato è quello *dichiarato*: in modalità
relativa `grain_duration_range` è la frazione, non una durata. Vale per
entrambi i consumatori della faccia `range` (vedi [[parameter-curve]]) — la
corsia `gr dur rng` della partitura PDF e il layer
`<stream_id>/grain_duration_range` delle sessioni Sonic Visualiser, che è quello
che resta su disco e dove un cursore di misura leggerebbe `0.5` come mezzo
secondo.

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
- Con `passthrough`, `clip_margin` è accettato e ignorato: senza filtro non c'è niente da allargare. Fino alla #265 la combinazione (anche col solo default `0.0`) faceva fallire il render con `TypeError`.

---

## Densità

`density` e `fill_factor` sono mutuamente esclusivi. `fill_factor` ha priorità.
C'è un terzo modo, [`grain.iot`](#grainiot--lattesa-fra-due-grani): l'attesa
fra due grani scritta direttamente, con cui la densità non si decide ma
emerge. Si sceglie per presenza della chiave, e con questi due non convive.

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

Bounds: `density` ∈ [0.01, ∞), `fill_factor` ∈ [0.001, 50], `distribution` ∈ [0, 1].

**La densità non ha un tetto** (issue #272). Fino alla 8.x il massimo era
4000 g/s, e in modalità `fill_factor` non tagliava un valore scritto ma il
quoziente: la regola implicita era `grain.duration >= fill_factor / 4000`
— 1 ms esatti con `fill_factor: 4` — e sotto quella soglia il motore rendeva
un `fill_factor` più basso di quello dichiarato senza dirlo. `fill_factor: 8`
con grani da 1 ms rendeva 4; `fill_factor: 4` con grani da 0.4 ms rendeva 1.6.
Il taglio non passava da `log_clip_warning` (che vive dentro
`Parameter._clamp`, e la density derivata non è un `Parameter`), quindi non
lasciava traccia né nei log né in partitura.

Il **minimo** invece resta, e non è un limite musicale: l'inter-onset è
`1.0 / density`, quindi una densità nulla è una divisione per zero e una
negativa è un cursore che non avanza.

Per la stessa ragione un valore **non finito** resta un errore al parse:
`.inf` e `.nan` sono scalari legali in YAML, e con un tetto finito li
fermava il confronto stesso (`min(4000, inf)` è un clip). Senza tetto quel
confronto non c'è più, e `density: .inf` renderebbe `1.0 / density` uguale
a zero — cioè il cursore che non avanza dall'altro capo, un render che non
finisce. Il parser li rifiuta con `ParameterBoundError`, come faceva prima
il tetto.

Conseguenza pratica: con grani brevi il conteggio dei grani ora cresce come
il `fill_factor` chiede. `fill_factor: 4` su grani da 0.4 ms sono 10000
grani/secondo per voce, non 4000. Sopra i 4000 g/s — la vecchia soglia — il
motore scrive una riga `[DENSITY_HIGH]` sul clip log (`./logs/`, rate limit
5 s di tempo-stream) con densità richiesta, durata del grano e IOT
risultante: non è un taglio, è la riga che il vecchio clamp non scriveva, e
serve a riconoscere un `grain.duration` sbagliato di un ordine di grandezza
prima che il render finisca la RAM.

### `grain.iot` — l'attesa fra due grani

`grain.iot` è l'attesa fino al grano successivo (inter-onset time, issue
#311): `onset[n+1] = onset[n] + iot`. È il terzo modo di dire quando nasce un
grano, e l'unico in cui lo si dice direttamente.

```yaml
grain:
  iot: 0.1                         # un metronomo: 10 grani al secondo
  iot: [[0, 0.2], [30, 0.05]]      # un accelerando
  iot: (0.020 + 0.180*m1)          # letta da una mappa (vedi sotto)
```

- **Il modo si sceglie per presenza della chiave.** Senza `grain.iot` vale
  tutto come prima, default `fill_factor: 2` compreso.
- **Insieme a `density`, `fill_factor` o `distribution` è un errore**, non una
  priorità (`InvalidFieldValueError` su `grain.iot`): dicono in un altro modo
  la stessa cosa, e scegliere in silenzio nasconderebbe l'errore. Vale per
  presenza: anche `distribution: 0`. Una `grain.iot:` scritta e lasciata vuota
  è un errore anche lei (`MissingFieldError`).
- **Niente distribuzione di Truax sopra**: l'attesa è quella scritta. Il
  disordine, se lo si vuole, viene dalla mappa.
- **Sta dentro `grain:` e segue `grain.duration_unit`**, come
  `grain.duration`: con `duration_unit: milliseconds`, `iot: 100` sono 0.1 s.
  Su un'espressione il fattore si applica al risultato. La regola
  dell'unità resta quella di `grain.duration`: con un'unità diversa da
  `seconds` `grain.duration` va scritta anche se l'unità serve solo a
  `grain.iot` (il default 0.05 è in secondi, e senza di lei è un
  `MissingFieldError` su `grain.duration`).
- **Limiti: da un campione (1/48000 s) a 100 s.** Un numero o un envelope
  fuori limite è un errore al parse, come per ogni parametro. Un'espressione
  viene **tagliata** a ogni grano e scritta sul clip log: un'attesa nulla,
  negativa o non finita non ferma il render, va a un campione (se è
  `+inf`, a 100 s). Non è un limite musicale ma l'invariante del giro dei
  grani: un'attesa nulla è un cursore che non avanza.
- Sotto 0.25 ms di attesa (sopra 4000 grani/s) continua a uscire la riga
  `[DENSITY_HIGH]`, con `mode=iot`.

**La densità emerge.** Con `grain.iot` la densità non è dichiarata: la si
legge a cose fatte. Con una mappa:

```yaml
maps:
  m1: {type: logistic, r: 3.5}
grain:
  iot: (0.020 + 0.180*m1)
```

le attese percorrono in ciclo 169, 110, 177, 89 ms: 545 ms per quattro grani,
7.3 grani/s in media, fra 5.6 e 11.2. È un anello chiuso: la mappa decide
quanto aspettare, e l'attesa decide quando la mappa farà il passo successivo
(`clock: grain` è contato sui grani, non sul tempo).

La densità emersa è pubblicata come curva, `effective_density`, come in
modalità `fill_factor`: in partitura e nella sessione Sonic Visualiser è
`1 / attesa` per ogni grano della voce 0, tenuto fino al grano dopo. Non è
una funzione del tempo — un'attesa letta da una mappa dipende dai grani già
nati — quindi si conosce a grani fatti. Accanto c'è la curva dell'attesa
stessa, `grain_iot` (issue #314): quella dichiarata se `grain.iot` è un
envelope, i valori realizzati se è un'espressione, con l'escursione vera in
legenda (`iot`, `89–177ms`).

**La stessa mappa su attesa e durata.** Con `iot` e `duration` che leggono la
stessa mappa a `clock: grain`, ogni grano porta il valore che ha deciso anche
la sua attesa: la mappa avanza una volta in testa al giro, e le due letture
vedono lo stesso stato.

**Più voci e `scatter`.** La formula è quella di sempre: l'attesa di una voce
oltre la prima è `(1 − scatter) · attesa della voce 0 + scatter · attesa
letta per la propria voce`. Ma le mappe delle voci partono tutte da `x0` e
sono deterministiche: danno la **stessa sequenza**, e `scatter` — una media
fra due attese uguali — **non sposta niente**. Le voci restano in fase, e si
distinguono solo per gli offset di `voices:`. È una scelta: dare alle voci
stati iniziali diversi resta fuori dalle mappe caotiche della #307 (vedi
[[mappe-caotiche]], «Trade-off»).

**Chi legge la densità.** Per uno stream con `grain.iot`, `Stream.density`,
`Stream.fill_factor` e `Stream.distribution` sono `None`; `Stream.iot` è il
parametro, `Stream.density_mode` vale `iot`. I commenti dello score Csound
scrivono `Inter-onset:` al posto di `Density:` e `Distribution:`, e la riga
di fine render dice `· iot`.

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
  duration: (0.02 + 0.08*m1)   # letta da una mappa: vedi «Mappe ed espressioni»
  iot: 0.1                 # attesa fino al grano successivo, al posto di
                           # density / fill_factor: vedi «Densità»
  duration: [[0, 0.02], [30, 0.2]]
  duration_range: 0.01     # banda larga 0.01 s (default: ±0.005 s)

  # Unità di misura per duration e duration_range: seconds (default) |
  # samples | milliseconds. La conversione avviene al parse e vale per
  # scalari ed envelope in ogni grafia, {type, points} compreso (solo i
  # valori, l'asse tempo resta invariato).

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

  # Unità della BANDA, indipendente da quella della base: absolute (default)
  # | relative. Con "relative" duration_range è una frazione di duration,
  # letta istante per istante — quindi qualunque duration_unit non la tocca,
  # perché una frazione non ha unità da convertire.
  duration_range_unit: relative
  duration: [[0, 0.021], [60, 500]]  # ms, da un campione a mezzo secondo
  duration_range: 0.5                # ±25% della durata corrente, sempre

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

  # Verso di lettura INTERNO al grano, dichiarativo (alternativa a reverse).
  # -1 = lettura all'indietro, +1 = lettura in avanti. Indipendente dal segno
  # di pointer.speed_ratio: la testina puo' percorrere il buffer all'indietro
  # mentre i grani leggono in avanti.
  read_direction: 1

  # Accetta envelope: il verso cambia nel tempo, a gradino
  read_direction: [[0, 1], [12, -1], [20, 1]]
  # ERRORE: read_direction insieme a reverse (gruppo esclusivo)
  # ERRORE: read_direction: 0 / 0.5 (solo -1 e +1)
  # ERRORE: interpolazione diversa da step
```

### `grain.read_direction` — il verso di lettura del grano

Tre grandezze diverse, che è bene non confondere:

| grandezza | governa | segno |
|---|---|---|
| `pointer.speed_ratio` | la velocità e il verso con cui la **testina** percorre il buffer | negativo = percorrenza all'indietro |
| `grain.read_direction` | il verso con cui il **grano** legge il materiale | `-1` indietro, `+1` avanti |
| blocco `pitch` | l'**altezza percepita** (trasposizione) | sempre positivo, per costruzione |

`read_direction` è alternativa a `reverse`, non un suo complemento: **le due
chiavi insieme sono un errore** (`InvalidFieldValueError`), non una priorità.
Governano la stessa grandezza con semantiche opposte, e sceglierne una in
silenzio nasconderebbe l'errore invece di segnalarlo. Con **entrambe assenti**
il comportamento è quello di sempre: modalità `auto`, il verso segue il segno
di `pointer.speed_ratio`.

Il caso che con `reverse` richiede un gate stocastico saturato:

```yaml
# Prima: gate al 100% per un comportamento che di stocastico non ha nulla
pointer: {speed_ratio: -1}
grain: {reverse:}
deviation_probability: {reverse: 100}

# Adesso: dichiarato
pointer: {speed_ratio: -1}
grain: {read_direction: 1}
```

**L'interpolazione è `step`, implicita e obbligatoria.** L'envelope si scrive
come una spezzata qualsiasi e il gradino lo impone la chiave; `type: step`
esplicito è ridondanza accettata. Qualunque altro interp — `linear`, `cubic`,
in forma dict, per-punto (`[t, v, type]`) o BP group (`[points, interp]`) — è
un **errore esplicito**, mai un avviso e mai una correzione silenziosa: il
verso di lettura ha due stati, non una rampa fra i due.

**I valori dichiarati stanno in `{-1, +1}`.** Con `step` imposto l'envelope
emette solo i valori scritti ai breakpoint, quindi il problema non è
l'interpolazione ma la dichiarazione: `0.3` non è un verso e `0` non ha un
segno. Ogni altro valore è rifiutato al parse, senza arrotondamento al segno.

Verso stocastico: si dichiara con la chiave `read_direction` del blocco
`deviation_probability`, che è la probabilità per-grano di **ribaltare** il
verso dichiarato (vedi [DeviationProbability](#deviation_probability-variazione-stocastica)).
`deviation_probability: {reverse: N}` resta legata a `grain.reverse` e non
tocca `read_direction`.

```yaml
grain:
  read_direction: 1        # base: in avanti
deviation_probability:
  read_direction: 30       # il 30% dei grani legge all'indietro
```

Con qualunque `duration_unit` diverso da `seconds` la `grain.duration` va
**sempre indicata esplicitamente**: il default `0.05` è in secondi e non
verrebbe convertito, per cui base (secondi) e `duration_range` (campioni o
millisecondi) finirebbero in domini diversi. Ometterla → `MissingFieldError`.

`duration_range_unit: relative` toglie il range da quella conversione: una
frazione è adimensionale, e convertirla la renderebbe muta (`0.5` sotto
`samples` diventerebbe `0.5/48000`). La `duration` esplicita resta comunque
obbligatoria — quel vincolo riguarda la base. Vedi
[Banda relativa](#banda-relativa-param_range_unit).
`output_sr` è una config globale del motore (48000 Hz), non impostabile
per-stream nello YAML — per questo `milliseconds`, che non lo usa, dà le stesse
durate a qualunque frequenza di rendering mentre `samples` no.

Bounds: `grain_duration` ∈ [1 campione (`1/48000` s), 10 s] — in `samples`:
[1, 480000]; in `milliseconds`: [1/48, 10000]. Valori frazionari sono ammessi
in ogni unità: il renderer arrotonda al campione più vicino
(`n_out = max(1, round(dur * sr))`).

Note sui grani a precisione di campione:

- **Sotto i 10 campioni non si finestra** (issue #225). Il renderer NumPy
  ignora `envelope` per i grani più corti di **208.3 µs** (10 campioni a
  48 kHz) e li rende piatti. A quelle lunghezze la finestra non taglia i
  bordi: decima il grano. `hanning(3)` è `[0, 1, 0]` — tiene un campione su
  tre e paga tre campioni di budget; a 4 ne tiene due su quattro. E l'effetto
  spettrale è l'opposto di quello per cui la finestra esiste: su un tono a
  440 Hz la quota di energia sopra 2 kHz (lo sporco da troncamento) vale
  0.767 per il grano non finestrato a 3 campioni contro 0.917 per lo stesso
  grano con `hanning`. Il pareggio arriva intorno ai 30 campioni; 10 è la
  linea scelta, conservativa rispetto alla misura.
- **Il grano muto non esiste più.** Era il caso degenere della stessa
  faccenda: a 1-2 campioni le finestre simmetriche cadono sui due estremi,
  che valgono zero (`np.hanning(2) == [0, 0]`), e le asimmetriche che partono
  da zero cadono sul solo punto di partenza (`exporise(1) == [0]`). Il grano
  veniva generato, moltiplicato per zero e reso come **silenzio digitale
  assoluto**, senza scarto e senza log: con `grain.duration` dentro la banda
  `round(dur * output_sr) == 2` — **31.25-52.08 µs**, estremi inclusi perché
  `round()` in Python è half-to-even — il risultato era un buco di centinaia
  di ms. Ora quelle lunghezze stanno sotto la soglia e non vengono finestrate.
- **Il salto alla soglia è dichiarato**: attraversando i 208.3 µs il livello
  del grano scende di colpo, da −0.4 dB (`expodec_strong`) a −7.3 dB
  (`rexpodec`), −4.3 dB con `hanning`. È la finestra che entra in funzione.
  Con una `duration` che sweepa attraverso la soglia si sente uno scalino:
  se dà fastidio, usare `rectangle`, che è piatta da entrambi i lati.
- **Divergenza NumPy/Csound**: i due renderer non sono mai stati dichiarati
  bit-equivalenti e sotto i 10 campioni divergono di più di prima, perché
  Csound la finestra la applica comunque. Legge la tabella con `poscil` a
  `1/p3` Hz e fase iniziale 0: su un grano di 1 campione ne legge solo il
  primo punto, quindi è **muto a N=1** su tutte le finestre che partono da
  zero (`hanning`, `bartlett`/`triangle`, `blackman`, `blackman_harris`,
  `sinc`, `half_sine`, `exporise`, `exporise_strong`, `rexporise`). Sotto i
  10 campioni la scelta del renderer domina il risultato più della scelta
  della finestra.
- **Densità derivata**: con `fill_factor` e grani da 1 campione la density
  `fill_factor/duration` è enorme — `fill_factor: 2` su un grano da un
  campione fa 96000 grani/secondo — e dalla #272 viene onorata per intero:
  prima saturava a 4000 in silenzio. È il regime in cui il conteggio dei
  grani esplode, ed è il motivo del `[DENSITY_HIGH]` sul clip log.

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

  # Unità delle posizioni nel sample (opzionale)
  loop_unit: normalized   # "normalized": valori [0,1] scalati su sample_dur_sec
                          # "seconds" (canonico) / "absolute" (alias): secondi
                          # default: seconds — NON eredita da time_mode
```

`loop_unit` governa i tre parametri di loop **e** `start`: sono tutte posizioni
nel sample, stesso dominio. Il vocabolario è chiuso — `seconds`, `absolute`,
`normalized` — e un'unità fuori da quello è `InvalidFieldValueError`, non un
silenzioso "assoluto".

Fino alla v8.0.0 inclusa `loop_unit` assente ereditava da `time_mode`: uno stream
`normalized` vedeva `start` e i parametri di loop scalati per `sample_dur_sec`
anche senza nessun loop dichiarato. Le due chiavi parlano di assi diversi (vedi
§10.1) e ora sono indipendenti. (issue #222)

Bounds: `pointer_speed_ratio` ∈ [-100, 100], `pointer_deviation` ∈ [-1, 1].

### `pointer.position` — la posizione dichiarata

`start` e `speed_ratio` sono una legge di moto: una partenza, più l'integrale
di una velocità. `position` è la seconda (issue #312): la posizione di lettura
**scritta**, grano per grano.

```yaml
maps:
  m1: {type: logistic, r: 3.2}
pointer:
  position: (m1)          # dove leggere, da 0 a 1 della finestra attiva
  loop_start: 0.2
  loop_dur: 0.1
  loop_unit: normalized
```

Con `r: 3.2` la logistica ha due valori, e i grani leggono da due sole
posizioni: a 0.513 e a 0.799 della finestra di loop.

- **Da 0 a 1 della finestra attiva**: la finestra di loop se c'è, altrimenti
  il file intero. `position: 0.5` senza loop è la metà del file; con
  `loop_start: 0.4`, `loop_end: 0.9` è 0.65 s. È sempre una frazione,
  qualunque sia `loop_unit`: quella dice in che unità sono scritti i bordi
  della finestra, non la posizione.
- **Un numero, un envelope o un'espressione.** Un numero è una lettura ferma;
  un envelope è uno scrub dichiarato (`[[0, 0], [10, 1]]` attraversa la
  finestra in dieci secondi) e segue il `time_mode` dello stream;
  un'[espressione](#le-espressioni) legge una mappa.
- **Al posto di `speed_ratio` e `start`**: scritte insieme a `position` sono
  un **errore** (`InvalidFieldValueError` su `pointer.position`), non una
  priorità, e vale per presenza della chiave — anche `start: 0`. Una
  `position:` lasciata vuota è un errore anche lei (`MissingFieldError`).
  Senza `position` il puntatore è quello di sempre, bit per bit.
- **Fuori da 0–1 rientra a capo**, non si taglia: `1.25` è `0.25`, `-0.25` è
  `0.75`, e un envelope da 0 a 3 ripassa la finestra tre volte. È lo stesso
  wrap del [confinamento al loop](#confinamento-al-loop), quindi non è un
  errore al caricamento e non scrive niente sul clip log. Un valore **non
  finito** dato da un'espressione (`sqrt` di un negativo, una divisione per
  zero) va all'inizio della finestra, e quello sì è una riga di clip log.
  Scritto nello YAML — `position: .nan`, o un punto `.inf` in un envelope —
  è un errore al caricamento (`ParameterBoundError`), come su ogni altro
  parametro: rientra a capo ciò che è finito.
- **La finestra vale da subito.** Con `speed_ratio` il puntatore entra nel
  loop quando ci arriva; con `position` non c'è un viaggio, e il primo grano
  è già dentro. La finestra può muoversi (`loop_start` e `loop_dur` a
  envelope): la posizione resta dentro la finestra di quell'istante. È il
  **vincolo** del puntatore.
- **`offset_range` e gli offset di pointer delle voci si sommano come
  prima**: la deviazione per grano è una frazione della finestra attiva, e il
  tutto resta confinato dentro la finestra.
- **Il verso `auto` vale «avanti».** Senza `grain.reverse` né
  `grain.read_direction` il verso del grano segue il segno di `speed_ratio`;
  con `position` una velocità dichiarata non c'è, e il grano si legge in
  avanti anche quando la posizione scende. Il verso si dichiara con
  [`grain.read_direction`](#grainread_direction--il-verso-di-lettura-del-grano)
  (o `grain.reverse`).
- **Più voci.** Con una mappa a `clock: grain` ogni voce ha il suo stato e
  percorre la sua sequenza di posizioni.

In partitura i grani stanno alle posizioni lette. Un `position` a envelope è
la curva `pointer_position`, e così i valori realizzati di un `position` a
espressione (vedi [Partitura ed export](#le-espressioni)); la curva
`pointer_speed` non c'è, perché la velocità non è dichiarata.

Bounds: `pointer_position` ∈ [0, 1), a capo (`WRAPPING_PARAMETERS` in
`parameter_definitions.py`: l'unico parametro i cui bounds non tagliano).

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

## Mappe ed espressioni (`maps:`)

Uno stream può dichiarare una **mappa iterata** e far leggere un parametro del
grano da quella, attraverso un'**espressione** (issue #307). Una mappa è una
regola che calcola il prossimo valore dal precedente: fra un grano e il
successivo c'è memoria, e una manopola sola (`r`) porta dall'ordine (un
valore, poi cicli di 2, 4, 8 valori) al disordine.

```yaml
- stream_id: s1
  sample: x.wav
  maps:
    m1: {type: logistic, r: 3.5}
  grain:
    duration: (0.02 + 0.08*m1)
```

Con `r: 3.5` la logistica percorre quattro valori (0.827, 0.501, 0.875,
0.383) e le durate dei grani, in ciclo, 86, 60, 90, 51 ms.

Per il modello — cosa fa una mappa, perché un'espressione e non una chiave
`min`/`max`, che cosa resta fuori — vedi [[mappe-caotiche]]; per aggiungere un
tipo di mappa al catalogo, [[add-map]].

`maps:` sta **dentro lo stream**, non in testa al documento: con `file:` la
testa del file importato viene ignorata, e dentro lo stream la mappa viaggia
col file. Lo stesso nome in due stream sono due mappe.

### Le chiavi di una mappa

| chiave | valore | default |
|---|---|---|
| `type` | il tipo di mappa (vedi sotto) | obbligatoria |
| `r` | il parametro della mappa: un numero o un envelope | obbligatoria |
| `clock` | quando la mappa fa un passo: `grain`, oppure i passi al secondo (numero o envelope), al più uno per campione | `grain` |
| `iterate` | al posto di `clock`: i passi fatti da `x0` a ogni lettura, intero da 1 a 40 | — |
| `x0` | lo stato iniziale, un numero | quello del tipo |
| `y0` | lo stato iniziale della seconda variabile, per le mappe che ne hanno due | quello del tipo |
| `transient` | i passi scartati prima del primo grano, intero da 0 a 100000 | 300 |
| `x`, `y` | le equazioni di una mappa [`type: custom`](#type-custom--lequazione-scritta-a-mano) | — |

Il **nome** di una mappa (`m1`) è fatto di lettere, cifre e `_`, e non
comincia con una cifra. Non può essere un nome che in un'espressione vuol dire
già un'altra cosa: una funzione, `pi`, `e`, `t`, e nemmeno `x`, `y`, `r`.

Un `maps:` scritto male si ferma al caricamento con un `MapConfigError` che
nomina il punto (`maps.m1.r`) e lo stream: `maps` che non è un dizionario o è
vuoto, un `type` che non c'è, `r` che manca o non è un numero finito, una
chiave sconosciuta, un `x:` accanto a un tipo di catalogo, un `y0` su una
mappa a una variabile, un `clock` non positivo, `clock` e `iterate` insieme, uno
dei tre tetti superato. Un envelope di `r` o di `clock` scritto male è
l'errore di forma di ogni altro envelope, col suo path (`maps.m1.clock`).
Vedi [[errors]].

**I tre tetti.** `iterate`, `transient` e `clock` contano dei passi, e un
passo costa: senza tetto un numero grande scritto per sbaglio teneva fermo il
render invece di dire che cosa non va. Sono costanti di
`src/pge/maps/map_set.py`, leggibili senza costruire uno stream.

| chiave | tetto | perché |
|---|---|---|
| `iterate` | 40 (`MAP_ITERATE_MAX`) | si itera a ogni lettura, cioè a ogni grano; ed è il tetto del «Banco del chirp», che però lì taglia in silenzio. Oltre non c'è niente da sentire: a `r = 4` la logistica perde un bit dello stato iniziale a ogni passo, e dopo una cinquantina di passi l'iterata dipende dagli arrotondamenti, non più da `r` |
| `transient` | 100000 (`MAP_TRANSIENT_MAX`) | si fa una volta per mappa, e fin qui costa pochi millisecondi: più di trecento volte il default, abbastanza anche per gli attrattori che si raggiungono piano, vicino a una biforcazione |
| `clock` | un passo per campione (`output_sr`, 48000 di default), in ogni punto se è un envelope | è la risoluzione del motore, la stessa a cui arriva una mappa a `clock: grain` con l'attesa più corta che [`grain.iot`](#grainiot--lattesa-fra-due-grani) ammette. Un passo più fitto nessun grano lo vede da solo, e costa come un passo vero |

### I tipi di mappa

| `type` | passo | `r` | intervallo di `m1` | `x0` |
|---|---|---|---|---|
| `logistic` | `r*x*(1-x)` | 2.5 – 4 | 0 … 1 | 0.3 |
| `tent` | `r/2*min(x, 1-x)` | 2.5 – 3.999 | 0 … 1 | 0.3 |
| `sine` (Di Scipio 1999) | `sin(r*x)` | 0 – 4 | −1 … 1 | 0.1 |
| `cubic` | `r*x*(1-x*x)` | 1.5 – 3 | −1.2 … 1.2 | 0.3 |
| `henon` | `x: 1 - r*x*x + y`, `y: 0.3*x` | 0.8 – 1.4 | −1.3 … 1.4 (`m1.y`: −0.39 … 0.42) | 0.1, 0.1 |
| `circle` | `frac(x + r - 0.3*sin(2*pi*x))` | 0 – 1 | 0 … 1 | 0.2 |
| `custom` | `x:` (e `y:`) scritte nello YAML | libero | dipende dall'equazione | 0.1, 0.1 |

- L'**intervallo di `m1`** è un fatto della mappa, e chi scrive un'espressione
  deve conoscerlo: `minimo + (massimo − minimo) * m1` vale per una mappa che
  vive in 0…1. La stessa fascia 20–200 ms è `(0.020 + 0.180*m1)` sulla
  logistica e `(0.110 + 0.090*m1)` sul seno di Di Scipio, che vive fra −1 e 1.
- **Le mappe a due variabili** (`henon`, e una `custom` con `y:`) hanno uno
  stato `(x, y)`: i due aggiornamenti usano la coppia di prima, e la seconda
  variabile si legge in un'espressione come **`m1.y`**. Vale nei tre modi di
  avanzare. `m1.y` su una mappa a una variabile è un errore
  (`nome sconosciuto`).
- **La `tent` non arriva a `r = 4`**: lì la pendenza è 2, ogni passo raddoppia
  e toglie un bit, e in float64 la mappa collassa a zero in una cinquantina di
  passi, per sempre. Il tetto documentato è 3.999.
- **`sine` e `circle` passano da `sin`**, e fra macchine diverse i grani
  possono divergere. Le mappe fatte di sole somme e prodotti (`logistic`,
  `tent`, `cubic`, `henon`) sono identiche bit per bit ovunque; `sin` dipende
  dall'ultimo bit della libreria matematica, e una differenza di 10⁻¹² diventa
  di ordine 1 in una cinquantina di passi. Lo stesso YAML sulla stessa
  macchina dà sempre gli stessi grani; fra macOS e Linux, con queste due, non è
  garantito (`SIN_BASED_TYPES` nel catalogo). Vale anche per una `custom` che
  usa `sin`, `cos`, `exp`, `log`.
- L'intervallo di **`r`** è quello in cui la mappa è interessante e resta nel
  suo intervallo: non è un limite imposto. Fuori (`r: 4.5`) la mappa
  **scappa**: quando un valore non è finito, o supera 1000 in modulo, la mappa
  riparte da `x0` e lo scrive sul clip log (`[MAP_ESCAPE]`, con un limite di
  una riga ogni 5 s di stream).
- **`x0` non dipende dal `seed`**: una mappa è deterministica, ed è il suo
  punto. Lo stesso YAML dà la stessa sequenza con qualunque seed.
- Il **transitorio** fa sì che il primo grano sia già sull'attrattore. Con un
  transitorio diverso cambia la *fase* di un ciclo, non l'insieme dei valori.

Dati dello stesso catalogo, leggibili senza costruire uno stream: `MAP_TYPES`
e `MAP_KINDS` in `src/pge/maps/catalog.py`. Ogni voce di `MAP_KINDS` dichiara
con dei letterali `x0`, `r_range`, `value_range` (l'intervallo di `m1`) e, per
le mappe a due variabili, `y0` e `y_range`: un editor li legge dal sorgente.

#### `type: custom` — l'equazione scritta a mano

```yaml
maps:
  m2:
    type: custom
    x: sin(r*x)*cos(x)
    r: 3
  m3:
    type: custom
    x: 1 - r*x*x + y        # Hénon, scritta a mano
    y: 0.3*x
    r: 1.4
```

- **`x:` è obbligatoria, `y:` opzionale.** Con `y:` la mappa ha due variabili,
  e `m3.y` si legge nelle espressioni.
- Le equazioni sono scritte nel **linguaggio delle
  [espressioni](#le-espressioni)**, con le variabili `x`, `y`, `r` (lo stato
  di prima e il parametro) e le stesse funzioni e costanti. Non leggono le
  altre mappe né `t`. Qui le parentesi esterne non servono: la chiave dice
  già che è un'equazione.
- **Un tipo di catalogo con accanto un `x:` (o un `y:`) è un errore**: non si
  capirebbe quale delle due equazioni vale.
- `r` serve solo se un'equazione lo legge; `x0` e `y0` valgono 0.1 se non
  sono scritti (non zero: per molte equazioni zero è un punto fisso). `y0`
  su una mappa a una variabile è un errore, e così un'`x:` che legge `y`
  senza una `y:`.
- Un'equazione scritta male è un `ExpressionError` col suo path
  (`maps.m2.x`); una chiave che manca o è di troppo un `MapConfigError`.
- Un'equazione scritta a mano **scappa** più facilmente di una di catalogo:
  la rete è la stessa (riparte da `x0`, `y0`; `[MAP_ESCAPE]` sul clip log).
- Il caricamento lascia le equazioni come sono scritte: non le valuta e non
  avvisa.

### Come avanza una mappa

Una mappa sa solo fare «un altro passo». Lo YAML dice quando.

| scrittura | quando fa un passo | stato |
|---|---|---|
| `clock: grain` (default) | ogni volta che nasce un grano | uno **per voce** |
| `clock: 8` | 8 passi al secondo, a intervalli fissi; il valore resta fermo fino al passo dopo | nessuno: è una funzione del tempo |
| `clock: [[0, 2], [12, 20]]` | il passo k cade quando l'integrale del clock vale k | come sopra |
| `iterate: 7` | mai: a ogni lettura si riparte da `x0` e si fanno 7 passi con l'`r` di quell'istante | nessuno |

```yaml
maps:
  m1: {type: logistic, r: [[0, 3.0], [12, 4.0]], clock: [[0, 2], [12, 20]]}
  m2: {type: logistic, r: [[0, 3.0], [12, 4.0]], iterate: 7, x0: 0.1}
```

**`clock: grain`** — la mappa fa **un passo per grano e per voce**: è contata
sui grani, non sul tempo, e a densità doppia la stessa sequenza scorre in metà
tempo.

- Lo stato è **uno per voce**. Con più voci ogni voce percorre la sequenza
  dall'inizio; con `scatter` i cursori delle voci divergono, e ognuna continua
  a contare i suoi passi.
- La mappa avanza in un punto solo, in testa al giro della voce, e chi la
  legge non la muove: due parametri che leggono `m1` nello stesso grano vedono
  lo stesso valore, in qualunque ordine.
- Il passo si conta anche quando `voices.num_voices` tiene la voce spenta: la
  sequenza di una voce non dipende da quando viene accesa.

**Clock a orologio** — `clock` è un numero di passi al secondo, o un envelope.

- Il primo passo cade a `t = 0`; il passo k dove l'integrale del clock da 0
  vale k. `clock: 5` è un passo ogni 0.2 s; da 2 a 20 passi/s lineari in 12 s
  sono 132 passi, radi in principio e fitti alla fine.
- Il valore **resta fermo** fra un passo e l'altro: i grani nati dentro lo
  stesso passo leggono lo stesso valore.
- È una funzione del tempo e **non ha uno stato per voce**: tutte le voci
  leggono lo stesso valore allo stesso istante, anche con `scatter`.
- Il clock deve essere **positivo e finito**, e al più un passo per
  campione, in ogni punto se è un envelope: altrimenti è un errore al
  caricamento.

**`iterate: n`** — il modo dell'articolo di Di Scipio (DAFx99). Sta **al posto
di `clock`**, e non è un clock: a ogni lettura si riparte da `x0` e si fanno n
passi con l'`r` di quell'istante. Il valore è l'n-esima iterata della stessa
funzione, e a disegnare la curva è il movimento di `r`.

- Con `r` fermo il valore è **fermo**: tutti i grani leggono lo stesso numero.
- Con `r` a envelope è una curva nel tempo, campionata dagli onset dei grani.
  `n` è la manopola della ruvidezza: più passi, più la curva è frastagliata.
  Va da 1 a 40 (vedi i tetti qui sopra).
- Nessuno stato, né per voce né nel tempo. Non c'è un transitorio: `transient`
  insieme a `iterate` è un errore.
- Se la mappa scappa non si itera oltre: il valore è `x0`.

`clock` e `iterate` insieme sono un **errore**, non una priorità.

**`r` a envelope** si legge all'istante del passo — con `clock: grain`
l'istante del grano, con un clock a orologio l'istante in cui il passo cade —
o della lettura, in `iterate`. Il transitorio si fa a `r(0)`. Gli envelope di
`r` e di `clock` seguono il `time_mode` dello stream come ogni altro: con
`time_mode: normalized` i loro tempi sono frazioni della durata.

Per chi deve sapere quando una mappa a orologio fa i suoi passi senza
generare i grani: `stream.map_set.step_times(nome, fino_a)`.

### Le espressioni

Un parametro che legge una mappa si scrive come un'espressione **fra
parentesi**, dove stanno un numero o un envelope.

| | |
|---|---|
| operatori | `+ - * / **`, parentesi |
| funzioni | `sin cos tan abs sqrt exp log floor round sign min max pow frac clip fold wrap` |
| costanti | `pi`, `e` |
| nomi | le mappe dichiarate nello stream (`m1`), la seconda variabile di quelle che ne hanno due (`m1.y`), e `t`: i secondi dall'inizio dello stream |

- Le precedenze sono quelle di Python: `-m1**2` è `-(m1**2)`, e `2**3**2` è
  `2**(3**2)`, cioè 512.
- `clip(v, lo, hi)` appiattisce ai bordi, `fold(v, lo, hi)` riflette
  (`fold(1.3, 0, 1)` dà 0.7), `wrap(v, lo, hi)` riparte dall'altro capo
  (`wrap(-0.25, 0, 1)` dà 0.75). `frac(v)` è la parte frazionaria; `round`
  arrotonda il mezzo verso l'alto (`round(2.5)` dà 3). `min` e `max` prendono
  quanti argomenti si vuole, le altre il loro numero esatto.
- Non c'è `eval`: l'interprete è un modulo suo
  (`src/pge/expressions/expression.py`), e un testo che non è un'espressione
  di questo linguaggio è un errore.
- Una catena di somme o di prodotti può essere lunga quanto si vuole. Ciò che
  si annida — una parentesi, un segno, una potenza, una chiamata — si annida
  al più 50 volte (`MAX_DEPTH`): oltre è un errore al caricamento
  (`e' annidata troppo`). Un'espressione scritta a mano ne usa meno di dieci,
  le parentesi esterne comprese.

**Minimo e massimo non sono chiavi: sono la forma dell'espressione.**
`minimo + (massimo − minimo) * m1` — il minimo è il valore del parametro
quando la mappa è in fondo al suo intervallo, il massimo quando è in cima. La
mappa non usa per forza tutta la fascia scritta: con `r: 3.2` i valori sono
due soli.

**Dove vale.** Sul **valore base** di ogni parametro a schema (l'elenco è
`EXPRESSION_FIELDS` in `src/pge/expressions/fields.py`, una tupla letterale):

| | |
|---|---|
| uscita | `volume`, `pan` |
| grano | `grain.duration`, [`grain.iot`](#grainiot--lattesa-fra-due-grani), `grain.read_direction` |
| puntatore | [`pointer.position`](#pointerposition--la-posizione-dichiarata) |
| pitch | il valore, in ogni unità: `pitch.semitones`, `pitch.cents`, `pitch.quarter_tone`, `pitch.eighth_tone`, `pitch.ratio`, e `pitch.value` con `edo: N` |
| densità | `density`, `fill_factor`, `distribution` |

```yaml
maps:
  m1: {type: henon, r: 1.4}
volume: (-18 + 4*m1)
pan: (100*m1.y)
pitch:
  semitones: (12*m1)
```

Su `grain.read_direction` decide il **segno**: sotto zero il grano si legge
all'indietro, altrimenti in avanti (`(sign(m1 - 0.5))`). Su `density` e
`fill_factor` la densità cambia a ogni grano, e non è più una curva
dichiarata.

**Dove non vale**, il motore lo dice con un `ExpressionError` che nomina il
campo e suggerisce che cosa scrivere (`EXPRESSION_REFUSALS`, nello stesso
modulo):

| campo | perché, e che cosa scrivere |
|---|---|
| `pointer.speed_ratio` | la velocità si integra nel tempo per ricavare la posizione, e un'espressione non si integra: per leggere la posizione da una mappa c'è `pointer.position` |
| `pointer.start` | è la posizione di partenza, un numero: per una posizione che cambia a ogni grano c'è `pointer.position` |
| `pointer.loop_start`, `loop_end`, `loop_dur` | i bordi della finestra sono numeri o envelope: la finestra è il vincolo del puntatore, e la mappa muove la posizione al suo interno |
| `voices.num_voices` | il numero di voci si decide prima dei grani (è il picco del suo envelope): un numero o un envelope |

Lo stesso errore, col suggerimento generico, su ogni altro campo fuori
dall'elenco: le bande `_range`, `pitch.range`, `pointer.offset_range`,
`voices.scatter`, i parametri delle strategie di voce, e
`deviation_probability` (globale o per chiave: il campo è
`deviation_probability.volume`), dove il dettaglio dice che il campo vuole una
probabilità (0-100) o un envelope.

**Una stringa che non è un'espressione** resta l'errore di prima, anche nei
campi in cui un'espressione vale: `density: not_a_number` è un
`InvalidParameterError` («Formato non valido», con che cosa il campo vuole), e
`grain.read_direction: reverse` l'`InvalidFieldValueError` che spiega i due
versi. È scritta come un'espressione la stringa che sta tutta fra parentesi —
e se dentro è sbagliata lo dice l'interprete, con un `ExpressionError` — e
quella che senza parentesi l'interprete compila (`volume: -30 + 20*m1`): lì
l'`ExpressionError` propone le parentesi. Su `grain.duration` e `grain.iot`
ogni stringa è letta come un'espressione, come dalla #308.

**Quando si valuta.** A ogni grano, non al caricamento: è la differenza dalle
[espressioni matematiche nei valori](#9-espressioni-matematiche-nei-valori),
che sono costanti calcolate una volta sola. Il loader lascia com'è, senza
avvisi su stdout, una stringa fra parentesi che nomina una mappa dichiarata
nello stream, o `t`; le equazioni `x:` e `y:` di una mappa `custom`; e, nei
campi in cui un'espressione vale, anche una che nomina qualcosa che la
valutazione al caricamento non conosce: una funzione del linguaggio come
`sqrt`, `sin`, `clip`, o un nome sbagliato, che poi l'errore dell'interprete
nomina. Una costante che la valutazione sa fare
(`(10/2)`, `(0.05 * abs(-1))`) resta sua e diventa un numero, come prima.

**Gli errori sono al caricamento**, in un `ExpressionError` col campo
(`grain.duration`) e lo stream: una mappa non dichiarata, una parentesi che
manca, una funzione col numero sbagliato di argomenti, un'espressione scritta
senza le parentesi esterne.

**I valori non si validano al caricamento.** Un envelope fuori dai bounds è un
errore al parse; un'espressione no, perché i suoi valori nascono grano per
grano. Un valore che esce viene **tagliato** ai limiti del parametro e scritto
sul clip log, con `(EXP)` in fondo alla riga. Per riportarlo dentro in un
altro modo lo si scrive: `clip`, `fold`, `wrap`. (`pointer.position` non si
taglia: rientra a capo della finestra.)

- **Un valore infinito va dal suo lato**: `+inf` al massimo, `−inf` al minimo.
- **Un valore che non è un numero** (`nan`: `sqrt` di un negativo, `0/0`) non
  ha un lato, e va al **limite inferiore** del parametro: sul volume è
  silenzio (−120 dB), sulla durata un campione. Unica eccezione
  **`grain.iot`**, dove va al **tetto**, 100 s: al limite inferiore un'attesa è
  un campione, cioè 48000 grani al secondo, e un'espressione sempre `nan`
  teneva il render occupato per minuti. Al tetto il render finisce col primo
  grano (`NAN_TO_MAX_PARAMETERS` in `parameter_definitions.py`).
- **Il clip log di un'espressione ha un limite di frequenza**: una riga subito,
  poi una ogni 5 s di stream per parametro, col conto dei tagli taciuti nel
  frattempo (`+312 tagli taciuti`). Un'espressione fuori limite lo è a ogni
  grano, e una riga per grano sono decine di migliaia di righe. Il limite
  vale per le sole espressioni (`EXPRESSION_CLIP_LOG_INTERVAL`).

**Unità.** Con `grain.duration_unit` diversa da `seconds` il fattore si
applica al **risultato** dell'espressione: `(20 + 80*m1)` con
`duration_unit: milliseconds` sono gli stessi grani di `(0.02 + 0.08*m1)`.
Vale per `grain.duration` e per `grain.iot`.

**`_range` sopra un'espressione** resta lecito: `grain.duration_range`,
`volume_range`, `pan_range`, `pitch.range` sono un tremolio casuale attorno al
valore dato dalla mappa. La mappa non sostituisce
il generatore casuale dentro la banda.

**Cache.** Il fingerprint dello stream contiene `maps:` e il testo
dell'espressione: cambiare `r`, `clock`, `iterate`, `x0`, `transient` o
l'espressione rifà lo stem. Uno stream che non scrive queste chiavi ha i grani e il fingerprint di
prima.

**Partitura ed export.** Un parametro scritto come espressione non ha una
curva nota in anticipo: il suo valore dipende dallo stato della mappa, e
esiste solo nei grani generati. La partitura e la sessione Sonic Visualiser ne
mostrano i **valori realizzati** (issue #314):

- **i valori realizzati di ogni parametro a espressione**, sotto il nome del
  parametro (`grain_duration`, `volume`, `pan`, `pitch`, `pointer_position`,
  `grain_iot`, `density`…): il valore che il parametro ha dato a ogni grano
  della **voce 0**, a gradini — tenuto fino al grano dopo. È il valore che il
  grano ha avuto: tagliato ai limiti se usciva, e con la banda `_range` se
  c'è. In legenda, sotto il nome, l'**escursione vera** (`grain dur`,
  `50.6–90.0ms`): scritto 20–100 ms, usato 51–90;
- **il valore di ogni mappa**, `map__<nome>` (`map__m1`, e `map__m1.y` per la
  seconda variabile): a gradini per i modi a clock — un gradino per grano
  della voce 0 con `clock: grain`, un gradino per passo con un clock a
  orologio — e una curva continua per `iterate`. In legenda il nome della
  mappa e la sua escursione;
- **la densità che emerge**, `effective_density`: con `grain.iot`, e anche in
  modalità `fill_factor` quando `fill_factor` o la durata del grano sono
  un'espressione (lì `fill_factor / durata` non si può campionare). Con
  `grain.iot` c'è anche la curva dell'attesa, `grain_iot`.

Sono curve come le altre: `--plot-envelopes map` seleziona tutte le mappe,
`--plot-envelopes pan` i valori realizzati del pan; il preset `--bw` dà loro
un tratto proprio; nella sessione Sonic Visualiser sono layer con lo stesso
nome e nello stesso ordine. Un'espressione o una mappa che dà un valore solo
è una costante, e si vede con `--show-static`. Non hanno breakpoint annotati:
sono un punto per grano, non punti di controllo.

**Leggerle genera i grani** (la generazione è lazy), una volta: disegnare la
partitura non cambia il render e non pesca di nuovo da un generatore casuale.
Uno stream senza `maps:` e senza espressioni ha le curve di prima, nello
stesso ordine. Nei commenti dello score Csound compare il testo
dell'espressione.

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
  reverse: 5          # 5% probabilità di flip reverse (solo per grain.reverse)
  read_direction: 5   # 5% probabilità di ribaltare grain.read_direction
  envelope: 15        # 15% probabilità di cambiare finestra (se lista)

# Valore specifico come envelope
deviation_probability:
  volume: [[0, 0], [30, 80]]
  pan: 50
```

### Le cinque scritture della chiave

Ci sono cinque modi di scrivere `deviation_probability` "senza dirgli niente",
e **quattro su cinque danno lo stesso risultato**. Misurato su uno stream reale
(79 grani, `grain.read_direction: 1`, seed fisso, nessun `_range` dichiarato):

| YAML | gate | grani deviati |
|---|---|---|
| chiave **omessa** | `NeverGate` | 0 / 79 |
| `deviation_probability:` (scritta, vuota → `null`) | **probabilità implicita** (`DEFAULT_PROB`, 1%) | 1 / 79 |
| `deviation_probability: {}` | `NeverGate` | 0 / 79 |
| `deviation_probability: false` | `NeverGate` | 0 / 79 |
| `deviation_probability: {<chiave>: null}` | `NeverGate` | 0 / 79 |

L'eccezione è la seconda riga: **la chiave scritta e lasciata vuota è l'unica a
non dare `NeverGate`**. `null` non significa "assente" — significa *modalità
implicita*, cioè l'1% di jitter per grano su ogni parametro dello schema.

È la scrittura che più assomiglia a "non voglio deviazione" e fa l'opposto. Se
l'intenzione è disattivare, la scrittura da usare è `false` (o l'omissione); la
chiave vuota è una dichiarazione, non un'assenza.

> Non è specifico di un parametro: la modalità implicita vale per tutti. Si
> nota di più su `grain.read_direction`, dove il flip è udibile come inversione
> del verso, mentre su un parametro additivo l'1% si confonde con la grana.
>
> Con un `_range` esplicito le righe `NeverGate` diventano `AlwaysGate`: è la
> semantica *range-only* descritta qui sotto, e non riguarda queste scritture.

Il contratto è fissato da `tests/parameters/test_deviation_probability_scritture.py`.

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

`points` assente, `null` o un numero, un corpo vuoto (`points: []`, come la
lista nuda `[]`) e un `type` che non è uno dei tre nomi — maiuscole e spazi
attorno a parte, che la factory delle interpolazioni ignora — o scritto e
lasciato vuoto sono `InvalidFieldValueError` sulla chiave dell'envelope (issue
#288): vedi `docs/reference/errors.md`, «Envelope malformato (forma)». Un
`type: Cubic` è la cubica, come `type: cubic` (§4.5).

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
- Gruppo con meno di 2 punti → `InvalidFieldValueError` (zona senza segmenti
  interni), che nomina la chiave su cui il gruppo è scritto (issue #211).

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

**(c) Solo per le posizioni nel sample: `loop_unit`**

I parametri `loop_start`, `loop_end`, `loop_dur` (e `start`, che è scalare ma
segue la stessa unità) hanno una semantica aggiuntiva: `loop_unit: normalized`
scala i **valori** (asse Y) da `[0, 1]` a `[0, sample_dur_sec]`. Non agisce
sull'asse X, e **non** si deduce da `time_mode`: il suo default è `seconds`. È
documentato nella sezione 10.

#### 3.3 Scaling del formato compatto

Quando `time_mode: normalized` è attivo, anche `end_time` di un formato compatto
viene scalato per `duration`. Vedere `_scale_time_recursive` in `envelope.py`.
Si scala solo un `end_time` che è un numero: `true * 30` farebbe `30.0`, un
valore legittimo, e la scala cancellerebbe l'errore (§5.5) prima che il builder
lo veda (issue #211). Lo stesso per i breakpoint di una lista: se ne scala il
tempo solo se il builder li accetterà (`[t, v]`, `[t, v, type]`, `{t, v,
type?}` con `t` e `v` numeri), e il resto gli arriva com'è scritto — un
`[true, v]` non diventa un breakpoint a `t = durata`, e l'errore riporta
l'elemento come sta nel file. Anche un BP group si scala solo se il builder lo
espanderà (interp valido, almeno 2 punti): l'errore di arità riporta i punti
del gruppo come sono scritti, non moltiplicati per la durata.

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

Su `grain.read_direction` non è una scelta ma la natura della chiave: è
imposto, e ogni altro interp è un errore (vedi
[§10.5](#105-grainread_direction-step-imposto)).

#### 4.4 Discontinuità con formato compatto

Quando si concatenano cicli, il `BUILDER` inserisce automaticamente un offset
infinitesimale di `1e-6` secondi (`DISCONTINUITY_OFFSET` in `envelope_builder.py`)
tra il primo punto di un nuovo ciclo e il punto precedente, in modo che due
breakpoint non coincidano sullo stesso tempo. Questo permette discontinuità
intenzionali senza degenerare gli algoritmi di interpolazione.

#### 4.5 Come si scrive il nome

Il nome si legge in due modi, secondo dove sta.

**Il tipo globale non bada a maiuscole e spazi attorno**: il `type` della forma
dict e lo slot `interp` del formato compatto, che l'envelope prende come
proprio tipo. `Cubic`, `' cubic '` e `CUBIC` sono la cubica, e l'envelope tiene
il nome canonico (`env.type == 'cubic'`, issue #300): la stessa curva di
`cubic`, con le tangenti di Fritsch-Carlson, lo stesso stile nell'export Sonic
Visualiser e lo stesso ramo nella partitura.

```yaml
density: {type: Cubic, points: [[0, 10], [0.6, 40], [1.2, 15], [2.0, 30]]}
# identico a type: cubic
```

**Ogni altro interp si confronta alla lettera** con `linear`, `cubic`, `step`:
quello per-punto (`[t, v, type]`, `{t, v, type}`, §2.6), quello del BP group
(§2.7), l'`interp` di `chord_progression` e quello di `grain.read_direction`
(§10.5). `[0.5, 30, 'Cubic']` è `InvalidFieldValueError`. PGE-ls e gl-ls
controllano alla lettera questi stessi nomi: allargarli cambierebbe la
superficie che validano, e non è stato fatto.

Il tipo globale gl-ls non lo legge. L'editor d'inviluppo di PGE-ls sì, e alla
lettera: `{type: Cubic}` e lo slot `'CUBIC'` vi si disegnano come `linear`, e
salvati dalla GUI perdono il tipo (PGE-ls#72).

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
| 1         | `end_time`       | numero finito (non booleano) | sì         | **tempo assoluto finale** del blocco compatto |
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
- `x_finale > 100` → **errore** (`InvalidFieldValueError`, issue #211): il
  punto cadrebbe oltre la fine del ciclo, sovrapponendosi al successivo. Fino
  a #211 non c'era guard e l'envelope si rendeva in silenzio con l'ordine
  temporale dei breakpoint rotto. Stessa sorte per una `x` negativa (un
  breakpoint a tempo negativo) e per `x` che tornano indietro
  (`[[100, a], [0, b]]`): il ciclo si percorre in avanti una volta sola. Una
  `x` ripetuta resta valida — è la discontinuità.

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

Tutte alzano `InvalidFieldValueError` col nome della chiave su cui il compatto
è scritto (`density`, `grain.duration`, `deviation_probability.volume`, …) e lo
stream; dove cade dentro il blocco lo dice l'hint. Vivono in `EnvelopeBuilder`
e valgono per ogni chiave che accetta un envelope (issue #211) — prima le
applicava solo `grain.read_direction`, e sotto le altre chiavi lo stesso corpo
risaliva come `ValueError` nudo o si rendeva in silenzio.

- `n_reps` non intero o `< 1` → errore. Il booleano è escluso: `true` supera il
  riconoscimento della forma (in Python `bool` è un `int`) e renderebbe un
  ciclo senza dire niente.
- `end_time` non numero (booleano compreso), non finito (`.inf`, `.nan`) o
  `<= time_offset` → errore.
  `time_offset` è 0 nella forma diretta e l'ultimo breakpoint precedente in una
  lista mista. Con `time_mode: normalized` il controllo sul tipo vale prima
  della scala (§3.3): un `true` non diventa la durata dello stream. Il
  confronto con `time_offset` invece vale dopo, perché l'offset in una lista
  mista è accumulato da elementi già scalati: l'errore riporta allora i due
  istanti in secondi, e l'hint lo dice.
- `pattern_points` vuoto → errore.
- punto del pattern non piatto → errore. Piatto è la forma di un breakpoint
  nudo: `x` e `y` numeri (il booleano no: `true` non è `1`) e il terzo
  elemento, se c'è, il nome di un'interpolazione; una macro-forma annidata non
  lo è. Le scale delle `y` (`grain.duration_unit`, `loop_unit: normalized`,
  §10.1) non convertono una `y` che non è un numero, per la stessa ragione di
  §3.3. `x` fuori da `[0, 100]` o che torna indietro → errore (§5.3.1).
- `time_dist` con un nome fuori dal registro (§6) o con parametri che la
  distribuzione non accetta → errore. I vincoli sui parametri li applica il
  costruttore di ciascuna distribuzione.
- `interp` (quarto elemento) che non è `linear`/`cubic`/`step` (maiuscole e
  spazi attorno a parte, come per il `type` del dict) → errore, sulla
  sotto-posizione `envelope.compact.interp` quando la chiave non è passata
  (issue #288). Vale per lo slot che l'envelope prende come proprio tipo:
  quello del compatto diretto, o del primo compatto di una lista che ne
  dichiara uno. Lo slot di un compatto dentro `{type, points}`, dove decide il
  `type` del dict, resta ignorato come lo resta un nome valido. Omesso, `null`
  o scritto vuoto, il tipo resta `linear`.

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
- `power.exponent` non numerico → `InvalidFieldValueError`

Tutti scattano alla costruzione della distribuzione. Da uno YAML risalgono come
`InvalidFieldValueError` sulla chiave dell'envelope (§5.5, issue #211), con
l'eccezione della distribuzione nel `__cause__`. `power` era l'unico a non
validare il proprio parametro, e falliva più tardi con un `TypeError` dentro
`calculate_distribution`. Il controllo su `exponent` è sul **tipo** (non è un
numero) e non sui bound: qualunque reale è un esponente legittimo.

Nessuna delle cinque rifiuta i booleani in quanto tali — sono numeri — ma i
bound qui sopra li trattano diversamente, perché non sono la stessa condizione:

| | `true` (vale 1) | `false` (vale 0) |
|---|---|---|
| `power.exponent` (nessun bound) | passa | passa |
| `exponential.rate > 0` | passa | errore |
| `geometric.ratio > 0` | passa | errore |
| `logarithmic.base > 1` | **errore** | errore |

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

Il loader YAML (`Generator._eval_math_expressions`) valuta le espressioni
racchiuse tra parentesi prima di passare il dato al parser envelope.

| | |
|---|---|
| operatori | `+ - * / // **`, parentesi |
| funzioni | `abs`, `int`, `float`, `min`, `max`, `pow` |
| costanti | `pi`, `e` |

Sintassi:

```yaml
volume: [[0, -12], [(pi*5), 0], [(10*3), -12]]
grain:
  duration: (1/20)
  duration_range: (pi/100)
pitch:
  ratio: (2**(7/12))                 # ratio del semitono x7
density: (max(8, 100/4))             # 25.0
```

L'espressione è valutata a parse-time, non a run-time: il risultato è un numero
che diventa parte del breakpoint. Non è quindi modulabile dinamicamente.

- **Gli argomenti di una funzione si separano con la virgola**: `(max(3, 7))`
  vale 7, `(pow(2, 3))` vale 8, `(min(1, 2, 3))` vale 1 (issue #309: prima la
  virgola non era ammessa, e una funzione a due argomenti restava una
  stringa).
- **Un intero resta un intero**: `(2*2)` è 4 e `(10/2)` è 5.0, come in
  Python. Conta dove il motore pretende un intero (`n_reps` di un ciclo,
  `iterate` di una mappa).
- **L'espressione sta tutta dentro le parentesi esterne.** Si valuta solo ciò
  che sta fra parentesi: `((10/2)/10)` vale 0.5, mentre `(10/2)/10` e
  `2*(3+4)` sono scritte per metà fuori, e sono un **errore al caricamento**
  (`ExpressionError`) che nomina il campo e propone la grafia con le
  parentesi. Prima uscivano valutate a metà, come la stringa `5.0/10`, e più
  a valle erano un errore di tipo. È la stessa regola delle
  [espressioni che leggono una mappa](#le-espressioni). Non è scritta per
  metà fuori ciò che il loader valuta già per intero: `-(90/2)` vale −45.0 e
  `-(pi)` vale −π, come prima (sostituite le parentesi resta un numero).
- Una stringa con delle parentesi che **non** è un'espressione non è toccata
  da questa regola: è un errore solo la stringa che, messa intera fra
  parentesi, vale un numero. Ciò che fra parentesi non è un numero — una
  parola, una coppia `(1, 2)` — resta il testo che era; un nome sconosciuto
  lascia sullo stdout l'avviso `impossibile valutare`.
- La regola vale dove il motore legge un numero: fuori dagli stream solo su
  `seed` (un titolo in `composition:` è testo: `title: 11 - (2026)` non è un
  errore), e dentro uno stream non su `stream_id` e `sample`.

Fa eccezione una stringa tutta fra parentesi che nomina una mappa dichiarata
in `maps:` dello stesso stream, o `t`: quella non è una costante, il loader la
lascia com'è e la compila il parser dei parametri, per valutarla a ogni grano.
È un altro linguaggio, con le sue funzioni: vedi
[Mappe ed espressioni](#mappe-ed-espressioni-maps). Nei campi in cui
un'espressione vale (`volume`, `pan`, `grain.duration`, `pointer.position`…:
l'elenco è `EXPRESSION_FIELDS`) il loader lascia com'è
anche una stringa che nomina un nome che questa valutazione non conosce
(`sqrt`, `clip`): la compila l'interprete, senza l'avviso
`impossibile valutare`.

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

Unità ammesse: `seconds` (canonico), `absolute` (alias di `seconds`),
`normalized`. **Default `seconds`**, indipendente da qualsiasi altra chiave;
un'unità fuori vocabolario è `InvalidFieldValueError`.

Con envelope normalizzato sui valori:

```yaml
pointer:
  loop_unit: normalized
  loop_start: [[0, 0.0], [30, 0.8]]  # da 0% a 80% della durata del sample
```

Internamente `PointerController._pre_normalize_loop_params` usa
`Envelope._scale_raw_values_y` per moltiplicare ogni Y dei breakpoint per
`sample_dur_sec` prima di costruire l'`Envelope`. Funziona anche su formati
compatti: il pattern `[x%, y]` viene scalato sul valore. Si scala solo un punto,
un breakpoint o un BP group che il builder accetterà (§3.3): ciò che non lo è
resta com'è, e lo rifiuta il builder nominando la chiave (§5.5, issue #211).

Vale in ogni grafia, e la forma dict non fa eccezione: `points` si legge come
la lista nuda, quindi un compatto o un BP group scritti direttamente dentro
`{type, points}` si scalano come scritti da soli. Fino alla issue #289 no: la
scala percorreva `points` elemento per elemento, il compatto e il gruppo
diretti restavano nell'unità dello YAML, e il motore li leggeva in secondi —
un loop diverso da quello scritto, senza errori. La stessa regola vale per la
conversione di `grain.duration_unit` (§ Blocco Grain), che passa per la stessa
funzione.

```yaml
pointer:
  loop_unit: normalized
  # il pattern è scalato per sample_dur_sec
  loop_start: [[[0, 0.1], [100, 0.2]], 1.0, 2]
  # identico, nella forma dict:
  # loop_start: {type: linear, points: [[[0, 0.1], [100, 0.2]], 1.0, 2]}
```

### Differenza chiave da `time_mode`

Sono due chiavi indipendenti, e la ragione è che parlano di grandezze che non
hanno niente in comune:

|  | `time_mode: normalized` | `loop_unit: normalized` |
|---|---|---|
| asse | **X** (tempo) | **Y** (valore) |
| riferimento | `duration` dello stream | `sample_dur_sec` del file audio |
| dominio | la timeline della composizione | la lunghezza di un file su disco |

I due **coesistono**, e su uno stesso envelope agiscono insieme senza toccarsi:

```yaml
duration: 20
time_mode: normalized
pointer:
  loop_unit: normalized
  loop_start: [[0, 0.25], [1, 0.75]]   # X: 0..1 → 0..20 s di stream
                                       # Y: 0.25..0.75 → 25%..75% del sample
```

Con un sample da 8 secondi: a `t=0` il loop parte da 2.0 s del file, a `t=20`
da 6.0 s, a metà stream da 4.0 s.

**`loop_unit` non eredita da `time_mode`** (issue #222). Fino alla v8.0.0 inclusa lo
faceva, e un solo keyword finiva per governare i due assi: uno stream che
dichiarava `time_mode` per i propri envelope si vedeva spostare anche la
testina di lettura, `start` compreso, senza aver detto niente al riguardo.
`start` è `is_smart=False` e quindi non ha bounds, per cui lo spostamento non
sollevava nulla: wrappava modularmente e rendeva un suono diverso da quello
scritto.

**Migrazione:** per riavere il comportamento precedente basta scrivere
`loop_unit: normalized` nel blocco pointer. Dalla v9.0.0 alla v9.1.0 il motore
lo diceva da sé, con un warning `[LOOP_UNIT]` che nominava le chiavi
interessate; passata quella release l'avviso è stato tolto (issue #242), e il
default `seconds` non viene più annunciato.

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

> **Un envelope che non si costruisce è un errore.** Un corpo malformato —
> `[]`, `['x']`, un dict senza `points` — solleva `InvalidFieldValueError` sul
> campo `deviation_probability.<chiave>` (o `deviation_probability` per la
> forma globale). Prima veniva accettato in silenzio come probabilità 100%,
> cioè la variazione applicata a **tutti** i grani: il contrario di quanto
> scritto, e senza nulla in output che lo dicesse.

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
avviene nel controller del blocco, `VoicesController` (issue #284), via
`_parse_strategy_kwarg`, che usa
`Envelope.is_envelope_like` per discriminare. Una lista o un dict che envelope
non è (`step: []`, `pitch_range: [1, 2, 3]`, un dict senza `points`) è
`InvalidFieldValueError` su `voices.<asse>.<kwarg>` al parse (issue #288):
prima lo Stream si costruiva e il render moriva al primo grano, o con una voce
sola finiva senza che la strategy fosse mai consultata. Il rifiuto vale anche
con `num_voices: 1`.

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

#### 10.5 `grain.read_direction`: `step` imposto

`read_direction` (vedi [Blocco Grain](#grainread_direction--il-verso-di-lettura-del-grano))
è l'unico parametro con un'interpolazione **imposta** invece che scelta: il
valore grezzo viene avvolto in `{type: step, points: <scritto>}` prima del
parser, e ogni interp dichiarato diverso da `step` solleva
`InvalidFieldValueError` invece di essere accettato o corretto in silenzio.

```yaml
grain:
  read_direction: [[0, 1], [12, -1], [20, 1]]   # step, senza doverlo scrivere
```

Le **forme** dell'envelope restano tutte quelle documentate qui — lista di
breakpoint, dict `{points: ...}`, BP group, formato compatto, lista mista — e
valgono identiche nei due modi di scriverle: quello che è accettato come lista
nuda è accettato dentro `points`, e viceversa. A essere imposta è
l'interpolazione, non la sintassi.

Il rifiuto copre tutte le forme in cui un interp è dichiarabile: dict
(`type:`), tag per-punto `[t, v, type]`, BP group `[points, interp]` e formato
compatto (quarto elemento). Così cade anche il caso del segmento **di confine**
fra due macrozone, che l'interp di gruppo non governa (vedi
[BP group](#4-tipi-di-interpolazione)): con `step` ovunque non esiste un
segmento che possa produrre valori intermedi.

Conseguenza sui valori: l'envelope emette solo i valori scritti ai breakpoint,
che devono stare in `{-1, +1}`. La validazione è a parse-time e precede il
clamp dei bounds, così `read_direction: 0.5` produce un errore sul dominio a
due valori invece di passare silenziosamente il clamp `[-1, 1]`.

Di suo questa chiave aggiunge solo i due guard di **dominio** — interp `step`
e valori in `{-1, +1}` — e li applica per primi: un corpo che li viola entrambi
riceve l'errore sul dominio. I guard sulla **forma** — arità del BP group,
`end_time` e `n_reps` del compatto, pattern, distribuzione temporale, elemento
non riconosciuto — non sono suoi: stanno in `EnvelopeBuilder` e valgono per
ogni chiave (vedi [§5.5](#55-validazioni)). Anche qui alzano
`InvalidFieldValueError` con il campo `grain.read_direction` e lo `stream_id`,
compreso `end_time <= time_offset` nella lista mista. Fino a #211 esistevano
solo per questa chiave, applicati da `read_direction.py` al valore grezzo, e lo
stesso corpo sotto un'altra chiave risaliva come `ValueError` nudo o si rendeva
in silenzio.

#### 10.6 `num_voices` come envelope

`num_voices` è un caso particolare: viene parsato come `Parameter` che ammette
envelope, ma il `VoiceManager` pre-alloca `max_voices` pari al picco massimo dei
breakpoint (vedere `VoicesController`). Le voci eccedenti il valore
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
| Loop pointer normalizzato (valori)            | `loop_unit: normalized` + `loop_start: 0.0`        | Scala Y per sample_dur_sec; default `seconds`, indipendente da `time_mode` |
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
   - **Stream come file** (#290): `resolve_stream_files` sostituisce ogni voce
     `file:` di `streams:` con lo stream che importa, letto con lo stesso
     loader. È prima del math eval, quindi le espressioni dello stream
     importato si valutano al passo 2 come quelle del master.
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
  `is_compact_format`, `_expand_compact_format`, `is_bp_group`,
  `_expand_bp_group`, `DISCONTINUITY_OFFSET`
- `src/pge/envelopes/envelope_interpolation.py` — `LinearInterpolation`,
  `StepInterpolation`, `CubicInterpolation`
- `src/pge/envelopes/envelope_segment.py` — `NormalSegment` con hold behavior
- `src/pge/envelopes/envelope_factory.py` — `InterpolationStrategyFactory`
- `src/pge/envelopes/time_distribution.py` — `TimeDistributionFactory` e le 5 strategie
- `src/pge/parameters/parser.py` — `GranularParser.parse_parameter` + validazione
- `src/pge/parameters/gate_factory.py` — uso di envelope per `deviation_probability`
- `src/pge/controllers/pointer_controller.py` — `loop_unit` e scaling dei valori loop
- `src/pge/parameters/loop_unit.py` — vocabolario di `loop_unit` (`LOOP_UNITS`) e
  chiavi che interpreta (`LOOP_UNIT_SCOPE`)
- `src/pge/controllers/window_selection_strategy.py` — `_validate_curve_range`
- `src/pge/controllers/voices_controller.py` — `_parse_strategy_kwarg` per envelope nelle voice strategy

---

## Tabella Bounds Parametri

| Parametro | Min | Max | Default | Note |
|-----------|-----|-----|---------|------|
| `density` | 0.01 | — (nessun tetto; `.inf`/`.nan` restano un errore) | — | grani/secondo; sopra 4000 avvisa sul clip log (#272) |
| `fill_factor` | 0.001 | 50 | 2.0 | priorità su density |
| `distribution` | 0 | 1 | 0.0 | 0=sync, 1=async |
| `grain_duration` | 1/48000 (1 campione) | 10 | 0.05 | secondi; `duration_unit` li porta in `samples` o `milliseconds` |
| `grain_iot` | 1/48000 (1 campione) | 100 | — | secondi, segue `duration_unit`; l'attesa fra due grani (`grain.iot`), al posto di `density` / `fill_factor` / `distribution` |
| `grain_duration_range` | 0 | 1 | — | secondi; con `duration_range_unit: relative` il numero è una frazione e il dominio è quello della modalità (`RELATIVE_RANGE_BOUNDS`), non quello del parametro — che i due `1` coincidano è un caso |
| `volume` | -120 | 12 | 0.0 | dB |
| `pan` | -3600 | 3600 | 0.0 | gradi |
| `pitch_ratio` | 0.001 | 8 | 1.0 | ratio diretto |
| `pitch_semitones` | -36 | 36 | 0 | ±3 ottave |
| `read_direction` | -1 | +1 | — | solo `-1` e `+1`; assente = modalità `auto` |
| `pointer_speed_ratio` | -100 | 100 | 1.0 | negativo = indietro |
| `pointer_position` | 0 | 1 | — | frazione della finestra attiva (`pointer.position`), al posto di `speed_ratio` e `start`; fuori da 0–1 **rientra a capo**, non si taglia |
| `pointer_deviation` | -1 | 1 | 0.0 | offset per-grano |
| `loop_start` | 0 | sample_dur | — | secondi; `loop_unit: normalized` li scrive come frazione |
| `loop_end` | 0 | sample_dur | — | secondi; `loop_unit: normalized` li scrive come frazione |
| `loop_dur` | 0.005 | sample_dur | — | secondi; `loop_unit: normalized` li scrive come frazione |
| `num_voices` | 1 | 256 | 1 | intero |
| `scatter` | 0 | 1 | 0.0 | 0=sync, 1=indip. |

Per la sintassi completa multi-voice, vedere [[multi-voice]].
Per la sintassi envelope (in ogni parametro che la accetta), vedere la sezione
[Envelopes](#envelopes) interna a questo doc.
