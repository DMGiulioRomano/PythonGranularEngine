# =============================================================================
# tests/shared/test_engine_exceptions.py
# =============================================================================
"""
Test per la gerarchia di EngineError e SampleNotFoundError (issue #33).

Verifica che gli errori engine producano messaggi user-facing puliti
con il context disponibile a ciascun layer.
"""
import pytest


def test_sample_not_found_user_message_contains_filename_and_path():
    """SampleNotFoundError espone un messaggio leggibile con file e path cercato."""
    from shared.exceptions import SampleNotFoundError

    err = SampleNotFoundError(filename="pino.wav", search_path="./refs/")

    msg = err.user_message()
    assert "pino.wav" in msg
    assert "./refs/" in msg


def test_sample_not_found_is_engine_error():
    """SampleNotFoundError è catturabile come EngineError (handler unico in main)."""
    from shared.exceptions import EngineError, SampleNotFoundError

    err = SampleNotFoundError(filename="x.wav", search_path="./refs/")
    assert isinstance(err, EngineError)
    assert isinstance(err, Exception)


def test_sample_not_found_user_message_includes_optional_context():
    """Quando stream_id e config_file sono settati, compaiono nel messaggio."""
    from shared.exceptions import SampleNotFoundError

    err = SampleNotFoundError(filename="pino.wav", search_path="./refs/")
    err.stream_id = "drone_a"
    err.config_file = "configs/PGE_test.yml"

    msg = err.user_message()
    assert "drone_a" in msg
    assert "configs/PGE_test.yml" in msg


def test_sample_not_found_user_message_omits_missing_context():
    """Senza context arricchito, il messaggio non mostra righe vuote."""
    from shared.exceptions import SampleNotFoundError

    err = SampleNotFoundError(filename="x.wav", search_path="./refs/")
    msg = err.user_message()
    assert "Stream:" not in msg
    assert "Config:" not in msg


# =============================================================================
# Issue #38 — PR1: ConfigError, MissingFieldError, InvalidFieldValueError
# =============================================================================


def test_missing_field_error_inherits_engine_error_and_value_error():
    """MissingFieldError ereditare da EngineError e ValueError per compat catch."""
    from shared.exceptions import (
        ConfigError,
        EngineError,
        MissingFieldError,
    )

    err = MissingFieldError(field="sample")
    assert isinstance(err, EngineError)
    assert isinstance(err, ValueError)
    assert isinstance(err, ConfigError)


def test_missing_field_error_user_message_single_field():
    """MissingFieldError espone messaggio pulito con field name."""
    from shared.exceptions import MissingFieldError

    err = MissingFieldError(field="sample")
    msg = err.user_message()
    assert "[ERRORE]" in msg
    assert "sample" in msg


def test_missing_field_error_user_message_includes_optional_context():
    """stream_id e config_file appaiono in user_message quando settati."""
    from shared.exceptions import MissingFieldError

    err = MissingFieldError(field="sample")
    err.stream_id = "drone_a"
    err.config_file = "configs/PGE_test.yml"

    msg = err.user_message()
    assert "drone_a" in msg
    assert "configs/PGE_test.yml" in msg


def test_missing_field_error_user_message_omits_missing_context():
    """Senza context arricchito, niente righe vuote."""
    from shared.exceptions import MissingFieldError

    err = MissingFieldError(field="sample")
    msg = err.user_message()
    assert "Stream:" not in msg
    assert "Config:" not in msg


def test_missing_field_error_supports_multiple_fields():
    """MissingFieldError accetta lista di fields per casi multi-campo."""
    from shared.exceptions import MissingFieldError

    err = MissingFieldError(fields=["foo", "bar"])
    msg = err.user_message()
    assert "foo" in msg
    assert "bar" in msg


def test_invalid_field_value_error_inherits_engine_and_value_error():
    """InvalidFieldValueError catturabile come EngineError e ValueError."""
    from shared.exceptions import (
        ConfigError,
        EngineError,
        InvalidFieldValueError,
    )

    err = InvalidFieldValueError(field="grain.reverse", value=True)
    assert isinstance(err, EngineError)
    assert isinstance(err, ValueError)
    assert isinstance(err, ConfigError)


