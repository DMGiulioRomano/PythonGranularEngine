from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class Grain:
    """
    Rappresentazione immutabile di un singolo evento granulare.
    Usa un __slots__ esplicito per ottimizzare la memoria su grandi quantità di
    istanze. Equivale a dataclass(slots=True) ma resta compatibile con Python
    >= 3.9 (il parametro slots= di @dataclass esiste solo da 3.10).
    """
    __slots__ = (
        'onset', 'duration', 'pointer_pos', 'pitch_ratio',
        'volume', 'pan', 'sample_table', 'envelope_table',
    )
    onset: float
    duration: float
    pointer_pos: float
    pitch_ratio: float
    volume: float
    pan: float
    sample_table: int
    envelope_table: int

    def __post_init__(self):
        """Valida i tipi degli attributi al momento dell'inizializzazione."""
        # Validazione campi numerici (float/int accettabili)
        numeric_fields = ['onset', 'duration', 'pointer_pos', 'pitch_ratio', 'volume', 'pan']
        for field_name in numeric_fields:
            value = getattr(self, field_name)
            if not isinstance(value, (int, float)):
                raise TypeError(
                    f"Field '{field_name}' must be a number (int or float), "
                    f"got {type(value).__name__}"
                )
        
        # Validazione campi interi
        int_fields = ['sample_table', 'envelope_table']
        for field_name in int_fields:
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(
                    f"Field '{field_name}' must be an int, "
                    f"got {type(value).__name__}"
                )

    def __reduce__(self):
        """Pickling frozen+slots: lo slot-state di default viene ripristinato
        via setattr, che il __setattr__ frozen rifiuta. Ricostruire via
        __init__ preserva immutabilita' e validazione (necessario per il
        rendering multi-processo, dove i Grain attraversano il pickle)."""
        return (self.__class__, (
            self.onset, self.duration, self.pointer_pos, self.pitch_ratio,
            self.volume, self.pan, self.sample_table, self.envelope_table,
        ))
