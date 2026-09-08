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


def test_subprocess_render_error_hint_e_opzionale():
    """L'hint del render fallito e' condizionale, non decorativo: dice come
    riavere lo score temporaneo, e con `--keep-sco` quello score c'e' gia'.
    Una riga `Hint:` stampata sempre sarebbe un rimedio per un guasto assente
    -- e' la stessa regola di `_BinaryNotFoundError`, da cui questa base copia
    il formato della riga."""
    from pge.shared.exceptions import CsoundRenderError
    senza = CsoundRenderError(
        returncode=2, command=["csound", "/tmp/x.sco"], stderr="err")
    assert "Hint:" not in senza.user_message()

    con = CsoundRenderError(
        returncode=2, command=["csound", "/tmp/x.sco"], stderr="err",
        hint="Rilancia con --keep-sco.")
    con.stream_id = "drone_a"
    con.config_file = "configs/x.yml"
    msg = con.user_message()
    assert "  Hint:         Rilancia con --keep-sco." in msg
    # Dopo la diagnostica e prima delle righe di contesto: l'hint e' il
    # seguito dell'errore, non un'intestazione -- ed e' la posizione che
    # `docs/reference/errors.md` mostra nell'esempio del render fallito.
    # Serve la coppia: `Output: < Hint:` da sola resta vera anche con
    # l'hint spinto in fondo, sotto Stream e Config, cioe' proprio sul
    # difetto che il commento dichiara di coprire. Le righe di contesto
    # vanno quindi materializzate, altrimenti non c'e' un "dopo".
    assert msg.index("Output:") < msg.index("Hint:") < msg.index("Stream:")


def test_csound_render_error_context_lines():
    from pge.shared.exceptions import CsoundRenderError
    err = CsoundRenderError(returncode=2, command=["csound"], stderr="x")
    err.stream_id = "drone_a"
    err.config_file = "configs/x.yml"
    msg = err.user_message()
    assert "drone_a" in msg
    assert "configs/x.yml" in msg


# =============================================================================
# Issue #241 — csound assente: un errore azionabile, non un FileNotFoundError
# =============================================================================

def test_csound_not_found_error_inheritance_and_message():
    from pge.shared.exceptions import (
        CsoundNotFoundError, EngineError, EngineRuntimeError,
    )
    err = CsoundNotFoundError(
        what="binario 'csound'",
        hint="Installa csound, oppure usa --renderer numpy.",
    )
    assert isinstance(err, EngineRuntimeError)
    assert isinstance(err, EngineError)
    msg = err.user_message()
    assert "[ERRORE]" in msg
    assert "Csound" in msg
    assert "binario 'csound'" in msg
    assert "--renderer numpy" in msg


def test_csound_not_found_error_non_e_un_FileNotFoundError():
    """Per un binario assente il builtin sarebbe falso: il file che manca non
    e' quello che il tipo lascia intendere (stessa regola di
    SuperColliderNotFoundError).

    La ragione scritta qui prima -- «la CLI intercetta FileNotFoundError per
    annunciare 'file YAML non trovato'» -- non vale piu' dalla #257:
    `cli.main()` non cattura nessun builtin sul percorso di caricamento, e
    una guardia strutturale lo verifica (`tests/test_cli_no_builtin_handlers`).
    Quella che regge e' il valore di verita' del tipo, ed e' anche cio' che
    spiega l'asimmetria con `ConfigFileNotFoundError`, che il builtin lo
    eredita proprio perche' li' il file mancante e' davvero quello."""
    from pge.shared.exceptions import CsoundNotFoundError
    err = CsoundNotFoundError(what="binario 'csound'")
    assert not isinstance(err, FileNotFoundError)
    assert not isinstance(err, OSError)


def test_csound_not_found_error_context_lines():
    from pge.shared.exceptions import CsoundNotFoundError
    err = CsoundNotFoundError(what="binario 'csound'", hint="Usa --renderer numpy.")
    err.stream_id = "drone_a"
    err.config_file = "configs/x.yml"
    msg = err.user_message()
    assert "drone_a" in msg
    assert "configs/x.yml" in msg
    # Stessa regola di posizione di `_SubprocessRenderError`, e stesso modo
    # di sbagliarla: il rimedio precede il contesto, come nell'esempio di
    # `docs/reference/errors.md`. Senza questa riga, spostare l'hint in
    # fondo lasciava verdi tutte e due le meta' della gerarchia.
    assert msg.index("Hint:") < msg.index("Stream:")


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


def test_csound_emitter_unknown_window_is_invalid_window():
    """window_ftable con nome ignoto -> InvalidWindowError (issue #203)."""
    from pge.shared.exceptions import ConfigError, InvalidWindowError
    from pge.rendering.csound_emitter import CsoundEmitter

    with pytest.raises(InvalidWindowError) as excinfo:
        CsoundEmitter().window_ftable(1, 'totally_fake_window_xyz')
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


