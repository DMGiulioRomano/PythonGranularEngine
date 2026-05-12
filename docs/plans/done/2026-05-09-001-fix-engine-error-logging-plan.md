---
title: "fix: logging strutturato per errori engine — sample mancanti con messaggio terminale pulito (issue #33)"
type: fix
status: done
date: 2026-05-09
issue: 33
---

# fix: logging strutturato per errori engine

## Overview

Issue #33: quando un sample referenziato dal YAML non esiste in `./refs/`, il pipeline crasha con un traceback Python grezzo da `soundfile.LibsndfileError`. Niente messaggio leggibile, niente file di log per errori engine, niente context (quale stream, quale config).

Questo piano introduce:
1. Gerarchia `EngineError` con sotto-tipi specifici (a partire da `SampleNotFoundError`)
2. `engine_logger` separato dal `clip_logger` esistente, scrive su `./logs/<yaml>_engine.log`
3. Top-level handler in `main.py` che formatta messaggio terminale pulito + persiste traceback nel log
4. Wrapping del context (stream_id, yaml_file) lato caller — `Stream.__init__` arricchisce l'errore con info che `get_sample_duration` non possiede

**Ambito iniziale:** solo `SampleNotFoundError`. Altri errori (YAML invalidi, render failures) restano traceback finché non emergeranno come issue separate.

---

## Vincolo architetturale

`get_sample_duration` (`src/shared/utils.py`) resta una utility pura: non conosce `stream_id` né `yaml_file`. Il context viene aggiunto dal caller (`Stream.__init__`) tramite wrapping dell'eccezione. Separazione concerns: utility = primitive su filesystem; stream = consapevole del proprio identity.

Il logger engine è separato dal `clip_logger` esistente perché:
- diverso scope (errori fatali vs warning di clipping envelope)
- diversa configurazione (sempre file, mai console; vs clip configurabile)
- diverso ciclo di vita (engine logger sempre attivo da inizio main; clip configurato dopo arg parsing)

---

## Problem Frame

### Comportamento attuale

```
$ make all FILE=PGE_test
...
 Errore: Error opening './refs/pino.wav': System error.
Traceback (most recent call last):
  File ".../main.py", line 214, in main
    generator.create_elements()
  File ".../generator.py", line 106, in create_elements
    self._create_streams(filtered_streams)
  File ".../generator.py", line 240, in _create_streams
    stream = Stream(stream_data)
  File ".../stream.py", line 76, in __init__
    config = StreamConfig.from_yaml(...)
  File ".../utils.py", line 9, in get_sample_duration
    info = sf.info(PATHSAMPLES + filepath)
  ...
soundfile.LibsndfileError: Error opening './refs/pino.wav': System error.
```

Problemi:
- traceback Python invece di messaggio leggibile
- messaggio "System error" da libsndfile non aiuta utente
- niente indicazione dello stream colpevole
- niente file di log persistente per debug futuro
- l'utente deve leggere stack trace per capire che manca un file

### Comportamento atteso

Terminale:
```
[ERRORE] Sample non trovato: 'pino.wav'
  Path cercato:  ./refs/pino.wav
  Stream:        <stream_id>
  Config:        configs/PGE_test.yml
  Dettagli:      ./logs/PGE_test_engine.log
```

File `./logs/PGE_test_engine.log`:
```
2026-05-09 14:23:01 [ERROR] SampleNotFoundError: 'pino.wav' (path: ./refs/pino.wav, stream: <id>, config: configs/PGE_test.yml)
Traceback (most recent call last):
  ...
```

---

## Design

### Nuovi moduli

**`src/shared/exceptions.py`** (nuovo file)
```python
class EngineError(Exception):
    """Base per errori dell'engine destinati a output user-facing pulito."""
    def user_message(self) -> str: ...

class SampleNotFoundError(EngineError):
    def __init__(self, filename: str, search_path: str,
                 stream_id: str | None = None,
                 config_file: str | None = None):
        ...
```

`user_message()` ritorna stringa formattata multi-line per terminale. `__str__` resta usabile per log.

### Estensioni a moduli esistenti

**`src/shared/logger.py`**
- aggiungere `configure_engine_logger(yaml_name, log_dir='./logs')`
- aggiungere `get_engine_logger() -> logging.Logger`
- file handler su `./logs/<yaml>_engine.log`, livello ERROR
- nessun console handler (terminal output gestito da main.py)

**`src/shared/utils.py:get_sample_duration`**
- check `os.path.exists(PATHSAMPLES + filepath)` prima di `sf.info()`
- se manca: raise `SampleNotFoundError(filename=filepath, search_path=PATHSAMPLES)`
- nessun riferimento a stream_id (utility pura)

**`src/core/stream.py:Stream.__init__`**
- wrap `StreamConfig.from_yaml(...)` in try/except `SampleNotFoundError`
- arricchisce con `stream_id` (presente in `params`) e re-raise

