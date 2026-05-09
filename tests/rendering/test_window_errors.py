# =============================================================================
# tests/rendering/test_window_errors.py
# =============================================================================
"""
Issue #38, PR4 — Window errors: NumpyWindowRegistry.get solleva
InvalidWindowError (ConfigError) per nome sconosciuto e lunghezza non valida.
"""
import pytest


def test_unknown_window_name_raises_invalid_window_error():
    from rendering.numpy_window_registry import NumpyWindowRegistry
    from shared.exceptions import (
        ConfigError,
        EngineError,
        InvalidWindowError,
    )

    reg = NumpyWindowRegistry()
    with pytest.raises(InvalidWindowError) as exc_info:
        reg.get("bogus", 100)

    err = exc_info.value
    assert isinstance(err, ConfigError)
    assert isinstance(err, EngineError)
    assert isinstance(err, ValueError)
    assert err.name == "bogus"
    assert "hanning" in err.available
    msg = err.user_message()
    assert "[ERRORE]" in msg
    assert "bogus" in msg


def test_window_controller_unknown_window_raises_invalid_window_error():
    from controllers.window_controller import WindowController
    from shared.exceptions import ConfigError, InvalidWindowError

    with pytest.raises(InvalidWindowError) as exc_info:
        WindowController.parse_window_list(
            {"envelope": "totally_bogus"}, stream_id="s1"
        )

    err = exc_info.value
    assert isinstance(err, ConfigError)
    assert err.name == "totally_bogus"
    msg = err.user_message()
    assert "[ERRORE]" in msg
    assert "totally_bogus" in msg


def test_window_controller_invalid_envelope_format_raises_invalid_window_error():
    from controllers.window_controller import WindowController
    from shared.exceptions import InvalidWindowError

    with pytest.raises(InvalidWindowError) as exc_info:
        WindowController.parse_window_list({"envelope": 42}, stream_id="s1")

    err = exc_info.value
    msg = err.user_message()
    assert "[ERRORE]" in msg


def test_window_controller_empty_list_raises_invalid_window_error():
    from controllers.window_controller import WindowController
    from shared.exceptions import InvalidWindowError

    with pytest.raises(InvalidWindowError):
        WindowController.parse_window_list({"envelope": []}, stream_id="s1")


def test_window_controller_short_states_raises_invalid_window_error():
    from controllers.window_controller import WindowController
    from shared.exceptions import InvalidWindowError

    with pytest.raises(InvalidWindowError):
        WindowController.parse_window_list(
            {"envelope": {"states": [[0.0, "hanning"]], "curve": 0}},
            stream_id="s1",
        )


def test_invalid_length_raises_invalid_window_error():
    from rendering.numpy_window_registry import NumpyWindowRegistry
    from shared.exceptions import InvalidWindowError

    reg = NumpyWindowRegistry()
    with pytest.raises(InvalidWindowError) as exc_info:
        reg.get("hanning", 0)

    err = exc_info.value
    assert err.param == "n"
    assert err.value == 0
    msg = err.user_message()
    assert "[ERRORE]" in msg
    assert "n" in msg
