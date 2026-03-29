# Design Proposal: OCP-Compliant Renderer Architecture

## Problema Attuale

main.py contiene logica specifica per ogni renderer, violando Open/Closed Principle.

## Soluzione Proposta

### 1. AudioRenderer ABC - Interfaccia Unificata

```python
from abc import ABC, abstractmethod
from typing import List

class AudioRenderer(ABC):
    """
    Strategy per rendering audio.

    Open/Closed Principle: main.py chiama solo render(),
    ogni renderer decide internamente come gestire per_stream flag.
    """

    @abstractmethod
    def render(
        self,
        streams: List,
        output_path: str,
        per_stream: bool
    ) -> List[str]:
        """
        Renderizza stream(s) in file audio.

        Args:
            streams: lista di Stream objects con grani già generati
            output_path: percorso base per output (es. 'output/composition.aif')
            per_stream:
                - True: genera un file separato per ogni stream (STEMS)
                  → output_composition_stream1.aif, output_composition_stream2.aif, ...
                - False: genera un unico file con tutti gli stream mixati (MIX)
                  → output_composition.aif

        Returns:
            Lista di path file audio generati

        Esempi:
            # STEMS mode
            renderer.render(streams, 'out.aif', per_stream=True)
            → ['out_s1.aif', 'out_s2.aif', 'out_s3.aif']

            # MIX mode
            renderer.render(streams, 'out.aif', per_stream=False)
            → ['out.aif']
        """
        pass
```

---

### 2. NumpyAudioRenderer - Implementazione

```python
class NumpyAudioRenderer(AudioRenderer):
    def render(self, streams, output_path: str, per_stream: bool) -> List[str]:
        """
        NumPy rendering: decide internamente come gestire per_stream.
        """
        if per_stream:
            # STEMS: un file per stream
            return self._render_stems(streams, output_path)
        else:
            # MIX: un file unico con onset assoluti
            return self._render_mix(streams, output_path)

    def _render_stems(self, streams, output_path):
        """
        STEMS: crea N file separati.
        Ogni stream parte da onset=0 nel proprio file.
        """
        generated = []
        base = os.path.splitext(output_path)[0]

        for stream in streams:
            path = f"{base}_{stream.stream_id}.aif"
            self._render_single_stream(stream, path)
            generated.append(path)

        return generated

    def _render_mix(self, streams, output_path):
        """
        MIX: crea 1 file con tutti gli stream.
        Rispetta onset assoluti (stream.onset per posizionamento).
        """
        # Calcola durata totale
        max_end_time = max(s.onset + s.duration for s in streams)
        n_total = int(max_end_time * self.output_sr)
        buffer = np.zeros((n_total, 2), dtype=np.float64)

        # Overlap-add con onset assoluti
        for stream in streams:
            for voice_grains in stream.voices:
                for grain in voice_grains:
                    self._add_grain_absolute(buffer, grain, n_total)

        # Scrivi file
        np.clip(buffer, -1.0, 1.0, out=buffer)
        sf.write(output_path, buffer, self.output_sr, format='AIFF')

        return [output_path]

    def _render_single_stream(self, stream, output_path):
        """
        Renderizza UN stream (onset relativi, parte da 0).
        Usato da _render_stems().
        """
        # Codice esistente di render_stream()
        n_total = int(stream.duration * self.output_sr)
        buffer = np.zeros((n_total, 2), dtype=np.float64)

        for voice_grains in stream.voices:
            for grain in voice_grains:
                self._add_grain_relative(buffer, grain, stream.onset, n_total)

        np.clip(buffer, -1.0, 1.0, out=buffer)
        sf.write(output_path, buffer, self.output_sr, format='AIFF')
```

---

### 3. CsoundRenderer - Implementazione

```python
class CsoundRenderer(AudioRenderer):
    """
    CsoundRenderer incapsula TUTTA la logica Csound internamente.
    Non espone ScoreWriter all'esterno.
    """

    def __init__(self, score_writer, csound_config):
        self.score_writer = score_writer
        self.csound_config = csound_config

    def render(self, streams, output_path: str, per_stream: bool) -> List[str]:
        """
        Csound rendering: decide internamente come gestire per_stream.
        """
        if per_stream:
            # STEMS: N file .sco → N file .aif
            return self._render_stems(streams, output_path)
        else:
            # MIX: 1 file .sco → 1 file .aif
            return self._render_mix(streams, output_path)

    def _render_stems(self, streams, output_path):
        """
        STEMS: crea un file .sco per stream, renderizza ognuno.
        """
        generated = []
        base = os.path.splitext(output_path)[0]

        for stream in streams:
            # Scrivi .sco per questo stream
            sco_path = self._write_temp_score(streams=[stream])

            # Renderizza con csound
            aif_path = f"{base}_{stream.stream_id}.aif"
            self._run_csound(sco_path, aif_path)
            generated.append(aif_path)

        return generated

    def _render_mix(self, streams, output_path):
        """
        MIX: crea un unico .sco con tutti gli stream, renderizza.
        """
        # Scrivi .sco con tutti gli stream
        sco_path = self._write_temp_score(streams=streams)

        # Renderizza con csound
        self._run_csound(sco_path, output_path)

        return [output_path]

    # Metodi helper privati (_write_temp_score, _run_csound) rimangono invariati
```

