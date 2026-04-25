---
title: "feat: Add SpectralPitchStrategy — distribuzione voci sulla serie armonica"
type: feat
status: active
date: 2026-04-25
origin: https://github.com/DMGiulioRomano/PythonGranularEngine/issues/21
---

# feat: Add SpectralPitchStrategy — distribuzione voci sulla serie armonica

## Overview

Aggiunge `SpectralPitchStrategy`, una nuova voice pitch strategy che distribuisce le
voci sui parziali della serie armonica naturale. La voce `i` riceve l'offset
`round(12 * log2(i + 1))` semitoni, producendo texture risonanti coerenti con
la fisica acustica. La strategy è accessibile via YAML con `strategy: spectral`.

---

## Problem Frame

Le strategy di pitch esistenti (`step`, `range`, `chord`, `stochastic`) operano in
logica armonica temperata o stocastica. Nessuna rispecchia la struttura fisica dello
spettro armonico. `SpectralPitchStrategy` colma questo gap: distribuisce le voci
secondo i rapporti di frequenza interi (1f, 2f, 3f, …), che convertiti in semitoni
producono la serie [0, 12, 19, 24, 28, 31, 34, 36, …].

---

## Requirements Trace

- R1. Voce `i` restituisce `round(12 * log2(i + 1))` semitoni (i 1-based per il parziale).
- R2. Voce 0 restituisce sempre `0.0` (invariante condiviso da tutte le strategy).
- R3. `max_partial` (default 16) pre-calcola i parziali; se `num_voices > max_partial`, i
  parziali sono estesi dinamicamente con la stessa formula.
- R4. La strategy è registrata in `VOICE_PITCH_STRATEGIES` con chiave `'spectral'`.
- R5. `VoicePitchStrategyFactory.create('spectral')` restituisce un'istanza valida.
- R6. `strategy: spectral` in un config YAML con `num_voices: 8` produce output coerente.

---

## Scope Boundaries

- Non si modifica la formula matematica della serie armonica — è fisica, non una scelta.
- Non si aggiunge supporto per `fundamental_hz` o trasposizione assoluta: la strategy
  restituisce offset in semitoni rispetto al pitch base dello stream, come tutte le altre.
- Non si tocca `stream.py`, `voice_manager.py`, né alcun renderer: il parser YAML e la
  factory esistenti gestiscono già `strategy: spectral` senza modifiche.
- Nessun file di documentazione aggiuntivo richiesto: l'issue è autoesplicativa e
  `docs/yaml-reference.md` non è nel perimetro di questa PR.

---

## Context & Research

### Relevant Code and Patterns

- `src/strategies/voice_pitch_strategy.py` — modulo da estendere; struttura consolidata:
  costanti → ABC → classi concrete → registry dict → `register_*` → factory.
- `tests/strategies/test_voice_pitch_strategy.py` — suite da estendere; pattern `_get_module()`
  con import lazy e unpacking posizionale; fixture `restore_registry` autouse.
- `TestVoiceZeroInvariant` (riga 342) — usa `pytest.mark.parametrize` con lambda indicizzate
  sul tuple restituito da `_get_module()`; va aggiunta una lambda per `SpectralPitchStrategy`.
- `ChordPitchStrategy` — il pattern più vicino per la logica "lista di offsets pre-calcolata
  al `__init__` + extend dinamico se `voice_index` supera la lista" è il riferimento da seguire.

### Institutional Learnings

- Nessun learning archiviato in `docs/solutions/` (directory assente).

### External References

- Issue #21: tabella parziali 1–16 e formula `round(12 * log2(n))`.

---

## Key Technical Decisions

- **Pre-calcolo al `__init__`**: gli offset sono calcolati una volta sola e memorizzati in
  `self._offsets: list[float]` fino a `max_partial`. Questo allinea la struttura a
  `ChordPitchStrategy` (lista `_intervals`) e rende `get_pitch_offset` O(1).
- **Extend dinamico**: se `voice_index >= max_partial`, l'offset viene calcolato on-demand
  con la formula e aggiunto alla lista. Nessun limite rigido, nessuna eccezione.
- **`math.log2`**: si usa il modulo stdlib `math`, non `numpy`, coerentemente con il resto
  del modulo che non importa numpy.
- **Arrotondamento a `int` poi cast a `float`**: `round(12 * log2(i+1))` restituisce `int`
  in Python; il cast a `float` è necessario perché il contratto ABC dichiara `-> float`.
