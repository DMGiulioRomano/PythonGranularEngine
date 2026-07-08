---
slug: add-renderer
type: how-to
status: stable
tags: [renderer, ocp, extension]
sources:
  - src/pge/rendering/renderer_factory.py
  - src/pge/rendering/audio_renderer.py
last_synced_commit: 8c896d8
entry_for: [add-renderer]
---

# Add a New Renderer

## Quando usarlo

Devi sostituire o affiancare i renderer Csound / NumPy con un backend audio nuovo (PyTorch, JUCE bridge, offline analysis-resynthesis). Stop: se vuoi solo cambiare parametri di rendering, modifica il renderer esistente.

## Prerequisiti

- Lettura [[architecture]] § OCP design dei renderer
- Conoscenza ABC `AudioRenderer` (metodi `render_single_stream` e `render_merged_streams`)
- Decisione: il renderer supporta stems? Cache? Multi-voce?

## Passi

1. Crea il modulo in `src/pge/rendering/<nome>_renderer.py` ed eredita `AudioRenderer`
2. Implementa `render_single_stream(stream, output_path)` e `render_merged_streams(streams, output_path)`
3. Registra in `src/pge/rendering/renderer_factory.py` aggiungendo entry a `REGISTRY`
4. Niente da modificare in `main.py` (OCP)
5. Aggiungi test unit + e2e per il nuovo renderer

## File toccati

| Path | Tipo |
|------|------|
| `src/pge/rendering/<nome>_renderer.py` | nuovo file |
| `src/pge/rendering/renderer_factory.py` | aggiunta a REGISTRY |
| `tests/rendering/test_<nome>_renderer.py` | nuovi test |

## Test da aggiornare

- Test unit per ogni metodo della ABC
- E2E `tests/e2e/` con YAML minimo + nuovo renderer
- Test fallback / errori (sample mancante, output path non scrivibile)

## Verifica

```bash
make tests
make e2e-tests
RENDERER=<nome> make YAML=PGE_test SEZIONE=sezione1
```
