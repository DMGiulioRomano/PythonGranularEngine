# src/shared/seeding.py
"""
seeding.py — derivazione deterministica del RNG per-voce (issue #81).

Singola fonte di verità per il seed locale delle voice strategy stocastiche
(`StochasticPitchStrategy`, `StochasticOnsetStrategy`, `StochasticPointerStrategy`,
`RandomPanStrategy`). Mantenere allineate le quattro strategy: tutte delegano qui.

Due regimi:

- `seed is None` → comportamento legacy: `hash(stream_id + str(voice_index))`.
  Stabile ENTRO un run, NON riproducibile fra processi: `hash()` su stringa è
  randomizzato per-processo (PYTHONHASHSEED non è fissato nel repo).
- `seed` valorizzato (int/str) → derivazione `hashlib.sha256` su
  `f"{seed}:{stream_id}:{voice_index}"`. `hashlib` è deterministico per
  costruzione: il valore non dipende da PYTHONHASHSEED, quindi è riproducibile
  fra processi diversi. Copre `seed: 0` e seed negativi/stringa senza casi speciali.
"""
from __future__ import annotations

import hashlib
import random


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
