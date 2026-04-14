# Common Workflows — PythonGranularEngine

Reference for the most common extension points. Read this before adding any new component.

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

See `docs/ARCHITECTURE.md` for the full OCP architecture.

---

## Running a Single Test

```bash
source .venv/bin/activate
pytest tests/path/to/test_file.py::test_function_name -v
```
