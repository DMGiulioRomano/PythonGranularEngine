# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A compositional system for granular synthesis. The pipeline transforms high-level YAML configurations into audio output through either a two-stage Csound pipeline (YAML → SCO → AIF) or direct NumPy rendering (YAML → AIF).

Inspired by Barry Truax's DMX-1000 (1988).

## Development Process

**CRITICAL: Test-Driven Development (TDD)**

Ad ogni refactoring o nuova funzionalità, valuta sempre se applicare TDD. Prima di scrivere codice di produzione:

1. Analizza quali suite di test sono necessarie
2. Scrivi i test rossi (failing tests)
3. Verificali localmente con `make tests` o `pytest`
4. Implementa il codice di produzione per far passare i test

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
make tests                    # Run full test suite (176 tests)
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

### Two-Stage Pipeline Philosophy

**Csound Renderer (default):**
1. Python generates Csound score (`.sco`) containing grain events
2. Csound renders `.sco` to audio using `csound/main.orc` orchestra

**NumPy Renderer (new):**
1. Python renders audio directly using NumPy overlap-add synthesis
2. No intermediate `.sco` file, no Csound invocation

Both renderers produce identical audio output and share the same grain generation logic.

### Core Architecture

**Grain Generation (shared by both renderers):**

```
Generator (engine/generator.py)
    ↓
  loads YAML → creates Stream objects
    ↓
Stream (core/stream.py) - orchestrator coordinating:
    ├─ ParameterOrchestrator: creates smart Parameter objects from YAML
    ├─ PointerController: tape head position (loop, jitter, speed)
    ├─ PitchController: transposition (semitones or ratio)
    ├─ DensityController: temporal distribution
    └─ WindowController: grain envelope selection
    ↓
  generates List[Grain] - immutable dataclass (core/grain.py)
```

**Rendering (diverges after grain generation):**

```
CsoundRenderer:
  Grain → ScoreWriter → .sco file → Csound → .aif

NumpyAudioRenderer:
  Grain → overlap-add synthesis → .aif
```

### Key Concepts

**Stream**: Continuous granular synthesis process with parameters that can evolve over time. Each stream:
- Reads from one audio sample (`refs/*.wav`)
- Has a duration, onset time, and stream_id
- Contains Parameter objects that may be static values or Envelope objects

**Parameter**: Smart parameter object that encapsulates:
- Base value (static float or Envelope for time-varying behavior)
- Variation range (mod_range) for stochastic behavior
- Bounds checking (min/max safety limits)
- Distribution mode (uniform, gaussian, etc.)
- Evaluation at specific time points

**Grain**: Immutable event representing a single granular playback:
- onset: when to play
- duration: grain length
- pointer_pos: position in source sample
- pitch_ratio: playback speed multiplier
- volume, pan: amplitude/stereo
- sample_table, envelope_table: references to function tables

**Envelope**: Time-varying parameter defined by interpolation points. Supports:
- Linear, cubic, exponential curves
- Nested envelopes (envelope of envelopes)
- Cycle mode for repetition

**Cartridge**: Tape recorder playback (non-granular, continuous sample playback)

### Controllers (Strategy Pattern)

Located in `src/controllers/`, each controller is responsible for one aspect:

- **PointerController**: Manages tape head position with loop boundaries and jitter
- **PitchController**: Transposes grains (semitones → ratio conversion)
- **DensityController**: Calculates grain onsets using temporal distribution
- **WindowController**: Selects grain envelopes (hanning, gaussian, expodec, etc.)

### Parameter System (Factory Pattern)

Located in `src/parameters/`:

- **ParameterOrchestrator**: Creates Parameter objects from YAML using ParameterFactory
- **ParameterFactory**: Builds Parameter instances with bounds and validation
- **ParameterSchema**: Defines which YAML keys map to Parameter objects
- **Parameter**: Smart parameter with Envelope support, variation, and bounds

### Variation Strategies

Located in `src/strategies/`:

- **VariationStrategy**: Abstract strategy for parameter randomization
- Implementations: additive, quantized, invert, choice
- **VariationRegistry**: Factory that maps strategy names to implementations

### Rendering Pipeline

**Csound Renderer** (`src/rendering/csound_renderer.py`):
- Delegates to ScoreWriter to generate `.sco` text
- FtableManager assigns function table numbers for samples and windows

