# tests/e2e/test_engine_errors_e2e.py
"""
E2E test per la gerarchia EngineError: invoca src/main.py come subprocess
sui YAML in configs/error_tests/ e verifica:
  - exit code 1
  - stdout: messaggio user-facing pulito (niente Traceback)
  - log file: messaggio + Traceback
"""

import os
import subprocess

import pytest


PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..')
)
ERROR_DIR = os.path.join(PROJECT_ROOT, 'configs', 'error_tests')
LOG_DIR = os.path.join(PROJECT_ROOT, 'logs')


def _run(yaml_path: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ['python', 'src/main.py', yaml_path],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _log_path_for(yaml_path: str) -> str:
    name = os.path.splitext(os.path.basename(yaml_path))[0]
    return os.path.join(LOG_DIR, f'{name}_engine.log')


def _assert_clean_user_output(result, yaml_rel: str):
    """Exit non-zero, stdout pulito (no Traceback), [ERRORE] presente."""
    assert result.returncode != 0, f"Atteso exit != 0 per {yaml_rel}"
    assert "[ERRORE]" in result.stdout, f"Manca [ERRORE] in stdout: {result.stdout}"
    assert "Traceback" not in result.stdout, (
        f"Stdout contiene Traceback (deve stare solo nel log): {result.stdout}"
    )
    assert "Dettagli:" in result.stdout
    assert "Config:" in result.stdout


def _assert_log_contains(yaml_path: str, error_class_name: str, must_contain: list[str]):
    log = _log_path_for(yaml_path)
    assert os.path.exists(log), f"Log file non creato: {log}"
    contents = open(log).read()
    assert error_class_name in contents, f"{error_class_name} non in log {log}"
    assert "Traceback" in contents, f"Traceback assente in log {log}"
    for s in must_contain:
        assert s in contents, f"'{s}' non in log {log}"


@pytest.mark.e2e
def test_e2e_missing_sample():
    yaml_rel = 'configs/error_tests/01_missing_sample.yml'
    yaml_abs = os.path.join(PROJECT_ROOT, yaml_rel)
    result = _run(yaml_abs)
    _assert_clean_user_output(result, yaml_rel)
    assert "Campo obbligatorio mancante" in result.stdout
    assert "'sample'" in result.stdout
    assert "stream_no_sample" in result.stdout
    _assert_log_contains(yaml_abs, "MissingFieldError", ["sample"])


@pytest.mark.e2e
def test_e2e_missing_context_fields():
    yaml_rel = 'configs/error_tests/02_missing_context_fields.yml'
    yaml_abs = os.path.join(PROJECT_ROOT, yaml_rel)
    result = _run(yaml_abs)
    _assert_clean_user_output(result, yaml_rel)
    assert "Campi obbligatori mancanti" in result.stdout
    assert "'duration'" in result.stdout
    assert "'onset'" in result.stdout
    assert "stream_no_ctx" in result.stdout
    _assert_log_contains(yaml_abs, "MissingFieldError", ["duration", "onset"])


@pytest.mark.e2e
def test_e2e_invalid_grain_reverse():
    yaml_rel = 'configs/error_tests/03_invalid_grain_reverse.yml'
    yaml_abs = os.path.join(PROJECT_ROOT, yaml_rel)
    result = _run(yaml_abs)
    _assert_clean_user_output(result, yaml_rel)
    assert "Valore invalido per 'grain.reverse'" in result.stdout
    assert "True" in result.stdout
    assert "stream_bad_reverse" in result.stdout
    _assert_log_contains(yaml_abs, "InvalidFieldValueError", ["grain.reverse"])


@pytest.mark.e2e
def test_e2e_sample_not_found():
    yaml_rel = 'configs/error_tests/04_sample_not_found.yml'
    yaml_abs = os.path.join(PROJECT_ROOT, yaml_rel)
    result = _run(yaml_abs)
    _assert_clean_user_output(result, yaml_rel)
    assert "Sample non trovato" in result.stdout
    assert "pinuzzo_inesistente.wav" in result.stdout
    assert "stream_missing_file" in result.stdout
    _assert_log_contains(yaml_abs, "SampleNotFoundError", ["pinuzzo_inesistente.wav"])
