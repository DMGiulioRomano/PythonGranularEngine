# Changelog

Tutte le modifiche rilevanti al progetto sono documentate in questo file.
Formato basato su [Keep a Changelog](https://keepachangelog.com/it/1.0.0/).
Versioning semantico: [SemVer](https://semver.org/lang/it/).

---

## [Unreleased]

### Aggiunto

- Sistema pitch **unit-driven** (`PitchUnit`): il blocco `pitch` (base e
  `voices.pitch`) accetta sei unità di misura — `semitones`, `cents`,
  `quarter_tone`, `eighth_tone`, `edo` (EDO arbitrario `{divisions, value}`)
  e `ratio` — con un'unica interfaccia di conversione a ratio. Famiglia EDO:
  `2^(valore / N)`; `ratio` è moltiplicatore diretto. Default invariato
  (`semitones`, valore neutro → ratio 1.0). `EdoUnit`/`RatioUnit` e factory
  `make_pitch_unit` in `src/parameters/pitch_unit.py`; strategy unica
  `UnitPitchStrategy`. PR #84.
- Validazione strict del blocco `pitch`: una chiave sconosciuta — incluso un
  refuso sull'unità (es. `semitone:` invece di `semitones:`) — solleva
  `InvalidFieldValueError` che elenca le chiavi valide, invece di essere
  ignorata silenziosamente con default a semitoni neutri (No Silent Failures).
  Chiavi valide: le 6 unità più `range`. PR #84.

- Flag `normalized` nel blocco `voices.pointer` (YAML): opt-in per interpretare
  l'offset di pointer di voce come **frazione di `sample_dur_sec`** anziché in
  secondi. Default invariato (`normalized: false` → secondi), nessun breaking
  change sugli YAML esistenti. Vale per le strategie `linear` e `stochastic`;
  lo scaling avviene in `Stream._create_grain`, le strategy restano pure.
  Il flag accetta solo `true`/`false`: un valore non-bool solleva
  `InvalidFieldValueError` (nessuna coercion silenziosa, coerente con
  `grain.reverse`). Risolve l'ambiguità di unità documentata in issue #80.

- Flag `--format aiff|wav|flac` in `src/main.py` e variabile `FORMAT` nel
  Makefile: seleziona il formato audio di output (default `aiff`). Il formato
  viene propagato a `NamingStrategy` (estensione file), `NumpyAudioRenderer`
  (parametri `sf.write`), `StreamCacheManager` (fingerprint cache e
  garbage collection). Csound non richiede modifiche: rileva il formato
  dall'estensione del flag `-o`. Aggiunto `AudioFormat` dataclass in
  `src/rendering/audio_format.py`. Risolve issue #75.

- Target `make clean-rpp` (`make/clean.mk`): rimuove i file `.rpp` e `.rpp-bak`
  in `$(SFDIR)` (default `output/`) e nella root del repo. Risolve la
  pulizia esplicita dei progetti Reaper, prima orfana di target dedicato.
  Issue #65.
- Flag `CLEAN_RPP` nel `Makefile` (default `false`): controlla se `make clean`
  rimuove anche i `.rpp` in `output/`. Default `false` per preservare
  eventuale lavoro REAPER manuale (FX chain, automation, mixer routing) che
  non è rigenerabile da YAML. `CLEAN_RPP=true` ripristina il comportamento
  pre-issue#65 (wipe totale `$(SFDIR)/*`). Issue #65.
- Flag `REAPER_REUSE_TAB` nel `Makefile` (default `false`): se `true` con
  `REAPER=true`, prima di aprire il `.rpp` aggiornato lo script Lua
  `generated/open_reaper_tab.lua` scorre le tab REAPER aperte (`EnumProjects`)
  e chiude solo quella con path assoluto matching (action `40860` "Close
  current project tab"), poi apre nuova tab (action `40859`). Le altre tab
  restano intatte. Alternativa meno distruttiva ad `AUTOKILL_REAPER` per
  rebuild ripetuti dello stesso YAML. Risolve issue #59.
- Refactor `make/build.mk`: estratta macro `emit_open_reaper_lua` condivisa
  da `autopen_stems` e `autopen_single` per centralizzare la generazione
  dello ReaScript Lua (branch condizionale su `REAPER_REUSE_TAB`).
- Supporto Fedora / RHEL / Rocky / AlmaLinux nel branch `dnf` di
  `make install-system-deps` (issue #58). Installa `python3` + `sox`;
  stampa istruzioni per Csound (non disponibile nei repo Fedora / RPM
  Fusion — usare `RENDERER=numpy` o compilare dai sorgenti).
- README: sezione dedicata "Fedora / RHEL / Rocky / AlmaLinux" con
  istruzioni install e nota Csound; righe Fedora/RHEL nella tabella
  compatibilità Python; voce Fedora/RHEL nella tabella "Platform Support".
- Flag `AUTOKILL_REAPER` nel `Makefile` (default `false`): se `true` con
  `REAPER=true`, chiude REAPER prima del build via `SIGKILL`
  (`pkill -9 -x REAPER` macOS / `pkill -9 -x reaper` Linux), poi il `.rpp`
  viene riscritto e REAPER riaperto. Kill immediato senza dialog di
  salvataggio (modifiche manuali non salvate vengono perse — scelta
  intenzionale per garantire automazione non bloccante). Risolve issue #17 —
  REAPER non ricarica da disco le modifiche a `onset` / `duration` se il
  progetto e' gia' aperto.
- Target `make reaper-stop`: chiude REAPER se attivo (specchio di `rx-stop`).
- Multi-tab REAPER per YAML: se REAPER e' gia' in esecuzione, l'apertura del
  `.rpp` post-build avviene via ReaScript Lua generato al volo in
  `generated/open_reaper_tab.lua` (action `40859` "New project tab" +
  `Main_openProject`), invocato con `REAPER -nonewinst <script.lua>`.
  Build dello stesso YAML produce nuova tab con dati aggiornati; build di
  YAML diverso produce tab indipendente. Comportamento deterministico, non
  dipende da preferenze utente REAPER. Richiede REAPER >= 6.80.
- `docs/reaper-workflow.md`: workflow REAPER, requisiti, troubleshooting.
- `tests/e2e/test_reaper_makefile_e2e.py`: 6 scenari su target `reaper-stop`,
  wiring `AUTOKILL_REAPER`, default `REAPER_PATH`.

### Modificato

- Pitch delle voci **unit-agnostico**: la geometria della distribuzione vive
  ora nella `PitchUnit` via il nuovo metodo `materialize(position, amount)`
  (EDO additiva `2^(position·amount/N)`, `ratio` geometrica `amount^position`).
  Le voice pitch strategy emettono un **fattore di ratio** (`get_pitch_factor`,
  prima `get_pitch_offset` in semitoni); `VoiceConfig.pitch_offset` →
  `pitch_factor` (default `1.0` = identità) e `Stream._create_grain` moltiplica
  direttamente, senza il guard `!= 0.0`. Conseguenze su `voices.pitch` con
  `unit: ratio`: `range` e `stochastic` diventano **validi** (distribuzione
  geometrica, nessun ratio negativo o sub-zero); `step` passa da `i·step`
  (lineare) a `step^i` (geometrico) — **breaking sui valori delle voci ≥2** con
  `unit: ratio`. I path EDO (semitones/cents/quarter_tone/eighth_tone/edo)
  restano numericamente identici. `chord`/`spectral` restano semitone-locked.
- Default `REAPER_PATH`: da `$(FILE).rpp` (root del repo) a `$(SFDIR)/$(FILE).rpp`
  (default `output/$(FILE).rpp`). I progetti Reaper vivono ora accanto agli
  `.aif` generati, co-location semantica tra progetto Reaper e audio referenziati.
  **Breaking change minore:** script che cercano `foo.rpp` nella root vanno
  aggiornati a `output/foo.rpp`. `REAPER_PATH=custom/path.rpp` resta supportato
  per override esplicito. Issue #65.
- `make clean` non rimuove più `$(SFDIR)/*` con `rm -rf` per default. Usa `find`
  con esclusione di `*.rpp` per preservare progetti Reaper. Override via
  `CLEAN_RPP=true`. Issue #65.

### Modificato (breaking)

- Default `REAPER_PATH`: era `Project.rpp` fisso, ora `$(FILE).rpp`. Ogni YAML
  produce un `.rpp` con lo stesso basename, abilitando il multi-tab. Override
  esplicito via `REAPER_PATH=...` sempre supportato. Aggiornato help
  `make help` di conseguenza.

### Corretto

- `Stream._create_grain` (`src/core/stream.py`): l'offset di voce sul pointer
  veniva sommato *dopo* il wrap base, lasciando `grain.pointer_pos` oltre
  `sample_dur` per le voci con offset positivo. Ora la somma è re-wrappata
  in `[0, sample_dur)` con `% self.sample_dur_sec`. L'audio era già corretto
  (`GrainRenderer` e Csound ri-wrappano la traiettoria di lettura), ma la
  partitura (`ScoreVisualizer`) clippava le voci sopra il bordo del buffer,
  facendole "ricomparire" tutte insieme al wrap della voce 0 invece che
  sfasate. Ora `grain.pointer_pos` è la posizione reale di lettura, condivisa
  da audio e partitura. Risolve issue #79.
- Docstring delle voice strategy (`voice_pointer_strategy.py`,
  `voice_onset_strategy.py`, `voice_pitch_strategy.py`, `voice_pan_strategy.py`):
  rimosso il claim falso «seed deterministico / riproducibile tra sessioni».
  `hash()` su stringa è randomizzato per-processo (`PYTHONHASHSEED` non fissato),
  quindi l'offset per voce è stabile solo *entro* un run, non fra processi. Le
  docstring ora descrivono accuratamente il comportamento. Corretta anche la
  frase del README sui due renderer: stesso *comportamento musicale*, non output
  bit-identico (sequenze `random` indipendenti per i grani stocastici). Solo
  documentazione, nessuna modifica al comportamento. Risolve issue #76.
- Macro `autopen_stems` in `make/build.mk`: il glob `*.aif` hardcoded è stato
  sostituito con `*$(FORMAT_EXT)`, così con `FORMAT=wav` o `FORMAT=flac` il
  comando `AUTOPEN=true` apre i file con l'estensione corretta invece di non
  trovare nulla. Nessuna regressione: `FORMAT_EXT` defaults a `.aif`. Risolve
  issue #77.

- Naming dei file stem `.aif` in STEMS mode: separatore tra basename del
  progetto e `stream_id` cambiato da `_` a `__` (issue #56), per
  allinearsi al protocollo del server PGE-ui (`server.py` glob,
  `backend.js` fetch URL). Senza il fix la UI mostrava "no stems · render
  first" anche dopo render completati, e la riproduzione audio nel
  browser ritornava 404. Vedi
  `docs/plans/done/2026-05-21-001-fix-stem-naming-double-underscore-plan.md`.

### Rimosso

- Property legacy del pitch superate dal modello unit-driven:
  `Stream.pitch_ratio`, `Stream.pitch_semitones` (`src/core/stream.py`) e
  `PitchController.base_ratio`, `PitchController.base_semitones`
  (`src/controllers/pitch_controller.py`). Erano ratio/semitoni-only e prive di
  consumer in produzione (la visualizzazione legge ora `Stream.pitch_value` +
  `Stream.pitch_unit`, validi per ogni unità). Nessun impatto cross-repo: le 4
  property non erano referenziate da PGE-ls/PGE-ui. PR #84.

- Chiavi pitch_* morte nei dict di config di `ScoreVisualizer`
  (`src/rendering/score_visualizer.py`): rimosse le entry per-unità
  (`pitch_ratio`, `pitch_semitones`, `pitch_cents`, `pitch_quarter_tone`,
  `pitch_eighth_tone` e relative `*_prob`) da `envelope_ranges`,
  `envelope_colors` e dal dict `units`. Dopo il passaggio unit-driven la curva
  pitch usa l'unica chiave `'pitch'`: bounds da `pitch_unit.value_bounds()` e
  simbolo da `pitch_unit.symbol`, quindi quelle entry non venivano mai
  consultate. Conservata la sola chiave viva `'pitch'` in `envelope_colors`.
  Nessun impatto cross-repo (config interna del rendering).

---

## [v3.8.0] — "Arch/Manjaro compat + Cartridge removal" — 2026-05-12

### Aggiunto

- Detection Python multi-versione nel Makefile: cerca `python3.12..python3.16`
  versionati e fa fallback a `python3` generico con runtime version check
  (issue #51). Sblocca `make setup` su Arch/Manjaro (`pacman -Sy python`
  installa la versione corrente di sistema, oggi 3.14).
- `tests/test_makefile_python_detection.py`: 5 scenari (versionato 3.12,
  Arch-like 3.14, fallback python3 generico, no python, check-system-deps).
- README: tabella compatibilità OS, distinzione Ubuntu 24.04 / Debian 12,
  istruzioni Arch.
- Brief design UI editor visuale (documentazione).

### Modificato

- `Makefile`: `check-system-deps` riusa `$(PYTHON_CMD)` invece di
  `command -v python3.12` hardcoded.
- `Makefile`: `PYTHON_CMD` Darwin/Linux ora `python3` (placeholder, sovrascritto
  da `make/test.mk`); rimosso codice morto fuorviante.
- `configs/PGE_test.yml`: sample `pino.wav`.

### Rimosso (breaking change)

Issue #40. Rimossa completamente la classe `Cartridge` (tape recorder head)
e tutto il codice correlato. Feature non utilizzata da nessun YAML in
`configs/`, rappresentava solo debito tecnico.

- `src/core/cartridge.py` eliminato
- `csound/main.orc`: rimosso `instr TapeRecorder`
- `Generator.create_elements()` ora ritorna `List[Stream]` (era `Tuple[List[Stream], List[Cartridge]]`)
- Rimossi parametri/attributi `cartridges` da `Generator`, `CsoundRenderer`,
  `RendererFactory.create('csound', ...)`, `ScoreWriter.write_score`
- Test correlati rimossi (`tests/core/test_cartridge.py` e sezioni in test misti)

### Compatibilità

Chiave `cartridges:` in YAML viene ignorata silenziosamente (zero impatto
sui brani esistenti in `configs/`, verificato).

---

## [v3.7.0] — "EngineError extension: controllers + envelopes" — 2026-05-10

Issue #46 chiusa (follow-up di #38). Convertiti gli ultimi 11 raise
user-facing residui nei moduli `controllers/` e `envelopes/` alle sotto-classi
`EngineError` esistenti, completando l'unificazione della Categoria A
(config errors). I 5 raise di Categoria C (internal contracts) restano
intenzionalmente come `Exception`.

### Modificato

- **Controllers** (PR #47):
  - `controllers/window_selection_strategy.py`:
    - `_validate_curve_range` → `InvalidStrategyConfigError(strategy_kind="window")`
    - `MultiStateWindowStrategy.__init__` (<2 stati / non ordinati) →
      `InvalidStrategyConfigError(strategy_kind="window_multistate")`
    - `WindowStrategyFactory.create` (nome ignoto) →
      `StrategyNotFoundError(strategy_kind="window_selection")` (era `KeyError`)
  - `controllers/window_registry.py`:
    `WindowRegistry.generate_ftable_statement` → `InvalidWindowError`
  - `controllers/pitch_controller.py` / `controllers/density_controller.py`:
    violazione gruppo esclusivo → `InvalidFieldValueError`
- **Envelopes** (PR #48):
  - `envelopes/envelope_segment.py`: empty breakpoints → `InvalidFieldValueError`
  - `envelopes/time_distribution.py`: `n_reps < 1`, `total_time <= 0`,
    `rate <= 0` → `ParameterBoundError`

### Compatibilità

- Tutte le nuove sotto-classi ereditano `ValueError` via
  `ConfigError(EngineError, ValueError)` → `pytest.raises(ValueError)` e
  `except ValueError` pre-esistenti continuano a funzionare.
- Unica eccezione: `WindowStrategyFactory.create` nome ignoto cambia base
  da `KeyError` a `StrategyNotFoundError(ValueError)`. Verificato con grep:
  nessun caller `except KeyError` su questa API.

### Test

- 4172 unit tests passing
- 51 e2e tests passing (aggiunti `curve_exceeds_range`,
  `multistate_unsorted` in `tests/e2e/test_engine_errors_e2e.py`)
- Casi non raggiungibili da pipeline YAML (multistate <2 stati,
  pitch/density exclusive group, time_distribution input runtime,
  empty Segment breakpoints) coperti dai test unit

### Riferimenti

- Issue: #46 (PR1: #47 · PR2: #48)
- Issue padre: #38

---

## [v3.6.0] — "EngineError hierarchy & user-facing errors" — 2026-05-09

Issue #38 chiusa. Estensione completa della gerarchia `EngineError` introdotta
in #33: tutti gli errori di configurazione YAML e di rendering producono ora
output user-facing pulito su stdout (formato `[ERRORE] ...` + context
strutturato), con il traceback Python persistito separatamente nel log engine.

### Aggiunto

- **Gerarchia `EngineError` estesa** (`src/shared/exceptions.py`):
  - `ConfigError(EngineError, ValueError)` — base config errors
    - `MissingFieldError` — campo YAML obbligatorio mancante o null
    - `InvalidFieldValueError` — campo presente con valore invalido
    - `InvalidParameterError` — formato/tipo parametro non supportato
    - `ParameterBoundError` — parametro fuori bounds (scalare o envelope)
    - `StrategyNotFoundError` — strategia non registrata nel registry
    - `InvalidStrategyConfigError` — strategia trovata ma config invalida
    - `InvalidRendererError` — renderer kind sconosciuto
    - `InvalidWindowError` — window name/param invalido
    - `FtableError` — incoerenza FtableManager
  - `EngineRuntimeError(EngineError)` — runtime engine non-config
    - `CsoundRenderError(EngineRuntimeError, RuntimeError)` — subprocess csound fallito
- **Contratto `user_message()`** su tutte le sotto-classi: head `[ERRORE]` +
  righe indentate con context locale + `Stream:` + `Config:` (quando
  arricchiti) + path engine log appeso dal handler
- **Pattern context enrichment layered**:
  - `stream_id` arricchito al chiamante più prossimo (parser, strategy,
    controller) prima di rilanciare
  - `config_file` arricchito in `Generator.create_elements`
  - Handler unico polimorfico in `main.py` (`except EngineError`)
- **Documentazione**: nuovo `docs/error-handling.md` con gerarchia, contratto
  `user_message()`, pattern enrichment, esempi YAML invalidi → output
  user-facing, guida estensione, test patterns

### Modificato

- `parser.py`, `gate_factory.py`, registry strategy, `RendererFactory`,
  `NumpyWindowRegistry`, `WindowController`, `FtableManager`,
  `CsoundRenderer`, `main._build_renderer`: tutti i raise convertiti alle
  sotto-classi `ConfigError`/`EngineRuntimeError` corrispondenti

### Compatibilità

- `ConfigError` eredita anche da `ValueError` → catch espliciti pre-esistenti
  continuano a funzionare
- `CsoundRenderError` eredita anche da `RuntimeError` → idem

### Test

- 4161 unit tests passing
- 49 e2e tests passing (tutti gli errori coperti via subprocess su YAML inline)
- Pattern test: unit (isinstance + `user_message`), integration per modulo,
  handler in `main`, e2e subprocess

### Riferimenti

- Issue: #38 (PR1: #39 · PR2: #41 · PR3: #42 · PR4: #43 · PR5: #44)
- Doc: `docs/error-handling.md`

---

## [v3.5.0] — "Strategy passThrough" — 2026-05-09

### Aggiunto

- **`GrainClipStrategy`** (`src/strategies/grain_clip_strategy.py`):
  ABC + registry + factory pattern per filtrare i grain in post-process dentro
  `Stream.generate_grains`. `stream.voices` diventa l'unica fonte di verità su
  quali grain esistono — Csound e NumPy ricevono ora la stessa struttura.
  - `OverflowMarginClipStrategy(margin: float = 0.0)` — default; esclude grain
    la cui coda sfora `stream_end + margin`
  - `PassthroughClipStrategy` — nessun filtro; tutti i grain raggiungono il renderer
- **Nuovi campi YAML in `StreamConfig`**:
  - `clip_strategy: 'overflow_margin' | 'passthrough'` (default: `overflow_margin`)
  - `clip_margin: float` (default: `0.0`)
- **NumPy renderer passthrough puro** (`src/rendering/numpy_audio_renderer.py`):
  buffer dimensionato sull'extent reale dei grain in `stream.voices`
  (`max(g.onset + g.duration)`); il renderer non ha più opinioni proprie sui bounds

### Modificato

- `_add_grain_at_position`: rimossi i clamp `end_sample > n_total` e
  `onset_sample >= n_total` (responsabilità migrata a `GrainClipStrategy`).
  Preservato il clamp `onset_sample < 0` come difesa legittima
- Firme `_add_grain_relative` / `_add_grain_absolute` / `_add_grain_at_position`
  senza parametro `n_total`

### Risolto

- **#27** — Divergenza renderer su grain con `onset > stream.duration`:
  prima NumPy troncava silenziosamente la coda, Csound includeva il grain intero.
  Ora entrambi ricevono la stessa `stream.voices` filtrata
- **#32** — `make`: rilevamento package manager Linux a runtime (apt vs pacman)

### Compatibilità

Comportamento default più restrittivo per la coda: grain con
`grain.onset + grain.duration > stream_end` vengono esclusi. Per ripristinare
l'inclusione integrale (vecchio comportamento Csound), aggiungere al blocco stream:

```yaml
clip_strategy: passthrough
```

In modalità `passthrough` il file `.aif` può superare `stream.duration` se i grain
sforano. Tutti i config YAML scalari esistenti senza grain out-of-bounds restano
validi senza modifiche.

### Documentazione

- `docs/yaml-reference.md`: nuova sottosezione "clip_strategy — Controllo grain
  out-of-bounds" sotto "Configurazione Processo"
- Piani archiviati in `docs/plans/done/`: `2026-05-03-001-fix-grain-clip-strategy-plan.md`,
  `2026-05-03-002-fix-numpy-renderer-passthrough-plan.md`

### Test

4076 unit test + 39 e2e test, tutti verdi.

---

## [v3.4.0] — "Temporal Voice" — 2026-04-28

### Aggiunto

- **Parametri strategy dinamici** (`src/parameters/parameter.py`, `src/strategies/`):
  ogni parametro delle voice strategy accetta ora `float` o `Envelope` — il valore
  viene valutato al tempo reale di ogni grain, consentendo evoluzione temporale su
  tutte le dimensioni del sistema multi-voice
  - `resolve_param(param, time)` — primitiva condivisa; risolve `Union[float, Envelope]` a `float`
  - Tutte le strategy ABC ricevono `time: float`; implementazioni stochastiche separano
    direzione (cache fissa, seeded) da magnitudine (time-varying)
  - `VoiceManager` stateless: `get_voice_config(voice_index, time)` calcola on-the-fly per ogni grain
  - Parsing YAML: `_parse_strategy_kwarg` rileva list/dict → costruisce `Envelope`;
    supporta `time_mode: normalized`
  - `generate_grains` passa `voice_cursors[voice_index]` — ogni voce valuta l'envelope
    al proprio tempo musicale reale
- **`SpectralPitchStrategy`**: voci sui parziali della serie armonica
  (`src/strategies/voice_pitch_strategy.py`)
- **Config di test empirico** `PGE_dynamic_strategy_params_test.yml` (allegato release):
  19 stream da 10s (~3.75 min), ogni dimensione time-varying in isolamento e combinazione

### Parametri time-varying per strategy

| Strategy | Parametri |
|---|---|
| `step` pitch | `step` |
| `range` pitch | `semitone_range` |
| `stochastic` pitch | `semitone_range` |
| `linear` onset | `step` |
| `geometric` onset | `step`, `base` |
| `stochastic` onset | `max_offset` |
| `linear` pointer | `step` |
| `stochastic` pointer | `pointer_range` |
| tutte le pan | `spread` (via VoiceManager) |

### Backward compatibility

Tutti i config YAML scalari esistenti rimangono validi senza modifiche.

### Documentazione

- `docs/multi-voice.md`: aggiornata con architettura stateless e parametri dinamici

---

## [v3.3.0] — "Jazz Chords & Chord Inversions" — 2026-04-14

### Aggiunto

- **11 nuovi accordi jazz** in `CHORD_INTERVALS` (`ChordPitchStrategy`):
  - 5 voci: `dom9`, `maj9`, `min9`, `9sus4`
  - 6 voci: `dom9s11`, `maj9s11`, `min11`
  - 7 voci: `dom13`, `min13`, `maj13s11`, `altered`
- **Inversioni accordo**: `ChordPitchStrategy` accetta `inversion: int = 0` — ruota
  gli intervalli in modo che il grado k diventi la voce più bassa, normalizzata a 0

  ```yaml
  voices:
    num_voices: 4
    pitch:
      strategy: chord
      chord: dom7
      inversion: 1   # [0,3,6,8] invece di [0,4,7,10]
  ```

### Test

3974 test, tutti verdi.

---

## [v3.2.0] — "Window Transitions" — 2026-04-13

### Aggiunto

- **Transizioni probabilistiche tra finestre di grano** (`src/controllers/window_controller.py`):
  - Modalità `transition` — morphing da una finestra a un'altra guidato da una curva temporale:
    ```yaml
    grain:
      envelope:
        from: hanning
        to: expodec
        curve: [[0, 0], [30, 1]]
    ```
  - Modalità `multi-state` — transizione attraverso N finestre con separazione tra
    spazio del valore e spazio del tempo:
    ```yaml
    grain:
      envelope:
        states:
          - [0.0, hanning]
          - [0.3, bartlett]
          - [0.7, expodec]
          - [1.0, gaussian]
        curve: [[0, 0], [60, 1]]
    ```
  - La selezione per ogni grain è stocastica — il timbro dell'involucro evolve
    in modo probabilistico, non a step
- **`WindowStrategyFactory`**: registry + `**kwargs`, allineata al pattern delle voice strategy;
  estendibile senza toccare `WindowController`
- **Finestra `gaussian`** supportata anche nel renderer NumPy (era già disponibile nel path Csound)

### Corretto

- Errore leggibile quando `sample` è mancante o null in uno stream

### Breaking changes

- `envelope_range` rimosso dal YAML (era ridondante — la variazione è implicita
  dalla struttura lista/stringa)

---

## [v3.1.0] — 2026-04-08

### Aggiunto

- **`PointerController`**: quando `loop_start` è definito ma `start` non è esplicito
  nello YAML, il pointer parte da `loop_start(t=0)` invece che da `0`.
  Il valore `start` esplicito non viene mai sovrascritto.

### Corretto

- **Loop bounds relativi al file audio**: `loop_dur`, `loop_start`, `loop_end` non hanno
  più un upper bound statico arbitrario nel registry. `max_val=None` indica assenza di
  limite statico — il bound reale è sempre `sample_dur_sec`, passato dinamicamente.
  Eliminati i fallback `1000.0` / `100.0` che non rispecchiavano la realtà.

### Test

3802 test, 0 falliti.

---

## [v3.0.0] — "Stimmung" — 2026-04-05

### Aggiunto

- **Sistema multi-voice** (`src/controllers/voice_manager.py`, `src/strategies/voice_*_strategy.py`):
  ogni `Stream` può generare N voci parallele con offset indipendenti su quattro dimensioni
  - `VoiceManager`: orchestratore che pre-computa `VoiceConfig` per ogni voce all'init (O(1) in sintesi)
  - `VoicePitchStrategy`: `step`, `range`, `chord` (11 accordi), `stochastic`
  - `VoiceOnsetStrategy`: `linear`, `geometric`, `stochastic`
  - `VoicePointerStrategy`: `linear`, `stochastic`
  - `VoicePanStrategy`: già presente — `linear`, `additive`, `random`
  - `num_voices` e `spread` supportano `Parameter` (statico o envelope)
  - Voce 0 è sempre il riferimento immutabile (`VoiceConfig(0, 0, 0, 0)`)
  - Backward compatibility: `stream.grains` rimane flat e ordinato per onset
- **Nuovi parametri YAML**: `num_voices`, `voice_spread`, `voice_pitch_strategy`,
  `voice_pointer_strategy`, `voice_onset_strategy`
- **Cache incrementale per NumPy** (`src/rendering/numpy_audio_renderer.py`):
  `NumpyAudioRenderer` ora usa `StreamCacheManager` — log dirty/clean e skip stream
  invariati disponibili anche con `RENDERER=numpy STEMS=true CACHE=true`
- **Documentazione** `docs/multi-voice.md`: architettura, strategie, esempi YAML,
  invarianti di design, tabella test coverage
- **+322 test** (3787 totali vs 3465 di v2.1.0):
  - `test_voice_manager.py` (373 test)
  - `test_voice_pitch_strategy.py` (474 test)
  - `test_voice_onset_strategy.py` (380 test)
  - `test_voice_pointer_strategy.py` (305 test)
  - `test_stream_multivoice.py` (669 test)
  - `test_stream_voices_yaml.py` (492 test)
  - `TestNumpyAudioRendererCache` (7 test unit)
  - `TestNumpyStemsCache` (4 test E2E)

### Corretto

- **Cache numpy+stems**: `make/build.mk` non passava `--cache --cache-dir` al branch
  `STEMS=true RENDERER=numpy` — ogni build ri-renderizzava tutti gli stream senza log
- **Test E2E numpy** `test_no_cache_manifest_created`: asserzione errata rimossa —
  il test affermava che NumPy non usa mai la cache (ora la usa con `CACHE=true`)

### Modificato

- `src/core/stream.py`: integrazione `VoiceManager`, output `self.voices: List[List[Grain]]`
- `src/rendering/renderer_factory.py`: forward `cache_manager`/`stream_data_map` al renderer numpy
- `src/main.py`: crea `StreamCacheManager` anche per `renderer_type == 'numpy'`

---

## [v2.1.0] — "Reaper Gate" — 2026-03-30

### Aggiunto
- **ReaperProjectWriter** (`src/export/reaper_project_writer.py`): esportazione
  dei stream granulari in progetto Reaper `.rpp` (27 test TDD)
- Flag `REAPER=true` e `REAPER_PATH` nel Makefile per attivare l'export `.rpp`
- `--reaper` e `--reaper-path` come argomenti CLI di `main.py`

### Corretto
- **Onset silence in Csound STEMS**: `grain.to_score_line(onset_offset=0.0)` —
  in STEMS mode il renderer Csound ora sottrae `stream.onset` dagli onset dei
  grani (comportamento identico al renderer NumPy con `_add_grain_relative`)
  - `ScoreWriter.write_score(per_stream=True)` propaga l'offset attraverso
    `_write_stream_section` fino a `grain.to_score_line`
  - `CsoundRenderer.render_single_stream` ora passa `per_stream=True`
- **AUTOKILL/AUTOPEN con `REAPER=true`**: quando `REAPER=true`, il Makefile
  non chiude più iZotope RX prima della build (`rx-stop` saltato) e apre il
  file `.rpp` con REAPER invece dei `.aif` con iZotope dopo la build
  - Nuova variabile `OPEN_REAPER_CMD` (`open -a "REAPER"` su macOS,
    `xdg-open` su Linux) nella sezione rilevazione OS del Makefile

### Test
- +28 test TDD: `TestGrainToScoreLineWithOnsetOffset` (6),
  `TestWriteStreamSectionOnsetOffset` (3), `TestWriteScorePerStream` (4),
  `TestCsoundRendererPerStream` (2), `ReaperProjectWriter` (27)

---

## [v2.0.0] — "Granular Overlap" — 2026-03-30

### Aggiunto
- **NumPy renderer**: pipeline diretta YAML → overlap-add → `.aif` senza Csound
  - `STEMS=true RENDERER=numpy`: un file `.aif` per stream (onset relativi)
  - `STEMS=false RENDERER=numpy`: file unico con tutti gli stream mixati (onset assoluti)
- **Architettura OCP** (`src/rendering/`):
  - `AudioRenderer` ABC con interfaccia atomica (`render_single_stream` / `render_merged_streams`)
  - `RenderMode` strategy: `StemsRenderMode` e `MixRenderMode`
  - `RenderingEngine` facade — `main.py` agnostico rispetto al renderer
  - `NamingStrategy` — generazione path output separata dalla logica di rendering
  - `RendererFactory` — selezione renderer da stringa CLI
- **Garbage collection** cache: `garbage_collect()` rimuove dal manifest e dal filesystem
  gli stream rimossi o rinominati nel YAML (modalità `STEMS + CACHE`)
- **Suite E2E** (21 test, `@pytest.mark.e2e`, `make e2e-tests`):
  - Csound (15 test): prima build, build incrementale, rebuild parziale, GC
  - NumPy (6 test): STEMS e MIX mode
- `ARCHITECTURE.md`: documento architetturale con stato dell'arte, delta rispetto
  al design originale, copertura test
- `CLAUDE.md`: guida per Claude Code con architettura, convenzioni e workflow

### Modificato
- `main.py`: refactoring completo — agnostico rispetto al renderer, GC integrato
- `make/build.mk`: branch `RENDERER=numpy` per STEMS e MIX mode
- `make/test.mk`: nuovo target `make e2e-tests`
- `make/clean.mk`: nuovo target `make clean-file`
- `pytest.ini`: marker `e2e` registrato, escluso da `make tests` default
- **3465 test totali** (3444 unit + 21 E2E)

### Corretto
- `STEMS=true RENDERER=numpy` ora passa `--per-stream` — comportamento coerente
  con Csound (produceva un file mix invece di un file per stream)
- GC usa `os.path.dirname(output_file)` invece di `--sfdir` per individuare
  i file orfani — corretto su path assoluti costruiti dal Makefile

### Rinominato
- `DESIGN_PROPOSAL_OCP.md` → `ARCHITECTURE.md`

---

## [v1.1.0] — 2025

### Aggiunto
- `StreamCacheManager`: caching incrementale con fingerprint SHA-256
  per modalità `STEMS=true CACHE=true RENDERER=csound`
- Skip automatico degli stream invariati tra una build e l'altra
- `cache/` aggiunto a `.gitignore`
- Flag `CACHE=true` nel Makefile (disabilita `PRECLEAN` automaticamente)

### Corretto
- Bug posizione pointer in modalità loop

---

## [v1.0.0] — Release iniziale

- Pipeline Csound: YAML → SCO → AIF
- Generator con supporto stream granulari, cartridges, envelope, strategie
- Modalità STEMS e MIX
- Suite test unit (176 test)
- Supporto `solo`, `mute`, `time_mode: normalized`
- Ispirato al DMX-1000 di Barry Truax (1988)
