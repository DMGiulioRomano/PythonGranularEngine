"""
distribution_strategy.py - Strategy Pattern per distribuzioni statistiche.

Implementa diverse distribuzioni di probabilità per la generazione 
di valori stocastici nei parametri granulari.
"""
from __future__ import annotations

import random
from abc import ABC, abstractmethod
from typing import Tuple

from pge.shared.exceptions import (
    InvalidStrategyConfigError,
    StrategyNotFoundError,
)

# =============================================================================
# ANCORA DEL RANGE
# =============================================================================
# Decide come la coppia (base, range) diventa una banda. E' un asse ORTOGONALE
# alla forma della distribuzione: 'uniform'/'gaussian' dicono COME si riempie
# la banda, l'ancora dice DOV'E'.
#
#   'center' (default, storico) → [base - range/2, base + range/2]
#   'min'                       → [base, base + range]
#
# La modalita' 'min' e' la semantica di granulation-studies
# (`value_generators._band_at`): `base` e' il minimo e `range` la forbice di
# apertura verso l'alto. In quella modalita' `range` e' una LARGHEZZA per
# entrambe le distribuzioni — anche per la gaussiana, che in 'center' lo legge
# invece come sigma (vedi GaussianDistribution.sample).
ANCHOR_CENTER = 'center'
ANCHOR_MIN = 'min'

VALID_RANGE_ANCHORS = frozenset({ANCHOR_CENTER, ANCHOR_MIN})


class DistributionStrategy(ABC):
    """
    Strategy astratta per distribuzioni statistiche.

    Ogni strategia implementa un metodo sample() che genera
    un valore random secondo una specifica distribuzione.

    RNG locale (issue #154): il costruttore accetta un `random.Random`
    iniettato; i sample pescano da quello, così ogni Parameter ha il proprio
    stream di draw isolato. Senza rng si usa il modulo `random` globale
    (comportamento legacy).

    Ancora del range: `anchor` decide se (center, spread) descrivono una banda
    centrata (default, comportamento storico) o ancorata al minimo. Il default
    lascia ogni formula identica bit-per-bit.
    """

    def __init__(self, rng=None, anchor: str = ANCHOR_CENTER):
        self._rng = rng if rng is not None else random
        if anchor not in VALID_RANGE_ANCHORS:
            raise StrategyNotFoundError(
                strategy_kind="range_anchor",
                name=anchor,
                available=sorted(VALID_RANGE_ANCHORS),
            )
        self._anchor = anchor

    @property
    def rng(self):
        """RNG locale della strategia (random.Random o modulo random)."""
        return self._rng

    @property
    def anchor(self) -> str:
        """Ancora del range: 'center' (banda centrata) o 'min' (banda in su)."""
        return self._anchor

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
    
    Comportamento (anchor='center', default):
    - center viene ignorato (uniform è simmetrico attorno a 0)
    - spread definisce il range totale
    - Output: center + uniform(-spread/2, +spread/2)

    Comportamento (anchor='min'):
    - center è il MINIMO della banda, spread la sua larghezza
    - Output: uniform(center, center + spread)

    Uso tipico: comportamento attuale del sistema.
    """

    def sample(self, center: float, spread: float) -> float:
        """
        Genera valore uniformemente distribuito.

        Formula 'center': center + rng.uniform(-0.5, 0.5) * spread
        Formula 'min':    rng.uniform(center, center + spread)
        """
        if spread <= 0:
            return center

        if self._anchor == ANCHOR_MIN:
            return self._rng.uniform(center, center + spread)

        return center + self._rng.uniform(-0.5, 0.5) * spread

    @property
    def name(self) -> str:
        return "uniform"

    def get_bounds(self, center: float, spread: float) -> Tuple[float, float]:
        """Bounds teorici: [center - spread/2, center + spread/2] in 'center',
        [center, center + spread] in 'min'."""
        if self._anchor == ANCHOR_MIN:
            return (center, center + spread)

        half_spread = spread / 2
        return (center - half_spread, center + half_spread)


class GaussianDistribution(DistributionStrategy):
    """
    Distribuzione gaussiana (normale): valori concentrati attorno al centro.
    
    Comportamento (anchor='center', default):
    - center = μ (media della gaussiana)
    - spread = σ (deviazione standard)
    - ~68% dei valori in [μ±σ]
    - ~95% dei valori in [μ±2σ]
    - ~99.7% dei valori in [μ±3σ]

    Comportamento (anchor='min'):
    - center è il MINIMO della banda, spread la sua LARGHEZZA (non σ)
    - μ = centro banda, σ = spread/6 → i bordi cadono a 3σ
    - clamp ai bordi banda: la coda fuori banda (~0.3%) si appiattisce
      sull'estremo invece di uscire
    Allineato a granulation-studies (`value_generators._draw`): in modalità
    'min' la banda è una promessa, e una gaussiana illimitata la romperebbe
    per circa un terzo dei valori.

    Uso tipico: texture "smooth", nuvole sonore, variazioni naturali.

    Note:
    - In 'center' la gaussiana è teoricamente illimitata, ma clamping ai
      bounds del parametro viene fatto successivamente in Parameter._clamp()
    """

    def sample(self, center: float, spread: float) -> float:
        """
        Genera valore con distribuzione gaussiana.

        Formula 'center': rng.gauss(μ=center, σ=spread)
        Formula 'min':    clamp(rng.gauss(μ=center+spread/2, σ=spread/6),
                                center, center+spread)
        """
        if spread <= 0:
            return center

        if self._anchor == ANCHOR_MIN:
            lo = center
            hi = center + spread
            mu = (lo + hi) / 2.0
            sigma = spread / 6.0
            return min(max(self._rng.gauss(mu, sigma), lo), hi)

        return self._rng.gauss(center, spread)

    @property
    def name(self) -> str:
        return "gaussian"

    def get_bounds(self, center: float, spread: float) -> Tuple[float, float]:
        """
        Bounds teorici: ~99.7% dei valori in [μ-3σ, μ+3σ] in 'center'.

        Nota: in 'center' la gaussiana è teoricamente illimitata,
        ma usiamo 3σ come bound pratico (3-sigma rule).
        In 'min' i bounds sono esatti: il clamp rende la banda
        [center, center + spread] un limite reale, non statistico.
        """
        if self._anchor == ANCHOR_MIN:
            return (center, center + spread)

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
    def create(cls, mode: str, rng=None,
               anchor: str = ANCHOR_CENTER) -> DistributionStrategy:
        """
        Crea una strategia di distribuzione.

        Args:
            mode: Nome della distribuzione ('uniform', 'gaussian')
            rng: random.Random locale da iniettare (issue #154);
                 None → modulo random globale (legacy)
            anchor: ancora del range ('center' default, 'min')

        Returns:
            Istanza di DistributionStrategy

        Raises:
            StrategyNotFoundError: Se mode o anchor non sono riconosciuti
        """
        if mode not in cls._registry:
            raise StrategyNotFoundError(
                strategy_kind="distribution",
                name=mode,
                available=list(cls._registry.keys()),
            )

        strategy_class = cls._registry[mode]
        return strategy_class(rng=rng, anchor=anchor)
    
    @classmethod
    def register(cls, name: str, strategy_class: type):
        """
        Registra una nuova distribuzione (estensibilità futura).

        Nota: la classe deve accettare il kwarg `rng` nel costruttore
        (basta non ridefinire __init__ ed ereditare da DistributionStrategy).

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
