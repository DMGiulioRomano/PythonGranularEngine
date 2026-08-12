# src/shared/seeding.py
"""
seeding.py — derivazione deterministica degli RNG locali (issue #81, #154, #169).

Singola fonte di verità per la derivazione dei generatori pseudo-casuali:

- `voice_rng` (issue #81): RNG per-voce delle voice strategy stocastiche
  (`StochasticPitchStrategy`, `StochasticOnsetStrategy`,
  `StochasticPointerStrategy`, `StochasticPanStrategy`).
- `component_rng` (issue #154): RNG per-componente di tutti gli altri siti
  stocastici della generazione grani (variazione `_range` dei Parameter,
  probability gate, IOT async, selezione finestra, detune implicito).
  Ogni componente pesca dal proprio stream: solo/mute, cache stems e ordine
  di materializzazione non alterano i draw degli altri componenti.
- `session_seed` (issue #154): seed di sessione derivato da timestamp per i
  run senza `seed:` nello YAML — loggato dal Generator, così ogni run resta
  ricostruibile a posteriori.

Identità di derivazione (issue #169): il parametro `stream_id` di queste
funzioni è l'*identità* della sequenza, non necessariamente l'id dello
stream. I call site passano `StreamContext.rng_id`: lo stream_id di default
(isolamento per-stream, contratto #154) oppure il `rng_group` dichiarato
nello YAML per-stream — così stream diversi possono pescare la stessa
sequenza pseudo-casuale. Le firme qui non cambiano: la leva è tutta nel
valore passato dai chiamanti.

Regimi di derivazione:

- `seed` valorizzato (int/str) → `hashlib.sha256` su
  `f"{seed}:{stream_id}:{discriminante}"`. `hashlib` è deterministico per
  costruzione: il valore non dipende da PYTHONHASHSEED, quindi è riproducibile
  fra processi diversi. Copre `seed: 0` e seed negativi/stringa senza casi
  speciali.
- `seed is None` → comportamento legacy, diverso per funzione:
  `voice_rng` usa `hash(stream_id + str(voice_index))` (stabile ENTRO un run,
  NON riproducibile fra processi); `component_rng` restituisce il modulo
  `random` globale (per le costruzioni dirette fuori dal Generator — il
  Generator non passa mai None: senza seed YAML genera un session seed).
"""
from __future__ import annotations

import hashlib
import random
import time


def voice_rng(seed, stream_id: str, voice_index: int) -> random.Random:
    """Restituisce un `random.Random` deterministico per (seed, stream_id, voice_index).

    Args:
        seed: seed YAML top-level (int/str) oppure None per il fallback legacy.
        stream_id: id dello stream proprietario della voce.
        voice_index: indice della voce (0-based).

    Returns:
        Istanza `random.Random` già seminata.
    """
    if seed is None:
        derived = hash(stream_id + str(voice_index))
    else:
        digest = hashlib.sha256(
            f"{seed}:{stream_id}:{voice_index}".encode()
        ).hexdigest()
        derived = int(digest, 16)
    return random.Random(derived)


def component_rng(seed, stream_id: str, component: str):
    """Restituisce l'RNG locale per (seed, stream_id, component) — issue #154.

    Componenti in uso: il nome del Parameter (es. `grain_duration`,
    `pitch_semitones`), `gate:<deviation_probability_key>` per i probability gate, `iot`
    (distribuzione Truax async), `window` (selezione finestra), `detune`
    (detune implicito EDO). Componenti distinti → stream RNG indipendenti.

    Args:
        seed: seed effettivo (YAML o di sessione) oppure None.
        stream_id: id dello stream proprietario del componente.
        component: discriminante testuale del sito stocastico.

    Returns:
        `random.Random` seminato via sha256 se `seed` è valorizzato; il modulo
        `random` globale se `seed` è None (fallback legacy per costruzioni
        dirette di Stream/controller fuori dal Generator).
    """
    if seed is None:
        return random
    digest = hashlib.sha256(
        f"{seed}:{stream_id}:{component}".encode()
    ).hexdigest()
    return random.Random(int(digest, 16))


def session_seed() -> int:
    """Genera il seed di sessione per i run senza `seed:` nello YAML.

    Derivato dal timestamp (ns) e ridotto a 9 cifre per essere comodo da
    copiare nello YAML (`seed: <valore loggato>`): il run torna riproducibile
    a posteriori con la stessa derivazione dei seed espliciti.
    """
    return time.time_ns() % 1_000_000_000
