# =============================================================================
# tests/parameters/test_parser_errors.py
# =============================================================================
"""
Issue #38, PR2 — GranularParser solleva sotto-classi di ConfigError
con context arricchito (stream_id) per errori user-facing.
"""
import pytest

from pge.parameters.parser import GranularParser
from pge.core.stream_config import StreamConfig, StreamContext
from pge.shared.exceptions import (
    ConfigError,
    InvalidParameterError,
    ParameterBoundError,
)


def _make_parser(stream_id: str = "drone_a", duration: float = 5.0):
    ctx = StreamContext(
        stream_id=stream_id,
        onset=0.0,
        duration=duration,
        sample="x.wav",
        sample_dur_sec=10.0,
    )
    cfg = StreamConfig(
        distribution_mode="uniform",
        time_mode="absolute",
        context=ctx,
    )
    return GranularParser(cfg)


def test_parser_invalid_input_format_raises_invalid_parameter_error():
    """Tipo non supportato come value_raw → InvalidParameterError con stream_id."""
    parser = _make_parser(stream_id="drone_a")

    with pytest.raises(InvalidParameterError) as exc_info:
        parser.parse_parameter(name="density", value_raw="not_a_number")

    err = exc_info.value
    assert isinstance(err, ConfigError)
    assert err.stream_id == "drone_a"
    assert "density" in err.param_name


def test_parser_scalar_out_of_bounds_raises_parameter_bound_error():
    """Scalare fuori bounds in strict mode → ParameterBoundError."""
    parser = _make_parser(stream_id="drone_b")

    with pytest.raises(ParameterBoundError) as exc_info:
        parser.parse_parameter(name="density", value_raw=999999.0)

    err = exc_info.value
    assert isinstance(err, ConfigError)
    assert err.stream_id == "drone_b"
    assert err.param_name == "density"
    assert err.value == 999999.0


def test_parser_envelope_out_of_bounds_raises_parameter_bound_error():
    """Envelope con breakpoint fuori bounds → ParameterBoundError con violations."""
    parser = _make_parser(stream_id="drone_c", duration=2.0)

    with pytest.raises(ParameterBoundError) as exc_info:
        parser.parse_parameter(name="density", value_raw=[[0, 999999.0], [1, 5]])

    err = exc_info.value
    assert err.stream_id == "drone_c"
    assert err.param_name == "density"
    assert len(err.violations) >= 1
