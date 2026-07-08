# =============================================================================
# tests/parameters/test_gate_factory_errors.py
# =============================================================================
"""
Issue #38, PR2 — GateFactory solleva InvalidParameterError per dephase
malformato (tipo non supportato o valore non parsabile).
"""
import pytest

from pge.parameters.gate_factory import GateFactory
from pge.shared.exceptions import ConfigError, InvalidParameterError


def test_classify_dephase_invalid_type_raises_invalid_parameter_error():
    """dephase di tipo non supportato → InvalidParameterError."""
    with pytest.raises(InvalidParameterError) as exc_info:
        GateFactory._classify_dephase(object())

    err = exc_info.value
    assert isinstance(err, ConfigError)
    assert "dephase" in err.param_name


def test_parse_raw_value_invalid_type_raises_invalid_parameter_error():
    """Valore dephase per chiave specifica con tipo invalido → InvalidParameterError."""
    with pytest.raises(InvalidParameterError) as exc_info:
        GateFactory._parse_raw_value(object(), duration=1.0, time_mode='absolute')

    err = exc_info.value
    assert isinstance(err, ConfigError)
    assert "dephase" in err.param_name
