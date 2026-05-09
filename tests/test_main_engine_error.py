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


def test_handle_engine_error_works_for_missing_field_error(tmp_path, capsys):
    """Handler EngineError gestisce anche MissingFieldError (issue #38)."""
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
    from main import _handle_engine_error
    from shared.exceptions import MissingFieldError
    from shared.logger import configure_engine_logger, get_engine_log_path

    configure_engine_logger(yaml_name='broken_cfg', log_dir=str(tmp_path))

    err = MissingFieldError(field='sample', hint="specificare il file wav")
    err.stream_id = 'drone_a'
    err.config_file = 'configs/broken.yml'

    try:
        raise err
    except MissingFieldError as e:
        _handle_engine_error(e)

    captured = capsys.readouterr()
    assert "Campo obbligatorio mancante" in captured.out
    assert "sample" in captured.out
    assert "drone_a" in captured.out
    assert "Dettagli:" in captured.out

    log_path = get_engine_log_path()
    for h in __import__('logging').getLogger('engine').handlers:
        h.flush()
    contents = open(log_path).read()
    assert "MissingFieldError" in contents
    assert "Traceback" in contents


def test_handle_engine_error_works_for_invalid_field_value_error(tmp_path, capsys):
    """Handler EngineError gestisce anche InvalidFieldValueError (issue #38)."""
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
    from main import _handle_engine_error
    from shared.exceptions import InvalidFieldValueError
    from shared.logger import configure_engine_logger, get_engine_log_path

    configure_engine_logger(yaml_name='broken_val', log_dir=str(tmp_path))

    err = InvalidFieldValueError(field='grain.reverse', value=True, hint="lascia vuoto")
    err.stream_id = 'sx'

    try:
        raise err
    except InvalidFieldValueError as e:
        _handle_engine_error(e)

    captured = capsys.readouterr()
    assert "grain.reverse" in captured.out
    assert "True" in captured.out
    assert "Dettagli:" in captured.out


def test_handle_engine_error_works_for_invalid_parameter_error(tmp_path, capsys):
    """Handler EngineError gestisce InvalidParameterError (issue #38, PR2)."""
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
    from main import _handle_engine_error
    from shared.exceptions import InvalidParameterError
    from shared.logger import configure_engine_logger, get_engine_log_path

    configure_engine_logger(yaml_name='broken_param', log_dir=str(tmp_path))

    err = InvalidParameterError(param_name='density.value', value='abc', hint="atteso numero")
    err.stream_id = 'drone_a'

    try:
        raise err
    except InvalidParameterError as e:
        _handle_engine_error(e)

    captured = capsys.readouterr()
    assert "density.value" in captured.out
    assert "Dettagli:" in captured.out

    log_path = get_engine_log_path()
    for h in __import__('logging').getLogger('engine').handlers:
        h.flush()
    contents = open(log_path).read()
    assert "InvalidParameterError" in contents
    assert "Traceback" in contents


def test_handle_engine_error_works_for_parameter_bound_error(tmp_path, capsys):
    """Handler EngineError gestisce ParameterBoundError (issue #38, PR2)."""
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
    from main import _handle_engine_error
    from shared.exceptions import ParameterBoundError
    from shared.logger import configure_engine_logger, get_engine_log_path

    configure_engine_logger(yaml_name='broken_bound', log_dir=str(tmp_path))

    err = ParameterBoundError(
        param_name='density', value_type='value',
        value=999.0, min_bound=0.0, max_bound=100.0,
    )
    err.stream_id = 'drone_b'

    try:
        raise err
    except ParameterBoundError as e:
        _handle_engine_error(e)

    captured = capsys.readouterr()
    assert "density" in captured.out
    assert "999" in captured.out
    assert "Dettagli:" in captured.out

    log_path = get_engine_log_path()
    for h in __import__('logging').getLogger('engine').handlers:
        h.flush()
    contents = open(log_path).read()
    assert "ParameterBoundError" in contents
    assert "Traceback" in contents


