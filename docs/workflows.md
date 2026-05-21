# Common Workflows — PythonGranularEngine

Reference for the most common extension points. Read this before adding any new component.

**Documenti collegati:** [[INDEX]] · [[ARCHITECTURE]] (OCP design dei renderer) ·
[[yaml-reference]] (sintassi parametri) · [[envelopes-reference]] (parametri come envelope) ·
[[multi-voice]] (voice strategy) · [[error-handling]] (errori da sollevare nei nuovi
moduli).

---

## Adding a New Parameter to Stream

1. Add parameter definition (bounds) to `src/parameters/parameter_definitions.py`
2. Add schema entry to `src/parameters/parameter_schema.py` (`STREAM_PARAMETER_SCHEMA`)
3. Access in Stream or controller via `self.parameter_name.evaluate(time)`

---

## Adding a New Variation Strategy

1. Create class in `src/strategies/` implementing `VariationStrategy`
2. Register in `src/strategies/variation_registry.py` (`VariationFactory.REGISTRY`)
3. Use in YAML: `variation_mode: 'new_strategy'`

---

## Adding a New Window Function

1. Add function to `src/controllers/window_registry.py`
2. Register in `WindowRegistry.WINDOW_FUNCTIONS` dict
3. Use in YAML: `grain: {envelope: 'new_window'}`

---

## Adding a New Renderer

1. Implement `AudioRenderer` ABC (`render_single_stream` + `render_merged_streams`)
2. Register in `src/rendering/renderer_factory.py` (`REGISTRY` dict)
3. `main.py` requires zero modifications

See [[ARCHITECTURE]] for the full OCP architecture.

---

## Adding a New Voice Strategy

Estendere il sistema multi-voice (pitch / onset / pointer / pan).

1. Sottoclasse l'ABC giusta in `src/strategies/` (`VoicePitchStrategy`,
   `VoiceOnsetStrategy`, `VoicePointerStrategy`, `VoicePanStrategy`).
2. Implementa `get_<axis>_offset(voice_index, num_voices, time)`.
   - Invariante: `voice_index == 0` deve sempre ritornare `0.0`.
   - Onset: offset `>= 0` (le voci secondarie non precedono la voce 0).
3. Registra nella factory corrispondente (`Voice<Axis>StrategyFactory.REGISTRY`).
4. Parser YAML: estendi `_build_<axis>_strategy` in `src/core/stream.py` se i
   parametri richiedono parsing custom (es. envelope auto-detect via
   `_parse_strategy_kwarg`).
5. Test: `tests/strategies/test_voice_<axis>_strategy.py` con voice-0
   invariant + envelope param + (per le stochastiche) determinismo dal
   `stream_id`.

Vedi [[multi-voice]] per le invarianti complete.

---

## Adding a New Error Class

1. Eredita dal nodo giusto in `src/shared/exceptions.py`:
   - errore config YAML → `ConfigError`
   - errore runtime engine → `EngineRuntimeError`
2. Override `user_message()` (formato `[ERRORE] head` + righe indentate +
   `self._context_lines()`).
3. Solleva con dato locale minimo; arricchisci `stream_id` / `config_file`
   nei chiamanti (parser / controller / Generator).
4. Test: unit (`tests/shared/test_engine_exceptions.py`) + integration +
   e2e (`tests/e2e/test_engine_errors_e2e.py`).

Dettagli e pattern context-enrichment in [[error-handling]].

---

## Making a Parameter Envelope-Aware

Quando un parametro nuovo deve accettare anche envelope, non solo scalare:

1. Schema (`STREAM_PARAMETER_SCHEMA`) → flag `accepts_envelope: True`.
2. Sito di consumo → invece di leggere `params['x']`, usa
   `resolve_param(self.x, time)` (o `self.x.evaluate(time)` se sempre Envelope).
3. Per voice strategy: il parsing in `Stream._parse_strategy_kwarg` riconosce
   liste `[[t, v], ...]` e dict `{points, time_mode}` e li trasforma in
   `Envelope` automaticamente.

Sintassi accettate dal parser → [[envelopes-reference]] § 2.

---

## Running a Single Test

```bash
source .venv/bin/activate
pytest tests/path/to/test_file.py::test_function_name -v
```

Suite via `Makefile`:

```bash
make tests              # unit + integration (richiesto pre-commit)
make e2e-tests          # E2E (richiesto pre-tag release)
make TEST_FILE=tests/strategies/test_voice_pitch_strategy.py tests
```

Pre-commit gate documentato in `CLAUDE.md` § "Test Gate".
