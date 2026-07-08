"""
probability_gate.py - Pattern Gateway per la gestione delle probabilità.
Isola completamente la logica di dephase da Parameter e ParameterFactory.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Union
import random
from pge.envelopes.envelope import Envelope

class ProbabilityGate(ABC):
    """
    Gateway pattern: interfaccia unificata per gate probabilistici.
    """
    
    @abstractmethod
    def should_apply(self, time: float) -> bool:
        """Decide se applicare una variazione al tempo specificato."""
        pass
    
    @abstractmethod
    def get_probability_value(self, time: float) -> float:
        """Restituisce il valore di probabilità corrente (0-100)."""
        pass
    
    @property
    @abstractmethod
    def mode(self) -> str:
        """Tipo di gate ('never', 'always', 'random', 'envelope')."""
        pass


class NeverGate(ProbabilityGate):
    """Gate che NON applica mai variazione."""
    
    def should_apply(self, time: float) -> bool:
        return False
    
    def get_probability_value(self, time: float) -> float:
        return 0.0
    
    @property
    def mode(self) -> str:
        return "never"


class AlwaysGate(ProbabilityGate):
    """Gate che applica SEMPRE variazione (100%)."""
    
    def should_apply(self, time: float) -> bool:
        return True
    
    def get_probability_value(self, time: float) -> float:
        return 100.0
    
    @property
    def mode(self) -> str:
        return "always"


class RandomGate(ProbabilityGate):
    """Gate con probabilità costante.

    RNG locale (issue #154): `rng` iniettato isola i draw del gate dagli
    altri componenti; None → modulo random globale (legacy).
    """

    def __init__(self, probability: float, rng=None):
        self._probability = min(100.0, max(0.0, probability))
        self._rng = rng if rng is not None else random

    def should_apply(self, time: float) -> bool:
        return self._rng.uniform(0, 100) < self._probability
    
    def get_probability_value(self, time: float) -> float:
        return self._probability

    @property
    def probability(self) -> float:
        """Probabilità costante (0-100). Esposta per la visualizzazione."""
        return self._probability

    @property
    def mode(self) -> str:
        return f"random({self._probability}%)"


class EnvelopeGate(ProbabilityGate):
    """Gate con probabilità variabile nel tempo (envelope).

    RNG locale (issue #154): `rng` iniettato isola i draw del gate dagli
    altri componenti; None → modulo random globale (legacy).
    """

    def __init__(self, envelope: Envelope, rng=None):
        self._envelope = envelope
        self._rng = rng if rng is not None else random

    def should_apply(self, time: float) -> bool:
        prob = self._envelope.evaluate(time)
        return self._rng.uniform(0, 100) < prob
    
    def get_probability_value(self, time: float) -> float:
        return self._envelope.evaluate(time)

    @property
    def envelope(self) -> Envelope:
        """Envelope di probabilità nel tempo. Esposta per la visualizzazione."""
        return self._envelope

    @property
    def mode(self) -> str:
        return f"envelope({self._envelope.type})"
