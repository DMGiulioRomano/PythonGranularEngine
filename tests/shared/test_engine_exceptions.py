# =============================================================================
# tests/shared/test_engine_exceptions.py
# =============================================================================
"""
Test per la gerarchia di EngineError e SampleNotFoundError (issue #33).

Verifica che gli errori engine producano messaggi user-facing puliti
con il context disponibile a ciascun layer.
"""
import pytest


def test_sample_not_found_user_message_contains_filename_and_path():
    """SampleNotFoundError espone un messaggio leggibile con file e path cercato."""
    from pge.shared.exceptions import SampleNotFoundError

    err = SampleNotFoundError(filename="pino.wav", search_path="./refs/")

    msg = err.user_message()
    assert "pino.wav" in msg
    assert "./refs/" in msg


def test_sample_not_found_is_engine_error():
    """SampleNotFoundError è catturabile come EngineError (handler unico in main)."""
    from pge.shared.exceptions import EngineError, SampleNotFoundError

    err = SampleNotFoundError(filename="x.wav", search_path="./refs/")
    assert isinstance(err, EngineError)
    assert isinstance(err, Exception)


def test_sample_not_found_user_message_includes_optional_context():
    """Quando stream_id e config_file sono settati, compaiono nel messaggio."""
    from pge.shared.exceptions import SampleNotFoundError

    err = SampleNotFoundError(filename="pino.wav", search_path="./refs/")
    err.stream_id = "drone_a"
    err.config_file = "configs/PGE_test.yml"

    msg = err.user_message()
    assert "drone_a" in msg
    assert "configs/PGE_test.yml" in msg


def test_sample_not_found_user_message_omits_missing_context():
    """Senza context arricchito, il messaggio non mostra righe vuote."""
    from pge.shared.exceptions import SampleNotFoundError

    err = SampleNotFoundError(filename="x.wav", search_path="./refs/")
    msg = err.user_message()
    assert "Stream:" not in msg
    assert "Config:" not in msg


# =============================================================================
# Issue #38 — PR1: ConfigError, MissingFieldError, InvalidFieldValueError
# =============================================================================


def test_missing_field_error_inherits_engine_error_and_value_error():
    """MissingFieldError ereditare da EngineError e ValueError per compat catch."""
    from pge.shared.exceptions import (
        ConfigError,
        EngineError,
        MissingFieldError,
    )

    err = MissingFieldError(field="sample")
    assert isinstance(err, EngineError)
    assert isinstance(err, ValueError)
    assert isinstance(err, ConfigError)


def test_missing_field_error_user_message_single_field():
    """MissingFieldError espone messaggio pulito con field name."""
    from pge.shared.exceptions import MissingFieldError

    err = MissingFieldError(field="sample")
    msg = err.user_message()
    assert "[ERRORE]" in msg
    assert "sample" in msg


def test_missing_field_error_user_message_includes_optional_context():
    """stream_id e config_file appaiono in user_message quando settati."""
    from pge.shared.exceptions import MissingFieldError

    err = MissingFieldError(field="sample")
    err.stream_id = "drone_a"
    err.config_file = "configs/PGE_test.yml"

    msg = err.user_message()
    assert "drone_a" in msg
    assert "configs/PGE_test.yml" in msg


def test_missing_field_error_user_message_omits_missing_context():
    """Senza context arricchito, niente righe vuote."""
    from pge.shared.exceptions import MissingFieldError

    err = MissingFieldError(field="sample")
    msg = err.user_message()
    assert "Stream:" not in msg
    assert "Config:" not in msg


def test_missing_field_error_supports_multiple_fields():
    """MissingFieldError accetta lista di fields per casi multi-campo."""
    from pge.shared.exceptions import MissingFieldError

    err = MissingFieldError(fields=["foo", "bar"])
    msg = err.user_message()
    assert "foo" in msg
    assert "bar" in msg