**NumPy Renderer** (`src/rendering/numpy_audio_renderer.py`):
- Uses SampleRegistry and NumpyWindowRegistry for audio/window lookup
- GrainRenderer performs overlap-add synthesis
- Produces `.aif` directly via `scipy.io.wavfile` and `soundfile`

### YAML Configuration Structure

Example minimal stream:
```yaml
streams:
  - stream_id: "stream1"
    onset: 0.0
    duration: 30
    sample: "sample.wav"
    grain:
      duration: 0.05
```

**Parameter Syntax:**
- Static value: `density: 10`
- Envelope: `density: [[0, 10], [1, 50]]` (linear interpolation)
- Nested envelope: `density: [[[0, 5], [10, 50]], 1.0, 5]` (envelope of envelopes)
- Variation: `grain: {duration: 0.05, duration_range: 0.01}` (±0.01 randomization)

**Special Flags:**
- `solo`: Only render streams with this flag (if any stream has it)
- `mute`: Skip this stream (unless solo mode is active)
- `time_mode: normalized`: Use 0.0-1.0 time range instead of seconds

### Testing Structure (176 tests)

Test coverage is extensive (tests/ mirrors src/ structure):
- `tests/core/`: Stream, Grain, Cartridge, StreamConfig
- `tests/parameters/`: Parameter, ParameterFactory, parsing
- `tests/controllers/`: All controller classes
- `tests/envelopes/`: Envelope, interpolation, segment building
- `tests/strategies/`: Variation strategies, voice panning
- `tests/rendering/`: FtableManager, ScoreWriter, visualizer
- `tests/shared/`: Utility functions, probability gates, distribution strategies

Use `make tests` for full suite, `make TEST_FILE=tests/specific/ tests` for targeted testing.

### File Organization

```
src/
  ├── core/           # Grain, Stream, Cartridge, StreamConfig
  ├── engine/         # Generator (main orchestrator)
  ├── rendering/      # Renderers, ScoreWriter, FtableManager, visualizer
  ├── controllers/    # PointerController, PitchController, etc.
  ├── parameters/     # Parameter, ParameterFactory, parsing
  ├── envelopes/      # Envelope, interpolation, time distribution
  ├── strategies/     # Variation strategies, voice panning
  └── shared/         # Utils, logger, probability gates
```

### Important Implementation Notes

**Immutability:** Grain is a frozen dataclass for memory efficiency. Never mutate grains after creation.

**Math Expressions in YAML:** Generator preprocesses YAML and evaluates expressions like `(pi)`, `(10/2)` using safe_eval.

**Stream Cache:** When `STEMS=true CACHE=true`, StreamCacheManager fingerprints stream YAML data to skip unchanged streams. Only dirty streams are re-rendered.

**Window Registry:** WindowController pre-registers all possible window functions at Stream creation time. FtableManager assigns table numbers. This ensures consistent table numbering across renders.

**Rendering Entry Point:** `src/main.py` is the CLI entry point. It parses `--renderer csound|numpy` flag and delegates to RendererFactory.

**Voice System:** Streams can have multiple voices with pitch/pointer offsets. Each voice generates its own grain list, then lists are interleaved.

**Time Modes:** Streams support `time_mode: normalized` to work in 0.0-1.0 time space, mapped to actual duration at grain generation time.

## Common Workflows

### Adding a New Parameter to Stream

1. Add parameter definition to `src/parameters/parameter_definitions.py` (bounds)
2. Add schema entry to `src/parameters/parameter_schema.py` (STREAM_PARAMETER_SCHEMA)
3. Access parameter in Stream or controller via `self.parameter_name.evaluate(time)`

### Adding a New Variation Strategy

1. Create class in `src/strategies/` implementing VariationStrategy
2. Register in `src/strategies/variation_registry.py` (VariationFactory.REGISTRY)
3. Use in YAML: `variation_mode: 'new_strategy'`

### Adding a New Window Function

1. Add function to `src/controllers/window_registry.py`
2. Register in WindowRegistry.WINDOW_FUNCTIONS dict
3. Use in YAML: `grain: {envelope: 'new_window'}`

### Running Single Test

```bash
source .venv/bin/activate
pytest tests/path/to/test_file.py::test_function_name -v
```

## Platform Notes

- macOS: Fully supported (Apple Silicon and Intel)
- Linux: Fully supported (iZotope RX integration disabled automatically)
- Python: Requires 3.12 or higher
- Dependencies: csound (for Csound renderer), sox (for audio trimming), NumPy/SciPy (for NumPy renderer)