---

### 4. main.py - AGNOSTICO

```python
def main():
    # ... parsing args ...

    generator = Generator(yaml_file)
    generator.load_yaml()
    generator.create_elements()

    # ════════════════════════════════════════════════════════
    # RENDERER AGNOSTICO - OCP COMPLIANT
    # ════════════════════════════════════════════════════════

    renderer = RendererFactory.create(
        renderer_type=renderer_type,  # 'numpy' o 'csound'
        # ... kwargs specifici per ogni renderer ...
    )

    # UNICA CHIAMATA - uguale per tutti i renderer
    generated_files = renderer.render(
        streams=generator.streams,
        output_path=output_file,
        per_stream=per_stream
    )

    print(f"\n✓ Generati {len(generated_files)} file:")
    for path in generated_files:
        print(f"  - {path}")

    # ════════════════════════════════════════════════════════
    # FINE - main.py non sa nulla di .sco, numpy, onset, etc.
    # ════════════════════════════════════════════════════════
```

---

## Vantaggi

### 1. Open/Closed Principle ✅
```python
# Aggiungere nuovo renderer SuperColliderRenderer:
class SuperColliderRenderer(AudioRenderer):
    def render(self, streams, output_path, per_stream):
        # logica SuperCollider interna
        pass

# main.py: ZERO MODIFICHE
renderer = RendererFactory.create('supercollider', ...)
generated = renderer.render(streams, path, per_stream)
```

### 2. Single Responsibility ✅
- **main.py**: orchestrazione CLI, non sa come funzionano i renderer
- **Renderer**: incapsula TUTTA la logica di rendering
- **Generator**: genera stream, non sa di rendering

### 3. Dependency Inversion ✅
- main.py dipende da `AudioRenderer` (astrazione)
- NON dipende da `NumpyAudioRenderer` o `CsoundRenderer` (implementazioni)

### 4. Testabilità ✅
```python
# Mock renderer per testing main.py
class MockRenderer(AudioRenderer):
    def render(self, streams, output_path, per_stream):
        return ['/fake/path.aif']

# Test main.py senza dipendenze reali
```

---

## Migrazione da Codice Attuale

### Cosa cambia:

1. **AudioRenderer ABC**:
   - ~~render_stream(stream, path)~~ → rimosso
   - ~~render_merged(streams, path)~~ → rimosso
   - ✅ `render(streams, path, per_stream)` → unico metodo pubblico

2. **Generator**:
   - ~~generate_score_file()~~ → diventa PRIVATO (usato solo da CsoundRenderer)
   - ~~generate_score_files_per_stream()~~ → diventa PRIVATO
   - ✅ Generator fornisce solo `.streams` pubblicamente

3. **main.py**:
   - ~~if renderer_type == 'numpy': ...~~ → rimosso
   - ~~if per_stream: ... else: ...~~ → rimosso
   - ✅ Una sola chiamata: `renderer.render(...)`

---

## Test Coverage

### Test per NumpyAudioRenderer.render():
1. `test_render_with_per_stream_true_creates_multiple_files`
2. `test_render_with_per_stream_false_creates_single_file`
3. `test_render_stems_uses_relative_onset`
4. `test_render_mix_uses_absolute_onset`
5. `test_render_returns_list_of_paths`

### Test per CsoundRenderer.render():
1. `test_render_with_per_stream_true_calls_csound_n_times`
2. `test_render_with_per_stream_false_calls_csound_once`
3. `test_render_stems_creates_separate_sco_files`
4. `test_render_mix_creates_single_sco_file`

### Test per main.py (integration):
1. `test_main_with_numpy_renderer_stems`
2. `test_main_with_numpy_renderer_mix`
3. `test_main_with_csound_renderer_stems`
4. `test_main_with_csound_renderer_mix`

---

## Domande Aperte

1. **Generator.generate_score_file() diventa privato?**
   - Pro: OCP puro, Generator non espone rendering
   - Contro: potrebbe servire per debugging/testing
   - Proposta: lasciarlo pubblico ma deprecato?

2. **RendererFactory come crea CsoundRenderer?**
   ```python
   # Opzione A: Factory crea ScoreWriter internamente
   renderer = RendererFactory.create('csound', generator=generator)

   # Opzione B: Factory riceve ScoreWriter da main.py
   score_writer = generator.score_writer
   renderer = RendererFactory.create('csound', score_writer=score_writer)
   ```

3. **Cartridges?**
   - Per ora ignorate, da aggiungere dopo?
   - O metodo `render()` accetta anche `cartridges: List`?

