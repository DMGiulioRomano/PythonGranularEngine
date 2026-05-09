# src/strategies/grain_clip_strategy.py
"""
GrainClipStrategy — controllo dichiarativo dei grain out-of-bounds.

Plan riferimento: docs/plans/2026-05-03-001-fix-grain-clip-strategy-plan.md (U1)

Responsabilita': filtrare grain non validi da stream.voices in post-process,
prima dell'assegnazione finale a Stream. Rende stream.voices unica fonte di
verita' su quali grain esistono. Il renderer non ha piu' opinioni sui bounds.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Type

from core.grain import Grain
from shared.exceptions import StrategyNotFoundError


class GrainClipStrategy(ABC):
    """Strategy astratta per filtrare grain out-of-bounds da stream.voices."""

    @abstractmethod
    def apply(self, voices: List[List[Grain]], stream) -> List[List[Grain]]:
        """Filtra grain invalidi da ogni voce. Restituisce nuova struttura."""
        ...


class OverflowMarginClipStrategy(GrainClipStrategy):
    """Esclude grain la cui coda sfora stream_end + margin."""

    def __init__(self, margin: float = 0.0):
        self.margin = margin

    def apply(self, voices, stream):
        stream_end = stream.onset + stream.duration
        limit = stream_end + self.margin
        return [
            [g for g in voice if g.onset < stream_end and g.onset + g.duration <= limit]
            for voice in voices
        ]


class PassthroughClipStrategy(GrainClipStrategy):
    """Nessun filtro: tutti i grain passano al renderer integralmente."""

    def apply(self, voices, stream):
        return voices


# =============================================================================
# REGISTRY
# =============================================================================

GRAIN_CLIP_STRATEGIES: Dict[str, Type[GrainClipStrategy]] = {
    'overflow_margin': OverflowMarginClipStrategy,
    'passthrough': PassthroughClipStrategy,
}


# =============================================================================
# FACTORY
# =============================================================================

class GrainClipStrategyFactory:
    """Factory per creare GrainClipStrategy da nome registrato."""

    @staticmethod
    def create(name: str, **kwargs) -> GrainClipStrategy:
        if name not in GRAIN_CLIP_STRATEGIES:
            raise StrategyNotFoundError(
                strategy_kind="grain_clip",
                name=name,
                available=list(GRAIN_CLIP_STRATEGIES.keys()),
            )
        return GRAIN_CLIP_STRATEGIES[name](**kwargs)