**`src/main.py`**
- chiamare `configure_engine_logger(yaml_basename)` prima del try
- nuovo branch nel except: `except EngineError as e:` → `print(e.user_message())` + `engine_logger.error(...)` con traceback
- `Generator` o `main` arricchisce con `config_file` (path YAML noto solo qui)

### Flusso del context

```
get_sample_duration  →  raise SampleNotFoundError(filename, search_path)
                              ↓ propaga
Stream.__init__      →  catch, aggiungi stream_id, re-raise
                              ↓ propaga
Generator.create_elements →  catch, aggiungi config_file, re-raise
                              ↓ propaga
main.py              →  catch EngineError, log + print
```

Ogni layer aggiunge solo ciò che conosce. Mai accesso a info che non gli appartiene.

---

## Implementation Plan (TDD)

Ogni step: test rosso → conferma fallimento → impl → verde → `make tests`.

### Step 1: `EngineError` base + `SampleNotFoundError`
- `tests/test_engine_exceptions.py`
  - `test_sample_not_found_has_user_message`
  - `test_sample_not_found_includes_optional_context`
  - `test_engine_error_subclass`
- impl: `src/shared/exceptions.py`

### Step 2: `get_sample_duration` raise pulito
- `tests/test_utils_sample_duration.py` (estende esistente se c'è)
  - `test_get_sample_duration_raises_sample_not_found_for_missing_file`
  - `test_get_sample_duration_message_contains_path`
- impl: guard `os.path.exists` in `utils.py`

### Step 3: `Stream.__init__` arricchisce con `stream_id`
- `tests/test_stream_error_context.py`
  - `test_stream_init_wraps_sample_error_with_id`
- impl: try/except in `Stream.__init__`

### Step 4: `Generator.create_elements` arricchisce con `config_file`
- test analogo per generator
- impl: try/except in `Generator.create_elements`

### Step 5: `engine_logger` configurabile
- `tests/test_engine_logger.py`
  - `test_engine_logger_writes_to_file`
  - `test_engine_logger_separate_from_clip_logger`
- impl: estensioni a `shared/logger.py`

### Step 6: `main.py` handler
- test e2e su sample mancante (forse manuale, o smoke test con subprocess)
- impl: catch `EngineError` in `main.py`, log + print

### Step 7: e2e manuale
- creare config con sample inesistente
- eseguire `make all FILE=...`
- verificare:
  - exit code 1
  - terminale: messaggio pulito senza traceback
  - file `./logs/<yaml>_engine.log` contiene traceback completo

---

## File toccati (riassunto)

**Nuovi:**
- `src/shared/exceptions.py`
- `tests/test_engine_exceptions.py`
- `tests/test_engine_logger.py`
- `tests/test_stream_error_context.py`

**Modificati:**
- `src/shared/utils.py` — guard `os.path.exists`
- `src/shared/logger.py` — `configure_engine_logger`, `get_engine_logger`
- `src/core/stream.py` — wrap in `__init__`
- `src/engine/generator.py` — wrap in `create_elements`
- `src/main.py` — handler `EngineError`
- test esistenti su utils/stream se presenti

---

## Out of scope

- Logging per errori YAML malformati (parser, schema validation)
- Logging per errori di rendering (Csound exit fail, NumPy buffer issues)
- Logging strutturato JSON
- Rotazione log

Estensioni future seguiranno lo stesso pattern (`EngineError` + caller wrapping + handler in `main.py`).

---

## Done criteria

- [x] `make tests` verde (4088 test passano)
- [x] Sample mancante produce messaggio terminale pulito + log file con traceback
- [x] Nessuna regressione su path felice (sample esistenti) — verificato con `configs/PGE_density_experiment.yml`
- [x] Test case riproducibile (`__nonexistent_sample_123__.wav`) e gestito correttamente

## E2E verifica (step 7)

Comando:
```
.venv/bin/python src/main.py /tmp/pge_e2e/broken.yml out.aif --renderer numpy
```

Output terminale (exit 1):
```
Caricamento /tmp/pge_e2e/broken.yml...
Generazione streams...
Creazione di 1 stream...
[ERRORE] Sample non trovato: '__nonexistent_sample_123__.wav'
  Path cercato: ./refs/__nonexistent_sample_123__.wav
  Stream:       drone_a
  Config:       /tmp/pge_e2e/broken.yml
  Dettagli:     ./logs/broken_engine.log
```

File `./logs/broken_engine.log`:
```
2026-05-09 18:41:43 [ERROR] Sample non trovato: '__nonexistent_sample_123__.wav' in ./refs/
Traceback (most recent call last):
  File ".../src/main.py", line 231, in main
    generator.create_elements()
  ...
shared.exceptions.SampleNotFoundError: Sample non trovato: '__nonexistent_sample_123__.wav' in ./refs/
```
