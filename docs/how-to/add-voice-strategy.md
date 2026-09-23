---
slug: add-voice-strategy
type: how-to
status: stable
tags: [voices, strategy, extension]
sources:
  - src/pge/strategies/
  - src/pge/strategies/registry.py
  - src/pge/core/stream.py
last_synced_commit: 189e7b1
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
4. I kwarg della strategy non chiedono wiring. `Stream._build_voice_strategy`
   (`src/pge/core/stream.py`) e' il passo unico delle quattro dimensioni
   (issue #186): passa ogni kwarg per `_parse_strategy_kwarg`, che rende
   envelope quelli che ne hanno la forma, e inietta `stream_id`/`seed` se la
   strategy si chiama `stochastic`.

   `stream.py` va toccato solo in due casi, entrambi nel `take_block_keys`
   della dimensione in `Stream._VOICE_AXES`: un kwarg con la forma di un
   envelope che envelope non e' (come `progression` di `chord_progression`),
   da sottrarre alla conversione; oppure una chiave di blocco, config della
   dimensione e non della strategy (come `unit` del pitch o `normalized` del
   pointer). Pitch e pointer un `take_block_keys` ce l'hanno gia'
   (`_take_voice_pitch_keys`, `_take_voice_pointer_keys`); onset e pan no, e la
   riga di tabella e' dove aggiungerlo.

   Il passo scritto qui prima nominava `_build_<axis>_strategy`: quella
   funzione non e' mai esistita.
5. Test: `tests/strategies/test_voice_<axis>_strategy.py` con voice-0 invariant + envelope param + (per le stochastiche) determinismo dal `stream_id`

## File toccati

| Path | Tipo |
|------|------|
| `src/pge/strategies/voice_<axis>_<nome>.py` | nuovo file |
| `src/pge/strategies/voice_<axis>_strategy.py` | aggiunta a `VOICE_<AXIS>_STRATEGIES` |
| `src/pge/core/stream.py` | solo kwarg strutturali o chiavi di blocco (`take_block_keys`) |
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
