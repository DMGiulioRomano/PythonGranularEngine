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
    """La CLI intercetta FileNotFoundError per annunciare «file YAML non
    trovato»: un binario mancante che passasse di li' verrebbe riportato
    come una configurazione inesistente (stessa regola di
    SuperColliderNotFoundError)."""
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
