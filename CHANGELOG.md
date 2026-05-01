# Changelog

Tutte le modifiche rilevanti al progetto sono documentate in questo file.
Formato basato su [Keep a Changelog](https://keepachangelog.com/it/1.0.0/).
Versioning semantico: [SemVer](https://semver.org/lang/it/).

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
