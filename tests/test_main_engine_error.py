# =============================================================================
# tests/test_main_engine_error.py
# =============================================================================
"""
Test per il handler EngineError in main.py (issue #33, step 6).

Verifica che:
- terminale riceva user_message() pulito + riga "Dettagli: <log_path>"
- file di log contenga messaggio + traceback
"""
import os
import sys

import pytest


def test_handle_engine_error_prints_user_message_and_logs_traceback(tmp_path, capsys):
    """Handler stampa user_message su stdout e logga su file."""
    # Carica handler senza eseguire main()
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
    from main import _handle_engine_error
    from shared.exceptions import SampleNotFoundError
    from shared.logger import configure_engine_logger, get_engine_log_path

    configure_engine_logger(yaml_name='broken', log_dir=str(tmp_path))

    err = SampleNotFoundError(filename='pino.wav', search_path='./refs/')
    err.stream_id = 'drone_a'
    err.config_file = 'configs/broken.yml'

    try:
        raise err
    except SampleNotFoundError as e:
        _handle_engine_error(e)

    captured = capsys.readouterr()
    assert "Sample non trovato: 'pino.wav'" in captured.out
    assert "drone_a" in captured.out
    assert "configs/broken.yml" in captured.out
    assert "Dettagli:" in captured.out

    log_path = get_engine_log_path()
    for h in __import__('logging').getLogger('engine').handlers:
        h.flush()
    contents = open(log_path).read()
    assert "SampleNotFoundError" in contents
    assert "pino.wav" in contents
    assert "Traceback" in contents
