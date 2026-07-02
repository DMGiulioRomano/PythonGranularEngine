---
slug: architecture
type: explanation
status: stable
tags: [architecture, rendering, ocp]
sources:
  - src/rendering/
  - src/main.py
last_synced_commit: 9de1079
---

# Architettura Renderer

**Documenti collegati:** [[INDEX]] · [[caching]] (StreamCacheManager dedicato) · [[yaml]] · [[multi-voice]] · [[errors]] · [[reaper]] · [[add-renderer]]

---

## Problema

Il sistema deve renderizzare YAML in audio usando back-end multipli (Csound, NumPy, in futuro SuperCollider/altri). Senza disciplina, aggiungere un renderer significa modificare `main.py` con `if renderer_type == 'csound': ...` ovunque — accumulazione di switch case nel core. Inoltre, la decisione "un file per stream" (stems) vs "un file unico" (mix) deve essere ortogonale alla scelta del renderer.

## Modello

Quattro componenti coordinati. **Open/Closed Principle**: nuovi renderer e nuovi modi di output sono additivi, niente modifiche al core.

```
main.py
  └── _build_renderer()        ← factory: crea il renderer giusto (lazy import)
  └── RenderingEngine.render() ← unica chiamata, mode-agnostica

RenderingEngine (Facade)
  ├── AudioRenderer (ABC)      ← interfaccia atomica
  │     ├── CsoundRenderer     ← adapter su ScoreWriter + subprocess csound
  │     └── NumpyAudioRenderer ← rendering NumPy puro (overlap-add)
  ├── NamingStrategy           ← genera path output
  └── RenderMode (Strategy)
        ├── StemsRenderMode    ← un file per stream
        └── MixRenderMode      ← un file unico
```

**AudioRenderer ABC** — interfaccia atomica:

```python
class AudioRenderer(ABC):
    @abstractmethod
    def render_single_stream(self, stream, output_path: str) -> str:
        """Renderizza UN stream in UN file (onset relativi). Usato da StemsRenderMode."""

    @abstractmethod
    def render_merged_streams(self, streams: List, output_path: str) -> str:
        """Renderizza PIÙ stream in UN file (onset assoluti). Usato da MixRenderMode."""
```

Il renderer **non decide** stems/mix: lo fa `RenderMode`.

**RenderMode** — Strategy:

```python
class StemsRenderMode(RenderMode):
    def execute(self, renderer, naming, streams, output_path):
        paths_map = naming.generate_paths(output_path, streams, mode='stems')
        for stream, path in paths_map:
            renderer.render_single_stream(stream, path)

class MixRenderMode(RenderMode):
    def execute(self, renderer, naming, streams, output_path):
        paths_map = naming.generate_paths(output_path, streams, mode='mix')
        all_streams, mix_path = paths_map[0]
        renderer.render_merged_streams(all_streams, mix_path)
```

**main.py** è agnostico — un solo punto di factory:

```python
renderer = _build_renderer(renderer_type, generator, **kwargs)
engine = RenderingEngine(renderer)
mode = StemsRenderMode() if per_stream else MixRenderMode()
generated = engine.render(streams=generator.streams, output_path=output_file, mode=mode)
```

Caching incrementale è componente separato, vedi [[caching]].

### Rendering NumPy multi-processo (`--jobs`)

L'overlap-add del renderer NumPy è parallelizzabile perché il rendering del
singolo grano è puro (nessun `random`, nessuno stato condiviso:
`GrainRenderer`). La **generazione** dei grani invece consuma il `random`
globale seminato una volta in `Generator.create_elements()` e resta nel
processo parent: l'ordine di consumo è la riproducibilità delle composizioni.

Il parallelismo vive interamente dentro `NumpyAudioRenderer`
(`RenderMode`/`RenderingEngine`/ABC invariati): le coppie
`(grain, onset_sample)` vengono ordinate per onset, divise in chunk contigui
(`src/rendering/numpy_parallel.py`) e affidate a un pool `spawn` di
`jobs` worker; ogni worker rende il proprio chunk in un buffer locale
all'extent del chunk e il parent somma i risultati in ordine di chunk fisso,
poi applica `dc_block`, clamp e scrittura come nel path sequenziale.

Proprietà:

- `jobs=1` (default dell'API; il default `auto` = core-1 è policy del solo
  entry point CLI/Make) → path sequenziale **bit-identico allo storico**.
- Sotto `PARALLEL_MIN_GRAINS` grani il render resta sequenziale anche con
  `jobs > 1`: niente pool per render piccoli e per i test.
- A parità di `jobs` l'output è byte-identico tra run; tra valori diversi di
  `jobs` cambia solo l'ordine delle somme float64 (< 1 LSB a 24 bit).
- Il pool è lazy, riusato per tutti gli stream della run (STEMS) e spento
  con `close()`; i worker ricostruiscono i registry da disco (`init_worker`).
- Il check cache (`is_dirty` prima di toccare `.voices`) e la generazione
  lazy dei grani (issue #117) sono invariati.

## Trade-off

| Aspetto | Alternativa | Perché questa |
|---------|-------------|---------------|
| Interfaccia ABC con 2 metodi atomici | Unico `render(streams, path, per_stream)` | Atomica → nuova `RenderMode` (es. per-voice) non richiede modifiche ai renderer |
| RenderMode esterno al renderer | Flag `per_stream` nel renderer | Switch ortogonale: ogni renderer × ogni modo combinabile gratis |
| NamingStrategy esterno al renderer | Naming dentro al renderer | Riuso tra renderer; test isolati |
| Facade `RenderingEngine` | main.py orchestrazione diretta | Single entry point, test integrabili facilmente |

## Implicazioni codice

- Aggiungere un renderer: vedi [[add-renderer]] (3 step, zero modifiche a main.py)
- Aggiungere una mode (es. per-voice): nuova `RenderMode` subclass + uso in main; ABC invariata
- Caching: vedi [[caching]]
- Errori specifici renderer: `CsoundRenderError`, `InvalidRendererError` (vedi [[errors]])

### Copertura test

| Layer | Strumento | Conteggio |
|-------|-----------|-----------|
| Unit (mock) | `pytest` / `make tests` | 4149 test |
| E2E | `pytest -m e2e` / `make e2e-tests` | 21 test |

**E2E Csound** (`tests/e2e/test_cache_e2e.py`, 15 test): pipeline `make → Python → Csound → filesystem` in `STEMS=true CACHE=true`. Copre first build, incremental, partial rebuild, garbage collection.

**E2E NumPy** (`tests/e2e/test_numpy_renderer_e2e.py`, 6 test): pipeline `make → Python → NumPy → filesystem`, no Csound. Copre stems e mix.

**Note semantica onset:**
- Csound/NumPy STEMS: onset relativi allo stream (onset=0 nel file)
- Csound/NumPy MIX: onset assoluti, stream posizionati nel tempo

### Platform notes

- macOS: fully supported (Apple Silicon e Intel)
- Linux: fully supported (iZotope RX integration disabled automatically)
- Python: 3.12+
- Dipendenze: csound (Csound renderer), sox (audio trimming), NumPy/SciPy (NumPy renderer)

## Vedi anche

- [[caching]] — caching incrementale per stems Csound
- [[add-renderer]] — workflow estensione
- [[yaml]] — input accettato dalla pipeline
- [[errors]] — errori renderer
