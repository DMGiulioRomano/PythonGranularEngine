# variation_registry.py
"""
Registry e Factory per le strategie di variazione.
Segue lo stesso pattern di strategy_registry.py per coerenza.
"""
from __future__ import annotations

from typing import Type
from pge.strategies.variation_strategy import (
    VariationStrategy,
    AdditiveVariation,
    QuantizedVariation,
    InvertVariation,
    NegateVariation,
    ChoiceVariation
)
from pge.strategies.registry import StrategyRegistry

# =============================================================================
# REGISTRY
# =============================================================================

VARIATION_STRATEGIES = StrategyRegistry('variation', VariationStrategy, {
    'additive': AdditiveVariation,
    'quantized': QuantizedVariation,
    'invert': InvertVariation,
    'negate': NegateVariation,
    'choice': ChoiceVariation,
})


# =============================================================================
# FUNZIONI DI REGISTRAZIONE (per estensibilità futura)
# =============================================================================

def register_variation_strategy(name: str, strategy_class: Type[VariationStrategy]):
    """
    Registra una nuova strategia di variazione.

    Il primo parametro si chiamava `mode_name` (issue #185): diceva da dove
    viene il valore, non che cosa e' -- la chiave del registry. Tutti i
    chiamanti lo passano posizionalmente, quindi la convergenza su `name` non
    rompe nessuna chiamata viva.

    Esempi futuri:
    - 'logarithmic': LogarithmicVariation
    - 'exponential': ExponentialVariation
    - 'biased_gaussian': BiasedGaussianVariation
    """
    VARIATION_STRATEGIES.register(name, strategy_class)


# =============================================================================
# FACTORY
# =============================================================================

class VariationFactory:
    """Crea strategie di variazione basate sul variation_mode."""
    
    @staticmethod
    def create(name: str) -> VariationStrategy:
        """
        Crea una strategia di variazione.

        Il primo parametro si chiamava `variation_mode`, come quello di
        `register_variation_strategy` si chiamava `mode_name`: la
        convergenza su `name` e' la #185.

        Args:
            name: nome della modalità ('additive', 'quantized', 'invert')

        Returns:
            Istanza della strategia corrispondente

        Raises:
            StrategyNotFoundError: se `name` non è registrato, con l'elenco
                delle modalità disponibili
        """
        return VARIATION_STRATEGIES.create(name)
