# src/strategies/voice_pointer_strategy.py
"""
voice_pointer_strategy.py

Strategy pattern per la distribuzione della posizione di lettura (pointer)
delle voci nella sintesi granulare multi-voice.

Responsabilità:
- Calcolare l'offset di pointer (normalizzato 0.0-1.0) per una voce data.
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
    def get_pointer_offset(self, voice_index: int, num_voices: int) -> float:
        """
        Calcola l'offset di pointer per la voce data.

        Args:
            voice_index: indice della voce (0-based). Voce 0 = riferimento.
            num_voices: numero totale di voci attive.

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

    Voce i → i × step.
    Esempio: step=0.1, 4 voci → [0.0, 0.1, 0.2, 0.3]
    Crea un effetto di lettura da posizioni equidistanti nel sample.
    Step negativo → le voci leggono indietro rispetto alla voce 0.
    """

    def __init__(self, step: float):
        self.step = step

    def get_pointer_offset(self, voice_index: int, num_voices: int) -> float:
        if voice_index == 0:
            return 0.0
        return float(voice_index * self.step)


class StochasticPointerStrategy(VoicePointerStrategy):
    """
    Offset fisso per voce, calcolato una volta con seed deterministico.

    Seed = hash(stream_id + str(voice_index)) — riproducibile tra sessioni.
    L'offset è uniforme in [-pointer_range, +pointer_range].
    Voce 0 → sempre 0.0.

    Utile per "thickening": ogni voce legge da una posizione leggermente
    diversa nel sample, creando variazione timbrica senza pattern regolari.
    """

    def __init__(self, pointer_range: float, stream_id: str):
        self.pointer_range = pointer_range
        self.stream_id = stream_id
        self._cache: Dict[int, float] = {}

    def get_pointer_offset(self, voice_index: int, num_voices: int) -> float:
        if voice_index == 0 or self.pointer_range == 0.0:
            return 0.0
        if voice_index not in self._cache:
            seed = hash(self.stream_id + str(voice_index))
            rng = random.Random(seed)
            self._cache[voice_index] = rng.uniform(
                -self.pointer_range, self.pointer_range
            )
        return self._cache[voice_index]


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
