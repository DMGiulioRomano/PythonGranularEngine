# Changelog

Tutte le modifiche rilevanti al progetto sono documentate in questo file.
Formato basato su [Keep a Changelog](https://keepachangelog.com/it/1.0.0/).
Versioning semantico: [SemVer](https://semver.org/lang/it/).

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
