---
slug: add-voice-strategy
type: how-to
status: stable
tags: [voices, strategy, extension]
sources:
  - src/pge/strategies/
  - src/pge/strategies/registry.py
  - src/pge/core/stream.py
last_synced_commit: a849234
entry_for: [add-voice-strategy]
---

# Add a New Voice Strategy

## Quando usarlo

Estendere il sistema multi-voice lungo uno degli assi: pitch, onset, pointer, pan. Per un asse nuovo (non uno dei 4) servirà refactor più ampio — non coperto qui.

## Prerequisiti

- Lettura [[multi-voice]] § invarianti
- Identifica l'asse: `pitch | onset | pointer | pan`
- Conosci l'ABC corrispondente: `VoicePitchStrategy`, `VoiceOnsetStrategy`, `VoicePointerStrategy`, `VoicePanStrategy`
- Invariante: `voice_index == 0` deve sempre ritornare `0.0`. Per onset: offset `>= 0`.

## Passi

1. Sottoclasse l'ABC giusta in `src/pge/strategies/`
2. Implementa `get_<axis>_offset(voice_index, num_voices, time)`
3. Registra nella mappa di modulo dell'asse — `VOICE_<AXIS>_STRATEGIES`, che
   sta accanto alle classi in `voice_<axis>_strategy.py`. A runtime si passa
   invece per `register_voice_<axis>_strategy(nome, Classe)`, che e' l'API di
   estensione dinamica.

   La factory **non** ha un attributo `REGISTRY`, e non l'ha mai avuto: questo
   passo diceva `Voice<Axis>StrategyFactory.REGISTRY` e mandava a un nome
   inesistente. La mappa vive a livello di modulo, che e' dove i test la
   cercano e dove la parita' di PGE-ls la importa per nome.

   Le mappe dei quattro assi sono `StrategyRegistry` (issue #184 per pan,
   #185 per pitch, onset e pointer; forma decisa in #177): il valore si scrive
   uguale, ma la registrazione dinamica e la costruzione passano per i metodi
   del registry invece che per codice ripetuto in ogni modulo. La firma e'
   la stessa su tutti e quattro — `register_voice_<axis>_strategy(name,
   strategy_class)` — e la mappa resta un `dict` a tutti gli effetti.
4. Se i parametri richiedono parsing custom (es. envelope auto-detect), estendi `_build_<axis>_strategy` in `src/pge/core/stream.py` via `_parse_strategy_kwarg`
5. Test: `tests/strategies/test_voice_<axis>_strategy.py` con voice-0 invariant + envelope param + (per le stochastiche) determinismo dal `stream_id`

## File toccati

| Path | Tipo |
|------|------|
| `src/pge/strategies/voice_<axis>_<nome>.py` | nuovo file |
| `src/pge/strategies/voice_<axis>_strategy.py` | aggiunta a `VOICE_<AXIS>_STRATEGIES` |
| `src/pge/core/stream.py` | eventuale parsing kwarg |
| `tests/strategies/test_voice_<axis>_strategy.py` | nuovi test |

## Test da aggiornare

- Voice-0 invariant: `get_<axis>_offset(0, N, t) == 0.0` per ogni N, t
- Determinismo (per strategy stochastic): stesso `stream_id` → stesso risultato
- Envelope param: se la strategy accetta envelope, test che il valore evolva nel tempo

## Verifica

```bash
make tests
```

YAML con `voices: {num_voices: N, <axis>: {strategy: <nome>, ...}}` e ascolto del risultato.
