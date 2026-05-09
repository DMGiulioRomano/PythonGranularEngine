# tests/e2e/test_engine_errors_e2e.py
"""
E2E test per la gerarchia EngineError: invoca src/main.py come subprocess
su YAML invalidi (scritti inline via tmp_path) e verifica:
  - exit code != 0
  - stdout: messaggio user-facing pulito (niente Traceback)
  - log file: messaggio + Traceback

I YAML di test stanno qui (non in configs/), perche' sono fixture di test
e non materiale di lavoro dell'engine.
"""

import os
import shutil
import subprocess

import pytest


PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..')
)


YAML_MISSING_SAMPLE = """\
composition:
  title: "test missing sample"
streams:
  - stream_id: "stream_no_sample"
    onset: 0.0
    duration: 5
    sample:
    distribution_mode: 'gaussian'
    density: 5
    distribution: [[0,1],[1,1]]
    pointer:
      speed_ratio: 1.0
    grain:
      duration: 0.05
      duration_range: 0.01
"""

YAML_MISSING_CONTEXT = """\
composition:
  title: "test missing context"
streams:
  - stream_id: "stream_no_ctx"
    sample: "pino.wav"
    distribution_mode: 'gaussian'
    density: 5
    distribution: [[0,1],[1,1]]
    pointer:
      speed_ratio: 1.0
    grain:
      duration: 0.05
      duration_range: 0.01
"""

YAML_INVALID_GRAIN_REVERSE = """\
composition:
  title: "test invalid grain.reverse"
streams:
  - stream_id: "stream_bad_reverse"
    onset: 0.0
    duration: 5
    sample: "pino.wav"
    distribution_mode: 'gaussian'
    density: 5
    distribution: [[0,1],[1,1]]
    pointer:
      speed_ratio: 1.0
    grain:
      duration: 0.05
      duration_range: 0.01
      reverse: true
"""

REAL_SAMPLE = "001-0_0-3_0.wav"


YAML_INVALID_PARAM_FORMAT = f"""\
composition:
  title: "test invalid param format"
streams:
  - stream_id: "stream_bad_density"
    onset: 0.0
    duration: 5
    sample: "{REAL_SAMPLE}"
    distribution_mode: 'gaussian'
    density: "not_a_number"
    distribution: [[0,1],[1,1]]
    pointer:
      speed_ratio: 1.0
    grain:
      duration: 0.05
      duration_range: 0.01
"""

YAML_PARAM_OUT_OF_BOUNDS = f"""\
composition:
  title: "test param bound violation"
streams:
  - stream_id: "stream_bad_bound"
    onset: 0.0
    duration: 5
    sample: "{REAL_SAMPLE}"
    distribution_mode: 'gaussian'
    density: 999999
    distribution: [[0,1],[1,1]]
    pointer:
      speed_ratio: 1.0
    grain:
      duration: 0.05
      duration_range: 0.01
"""

YAML_INVALID_DEPHASE = f"""\
composition:
  title: "test invalid dephase"
streams:
  - stream_id: "stream_bad_dephase"
    onset: 0.0
    duration: 5
    sample: "{REAL_SAMPLE}"
    distribution_mode: 'gaussian'
    density: 5
    distribution: [[0,1],[1,1]]
    dephase: "not_a_valid_dephase"
    pointer:
      speed_ratio: 1.0
    grain:
      duration: 0.05
      duration_range: 0.01
"""

YAML_INVALID_DISTRIBUTION = f"""\
composition:
  title: "test invalid distribution mode"
streams:
  - stream_id: "stream_bad_dist"
    onset: 0.0
    duration: 5
    sample: "{REAL_SAMPLE}"
    distribution_mode: 'bogus_distribution'
    density: 5
    distribution: [[0,1],[1,1]]
    pointer:
      speed_ratio: 1.0
    grain:
      duration: 0.05
      duration_range: 0.01
"""

