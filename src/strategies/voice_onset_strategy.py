# src/strategies/voice_onset_strategy.py
"""
voice_onset_strategy.py

Strategy pattern per la distribuzione temporale (onset offset) delle voci
nella sintesi granulare multi-voice.

Responsabilità:
- Calcolare l'offset di onset in SECONDI per una voce data al tempo t.
- Voce 0 restituisce sempre 0.0 (riferimento immutato).
- L'offset è additivo rispetto all'onset base dello stream.
- Gli offset sono sempre >= 0: le voci seguono nel tempo, non precedono.

Design:
- VoiceOnsetStrategy (ABC): interfaccia comune
- LinearOnsetStrategy: voce i = i × step
- GeometricOnsetStrategy: spaziatura esponenziale step * base^(i-1)
- StochasticOnsetStrategy: offset fisso per voce, seed deterministico, in [0, max_offset]
- VOICE_ONSET_STRATEGIES: registry globale {nome: classe}
- register_voice_onset_strategy(): estensibilità dinamica
- VoiceOnsetStrategyFactory: factory con create() statico

Coerente con: voice_pitch_strategy.py, voice_pan_strategy.py
"""

import random
from abc import ABC, abstractmethod
from typing import Dict, Type

from parameters.parameter import resolve_param, StrategyParam


# =============================================================================
# ABSTRACT BASE CLASS
# =============================================================================

class VoiceOnsetStrategy(ABC):
    """
    Strategy astratta per la distribuzione temporale delle voci.

    Il valore restituito è un offset in SECONDI rispetto all'onset base
    dello stream. Voce 0 restituisce sempre 0.0.
    """

    @abstractmethod
    def get_onset_offset(self, voice_index: int, num_voices: int, time: float) -> float:
        """
        Calcola l'offset di onset per la voce data al tempo dato.

        Args:
            voice_index: indice della voce (0-based). Voce 0 = riferimento.
            num_voices: numero totale di voci attive.
            time: tempo corrente in secondi (onset del grain).

        Returns:
            Offset in secondi (float >= 0.0). Voce 0 → sempre 0.0.
        """
        pass


# =============================================================================
# CONCRETE STRATEGIES
# =============================================================================

class LinearOnsetStrategy(VoiceOnsetStrategy):
    """
    Spaziatura lineare uniforme tra voci.

    Voce i → i × step(t) secondi.
    Esempio: step=0.05, 4 voci → [0.0, 0.05, 0.10, 0.15]
    Crea un effetto di phasing regolare (Truax-style).
    """

    def __init__(self, step: StrategyParam):
        self.step = step

    def get_onset_offset(self, voice_index: int, num_voices: int, time: float) -> float:
        if voice_index == 0:
            return 0.0
        return float(voice_index) * resolve_param(self.step, time)


class GeometricOnsetStrategy(VoiceOnsetStrategy):
    """
    Spaziatura esponenziale tra voci.

    Voce 1 → step(t)
    Voce 2 → step(t) × base(t)
    Voce 3 → step(t) × base(t)²
    Voce i → step(t) × base(t)^(i-1)

    Con base > 1: le voci più lontane hanno offset sempre più grandi.
    Con base = 1: equivale a LinearOnsetStrategy con step fisso per tutte le voci.
    """

    def __init__(self, step: StrategyParam, base: StrategyParam):
        self.step = step
        self.base = base

    def get_onset_offset(self, voice_index: int, num_voices: int, time: float) -> float:
        if voice_index == 0:
            return 0.0
        return float(resolve_param(self.step, time) * (resolve_param(self.base, time) ** (voice_index - 1)))


class StochasticOnsetStrategy(VoiceOnsetStrategy):
    """
    Offset per voce con seed deterministico; la magnitudine può variare nel
    tempo se max_offset è un Envelope.

    Seed = hash(stream_id + str(voice_index)) — riproducibile tra sessioni.
    _cache[voice_index] memorizza il fattore normalizzato in [0, 1].
    Offset = _cache[vi] * max_offset(t).
    Voce 0 → sempre 0.0.
    """

    def __init__(self, max_offset: StrategyParam, stream_id: str):
        self.max_offset = max_offset
        self.stream_id = stream_id
        self._cache: Dict[int, float] = {}

    def get_onset_offset(self, voice_index: int, num_voices: int, time: float) -> float:
        resolved = resolve_param(self.max_offset, time)
        if voice_index == 0 or resolved == 0.0:
            return 0.0
        if voice_index not in self._cache:
            seed = hash(self.stream_id + str(voice_index))
            rng = random.Random(seed)
            self._cache[voice_index] = rng.uniform(0.0, 1.0)
        return self._cache[voice_index] * resolved


# =============================================================================
# REGISTRY
# =============================================================================

VOICE_ONSET_STRATEGIES: Dict[str, Type[VoiceOnsetStrategy]] = {
    'linear':      LinearOnsetStrategy,
    'geometric':   GeometricOnsetStrategy,
    'stochastic':  StochasticOnsetStrategy,
}


def register_voice_onset_strategy(name: str, cls: Type[VoiceOnsetStrategy]) -> None:
    """
    Registra dinamicamente una nuova VoiceOnsetStrategy.

    Args:
        name: chiave stringa per il registry
        cls: classe che implementa VoiceOnsetStrategy
    """
    VOICE_ONSET_STRATEGIES[name] = cls


# =============================================================================
# FACTORY
# =============================================================================

class VoiceOnsetStrategyFactory:
    """
    Factory per la creazione di VoiceOnsetStrategy da nome stringa.

    Esempio:
        s = VoiceOnsetStrategyFactory.create('linear', step=0.05)
        s = VoiceOnsetStrategyFactory.create('geometric', step=0.05, base=2.0)
        s = VoiceOnsetStrategyFactory.create('stochastic', max_offset=0.1, stream_id='s1')
    """

    @staticmethod
    def create(name: str, **kwargs) -> VoiceOnsetStrategy:
        """
        Crea una VoiceOnsetStrategy dal nome registrato.

        Args:
            name: nome della strategy nel registry
            **kwargs: parametri passati al costruttore della strategy

        Returns:
            Istanza di VoiceOnsetStrategy

        Raises:
            KeyError: se il nome non è nel registry
        """
        if name not in VOICE_ONSET_STRATEGIES:
            raise KeyError(
                f"VoiceOnsetStrategy '{name}' non trovata. "
                f"Disponibili: {sorted(VOICE_ONSET_STRATEGIES.keys())}"
            )
        return VOICE_ONSET_STRATEGIES[name](**kwargs)
