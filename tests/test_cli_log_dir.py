# tests/test_cli_log_dir.py
"""
Test di integrazione del flag CLI --log-dir (issue #251).

Niente mock dei logger: si invoca `pge.cli.main()` per davvero da un cwd
temporaneo e si guarda dove i file finiscono sul disco. E' l'unica verifica
che dimostra la cosa che conta -- che i log di un run stiano tutti nella
directory chiesta, e che `./logs` smetta di comparire nel cwd di chi il
flag lo passa.

Prima della issue #251 `--log-dir` raggiungeva solo il renderer csound
(`CsoundOptions.log_dir` -> `--logfile=`): i due logger di caricamento
avevano './logs' scritto a mano, e con `--renderer numpy` il flag non
aveva alcun effetto.

Lo YAML cita un sample inesistente apposta: il run muore in
`Generator.create_elements()`, cioe' dopo la configurazione dei logger e
prima di qualunque render. Cosi' la prova non ha bisogno ne' di csound ne'
di un file audio, e il log dell'errore -- quello che la issue segnala --
viene scritto davvero.
"""

import os
import sys

import pytest
from unittest.mock import patch

import pge.shared.logger as logger_module
from pge.shared.logger import get_clip_logger, get_clip_log_path


_YAML_SAMPLE_MANCANTE = """\
seed: 42
streams:
  - stream_id: s1
    onset: 0
    duration: 0.5
    sample: inesistente.wav
    time_mode: normalized
    distribution_mode: uniform
    density: 10
    distribution: 0
    grain:
      duration: 0.05
      envelope: hanning
    pointer:
      start: 0
      speed_ratio: 1
"""


@pytest.fixture(autouse=True)
def reset_logger_state():
    """Riporta i due logger allo stato di partenza, prima e dopo ogni test.

    Sono globali di modulo con file aperti dentro: senza reset un test si
    porterebbe dietro la configurazione (e i descriptor) del precedente.
    """
    def _close_and_reset():
        for logger in (logger_module._clip_logger, logger_module._engine_logger):
            if logger is not None:
                for handler in logger.handlers[:]:
                    handler.close()
                    logger.removeHandler(handler)
        logger_module._clip_logger = None
        logger_module._clip_logger_initialized = False
        logger_module._engine_logger = None
        logger_module._engine_log_path = None
        logger_module.CLIP_LOG_CONFIG.update({
            'enabled': True,
            'console_enabled': True,
            'file_enabled': True,
            'log_dir': './logs',
            'log_filename': None,
            'validation_mode': 'strict',
            'log_transformations': True,
        })
        logger_module.CLIP_LOG_CONFIG.pop('yaml_name', None)

    _close_and_reset()
    yield
    _close_and_reset()


@pytest.fixture
def work(tmp_path, monkeypatch):
    """Un cwd temporaneo con dentro solo lo YAML."""
    d = tmp_path / "work"
    d.mkdir()
    (d / "prova.yml").write_text(_YAML_SAMPLE_MANCANTE)
    monkeypatch.chdir(d)
    return d


def _run(argv):
    """Invoca la CLI reale: il run muore sul sample mancante, exit 1."""
    from pge.cli import main
    with patch.object(sys, 'argv', argv):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1


class TestLogDirIsHonoured:
    """La verifica della issue: tutti i log del run nella directory chiesta."""

    def test_engine_log_lands_in_the_requested_dir(self, work):
        _run(['main.py', 'prova.yml', 'out.aif',
              '--renderer', 'numpy', '--log-dir', 'miei_log'])
        assert (work / "miei_log" / "prova_engine.log").exists()

    def test_no_logs_dir_is_created_in_the_cwd(self, work):
        """Il sintomo della issue: `./logs` nasceva lo stesso, nel cwd."""
        _run(['main.py', 'prova.yml', 'out.aif',
              '--renderer', 'numpy', '--log-dir', 'miei_log'])
        assert not (work / "logs").exists()

    def test_the_error_message_names_the_requested_dir(self, work, capsys):
        """La riga 'Dettagli:' e' l'unico indirizzo che l'utente riceve."""
        _run(['main.py', 'prova.yml', 'out.aif',
              '--renderer', 'numpy', '--log-dir', 'miei_log'])
        dettagli = [
            line for line in capsys.readouterr().out.splitlines()
            if 'Dettagli:' in line
        ]
        assert dettagli, "nessuna riga 'Dettagli:' nell'output"
        assert 'miei_log' in dettagli[0]

    def test_the_clip_log_follows_too(self, work):
        """Il clip logger crea il file al primo warning, non a configure:
        si guarda dove lo creerebbe."""
        _run(['main.py', 'prova.yml', 'out.aif',
              '--renderer', 'numpy', '--log-dir', 'miei_log'])
        get_clip_logger()
        clip_path = get_clip_log_path()
        assert clip_path is not None
        assert os.path.dirname(os.path.abspath(clip_path)) == str(work / "miei_log")

    def test_an_absolute_dir_outside_the_cwd(self, work, tmp_path):
        """Il caso della issue: un consumatore che tiene l'engine come
        submodule e vuole gli artefatti sotto una sua sottocartella."""
        altrove = tmp_path / "altrove" / "log"
        _run(['main.py', 'prova.yml', 'out.aif',
              '--renderer', 'numpy', '--log-dir', str(altrove)])
        assert (altrove / "prova_engine.log").exists()
        assert not (work / "logs").exists()


class TestDefaultUnchanged:
    """Senza il flag non cambia niente: `logs` nel cwd, come da sempre."""

    def test_logs_stay_in_the_cwd(self, work):
        _run(['main.py', 'prova.yml', 'out.aif', '--renderer', 'numpy'])
        assert (work / "logs" / "prova_engine.log").exists()