YAML_SAMPLE_NOT_FOUND = """\
composition:
  title: "test sample not found"
streams:
  - stream_id: "stream_missing_file"
    onset: 0.0
    duration: 5
    sample: "pinuzzo_inesistente.wav"
    distribution_mode: 'gaussian'
    density: 5
    distribution: [[0,1],[1,1]]
    pointer:
      speed_ratio: 1.0
    grain:
      duration: 0.05
      duration_range: 0.01
"""


def _write_yaml(tmp_path, name: str, content: str) -> str:
    """
    Scrive un YAML dentro PROJECT_ROOT/<tmp>/ perche' src/main.py costruisce
    log path da basename(yaml) e logs/ vive nel CWD del subprocess.
    Ritorna il path assoluto (anche relativo al PROJECT_ROOT).
    """
    f = tmp_path / name
    f.write_text(content)
    return str(f)


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
    return os.path.join(PROJECT_ROOT, 'logs', f'{name}_engine.log')


def _assert_clean_user_output(result):
    assert result.returncode != 0, f"Atteso exit != 0 (stdout={result.stdout})"
    assert "[ERRORE]" in result.stdout
    assert "Traceback" not in result.stdout, (
        f"Stdout deve restare pulito: {result.stdout}"
    )
    assert "Dettagli:" in result.stdout
    assert "Config:" in result.stdout


def _assert_log_contains(yaml_path: str, error_class: str, must_contain: list[str]):
    log = _log_path_for(yaml_path)
    assert os.path.exists(log), f"Log non creato: {log}"
    contents = open(log).read()
    assert error_class in contents
    assert "Traceback" in contents
    for s in must_contain:
        assert s in contents


@pytest.fixture
def cleanup_log():
    """Rimuove il log file creato dal test (basename univoco per test)."""
    created = []
    yield created
    for p in created:
        if os.path.exists(p):
            os.remove(p)


@pytest.mark.e2e
def test_e2e_missing_sample(tmp_path, cleanup_log):
    yaml_abs = _write_yaml(tmp_path, '01_missing_sample.yml', YAML_MISSING_SAMPLE)
    cleanup_log.append(_log_path_for(yaml_abs))
    result = _run(yaml_abs)
    _assert_clean_user_output(result)
    assert "Campo obbligatorio mancante" in result.stdout
    assert "'sample'" in result.stdout
    assert "stream_no_sample" in result.stdout
    _assert_log_contains(yaml_abs, "MissingFieldError", ["sample"])


@pytest.mark.e2e
def test_e2e_missing_context_fields(tmp_path, cleanup_log):
    yaml_abs = _write_yaml(tmp_path, '02_missing_context.yml', YAML_MISSING_CONTEXT)
    cleanup_log.append(_log_path_for(yaml_abs))
    result = _run(yaml_abs)
    _assert_clean_user_output(result)
    assert "Campi obbligatori mancanti" in result.stdout
    assert "'duration'" in result.stdout
    assert "'onset'" in result.stdout
    assert "stream_no_ctx" in result.stdout
    _assert_log_contains(yaml_abs, "MissingFieldError", ["duration", "onset"])


@pytest.mark.e2e
def test_e2e_invalid_grain_reverse(tmp_path, cleanup_log):
    yaml_abs = _write_yaml(tmp_path, '03_invalid_reverse.yml', YAML_INVALID_GRAIN_REVERSE)
    cleanup_log.append(_log_path_for(yaml_abs))
    result = _run(yaml_abs)
    _assert_clean_user_output(result)
    assert "Valore invalido per 'grain.reverse'" in result.stdout
    assert "True" in result.stdout
    assert "stream_bad_reverse" in result.stdout
    _assert_log_contains(yaml_abs, "InvalidFieldValueError", ["grain.reverse"])


@pytest.mark.e2e
def test_e2e_invalid_parameter_format(tmp_path, cleanup_log):
    yaml_abs = _write_yaml(tmp_path, '05_invalid_param.yml', YAML_INVALID_PARAM_FORMAT)
    cleanup_log.append(_log_path_for(yaml_abs))
    result = _run(yaml_abs)
    _assert_clean_user_output(result)
    assert "Formato non valido" in result.stdout
    assert "density" in result.stdout
    assert "stream_bad_density" in result.stdout
    _assert_log_contains(yaml_abs, "InvalidParameterError", ["density"])


