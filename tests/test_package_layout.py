# tests/test_package_layout.py
"""
Test del layout package `pge` (Fase 3 del refactor library/CLI).

Verifica che:
- `import pge` funzioni e sia economico (niente matplotlib);
- l'API e la CLI siano importabili dai nuovi path (`pge.api`, `pge.cli`);
- `pge.__version__` esista;
- lo shim `src/main.py` resti importabile per compatibilita'
  (`python src/main.py` e Makefile invariati).
"""

import subprocess
import sys
import os

import pytest

SRC_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'src'))


class TestPgePackage:

    def test_import_pge(self):
        import pge
        assert pge is not None

    def test_pge_has_version(self):
        import pge
        assert isinstance(pge.__version__, str)
        assert pge.__version__

    def test_api_importable_from_pge(self):
        from pge.api import render_file, load_generator, RenderResult
        assert callable(render_file)
        assert callable(load_generator)
        assert RenderResult is not None

    def test_cli_importable_from_pge(self):
        from pge.cli import main
        assert callable(main)

    def test_import_pge_does_not_pull_matplotlib(self):
        """`import pge` non deve trascinare matplotlib (lazy via PEP 562):
        verificato in un interprete pulito."""
        code = (
            "import sys; import pge; "
            "assert 'matplotlib' not in sys.modules, 'matplotlib importato'; "
            "print('ok')"
        )
        proc = subprocess.run(
            [sys.executable, '-c', code],
            capture_output=True, text=True,
            env={**os.environ, 'PYTHONPATH': SRC_DIR},
        )
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == 'ok'

    def test_scorevisualizer_lazy_export(self):
        """pge.ScoreVisualizer disponibile via __getattr__ lazy."""
        import pge
        from pge.rendering.score_visualizer import ScoreVisualizer
        assert pge.ScoreVisualizer is ScoreVisualizer


class TestMainShim:
    """src/main.py resta per sempre: python src/main.py mette src/ in testa
    a sys.path e delega a pge.cli (Makefile, e2e e PGE-ui non cambiano)."""

    def test_shim_reexports_symbols(self):
        # Import freschi: altri test (fixture mocks) reimportano pge.cli
        # sotto sys.modules patchato e possono lasciare in cache coppie
        # main/pge.cli non allineate.
        import importlib
        sys.modules.pop('main', None)
        sys.modules.pop('pge.cli', None)
        main = importlib.import_module('main')
        cli = importlib.import_module('pge.cli')
        assert main.main is cli.main
        assert main._handle_engine_error is cli._handle_engine_error
        assert main._parse_jobs is cli._parse_jobs
        assert main._parse_magnify_spec is cli._parse_magnify_spec
        assert main._build_renderer is cli._build_renderer

    def test_shim_usage_via_subprocess(self):
        """python src/main.py senza argomenti: usage su stdout, exit 1."""
        proc = subprocess.run(
            [sys.executable, os.path.join(SRC_DIR, 'main.py')],
            capture_output=True, text=True,
        )
        assert proc.returncode == 1
        assert proc.stdout.startswith('Uso: python main.py <file.yml>')