def test_config_parse_error_dettaglio_resta_una_riga_sola():
    """Il blocco `user_message()` e' righe `  <Campo>:      <valore>`, e una
    causa che parla su due righe non deve romperlo.

    `yaml.reader.ReaderError` e' l'unico `yaml.YAMLError` del percorso di
    caricamento che non sia un `MarkedYAMLError` (gli altri quattro non marcati
    -- Emitter, Representer, Serializer, Resolver -- stanno sul lato dump),
    quindi e' l'unico a cadere sul ripiego `str(self.cause)`. Il suo `__str__`
    e' due righe *sempre*, e la seconda usciva dal blocco senza nome di campo:
    una riga che si legge come un campo rotto, fra `Dettaglio:` e il
    `Dettagli:` che `_handle_engine_error` appende subito dopo. E' il contratto
    della Sez. 2 di `docs/reference/errors.md`, che ogni altra classe rispetta
    -- `_SubprocessRenderError` arriva a pescare *una* riga da uno stderr
    intero pur di non violarlo.

    Qui non si butta via niente: il seguito e' incolonnato sotto il valore, che
    e' l'unico modo di tenere la posizione del carattere (`position N`, la sola
    cosa che dica *dove*) senza inventare un campo nuovo.
    """
    import yaml.reader
    from pge.shared.exceptions import config_parse_error

    cause = yaml.reader.ReaderError(
        'configs/rotto.yml', 22, 0x07, 'unicode',
        'special characters are not allowed')
    err = config_parse_error('configs/rotto.yml', cause)

    import re

    righe = err.user_message().split('\n')
    assert righe[0] == (
        "[ERRORE] File di configurazione malformato: 'configs/rotto.yml'")

    # Ogni riga sotto il head e' o un campo (`  Nome:` + valore) o un seguito
    # incolonnato sotto il valore. Niente altro: e' quello il contratto.
    for riga in righe[1:]:
        assert re.match(r'^  \S[^:]*: +\S', riga) or riga.startswith(' ' * 16), (
            f"riga senza nome di campo e non incolonnata: {riga!r}")

    # E il seguito c'e' ancora: incolonnato, non buttato via. `position 22` e'
    # la sola cosa che dica *dove* sta il carattere che il parser rifiuta.
    seguito = [r for r in righe[1:] if r.startswith(' ' * 16)]
    assert seguito, f"la seconda riga del ReaderError e' sparita: {righe}"
    assert 'position 22' in '\n'.join(seguito)


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


# -----------------------------------------------------------------------------
# Ereditare il builtin non basta: chi lo cattura ne legge lo *stato*
# -----------------------------------------------------------------------------
#
# La #257 fa ereditare alle due classi il tipo che sostituiscono perche' un
# `except FileNotFoundError` / `except yaml.YAMLError` scritto contro le
# versioni precedenti continui a funzionare. Ma quel codice non si limita a
# catturare: legge `e.filename`, confronta `e.errno` con `errno.ENOENT`,
# guarda `e.problem_mark` -- e' l'idioma con cui si legge un errore PyYAML.
# Un wrapper che porta solo il tipo lascia tutti quegli attributi a None o
# assenti, cioe' mantiene la promessa per `isinstance` e la rompe per tutto
# il resto, in silenzio.


def test_config_file_not_found_e_un_FileNotFoundError_completo():
    """`errno`, `strerror` e `filename`, non solo il tipo."""
    import errno as errno_mod
    from pge.shared.exceptions import ConfigFileNotFoundError

    err = ConfigFileNotFoundError('configs/missing.yml')

    assert err.errno == errno_mod.ENOENT
    assert err.filename == 'configs/missing.yml'
    assert err.strerror


def test_config_file_not_found_str_resta_il_messaggio_di_dominio():
    """`OSError.__str__` riscriverebbe il messaggio in `[Errno 2] ...`.

    E' quella la riga che finisce nel log engine (`logger.error("%s", err)`)
    e nel ramo generico della CLI: popolare i campi del builtin non deve
    costare la prosa. La coppia col test sopra e' il punto -- l'uno senza
    l'altro e' una regressione.
    """
    from pge.shared.exceptions import ConfigFileNotFoundError

    err = ConfigFileNotFoundError('configs/missing.yml')

    assert str(err) == "File di configurazione non trovato: 'configs/missing.yml'"
    assert '[Errno' not in str(err)


def test_config_parse_error_riporta_gli_attributi_di_pyyaml():
    """`e.problem_mark` e' *l'*idioma con cui si legge un errore PyYAML.

    Prima della #257 il chiamante riceveva il `MarkedYAMLError` vero. Un
    wrapper che eredita `yaml.YAMLError` e basta lo fa sparire, e chi lo
    interrogava con `hasattr(e, 'problem_mark')` smette di trovarlo senza
    che niente fallisca.
    """
    import yaml
    from pge.shared.exceptions import ConfigParseError

    cause = None
    try:
        yaml.safe_load("a: 1\nb: [2, 3\nc: 4\n")
    except yaml.YAMLError as e:
        cause = e
    assert cause is not None

    err = ConfigParseError('configs/broken.yml', cause)

    assert err.problem_mark is cause.problem_mark
    assert err.problem == cause.problem
    assert err.context == cause.context
    assert err.context_mark is cause.context_mark


