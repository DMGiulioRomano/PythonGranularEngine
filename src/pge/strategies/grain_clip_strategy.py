# src/strategies/grain_clip_strategy.py
"""
GrainClipStrategy — controllo dichiarativo dei grain out-of-bounds.

Plan riferimento: docs/plans/2026-05-03-001-fix-grain-clip-strategy-plan.md (U1)

Responsabilita': filtrare grain non validi da stream.voices in post-process,
prima dell'assegnazione finale a Stream. Rende stream.voices unica fonte di
verita' su quali grain esistono. Il renderer non ha piu' opinioni sui bounds.

`GRAIN_CLIP_STRATEGIES` e' uno `StrategyRegistry` del dominio 'grain_clip'
(issue #265, forma decisa in #177): lookup e `StrategyNotFoundError` vivono
nella classe generica, `GrainClipStrategyFactory.create` delega.

**Questo modulo non dichiara un punto di registrazione, per decisione.** Il
registry generico offre `.register` gratis, ma una `register_*_strategy` di
modulo dichiarerebbe estensibile la chiave YAML `clip_strategy`, e quel
vocabolario e' chiuso anche fuori dal motore: `docs/reference/yaml.md` lo
elenca, gl-ls ne tiene una copia a mano (un nome nuovo sarebbe un rosso su YAML
valido), PGE-ui ne disegna i due bottoni. Nessuno nel motore la chiede. Se un
giorno servira', e' una decisione con la sua analisi d'impatto cross-repo, e
`tests/strategies/test_registry_convergenza.py` la pretende dichiarata.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from pge.core.grain import Grain
from pge.strategies.registry import StrategyRegistry


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

GRAIN_CLIP_STRATEGIES = StrategyRegistry('grain_clip', GrainClipStrategy, {
    'overflow_margin': OverflowMarginClipStrategy,
    'passthrough': PassthroughClipStrategy,
})


# =============================================================================
# FACTORY
# =============================================================================

class GrainClipStrategyFactory:
    """Factory per creare GrainClipStrategy da nome registrato."""

    @staticmethod
    def create(name: str, **kwargs) -> GrainClipStrategy:
        """
        Raises:
            StrategyNotFoundError: se il nome non e' nel registry, con il
                dominio 'grain_clip' e le chiavi disponibili.
        """
        return GRAIN_CLIP_STRATEGIES.create(name, **kwargs)
