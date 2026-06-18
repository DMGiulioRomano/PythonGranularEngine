# =============================================================================
# tests/strategies/test_voice_strategy_errors.py
# =============================================================================
"""
Issue #38, PR3 — Voice strategy factories e validazioni sollevano
StrategyNotFoundError / InvalidStrategyConfigError (sotto-classi ConfigError).
"""
import pytest

from shared.exceptions import (
    ConfigError,
    InvalidStrategyConfigError,
    StrategyNotFoundError,
)


def test_voice_pitch_factory_unknown_raises_strategy_not_found():
    from strategies.voice_pitch_strategy import VoicePitchStrategyFactory

    with pytest.raises(StrategyNotFoundError) as exc_info:
        VoicePitchStrategyFactory.create("bogus")

    err = exc_info.value
    assert isinstance(err, ConfigError)
    assert err.strategy_kind == "voice_pitch"
    assert err.name == "bogus"


def test_voice_onset_factory_unknown_raises_strategy_not_found():
    from strategies.voice_onset_strategy import VoiceOnsetStrategyFactory

    with pytest.raises(StrategyNotFoundError) as exc_info:
        VoiceOnsetStrategyFactory.create("bogus")

    err = exc_info.value
    assert err.strategy_kind == "voice_onset"


def test_voice_pointer_factory_unknown_raises_strategy_not_found():
    from strategies.voice_pointer_strategy import VoicePointerStrategyFactory

    with pytest.raises(StrategyNotFoundError) as exc_info:
        VoicePointerStrategyFactory.create("bogus")

    err = exc_info.value
    assert err.strategy_kind == "voice_pointer"


def test_voice_pan_factory_unknown_raises_strategy_not_found():
    from strategies.voice_pan_strategy import VoicePanStrategyFactory

    with pytest.raises(StrategyNotFoundError) as exc_info:
        VoicePanStrategyFactory.create("bogus")

    err = exc_info.value
    assert err.strategy_kind == "voice_pan"


def test_chord_pitch_strategy_unknown_chord_raises_invalid_strategy_config():
    from strategies.voice_pitch_strategy import ChordPitchStrategy

    with pytest.raises(InvalidStrategyConfigError) as exc_info:
        ChordPitchStrategy(chord="bogus_chord")

    err = exc_info.value
    assert isinstance(err, ConfigError)
    assert err.strategy_kind == "voice_pitch"
    assert err.field == "chord"


def test_chord_pitch_strategy_invalid_inversion_raises_invalid_strategy_config():
    from strategies.voice_pitch_strategy import ChordPitchStrategy

    with pytest.raises(InvalidStrategyConfigError) as exc_info:
        ChordPitchStrategy(chord="dom7", inversion=99)

    err = exc_info.value
    assert err.field == "inversion"


def test_chord_progression_unknown_chord_raises_invalid_strategy_config():
    from strategies.voice_pitch_strategy import ChordProgressionPitchStrategy

    with pytest.raises(InvalidStrategyConfigError) as exc_info:
        ChordProgressionPitchStrategy(progression=[[0, "bogus_chord"]])

    err = exc_info.value
    assert isinstance(err, ConfigError)
    assert err.strategy_kind == "voice_pitch"
    assert err.field == "chord"


def test_chord_progression_invalid_interp_raises_invalid_strategy_config():
    from strategies.voice_pitch_strategy import ChordProgressionPitchStrategy

    with pytest.raises(InvalidStrategyConfigError) as exc_info:
        ChordProgressionPitchStrategy(progression=[[0, "maj"]], interp="bogus")

    assert exc_info.value.field == "interp"


def test_chord_progression_invalid_voice_leading_raises_invalid_strategy_config():
    from strategies.voice_pitch_strategy import ChordProgressionPitchStrategy

    with pytest.raises(InvalidStrategyConfigError) as exc_info:
        ChordProgressionPitchStrategy(progression=[[0, "maj"]], voice_leading="bogus")

    assert exc_info.value.field == "voice_leading"


def test_stochastic_pan_strategy_negative_spread_raises_invalid_strategy_config():
    from strategies.voice_pan_strategy import StochasticPanStrategy

    strategy = StochasticPanStrategy(spread=-0.5, stream_id="s1")
    with pytest.raises(InvalidStrategyConfigError) as exc_info:
        strategy.get_pan_offset(voice_index=1, num_voices=2, time=0.0)

    err = exc_info.value
    assert err.field == "spread"
    assert err.value == -0.5
