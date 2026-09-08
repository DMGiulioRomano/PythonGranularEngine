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
    """La CLI intercettava FileNotFoundError per annunciare «file YAML non
    trovato»: un binario mancante che passasse di li' verrebbe riportato
    come una configurazione inesistente (stessa regola di
    SuperColliderNotFoundError). Dalla #257 quell'handler non c'e' piu', e a
    separare i due guasti non e' piu' la posizione di un `except` ma il tipo:
    dentro EngineError il builtin appartiene al solo `ConfigFileNotFoundError`,
    quindi la regola vale per chiunque lo catturi, CLI o no. E' la stessa che
    `test_solo_la_configurazione_e_un_FileNotFoundError` deriva dalla
    gerarchia, piu' in giu' in questo file: qui se ne fissa il caso csound."""
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
# Issue #257 — lo YAML che manca (o che non si legge) ha un tipo, non una
# posizione nel file sorgente della CLI
# =============================================================================

def test_config_file_not_found_e_un_config_error():
    """Un file di configurazione che non esiste e' un errore di configurazione:
    sta sotto ConfigError, quindi `except EngineError` della CLI lo prende."""
    from pge.shared.exceptions import (
        ConfigError, ConfigFileNotFoundError, EngineError,
    )
    err = ConfigFileNotFoundError('configs/mancante.yml')
    assert isinstance(err, ConfigError)
    assert isinstance(err, EngineError)
    # ConfigError eredita ValueError, e la sottoclasse non lo perde.
    assert isinstance(err, ValueError)


def test_config_file_not_found_eredita_FileNotFoundError():
    """Qui il builtin non e' una bugia: il file che manca e' proprio quello.

    E' l'asimmetria con `_BinaryNotFoundError` (#228/#241), che il builtin lo
    rifiuta perche' li' descriveva un file diverso da quello che il tipo
    lasciava intendere. `Generator.load_yaml` e `api.load_generator`
    dichiarano FileNotFoundError fra i `Raises`: chi lo cattura continua a
    catturarlo."""
    from pge.shared.exceptions import ConfigFileNotFoundError
    err = ConfigFileNotFoundError('configs/mancante.yml')
    assert isinstance(err, FileNotFoundError)
    assert isinstance(err, OSError)


def _famiglia_engine_error():
    """Ogni sottoclasse di EngineError che il pacchetto `pge` dichiara.

    Derivata dall'albero delle classi, non dai membri di
    `pge.shared.exceptions`. I due insiemi coincidono oggi perche' la
    convenzione vuole le eccezioni li' (punto 1 di
    docs/reference/errors.md), ma «dove la convenzione le vuole» non e'
    «dove finiranno»: una sottoclasse dichiarata in un modulo di rendering
    non comparirebbe fra i membri di quel file, e la regola qui sotto
    tacerebbe proprio sul caso per cui esiste — un secondo erede di
    `FileNotFoundError` nato lontano da dove qualcuno lo cerchera'.

    I moduli si importano tutti prima di leggere `__subclasses__`, o la
    risposta dipenderebbe da quali test hanno gia' girato; il filtro su
    `__module__` tiene fuori le sottoclassi sintetiche dei test, per la
    stessa ragione.
    """
    import importlib
    import pkgutil

    import pge
    from pge.shared.exceptions import EngineError

    for modulo in pkgutil.walk_packages(pge.__path__, 'pge.'):
        importlib.import_module(modulo.name)

    def discendenti(base):
        for figlia in base.__subclasses__():
            yield figlia
            yield from discendenti(figlia)

    return {cls for cls in discendenti(EngineError)
            if cls.__module__.startswith('pge.')}


def test_solo_la_configurazione_e_un_FileNotFoundError():
    """La regola che #228/#241 e #257 scrivono insieme, derivata dalla
    gerarchia invece che trascritta: dentro EngineError `FileNotFoundError`
    significa una cosa sola — il file di configurazione che hai nominato non
    esiste. Se un domani un binario assente, o un sample, tornasse a
    ereditarlo, il tipo smetterebbe di isolare e questo test lo direbbe."""
    famiglia = _famiglia_engine_error()
    # La famiglia e' popolata: senza questa riga il test passerebbe anche su
    # un modulo vuoto.
    assert len(famiglia) > 10
    eredi = {cls.__name__ for cls in famiglia
             if issubclass(cls, FileNotFoundError)}
    assert eredi == {'ConfigFileNotFoundError'}