- **Posizione nel file**: la classe va inserita dopo `StochasticPitchStrategy` e prima del
  blocco `# REGISTRY`, coerentemente con l'ordine dichiarato nel docstring del modulo.

---

## Open Questions

### Resolved During Planning

- **`max_partial` è un parametro del costruttore o una costante?** — Parametro del
  costruttore con default 16, come da issue. Consente flessibilità senza modificare la classe.
- **La formula usa `round()` o `int()`?** — `round()`, come da issue. I parziali come 7 e 11
  hanno offset irrazionali (es. 34.02, 41.96); arrotondare è la scelta acusticamente corretta.
- **`stream.py` va aggiornato?** — No. Il parser estrae `strategy` e fa `pop` dei kwargs
  rimanenti, passandoli a `VoicePitchStrategyFactory.create(name, **kw)`. Il flusso supporta
  già `max_partial` come kwarg opzionale senza modifiche.

### Deferred to Implementation

- Nessuno.

---

## Implementation Units

- [x] U1. **Aggiungere `SpectralPitchStrategy` e registrarla nel registry**

**Goal:** Implementare la classe e renderla disponibile via `VOICE_PITCH_STRATEGIES['spectral']`.

**Requirements:** R1, R2, R3, R4, R5

**Dependencies:** Nessuna (l'implementazione viene dopo i test — TDD)

**Files:**
- Modify: `src/strategies/voice_pitch_strategy.py`

**Approach:**
- Aggiungere `import math` in cima al file (se non già presente).
- Definire `SpectralPitchStrategy(VoicePitchStrategy)` dopo `StochasticPitchStrategy`.
- Nel `__init__(self, max_partial: int = 16)`: pre-calcolare `_offsets` come lista
  `[float(round(12 * math.log2(i + 1))) for i in range(max_partial)]` con il primo
  elemento fissato a `0.0` (parziale 1 = fondamentale, `log2(1) = 0`).
- In `get_pitch_offset`: se `voice_index == 0` restituire `0.0`; se `voice_index <
  len(self._offsets)` restituire `self._offsets[voice_index]`; altrimenti calcolare
  on-demand `float(round(12 * math.log2(voice_index + 1)))`, aggiungere alla lista,
  e restituirlo.
- Aggiungere `'spectral': SpectralPitchStrategy` in `VOICE_PITCH_STRATEGIES`.

**Execution note:** Implementazione test-first — scrivere U2 prima di questo unit.

**Patterns to follow:**
- `ChordPitchStrategy.__init__` per la pre-computazione della lista al costruttore.
- `StochasticPitchStrategy.get_pitch_offset` per il pattern `if voice_index == 0: return 0.0`.

**Test scenarios:**
- Happy path: `get_pitch_offset(0, 8)` → `0.0` (fondamentale)
- Happy path: `get_pitch_offset(1, 8)` → `12.0` (parziale 2, ottava)
- Happy path: `get_pitch_offset(2, 8)` → `19.0` (parziale 3, quinta)
- Happy path: sequenza voci 0–7 → `[0, 12, 19, 24, 28, 31, 34, 36]`
- Edge case: offset della serie sono monotonicamente crescenti
- Edge case: `voice_index == max_partial` (primo oltre la lista) → calcolato dinamicamente
- Edge case: `voice_index > max_partial` → calcolato correttamente con la formula

**Verification:**
- `SpectralPitchStrategy` è importabile da `strategies.voice_pitch_strategy`.
- `'spectral' in VOICE_PITCH_STRATEGIES` è `True`.
- `get_pitch_offset(0, n)` restituisce `0.0` per qualsiasi `n`.

---

- [x] U2. **Scrivere `TestSpectralPitchStrategy` e aggiornare la suite esistente**

**Goal:** Coprire il contratto di `SpectralPitchStrategy` con test esaustivi; aggiornare
`_get_module()` e `TestVoiceZeroInvariant` per includere la nuova classe.

**Requirements:** R1, R2, R3, R4, R5

**Dependencies:** Nessuna (i test vanno scritti prima dell'implementazione — TDD)

**Files:**
- Modify: `tests/strategies/test_voice_pitch_strategy.py`

**Approach:**
- Estendere l'import in `_get_module()`: aggiungere `SpectralPitchStrategy` all'import e
  al tuple di ritorno come nono elemento (dopo `VoicePitchStrategyFactory`).
- Aggiornare `TestVoicePitchStrategiesRegistry` aggiungendo `test_registry_contains_spectral`.
- Aggiungere una lambda in `TestVoiceZeroInvariant` per `SpectralPitchStrategy`:
  `lambda m: m[8](max_partial=4)` dove `m[8]` è il nono elemento del tuple.
- Aggiungere `class TestSpectralPitchStrategy` con i test elencati.

**Execution note:** Scrivi i test prima dell'implementazione. Eseguire `make tests` e
verificare che tutti i nuovi test falliscano (red) prima di passare a U1.

**Patterns to follow:**
- Pattern di unpacking `m[8]` per il nono elemento aggiunto a `_get_module()`.
- `TestStepPitchStrategy` come modello di struttura per la nuova classe di test.
- `TestVoiceZeroInvariant` per il pattern lambda parametrizzato.

**Test scenarios:**
- Happy path: `test_voice_0_returns_zero` — `SpectralPitchStrategy().get_pitch_offset(0, 8) == 0.0`
- Happy path: `test_voice_1_returns_12` — parziale 2 = ottava
- Happy path: `test_voice_2_returns_19` — parziale 3 = quinta
- Happy path: `test_first_8_partials` — sequenza `[0, 12, 19, 24, 28, 31, 34, 36]`
- Edge case: `test_offsets_are_monotonically_increasing` — ogni elemento maggiore del precedente
- Edge case: `test_beyond_default_max_partial` — voce 16 calcolata dinamicamente con formula corretta
- Edge case: `test_default_max_partial_is_16` — `SpectralPitchStrategy().max_partial == 16`
- Edge case: `test_custom_max_partial` — `SpectralPitchStrategy(max_partial=8).max_partial == 8`
- Integration: `test_in_registry` — `'spectral' in VOICE_PITCH_STRATEGIES`
- Integration: `test_factory_creates_spectral` — `VoicePitchStrategyFactory.create('spectral')` è istanza di `SpectralPitchStrategy`
- Integration: `test_factory_creates_spectral_with_max_partial` — `VoicePitchStrategyFactory.create('spectral', max_partial=8)` funziona

**Verification:**
- `make tests` passa completamente (verde) dopo U1 + U2.
- Tutti i nuovi test sono rossi prima di U1, verdi dopo.

---

## System-Wide Impact

- **Interaction graph:** Nessuna callback o middleware coinvolto. `stream.py` passa `**kw`
  alla factory senza conoscerne il contenuto — nessuna modifica richiesta.
- **Error propagation:** `VoicePitchStrategyFactory.create('spectral', max_partial='x')`
  solleverà `TypeError` dal costruttore Python, comportamento coerente con le altre strategy.
- **State lifecycle risks:** `_offsets` cresce on-demand ma è bounded da `num_voices` che
  non varia durante il ciclo di vita di uno stream. Nessun rischio di leak.
- **API surface parity:** `register_voice_pitch_strategy` resta invariata; il registry
  esteso non rompe nessun consumer esistente.
- **Integration coverage:** Un config YAML `strategy: spectral, num_voices: 8` deve
  produrre 8 voci con pitch offset `[0, 12, 19, 24, 28, 31, 34, 36]` — verificabile
  manualmente con `make FILE=<config> all`.
- **Unchanged invariants:** Tutte le strategy esistenti e i loro test rimangono invariati.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| L'unpacking posizionale di `_get_module()` rompe i test esistenti se il nuovo elemento viene inserito in posizione errata | Aggiungere `SpectralPitchStrategy` come **ultimo** elemento del tuple, dopo `VoicePitchStrategyFactory`, e usare `m[8]` nella lambda di `TestVoiceZeroInvariant` |
| `math.log2(1) == 0.0` ma `round(0.0) == 0` — il parziale 1 deve dare esattamente `0.0` | Pre-calcolo nel `__init__` con `i` che parte da 0: `log2(0+1) = log2(1) = 0.0`, confermato |
| `voice_index` passato come argomento può differire dall'indice nel dict di parziali se `num_voices` cambia tra chiamate | `get_pitch_offset` usa `voice_index` direttamente come indice del parziale (non `num_voices`) — comportamento deterministico e indipendente da `num_voices` |

---

## Sources & References

- **Origin document (issue):** https://github.com/DMGiulioRomano/PythonGranularEngine/issues/21
- Related code: `src/strategies/voice_pitch_strategy.py`
- Related tests: `tests/strategies/test_voice_pitch_strategy.py`
