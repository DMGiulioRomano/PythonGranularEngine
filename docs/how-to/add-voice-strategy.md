---
slug: add-voice-strategy
type: how-to
status: stable
tags: [voices, strategy, extension]
sources:
  - src/pge/strategies/
  - src/pge/strategies/registry.py
  - src/pge/core/stream.py
  - src/pge/shared/seeding.py
last_synced_commit: cef5050
entry_for: [add-voice-strategy]
---

# Add a New Voice Strategy

## Quando usarlo

Estendere il sistema multi-voice lungo uno degli assi: pitch, onset, pointer, pan. Per un asse nuovo (non uno dei 4) servirà refactor più ampio — non coperto qui.

## Prerequisiti

- Lettura [[multi-voice]] § invarianti
- Identifica l'asse: `pitch | onset | pointer | pan`
- Conosci l'ABC corrispondente: `VoicePitchStrategy`, `VoiceOnsetStrategy`, `VoicePointerStrategy`, `VoicePanStrategy`
- Invariante: `voice_index == 0` deve sempre ritornare `0.0` — `1.0` sul pitch, che restituisce un fattore di ratio e non un offset. Per onset: offset `>= 0`.

## Passi

1. Sottoclasse l'ABC giusta in `src/pge/strategies/`
2. Implementa `get_<axis>_offset(voice_index, num_voices, time)` per onset,
   pointer e pan; per il pitch `get_pitch_factor(voice_index, num_voices,
   time, unit)`, che materializza la posizione con la `PitchUnit` attiva
   (`unit.materialize` / `unit.to_ratio`) e restituisce un fattore di ratio.
   Sul pan serve anche la property `name`, che `VoicePanStrategy` dichiara
   astratta (le altre tre ABC no): senza, la registrazione passa e la classe
   cade al primo `create` con un `TypeError` — cioe' alla costruzione dello
   stream che la usa
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

   `stream.py` va toccato in tre casi. I primi due stanno nel
   `take_block_keys` della dimensione in `Stream._VOICE_AXES`: un kwarg con la
   forma di un envelope che envelope non e' (come `progression` di
   `chord_progression`), da sottrarre alla conversione; oppure una chiave di
   blocco, config della dimensione e non della strategy (come `unit` del pitch
   o `normalized` del pointer). Pitch e pointer un `take_block_keys` ce l'hanno
   gia' (`_take_voice_pitch_keys`, `_take_voice_pointer_keys`); onset e pan
   no: si scrive il metodo su `Stream` e se ne mette il *nome*, come stringa,
   nella riga di tabella. `_build_voice_strategy` lo risolve sull'istanza,
   quindi un override o un `patch.object` lo raggiungono.

   Il terzo e' una strategy stocastica nuova. L'iniezione di `stream_id`
   (che vale `rng_id`, #169) e `seed` in `_build_voice_strategy` e' decisa dal
   nome, `name == 'stochastic'`, e quel nome e' gia' preso su tutti e quattro
   gli assi: una seconda stocastica ne ha per forza un altro. Senza toccare
   quella condizione il costruttore non riceve `stream_id` — un `TypeError`
   se l'argomento e' obbligatorio, come nelle quattro esistenti, e se e'
   opzionale la perdita silenziosa della riproducibilita' e di `rng_group`.

   Il passo scritto qui prima nominava `_build_<axis>_strategy`: quella
   funzione non e' mai esistita.
5. Test: `tests/strategies/test_voice_<axis>_strategy.py` con voice-0 invariant + envelope param + (per le stochastiche) determinismo da `(seed, stream_id, voice_index)` via `voice_rng` — vedi sotto

## File toccati

| Path | Tipo |
|------|------|
| `src/pge/strategies/voice_<axis>_strategy.py` | nuova classe, accanto alle altre dell'asse, e sua voce in `VOICE_<AXIS>_STRATEGIES` |
| `src/pge/core/stream.py` | solo kwarg strutturali o chiavi di blocco (`take_block_keys`), o una stocastica con un nome diverso da `stochastic` |
| `tests/strategies/test_voice_<axis>_strategy.py` | nuovi test |

## Test da aggiornare

- Voice-0 invariant: `get_<axis>_offset(0, N, t) == 0.0` per ogni N, t (pitch: `get_pitch_factor(0, N, t, unit) == 1.0`)
- Determinismo (per strategy stochastic): con un `seed`, il valore e' quello
  di `voice_rng(seed, stream_id, voice_index)` (`src/pge/shared/seeding.py`,
  sha256), quindi uguale fra processi; e `seed` diversi danno offset diversi.
  Il modello sono le `TestStochastic<Axis>Seed` delle quattro suite esistenti.
  Un test «stesso `stream_id` → stesso risultato» non basta: con `seed=None`
  vale il fallback `hash()`, stabile dentro il processo, e quel test passa
  anche su una strategy che scarta il `seed` — cioe' che non riproduce il
  brano fuori dal run in cui e' stato ascoltato
- Envelope param: se la strategy accetta envelope, test che il valore evolva nel tempo

## Verifica

```bash
make tests
```

YAML con `voices: {num_voices: N, <chiave>: {strategy: <nome>, ...}}` e ascolto del risultato.
`<chiave>` e' la chiave YAML della riga in `Stream._VOICE_AXES` (`pitch`,
`onset_offset`, `pointer`, `pan`), non il nome dell'asse usato negli altri
passi: per l'onset le due differiscono, e un `onset:` dentro `voices:` viene
ignorato senza errore — la strategy non viene nemmeno costruita, e l'ascolto
non ha niente da far sentire. `N` almeno 2: la voce 0 non riceve offset.
