# variation_strategy.py
from __future__ import annotations

from abc import ABC, abstractmethod
from shared.distribution_strategy import DistributionStrategy
from shared.exceptions import InvalidParameterError
from typing import Any

class VariationStrategy(ABC):
    """Strategia di applicazione randomness a un valore base."""
    
    @abstractmethod
    def apply(self, base: float, mod_range: float, 
              distribution: DistributionStrategy) -> float:
        """Applica variazione al valore base."""
        pass

class AdditiveVariation(VariationStrategy):
    def apply(self, base: float, mod_range: float, 
              distribution: DistributionStrategy) -> float:
        return distribution.sample(base, mod_range) if mod_range > 0 else base

class QuantizedVariation(VariationStrategy):
    def apply(self, base: float, mod_range: float, 
              distribution: DistributionStrategy) -> float:
        if mod_range >= 1.0:
            raw_sample = distribution.sample(0.0, mod_range)
            return base + round(raw_sample)
        return base

class InvertVariation(VariationStrategy):
    def apply(self, base: float, mod_range: float, 
              distribution: DistributionStrategy) -> float:
        return 1.0 - base
    
class ChoiceVariation(VariationStrategy):
    """
    Selezione casuale da lista discreta.
    Usato per envelope, samples, preset values.
    
    Supporta due modalità:
    1. Lista esplicita: ['hanning', 'hamming', 'gaussian']
    2. Range=True: espande a tutte le finestre disponibili
    """
    
    def apply(self, value: Any, mod_range: float, 
              distribution: DistributionStrategy) -> Any:
        """
        Args:
            value: può essere:
                   - stringa singola: 'hanning' → nessuna variazione
                   - lista: ['hanning', 'hamming'] → choice da lista
                   - True: espande a tutte le finestre da WindowRegistry
            mod_range: se > 0, abilita la variazione (altrimenti ritorna primo elemento)
        
        Returns:
            elemento scelto dalla lista
        """
        # Caso 1: Valore singolo (stringa) → comportamento deterministico
        if isinstance(value, str):
            return value
        
        # Caso 2: Range=True → espandi a tutte le finestre
        if value is True or (isinstance(value, str) and value.lower() == 'all'):
            from window_registry import WindowRegistry
            value = list(WindowRegistry.WINDOWS.keys())
        
        # Caso 3: Lista esplicita
        if not isinstance(value, list):
            raise InvalidParameterError(
                param_name="ChoiceVariation",
                value=value,
                hint="richiede stringa, lista, o True",
            )
        
        # Se mod_range == 0, non variare (usa primo elemento come default)
        if mod_range == 0:
            return value[0] if value else 'hanning'
        
        # Altrimenti, scelta random dall'RNG per-componente della distribuzione
        # (issue #154): la selezione rientra nel seeding per (seed, stream_id,
        # componente) invece di pescare dal random globale condiviso.
        return distribution.rng.choice(value)