def test_la_regola_vede_anche_una_sottoclasse_dichiarata_altrove():
    """La guardia misurata invece che riasserita.

    Il caso che distingue le due letture: una sottoclasse di `EngineError`
    che non sta in `pge/shared/exceptions.py`. Leggendo i membri di quel
    modulo non esiste; leggendo l'albero delle classi si', ed e' la lettura
    che la regola qui sopra richiede — altrimenti basterebbe dichiarare il
    secondo erede di `FileNotFoundError` un file piu' in la' per farla
    tacere. Non eredita `FileNotFoundError` di proposito: una classe
    sintetica che sopravvivesse al test non deve poter arrossare la regola
    vera.
    """
    import gc
    import inspect

    from pge.shared import exceptions as exc

    class ErroreDichiaratoAltrove(exc.EngineError):
        pass

    # `__subclasses__` non guarda dove il file sta sul disco, guarda
    # `__module__`: e' quello che va falsificato per simulare la classe
    # dichiarata in un altro modulo di `pge`.
    ErroreDichiaratoAltrove.__module__ = 'pge.engine.generator'
    try:
        assert ErroreDichiaratoAltrove in _famiglia_engine_error()

        membri = {cls for _, cls in inspect.getmembers(exc, inspect.isclass)
                  if issubclass(cls, exc.EngineError)}
        assert ErroreDichiaratoAltrove not in membri, (
            "la lettura per membri di modulo la vede: il caso scelto non "
            "distingue le due letture, e la misura non misura niente")
    finally:
        del ErroreDichiaratoAltrove
        gc.collect()


def test_config_file_not_found_user_message_nomina_il_file_e_il_path():
    from pge.shared.exceptions import ConfigFileNotFoundError
    err = ConfigFileNotFoundError('configs/mancante.yml')
    msg = err.user_message()
    assert "[ERRORE]" in msg
    assert "File di configurazione non trovato" in msg
    # Il nome come l'utente l'ha scritto, sulla riga di contesto di casa.
    assert "  Config:       configs/mancante.yml" in msg
    # E il path risolto, che dice in quale directory si e' cercato.
    import os
    assert os.path.abspath('configs/mancante.yml') in msg


def test_config_file_not_found_non_ripete_il_path_gia_assoluto():
    """Un intervallo che non esiste non si stampa (regola di
    ParameterBoundError); un path che coincide con quello gia' scritto
    nemmeno."""
    from pge.shared.exceptions import ConfigFileNotFoundError
    err = ConfigFileNotFoundError('/tmp/assoluto/mancante.yml')
    msg = err.user_message()
    assert "Path cercato" not in msg
    assert msg.count('/tmp/assoluto/mancante.yml') == 1


def test_config_file_not_found_valorizza_config_file():
    """Il contesto strutturato e' quello di casa: chi legge l'eccezione a
    programma trova il path dove lo trova in tutte le sorelle."""
    from pge.shared.exceptions import ConfigFileNotFoundError
    err = ConfigFileNotFoundError('configs/mancante.yml')
    assert err.config_file == 'configs/mancante.yml'


def test_config_parse_error_e_un_config_error_e_uno_yaml_error():
    """Il file c'e' ma non si legge: stessa famiglia, stesso trattamento.

    `yaml.YAMLError` resta fra le basi per la stessa ragione del builtin
    accanto — `load_yaml` e `api.load_generator` lo dichiarano nei `Raises`."""
    import yaml
    from pge.shared.exceptions import (
        ConfigError, ConfigParseError, EngineError,
    )
    err = ConfigParseError('configs/rotto.yml', reason='qualcosa')
    assert isinstance(err, ConfigError)
    assert isinstance(err, EngineError)
    assert isinstance(err, yaml.YAMLError)


def test_config_parse_error_user_message():
    from pge.shared.exceptions import ConfigParseError
    err = ConfigParseError('configs/rotto.yml',
                           reason="expected <block end>, but found ':'",
                           line=4, column=10)
    msg = err.user_message()
    assert "[ERRORE]" in msg
    assert "YAML non valido" in msg
    assert "  Motivo:       expected <block end>, but found ':'" in msg
    assert "  Posizione:    riga 4, colonna 10" in msg
    assert "  Config:       configs/rotto.yml" in msg


def test_config_parse_error_senza_posizione_non_stampa_la_riga():
    from pge.shared.exceptions import ConfigParseError
    err = ConfigParseError('configs/rotto.yml', reason='qualcosa')
    assert "Posizione" not in err.user_message()


