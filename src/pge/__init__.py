# =============================================================================
# Package pubblico `pge` (Fase 3 refactor library/CLI).
#
# Ri-esporta solo simboli leggeri (api, eccezioni, costanti, configure_* dei
# logger); i simboli pesanti (ScoreVisualizer -> matplotlib, Generator,
# RenderingEngine) sono risolti lazy via __getattr__ di modulo (PEP 562)
# cosi' `import pge` resta economico per i consumatori render-only.
# =============================================================================

from __future__ import annotations

# Versione: dal package installato quando disponibile (Fase 4, editable
# install); fallback stringa per l'uso da repository non installato.
try:
    from importlib.metadata import version as _pkg_version
    __version__ = _pkg_version("pge")
except Exception:
    __version__ = "0.0.0+repo"

from pge import api  # noqa: F401  (modulo leggero: lazy import interni)
from pge.shared.constants import DEFAULT_OUTPUT_SR  # noqa: F401
from pge.shared.exceptions import EngineError  # noqa: F401
# I configure_* dei logger sono API pubblica documentata: chiamarli prima
# di load_generator (la configurazione del logging resta responsabilita'
# del chiamante; la libreria non scrive mai in ./logs di sua iniziativa).
from pge.shared.logger import (  # noqa: F401
    configure_clip_logger,
    configure_engine_logger,
    get_clip_log_path,
    get_engine_log_path,
)

# Simboli pesanti: risolti al primo accesso, mai all'import del package.
_LAZY_EXPORTS = {
    'ScoreVisualizer': ('pge.rendering.score_visualizer', 'ScoreVisualizer'),
    'Generator': ('pge.engine.generator', 'Generator'),
    'RenderingEngine': ('pge.rendering.rendering_engine', 'RenderingEngine'),
}


def __getattr__(name):
    if name in _LAZY_EXPORTS:
        import importlib
        module_name, attr = _LAZY_EXPORTS[name]
        return getattr(importlib.import_module(module_name), attr)
    raise AttributeError(f"module 'pge' has no attribute {name!r}")


def __dir__():
    return sorted(list(globals()) + list(_LAZY_EXPORTS))