def test_config_parse_error_senza_marker_non_inventa_gli_attributi():
    """Un `yaml.YAMLError` nudo non li ha: il wrapper non deve fabbricarli."""
    import yaml
    from pge.shared.exceptions import ConfigParseError

    err = ConfigParseError('configs/broken.yml', yaml.YAMLError('boom'))

    assert not hasattr(err, 'problem_mark')
    assert not hasattr(err, 'problem')


def test_config_unicode_parse_error_e_un_UnicodeDecodeError_completo():
    """Il terzo builtin ereditato, e l'ultimo a cui mancava lo stato.

    `e.object[e.start:e.end]` -- i byte che non si decodificano -- e' l'idioma
    con cui si legge un `UnicodeDecodeError`, come `e.problem_mark` lo e' per
    PyYAML e `e.errno` per `OSError`, e prima della #257 il chiamante riceveva
    il builtin vero. `UnicodeDecodeError.__init__` qui non viene chiamato --
    vuole cinque argomenti e intercetterebbe il messaggio -- quindi senza
    riporto quei cinque campi restano al valore vuoto del tipo: `None` per
    tre, e `0` per `start` e `end`, che non e' un «non lo so» ma una posizione
    plausibile e falsa.
    """
    from pge.shared.exceptions import config_parse_error

    causa = None
    try:
        'perch\xe8 no'.encode('latin-1').decode('utf-8')
    except UnicodeDecodeError as e:
        causa = e
    assert causa is not None

    err = config_parse_error('configs/latin1.yml', causa)

    assert err.encoding == causa.encoding
    assert err.object == causa.object
    assert err.start == causa.start
    assert err.end == causa.end
    assert err.reason == causa.reason
    # L'idioma per esteso: i byte incriminati restano leggibili dal wrapper.
    assert err.object[err.start:err.end] == b'\xe8'


def test_config_unicode_parse_error_regge_una_causa_che_non_li_ha():
    """Riportati dalla causa, mai fabbricati -- la regola di `problem_mark`.

    Il costruttore e' pubblico e `config_parse_error` non e' l'unica via:
    con una causa che quei campi non li ha, l'assenza deve restare tale
    invece di alzare `AttributeError` mentre si costruisce un'eccezione.
    """
    import yaml
    from pge.shared.exceptions import ConfigUnicodeParseError

    err = ConfigUnicodeParseError('configs/x.yml', yaml.YAMLError('boom'))

    assert str(err) == "File di configurazione malformato: 'configs/x.yml'"
    assert err.reason is None


# -----------------------------------------------------------------------------
# ConfigReadError: il file c'e', il sistema operativo non lo apre
# -----------------------------------------------------------------------------
#
# `open()` sul file di configurazione fallisce in piu' modi di quanti la
# passata precedente ne avesse tradotti: oltre a ENOENT e alla decodifica ci
# sono EISDIR (`pge configs/ out.wav`, il typo che la tab-completion della
# shell fabbrica da sola) ed EACCES. Restavano gli unici a uscire dal ramo
# generico della CLI come traceback, cioe' l'enumerazione «i tre modi» era
# incompleta proprio sul caso piu' probabile.


def test_config_read_error_is_a_config_error():
    """Il file di configurazione che non si apre e' un errore di config."""
    from pge.shared.exceptions import (
        ConfigError, ConfigReadError, EngineError)

    err = ConfigReadError('configs/', IsADirectoryError(21, 'Is a directory'))
    assert isinstance(err, ConfigError)
    assert isinstance(err, EngineError)


def test_config_read_error_resta_un_OSError():
    """La promessa di libreria, come per gli altri due (issue #257).

    Prima `load_yaml` lasciava salire l'`OSError` di `open()`: chi lo cattura
    per nome deve continuare a catturarlo.
    """
    from pge.shared.exceptions import ConfigReadError

    err = ConfigReadError('configs/', IsADirectoryError(21, 'Is a directory'))
    assert isinstance(err, OSError)


def test_config_read_error_non_e_un_file_not_found():
    """Una directory non e' un file mancante, e i due non vanno confusi.

    E' la stessa ragione per cui `ConfigParseError` non e' un
    `FileNotFoundError`: il tipo deve dire il vero, altrimenti chi cattura
    diagnostica il guasto sbagliato.
    """
    from pge.shared.exceptions import ConfigReadError

    err = ConfigReadError('configs/', IsADirectoryError(21, 'Is a directory'))
    assert not isinstance(err, FileNotFoundError)


def test_config_read_error_user_message_riporta_la_ragione_del_sistema():
    """`strerror` e' cio' che distingue EISDIR da EACCES: senza, il messaggio
    direbbe solo che il file non si legge, che l'utente gia' sa."""
    from pge.shared.exceptions import ConfigReadError

    err = ConfigReadError(
        'configs/', IsADirectoryError(21, 'Is a directory', 'configs/'))

    msg = err.user_message()
    assert msg.startswith(
        "[ERRORE] File di configurazione non leggibile: 'configs/'")
    assert '  Dettaglio:    Is a directory' in msg


def test_config_read_error_senza_strerror_degrada_alla_causa():
    """Non tutti gli `OSError` portano uno `strerror`."""
    from pge.shared.exceptions import ConfigReadError

    err = ConfigReadError('configs/x.yml', OSError('boom senza strerror'))

    msg = err.user_message()
    assert 'boom senza strerror' in msg


