# tests/e2e/test_engine_errors_e2e.py
"""
E2E test per la gerarchia EngineError: invoca src/main.py come subprocess
su YAML invalidi (scritti inline via tmp_path) e verifica:
  - exit code != 0
  - stdout: messaggio user-facing pulito (niente Traceback)
  - log file: messaggio + Traceback

I YAML di test stanno qui (non in configs/), perche' sono fixture di test
e non materiale di lavoro dell'pge.engine.
"""

import os
import shutil
import subprocess
import sys

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

# Mancano `stream_id`, `onset` e `duration`. Le ultime due sono opzionali
# (issue #205 e #220): ometterle non e' un errore, quindi qui il campo
# mancante e' uno solo -> messaggio singolare.
YAML_MISSING_CONTEXT = """\
composition:
  title: "test missing context"
streams:
  - sample: "pino.wav"
    distribution_mode: 'gaussian'
    density: 5
    distribution: [[0,1],[1,1]]
    pointer:
      speed_ratio: 1.0
    grain:
      duration: 0.05
      duration_range: 0.01
"""

# Mancano entrambe le condizioni di esistenza rimaste: `stream_id` e `sample`.
YAML_MISSING_BOTH_CONDITIONS = """\
composition:
  title: "test missing both existence conditions"
streams:
  - distribution_mode: 'gaussian'
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

REAL_SAMPLE = "pino.wav"


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

YAML_INVALID_DEVIATION_PROBABILITY = f"""\
composition:
  title: "test invalid deviation_probability"
streams:
  - stream_id: "stream_bad_deviation_probability"
    onset: 0.0
    duration: 5
    sample: "{REAL_SAMPLE}"
    distribution_mode: 'gaussian'
    density: 5
    distribution: [[0,1],[1,1]]
    deviation_probability: "not_a_valid_deviation_probability"
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
        [sys.executable, 'src/main.py', yaml_path],
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
    assert "Campo obbligatorio mancante" in result.stdout
    assert "'stream_id'" in result.stdout
    # duration (issue #205) e onset (issue #220) omesse non sono un errore:
    # non devono comparire fra i campi mancanti.
    assert "'duration'" not in result.stdout
    assert "'onset'" not in result.stdout
    _assert_log_contains(yaml_abs, "MissingFieldError", ["stream_id"])


@pytest.mark.e2e
def test_e2e_missing_both_existence_conditions_reports_sample_first(tmp_path, cleanup_log):
    """Con `stream_id` e `sample` entrambi assenti l'errore nomina `sample`.

    Il controllo su `sample` in Stream.__init__ precede quello sui campi di
    contesto e si ferma li'. Da #220 le condizioni di esistenza sono due e una
    delle due e' proprio `sample`, quindi dalla CLI il messaggio plurale di
    MissingFieldError non e' piu' raggiungibile: resta esercitato dove nasce
    (tests/shared/test_engine_exceptions.py) e sul percorso che bypassa
    __init__ (tests/core/test_stream.py).
    """
    yaml_abs = _write_yaml(tmp_path, '02b_missing_both_conditions.yml',
                           YAML_MISSING_BOTH_CONDITIONS)
    cleanup_log.append(_log_path_for(yaml_abs))
    result = _run(yaml_abs)
    _assert_clean_user_output(result)
    assert "Campo obbligatorio mancante" in result.stdout
    assert "'sample'" in result.stdout
    _assert_log_contains(yaml_abs, "MissingFieldError", ["sample"])


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
def test_e2e_invalid_deviation_probability(tmp_path, cleanup_log):
    yaml_abs = _write_yaml(tmp_path, '07_invalid_deviation_probability.yml', YAML_INVALID_DEVIATION_PROBABILITY)
    cleanup_log.append(_log_path_for(yaml_abs))
    result = _run(yaml_abs)
    _assert_clean_user_output(result)
    assert "Formato non valido" in result.stdout
    assert "deviation_probability" in result.stdout
    _assert_log_contains(yaml_abs, "InvalidParameterError", ["deviation_probability"])


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
        [sys.executable, 'src/main.py', yaml_abs, '--renderer', 'bogus'],
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


