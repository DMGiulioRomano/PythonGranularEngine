# src/strategies/voice_pitch_strategy.py
"""
voice_pitch_strategy.py

Strategy pattern per la distribuzione di pitch (altezza) delle voci
nella sintesi granulare multi-voice.

Responsabilità:
- Calcolare il FATTORE DI RATIO di pitch per una voce data al tempo t.
- La geometria vive nell'unità (PitchUnit): le strategy "scalate"
  (step/range/stochastic) emettono una posizione adimensionale e chiedono
  all'unità di materializzarla (`unit.materialize(position, amount)`); quelle
  "assolute" (chord/spectral) emettono un offset in semitoni e usano
  `unit.to_ratio` (valido solo con unità semitones, vedi SEMITONE_LOCKED).
- Voce 0 restituisce sempre 1.0 (riferimento immutato = ratio identità).
- NON gestisce la variazione per-grano (responsabilità di PitchController + mod_range).

Design:
- VoicePitchStrategy (ABC): interfaccia comune
- StepPitchStrategy: voce i = i × step
- RangePitchStrategy: distribuiti linearmente in [0, pitch_range]
- ChordPitchStrategy: offsets da nome accordo, extend all'ottava se num_voices > chord
- StochasticPitchStrategy: offset fisso per voce (stabile entro un run)
- VOICE_PITCH_STRATEGIES: registry globale {nome: classe}
- register_voice_pitch_strategy(): estensibilità dinamica
- VoicePitchStrategyFactory: factory con create() statico

Coerente con: voice_pan_strategy.py, variation_strategy.py
"""

import math
import random
from abc import ABC, abstractmethod
from typing import Dict, List, Type

from shared.exceptions import (
    InvalidStrategyConfigError,
    StrategyNotFoundError,
)

from parameters.parameter import resolve_param, StrategyParam


# =============================================================================
# CHORD DEFINITIONS
# =============================================================================

CHORD_INTERVALS: Dict[str, List[int]] = {
    # --- 3 voci ---
    'maj':     [0, 4, 7],
    'min':     [0, 3, 7],
    'dim':     [0, 3, 6],
    'aug':     [0, 4, 8],
    'sus2':    [0, 2, 7],
    'sus4':    [0, 5, 7],
    # --- 4 voci ---
    'dom7':    [0, 4, 7, 10],
    'maj7':    [0, 4, 7, 11],
    'min7':    [0, 3, 7, 10],
    'dim7':    [0, 3, 6,  9],
    'minmaj7': [0, 3, 7, 11],
    # --- 5 voci ---
    'dom9':    [0, 4, 7, 10, 14],
    'maj9':    [0, 4, 7, 11, 14],
    'min9':    [0, 3, 7, 10, 14],
    '9sus4':   [0, 5, 7, 10, 14],
    # --- 6 voci ---
    'dom9s11': [0, 4, 7, 10, 14, 18],
    'maj9s11': [0, 4, 7, 11, 14, 18],
    'min11':   [0, 3, 7, 10, 14, 17],
    # --- 7 voci ---
    'dom13':   [0,  4,  7, 10, 14, 17, 21],
    'min13':   [0,  3,  7, 10, 14, 17, 21],
    'maj13s11':[0,  4,  7, 11, 14, 18, 21],
    'altered': [0,  4,  7, 10, 13, 15, 20],
}


# =============================================================================
# ABSTRACT BASE CLASS
# =============================================================================

class VoicePitchStrategy(ABC):
    """
    Strategy astratta per la distribuzione di pitch delle voci.

    Il valore restituito è un FATTORE DI RATIO rispetto al pitch base
    dello stream, prodotto tramite la PitchUnit attiva. Voce 0 → sempre 1.0.
    """

    @abstractmethod
    def get_pitch_factor(
        self, voice_index: int, num_voices: int, time: float, unit: 'PitchUnit'
    ) -> float:
        """
        Calcola il fattore di ratio per la voce data al tempo dato.

        Args:
            voice_index: indice della voce (0-based). Voce 0 = riferimento.
            num_voices: numero totale di voci attive.
            time: tempo corrente in secondi (onset del grain).
            unit: PitchUnit attiva — possiede la geometria (materialize/to_ratio).

        Returns:
            Fattore di ratio (float) da moltiplicare sul ratio base.
            Voce 0 → sempre 1.0 (identità).
        """
        pass


