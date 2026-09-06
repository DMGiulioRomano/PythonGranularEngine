# variation_registry.py
"""
Registry e Factory per le strategie di variazione.
Segue lo stesso pattern di strategy_registry.py per coerenza.
"""
from __future__ import annotations

from typing import Dict, Type
from pge.strategies.variation_strategy import (
    VariationStrategy,
    AdditiveVariation,
    QuantizedVariation,
    InvertVariation,
    NegateVariation,
    ChoiceVariation
)
from pge.shared.exceptions import StrategyNotFoundError
from pge.shared.logger import log_strategy_registration

# =============================================================================
# REGISTRY
# =============================================================================

VARIATION_STRATEGIES: Dict[str, Type[VariationStrategy]] = {
    'additive': AdditiveVariation,
    'quantized': QuantizedVariation,
    'invert': InvertVariation,
    'negate': NegateVariation,
    'choice': ChoiceVariation,
}


# =============================================================================
# FUNZIONI DI REGISTRAZIONE (per estensibilità futura)
# =============================================================================

def register_variation_strategy(mode_name: str, strategy_class: Type[VariationStrategy]):
    """
    Registra una nuova strategia di variazione.
    
    Esempi futuri:
    - 'logarithmic': LogarithmicVariation
    - 'exponential': ExponentialVariation
    - 'biased_gaussian': BiasedGaussianVariation
    """
    VARIATION_STRATEGIES[mode_name] = strategy_class
    log_strategy_registration('variation', mode_name, strategy_class)


# =============================================================================
# FACTORY
# =============================================================================

class VariationFactory:
    """Crea strategie di variazione basate sul variation_mode."""
    
    @staticmethod
    def create(variation_mode: str) -> VariationStrategy:
        """
        Crea una strategia di variazione.
        
        Args:
            variation_mode: nome della modalità ('additive', 'quantized', 'invert')
            
        Returns:
            Istanza della strategia corrispondente
            
        Raises:
            ValueError: se variation_mode non è registrato
        """
        if variation_mode not in VARIATION_STRATEGIES:
            raise StrategyNotFoundError(
                strategy_kind="variation",
                name=variation_mode,
                available=list(VARIATION_STRATEGIES.keys()),
            )
        
        strategy_class = VARIATION_STRATEGIES[variation_mode]
        return strategy_class()
