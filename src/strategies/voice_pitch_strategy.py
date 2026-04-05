# src/strategies/voice_pitch_strategy.py
"""
voice_pitch_strategy.py

Strategy pattern per la distribuzione di pitch (altezza) delle voci
nella sintesi granulare multi-voice.

Responsabilità:
- Calcolare l'offset di pitch in SEMITONI per una voce data.
- Voce 0 restituisce sempre 0.0 (riferimento immutato).
- NON gestisce la variazione per-grano (responsabilità di PitchController + mod_range).

Design:
- VoicePitchStrategy (ABC): interfaccia comune
- StepPitchStrategy: voce i = i × step
- RangePitchStrategy: distribuiti linearmente in [0, semitone_range]
- ChordPitchStrategy: offsets da nome accordo, extend all'ottava se num_voices > chord
- StochasticPitchStrategy: offset fisso per voce, seed deterministico
- VOICE_PITCH_STRATEGIES: registry globale {nome: classe}
- register_voice_pitch_strategy(): estensibilità dinamica
- VoicePitchStrategyFactory: factory con create() statico

Coerente con: voice_pan_strategy.py, variation_strategy.py
"""

import random
from abc import ABC, abstractmethod
from typing import Dict, List, Type


# =============================================================================
# CHORD DEFINITIONS
# =============================================================================

CHORD_INTERVALS: Dict[str, List[int]] = {
    'maj':   [0, 4, 7],
    'min':   [0, 3, 7],
    'dom7':  [0, 4, 7, 10],
    'maj7':  [0, 4, 7, 11],
    'min7':  [0, 3, 7, 10],
    'dim':   [0, 3, 6],
    'aug':   [0, 4, 8],
    'sus2':  [0, 2, 7],
    'sus4':  [0, 5, 7],
    'dim7':  [0, 3, 6, 9],
    'minmaj7': [0, 3, 7, 11],
}


# =============================================================================
# ABSTRACT BASE CLASS
# =============================================================================

class VoicePitchStrategy(ABC):
    """
    Strategy astratta per la distribuzione di pitch delle voci.

    Il valore restituito è un offset in SEMITONI rispetto al pitch base
    dello stream. Voce 0 restituisce sempre 0.0.
    """

    @abstractmethod
    def get_pitch_offset(self, voice_index: int, num_voices: int) -> float:
        """
        Calcola l'offset di pitch per la voce data.

        Args:
            voice_index: indice della voce (0-based). Voce 0 = riferimento.
            num_voices: numero totale di voci attive.

        Returns:
            Offset in semitoni (float). Voce 0 → sempre 0.0.
        """
        pass


# =============================================================================
# CONCRETE STRATEGIES
# =============================================================================

class StepPitchStrategy(VoicePitchStrategy):
    """
    Distribuzione lineare per step fisso.

    Voce i → i × step semitoni.
    Esempio: step=3, 4 voci → [0, 3, 6, 9]
    """

    def __init__(self, step: float):
        self.step = step

    def get_pitch_offset(self, voice_index: int, num_voices: int) -> float:
        if voice_index == 0:
            return 0.0
        return float(voice_index * self.step)


class RangePitchStrategy(VoicePitchStrategy):
    """
    Distribuzione lineare nel range [0, semitone_range].

    Le voci sono distribuite equidistanti nell'intervallo.
    Esempio: range=12, 4 voci → [0, 4, 8, 12]
    Con num_voices=1 → [0].
    """

    def __init__(self, semitone_range: float):
        self.semitone_range = semitone_range

    def get_pitch_offset(self, voice_index: int, num_voices: int) -> float:
        if voice_index == 0 or num_voices <= 1:
            return 0.0
        return float(voice_index * self.semitone_range / (num_voices - 1))


class ChordPitchStrategy(VoicePitchStrategy):
    """
    Offsets da nome accordo nominale.

    Gli intervalli sono presi da CHORD_INTERVALS. Se num_voices > len(chord),
    le voci eccedenti continuano il pattern all'ottava superiore (extend).

    Extend policy: voce i → intervals[i % n] + (i // n) * 12
    dove n = len(chord_intervals).

    Esempio: dom7=[0,4,7,10], 6 voci → [0, 4, 7, 10, 12, 16]
    """

    def __init__(self, chord: str):
        if chord not in CHORD_INTERVALS:
            raise ValueError(
                f"Accordo '{chord}' non riconosciuto. "
                f"Disponibili: {sorted(CHORD_INTERVALS.keys())}"
            )
        self.chord = chord
        self._intervals = CHORD_INTERVALS[chord]

    def get_pitch_offset(self, voice_index: int, num_voices: int) -> float:
        if voice_index == 0:
            return 0.0
        n = len(self._intervals)
        octave = voice_index // n
        interval_idx = voice_index % n
        return float(self._intervals[interval_idx] + octave * 12)


class StochasticPitchStrategy(VoicePitchStrategy):
    """
    Offset fisso per voce, calcolato una volta con seed deterministico.

    Seed = hash(stream_id + str(voice_index)) — riproducibile tra sessioni.
    L'offset è uniforme in [-semitone_range, +semitone_range].
    Voce 0 → sempre 0.0.
    """

    def __init__(self, semitone_range: float, stream_id: str):
        self.semitone_range = semitone_range
        self.stream_id = stream_id
        self._cache: Dict[int, float] = {}

    def get_pitch_offset(self, voice_index: int, num_voices: int) -> float:
        if voice_index == 0 or self.semitone_range == 0.0:
            return 0.0
        if voice_index not in self._cache:
            seed = hash(self.stream_id + str(voice_index))
            rng = random.Random(seed)
            self._cache[voice_index] = rng.uniform(
                -self.semitone_range, self.semitone_range
            )
        return self._cache[voice_index]


# =============================================================================
# REGISTRY
# =============================================================================

VOICE_PITCH_STRATEGIES: Dict[str, Type[VoicePitchStrategy]] = {
    'step':        StepPitchStrategy,
    'range':       RangePitchStrategy,
    'chord':       ChordPitchStrategy,
    'stochastic':  StochasticPitchStrategy,
}


def register_voice_pitch_strategy(name: str, cls: Type[VoicePitchStrategy]) -> None:
    """
    Registra dinamicamente una nuova VoicePitchStrategy.

    Args:
        name: chiave stringa per il registry
        cls: classe che implementa VoicePitchStrategy
    """
    VOICE_PITCH_STRATEGIES[name] = cls


# =============================================================================
# FACTORY
# =============================================================================

class VoicePitchStrategyFactory:
    """
    Factory per la creazione di VoicePitchStrategy da nome stringa.

    Esempio:
        s = VoicePitchStrategyFactory.create('chord', chord='dom7')
        s = VoicePitchStrategyFactory.create('step', step=3.0)
    """

    @staticmethod
    def create(name: str, **kwargs) -> VoicePitchStrategy:
        """
        Crea una VoicePitchStrategy dal nome registrato.

        Args:
            name: nome della strategy nel registry
            **kwargs: parametri passati al costruttore della strategy

        Returns:
            Istanza di VoicePitchStrategy

        Raises:
            KeyError: se il nome non è nel registry
        """
        if name not in VOICE_PITCH_STRATEGIES:
            raise KeyError(
                f"VoicePitchStrategy '{name}' non trovata. "
                f"Disponibili: {sorted(VOICE_PITCH_STRATEGIES.keys())}"
            )
        return VOICE_PITCH_STRATEGIES[name](**kwargs)
