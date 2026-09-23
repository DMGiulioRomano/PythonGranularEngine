---
slug: add-variation-strategy
type: how-to
status: stable
tags: [strategy, variation, extension]
sources:
  - src/pge/strategies/variation_registry.py
  - src/pge/strategies/registry.py
last_synced_commit: a849234
entry_for: [add-variation-strategy]
---

# Add a New Variation Strategy

## Quando usarlo

Aggiungere un nuovo modo di variare i parametri grain nel tempo (es. perlin noise, deterministic chaos, custom probability distribution). Stop: per voice strategy vedi [[add-voice-strategy]]; per envelope custom non serve — sono già esposti via YAML.

## Prerequisiti

- Conoscenza ABC `VariationStrategy` (`src/pge/strategies/variation_strategy.py`)
- Decisione: la strategy è deterministica? Se sì, deve usare `stream_id` come seed
- Conoscenza interfaccia: `apply(value, time, ...)` o equivalente

## Passi

1. Crea la classe in `src/pge/strategies/<nome>_variation.py` ed eredita `VariationStrategy`
2. Registra nella mappa di modulo di `src/pge/strategies/variation_registry.py`
   — `VARIATION_STRATEGIES`, che dalla #185 è uno `StrategyRegistry` del
   dominio `variation` (forma decisa in #177). A runtime si passa invece per
   `register_variation_strategy(name, strategy_class)`, che è l'API di
   estensione dinamica e annuncia la registrazione al logger `pge.diagnostics`.

   La factory **non** ha un attributo `REGISTRY`, e non l'ha mai avuto: questo
   passo diceva `VariationFactory.REGISTRY` e mandava a un nome inesistente.
   La mappa vive a livello di modulo, che è dove i test la cercano.
3. Usa in YAML: `variation_mode: 'nome_strategy'`
4. Test determinismo (stesso `stream_id` → stessa sequenza) e invarianti

## File toccati

| Path | Tipo |
|------|------|
| `src/pge/strategies/<nome>_variation.py` | nuovo file |
| `src/pge/strategies/variation_registry.py` | aggiunta a `VARIATION_STRATEGIES` |
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
