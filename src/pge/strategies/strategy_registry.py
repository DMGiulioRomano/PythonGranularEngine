# strategy_registry.py
"""
Registry pattern: collega nomi di parametri a classi Strategy.
Permette di aggiungere nuove strategie SENZA modificare controller esistenti.
"""
from __future__ import annotations

from typing import Type
from pge.strategies.strategie import *
from pge.shared.exceptions import InvalidStrategyConfigError
from pge.strategies.registry import StrategyRegistry

# =============================================================================
# REGISTRI
# =============================================================================

# Il pitch base è unit-driven: PitchController costruisce direttamente
# UnitPitchStrategy dalla PitchUnit, senza registry per-preset.

DENSITY_STRATEGIES = StrategyRegistry('density', DensityStrategy, {
    'fill_factor': FillFactorStrategy,
    'density': DirectDensityStrategy,
})


# =============================================================================
# FUNZIONI DI REGISTRAZIONE (per estensibilità)
# =============================================================================

def register_density_strategy(name: str, strategy_class: Type[DensityStrategy]):
    """Registra una nuova strategia di density.

    Il primo parametro si chiamava `param_name` (issue #185): la chiave del
    registry e' un nome di parametro YAML solo per density, e a descriverla
    cosi' la firma divergeva da quella degli altri otto punti di
    registrazione. I chiamanti la passano posizionalmente.
    """
    DENSITY_STRATEGIES.register(name, strategy_class)


# =============================================================================
# FACTORY DELLE STRATEGIE
# =============================================================================

class StrategyFactory:
    """Crea strategie basate sui parametri selezionati."""

    @staticmethod
    def create_density_strategy(selected_param_name: str,
                               param_obj: Parameter,
                               all_params: dict) -> DensityStrategy:
        """Crea una strategia di density.

        Lookup ed errore sono del registry (issue #185); resta qui la
        validazione di `distribution`, che non e' lookup ma una regola su come
        si costruisce una strategy di density.

        **L'ordine fra le due e' pinnato.** Con un nome non registrato *e*
        `distribution` mancante le due condizioni di fallimento sono vive
        insieme, quindi e' l'ordine a decidere il tipo dell'eccezione:
        `tests/strategies/test_registry_errors.py` chiama
        `create_density_strategy("bogus", None, {})` e pretende
        `StrategyNotFoundError`. Per questo la validazione e' subordinata al
        lookup (`name in DENSITY_STRATEGIES`) invece di stare davanti.
        """
        # La strategia density ha bisogno anche del parametro distribution
        distribution_param = all_params.get('distribution')
        if (selected_param_name in DENSITY_STRATEGIES
                and not isinstance(distribution_param, Parameter)):
            raise InvalidStrategyConfigError(
                strategy_kind="density",
                field="distribution",
                value=distribution_param,
                hint="density strategy richiede parametro 'distribution' valido",
            )
        return DENSITY_STRATEGIES.create(
            selected_param_name, param_obj, distribution_param)
