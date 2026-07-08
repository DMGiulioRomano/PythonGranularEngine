# =============================================================================
# tests/rendering/test_ftable_errors.py
# =============================================================================
"""
Issue #38, PR4 — FtableManager errors.

- register_window con nome sconosciuto → InvalidWindowError
- write_to_file invariant violation → FtableError
"""
import io
import pytest


def test_register_window_unknown_raises_invalid_window_error():
    from pge.rendering.ftable_manager import FtableManager
    from pge.shared.exceptions import ConfigError, InvalidWindowError

    mgr = FtableManager()
    with pytest.raises(InvalidWindowError) as exc_info:
        mgr.register_window("bogus_window")

    err = exc_info.value
    assert isinstance(err, ConfigError)
    assert err.name == "bogus_window"
    msg = err.user_message()
    assert "[ERRORE]" in msg
    assert "bogus_window" in msg


def test_write_to_file_corrupt_window_raises_ftable_error():
    from pge.rendering.ftable_manager import FtableManager
    from pge.shared.exceptions import ConfigError, FtableError

    mgr = FtableManager()
    # Inject inconsistent state: table references a window not in WindowRegistry
    mgr.tables[1] = ('window', 'nonexistent_window_xyz')

    buf = io.StringIO()
    with pytest.raises(FtableError) as exc_info:
        mgr.write_to_file(buf)

    err = exc_info.value
    assert isinstance(err, ConfigError)
    msg = err.user_message()
    assert "[ERRORE]" in msg
    assert "nonexistent_window_xyz" in msg
