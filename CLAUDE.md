# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A compositional system for granular synthesis. The pipeline transforms high-level YAML configurations into audio output through either a two-stage Csound pipeline (YAML → SCO → AIF) or direct NumPy rendering (YAML → AIF).

Inspired by Barry Truax's DMX-1000 (1988).

## Claude Code Behavior

**Lingua:** Rispondi sempre in italiano. No emoji, no emoticon, mai.

**Prima di toccare qualsiasi file:** leggi il file effettivo con Read — non assumere nulla sull'implementazione senza aver verificato il codice.

**Prima di modificare un modulo esistente:** esegui `/impact-analysis`.

**Entry point TDD:** usa `/new-feature <nome>` per avviare ogni refactoring o nuova funzionalità — proponi le suite di test prima di scrivere codice di produzione, attendi conferma del design.

**Codice generato:** fornisci prima il codice, poi chiedi se l'utente vuole un documento markdown di confronto. Non generare automaticamente documenti markdown di confronto.

**Csound:** fai sempre riferimento al FLOSS manual e fornisci link agli opcode referenziati.

## Slash Commands

- `/new-feature <nome>` — apre branch + avvia workflow TDD completo
- `/impact-analysis` — analisi impatto prima di modificare moduli esistenti
- `/run-tests [path]` — lancia pytest (suite completa o specifica)
- `/explain-module <path>` — spiega un modulo in profondità prima di modificarlo
- `/release` — workflow merge + tag + release notes

## Development Process

**CRITICAL: Test-Driven Development (TDD)**

Per refactoring e nuove funzionalità:
- Se modifichi logiche esistenti: applica TDD (test rossi → verdi)
- Se aggiungi feature completamente nuove: applica TDD
- Se fix minori o docs: usa giudizio, ma `make tests` sempre obbligatorio prima di commit
Prima di scrivere codice di produzione:

**Non generare mai codice di produzione senza aver prima discusso e approvato il design con l'utente.**

**CRITICAL: Test Gate prima di commit, PR e tag**

Prima di eseguire qualsiasi operazione git significativa (commit, push, PR, tag, release):

1. Esegui `make tests` e verifica che tutti i test passino (exit code 0)
2. Se un test fallisce, **non procedere** — analizza la causa e correggi prima
3. Per i tag di release, esegui anche `make e2e-tests` se disponibile

```bash
make tests        # OBBLIGATORIO prima di ogni commit/PR/tag
make e2e-tests    # OBBLIGATORIO prima di ogni tag di release
```

Questo vale anche per refactoring, fix al Makefile e modifiche alla documentazione
che toccano file importati dai test.

Questo progetto ha copertura test estensiva. Mantieni questo standard di qualità per ogni nuova funzionalità.

## Build Commands

### Setup
```bash
make setup                    # Full project setup
make check-system-deps        # Verify Python 3.12, csound, sox installed
```

### Build Pipeline
```bash
make all                      # Build default file (FILE=PGE_test)
make FILE=name all            # Build specific config
make all TEST=true            # Build all configs in configs/

# Renderer selection (default: csound)
make FILE=name RENDERER=numpy all      # NumPy direct rendering
make FILE=name RENDERER=csound all     # Csound rendering (default)

# Stem mode (one file per stream)
make FILE=name STEMS=true all                     # Csound stems
make FILE=name STEMS=true CACHE=true all          # Incremental build (skips unchanged)
make FILE=name STEMS=true RENDERER=numpy all      # NumPy stems
```

### Testing
```bash
make tests                    # Run full test suite
make tests-cov                # Run with HTML coverage report
make TEST_FILE=tests/core/ tests   # Run specific test directory
```

### Development Flags
- `AUTOKILL=true/false`: Auto-quit iZotope RX 11 before build (macOS only, default: true)
- `AUTOPEN=true/false`: Auto-open output files (default: true)
- `AUTOVISUAL=true/false`: Generate PDF score visualizations (default: true)
- `SHOWSTATIC=true/false`: Show static analysis output (default: true)
- `PRECLEAN=true/false`: Run clean before build (default: true, disabled when CACHE=true)

## Architecture

For full documentation see `docs/ARCHITECTURE.md` (renderers, caching, OCP design) and `docs/multi-voice.md` (voice strategies).

### Implementation Notes

- **Grain is a frozen dataclass** — never mutate after creation
- **Window Registry:** WindowController pre-registers all window functions at Stream init — FtableManager table numbering depends on this; don't lazy-register
- **Stream Cache:** active only with `STEMS=true CACHE=true RENDERER=csound`; StreamCacheManager fingerprints YAML per stream, only dirty streams re-render
- **Voice System:** each voice generates its own grain list; interleaved into `self.grains` (flat, ordered by onset) for backward compatibility
- **Time Modes:** `time_mode: normalized` maps 0.0–1.0 to actual duration at grain generation time
- **Math in YAML:** expressions like `(pi)` and `(10/2)` are evaluated via safe_eval before parsing

## Common Workflows

When adding a new parameter, renderer, window function, or variation strategy: read `docs/workflows.md` first — lista i file esatti da toccare nell'ordine giusto.

For YAML syntax (parameter, envelope, voices): see `docs/yaml-reference.md`.

## Platform Notes

- macOS: Fully supported (Apple Silicon and Intel)
- Linux: Fully supported (iZotope RX integration disabled automatically)
- Python: Requires 3.12 or higher
- Dependencies: csound (for Csound renderer), sox (for audio trimming), NumPy/SciPy (for NumPy renderer)

## Documentation

- **Architecture & rendering** (Csound/NumPy, caching, OCP, e2e tests): `docs/ARCHITECTURE.md`
- **Multi-voice system** (pitch/onset/pointer/pan strategies): `docs/multi-voice.md`
- **Common workflows** (how to add parameters, renderers, windows, strategies): `docs/workflows.md`
- **YAML reference** (parameter syntax, envelope syntax, voices, flags): `docs/yaml-reference.md`