def test_invalid_field_value_error_inherits_engine_and_value_error():
    """InvalidFieldValueError catturabile come EngineError e ValueError."""
    from pge.shared.exceptions import (
        ConfigError,
        EngineError,
        InvalidFieldValueError,
    )

    err = InvalidFieldValueError(field="grain.reverse", value=True)
    assert isinstance(err, EngineError)
    assert isinstance(err, ValueError)
    assert isinstance(err, ConfigError)


def test_invalid_field_value_error_user_message_contains_field_and_value():
    """user_message mostra field e valore invalido."""
    from pge.shared.exceptions import InvalidFieldValueError

    err = InvalidFieldValueError(field="grain.reverse", value=True, hint="lascia vuoto")
    msg = err.user_message()
    assert "grain.reverse" in msg
    assert "True" in msg
    assert "lascia vuoto" in msg


def test_invalid_field_value_error_includes_optional_context():
    """stream_id e config_file appaiono quando settati."""
    from pge.shared.exceptions import InvalidFieldValueError

    err = InvalidFieldValueError(field="x", value=1)
    err.stream_id = "s1"
    err.config_file = "c.yml"
    msg = err.user_message()
    assert "s1" in msg
    assert "c.yml" in msg


# =============================================================================
# Issue #38 — PR2: InvalidParameterError, ParameterBoundError
# =============================================================================


def test_invalid_parameter_error_inherits_config_error():
    """InvalidParameterError catturabile come ConfigError/EngineError/ValueError."""
    from pge.shared.exceptions import (
        ConfigError,
        EngineError,
        InvalidParameterError,
    )

    err = InvalidParameterError(param_name="density.value", value="bad")
    assert isinstance(err, ConfigError)
    assert isinstance(err, EngineError)
    assert isinstance(err, ValueError)


def test_invalid_parameter_error_user_message_contains_param_and_value():
    """user_message mostra param_name e value, formato pulito."""
    from pge.shared.exceptions import InvalidParameterError

    err = InvalidParameterError(
        param_name="density.value",
        value={"x": 1},
        hint="atteso numero o lista breakpoints",
    )
    msg = err.user_message()
    assert "[ERRORE]" in msg
    assert "density.value" in msg
    assert "atteso numero" in msg


def test_invalid_parameter_error_includes_optional_context():
    """stream_id e config_file compaiono quando settati."""
    from pge.shared.exceptions import InvalidParameterError

    err = InvalidParameterError(param_name="deviation_probability", value=object())
    err.stream_id = "s1"
    err.config_file = "c.yml"
    msg = err.user_message()
    assert "s1" in msg
    assert "c.yml" in msg


def test_parameter_bound_error_inherits_config_error():
    """ParameterBoundError catturabile come ConfigError/EngineError/ValueError."""
    from pge.shared.exceptions import (
        ConfigError,
        EngineError,
        ParameterBoundError,
    )

    err = ParameterBoundError(
        param_name="density",
        value_type="value",
        value=999.0,
        min_bound=0.0,
        max_bound=100.0,
    )
    assert isinstance(err, ConfigError)
    assert isinstance(err, EngineError)
    assert isinstance(err, ValueError)


def test_parameter_bound_error_user_message_shows_violation():
    """user_message mostra param, valore trovato, bounds."""
    from pge.shared.exceptions import ParameterBoundError

    err = ParameterBoundError(
        param_name="density",
        value_type="value",
        value=999.0,
        min_bound=0.0,
        max_bound=100.0,
    )
    msg = err.user_message()
    assert "[ERRORE]" in msg
    assert "density" in msg
    assert "999" in msg
    assert "100" in msg


def test_parameter_bound_error_includes_optional_context():
    from pge.shared.exceptions import ParameterBoundError

    err = ParameterBoundError(
        param_name="density",
        value_type="value",
        value=-1.0,
        min_bound=0.0,
        max_bound=100.0,
    )
    err.stream_id = "s1"
    err.config_file = "c.yml"
    msg = err.user_message()
    assert "s1" in msg
    assert "c.yml" in msg


