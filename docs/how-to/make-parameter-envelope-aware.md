---
slug: make-parameter-envelope-aware
type: how-to
status: stable
tags: [parameters, envelopes, extension]
sources:
  - src/parameters/parameter_schema.py
  - src/envelopes/envelope.py
last_synced_commit: 8c896d8
entry_for: [make-parameter-envelope-aware]
---

# Make a Parameter Envelope-Aware

## Quando usarlo

Un parametro esistente accetta solo scalari e vuoi farlo accettare anche envelope. Stop: per un parametro nuovo, fai entrambi i passi insieme — vedi [[add-parameter]] + questo doc.

## Prerequisiti

- Il parametro è già definito (vedi [[add-parameter]])
- Decisione: il sito di consumo legge il valore una volta o ad ogni tempo `t`?
- Conoscenza [[yaml]] § Envelopes (sintassi accettate)

## Passi

1. Schema (`STREAM_PARAMETER_SCHEMA` o sotto-schema): aggiungi flag `accepts_envelope: True`
2. Sito di consumo: invece di leggere `params['x']`, usa `resolve_param(self.x, time)` (o `self.x.evaluate(time)` se garantito Envelope)
3. Per voice strategy: il parsing in `Stream._parse_strategy_kwarg` riconosce automaticamente liste `[[t, v], ...]` e dict `{points, time_mode}` e li trasforma in `Envelope`
4. Test envelope: scalare puro, lista breakpoint, dict cubic, formato compatto

## File toccati

| Path | Tipo |
|------|------|
| `src/parameters/parameter_schema.py` | flag `accepts_envelope: True` |
| Sito di consumo | uso di `evaluate(time)` |

## Test da aggiornare

- Test parametro con scalare (backward compat)
- Test parametro con envelope breakpoint
- Test parametro con envelope cubic + formato compatto
- Test bounds (envelope con breakpoint fuori range solleva `ParameterBoundError`)

## Verifica

```bash
make tests
```

YAML reale con envelope sul parametro + ascolto.

Sintassi accettate dal parser: [[yaml]] § Envelopes.