def test_invalid_field_value_error_user_message_contains_field_and_value():
    """user_message mostra field e valore invalido."""
    from shared.exceptions import InvalidFieldValueError

    err = InvalidFieldValueError(field="grain.reverse", value=True, hint="lascia vuoto")
    msg = err.user_message()
    assert "grain.reverse" in msg
    assert "True" in msg
    assert "lascia vuoto" in msg


def test_invalid_field_value_error_includes_optional_context():
    """stream_id e config_file appaiono quando settati."""
    from shared.exceptions import InvalidFieldValueError

    err = InvalidFieldValueError(field="x", value=1)
    err.stream_id = "s1"
    err.config_file = "c.yml"
    msg = err.user_message()
    assert "s1" in msg
    assert "c.yml" in msg


# =============================================================================
# Issue #38 — PR2: InvalidParameterError, ParameterBoundError
# =============================================================================


def test_invalid_parameter_error_inherits_config_error():
    """InvalidParameterError catturabile come ConfigError/EngineError/ValueError."""
    from shared.exceptions import (
        ConfigError,
        EngineError,
        InvalidParameterError,
    )

    err = InvalidParameterError(param_name="density.value", value="bad")
    assert isinstance(err, ConfigError)
    assert isinstance(err, EngineError)
    assert isinstance(err, ValueError)


def test_invalid_parameter_error_user_message_contains_param_and_value():
    """user_message mostra param_name e value, formato pulito."""
    from shared.exceptions import InvalidParameterError

    err = InvalidParameterError(
        param_name="density.value",
        value={"x": 1},
        hint="atteso numero o lista breakpoints",
    )
    msg = err.user_message()
    assert "[ERRORE]" in msg
    assert "density.value" in msg
    assert "atteso numero" in msg


def test_invalid_parameter_error_includes_optional_context():
    """stream_id e config_file compaiono quando settati."""
    from shared.exceptions import InvalidParameterError

    err = InvalidParameterError(param_name="dephase", value=object())
    err.stream_id = "s1"
    err.config_file = "c.yml"
    msg = err.user_message()
    assert "s1" in msg
    assert "c.yml" in msg


def test_parameter_bound_error_inherits_config_error():
    """ParameterBoundError catturabile come ConfigError/EngineError/ValueError."""
    from shared.exceptions import (
        ConfigError,
        EngineError,
        ParameterBoundError,
    )

    err = ParameterBoundError(
        param_name="density",
        value_type="value",
        value=999.0,
        min_bound=0.0,
        max_bound=100.0,
    )
    assert isinstance(err, ConfigError)
    assert isinstance(err, EngineError)
    assert isinstance(err, ValueError)


def test_parameter_bound_error_user_message_shows_violation():
    """user_message mostra param, valore trovato, bounds."""
    from shared.exceptions import ParameterBoundError

    err = ParameterBoundError(
        param_name="density",
        value_type="value",
        value=999.0,
        min_bound=0.0,
        max_bound=100.0,
    )
    msg = err.user_message()
    assert "[ERRORE]" in msg
    assert "density" in msg
    assert "999" in msg
    assert "100" in msg


def test_parameter_bound_error_includes_optional_context():
    from shared.exceptions import ParameterBoundError

    err = ParameterBoundError(
        param_name="density",
        value_type="value",
        value=-1.0,
        min_bound=0.0,
        max_bound=100.0,
    )
    err.stream_id = "s1"
    err.config_file = "c.yml"
    msg = err.user_message()
    assert "s1" in msg
    assert "c.yml" in msg


def test_parameter_bound_error_supports_envelope_violations():
    """ParameterBoundError accetta lista violazioni per envelope."""
    from shared.exceptions import ParameterBoundError

    err = ParameterBoundError(
        param_name="density",
        value_type="value",
        violations=[(0.0, 999.0), (1.0, -5.0)],
        min_bound=0.0,
        max_bound=100.0,
    )
    msg = err.user_message()
    assert "999" in msg
    assert "-5" in msg