def test_parameter_bound_error_accepts_hint():
    """`hint` opzionale, come nelle sorelle della stessa famiglia (issue #212).

    Serve dove il vincolo violato non e' un intervallo sul singolo valore:
    l'overflow di `ratio ** n_reps` non ha un bound da stampare, ha una coppia
    da nominare.
    """
    from pge.shared.exceptions import ParameterBoundError

    err = ParameterBoundError(
        param_name="ratio",
        value_type="value",
        value=10,
        min_bound=None,
        max_bound=None,
        hint="ratio=10 con n_reps=400 trabocca",
    )
    msg = err.user_message()
    assert "Hint:" in msg
    assert "n_reps=400" in msg


def test_parameter_bound_error_omits_bounds_when_unknown():
    """Senza bounds la riga Bounds sparisce, invece di stampare `[None, None]`.

    Un intervallo che non esiste non va scritto come se esistesse: il valore
    non e' fuori da nessun `[min, max]`, e' la sua combinazione con un altro
    a non stare in un float.
    """
    from pge.shared.exceptions import ParameterBoundError

    err = ParameterBoundError(
        param_name="ratio",
        value_type="value",
        value=10,
        min_bound=None,
        max_bound=None,
        hint="la coppia trabocca",
    )
    msg = err.user_message()
    assert "Bounds:" not in msg
    assert "None" not in msg


def test_parameter_bound_error_keeps_bounds_when_known():
    """Il caso storico non cambia: con bounds dichiarati la riga resta."""
    from pge.shared.exceptions import ParameterBoundError

    err = ParameterBoundError(
        param_name="density",
        value_type="value",
        value=999.0,
        min_bound=0.0,
        max_bound=100.0,
    )
    msg = err.user_message()
    assert "Bounds:" in msg
    assert "[0.0, 100.0]" in msg


def test_parameter_bound_error_keeps_bounds_when_partially_known():
    """Un solo bound dichiarato basta a stampare la riga.

    Non e' un caso di laboratorio: `parser.py` clippa gia' con `max_bound`
    None (bound superiore aperto), e in quel caso `[0.0, None]` e' il dato
    vero — il minimo esiste, il massimo no. Sopprimere la riga qui
    nasconderebbe l'unico bound che c'e'.
    """
    from pge.shared.exceptions import ParameterBoundError

    err = ParameterBoundError(
        param_name="grain_duration",
        value_type="value",
        value=-1.0,
        min_bound=0.0,
        max_bound=None,
    )
    msg = err.user_message()
    assert "Bounds:" in msg
    assert "[0.0, None]" in msg


def test_parameter_bound_error_supports_envelope_violations():
    """ParameterBoundError accetta lista violazioni per envelope."""
    from pge.shared.exceptions import ParameterBoundError

    err = ParameterBoundError(
        param_name="density",
        value_type="value",
        violations=[(0.0, 999.0), (1.0, -5.0)],
        min_bound=0.0,
        max_bound=100.0,
    )
    msg = err.user_message()
    assert "999" in msg
    assert "-5" in msg


# =============================================================================
# Issue #38 — PR3: StrategyNotFoundError, InvalidStrategyConfigError
# =============================================================================


def test_strategy_not_found_error_inherits_config_error():
    from pge.shared.exceptions import (
        ConfigError,
        EngineError,
        StrategyNotFoundError,
    )

    err = StrategyNotFoundError(
        strategy_kind="pitch",
        name="bogus",
        available=["step", "range"],
    )
    assert isinstance(err, ConfigError)
    assert isinstance(err, EngineError)
    assert isinstance(err, ValueError)


def test_strategy_not_found_user_message_lists_available():
    from pge.shared.exceptions import StrategyNotFoundError

    err = StrategyNotFoundError(
        strategy_kind="variation",
        name="bogus",
        available=["additive", "quantized"],
    )
    msg = err.user_message()
    assert "[ERRORE]" in msg
    assert "variation" in msg
    assert "bogus" in msg
    assert "additive" in msg
    assert "quantized" in msg


