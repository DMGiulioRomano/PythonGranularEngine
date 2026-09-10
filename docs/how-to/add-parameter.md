---
slug: add-parameter
type: how-to
status: stable
tags: [parameters, schema, extension]
sources:
  - src/pge/parameters/parameter_definitions.py
  - src/pge/parameters/parameter_schema.py
last_synced_commit: 4bfc074
entry_for: [add-parameter]
---

# Add a New Parameter to Stream

## Quando usarlo

Hai un parametro nuovo da accettare a livello stream o sub-blocco YAML (es. nuovo controllo grain, nuovo flag densità). Stop: se il parametro è solo locale a una strategy, vedi [[add-voice-strategy]].

## Prerequisiti

- Conoscenza schema parametri ([[yaml]] § Parameter Syntax)
- Bounds del parametro decisi (min, max, default, unità)
- Decisione: accetta envelope o solo scalare? Se envelope → leggi anche [[make-parameter-envelope-aware]]
- Se ha un `_range`: la banda è sempre assoluta, o ha senso dichiararla come
  frazione del valore base? Nel secondo caso lo spec porta anche un
  `range_unit_path` (es. `grain.duration_range_unit`), e il dominio del range
  diventa `RELATIVE_RANGE_BOUNDS` invece di quello del parametro. Vale la pena
  solo dove la base spazia su più ordini di grandezza — vedi [[yaml]] § Banda
  relativa

## Passi

1. Aggiungi la definizione (bounds) in `src/pge/parameters/parameter_definitions.py`
2. Aggiungi la entry di schema in `src/pge/parameters/parameter_schema.py` (`STREAM_PARAMETER_SCHEMA` o sotto-schema appropriato), con `range_path` e — se serve — `range_unit_path`
3. Accedi al parametro nel `Stream` o controller via `self.parameter_name.evaluate(time)`
4. Aggiungi test unit per il bound + test di parsing con valore valido e fuori range
5. Aggiorna [[yaml]] § Tabella Bounds Parametri con la nuova riga

## File toccati

| Path | Tipo |
|------|------|
| `src/pge/parameters/parameter_definitions.py` | nuova entry bounds |
| `src/pge/parameters/parameter_schema.py` | nuova entry schema |
| `src/pge/core/stream.py` o controller specifico | consumo del parametro |
| `docs/reference/yaml.md` | tabella bounds aggiornata |

## Test da aggiornare

- `tests/parameters/test_parameter_definitions.py` — bound assertion
- `tests/parameters/test_parameter_schema.py` — schema validation
- `tests/integration/` — pipeline parse → usa parametro

## Verifica

```bash
make tests
```

Se il parametro accetta envelope, esegui anche un YAML reale con envelope sul parametro e verifica il render.