def test_config_read_error_e_un_OSError_completo():
    """Come per `ConfigFileNotFoundError`: chi cattura il builtin ne legge lo
    stato, e qui lo stato c'e' gia' -- va riportato dalla causa, non
    fabbricato."""
    import errno as errno_mod
    from pge.shared.exceptions import ConfigReadError

    causa = IsADirectoryError(errno_mod.EISDIR, 'Is a directory', 'configs/')
    err = ConfigReadError('configs/', causa)

    assert err.errno == errno_mod.EISDIR
    assert err.strerror == 'Is a directory'
    assert err.filename == 'configs/'


def test_config_read_error_str_resta_il_messaggio_di_dominio():
    """Stesso prezzo dei campi `OSError` gia' pagato dall'altra classe:
    con `filename` valorizzato `OSError.__str__` riscriverebbe la riga che
    finisce nel log engine."""
    from pge.shared.exceptions import ConfigReadError

    err = ConfigReadError(
        'configs/', IsADirectoryError(21, 'Is a directory', 'configs/'))

    assert str(err) == "File di configurazione non leggibile: 'configs/'"
    assert '[Errno' not in str(err)


def test_config_read_error_espone_la_causa():
    """L'`OSError` originale resta raggiungibile."""
    from pge.shared.exceptions import ConfigReadError

    causa = PermissionError(13, 'Permission denied', 'configs/x.yml')
    err = ConfigReadError('configs/x.yml', causa)

    assert err.cause is causa
    assert err.path == 'configs/x.yml'
    assert err.config_file == 'configs/x.yml'


def test_config_read_error_non_ripete_il_config_nel_messaggio():
    """`Config:` sarebbe la ripetizione del head, come per l'altra classe."""
    from pge.shared.exceptions import ConfigReadError

    err = ConfigReadError('configs/', IsADirectoryError(21, 'Is a directory'))
    assert 'Config:' not in err.user_message()


# -----------------------------------------------------------------------------
# La base `yaml.YAMLError` non deve costare PyYAML a chi non parsa YAML
# -----------------------------------------------------------------------------
#
# `ConfigParseError` eredita `yaml.YAMLError`, e una classe base deve esistere
# nel momento in cui la classe *si crea*: l'import non puo' essere lazy. Ma un
# import duro in questo modulo non e' gratis, e il prezzo non lo paga il
# pyproject (PyYAML e' dipendenza dichiarata): lo paga chi importa il motore
# da un checkout, senza installarlo.
#
# `pge/shared/exceptions.py` sta sotto quasi ogni altro modulo -- `pge/__init__`
# compreso, che dichiara di ri-esportare «solo simboli leggeri» -- quindi un
# import duro qui mette PyYAML fra le dipendenze di import di tutto il motore.
# I moduli qui sotto sono quelli che l'oracolo di parita' di PGE-ui importa
# (`tests/parity/engine_oracle.py`) da un checkout **senza venv**, con il solo
# python del runner: nessuno di loro ha una dipendenza di terze parti, e con
# l'import duro smettevano tutti di importarsi. Il rosso sarebbe arrivato a
# valle, su ogni PR di un altro repository, per una riga scritta qui.
#
# L'elenco e' quello *intero*, e la distinzione conta: quattro di questi moduli
# l'oracolo li chiede dentro un `try/except OracleError` che scrive `None` nel
# payload invece di morire, quindi il loro guasto non e' un import che esplode
# ma un caso di parita' che confronta un `None` -- rosso comunque, e piu' muto.
# Fermarsi ai quattro che fanno morire l'oracolo avrebbe lasciato scoperta
# meta' della superficie che questa guardia dichiara di sorvegliare.

_MODULI_SENZA_TERZE_PARTI = (
    'pge.shared.exceptions',
    # Quelli che l'oracolo importa senza rete: il loro ImportError lo fa
    # morire (op fingerprint, constants, classify_deviation_probability,
    # build_time_distribution, parameter_bounds).
    'pge.rendering.stream_cache_manager',
    'pge.parameters.gate_factory',
    'pge.parameters.parameter_definitions',
    'pge.envelopes.time_distribution',
    # E quelli che chiede dentro un `try/except OracleError`: li' l'ImportError
    # non uccide l'oracolo, gli fa scrivere `None` nel payload -- e a valle il
    # `None` fallisce lo stesso, contro il letterale statico di `yaml-bridge.js`
    # (`output_sr`) o contro le liste di nomi che le mirror copiano intere.
    # Stessa superficie, stesso contratto, diagnosi peggiore: qui dentro
    # valgono quanto gli altri quattro.
    'pge.shared.constants',
    'pge.parameters.pitch_unit',
    'pge.parameters.parameter_schema',
    'pge.rendering.envelope_extractor',
)

# Se uno di questi acquista legittimamente una dipendenza pesante, il rosso qui
# e' la richiesta di aprire la issue su PGE-ui prevista da
# .claude/rules/cross-repo-impact.md, non di allentare la guardia.