def test_strategy_not_found_includes_optional_context():
    from pge.shared.exceptions import StrategyNotFoundError

    err = StrategyNotFoundError(
        strategy_kind="pitch", name="x", available=["a"],
    )
    err.stream_id = "s1"
    err.config_file = "c.yml"
    msg = err.user_message()
    assert "s1" in msg
    assert "c.yml" in msg


def test_invalid_strategy_config_error_inherits_config_error():
    from pge.shared.exceptions import (
        ConfigError,
        EngineError,
        InvalidStrategyConfigError,
    )

    err = InvalidStrategyConfigError(
        strategy_kind="pitch",
        field="chord",
        value="bogus",
    )
    assert isinstance(err, ConfigError)
    assert isinstance(err, EngineError)
    assert isinstance(err, ValueError)


def test_invalid_strategy_config_user_message_contains_field_and_value():
    from pge.shared.exceptions import InvalidStrategyConfigError

    err = InvalidStrategyConfigError(
        strategy_kind="pitch",
        field="chord",
        value="bogus",
        hint="usa uno tra dom7, maj7",
    )
    msg = err.user_message()
    assert "[ERRORE]" in msg
    assert "pitch" in msg
    assert "chord" in msg
    assert "bogus" in msg
    assert "dom7" in msg


def test_invalid_strategy_config_includes_optional_context():
    from pge.shared.exceptions import InvalidStrategyConfigError

    err = InvalidStrategyConfigError(
        strategy_kind="pan", field="spread", value=-1.0,
    )
    err.stream_id = "s1"
    err.config_file = "c.yml"
    msg = err.user_message()
    assert "s1" in msg
    assert "c.yml" in msg


# =============================================================================
# PR4: Rendering errors
# =============================================================================

def test_invalid_renderer_error_is_config_error():
    from pge.shared.exceptions import (
        ConfigError, EngineError, InvalidRendererError,
    )
    err = InvalidRendererError(renderer_type="bogus", available=["numpy", "csound"])
    assert isinstance(err, ConfigError)
    assert isinstance(err, EngineError)
    assert isinstance(err, ValueError)


def test_invalid_renderer_user_message_lists_available():
    from pge.shared.exceptions import InvalidRendererError
    err = InvalidRendererError(renderer_type="bogus", available=["numpy", "csound"])
    msg = err.user_message()
    assert "[ERRORE]" in msg
    assert "bogus" in msg
    assert "numpy" in msg
    assert "csound" in msg


def test_invalid_window_error_name_form():
    from pge.shared.exceptions import ConfigError, InvalidWindowError
    err = InvalidWindowError(name="bogus", available=["hanning", "hamming"])
    assert isinstance(err, ConfigError)
    msg = err.user_message()
    assert "bogus" in msg
    assert "hanning" in msg


def test_invalid_window_error_param_form():
    from pge.shared.exceptions import InvalidWindowError
    err = InvalidWindowError(param="n", value=0)
    msg = err.user_message()
    assert "[ERRORE]" in msg
    assert "n" in msg
    assert "0" in msg


def test_ftable_error_is_config_error():
    from pge.shared.exceptions import ConfigError, FtableError
    err = FtableError(key="hanning", reason="Window non trovata nel registry")
    assert isinstance(err, ConfigError)
    msg = err.user_message()
    assert "hanning" in msg
    assert "non trovata" in msg


def test_engine_runtime_error_is_engine_error():
    from pge.shared.exceptions import EngineError, EngineRuntimeError
    err = EngineRuntimeError("boom")
    assert isinstance(err, EngineError)
    assert err.stream_id is None
    assert err.config_file is None


def test_csound_render_error_inheritance_and_message():
    from pge.shared.exceptions import (
        CsoundRenderError, EngineError, EngineRuntimeError,
    )
    err = CsoundRenderError(
        returncode=1,
        command=["csound", "score.csd"],
        stderr="orch error\n",
    )
    assert isinstance(err, EngineRuntimeError)
    assert isinstance(err, EngineError)
    assert isinstance(err, RuntimeError)
    msg = err.user_message()
    assert "[ERRORE]" in msg
    assert "exit code 1" in msg
    assert "orch error" in msg