# =============================================================================
# #257: il file di configurazione che non si legge
# =============================================================================
#
# Le tre classi della #257 sono le prime `EngineError` che nascono *prima* che
# esista uno YAML, quindi non hanno una riga `Config:`: il file e' il soggetto
# del head e ripeterlo sotto non aggiungerebbe niente. `_assert_clean_user_output`
# quella riga la pretende, ed e' giusto che la pretenda per tutte le altre --
# da qui l'helper gemello, che ne asserisce l'assenza invece di ignorarla.
#
# E2E e non unit perche' i test della #257 girano tutti sui mock di
# `tests/main_mocks.py`, dove `_handle_engine_error`, il logger engine e
# `__str__` non vengono esercitati. Sono proprio le tre cose che qui si
# incontrano: gli `__str__` di queste classi esistono per non lasciare che
# `OSError.__str__` (o quello di `MarkedYAMLError`, o di `UnicodeDecodeError`)
# riscriva la riga che finisce nel log engine, e questa e' la sola suite che
# quella riga la legge. Il nome di classe atteso e' quello *concreto*, che
# solo il percorso reale produce: `config_read_error()` e `config_parse_error()`
# scelgono la sottoclasse dal tipo della causa, che sotto mock non c'e'.


def _assert_log_message_line(yaml_path: str, testo: str):
    """La riga `[ERROR] <testo>` del log engine, cioe' il `%s` di
    `logger.error("%s\\n%s", err, ...)`: e' `str(err)`, non `user_message()`.

    E' l'asserzione per cui questi casi devono essere e2e. Gli `__str__` delle
    classi della #257 esistono solo per difendere questa riga -- con `filename`
    valorizzato `OSError.__str__` scriverebbe «[Errno 2] No such file or
    directory», `MarkedYAMLError.__str__` il formato di PyYAML con contesto e
    freccia, `UnicodeDecodeError.__str__` la riga del codec -- e la riga finale
    del traceback, che pure porta `str(err)`, qui non discrimina: la scrive
    `format_exc()` e c'e' comunque. Solo il prefisso `[ERROR]` distingue le due.
    """
    contents = open(_log_path_for(yaml_path)).read()
    assert f"[ERROR] {testo}" in contents, (
        f"la riga del log engine non e' il messaggio di dominio: {contents}")


def _assert_clean_config_output(result):
    """Come `_assert_clean_user_output`, ma senza la riga `Config:`."""
    assert result.returncode != 0, f"Atteso exit != 0 (stdout={result.stdout})"
    assert "[ERRORE]" in result.stdout
    assert "Traceback" not in result.stdout, (
        f"Stdout deve restare pulito: {result.stdout}"
    )
    assert "Dettagli:" in result.stdout
    assert "Config:" not in result.stdout, (
        "il file e' gia' il soggetto del head: `Config:` sarebbe la stessa "
        f"riga due volte ({result.stdout})"
    )


YAML_MALFORMATO = """\
composition:
  title: "test yaml malformato"
streams:
  - stream_id: "s1"
    onset: 0.0
   duration: 5
"""


@pytest.mark.e2e
def test_e2e_config_file_not_found(tmp_path, cleanup_log):
    """Lo YAML che non c'e': prima « Errore: file 'x' non trovato», stampato
    da un `except FileNotFoundError` vero solo finche' nessun'altra riga
    dentro quel `try` apriva un secondo file."""
    yaml_abs = str(tmp_path / '50_config_assente.yml')
    cleanup_log.append(_log_path_for(yaml_abs))
    result = _run(yaml_abs)
    _assert_clean_config_output(result)
    assert "File di configurazione non trovato" in result.stdout
    assert '50_config_assente.yml' in result.stdout
    # Il path e' gia' assoluto: `Path cercato:` sarebbe la stessa riga due volte.
    assert "Path cercato:" not in result.stdout
    _assert_log_contains(yaml_abs, "ConfigFileNotFoundError",
                         ['50_config_assente.yml'])
    _assert_log_message_line(yaml_abs, "File di configurazione non trovato")