def test_config_parse_error_eredita_lo_yaml_error_vero_quando_pyyaml_c_e():
    """Il ripiego non deve entrare in funzione dove PyYAML e' installato.

    E' la meta' forte della coppia: senza, il ripiego qui sotto potrebbe
    diventare il ramo normale e la promessa di libreria
    (`Raises: yaml.YAMLError`) cadrebbe in silenzio.
    """
    import yaml
    from pge.shared import exceptions as mod

    assert mod.ConfigParseError.__bases__[-1] is yaml.YAMLError
    assert not mod.PYYAML_ASSENTE


#: Il nome con cui si importa una dipendenza, dove non e' quello con cui il
#: pyproject la dichiara. Una sola voce oggi, ed e' l'unico dato che il
#: pyproject non ha: la mappa distribuzione -> modulo non e' derivabile dal
#: nome. Una dipendenza nuova che non si importi col proprio nome fa fallire
#: `_dipendenze_di_terze_parti` chiedendo di essere nominata qui, invece di
#: entrare nella guardia con un nome che non blocca niente.
_NOME_DI_IMPORT = {'pyyaml': 'yaml'}

#: Quelle che si importano col proprio nome, dichiarate perche' il silenzio
#: non distingua «si importa cosi'» da «nessuno ci ha pensato».
_SI_IMPORTANO_COL_PROPRIO_NOME = frozenset({'numpy', 'soundfile', 'matplotlib'})


def _dipendenze_di_terze_parti():
    """I package di terze parti del motore, coi nomi con cui si importano.

    Letti da `pyproject.toml`, non trascritti qui: una dipendenza aggiunta la'
    entra in questa guardia da sola. Se non si importa col proprio nome e non
    e' in `_NOME_DI_IMPORT`, questa funzione fallisce chiedendo il nome --
    perche' bloccare un modulo che non esiste e' una guardia verde che non
    misura niente.
    """
    import os
    import re

    from pge.shared import exceptions as modulo

    radice = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(modulo.__file__)))))
    testo = open(os.path.join(radice, 'pyproject.toml'), encoding='utf-8').read()

    blocco = re.search(r'^dependencies\s*=\s*\[(.*?)\]', testo, re.M | re.S)
    assert blocco, ("pyproject.toml non dichiara piu' `dependencies` in questa "
                    "forma: la guardia non sa piu' cosa bloccare")

    nomi = []
    for voce in re.findall(r"""["']([^"']+)["']""", blocco.group(1)):
        distribuzione = re.split(r'[<>=!~\[; ]', voce, maxsplit=1)[0].strip().lower()
        if not distribuzione:
            continue
        if distribuzione in _NOME_DI_IMPORT:
            nomi.append(_NOME_DI_IMPORT[distribuzione])
            continue
        assert distribuzione in _SI_IMPORTANO_COL_PROPRIO_NOME, (
            f"dipendenza '{distribuzione}' nuova nel pyproject: dichiara come "
            f"si importa in _NOME_DI_IMPORT o in _SI_IMPORTANO_COL_PROPRIO_NOME, "
            f"altrimenti la guardia blocca un modulo che non esiste e resta verde")
        nomi.append(distribuzione)

    assert 'yaml' in nomi, ("PyYAML non e' piu' fra le dipendenze dichiarate: "
                            "la meta' #257 di questa guardia non misura niente")
    return tuple(sorted(set(nomi)))


def test_il_motore_si_importa_senza_le_dipendenze_di_terze_parti():
    """I moduli che l'oracolo di PGE-ui importa non devono averne una.

    Girato in un interprete figlio con le dipendenze rese non importabili:
    e' l'unico modo di misurare un import, che nel processo corrente e' gia'
    avvenuto.

    Blocca **tutte** le dipendenze dichiarate, non il solo PyYAML che la #257
    ha portato qui. Il contratto di PGE-ui e' «No op may need the engine venv»,
    e il runner del suo job node quel venv non lo costruisce: un `import numpy`
    che scendesse in uno di questi moduli farebbe esattamente il danno che
    questa guardia dichiara di prevenire, e con la sola `yaml` bloccata sarebbe
    passato in silenzio -- l'interprete figlio numpy ce l'ha, il runner di
    PGE-ui no.
    """
    import os
    import subprocess
    import sys
    import textwrap

    from pge.shared import exceptions as modulo

    src_dir = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(modulo.__file__))))

    env = dict(os.environ)
    env['PYTHONPATH'] = src_dir

    bloccati = _dipendenze_di_terze_parti()
    figlio = subprocess.run(
        [sys.executable, '-c', textwrap.dedent("""
            import importlib
            import sys

            bloccati = set(sys.argv[1].split(','))

            class Blocco:
                def find_spec(self, nome, percorso=None, target=None):
                    radice = nome.split('.')[0]
                    if radice in bloccati:
                        raise ImportError("No module named %r" % radice)
                    return None

            sys.meta_path.insert(0, Blocco())
            for nome in sys.argv[2:]:
                importlib.import_module(nome)
            from pge.shared.exceptions import ConfigParseError, ConfigError
            assert issubclass(ConfigParseError, ConfigError)
            print("ok")
        """), ','.join(bloccati), *_MODULI_SENZA_TERZE_PARTI],
        env=env, capture_output=True, text=True)

    assert figlio.returncode == 0, (
        f"senza {', '.join(bloccati)} il motore non si importa piu':\n"
        f"{figlio.stdout}\n{figlio.stderr}")
    assert 'ok' in figlio.stdout


