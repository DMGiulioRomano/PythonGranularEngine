# strategy_registry.py
"""
Registry pattern: collega nomi di parametri a classi Strategy.
Permette di aggiungere nuove strategie SENZA modificare controller esistenti.
"""
from __future__ import annotations

from typing import Dict, Type
from pge.strategies.strategie import *
from pge.shared.exceptions import (
    InvalidStrategyConfigError,
    StrategyNotFoundError,
)
from pge.shared.logger import log_strategy_registration

# =============================================================================
# REGISTRI
# =============================================================================

# Il pitch base è unit-driven: PitchController costruisce direttamente
# UnitPitchStrategy dalla PitchUnit, senza registry per-preset.

DENSITY_STRATEGIES: Dict[str, Type[DensityStrategy]] = {
    'fill_factor': FillFactorStrategy,
    'density': DirectDensityStrategy,
}


# =============================================================================
# FUNZIONI DI REGISTRAZIONE (per estensibilità)
# =============================================================================

def register_density_strategy(param_name: str, strategy_class: Type[DensityStrategy]):
    """Registra una nuova strategia di density."""
    DENSITY_STRATEGIES[param_name] = strategy_class
    log_strategy_registration('density', param_name, strategy_class)


# =============================================================================
# FACTORY DELLE STRATEGIE
# =============================================================================

class StrategyFactory:
    """Crea strategie basate sui parametri selezionati."""

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
