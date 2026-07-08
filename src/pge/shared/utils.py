from __future__ import annotations

import os
import random
import soundfile as sf
from typing import Any, Optional

from pge.shared.exceptions import SampleNotFoundError

# Path per i sample audio.
# DEPRECATO come stato globale (Fase 2 refactor library/CLI): preferire il
# parametro base_path di get_sample_duration / samples_dir di Stream e
# Generator. Resta come fallback per compatibilita' coi monkey-patch esterni
# durante la transizione.
PATHSAMPLES = './refs/'

def get_sample_duration(filepath: str, base_path: Optional[str] = None) -> float:
    """Ottiene la durata di un file audio in secondi.

    Args:
        filepath: nome del file relativo alla directory sample
        base_path: directory sample; None -> fallback sul globale
            PATHSAMPLES (deprecato)

    Raises:
        SampleNotFoundError: se il file non esiste nella directory sample.
    """
    base = base_path if base_path is not None else PATHSAMPLES
    if base and not base.endswith(('/', os.sep)):
        base = base + '/'
    full_path = base + filepath
    if not os.path.exists(full_path):
        raise SampleNotFoundError(filename=filepath, search_path=base)
    info = sf.info(full_path)
    return info.duration


def random_percent(percent: float = 90) -> bool:
    """Ritorna True con probabilità percent%."""
    return (percent / 100) > random.uniform(0, 1)

def get_nested(data: dict, path: str, default: Any) -> Any:
    """
    Naviga un dict con dot notation.
    
    Args:
        data: Dizionario da navigare
        path: Percorso in dot notation (es. 'grain.duration')
        default: Valore di default se il percorso non esiste
        
    Returns:
        Valore trovato o default
    """
    keys = path.split('.')
    current = data
    
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    
    return current