def test_lo_stub_yaml_dei_test_non_manda_exceptions_nel_ripiego():
    """Lo stub di `tests/main_mocks.py` deve portare *tutti* i nomi che
    `exceptions.py` prende da `yaml`, non il primo.

    Il modulo li chiede in due `from ... import` dentro lo stesso `try`, e un
    `from` che non trova un nome alza `ImportError`: uno stub rimasto indietro
    di un nome -- o del sottomodulo `yaml.reader`, che non e' un attributo dello
    stub ma una voce di `sys.modules` --
    manda quell'import nel ramo di ripiego, dove `PYYAML_ASSENTE` diventa vero
    con PyYAML installato e `ConfigParseError` smette di essere un
    `yaml.YAMLError` vero -- cioe' la promessa di libreria della #257 cade, in
    un processo in cui PyYAML c'e'.

    Nel processo corrente non si vede, ed e' il motivo per cui serve questo
    test: `pge.shared.exceptions` e' importato alla raccolta col `yaml` vero,
    quindi la guardia di `test_cli_no_builtin_handlers.py` legge una classe
    gia' creata e direbbe di si' comunque. L'import va misurato dove avviene,
    in un interprete figlio, come per il test qui sopra.
    """
    import os
    import subprocess
    import sys
    import textwrap

    from pge.shared import exceptions as modulo

    src_dir = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(modulo.__file__))))
    radice = os.path.dirname(src_dir)

    env = dict(os.environ)
    env['PYTHONPATH'] = os.pathsep.join([radice, src_dir])

    figlio = subprocess.run(
        [sys.executable, '-c', textwrap.dedent("""
            import sys
            import yaml as yaml_vero
            import yaml.reader as reader_vero
            from tests.main_mocks import _make_mock_yaml_module

            # Entrambi, e non solo `yaml`: `from yaml.reader import ...` si
            # risolve su `sys.modules['yaml.reader']`, quindi lasciare li' il
            # modulo vero misurerebbe PyYAML invece dello stub -- verde
            # qualunque cosa lo stub porti.
            stub, stub_reader = _make_mock_yaml_module()
            sys.modules['yaml'] = stub
            sys.modules['yaml.reader'] = stub_reader
            from pge.shared.exceptions import (
                ConfigParseError, ConfigReaderParseError, PYYAML_ASSENTE)

            assert not PYYAML_ASSENTE, (
                "sotto lo stub exceptions crede che PyYAML non ci sia")
            assert issubclass(ConfigParseError, yaml_vero.YAMLError), (
                "sotto lo stub ConfigParseError non e' un yaml.YAMLError vero")
            assert issubclass(ConfigReaderParseError, reader_vero.ReaderError), (
                "sotto lo stub ConfigReaderParseError non e' un "
                "yaml.reader.ReaderError vero")
            print("ok")
        """)],
        env=env, capture_output=True, text=True)

    assert figlio.returncode == 0, (
        "lo stub yaml dei test non regge l'import di pge.shared.exceptions:\n"
        f"{figlio.stdout}\n{figlio.stderr}")
    assert 'ok' in figlio.stdout


# -----------------------------------------------------------------------------
# Il tipo concreto della causa: `except IsADirectoryError` deve sopravvivere
# -----------------------------------------------------------------------------
#
# Impacchettare e' un guadagno finche' non toglie. Prima della #257 `load_yaml`
# lasciava salire l'eccezione *concreta* di `open()`, quindi un
# `except IsADirectoryError` scritto a valle funzionava; un `ConfigReadError`
# che eredita il solo `OSError` lo fa smettere di funzionare. E' la stessa
# promessa che le altre due classi mantengono verso `FileNotFoundError` e
# `yaml.YAMLError`: mantenerla a meta' era una scelta che nessuno aveva preso.
#
# La regola non cambia -- il tipo deve dire il vero -- e qui il builtin dice il
# vero, perche' e' quello che il sistema operativo ha sollevato.


def test_la_tabella_dei_builtin_di_lettura_non_puo_mentire():
    """Ogni voce eredita la propria chiave, ed e' un `ConfigReadError`.

    La tabella e' corta di proposito (i builtin che descrivono il *path*, non
    la macchina) e il ripiego non e' un buco: `ConfigReadError` resta un
    `OSError` e porta `errno`. Ma corta o lunga, non deve poter mentire.
    """
    from pge.shared.exceptions import ConfigReadError, LETTURA_PER_BUILTIN

    assert LETTURA_PER_BUILTIN, "tabella vuota: la guardia non misura niente"
    for builtin, classe in LETTURA_PER_BUILTIN.items():
        assert issubclass(classe, builtin), (
            f"{classe.__name__} non eredita {builtin.__name__}: chi cattura "
            f"il builtin per nome smette di catturarlo")
        assert issubclass(classe, ConfigReadError)
        assert not issubclass(classe, FileNotFoundError), (
            f"{classe.__name__} eredita FileNotFoundError: il tipo mente")