def test_csound_render_error_context_lines():
    from pge.shared.exceptions import CsoundRenderError
    err = CsoundRenderError(returncode=2, command=["csound"], stderr="x")
    err.stream_id = "drone_a"
    err.config_file = "configs/x.yml"
    msg = err.user_message()
    assert "drone_a" in msg
    assert "configs/x.yml" in msg


# =============================================================================
# Issue #46 — PR1: controllers raises -> EngineError
# =============================================================================

def test_window_curve_range_violation_is_invalid_strategy_config():
    """Curve breakpoint oltre range valido -> InvalidStrategyConfigError."""
    from pge.shared.exceptions import (
        ConfigError, EngineError, InvalidStrategyConfigError,
    )
    from pge.controllers.window_selection_strategy import _validate_curve_range
    from pge.envelopes.envelope import Envelope

    curve = Envelope([[0.0, 0.0], [2.5, 1.0]])
    with pytest.raises(InvalidStrategyConfigError) as excinfo:
        _validate_curve_range(curve, duration=1.0, time_mode='normalized', stream_id='s1')
    err = excinfo.value
    assert isinstance(err, ConfigError)
    assert isinstance(err, EngineError)
    assert isinstance(err, ValueError)
    assert err.stream_id == 's1'
    msg = err.user_message()
    assert "[ERRORE]" in msg
    assert "window" in msg.lower()
    assert "Stream:" in msg


def test_multistate_too_few_states_is_invalid_strategy_config():
    """MultiStateWindowStrategy con <2 stati -> InvalidStrategyConfigError."""
    from pge.shared.exceptions import InvalidStrategyConfigError
    from pge.controllers.window_selection_strategy import MultiStateWindowStrategy
    from pge.envelopes.envelope import Envelope

    curve = Envelope([[0.0, 0.0], [1.0, 1.0]])
    with pytest.raises(InvalidStrategyConfigError) as excinfo:
        MultiStateWindowStrategy(states=[(0.0, 'hanning')], curve=curve)
    err = excinfo.value
    assert isinstance(err, ValueError)
    msg = err.user_message()
    assert "[ERRORE]" in msg
    assert "almeno 2" in msg or "2" in msg


def test_multistate_unsorted_states_is_invalid_strategy_config():
    """Stati non in ordine crescente -> InvalidStrategyConfigError."""
    from pge.shared.exceptions import InvalidStrategyConfigError
    from pge.controllers.window_selection_strategy import MultiStateWindowStrategy
    from pge.envelopes.envelope import Envelope

    curve = Envelope([[0.0, 0.0], [1.0, 1.0]])
    with pytest.raises(InvalidStrategyConfigError) as excinfo:
        MultiStateWindowStrategy(
            states=[(0.5, 'a'), (0.2, 'b')],
            curve=curve,
        )
    err = excinfo.value
    msg = err.user_message()
    assert "[ERRORE]" in msg
    assert "crescente" in msg or "ordine" in msg.lower()


def test_window_strategy_factory_unknown_name_is_strategy_not_found():
    """Factory.create con nome ignoto -> StrategyNotFoundError (non KeyError)."""
    from pge.shared.exceptions import (
        ConfigError, EngineError, StrategyNotFoundError,
    )
    from pge.controllers.window_selection_strategy import WindowStrategyFactory

    with pytest.raises(StrategyNotFoundError) as excinfo:
        WindowStrategyFactory.create('bogus_strategy_name_xyz')
    err = excinfo.value
    assert isinstance(err, ConfigError)
    assert isinstance(err, EngineError)
    assert isinstance(err, ValueError)
    msg = err.user_message()
    assert "[ERRORE]" in msg
    assert "bogus_strategy_name_xyz" in msg


