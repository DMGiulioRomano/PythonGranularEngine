# src/parameters/pitch_unit.py
"""
pitch_unit.py

Astrazione delle unità di misura del pitch: converte un valore espresso in una
data unità nel ratio di frequenza corrispondente.

Famiglia esponenziale (Equal Division of the Octave):
    ratio = 2^(value / divisions)
    semitones=12, quarter_tone=24, eighth_tone=48, cents=1200, edo:N=N
Famiglia moltiplicativa:
    ratio = value (RatioUnit)
"""

from abc import ABC, abstractmethod
from typing import Callable, Dict, Optional, Union

from shared.exceptions import InvalidFieldValueError


class PitchUnit(ABC):
    """Interfaccia: traduce un valore nella sua unità in ratio di frequenza."""

    @abstractmethod
    def to_ratio(self, value: float) -> float:
        """Converte value (nell'unità) in ratio di frequenza."""


class EdoUnit(PitchUnit):
    """Equal Division of the Octave: ratio = 2^(value / divisions)."""

    def __init__(self, divisions: int):
        if not isinstance(divisions, int) or isinstance(divisions, bool) or divisions <= 0:
            raise InvalidFieldValueError(
                field='edo',
                value=divisions,
                hint="le divisioni per ottava devono essere un intero > 0 (es. 12, 24, 31).",
            )
        self.divisions = divisions

    def to_ratio(self, value: float) -> float:
        return 2 ** (value / self.divisions)


class RatioUnit(PitchUnit):
    """Moltiplicatore diretto: ratio = value."""

    def to_ratio(self, value: float) -> float:
        return value


# =============================================================================
# FACTORY
# =============================================================================

# Preset nominali: alias con N fisso (più RatioUnit).
PITCH_UNIT_PRESETS: Dict[str, Callable[[], PitchUnit]] = {
    'semitones':    lambda: EdoUnit(12),
    'cents':        lambda: EdoUnit(1200),
    'quarter_tone': lambda: EdoUnit(24),
    'eighth_tone':  lambda: EdoUnit(48),
    'ratio':        lambda: RatioUnit(),
}


def make_pitch_unit(spec: Optional[Union[str, dict]] = None) -> PitchUnit:
    """
    Costruisce una PitchUnit dalla specifica YAML.

    Args:
        spec: preset stringa (PITCH_UNIT_PRESETS), mapping {'edo': N},
              oppure None → semitoni (default retrocompatibile).

    Returns:
        PitchUnit
    """
    if spec is None:
        return EdoUnit(12)
    if isinstance(spec, str):
        factory = PITCH_UNIT_PRESETS.get(spec)
        if factory is None:
            raise InvalidFieldValueError(
                field='unit',
                value=spec,
                hint=f"unità disponibili: {sorted(PITCH_UNIT_PRESETS)} oppure {{edo: N}}",
            )
        return factory()
    if isinstance(spec, dict) and set(spec) == {'edo'}:
        return EdoUnit(spec['edo'])
    raise InvalidFieldValueError(
        field='unit',
        value=spec,
        hint=f"unità disponibili: {sorted(PITCH_UNIT_PRESETS)} oppure {{edo: N}}",
    )