def test_config_read_error_di_una_directory_resta_un_IsADirectoryError():
    """`pge configs/ out.wav`, il typo che la tab-completion fabbrica da sola."""
    from pge.shared.exceptions import (
        ConfigReadError, EngineError, config_read_error)

    err = config_read_error(
        'configs/', IsADirectoryError(21, 'Is a directory', 'configs/'))

    assert isinstance(err, IsADirectoryError)
    assert isinstance(err, ConfigReadError)
    assert isinstance(err, EngineError)
    # Il messaggio non cambia: la sottoclasse aggiunge solo il tipo.
    assert str(err) == "File di configurazione non leggibile: 'configs/'"
    assert '  Dettaglio:    Is a directory' in err.user_message()


def test_config_read_error_dei_permessi_resta_un_PermissionError():
    """L'altro caso che i doc nominano: EACCES."""
    from pge.shared.exceptions import ConfigReadError, config_read_error

    err = config_read_error(
        'configs/x.yml', PermissionError(13, 'Permission denied', 'configs/x.yml'))

    assert isinstance(err, PermissionError)
    assert isinstance(err, ConfigReadError)
    assert not isinstance(err, IsADirectoryError)


def test_config_read_error_generico_quando_il_builtin_non_ha_un_tipo_suo():
    """Il ripiego: resta `ConfigReadError`, che e' un `OSError` con `errno`."""
    from pge.shared.exceptions import ConfigReadError, config_read_error

    causa = OSError(36, 'File name too long', 'x' * 300)
    err = config_read_error('x' * 300, causa)

    assert type(err) is ConfigReadError
    assert isinstance(err, OSError)
    assert err.errno == 36


# -----------------------------------------------------------------------------
# Lo stesso, dall'altra parte: `except yaml.MarkedYAMLError`
# -----------------------------------------------------------------------------
#
# `problem_mark` e' riportato sull'eccezione, ma l'idioma completo con cui si
# legge un errore PyYAML e' `isinstance(e, MarkedYAMLError)` *poi* `e.problem_mark`
# -- il tipo e' la domanda «questa eccezione porta una posizione?». Ereditare il
# solo `YAMLError` risponde no a un errore che la posizione ce l'ha.


def test_config_parse_error_marcato_resta_un_MarkedYAMLError():
    """Un errore con posizione resta riconoscibile come tale."""
    import yaml
    from pge.shared.exceptions import ConfigParseError, config_parse_error

    cause = None
    try:
        yaml.safe_load("a: 1\nb: [2, 3\nc: 4\n")
    except yaml.YAMLError as e:
        cause = e
    assert cause is not None and isinstance(cause, yaml.MarkedYAMLError)

    err = config_parse_error('configs/rotto.yml', cause)

    assert isinstance(err, yaml.MarkedYAMLError)
    assert isinstance(err, ConfigParseError)
    assert err.problem_mark is cause.problem_mark


def test_config_parse_error_marcato_tiene_lo_str_di_dominio():
    """Il prezzo, gia' pagato due volte per `OSError.__str__`.

    `MarkedYAMLError.__str__` riscrive il messaggio nel formato di PyYAML
    (contesto, snippet, freccia), ed e' quella la riga che finisce nel log
    engine e nel ramo generico della CLI. La coppia col test sopra e' il punto:
    l'uno senza l'altro e' una regressione.
    """
    import yaml
    from pge.shared.exceptions import config_parse_error

    cause = None
    try:
        yaml.safe_load("a: 1\nb: [2, 3\nc: 4\n")
    except yaml.YAMLError as e:
        cause = e

    err = config_parse_error('configs/rotto.yml', cause)

    assert str(err) == "File di configurazione malformato: 'configs/rotto.yml'"
    assert 'in "<unicode string>"' not in str(err)


def test_config_parse_error_non_marcato_non_finge_di_esserlo():
    """Un `yaml.YAMLError` nudo non porta una posizione: il tipo non deve
    dire il contrario, come gli attributi non vanno fabbricati."""
    import yaml
    from pge.shared.exceptions import config_parse_error

    err = config_parse_error('configs/rotto.yml', yaml.YAMLError('boom'))

    assert isinstance(err, yaml.YAMLError)
    assert not isinstance(err, yaml.MarkedYAMLError)


def test_config_parse_error_di_una_decodifica_resta_un_UnicodeDecodeError():
    """Il `.yml` in latin-1: prima `load_yaml` lasciava salire il builtin."""
    from pge.shared.exceptions import ConfigParseError, config_parse_error

    causa = None
    try:
        'perch\xe8'.encode('latin-1').decode('utf-8')
    except UnicodeDecodeError as e:
        causa = e

    err = config_parse_error('configs/latin1.yml', causa)

    assert isinstance(err, UnicodeDecodeError)
    assert isinstance(err, ConfigParseError)
    assert str(err) == "File di configurazione malformato: 'configs/latin1.yml'"


