# =============================================================================
# SHIM di compatibilita' (Fase 3 refactor library/CLI).
#
# `python src/main.py` mette src/ in testa a sys.path, quindi `import pge`
# risolve da src/pge/ anche senza install: Makefile ($(INCDIR)/main.py),
# test e2e e PGE-ui restano invariati per sempre. I re-export mantengono
# importabili i simboli storici per chi facesse `from main import ...`.
# =============================================================================

from pge.cli import (  # noqa: F401
    main,
    _build_renderer,
    _handle_engine_error,
    _parse_jobs,
    _parse_magnify_spec,
)

if __name__ == '__main__':
    main()
