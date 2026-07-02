# tests/test_main_jobs_flag.py
"""
Test per il flag CLI --jobs (rendering NumPy multi-processo).

_parse_jobs(argv) e' l'helper testabile di main.py, stile --format:
- assente → 'auto' (default: parallelo, core disponibili - 1)
- --jobs N (intero >= 1) → N
- --jobs auto (case-insensitive) → 'auto'
- --jobs 0 | negativo | non numerico → messaggio + exit(1)
- --jobs senza valore → default (coerente con gli altri flag di main)

La risoluzione 'auto' → intero avviene in NumpyAudioRenderer via
numpy_parallel.resolve_jobs; qui si testa solo il parsing.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
from main import _parse_jobs


class TestParseJobs:
    """Parsing del flag --jobs."""

    def test_absent_defaults_to_auto(self):
        assert _parse_jobs(['main.py', 'file.yml']) == 'auto'

    def test_explicit_integer(self):
        assert _parse_jobs(['main.py', 'file.yml', '--jobs', '4']) == 4

    def test_explicit_one(self):
        """--jobs 1 = path sequenziale garantito byte-identico."""
        assert _parse_jobs(['main.py', 'file.yml', '--jobs', '1']) == 1

    def test_auto_keyword(self):
        assert _parse_jobs(['main.py', 'file.yml', '--jobs', 'auto']) == 'auto'

    def test_auto_keyword_case_insensitive(self):
        assert _parse_jobs(['main.py', 'file.yml', '--jobs', 'AUTO']) == 'auto'

    def test_zero_exits_with_message(self, capsys):
        with pytest.raises(SystemExit) as exc:
            _parse_jobs(['main.py', 'file.yml', '--jobs', '0'])
        assert exc.value.code == 1
        assert '--jobs' in capsys.readouterr().out

    def test_negative_exits_with_message(self, capsys):
        with pytest.raises(SystemExit) as exc:
            _parse_jobs(['main.py', 'file.yml', '--jobs', '-3'])
        assert exc.value.code == 1
        assert '--jobs' in capsys.readouterr().out

    def test_non_numeric_exits_with_message(self, capsys):
        with pytest.raises(SystemExit) as exc:
            _parse_jobs(['main.py', 'file.yml', '--jobs', 'tanti'])
        assert exc.value.code == 1
        assert '--jobs' in capsys.readouterr().out

    def test_missing_value_keeps_default(self):
        """--jobs come ultimo token: default, come gli altri flag di main."""
        assert _parse_jobs(['main.py', 'file.yml', '--jobs']) == 'auto'


class TestBuildRendererJobsWiring:
    """_build_renderer propaga jobs fino a NumpyAudioRenderer."""

    def _make_generator_stub(self, tmp_path):
        """Generator minimale: table_map senza sample (nessun load da disco)."""
        from unittest.mock import Mock
        import soundfile as sf
        import numpy as np

        sf.write(str(tmp_path / 'tone.wav'),
                 np.zeros(1000, dtype=np.float32), 48000)

        gen = Mock()
        gen.ftable_manager.get_all_tables.return_value = {
            1: ('sample', 'tone.wav'),
            2: ('window', 'hanning'),
        }
        gen.stream_data_map = {}
        return gen

    def test_jobs_reaches_renderer(self, tmp_path, monkeypatch):
        from main import _build_renderer
        monkeypatch.chdir(tmp_path)
        # SampleRegistry default base_path='./refs/'
        (tmp_path / 'refs').mkdir()
        import soundfile as sf
        import numpy as np
        sf.write(str(tmp_path / 'refs' / 'tone.wav'),
                 np.zeros(1000, dtype=np.float32), 48000)

        gen = self._make_generator_stub(tmp_path)
        renderer = _build_renderer('numpy', gen, jobs=3)
        assert renderer.jobs == 3

    def test_auto_resolved_to_positive_int(self, tmp_path, monkeypatch):
        from main import _build_renderer
        monkeypatch.chdir(tmp_path)
        (tmp_path / 'refs').mkdir()
        import soundfile as sf
        import numpy as np
        sf.write(str(tmp_path / 'refs' / 'tone.wav'),
                 np.zeros(1000, dtype=np.float32), 48000)

        gen = self._make_generator_stub(tmp_path)
        renderer = _build_renderer('numpy', gen, jobs='auto')
        assert isinstance(renderer.jobs, int)
        assert renderer.jobs >= 1