def test_config_parse_error_di_un_carattere_rifiutato_resta_un_ReaderError():
    """L'ultimo `yaml.YAMLError` del percorso di caricamento a perdere il
    proprio tipo concreto.

    `ReaderError` e' l'unico non marcato che il *load* possa produrre -- gli
    altri quattro (Emitter, Representer, Serializer, Resolver) stanno sul lato
    dump -- quindi era l'unico caso rimasto in cui impacchettare *toglieva*:
    prima della #257 `load_yaml` lasciava salire l'eccezione concreta, e con
    lei `e.position` ed `e.character`, che sono le sole cose che dicano quale
    carattere il parser rifiuta e dove. `config_parse_error` mappava
    `MarkedYAMLError` e `UnicodeDecodeError` e lasciava questo alla base,
    contro la regola che la #257 dichiara per tutti gli altri.
    """
    import yaml.reader
    from pge.shared.exceptions import ConfigParseError, config_parse_error

    causa = None
    try:
        yaml.safe_load('titolo: "a\x07b"\n')
    except yaml.YAMLError as e:
        causa = e
    assert isinstance(causa, yaml.reader.ReaderError), (
        f"non e' piu' un ReaderError che PyYAML solleva qui: {type(causa)}")

    err = config_parse_error('configs/ctrl.yml', causa)

    assert isinstance(err, yaml.reader.ReaderError)
    assert isinstance(err, ConfigParseError)
    # Il tipo senza lo stato e' meta' promessa: la stessa regola dei tre campi
    # `OSError` e dei cinque di `UnicodeDecodeError`.
    assert err.position == causa.position
    assert err.character == causa.character
    assert err.reason == causa.reason


def test_config_parse_error_di_un_carattere_rifiutato_tiene_lo_str_di_dominio():
    """Il prezzo, per la terza volta: `ReaderError.__str__` scrive due righe
    col nome del file e la posizione, ed e' quella la riga che finisce nel log
    engine. La coppia col test sopra e' il punto."""
    import yaml
    from pge.shared.exceptions import config_parse_error

    causa = None
    try:
        yaml.safe_load('titolo: "a\x07b"\n')
    except yaml.YAMLError as e:
        causa = e

    err = config_parse_error('configs/ctrl.yml', causa)

    assert str(err) == "File di configurazione malformato: 'configs/ctrl.yml'"
    assert '\n' not in str(err)


# -----------------------------------------------------------------------------
# Le tre classi devono sopravvivere al pickle
# -----------------------------------------------------------------------------
#
# I builtin che la #257 sostituisce erano tutti picklabili -- e' cosi' che una
# eccezione attraversa un confine di processo: `ProcessPoolExecutor` la ripaga
# nel parent proprio spicchiandola, ed e' il meccanismo su cui gira
# `numpy_parallel`. Un wrapper con `__init__` a due argomenti e `args` di uno
# solo rompe il `__reduce__` di default, in due modi diversi: `TypeError` in
# unpickling per chi ha due argomenti, e messaggio annidato due volte per chi
# ne ha uno (`OSError.__reduce__` ripassa `args`, non `path`).


def _classi_di_configurazione():
    import yaml
    from pge.shared import exceptions as mod

    causa_yaml = None
    try:
        yaml.safe_load("a: 1\nb: [2, 3\nc: 4\n")
    except yaml.YAMLError as e:
        causa_yaml = e
    causa_unicode = None
    try:
        'perch\xe8'.encode('latin-1').decode('utf-8')
    except UnicodeDecodeError as e:
        causa_unicode = e
    causa_reader = None
    try:
        yaml.safe_load('titolo: "a\x07b"\n')
    except yaml.YAMLError as e:
        causa_reader = e

    return [
        mod.ConfigFileNotFoundError('configs/missing.yml'),
        mod.config_parse_error('configs/rotto.yml', yaml.YAMLError('boom')),
        mod.config_parse_error('configs/rotto.yml', causa_yaml),
        mod.config_parse_error('configs/latin1.yml', causa_unicode),
        mod.config_parse_error('configs/ctrl.yml', causa_reader),
        mod.config_read_error(
            'configs/', IsADirectoryError(21, 'Is a directory', 'configs/')),
        mod.config_read_error('configs/x.yml', OSError(36, 'File name too long')),
    ]


def test_le_eccezioni_di_configurazione_sopravvivono_al_pickle():
    """Tipo, messaggio e stato del builtin, dall'altra parte del confine."""
    import pickle

    for err in _classi_di_configurazione():
        rifatto = pickle.loads(pickle.dumps(err))

        assert type(rifatto) is type(err), f"{type(err).__name__}: tipo perso"
        assert str(rifatto) == str(err), (
            f"{type(err).__name__}: messaggio {str(rifatto)!r} invece di "
            f"{str(err)!r}")
        assert rifatto.path == err.path
        assert rifatto.config_file == err.config_file
        assert rifatto.user_message() == err.user_message()


def test_il_pickle_non_annida_il_messaggio():
    """Il modo silenzioso di sbagliare: nessun errore, `str()` doppio.

    `OSError.__reduce__` ripassa `self.args` al costruttore, e il costruttore
    di queste classi vuole il *path*: senza `__reduce__` proprio, il messaggio
    gia' costruito rientrava come path e usciva impacchettato due volte.
    """
    import pickle
    from pge.shared.exceptions import ConfigFileNotFoundError

    err = ConfigFileNotFoundError('configs/missing.yml')
    rifatto = pickle.loads(pickle.dumps(err))

    assert rifatto.args == err.args
    assert str(rifatto).count('File di configurazione non trovato') == 1
