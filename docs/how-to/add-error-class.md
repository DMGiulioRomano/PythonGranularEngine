---
slug: add-error-class
type: how-to
status: stable
tags: [errors, exceptions, extension]
sources:
  - src/pge/shared/exceptions.py
last_synced_commit: 8c896d8
entry_for: [add-error-class]
---

# Add a New Error Class

## Quando usarlo

Devi sollevare un nuovo tipo di errore con un messaggio utente specifico, non coperto dalle eccezioni esistenti. Stop: se l'errore rientra in una classe già definita, usa quella e arricchisci context.

## Prerequisiti

- Lettura [[errors]] (gerarchia `EngineError`, `user_message()`, context enrichment)
- Decisione: errore di config YAML (`ConfigError`) o runtime engine (`EngineRuntimeError`)?
- Messaggio utente già scritto (head + righe dettaglio + context)

## Passi

1. Eredita dal nodo giusto in `src/pge/shared/exceptions.py`: `ConfigError` per YAML, `EngineRuntimeError` per runtime
2. Override `user_message()` (formato: `[ERRORE] head` + righe indentate + `self._context_lines()`)
3. Solleva con dato locale minimo
4. Arricchisci `stream_id` / `config_file` nei chiamanti (parser / controller / Generator)
5. Test unit + integration + e2e

## File toccati

| Path | Tipo |
|------|------|
| `src/pge/shared/exceptions.py` | nuova classe |
| Sito che la solleva | aggiornato |
| Chiamanti che arricchiscono context | aggiornato |

## Test da aggiornare

- `tests/shared/test_engine_exceptions.py` — unit
- Test integration sul sito che la solleva
- `tests/e2e/test_engine_errors_e2e.py` — e2e

## Verifica

```bash
make tests
make e2e-tests
```

Verifica anche `user_message()` ad occhio su un caso reale.