def test_window_registry_generate_unknown_is_invalid_window():
    """generate_ftable_statement con nome ignoto -> InvalidWindowError."""
    from pge.shared.exceptions import ConfigError, InvalidWindowError
    from pge.controllers.window_registry import WindowRegistry

    with pytest.raises(InvalidWindowError) as excinfo:
        WindowRegistry.generate_ftable_statement(1, 'totally_fake_window_xyz')
    err = excinfo.value
    assert isinstance(err, ConfigError)
    assert isinstance(err, ValueError)
    msg = err.user_message()
    assert "[ERRORE]" in msg
    assert "totally_fake_window_xyz" in msg


def test_pitch_controller_multiple_units_is_invalid_field_value(mock_config):
    """>1 chiave-unità nel blocco pitch -> InvalidFieldValueError."""
    from pge.shared.exceptions import ConfigError, InvalidFieldValueError
    from pge.controllers.pitch_controller import PitchController

    with pytest.raises(InvalidFieldValueError) as excinfo:
        PitchController({'semitones': 12, 'ratio': 2.0}, mock_config)
    err = excinfo.value
    assert isinstance(err, ConfigError)
    assert isinstance(err, ValueError)
    msg = err.user_message()
    assert "[ERRORE]" in msg
    assert "pitch" in msg.lower()


def test_density_controller_exclusive_group_violation_is_invalid_field_value():
    """0 o >1 param density -> InvalidFieldValueError."""
    from pge.shared.exceptions import ConfigError, InvalidFieldValueError
    from pge.controllers.density_controller import DensityController

    dc = DensityController.__new__(DensityController)
    dc._loaded_params = {}
    with pytest.raises(InvalidFieldValueError) as excinfo:
        dc._find_selected_param()
    err = excinfo.value
    assert isinstance(err, ConfigError)
    assert isinstance(err, ValueError)
    msg = err.user_message()
    assert "[ERRORE]" in msg
    assert "density" in msg.lower()


# =============================================================================
# Issue #46 — PR2: envelopes raises -> EngineError
# =============================================================================

def test_envelope_segment_empty_breakpoints_is_invalid_field_value():
    """Segment senza breakpoint -> InvalidFieldValueError."""
    from pge.shared.exceptions import ConfigError, InvalidFieldValueError
    from pge.envelopes.envelope_segment import NormalSegment
    from pge.envelopes.envelope_interpolation import LinearInterpolation

    with pytest.raises(InvalidFieldValueError) as excinfo:
        NormalSegment(breakpoints=[], strategy=LinearInterpolation())
    err = excinfo.value
    assert isinstance(err, ConfigError)
    assert isinstance(err, ValueError)
    msg = err.user_message()
    assert "[ERRORE]" in msg
    assert "breakpoint" in msg.lower()


def test_time_distribution_invalid_n_reps_is_parameter_bound():
    """n_reps < 1 -> ParameterBoundError."""
    from pge.shared.exceptions import ConfigError, ParameterBoundError
    from pge.envelopes.time_distribution import LinearDistribution

    dist = LinearDistribution()
    with pytest.raises(ParameterBoundError) as excinfo:
        dist.calculate_distribution(total_time=10.0, n_reps=0)
    err = excinfo.value
    assert isinstance(err, ConfigError)
    assert isinstance(err, ValueError)
    msg = err.user_message()
    assert "[ERRORE]" in msg
    assert "n_reps" in msg
    assert "fuori bounds" in msg


def test_time_distribution_invalid_total_time_is_parameter_bound():
    """total_time <= 0 -> ParameterBoundError."""
    from pge.shared.exceptions import ParameterBoundError
    from pge.envelopes.time_distribution import LinearDistribution

    dist = LinearDistribution()
    with pytest.raises(ParameterBoundError) as excinfo:
        dist.calculate_distribution(total_time=0.0, n_reps=5)
    err = excinfo.value
    assert isinstance(err, ValueError)
    msg = err.user_message()
    assert "[ERRORE]" in msg
    assert "total_time" in msg