def test_config_parse_error_from_yaml_error_legge_problema_e_marca():
    """La posizione la sa gia' PyYAML: `problem` e `problem_mark` di
    MarkedYAMLError. Le righe di YAML si contano da 1, il mark da 0."""
    import yaml
    from pge.shared.exceptions import ConfigParseError

    testo = "composition:\n  title: uno\n   cattiva: due\n"
    with pytest.raises(yaml.YAMLError) as excinfo:
        yaml.safe_load(testo)

    err = ConfigParseError.from_yaml_error('configs/rotto.yml', excinfo.value)
    assert err.reason == excinfo.value.problem
    assert err.line == excinfo.value.problem_mark.line + 1
    assert err.column == excinfo.value.problem_mark.column + 1


def test_config_parse_error_from_yaml_error_senza_marca():
    """Un YAMLError generico non ha `problem_mark`: il motivo resta, la
    posizione non si inventa."""
    import yaml
    from pge.shared.exceptions import ConfigParseError

    err = ConfigParseError.from_yaml_error('x.yml', yaml.YAMLError('rotto'))
    assert 'rotto' in err.reason
    assert err.line is None and err.column is None


def test_config_file_not_found_compila_i_campi_di_oserror():
    """Ereditare il tipo non basta: chi cattura FileNotFoundError legge
    `filename` e confronta `errno` con ENOENT. Su un wrapper nudo sono None,
    cioe' la compatibilita' regge per `isinstance` e cade per tutto il resto,
    in silenzio -- la stessa forma di guasto che la #257 chiude un piano piu'
    su."""
    import errno
    from pge.shared.exceptions import ConfigFileNotFoundError
    err = ConfigFileNotFoundError('configs/mancante.yml')
    assert err.errno == errno.ENOENT
    assert err.filename == 'configs/mancante.yml'
    assert err.strerror


def test_config_file_not_found_str_resta_il_messaggio_di_casa():
    """Il prezzo dei campi qui sopra, pagato: con `filename` valorizzato
    `OSError.__str__` scriverebbe «[Errno 2] No such file or directory» e
    butterebbe via la prosa -- ed e' `str(err)` che finisce nel log engine e
    nel ramo generico di chi cattura."""
    from pge.shared.exceptions import ConfigFileNotFoundError
    err = ConfigFileNotFoundError('configs/mancante.yml')
    assert str(err) == "File di configurazione non trovato: 'configs/mancante.yml'"
    assert 'Errno' not in str(err)


def test_config_file_not_found_sopravvive_a_pickle_e_copy():
    """Terzo modo di rompere la stessa promessa, e il piu' silenzioso.

    `OSError.__reduce__` accoda `filename` agli `args` — un OSError si
    ricostruisce da `(errno, strerror, filename)`. Valorizzare `filename`
    (il test qui sopra) mette quindi questa classe nel caso in cui `args` e'
    la sola prosa: senza `__reduce__`, il round trip chiamava
    `ConfigFileNotFoundError(<la prosa>)` e tornava indietro un'eccezione con
    il messaggio annidato dentro se' stesso e `path`/`filename` uguali al
    messaggio. Nessuna eccezione sollevata: esattamente la compatibilita' che
    regge per `isinstance` e cade in silenzio per tutto il resto.
    """
    import copy
    import errno
    import pickle
    from pge.shared.exceptions import ConfigFileNotFoundError

    originale = ConfigFileNotFoundError('configs/mancante.yml')
    # Arricchito come il punto 5 di docs/reference/errors.md prescrive per
    # ogni sottoclasse di ConfigError. Senza questa riga il round trip si
    # misura sui soli campi che `__init__` ricostruisce dal path, cioe' su
    # tutto tranne l'unico stato che il path non contiene: il test
    # resterebbe verde su un `__reduce__` che butta via il `__dict__`, e la
    # riga `Stream:` sparirebbe dal messaggio senza sollevare niente --
    # ancora la promessa che regge per `isinstance` e cade in silenzio.
    originale.stream_id = 'stream1'
    for ricostruito in (pickle.loads(pickle.dumps(originale)),
                        copy.copy(originale),
                        copy.deepcopy(originale)):
        assert isinstance(ricostruito, ConfigFileNotFoundError)
        assert str(ricostruito) == str(originale)
        assert ricostruito.path == 'configs/mancante.yml'
        assert ricostruito.filename == 'configs/mancante.yml'
        assert ricostruito.config_file == 'configs/mancante.yml'
        assert ricostruito.errno == errno.ENOENT
        assert ricostruito.stream_id == 'stream1'
        assert ricostruito.user_message() == originale.user_message()
        assert '  Stream:       stream1' in ricostruito.user_message()