@pytest.mark.e2e
def test_e2e_parameter_out_of_bounds(tmp_path, cleanup_log):
    yaml_abs = _write_yaml(tmp_path, '06_param_bound.yml', YAML_PARAM_OUT_OF_BOUNDS)
    cleanup_log.append(_log_path_for(yaml_abs))
    result = _run(yaml_abs)
    _assert_clean_user_output(result)
    assert "fuori bounds" in result.stdout
    assert "density" in result.stdout
    assert "stream_bad_bound" in result.stdout
    _assert_log_contains(yaml_abs, "ParameterBoundError", ["density"])


@pytest.mark.e2e
def test_e2e_invalid_dephase(tmp_path, cleanup_log):
    yaml_abs = _write_yaml(tmp_path, '07_invalid_dephase.yml', YAML_INVALID_DEPHASE)
    cleanup_log.append(_log_path_for(yaml_abs))
    result = _run(yaml_abs)
    _assert_clean_user_output(result)
    assert "Formato non valido" in result.stdout
    assert "dephase" in result.stdout
    _assert_log_contains(yaml_abs, "InvalidParameterError", ["dephase"])


@pytest.mark.e2e
def test_e2e_invalid_distribution_strategy(tmp_path, cleanup_log):
    yaml_abs = _write_yaml(tmp_path, '08_invalid_distribution.yml', YAML_INVALID_DISTRIBUTION)
    cleanup_log.append(_log_path_for(yaml_abs))
    result = _run(yaml_abs)
    assert result.returncode != 0, f"Atteso exit != 0 (stdout={result.stdout})"
    assert "[ERRORE]" in result.stdout
    assert "Traceback" not in result.stdout
    assert "Strategia distribution non trovata" in result.stdout
    assert "bogus_distribution" in result.stdout
    _assert_log_contains(yaml_abs, "StrategyNotFoundError", ["bogus_distribution"])


@pytest.mark.e2e
def test_e2e_sample_not_found(tmp_path, cleanup_log):
    yaml_abs = _write_yaml(tmp_path, '04_sample_not_found.yml', YAML_SAMPLE_NOT_FOUND)
    cleanup_log.append(_log_path_for(yaml_abs))
    result = _run(yaml_abs)
    _assert_clean_user_output(result)
    assert "Sample non trovato" in result.stdout
    assert "pinuzzo_inesistente.wav" in result.stdout
    assert "stream_missing_file" in result.stdout
    _assert_log_contains(yaml_abs, "SampleNotFoundError", ["pinuzzo_inesistente.wav"])


# =============================================================================
# PR4: Rendering errors
# =============================================================================

YAML_VALID_RENDERER = f"""\
composition:
  title: "test valid base"
streams:
  - stream_id: "s1"
    onset: 0.0
    duration: 1
    sample: "{REAL_SAMPLE}"
    distribution_mode: 'gaussian'
    density: 5
    distribution: [[0,1],[1,1]]
    pointer:
      speed_ratio: 1.0
    grain:
      duration: 0.05
      duration_range: 0.01
"""

YAML_INVALID_WINDOW = f"""\
composition:
  title: "test invalid window"
streams:
  - stream_id: "stream_bad_window"
    onset: 0.0
    duration: 5
    sample: "{REAL_SAMPLE}"
    distribution_mode: 'gaussian'
    density: 5
    distribution: [[0,1],[1,1]]
    pointer:
      speed_ratio: 1.0
    grain:
      duration: 0.05
      duration_range: 0.01
      envelope: "bogus_window_name_xyz"
"""