@pytest.mark.e2e
def test_e2e_config_file_not_found_nomina_il_path_risolto(tmp_path, cleanup_log):
    """Su un path relativo `Path cercato:` compare, ed e' l'informazione che il
    messaggio pre-#257 non dava: «hai lanciato dalla directory sbagliata».

    Il subprocess gira con `cwd=PROJECT_ROOT`, quindi il relativo si risolve
    di la' -- ed e' esattamente il caso che il messaggio serve a chiarire.
    """
    relativo = os.path.join('configs', '50b_config_assente.yml')
    assert not os.path.exists(os.path.join(PROJECT_ROOT, relativo))
    cleanup_log.append(_log_path_for(relativo))
    result = _run(relativo)
    _assert_clean_config_output(result)
    assert "File di configurazione non trovato" in result.stdout
    assert f"Path cercato: {os.path.join(PROJECT_ROOT, relativo)}" in result.stdout


@pytest.mark.e2e
def test_e2e_config_parse_error(tmp_path, cleanup_log):
    """Lo YAML malformato: prima nessuno traduceva `yaml.YAMLError` e usciva
    dal ramo generico come messaggio piu' traceback."""
    yaml_abs = _write_yaml(tmp_path, '51_config_malformato.yml', YAML_MALFORMATO)
    cleanup_log.append(_log_path_for(yaml_abs))
    result = _run(yaml_abs)
    _assert_clean_config_output(result)
    assert "File di configurazione malformato" in result.stdout
    assert "Riga/colonna:" in result.stdout
    assert "Dettaglio:" in result.stdout
    # `problem_mark` di PyYAML e' 0-based: la riga stampata e' quella
    # dell'editor, non una sopra.
    assert "  Riga/colonna: 6:4" in result.stdout, result.stdout
    # La sottoclasse che porta anche `yaml.MarkedYAMLError`: la sceglie
    # `config_parse_error()` dal tipo della causa, quindi solo il percorso
    # reale la produce.
    _assert_log_contains(yaml_abs, "ConfigMarkedParseError",
                         ['51_config_malformato.yml'])
    _assert_log_message_line(yaml_abs, "File di configurazione malformato")


@pytest.mark.e2e
def test_e2e_config_con_un_carattere_rifiutato(tmp_path, cleanup_log):
    """Un carattere di controllo nel file: `yaml.reader.ReaderError`, l'unico
    `yaml.YAMLError` del caricamento che non porti riga/colonna.

    Due cose che solo il percorso reale mostra. La classe concreta nel log --
    `config_parse_error()` la sceglie dal tipo della causa, che sotto mock non
    c'e'. E il blocco del messaggio: `ReaderError.__str__` e' due righe
    *sempre*, quindi e' l'unica causa che possa far uscire una riga dal
    formato `[ERRORE] head` + `  <Campo>:      <valore>` -- proprio fra
    `Dettaglio:` e il `Dettagli:` che `_handle_engine_error` appende sotto.
    """
    import re

    yaml_abs = str(tmp_path / '55_config_carattere.yml')
    with open(yaml_abs, 'w', encoding='utf-8') as f:
        f.write('composition:\n  title: "a\x07b"\nstreams: []\n')
    cleanup_log.append(_log_path_for(yaml_abs))
    result = _run(yaml_abs)
    _assert_clean_config_output(result)
    assert "File di configurazione malformato" in result.stdout
    assert "special characters are not allowed" in result.stdout
    # Il seguito e' incolonnato sotto il valore, non a capo senza nome di campo.
    corpo = result.stdout.split(
        "[ERRORE] File di configurazione malformato")[1].split("\n")[1:]
    for riga in corpo:
        if not riga.strip():
            break
        assert (re.match(r'^  \S[^:]*: +\S', riga)
                or riga.startswith(' ' * 16)), (
            f"riga senza nome di campo e non incolonnata: {riga!r}")
    _assert_log_contains(yaml_abs, "ConfigReaderParseError",
                         ['55_config_carattere.yml'])
    _assert_log_message_line(yaml_abs, "File di configurazione malformato")


