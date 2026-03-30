# Changelog

Tutte le modifiche rilevanti al progetto sono documentate in questo file.
Formato basato su [Keep a Changelog](https://keepachangelog.com/it/1.0.0/).
Versioning semantico: [SemVer](https://semver.org/lang/it/).

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
