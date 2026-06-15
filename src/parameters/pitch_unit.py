# src/parameters/pitch_unit.py
"""
pitch_unit.py

Astrazione delle unità di misura del pitch: converte un valore espresso in una
data unità nel ratio di frequenza corrispondente.

L'unità è la singola fonte di verità per il pitch: oltre alla conversione,
conosce il proprio valore neutro (`identity_value`), i propri bounds di
sicurezza (`value_bounds`) e la propria etichetta (`name`/`symbol`). Riusata
in entrambi i contesti — pitch base/per-grano e pitch delle voci.

Famiglia esponenziale (Equal Division of the Octave):
    ratio = 2^(value / divisions)
    semitones=12, quarter_tone=24, eighth_tone=48, cents=1200, edo:N=N
Famiglia moltiplicativa:
    ratio = value (RatioUnit)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Dict, Optional, Union

from parameters.parameter_definitions import ParameterBounds
from shared.exceptions import InvalidFieldValueError

# Detune implicito del dephase per le unità EDO (issue #95): semi-ampiezza in
# cents (±N) del micro-detune continuo applicato in ratio-space da
# UnitPitchStrategy quando il pitch è sotto dephase senza range esplicito.
# Non può vivere in default_jitter: il value-space EDO è quantizzato e un
# jitter sub-grado arrotonderebbe a 0 (no-op), un grado intero sarebbe una
# trasposizione piena.
EDO_IMPLICIT_DETUNE_CENTS = 12.0


class PitchUnit(ABC):
    """
    Interfaccia: traduce un valore nella sua unità in ratio di frequenza.

    Espone inoltre (attributi di istanza, valorizzati dalle sottoclassi):
        name:   identità testuale dell'unità (es. 'semitones', 'cents', 'edo').
        symbol: etichetta breve per la visualizzazione (es. 'st', 'c', 'edo31').
    """

    name: str
    symbol: str

    # Semi-ampiezza (±N cents) del detune implicito in ratio-space, campionato
    # continuo per grano da UnitPitchStrategy nel path dephase senza range.
    implicit_detune_cents: float = 0.0

    @abstractmethod
    def to_ratio(self, value: float) -> float:
        """Converte value (nell'unità) in ratio di frequenza."""

    @abstractmethod
    def materialize(self, position: float, amount: float) -> float:
        """Materializza una distribuzione voce in un fattore di ratio.

        `position` è una posizione adimensionale (indice voce, frazione,
        random in [-1,1]); `amount` è l'estensione espressa nell'unità.
        L'unità possiede la geometria: position=0 -> ratio 1.0 (identità)
        per ogni famiglia.
        """

    @abstractmethod
    def identity_value(self) -> float:
        """Valore neutro: quello che produce ratio 1.0 (nessuna trasposizione)."""

    @abstractmethod
    def value_bounds(self) -> ParameterBounds:
        """Bounds di sicurezza del valore espresso in questa unità."""


class EdoUnit(PitchUnit):
    """Equal Division of the Octave: ratio = 2^(value / divisions).

    I bounds del valore sono ±3 ottave, cioè ±(3·divisions), con variazione
    quantizzata (gradi interi). Il valore neutro è 0 (2^0 = 1).
    """

    implicit_detune_cents = EDO_IMPLICIT_DETUNE_CENTS

    def __init__(self, divisions: int, name: str = 'edo', symbol: Optional[str] = None):
        if not isinstance(divisions, int) or isinstance(divisions, bool) or divisions <= 0:
            raise InvalidFieldValueError(
                field='edo',
                value=divisions,
                hint="le divisioni per ottava devono essere un intero > 0 (es. 12, 24, 31).",
            )
        self.divisions = divisions
        self.name = name
        self.symbol = symbol if symbol is not None else f'edo{divisions}'

    def to_ratio(self, value: float) -> float:
        return 2 ** (value / self.divisions)

    def materialize(self, position: float, amount: float) -> float:
        # additiva nel log: equivale a to_ratio(position*amount)
        return 2 ** (position * amount / self.divisions)

    def identity_value(self) -> float:
        return 0.0

    def value_bounds(self) -> ParameterBounds:
        bound = 3.0 * self.divisions
        return ParameterBounds(
            min_val=-bound,
            max_val=bound,
            min_range=0.0,
            max_range=bound,
            default_jitter=0.0,
            variation_mode='quantized',
        )


class RatioUnit(PitchUnit):
    """Moltiplicatore diretto: ratio = value.

    Bounds e variazione del ratio diretto
    ([0.001, 8], variazione additiva continua). Il valore neutro è 1 (×1).
    """

    def __init__(self, name: str = 'ratio', symbol: str = 'x'):
        self.name = name
        self.symbol = symbol

    def to_ratio(self, value: float) -> float:
        return value

    def materialize(self, position: float, amount: float) -> float:
        # geometrica: ogni passo compone moltiplicativamente (amount^position).
        # amount <= 0 → identità (allineato al comportamento EDO con range 0).
        if amount <= 0:
            return 1.0
        return amount ** position

    def identity_value(self) -> float:
        return 1.0

    def value_bounds(self) -> ParameterBounds:
        return ParameterBounds(
            min_val=0.001,
            max_val=8.0,
            min_range=0.0,
            max_range=2.0,
            default_jitter=0.005,
            variation_mode='additive',
        )


# =============================================================================
# FACTORY
# =============================================================================

# Preset nominali: alias EdoUnit con N fisso (più RatioUnit). Ogni preset porta
# il proprio name/symbol; {edo: N} usa il name generico 'edo'.
PITCH_UNIT_PRESETS: Dict[str, Callable[[], PitchUnit]] = {
    'semitones':    lambda: EdoUnit(12, name='semitones', symbol='st'),
    'cents':        lambda: EdoUnit(1200, name='cents', symbol='c'),
    'quarter_tone': lambda: EdoUnit(24, name='quarter_tone', symbol='qt'),
    'eighth_tone':  lambda: EdoUnit(48, name='eighth_tone', symbol='et'),
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
        return PITCH_UNIT_PRESETS['semitones']()
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
