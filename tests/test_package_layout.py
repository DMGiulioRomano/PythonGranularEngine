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


class TestEditableInstall:
    """Packaging (Fase 4): pip install -e . funzionante e console script
    `pge` equivalente a python src/main.py."""

    def test_console_script_pge_usage(self):
        """Lo script `pge` installato nel venv di sviluppo (make venv-setup
        installa -e .[dev]) stampa la usage ed esce con rc 1."""
        import sysconfig
        scripts_dir = sysconfig.get_path('scripts')
        pge_bin = os.path.join(scripts_dir, 'pge')
        assert os.path.exists(pge_bin), (
            f"console script mancante: {pge_bin} (pip install -e . non "
            "eseguito nel venv?)")
        proc = subprocess.run([pge_bin], capture_output=True, text=True)
        assert proc.returncode == 1
        assert proc.stdout.startswith('Uso: python main.py <file.yml>')

    @pytest.mark.e2e
    def test_editable_install_in_clean_venv(self, tmp_path):
        """In un venv pulito: pip install -e . --no-deps, poi import pge e
        pge.api da una directory FUORI dal repo."""
        import venv as venv_mod
        venv_dir = tmp_path / 'venv'
        venv_mod.EnvBuilder(with_pip=True).create(str(venv_dir))
        py = str(venv_dir / 'bin' / 'python')
        repo_root = os.path.dirname(SRC_DIR)

        install = subprocess.run(
            [py, '-m', 'pip', 'install', '-q', '-e', repo_root, '--no-deps'],
            capture_output=True, text=True)
        assert install.returncode == 0, install.stderr

        check = subprocess.run(
            [py, '-c', 'import pge, pge.api; print(pge.__version__)'],
            capture_output=True, text=True,
            cwd=str(tmp_path),               # fuori dal repo
            env={k: v for k, v in os.environ.items() if k != 'PYTHONPATH'})
        assert check.returncode == 0, check.stderr
        assert check.stdout.strip()
