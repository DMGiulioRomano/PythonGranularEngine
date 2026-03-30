from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class Grain:
    """
    Rappresentazione immutabile di un singolo evento granulare.
    Usa slots=True per ottimizzare la memoria su grandi quantità di istanze.
    """
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

    def to_score_line(self, onset_offset: float = 0.0) -> str:
        """Genera la linea di score Csound.

        Args:
            onset_offset: sottratto dall'onset (usato in STEMS mode per onset relativi).
        """
        return (f'i "Grain" {self.onset - onset_offset:.6f} {self.duration:.6f} '
                f'{self.pointer_pos:.6f} {self.pitch_ratio:.6f} '
                f'{self.volume:.2f} {self.pan:.3f} '
                f'{self.sample_table} {self.envelope_table}\n')