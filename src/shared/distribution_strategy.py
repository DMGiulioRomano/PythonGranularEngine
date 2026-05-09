"""
distribution_strategy.py - Strategy Pattern per distribuzioni statistiche.

Implementa diverse distribuzioni di probabilità per la generazione 
di valori stocastici nei parametri granulari.
"""

import random
from abc import ABC, abstractmethod
from typing import Tuple

from shared.exceptions import (
    InvalidStrategyConfigError,
    StrategyNotFoundError,
)


class DistributionStrategy(ABC):
    """
    Strategy astratta per distribuzioni statistiche.
    
    Ogni strategia implementa un metodo sample() che genera
    un valore random secondo una specifica distribuzione.
    """
    
    @abstractmethod
    def sample(self, center: float, spread: float) -> float:        # pragma: no cover
        """
        Genera un campione dalla distribuzione.
        
        Args:
            center: Valore centrale (media o punto di riferimento)
            spread: Ampiezza della distribuzione (range o deviazione standard)
        
        Returns:
            Valore generato secondo la distribuzione
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:        # pragma: no cover
        """Nome descrittivo della distribuzione."""
        pass
    
    @abstractmethod
    def get_bounds(self, center: float, spread: float) -> Tuple[float, float]:         # pragma: no cover
        """
        Restituisce i bounds teorici della distribuzione.
        
        Utile per documentazione e debugging.
        
        Returns:
            (min_theoretical, max_theoretical)
        """
        pass 


class UniformDistribution(DistributionStrategy):
    """
    Distribuzione uniforme: tutti i valori nel range sono equiprobabili.
    
    Comportamento:
    - center viene ignorato (uniform è simmetrico attorno a 0)
    - spread definisce il range totale
    - Output: center + uniform(-spread/2, +spread/2)
    
    Uso tipico: comportamento attuale del sistema.
    """
    
    def sample(self, center: float, spread: float) -> float:
        """
        Genera valore uniformemente distribuito.
        
        Formula: center + random.uniform(-0.5, 0.5) * spread
        """
        if spread <= 0:
            return center
        
        return center + random.uniform(-0.5, 0.5) * spread
    
    @property
    def name(self) -> str:
        return "uniform"
    
    def get_bounds(self, center: float, spread: float) -> Tuple[float, float]:
        """Bounds teorici: [center - spread/2, center + spread/2]"""
        half_spread = spread / 2
        return (center - half_spread, center + half_spread)


class GaussianDistribution(DistributionStrategy):
    """
    Distribuzione gaussiana (normale): valori concentrati attorno al centro.
    
    Comportamento:
    - center = μ (media della gaussiana)
    - spread = σ (deviazione standard)
    - ~68% dei valori in [μ±σ]
    - ~95% dei valori in [μ±2σ]
    - ~99.7% dei valori in [μ±3σ]
    
    Uso tipico: texture "smooth", nuvole sonore, variazioni naturali.
    
    Note:
    - La gaussiana è teoricamente illimitata, ma clamping ai bounds
      del parametro viene fatto successivamente in Parameter._clamp()
    """
    
    def sample(self, center: float, spread: float) -> float:
        """
        Genera valore con distribuzione gaussiana.
        
        Formula: random.gauss(μ=center, σ=spread)
        """
        if spread <= 0:
            return center
        
        return random.gauss(center, spread)
    
    @property
    def name(self) -> str:
        return "gaussian"
    
    def get_bounds(self, center: float, spread: float) -> Tuple[float, float]:
        """
        Bounds teorici: ~99.7% dei valori in [μ-3σ, μ+3σ]
        
        Nota: la gaussiana è teoricamente illimitata,
        ma usiamo 3σ come bound pratico (3-sigma rule).
        """
        three_sigma = spread * 3
        return (center - three_sigma, center + three_sigma)


class DistributionFactory:
    """
    Factory per creare istanze di DistributionStrategy.
    
    Registry pattern: mappa stringhe a classi.
    """
    
    _registry = {
        'uniform': UniformDistribution,
        'gaussian': GaussianDistribution,
    }
    
    @classmethod
    def create(cls, mode: str) -> DistributionStrategy:
        """
        Crea una strategia di distribuzione.
        
        Args:
            mode: Nome della distribuzione ('uniform', 'gaussian')
        
        Returns:
            Istanza di DistributionStrategy
        
        Raises:
            ValueError: Se mode non è riconosciuto
        """
        if mode not in cls._registry:
            raise StrategyNotFoundError(
                strategy_kind="distribution",
                name=mode,
                available=list(cls._registry.keys()),
            )
        
        strategy_class = cls._registry[mode]
        return strategy_class()
    
    @classmethod
    def register(cls, name: str, strategy_class: type):
        """
        Registra una nuova distribuzione (estensibilità futura).
        
        Esempio:
            DistributionFactory.register('triangular', TriangularDistribution)
        """
        if not (isinstance(strategy_class, type) and issubclass(strategy_class, DistributionStrategy)):
            raise InvalidStrategyConfigError(
                strategy_kind="distribution",
                field="strategy_class",
                value=strategy_class,
                hint="deve essere subclass di DistributionStrategy",
            )
        cls._registry[name] = strategy_class