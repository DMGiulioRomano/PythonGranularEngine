# =============================================================================
# tests/rendering/test_ftable_errors.py
# =============================================================================
"""
Issue #38, PR4 — FtableManager errors.

- register_window con nome sconosciuto → InvalidWindowError
- symbol table incoerente → FtableError

La seconda si e' spostata su CsoundEmitter con la issue #203: e' l'emitter a
materializzare le tabelle, quindi e' li' che l'incoerenza si vede. Resta un
errore sul contenuto della symbol table del manager, che e' chi avrebbe
dovuto impedirla.
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


def test_emitting_a_corrupt_window_raises_ftable_error():
    from pge.rendering.csound_emitter import CsoundEmitter
    from pge.rendering.ftable_manager import FtableManager
    from pge.shared.exceptions import ConfigError, FtableError

    mgr = FtableManager()
    # Inject inconsistent state: table references a window not in WindowRegistry
    mgr.tables[1] = ('window', 'nonexistent_window_xyz')

    buf = io.StringIO()
    with pytest.raises(FtableError) as exc_info:
        CsoundEmitter().write_ftables(buf, mgr.get_all_tables())

    err = exc_info.value
    assert isinstance(err, ConfigError)
    msg = err.user_message()
    assert "[ERRORE]" in msg
    assert "nonexistent_window_xyz" in msg
