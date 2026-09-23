# =============================================================================
# tests/strategies/test_registry_errors.py
# =============================================================================
"""
Issue #38, PR3 — registry strategy sollevano StrategyNotFoundError
(sotto-classe ConfigError) per nomi non registrati.
"""
import pytest

from pge.shared.exceptions import (
    ConfigError,
    StrategyNotFoundError,
)


def test_strategy_factory_density_not_found_raises_strategy_not_found_error():
    from pge.strategies.strategy_registry import StrategyFactory

    with pytest.raises(StrategyNotFoundError) as exc_info:
        StrategyFactory.create_density_strategy("bogus", None, {})

    err = exc_info.value
    assert err.strategy_kind == "density"
    assert err.name == "bogus"


def test_variation_factory_unknown_mode_raises_strategy_not_found_error():
    from pge.strategies.variation_registry import VariationFactory

    with pytest.raises(StrategyNotFoundError) as exc_info:
        VariationFactory.create("bogus_mode")

    err = exc_info.value
    assert isinstance(err, ConfigError)
    assert err.strategy_kind == "variation"
    assert "bogus_mode" in err.name


def test_density_not_found_non_dipende_dal_tipo_di_all_params():
    """Il lookup viene prima, qualunque cosa sia `all_params`.

    La #185 ha reso la validazione di `distribution` subordinata al lookup,
    ma subordinato era solo il `raise`: la *lettura* `all_params.get(...)`
    stava davanti al gate, quindi un `all_params` che non e' una mappa moriva
    di `AttributeError` — fuori dalla gerarchia `EngineError`, cioe' un
    traceback nudo dove la CLI si aspetta un errore di configurazione — la
    dove prima cadeva `StrategyNotFoundError`.

    Il nome non registrato e' la condizione che rende la cosa osservabile:
    con un nome buono la lettura serve davvero, con uno sbagliato no.
    """
    from pge.strategies.strategy_registry import StrategyFactory

    for all_params in (None, [], "distribution", 0):
        with pytest.raises(StrategyNotFoundError) as exc_info:
            StrategyFactory.create_density_strategy("bogus", None, all_params)

        assert exc_info.value.strategy_kind == "density", (
            f"con all_params={all_params!r} l'errore non e' quello del "
            "lookup del registry"
        )
