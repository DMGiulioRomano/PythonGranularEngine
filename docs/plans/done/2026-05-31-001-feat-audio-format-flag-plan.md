---
slug: 2026-05-31-001-feat-audio-format-flag
type: plan
status: draft
issue: 75
tags: [cli, rendering, numpy, csound, audio-format]
sources:
  - src/main.py
  - src/rendering/naming_strategy.py
  - src/rendering/numpy_audio_renderer.py
  - src/rendering/stream_cache_manager.py
  - src/rendering/rendering_engine.py
  - src/rendering/renderer_factory.py
last_synced_commit: d6f0034
---

# Plan: feat — `--format` flag per formato audio output (issue #75)

## Contesto

Output è hardcoded AIFF in tre strati indipendenti:

1. **NamingStrategy** — estensione `.aif` cablata in `DefaultNamingStrategy.generate_paths()` (`naming_strategy.py:93`)
2. **NumpyAudioRenderer** — `format='AIFF'` hardcoded in entrambe le chiamate `sf.write()` (`numpy_audio_renderer.py:119, 166`)
3. **StreamCacheManager** — nomi file `.aif` cablati in `get_dirty_stream_dicts()` e `garbage_collect()` (`stream_cache_manager.py:129, 172`)

Csound non necessita modifiche: rileva il formato dall'estensione del file passato via `-o`.

Motivazione primaria: `PGE-ui` riproduce stem via Web Audio API — Firefox non decodifica AIFF, serve WAV.

---

## Design: `AudioFormat` dataclass

Nuovo file `src/rendering/audio_format.py`:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class AudioFormat:
    label: str        # 'aiff' | 'wav' | 'flac'
    extension: str    # '.aif' | '.wav' | '.flac'
    sf_format: str    # 'AIFF' | 'WAV' | 'FLAC'
    sf_subtype: str   # 'FLOAT' | 'FLOAT' | 'PCM_24'

FORMATS = {
    'aiff': AudioFormat('aiff', '.aif',  'AIFF', 'FLOAT'),
    'aif':  AudioFormat('aiff', '.aif',  'AIFF', 'FLOAT'),
    'wav':  AudioFormat('wav',  '.wav',  'WAV',  'FLOAT'),
    'flac': AudioFormat('flac', '.flac', 'FLAC', 'PCM_24'),
}
DEFAULT_FORMAT = FORMATS['aiff']
```

`sf_subtype` serve perché soundfile richiede subtype esplicito per FLAC.

---

## File da modificare

### 1. `src/rendering/audio_format.py` (NUOVO)
Dataclass + `FORMATS` dict + `DEFAULT_FORMAT`.

### 2. `src/rendering/naming_strategy.py`
- `DefaultNamingStrategy.__init__(self, ext: str = '.aif')`
- line 93: `f"{base}__{stream.stream_id}{self.ext}"`

### 3. `src/rendering/numpy_audio_renderer.py`
- `__init__()` aggiunge `audio_format: AudioFormat = DEFAULT_FORMAT`
- lines 119, 166:
  ```python
  sf.write(output_path, buffer, self.output_sr,
           format=self.audio_format.sf_format,
           subtype=self.audio_format.sf_subtype)
  ```

### 4. `src/rendering/stream_cache_manager.py`
- `get_dirty_stream_dicts(..., ext: str = '.aif')` — usa `ext` nelle f-string (line 129)
- `garbage_collect(..., ext: str = '.aif')` — usa `ext` nelle f-string (line 172)

### 5. `src/rendering/renderer_factory.py`
Passa `audio_format` a `NumpyAudioRenderer` in `create('numpy', ...)`.

### 6. `src/main.py`
**Parsing** (dopo line ~213):
```python
from rendering.audio_format import FORMATS, DEFAULT_FORMAT
audio_format = DEFAULT_FORMAT
if '--format' in sys.argv:
    idx = sys.argv.index('--format')
    if idx + 1 < len(sys.argv):
        fmt_label = sys.argv[idx + 1].lower()
        if fmt_label not in FORMATS:
            print(f"Formato non supportato: {fmt_label}. Usa: aiff, wav, flac")
            sys.exit(1)
        audio_format = FORMATS[fmt_label]
```

**Default output** (line ~138): se `output_file` è `'output.aif'` e formato non è AIFF:
```python
if output_file == 'output.aif' and audio_format.extension != '.aif':
    output_file = f'output{audio_format.extension}'
```

**RenderingEngine** (line ~267): passa naming strategy con estensione corretta:
```python
from rendering.naming_strategy import DefaultNamingStrategy
engine = RenderingEngine(renderer, naming_strategy=DefaultNamingStrategy(ext=audio_format.extension))
```

**_build_renderer**: aggiunge `audio_format=audio_format` in kwargs, propagato a `RendererFactory.create('numpy', ...)`.

**garbage_collect call** (~line 259): aggiunge `ext=audio_format.extension`.

**Usage string** (line ~122): aggiunge `[--format aiff|wav|flac]`.

---

## Cosa NON cambia

- CsoundRenderer: zero modifiche (formato da estensione `-o` flag)
- MIX mode: `naming_strategy.py` line 99 ritorna `base_path` invariato — estensione già nell'`output_file`
- Convenzione `<basename>__<streamId>`: invariata, cambia solo estensione

---

## Test da aggiungere (TDD: rossi prima, poi implementazione)

### `tests/rendering/test_naming_strategy.py` (o test esistente)
- `DefaultNamingStrategy(ext='.wav')` STEMS → `base__id.wav`
- `DefaultNamingStrategy(ext='.flac')` STEMS → `base__id.flac`
- `DefaultNamingStrategy()` default → `.aif` invariato

### `tests/rendering/test_numpy_audio_renderer.py`
- `FORMATS['wav']` → `sf.write` chiamata con `format='WAV'`
- `FORMATS['flac']` → `sf.write` chiamata con `format='FLAC', subtype='PCM_24'`

### `tests/test_main.py`
- `--format wav` → default output diventa `output.wav`
- `--format wav` → `RenderingEngine` riceve `DefaultNamingStrategy(ext='.wav')`
- `--format invalid` → exit(1)
- senza `--format` → comportamento invariato

### `tests/rendering/test_stream_cache_manager.py`
- `get_dirty_stream_dicts(..., ext='.wav')` → filename con `.wav`
- `garbage_collect(..., ext='.wav')` → elimina file `.wav` orfani

---

## Ordine implementazione (TDD)

1. `audio_format.py` (nuovo, nessun side-effect)
2. Test rossi → fix `naming_strategy.py`
3. Test rossi → fix `numpy_audio_renderer.py`
4. Test rossi → fix `stream_cache_manager.py`
5. Fix `renderer_factory.py` (propagazione)
6. Test rossi CLI → fix `main.py`
7. `make tests` + `make e2e-tests`

---

## Verifica end-to-end

```bash
python src/main.py tests/fixtures/PGE_test.yml output/test.wav --renderer numpy --format wav
python src/main.py tests/fixtures/PGE_test.yml output/test.wav --renderer numpy --format wav --per-stream
python src/main.py tests/fixtures/PGE_test.yml output/test.wav --format wav
python src/main.py tests/fixtures/PGE_test.yml --renderer numpy   # AIFF default invariato

file output/test.wav   # deve riportare RIFF/WAV
make tests
make e2e-tests
```
