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
