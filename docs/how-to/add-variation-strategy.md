---
slug: add-variation-strategy
type: how-to
status: stable
tags: [strategy, variation, extension]
sources:
  - src/strategies/variation_registry.py
last_synced_commit: 8c896d8
entry_for: [add-variation-strategy]
---

# Add a New Variation Strategy

## Quando usarlo

Aggiungere un nuovo modo di variare i parametri grain nel tempo (es. perlin noise, deterministic chaos, custom probability distribution). Stop: per voice strategy vedi [[add-voice-strategy]]; per envelope custom non serve — sono già esposti via YAML.

## Prerequisiti

- Conoscenza ABC `VariationStrategy` (`src/strategies/variation_strategy.py`)
- Decisione: la strategy è deterministica? Se sì, deve usare `stream_id` come seed
- Conoscenza interfaccia: `apply(value, time, ...)` o equivalente

## Passi

1. Crea la classe in `src/strategies/<nome>_variation.py` ed eredita `VariationStrategy`
2. Registra in `src/strategies/variation_registry.py` (`VariationFactory.REGISTRY`)
3. Usa in YAML: `variation_mode: 'nome_strategy'`
4. Test determinismo (stesso `stream_id` → stessa sequenza) e invarianti

## File toccati

| Path | Tipo |
|------|------|
| `src/strategies/<nome>_variation.py` | nuovo file |
| `src/strategies/variation_registry.py` | aggiunta a REGISTRY |
| `tests/strategies/test_<nome>_variation.py` | nuovi test |

## Test da aggiornare

- Test determinismo per seed
- Test bounds (output mai fuori da range del parametro)
- Test integrazione con uno stream YAML

## Verifica

```bash
make tests
```

Render con YAML che usa la nuova strategy + ascolto.
