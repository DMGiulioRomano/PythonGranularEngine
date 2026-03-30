# Architettura Renderer — Stato dell'Arte

> Questo documento descrive l'architettura **implementata** del sistema di rendering.
> Le variazioni rispetto al design iniziale sono documentate nella sezione
> [Delta rispetto alla proposta originale](#delta).

---

## Architettura Implementata

### Principi applicati

- **Open/Closed Principle**: aggiungere un nuovo renderer (es. SuperCollider) richiede
  solo una nuova classe — nessuna modifica a `main.py`, `RenderingEngine` o `RenderMode`.
- **Single Responsibility**: ogni classe ha una sola ragione per cambiare.
- **Strategy Pattern**: `RenderMode` decide la modalità (stems/mix), non il renderer.
- **Facade**: `RenderingEngine` nasconde la coordinazione interna.

---

### Componenti

```
main.py
  └── _build_renderer()        ← crea il renderer giusto (lazy import)
  └── RenderingEngine.render() ← unica chiamata, mode-agnostica

RenderingEngine (Facade)
  ├── AudioRenderer (ABC)      ← interfaccia atomica
  │     ├── CsoundRenderer     ← adapter su ScoreWriter + subprocess csound
  │     └── NumpyAudioRenderer ← rendering NumPy puro (overlap-add)
  ├── NamingStrategy           ← genera path output
  └── RenderMode (Strategy)
        ├── StemsRenderMode    ← un file per stream
        └── MixRenderMode      ← un file unico

StreamCacheManager             ← caching incrementale (solo STEMS + RENDERER=csound)
  ├── compute_fingerprint()    ← SHA-256 del dict YAML raw
  ├── is_dirty()               ← fingerprint + presenza .aif
  ├── update_after_build()     ← aggiorna manifest post-build
  └── garbage_collect()        ← rimuove stream orfani (rimossi/rinominati nel YAML)
```

---

### AudioRenderer ABC — Interfaccia Atomica

```python
class AudioRenderer(ABC):

    @abstractmethod
    def render_single_stream(self, stream, output_path: str) -> str:
        """
        Renderizza UN stream in UN file (onset relativi).
        Usato da StemsRenderMode.
        """
        ...

    @abstractmethod
    def render_merged_streams(self, streams: List, output_path: str) -> str:
        """
        Renderizza PIÙ stream in UN file (onset assoluti).
        Usato da MixRenderMode.
        """
        ...
```

Il renderer **non decide** la modalità (stems/mix): questa responsabilità
è delegata a `RenderMode`.

---

### RenderMode — Strategy

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

---

### main.py — Agnostico

```python
renderer = _build_renderer(renderer_type, generator, **kwargs)

engine = RenderingEngine(renderer)
mode = StemsRenderMode() if per_stream else MixRenderMode()
generated = engine.render(streams=generator.streams, output_path=output_file, mode=mode)
```

`main.py` non contiene `if renderer_type == 'csound': ...` nella logica di rendering.
L'unica discriminazione avviene in `_build_renderer()` (factory).

---

### StreamCacheManager — Caching Incrementale

Attivo solo con `STEMS=true CACHE=true RENDERER=csound`.

**Flusso:**

```
1. GC: garbage_collect(current_stream_ids, aif_dir, aif_prefix)
       → rimuove dal manifest gli stream non più nel YAML
       → cancella i file .aif orfani da output/

2. Per ogni stream (in render_single_stream):
       is_dirty(stream_dict, aif_path)
       → True se: stream_id assente nel manifest
                  fingerprint cambiato
                  file .aif assente su disco
       → False → skip (ritorna output_path senza invocare csound)

3. update_after_build(stream_dicts)
       → aggiorna manifest con fingerprint correnti
```

**Manifest:** `cache/{yaml_basename}.json` — dict `{stream_id: sha256_fingerprint}`

---

### Aggiungere un Nuovo Renderer

```python
# 1. Implementa l'interfaccia
class SuperColliderRenderer(AudioRenderer):
    def render_single_stream(self, stream, output_path):
        ...
    def render_merged_streams(self, streams, output_path):
        ...

# 2. Registra in RendererFactory
# src/rendering/renderer_factory.py → REGISTRY dict

# main.py: ZERO MODIFICHE
```

---

## Delta rispetto alla Proposta Originale

| Aspetto | Proposta | Implementato |
|---------|----------|--------------|
| Interfaccia ABC | `render(streams, path, per_stream)` — metodo unico | `render_single_stream` + `render_merged_streams` — interfaccia atomica |
| Decisione stems/mix | Dentro ogni renderer (`if per_stream`) | Delegata a `RenderMode` (Strategy separato) |
| Naming file | Dentro ogni renderer | Delegata a `NamingStrategy` |
| Facade | Assente | `RenderingEngine` coordina renderer + naming + mode |
| Cache | Non prevista | `StreamCacheManager` con fingerprint SHA-256 e GC |
| GC orfani | Non previsto | `garbage_collect()` rimuove stream rimossi dal YAML |

L'interfaccia atomica (`render_single_stream` / `render_merged_streams`) è più
OCP-pura della proposta: aggiungere una nuova modalità (es. per-voice) richiede
solo un nuovo `RenderMode`, non modifiche ai renderer.

---

## Copertura Test

| Layer | Strumento | Conteggio |
|-------|-----------|-----------|
| Unit (mock) | `pytest` / `make tests` | 3444 test |
| E2E | `pytest -m e2e` / `make e2e-tests` | 21 test |

### E2E Csound — `tests/e2e/test_cache_e2e.py` (15 test)

Testa la pipeline completa `make → Python → Csound → filesystem` in modalità `STEMS=true CACHE=true`.

| Classe | Scenario |
|--------|----------|
| `TestFirstBuild` (4) | Prima build: .aif creati, manifest popolato, entrambi DIRTY, fingerprint SHA-256 |
| `TestIncrementalBuild` (3) | Build invariata: tutti clean, nessun DIRTY, manifest immutato |
| `TestPartialRebuild` (3) | Modifica parziale YAML: solo stream modificato DIRTY, fingerprint aggiornato |
| `TestGarbageCollection` (5) | Stream rimosso: .aif orfano cancellato, entry manifest rimossa, GC in stdout |

### E2E NumPy — `tests/e2e/test_numpy_renderer_e2e.py` (6 test)

Testa la pipeline `make → Python → NumPy → filesystem`. Non richiede Csound.

| Classe | Scenario |
|--------|----------|
| `TestNumpyStems` (4) | `STEMS=true`: un .aif per stream, naming corretto, nessun manifest creato |
| `TestNumpyMix` (2) | `STEMS=false`: un .aif unico con tutti gli stream mixati |

**Note sui renderer:**
- **Csound STEMS**: ogni stem parte dall'onset relativo allo stream (onset=0 nel file)
- **NumPy STEMS**: idem — onset relativi, nessun silenzio iniziale
- **Csound/NumPy MIX**: onset assoluti, tutti gli stream posizionati correttamente nel tempo
- **Cache**: `StreamCacheManager` è attivo solo con `RENDERER=csound STEMS=true CACHE=true`