# =============================================================================
# CONCRETE STRATEGIES
# =============================================================================

class StepPitchStrategy(VoicePitchStrategy):
    """
    Distribuzione per step fisso o dinamico.

    Posizione voce i = i, ampiezza = step(t). L'unità materializza:
    EDO → 0, step, 2·step, … semitoni; ratio → step^i (geometrico).
    Esempio (semitones): step=3, 4 voci → [0, 3, 6, 9] semitoni.
    """

    def __init__(self, step: StrategyParam):
        self.step = step

    def get_pitch_factor(self, voice_index, num_voices, time, unit):
        if voice_index == 0:
            return 1.0
        return unit.materialize(float(voice_index), resolve_param(self.step, time))


class RangePitchStrategy(VoicePitchStrategy):
    """
    Distribuzione nell'intervallo [identità, pitch_range(t)].

    Posizione voce i = i/(num_voices-1) ∈ [0,1], ampiezza = pitch_range(t).
    EDO → equidistante in semitoni [0..range]; ratio → geometrica [1..range].
    Esempio (semitones): pitch_range=12, 4 voci → [0, 4, 8, 12] semitoni.
    Con num_voices=1 → solo identità.
    """

    def __init__(self, pitch_range: StrategyParam):
        self.pitch_range = pitch_range

    def get_pitch_factor(self, voice_index, num_voices, time, unit):
        if voice_index == 0 or num_voices <= 1:
            return 1.0
        position = float(voice_index) / (num_voices - 1)
        return unit.materialize(position, resolve_param(self.pitch_range, time))


class ChordPitchStrategy(VoicePitchStrategy):
    """
    Offsets da nome accordo nominale.

    Gli intervalli sono presi da CHORD_INTERVALS. Se num_voices > len(chord),
    le voci eccedenti continuano il pattern all'ottava superiore (extend).

    Extend policy: voce i → intervals[i % n] + (i // n) * 12
    dove n = len(chord_intervals).

    Esempio: dom7=[0,4,7,10], 6 voci → [0, 4, 7, 10, 12, 16]

    Il parametro `inversion` ruota gli intervalli dell'accordo in modo che
    il grado k diventi la voce più bassa (normalizzata a 0):
      inversion=0 → root position (default)
      inversion=1 → primo rivolto (terza al basso)
      ...

    L'extend policy funziona invariata sugli intervalli invertiti.
    Il parametro `time` è accettato ma ignorato (nessun param time-varying).
    """

    def __init__(self, chord: str, inversion: int = 0):
        if chord not in CHORD_INTERVALS:
            raise InvalidStrategyConfigError(
                strategy_kind="voice_pitch",
                field="chord",
                value=chord,
                hint=f"accordi disponibili: {sorted(CHORD_INTERVALS.keys())}",
            )
        base_intervals = CHORD_INTERVALS[chord]
        n = len(base_intervals)
        if not (0 <= inversion < n):
            raise InvalidStrategyConfigError(
                strategy_kind="voice_pitch",
                field="inversion",
                value=inversion,
                hint=(
                    f"accordo '{chord}' ha {n} note: inversion deve essere "
                    f"in [0, {n - 1}]"
                ),
            )
        self.chord = chord
        self.inversion = inversion
        self._intervals = self._invert(base_intervals, inversion)

    @staticmethod
    def _invert(intervals: List[int], k: int) -> List[int]:
        rotated = intervals[k:] + [x + 12 for x in intervals[:k]]
        base = rotated[0]
        return [x - base for x in rotated]

    def get_pitch_factor(self, voice_index, num_voices, time, unit):
        if voice_index == 0:
            return 1.0
        n = len(self._intervals)
        octave = voice_index // n
        interval_idx = voice_index % n
        semitones = float(self._intervals[interval_idx] + octave * 12)
        return unit.to_ratio(semitones)