@pytest.mark.e2e
def test_e2e_config_non_decodificabile(tmp_path, cleanup_log):
    """Un `.yml` salvato in latin-1: `open()` e' in modalita' testo e su UTF-8
    dichiarato, quindi lo rifiuta prima che PyYAML veda un byte."""
    yaml_abs = str(tmp_path / '52_config_latin1.yml')
    with open(yaml_abs, 'wb') as f:
        f.write('# perch\xe8 no\nstreams: []\n'.encode('latin-1'))
    cleanup_log.append(_log_path_for(yaml_abs))
    result = _run(yaml_abs)
    _assert_clean_config_output(result)
    assert "File di configurazione malformato" in result.stdout
    # Il codec nominato e' sempre utf-8: non dipende dal locale della macchina.
    assert "'utf-8' codec can't decode byte" in result.stdout
    _assert_log_contains(yaml_abs, "ConfigUnicodeParseError",
                         ['52_config_latin1.yml'])
    _assert_log_message_line(yaml_abs, "File di configurazione malformato")


@pytest.mark.e2e
def test_e2e_config_e_una_directory(tmp_path, cleanup_log):
    """`pge configs/ out.wav`, il typo che la tab-completion fabbrica da sola.

    `IsADirectoryError` non e' un `FileNotFoundError` ne' un `yaml.YAMLError`:
    era l'ultimo modo di sbagliare il path del proprio YAML a uscire dal ramo
    generico come traceback, e il piu' probabile.
    """
    directory = tmp_path / '53_config_directory'
    directory.mkdir()
    cleanup_log.append(_log_path_for(str(directory)))
    result = _run(str(directory))
    _assert_clean_config_output(result)
    assert "File di configurazione non leggibile" in result.stdout
    # `strerror` della causa: e' l'unica cosa che distingue EISDIR da EACCES.
    assert "Dettaglio:    Is a directory" in result.stdout
    assert "Path cercato:" not in result.stdout
    _assert_log_contains(str(directory), "ConfigIsADirectoryError",
                         ['53_config_directory'])
    _assert_log_message_line(str(directory),
                             "File di configurazione non leggibile")


@pytest.mark.e2e
def test_e2e_config_directory_con_la_barra_finale_non_nomina_il_log_col_basename(
        tmp_path, cleanup_log):
    """La forma che la tab-completion produce davvero: `pge configs/ out.wav`.

    Il gemello qui sopra passa il path *senza* barra, e la barra non e' un
    dettaglio cosmetico: `os.path.basename('configs/')` e' la stringa vuota,
    quindi `yaml_basename` esce vuoto da `cli.main()` e
    `configure_engine_logger` ripiega sul timestamp. Il messaggio resta lo
    stesso, il nome del log no -- e la Sez. 4 di `docs/reference/errors.md`,
    che e' un censimento di output reali, mostrava proprio il comando con la
    barra accanto a un `logs/configs_engine.log` che quel comando non produce:
    l'unico messaggio del censimento che nominasse un file dove l'utente poi
    non lo trova.

    Nessun `_log_path_for` qui: quella funzione ricalcola il basename come fa
    la CLI e su una barra finale risponderebbe `logs/_engine.log`, cioe' la
    stessa deduzione sbagliata. Il path si legge dalla riga «Dettagli:», che e'
    l'unico posto dove l'utente lo trova.
    """
    import re

    directory = tmp_path / '54_config_directory_slash'
    directory.mkdir()

    result = _run(str(directory) + os.sep)

    riga = re.search(r'^  Dettagli:\s+(\S+)$', result.stdout, re.M)
    assert riga, f"nessuna riga «Dettagli:» in stdout: {result.stdout}"
    log = riga.group(1)
    cleanup_log.append(log if os.path.isabs(log)
                       else os.path.join(PROJECT_ROOT, log))

    _assert_clean_config_output(result)
    assert "File di configurazione non leggibile" in result.stdout
    assert "Dettaglio:    Is a directory" in result.stdout

    nome = os.path.basename(log)
    assert nome != f'{directory.name}_engine.log', (
        "il log porterebbe il basename della directory: se questo diventa "
        "vero, l'esempio della Sez. 4 va rimesso su `logs/<dir>_engine.log`")
    assert re.fullmatch(r'\d{8}_\d{6}_engine\.log', nome), (
        f"ripiego di configure_engine_logger atteso sul timestamp: {nome}")