def test_handle_engine_error_works_for_strategy_not_found_error(tmp_path, capsys):
    """Handler EngineError gestisce StrategyNotFoundError (issue #38, PR3)."""
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
    from main import _handle_engine_error
    from shared.exceptions import StrategyNotFoundError
    from shared.logger import configure_engine_logger, get_engine_log_path

    configure_engine_logger(yaml_name='broken_strategy', log_dir=str(tmp_path))

    err = StrategyNotFoundError(
        strategy_kind="voice_pitch", name="bogus", available=["step", "range"],
    )
    err.stream_id = 'drone_a'
    err.config_file = 'configs/broken.yml'

    try:
        raise err
    except StrategyNotFoundError as e:
        _handle_engine_error(e)

    captured = capsys.readouterr()
    assert "voice_pitch" in captured.out
    assert "bogus" in captured.out
    assert "Dettagli:" in captured.out

    log_path = get_engine_log_path()
    for h in __import__('logging').getLogger('engine').handlers:
        h.flush()
    contents = open(log_path).read()
    assert "StrategyNotFoundError" in contents
    assert "Traceback" in contents


def test_handle_engine_error_works_for_invalid_strategy_config_error(tmp_path, capsys):
    """Handler EngineError gestisce InvalidStrategyConfigError (issue #38, PR3)."""
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
    from main import _handle_engine_error
    from shared.exceptions import InvalidStrategyConfigError
    from shared.logger import configure_engine_logger, get_engine_log_path

    configure_engine_logger(yaml_name='broken_strategy_cfg', log_dir=str(tmp_path))

    err = InvalidStrategyConfigError(
        strategy_kind="voice_pitch", field="chord", value="bogus_chord",
        hint="usa dom7, maj7",
    )
    err.stream_id = 'drone_a'

    try:
        raise err
    except InvalidStrategyConfigError as e:
        _handle_engine_error(e)

    captured = capsys.readouterr()
    assert "voice_pitch" in captured.out
    assert "chord" in captured.out
    assert "bogus_chord" in captured.out
    assert "Dettagli:" in captured.out

    log_path = get_engine_log_path()
    for h in __import__('logging').getLogger('engine').handlers:
        h.flush()
    contents = open(log_path).read()
    assert "InvalidStrategyConfigError" in contents
    assert "Traceback" in contents


def test_handle_engine_error_works_for_invalid_renderer_error(tmp_path, capsys):
    """Handler EngineError gestisce InvalidRendererError (issue #38, PR4)."""
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
    from main import _handle_engine_error
    from shared.exceptions import InvalidRendererError
    from shared.logger import configure_engine_logger, get_engine_log_path

    configure_engine_logger(yaml_name='broken_renderer', log_dir=str(tmp_path))

    err = InvalidRendererError(renderer_type="bogus", available=["numpy", "csound"])
    err.config_file = 'configs/broken.yml'

    try:
        raise err
    except InvalidRendererError as e:
        _handle_engine_error(e)

    captured = capsys.readouterr()
    assert "bogus" in captured.out
    assert "numpy" in captured.out
    assert "Dettagli:" in captured.out

    log_path = get_engine_log_path()
    for h in __import__('logging').getLogger('engine').handlers:
        h.flush()
    contents = open(log_path).read()
    assert "InvalidRendererError" in contents
    assert "Traceback" in contents


def test_handle_engine_error_works_for_csound_render_error(tmp_path, capsys):
    """Handler EngineError gestisce CsoundRenderError (issue #38, PR4)."""
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
    from main import _handle_engine_error
    from shared.exceptions import CsoundRenderError
    from shared.logger import configure_engine_logger, get_engine_log_path

    configure_engine_logger(yaml_name='broken_csound', log_dir=str(tmp_path))

    err = CsoundRenderError(
        returncode=1,
        command=["csound", "score.csd"],
        stderr="orchestra error",
    )
    err.stream_id = 'drone_a'

    try:
        raise err
    except CsoundRenderError as e:
        _handle_engine_error(e)

    captured = capsys.readouterr()
    assert "exit code 1" in captured.out
    assert "Dettagli:" in captured.out

    log_path = get_engine_log_path()
    for h in __import__('logging').getLogger('engine').handlers:
        h.flush()
    contents = open(log_path).read()
    assert "CsoundRenderError" in contents
    assert "Traceback" in contents


def test_handle_engine_error_works_for_invalid_window_error(tmp_path, capsys):
    """Handler EngineError gestisce InvalidWindowError (issue #38, PR4)."""
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
    from main import _handle_engine_error
    from shared.exceptions import InvalidWindowError
    from shared.logger import configure_engine_logger, get_engine_log_path

    configure_engine_logger(yaml_name='broken_window', log_dir=str(tmp_path))

    err = InvalidWindowError(name="bogus", available=["hanning"])
    err.stream_id = 'sx'

    try:
        raise err
    except InvalidWindowError as e:
        _handle_engine_error(e)

    captured = capsys.readouterr()
    assert "bogus" in captured.out
    assert "Dettagli:" in captured.out
