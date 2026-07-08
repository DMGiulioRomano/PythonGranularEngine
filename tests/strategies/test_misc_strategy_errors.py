# =============================================================================
# tests/strategies/test_misc_strategy_errors.py
# =============================================================================
"""
Issue #38, PR3 — grain_clip / distribution / naming / variation
sollevano sotto-classi di ConfigError per config user-facing invalida.
"""
import pytest

from pge.shared.exceptions import (
    ConfigError,
    InvalidParameterError,
    InvalidStrategyConfigError,
    StrategyNotFoundError,
)


def test_grain_clip_factory_unknown_raises_strategy_not_found():
    from pge.strategies.grain_clip_strategy import GrainClipStrategyFactory

    with pytest.raises(StrategyNotFoundError) as exc_info:
        GrainClipStrategyFactory.create("bogus")

    err = exc_info.value
    assert isinstance(err, ConfigError)
    assert err.strategy_kind == "grain_clip"


def test_distribution_factory_unknown_raises_strategy_not_found():
    from pge.shared.distribution_strategy import DistributionFactory

    with pytest.raises(StrategyNotFoundError) as exc_info:
        DistributionFactory.create("bogus_dist")

    err = exc_info.value
    assert err.strategy_kind == "distribution"
    assert err.name == "bogus_dist"


def test_distribution_register_invalid_subclass_raises_invalid_strategy_config():
    from pge.shared.distribution_strategy import DistributionFactory

    class NotAStrategy:
        pass

    with pytest.raises(InvalidStrategyConfigError) as exc_info:
        DistributionFactory.register("foo", NotAStrategy)

    err = exc_info.value
    assert err.strategy_kind == "distribution"
    assert err.field == "strategy_class"


def test_naming_strategy_unknown_mode_raises_invalid_strategy_config():
    from pge.rendering.naming_strategy import DefaultNamingStrategy

    with pytest.raises(InvalidStrategyConfigError) as exc_info:
        DefaultNamingStrategy().generate_paths(
            streams=[], base_path="out.aif", mode="bogus_mode",
        )

    err = exc_info.value
    assert err.strategy_kind == "naming"
    assert err.field == "mode"


def test_choice_variation_invalid_type_raises_invalid_parameter_error():
    from pge.strategies.variation_strategy import ChoiceVariation
    from pge.shared.distribution_strategy import UniformDistribution

    with pytest.raises(InvalidParameterError) as exc_info:
        ChoiceVariation().apply(
            value=12345, mod_range=1, distribution=UniformDistribution()
        )

    err = exc_info.value
    assert isinstance(err, ConfigError)
    assert err.param_name == "ChoiceVariation"