def test_exponential_distribution_invalid_rate_is_parameter_bound():
    """rate <= 0 -> ParameterBoundError."""
    from pge.shared.exceptions import ParameterBoundError
    from pge.envelopes.time_distribution import ExponentialDistribution

    with pytest.raises(ParameterBoundError) as excinfo:
        ExponentialDistribution(rate=0.0)
    err = excinfo.value
    assert isinstance(err, ValueError)
    msg = err.user_message()
    assert "[ERRORE]" in msg
    assert "rate" in msg


# =============================================================================
# ConfigFileNotFoundError / ConfigParseError (issue #257)
# =============================================================================
#
# Il file di configurazione che manca, e quello che c'e' ma non si legge.
# Prima della #257 erano due builtin nudi (`FileNotFoundError`, `yaml.YAMLError`)
# e la CLI li distingueva per estensione fisica del blocco `try`, non per tipo.


def test_config_file_not_found_is_a_config_error():
    """Un file di configurazione che non esiste e' un errore di configurazione."""
    from pge.shared.exceptions import (
        ConfigError, ConfigFileNotFoundError, EngineError)

    err = ConfigFileNotFoundError('configs/missing.yml')
    assert isinstance(err, ConfigError)
    assert isinstance(err, EngineError)


def test_config_file_not_found_resta_un_FileNotFoundError():
    """La promessa di libreria sopravvive al tipo nuovo (issue #257).

    `Generator.load_yaml` e `api.load_generator` dichiarano `FileNotFoundError`
    fra i `Raises` da sempre: chi lo cattura per nome deve continuare a
    catturarlo. E' lo stesso motivo per cui `ConfigError` eredita `ValueError`.

    Il contrario di `SuperColliderNotFoundError` / `CsoundNotFoundError`, e la
    ragione dell'asimmetria e' che li' il builtin era falso (il file mancante
    non era quello che il tipo lasciava intendere) mentre qui e' vero: il file
    che non c'e' e' proprio quello.
    """
    from pge.shared.exceptions import ConfigFileNotFoundError

    err = ConfigFileNotFoundError('configs/missing.yml')
    assert isinstance(err, FileNotFoundError)
    # E resta anche un ValueError, per la base ConfigError.
    assert isinstance(err, ValueError)


def test_config_file_not_found_user_message_nomina_file_e_path_risolto():
    """Head col nome dato dall'utente, riga col path assoluto cercato.

    Il path assoluto e' l'informazione che il messaggio precedente
    (« Errore: file 'missing.yml' non trovato») non dava: dice all'utente
    che sta lanciando dalla directory sbagliata.
    """
    import os
    from pge.shared.exceptions import ConfigFileNotFoundError

    err = ConfigFileNotFoundError('configs/missing.yml')

    msg = err.user_message()
    assert msg.startswith(
        "[ERRORE] File di configurazione non trovato: 'configs/missing.yml'")
    assert os.path.abspath('configs/missing.yml') in msg


def test_config_file_not_found_popola_config_file():
    """Il file e' il soggetto dell'errore, quindi `config_file` e' gia' pieno.

    Nessuno deve arricchirlo a valle come fa `create_elements` per gli altri
    `ConfigError`: qui il path lo conosce chi solleva.
    """
    from pge.shared.exceptions import ConfigFileNotFoundError

    err = ConfigFileNotFoundError('configs/missing.yml')
    assert err.config_file == 'configs/missing.yml'
    assert err.path == 'configs/missing.yml'


def test_config_file_not_found_non_ripete_il_config_nel_messaggio():
    """`Config:` sarebbe la ripetizione del head: il file *e'* il soggetto."""
    from pge.shared.exceptions import ConfigFileNotFoundError

    err = ConfigFileNotFoundError('configs/missing.yml')
    assert 'Config:' not in err.user_message()


def test_config_parse_error_is_a_config_error():
    """Uno YAML malformato e' un errore di configurazione."""
    import yaml
    from pge.shared.exceptions import (
        ConfigError, ConfigParseError, EngineError)

    err = ConfigParseError('configs/broken.yml', yaml.YAMLError('boom'))
    assert isinstance(err, ConfigError)
    assert isinstance(err, EngineError)