@pytest.mark.e2e
def test_e2e_invalid_renderer(tmp_path, cleanup_log):
    """--renderer bogus produce InvalidRendererError user-facing pulito."""
    yaml_abs = _write_yaml(tmp_path, '09_invalid_renderer.yml', YAML_VALID_RENDERER)
    cleanup_log.append(_log_path_for(yaml_abs))
    result = subprocess.run(
        ['python', 'src/main.py', yaml_abs, '--renderer', 'bogus'],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode != 0
    assert "[ERRORE]" in result.stdout
    assert "Traceback" not in result.stdout
    assert "Renderer non supportato" in result.stdout
    assert "bogus" in result.stdout


@pytest.mark.e2e
def test_e2e_invalid_window(tmp_path, cleanup_log):
    """envelope name sconosciuto produce InvalidWindowError user-facing pulito."""
    yaml_abs = _write_yaml(tmp_path, '10_invalid_window.yml', YAML_INVALID_WINDOW)
    cleanup_log.append(_log_path_for(yaml_abs))
    result = _run(yaml_abs)
    assert result.returncode != 0
    assert "[ERRORE]" in result.stdout
    assert "Traceback" not in result.stdout
    assert "bogus_window_name_xyz" in result.stdout
    _assert_log_contains(yaml_abs, "InvalidWindowError", ["bogus_window_name_xyz"])


# =============================================================================
# Issue #46 - PR1: controllers raises -> EngineError (e2e)
# =============================================================================

YAML_CURVE_EXCEEDS_RANGE = f"""\
composition:
  title: "test curve exceeds range"
streams:
  - stream_id: "stream_curve_bad"
    onset: 0.0
    duration: 5
    sample: "{REAL_SAMPLE}"
    distribution_mode: 'gaussian'
    density: 5
    distribution: [[0,1],[1,1]]
    pointer:
      speed_ratio: 1.0
    grain:
      duration: 0.05
      duration_range: 0.01
      envelope:
        from: hanning
        to: expodec
        curve: [[0, 0], [99, 1]]
"""

YAML_MULTISTATE_UNSORTED = f"""\
composition:
  title: "test multistate unsorted"
streams:
  - stream_id: "stream_ms_unsorted"
    onset: 0.0
    duration: 5
    sample: "{REAL_SAMPLE}"
    distribution_mode: 'gaussian'
    density: 5
    distribution: [[0,1],[1,1]]
    pointer:
      speed_ratio: 1.0
    grain:
      duration: 0.05
      duration_range: 0.01
      envelope:
        states:
          - [0.5, hanning]
          - [0.2, bartlett]
        curve: [[0, 0], [5, 1]]
"""

@pytest.mark.e2e
def test_e2e_curve_exceeds_range(tmp_path, cleanup_log):
    yaml_abs = _write_yaml(tmp_path, '46_curve_exceeds.yml', YAML_CURVE_EXCEEDS_RANGE)
    cleanup_log.append(_log_path_for(yaml_abs))
    result = _run(yaml_abs)
    assert result.returncode != 0
    assert "[ERRORE]" in result.stdout
    assert "Traceback" not in result.stdout
    assert "window" in result.stdout.lower()
    _assert_log_contains(yaml_abs, "InvalidStrategyConfigError", ["window"])


@pytest.mark.e2e
def test_e2e_multistate_unsorted(tmp_path, cleanup_log):
    """Multistate states non in ordine crescente -> InvalidStrategyConfigError.

    Note: i casi multistate <2 stati e pitch/density exclusive group sono
    coperti dai test unit -- la pipeline YAML li intercetta prima
    (parse layer per multistate; orchestrator priorita' per pitch/density),
    quindi non sono raggiungibili tramite e2e su src/main.py.
    """
    yaml_abs = _write_yaml(tmp_path, '46_ms_unsorted.yml', YAML_MULTISTATE_UNSORTED)
    cleanup_log.append(_log_path_for(yaml_abs))
    result = _run(yaml_abs)
    assert result.returncode != 0
    assert "[ERRORE]" in result.stdout
    assert "Traceback" not in result.stdout
    _assert_log_contains(yaml_abs, "InvalidStrategyConfigError", ["window_multistate"])
