# strategy_registry.py
"""
Registry pattern: collega nomi di parametri a classi Strategy.
Permette di aggiungere nuove strategie SENZA modificare controller esistenti.
"""

from typing import Dict, Type
from strategies.strategie import *
from shared.exceptions import (
    InvalidStrategyConfigError,
    StrategyNotFoundError,
)

# =============================================================================
# REGISTRI
# =============================================================================

PITCH_STRATEGIES: Dict[str, Type[PitchStrategy]] = {
    'pitch_semitones': SemitonesStrategy,
    'pitch_ratio': RatioStrategy,
}

DENSITY_STRATEGIES: Dict[str, Type[DensityStrategy]] = {
    'fill_factor': FillFactorStrategy,
    'density': DirectDensityStrategy,
}


# =============================================================================
# FUNZIONI DI REGISTRAZIONE (per estensibilità)
# =============================================================================

def register_pitch_strategy(param_name: str, strategy_class: Type[PitchStrategy]):
    """Registra una nuova strategia di pitch."""
    PITCH_STRATEGIES[param_name] = strategy_class
    print(f"✅ Registrata nuova strategia pitch: {param_name} -> {strategy_class.__name__}")


def register_density_strategy(param_name: str, strategy_class: Type[DensityStrategy]):
    """Registra una nuova strategia di density."""
    DENSITY_STRATEGIES[param_name] = strategy_class
    print(f"✅ Registrata nuova strategia density: {param_name} -> {strategy_class.__name__}")


# =============================================================================
# FACTORY DELLE STRATEGIE
# =============================================================================

class StrategyFactory:
    """Crea strategie basate sui parametri selezionati."""
    
    @staticmethod
    def create_pitch_strategy(selected_param_name: str, 
                             param_obj: Parameter,
                             all_params: dict) -> PitchStrategy:
        """Crea una strategia di pitch."""
        if selected_param_name not in PITCH_STRATEGIES:
            raise StrategyNotFoundError(
                strategy_kind="pitch",
                name=selected_param_name,
                available=list(PITCH_STRATEGIES.keys()),
            )

        strategy_class = PITCH_STRATEGIES[selected_param_name]
        return strategy_class(param_obj)
    
    @staticmethod
    def create_density_strategy(selected_param_name: str,
                               param_obj: Parameter,
                               all_params: dict) -> DensityStrategy:
        """Crea una strategia di density."""
        if selected_param_name not in DENSITY_STRATEGIES:
            raise StrategyNotFoundError(
                strategy_kind="density",
                name=selected_param_name,
                available=list(DENSITY_STRATEGIES.keys()),
            )

        # La strategia density ha bisogno anche del parametro distribution
        distribution_param = all_params.get('distribution')
        if distribution_param is None or not isinstance(distribution_param, Parameter):
            raise InvalidStrategyConfigError(
                strategy_kind="density",
                field="distribution",
                value=distribution_param,
                hint="density strategy richiede parametro 'distribution' valido",
            )
        strategy_class = DENSITY_STRATEGIES[selected_param_name]
        return strategy_class(param_obj, distribution_param)