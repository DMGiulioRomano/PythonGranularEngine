# =============================================================================
# tests/rendering/test_renderer_errors.py
# =============================================================================
"""
Issue #38, PR4 — Rendering errors: RendererFactory.create('bogus') solleva
InvalidRendererError (sotto-classe ConfigError).
"""
import pytest


def test_csound_render_error_user_message_and_inheritance():
    from pge.shared.exceptions import (
        CsoundRenderError,
        EngineError,
        EngineRuntimeError,
    )

    err = CsoundRenderError(
        returncode=2,
        command=["csound", "-o", "out.aif", "score.csd"],
        stderr="error: bad orchestra\n",
    )
    assert isinstance(err, EngineRuntimeError)
    assert isinstance(err, EngineError)
    assert isinstance(err, RuntimeError)
    assert err.returncode == 2
    msg = err.user_message()
    assert "[ERRORE]" in msg
    assert "exit code 2" in msg
    assert "csound" in msg


def test_unknown_renderer_raises_invalid_renderer_error():
    from pge.rendering.renderer_factory import RendererFactory
    from pge.shared.exceptions import (
        ConfigError,
        EngineError,
        InvalidRendererError,
    )

    with pytest.raises(InvalidRendererError) as exc_info:
        RendererFactory.create("bogus")

    err = exc_info.value
    assert isinstance(err, ConfigError)
    assert isinstance(err, EngineError)
    assert isinstance(err, ValueError)
    assert err.renderer_type == "bogus"
    assert "numpy" in err.available
    assert "csound" in err.available
    msg = err.user_message()
    assert "[ERRORE]" in msg
    assert "bogus" in msg
    assert "numpy" in msg
    assert "csound" in msg