class StochasticPitchStrategy(VoicePitchStrategy):
    """
    Offset fisso per voce entro un singolo run; la direzione è fissa, la magnitudine
    può variare nel tempo se pitch_range è un Envelope.

    Seed = hash(stream_id + str(voice_index)): stabile ENTRO un run, NON
    riproducibile fra processi diversi. hash() su stringa è randomizzato
    per-processo (PYTHONHASHSEED non è fissato in questo repo), quindi l'offset
    cambia a ogni avvio. Ciò che si conserva fra run è l'andamento, non il valore.
    _cache[voice_index] memorizza la posizione normalizzata in [-1, 1].
    Fattore = unit.materialize(position, pitch_range(t)): EDO → ± attorno a 0
    in semitoni; ratio → simmetrico geometrico (es. range=2 → [0.5, 2]).
    Voce 0 (e range 0) → sempre 1.0 (identità).
    """

    def __init__(self, pitch_range: StrategyParam, stream_id: str):
        self.pitch_range = pitch_range
        self.stream_id = stream_id
        self._cache: Dict[int, float] = {}

    def get_pitch_factor(self, voice_index, num_voices, time, unit):
        resolved = resolve_param(self.pitch_range, time)
        if voice_index == 0 or resolved == 0.0:
            return 1.0
        if voice_index not in self._cache:
            seed = hash(self.stream_id + str(voice_index))
            rng = random.Random(seed)
            self._cache[voice_index] = rng.uniform(-1.0, 1.0)
        return unit.materialize(self._cache[voice_index], resolved)


class SpectralPitchStrategy(VoicePitchStrategy):
    """
    Distribuzione voci sui parziali della serie armonica naturale.

    Voce i → parziale (i+1) → round(12 * log2(i+1)) semitoni.
    Voce 0 → fondamentale → 0 semitoni (invariante ABC).

    Serie [0, 12, 19, 24, 28, 31, 34, 36, ...] per le prime 8 voci.

    Args:
        max_partial: numero di parziali pre-calcolati al __init__ (default 16).
                     Voci oltre max_partial sono calcolate on-demand.

    Il parametro `time` è accettato ma ignorato (nessun param time-varying).
    """

    def __init__(self, max_partial: int = 16):
        self.max_partial = max_partial
        self._offsets: List[float] = [
            float(round(12 * math.log2(i + 1))) for i in range(max_partial)
        ]

    def get_pitch_factor(self, voice_index, num_voices, time, unit):
        if voice_index == 0:
            return 1.0
        while voice_index >= len(self._offsets):
            i = len(self._offsets)
            self._offsets.append(float(round(12 * math.log2(i + 1))))
        return unit.to_ratio(self._offsets[voice_index])


# =============================================================================
# REGISTRY
# =============================================================================

VOICE_PITCH_STRATEGIES: Dict[str, Type[VoicePitchStrategy]] = {
    'step':        StepPitchStrategy,
    'range':       RangePitchStrategy,
    'chord':       ChordPitchStrategy,
    'stochastic':  StochasticPitchStrategy,
    'spectral':    SpectralPitchStrategy,
}

# Strategie i cui offset sono intrinsecamente in semitoni (interi da
# CHORD_INTERVALS / 12*log2): in v1 accettano solo l'unità `semitones`.
# Singola fonte di verità per la validazione in Stream._init_voice_manager.
SEMITONE_LOCKED = frozenset({'chord', 'spectral'})


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
            raise StrategyNotFoundError(
                strategy_kind="voice_pitch",
                name=name,
                available=list(VOICE_PITCH_STRATEGIES.keys()),
            )
        return VOICE_PITCH_STRATEGIES[name](**kwargs)