def test_config_parse_error_resta_uno_yaml_error():
    """Stessa promessa di libreria dell'altro: `Raises: yaml.YAMLError`."""
    import yaml
    from pge.shared.exceptions import ConfigParseError

    err = ConfigParseError('configs/broken.yml', yaml.YAMLError('boom'))
    assert isinstance(err, yaml.YAMLError)


def test_config_parse_error_non_e_un_file_not_found():
    """I due errori restano distinguibili: il file c'e', non si legge.

    Senza questa guardia una base condivisa fra i due li renderebbe
    intercambiabili per chi cattura, che e' il difetto che la #257 chiude.
    """
    import yaml
    from pge.shared.exceptions import ConfigParseError

    err = ConfigParseError('configs/broken.yml', yaml.YAMLError('boom'))
    assert not isinstance(err, FileNotFoundError)


def test_config_file_not_found_non_e_uno_yaml_error():
    """Specchio del precedente, nell'altra direzione."""
    import yaml
    from pge.shared.exceptions import ConfigFileNotFoundError

    err = ConfigFileNotFoundError('configs/missing.yml')
    assert not isinstance(err, yaml.YAMLError)


def test_config_parse_error_user_message_riporta_riga_colonna_e_dettaglio():
    """Con un errore marcato, la posizione 1-based e il problema di PyYAML.

    `problem_mark` di PyYAML e' 0-based: renderlo cosi' com'e' manderebbe
    l'utente una riga sopra a quella che l'editor gli mostra.
    """
    import yaml
    from pge.shared.exceptions import ConfigParseError

    # `except ... as e` cancella il nome all'uscita del blocco: la causa va
    # tenuta da parte esplicitamente.
    cause = None
    try:
        yaml.safe_load("a: 1\nb: [2, 3\nc: 4\n")
    except yaml.YAMLError as e:
        cause = e
    assert cause is not None, "lo YAML della fixture deve essere malformato"
    err = ConfigParseError('configs/broken.yml', cause)

    msg = err.user_message()
    assert msg.startswith(
        "[ERRORE] File di configurazione malformato: 'configs/broken.yml'")
    assert 'Riga/colonna:' in msg
    assert 'Dettaglio:' in msg
    # 1-based: la riga stampata e' quella di problem_mark piu' uno.
    riga = cause.problem_mark.line + 1
    colonna = cause.problem_mark.column + 1
    assert f"  Riga/colonna: {riga}:{colonna}" in msg
    assert cause.problem in msg


def test_config_parse_error_senza_marker_degrada_alle_due_righe():
    """Non tutti gli `yaml.YAMLError` portano una posizione."""
    import yaml
    from pge.shared.exceptions import ConfigParseError

    err = ConfigParseError('configs/broken.yml', yaml.YAMLError('boom senza mark'))

    msg = err.user_message()
    assert msg.startswith(
        "[ERRORE] File di configurazione malformato: 'configs/broken.yml'")
    assert 'Riga/colonna:' not in msg
    assert 'boom senza mark' in msg


def test_config_parse_error_espone_la_causa():
    """L'errore di PyYAML resta raggiungibile per chi lo vuole leggere."""
    import yaml
    from pge.shared.exceptions import ConfigParseError

    cause = yaml.YAMLError('boom')
    err = ConfigParseError('configs/broken.yml', cause)
    assert err.cause is cause
    assert err.config_file == 'configs/broken.yml'
    assert err.path == 'configs/broken.yml'


def test_config_file_not_found_non_ripete_un_path_gia_assoluto():
    """`Path cercato:` esiste per dire «cwd sbagliata»: su un path assoluto
    sarebbe la stessa riga due volte."""
    from pge.shared.exceptions import ConfigFileNotFoundError

    err = ConfigFileNotFoundError('/tmp/assente.yml')

    msg = err.user_message()
    assert msg == "[ERRORE] File di configurazione non trovato: '/tmp/assente.yml'"
    assert err.resolved_path == '/tmp/assente.yml'
