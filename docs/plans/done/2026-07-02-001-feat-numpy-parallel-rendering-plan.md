---
slug: 2026-07-02-001-feat-numpy-parallel-rendering
type: plan
status: done
tags: [rendering, numpy, performance, multiprocessing, cli]
sources:
  - src/rendering/numpy_parallel.py
  - src/rendering/numpy_audio_renderer.py
  - src/rendering/renderer_factory.py
  - src/core/grain.py
  - src/main.py
  - make/build.mk
last_synced_commit: 9de1079
---

# Plan: feat — rendering NumPy multi-core (`--jobs` / `JOBS`)

## Contesto

Il renderer NumPy (default del Makefile: `RENDERER=numpy`) era mono-core.
Profiling empirico (stream 30s, density 200, ~6000 grani):

- `generate_grains()`: 61 ms (7.5%) — Python puro, **stateful**: consuma il
  `random` globale seminato una volta in `Generator.create_elements()`;
  l'ordine di consumo determina la riproducibilità → NON parallelizzabile
  senza cambiare l'output di YAML esistenti.
- rendering NumPy (overlap-add + dc_block + write): 752 ms (92.5%) — **puro**
  (zero `random` in `src/rendering/`) → parallelizzabile.

Composizioni reali: `PGE_12min.yml` = 132 stream, `PGE_cim.yml` = density
fino a ~3000. Amdahl con 92.5% parallelo → ~4-5x su macchine consumer.
Requisito: deve girare su tutti i computer senza saturarli (default
prudente core-1, fallback sequenziale sotto soglia).

Vincoli verificati empiricamente prima del design:

1. `Grain` (frozen + `__slots__` manuale) non era picklable: l'unpickle
   ripristina gli slot via `setattr`, rifiutato dal `__setattr__` frozen.
   Fix: `__reduce__` che ricostruisce via `__init__`.
2. `ProcessPoolExecutor` con contesto `spawn` (~130ms startup per 2 worker):
   i worker re-importano i moduli → il codice worker vive in un modulo
   importabile senza side effect a import-time.
3. I thread non aiutano (GIL: loop Python per-grano su array ~2400 campioni);
   nessun BLAS nel path caldo → niente oversubscription con i processi.

## Analisi d'impatto (procedura `.claude/commands/impact-analysis.md`)

- **Moduli modificati:** `core/grain.py` (additivo: `__reduce__`),
  `rendering/numpy_audio_renderer.py` (kwarg `jobs`, path parallelo),
  `rendering/renderer_factory.py` (propagazione), `main.py` (flag),
  `Makefile`/`make/build.mk` (variabile `JOBS`).
- **Dipendenti diretti di `numpy_audio_renderer`:** `renderer_factory`,
  `main`. `RenderMode`, `RenderingEngine`, ABC `AudioRenderer`,
  `CsoundRenderer`, cache manager: invariati.
- **Test coinvolti:** `tests/core/test_grain.py`,
  `tests/rendering/test_numpy_audio_renderer.py` (regressioni: rounding
  onset, cache clean/dirty, guard `.voices` issue #117, passthrough Plan
  002), `tests/rendering/test_numpy_parallel.py` (nuovo),
  `tests/test_main_jobs_flag.py` (nuovo), `tests/e2e/test_numpy_renderer_e2e.py`.
- **Rischio principale:** riproducibilità bit-level dell'output con il
  default parallelo → gestito dal contratto di determinismo (sotto) e da
  `--jobs 1`.

## Design

Tutto il parallelismo vive dentro `NumpyAudioRenderer` (OCP: RenderMode ed
engine invariati). Primitiva worker unica:
`render_grain_chunk(chunk) -> (offset_samples, buffer_locale)`.

- Parent: coppie `(grain, onset_sample)` (relativo per STEMS, assoluto per
  MIX) ordinate per onset → chunk contigui (`chunk_grains`) → pool `spawn`.
- Worker (`init_worker`): registries propri caricati da disco una volta;
  rende ogni grano con `GrainRenderer` + CLAMP 1 e fa overlap-add in un
  buffer locale all'extent del chunk (~1/N della timeline → IPC minimo).
- Parent: somma i buffer locali in ordine di chunk fisso → `dc_block` →
  clamp → `sf.write` (invariati).
- Generazione grani: nel parent, prima del dispatch → seed identico a oggi.
  Check cache `is_dirty` prima di `.voices` (issue #117): invariato.

Policy jobs: `resolve_jobs('auto')` = `max(1, core-1)` via
`sched_getaffinity` (quote container) con fallback `cpu_count`; sotto
`PARALLEL_MIN_GRAINS` (1024) per chiamata si resta sequenziali. Pool lazy,
riusato tra stream (STEMS), `close()` esplicito.

Contratto di determinismo:

- `jobs=1` → bit-identico al rendering sequenziale storico;
- a parità di `jobs` → output byte-identico tra run;
- tra `jobs` diversi → cambia solo l'ordine delle somme float64
  dell'overlap-add: differenza < 1 LSB a 24 bit (verificata dai test).

Default: CLI/Make = `auto`; API libreria `NumpyAudioRenderer(jobs=1)` resta
conservativa.

## Test (TDD, rossi → verdi)

1. `test_grain.py::TestGrainPickle` — roundtrip pickle.
2. `test_numpy_parallel.py` — `resolve_jobs`, `chunk_grains`,
   `resolve_table_name`, `render_grain_chunk` in-process (equivalenza
   bit-exact col riferimento sequenziale, CLAMP 1, chunk vuoto).
3. `test_numpy_audio_renderer.py::TestParallelRendering` — jobs=2 vs jobs=1
   `< 2^-24` (single e merged, pool reale), determinismo byte-identico tra
   run, soglia → nessun pool, `close()`, riuso pool tra stream.
4. `test_main_jobs_flag.py` — `_parse_jobs` (default auto, interi, invalidi
   → exit 1) e wiring `_build_renderer` → renderer.
5. e2e: `TestNumpyStemsParallel` — build `JOBS=2` via make + equivalenza
   `JOBS=1` vs `JOBS=2` sotto 1 LSB 24-bit.

## Cross-repo

- **PGE-ls:** nessun impatto (superficie YAML invariata).
- **PGE-ui:** nuovo flag CLI opzionale `--jobs`; nessun aggiornamento
  obbligatorio (default retro-compatibile a livello di semantica; da
  valutare se esporre il controllo jobs nell'UI).
- **Paper CIM 2026:** il default `auto` cambia l'output a livello di bit
  (non udibile, < 1 LSB 24-bit): alla PR va valutato il bump del submodule
  (regola `submodule-sync-cim.md`).
