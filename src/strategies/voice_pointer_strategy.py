# src/strategies/voice_pointer_strategy.py
"""
voice_pointer_strategy.py

Strategy pattern per la distribuzione della posizione di lettura (pointer)
delle voci nella sintesi granulare multi-voice.

Responsabilità:
- Calcolare l'offset di pointer (normalizzato 0.0-1.0) per una voce data al tempo t.
- Voce 0 restituisce sempre 0.0 (riferimento immutato).
- Il valore è additivo con il pointer base di PointerController e il grain
  jitter già esistente (mod_range). Vedere pointer_controller.py.

Layering pointer (da design doc):
  pointer_final = base_pointer(t)        # PointerController
               + voice_pointer_offset    # VoicePointerStrategy  ← qui
               + grain_jitter(t)         # mod_range per-grano

Design:
- VoicePointerStrategy (ABC): interfaccia comune
- LinearPointerStrategy: voce i = i × step (offset regolare)
- StochasticPointerStrategy: offset fisso per voce, seed deterministico
- VOICE_POINTER_STRATEGIES: registry globale {nome: classe}
- register_voice_pointer_strategy(): estensibilità dinamica
- VoicePointerStrategyFactory: factory con create() statico

Coerente con: voice_pitch_strategy.py, voice_onset_strategy.py
"""

import random
from abc import ABC, abstractmethod
from typing import Dict, Type

from parameters.parameter import resolve_param, StrategyParam


# =============================================================================
# ABSTRACT BASE CLASS
# =============================================================================

class VoicePointerStrategy(ABC):
    """
    Strategy astratta per la distribuzione del pointer delle voci.

    Il valore restituito è un offset normalizzato (tipicamente in [-1.0, 1.0])
    rispetto alla posizione di lettura base dello stream.
    Voce 0 restituisce sempre 0.0.
    """

    @abstractmethod
    def get_pointer_offset(self, voice_index: int, num_voices: int, time: float) -> float:
        """
        Calcola l'offset di pointer per la voce data al tempo dato.

        Args:
            voice_index: indice della voce (0-based). Voce 0 = riferimento.
            num_voices: numero totale di voci attive.
            time: tempo corrente in secondi (onset del grain).

        Returns:
            Offset normalizzato (float). Voce 0 → sempre 0.0.
        """
        pass


# =============================================================================
# CONCRETE STRATEGIES
# =============================================================================

class LinearPointerStrategy(VoicePointerStrategy):
    """
    Offset lineare uniforme tra voci.

    Voce i → i × step(t).
    Esempio: step=0.1, 4 voci → [0.0, 0.1, 0.2, 0.3]
    Crea un effetto di lettura da posizioni equidistanti nel sample.
    Step negativo → le voci leggono indietro rispetto alla voce 0.
    """

    def __init__(self, step: StrategyParam):
        self.step = step

    def get_pointer_offset(self, voice_index: int, num_voices: int, time: float) -> float:
        if voice_index == 0:
            return 0.0
        return float(voice_index) * resolve_param(self.step, time)


class StochasticPointerStrategy(VoicePointerStrategy):
    """
    Offset per voce con seed deterministico; la magnitudine può variare nel
    tempo se pointer_range è un Envelope.

    Seed = hash(stream_id + str(voice_index)) — riproducibile tra sessioni.
    _cache[voice_index] memorizza il fattore normalizzato in [-1, 1].
    Offset = _cache[vi] * pointer_range(t).
    Voce 0 → sempre 0.0.

    Utile per "thickening": ogni voce legge da una posizione leggermente
    diversa nel sample, creando variazione timbrica senza pattern regolari.
    """

    def __init__(self, pointer_range: StrategyParam, stream_id: str):
        self.pointer_range = pointer_range
        self.stream_id = stream_id
        self._cache: Dict[int, float] = {}

    def get_pointer_offset(self, voice_index: int, num_voices: int, time: float) -> float:
        resolved = resolve_param(self.pointer_range, time)
        if voice_index == 0 or resolved == 0.0:
            return 0.0
        if voice_index not in self._cache:
            seed = hash(self.stream_id + str(voice_index))
            rng = random.Random(seed)
            self._cache[voice_index] = rng.uniform(-1.0, 1.0)
        return self._cache[voice_index] * resolved


# =============================================================================
# REGISTRY
# =============================================================================

VOICE_POINTER_STRATEGIES: Dict[str, Type[VoicePointerStrategy]] = {
    'linear':      LinearPointerStrategy,
    'stochastic':  StochasticPointerStrategy,
}


def register_voice_pointer_strategy(name: str, cls: Type[VoicePointerStrategy]) -> None:
    """
    Registra dinamicamente una nuova VoicePointerStrategy.

    Args:
        name: chiave stringa per il registry
        cls: classe che implementa VoicePointerStrategy
    """
    VOICE_POINTER_STRATEGIES[name] = cls


# =============================================================================
# FACTORY
# =============================================================================

class VoicePointerStrategyFactory:
    """
    Factory per la creazione di VoicePointerStrategy da nome stringa.

    Esempio:
        s = VoicePointerStrategyFactory.create('linear', step=0.05)
        s = VoicePointerStrategyFactory.create('stochastic', pointer_range=0.2, stream_id='s1')
    """

    @staticmethod
    def create(name: str, **kwargs) -> VoicePointerStrategy:
        """
        Crea una VoicePointerStrategy dal nome registrato.

        Args:
            name: nome della strategy nel registry
            **kwargs: parametri passati al costruttore della strategy

        Returns:
            Istanza di VoicePointerStrategy

        Raises:
            KeyError: se il nome non è nel registry
        """
        if name not in VOICE_POINTER_STRATEGIES:
            raise KeyError(
                f"VoicePointerStrategy '{name}' non trovata. "
                f"Disponibili: {sorted(VOICE_POINTER_STRATEGIES.keys())}"
            )
        return VOICE_POINTER_STRATEGIES[name](**kwargs)
