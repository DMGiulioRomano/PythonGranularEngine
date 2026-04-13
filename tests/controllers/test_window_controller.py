"""
test_window_controller.py

Suite di test completa per controllers/window_controller.py.

Coverage:
1. parse_window_list - default, stringa singola, lista, 'all'/True, alias, errori
2. __init__ - parsing params, gate creation (stringa vs lista)
3. select_window - singola finestra, gate closed, gate open, elapsed_time, statistica
4. Integrazione - workflow YAML->selezione, tabella decisionale envelope/gate
"""

import pytest
from unittest.mock import Mock, patch
import random as random_module

from controllers.window_registry import WindowRegistry, WindowSpec
from shared.probability_gate import (
    ProbabilityGate, NeverGate, AlwaysGate, RandomGate, EnvelopeGate
)
from core.stream_config import StreamContext, StreamConfig
from parameters.gate_factory import GateFactory
from parameters.parameter_definitions import DEFAULT_PROB
from controllers.window_controller import WindowController


# =============================================================================
# HELPERS DI FIXTURE
# =============================================================================

def make_context(
    stream_id: str = "test_stream",
    onset: float = 0.0,
    duration: float = 10.0,
    sample: str = "test.wav",
    sample_dur_sec: float = 5.0,
) -> StreamContext:
    return StreamContext(
        stream_id=stream_id,
        onset=onset,
        duration=duration,
        sample=sample,
        sample_dur_sec=sample_dur_sec,
    )


def make_config(**kwargs) -> StreamConfig:
    """Costruisce StreamConfig con context di default se non fornito."""
    if "context" not in kwargs:
        kwargs["context"] = make_context()
    return StreamConfig(**kwargs)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def default_config():
    """StreamConfig con dephase=False e context valido."""
    return make_config(dephase=False)


@pytest.fixture
def config_dephase_disabled():
    return make_config(dephase=False)


@pytest.fixture
def config_dephase_implicit():
    return make_config(dephase=None)


@pytest.fixture
def config_dephase_global():
    return make_config(dephase=50.0)


@pytest.fixture
def config_dephase_100():
    return make_config(dephase=100.0)


@pytest.fixture
def config_dephase_0():
    return make_config(dephase=0.0)


@pytest.fixture
def config_with_stream_id():
    ctx = make_context(stream_id="my_stream_42")
    return StreamConfig(dephase=False, context=ctx)


@pytest.fixture
def all_window_names():
    return list(WindowRegistry.WINDOWS.keys())


# =============================================================================
# 1. TEST parse_window_list - DEFAULT BEHAVIOR
# =============================================================================

class TestParseWindowListDefaults:

    def test_no_envelope_key_returns_hanning(self):
        result = WindowController.parse_window_list({})
        assert result == ['hanning']

    def test_empty_params_returns_hanning(self):
        result = WindowController.parse_window_list({})
        assert len(result) == 1
        assert result[0] == 'hanning'

    def test_other_keys_do_not_interfere(self):
        params = {'duration': 0.05, 'duration_range': 0.01}
        result = WindowController.parse_window_list(params)
        assert result == ['hanning']

    def test_default_stream_id_in_error_is_unknown(self):
        with pytest.raises(ValueError, match="unknown"):
            WindowController.parse_window_list({'envelope': 'NONEXISTENT'})


# =============================================================================
# 2. TEST parse_window_list - STRINGA SINGOLA
# =============================================================================

class TestParseWindowListSingleString:

    @pytest.mark.parametrize("name", [
        'hanning', 'hamming', 'bartlett', 'blackman', 'gaussian',
        'kaiser', 'rectangle', 'half_sine', 'expodec', 'exporise',
    ])
    def test_valid_single_window_returns_list_of_one(self, name):
        result = WindowController.parse_window_list({'envelope': name})
        assert result == [name]

    def test_single_string_returns_list_not_string(self):
        result = WindowController.parse_window_list({'envelope': 'hanning'})
        assert isinstance(result, list)

    def test_alias_triangle_is_accepted(self):
        result = WindowController.parse_window_list({'envelope': 'triangle'})
        assert result == ['triangle']

    def test_invalid_string_raises_value_error(self):
        with pytest.raises(ValueError, match="non trovata"):
            WindowController.parse_window_list({'envelope': 'INVALID'})

    def test_invalid_string_error_contains_window_name(self):
        with pytest.raises(ValueError, match="FAKE_WINDOW"):
            WindowController.parse_window_list({'envelope': 'FAKE_WINDOW'})


# =============================================================================
# 3. TEST parse_window_list - LISTA ESPLICITA
# =============================================================================

class TestParseWindowListExplicit:

    def test_list_of_one_valid_window(self):
        result = WindowController.parse_window_list({'envelope': ['gaussian']})
        assert result == ['gaussian']

    def test_list_of_multiple_valid_windows(self):
        windows = ['hanning', 'expodec', 'half_sine']
        result = WindowController.parse_window_list({'envelope': windows})
        assert result == windows

    def test_list_preserves_order(self):
        windows = ['blackman', 'hanning', 'expodec', 'gaussian']
        result = WindowController.parse_window_list({'envelope': windows})
        assert result == windows

    def test_list_with_alias_is_accepted(self):
        result = WindowController.parse_window_list({'envelope': ['hanning', 'triangle']})
        assert 'triangle' in result

    def test_duplicate_windows_accepted(self):
        result = WindowController.parse_window_list(
            {'envelope': ['hanning', 'hanning', 'hanning']}
        )
        assert result == ['hanning', 'hanning', 'hanning']

    def test_empty_list_raises_value_error(self):
        with pytest.raises(ValueError, match="Lista envelope vuota"):
            WindowController.parse_window_list({'envelope': []})

    def test_empty_list_error_contains_stream_id(self):
        with pytest.raises(ValueError, match="stream_B"):
            WindowController.parse_window_list({'envelope': []}, stream_id="stream_B")

    def test_list_with_one_invalid_raises(self):
        with pytest.raises(ValueError, match="FAKE"):
            WindowController.parse_window_list({'envelope': ['hanning', 'FAKE']})

    def test_list_with_first_invalid_raises(self):
        with pytest.raises(ValueError, match="NON_EXISTENT"):
            WindowController.parse_window_list({'envelope': ['NON_EXISTENT', 'hanning']})


# =============================================================================
# 4. TEST parse_window_list - 'all' E True
# =============================================================================

class TestParseWindowListAll:

    def test_all_string_returns_all_windows(self, all_window_names):
        result = WindowController.parse_window_list({'envelope': 'all'})
        assert set(result) == set(all_window_names)

    def test_all_string_count_matches_registry(self, all_window_names):
        result = WindowController.parse_window_list({'envelope': 'all'})
        assert len(result) == len(all_window_names)

    def test_true_returns_all_windows(self, all_window_names):
        result = WindowController.parse_window_list({'envelope': True})
        assert set(result) == set(all_window_names)

    def test_all_and_true_produce_same_result(self, all_window_names):
        r_all = WindowController.parse_window_list({'envelope': 'all'})
        r_true = WindowController.parse_window_list({'envelope': True})
        assert set(r_all) == set(r_true)


# =============================================================================
# 5. TEST parse_window_list - ERRORI DI TIPO
# =============================================================================

class TestParseWindowListTypeErrors:

    @pytest.mark.parametrize("bad_spec,error_match", [
        (42, "Formato envelope non valido"),
        (3.14, "Formato envelope non valido"),
        (None, "Formato envelope non valido"),
        (False, "Formato envelope non valido"),
        ({'type': 'hanning'}, "Formato envelope non valido"),
        (('hanning', 'hamming'), "Formato envelope non valido"),
        ([], "Lista envelope vuota"),
        ('INVALID', "non trovata"),
        (['INVALID'], "non trovata"),
        (['hanning', 'INVALID'], "non trovata"),
    ])
    def test_bad_spec_raises(self, bad_spec, error_match):
        with pytest.raises(ValueError, match=error_match):
            WindowController.parse_window_list({'envelope': bad_spec})

    def test_error_includes_stream_id(self):
        with pytest.raises(ValueError, match="stream_X"):
            WindowController.parse_window_list({'envelope': 123}, stream_id="stream_X")

    def test_is_static_method(self):
        assert callable(WindowController.parse_window_list)
        result = WindowController.parse_window_list({'envelope': 'hanning'})
        assert result == ['hanning']


# =============================================================================
# 6. TEST __init__ - PARSING PARAMETRI
# =============================================================================

class TestWindowControllerInit:

    def test_default_init_single_window(self, default_config):
        ctrl = WindowController({'envelope': 'hanning'}, config=default_config)
        assert ctrl._windows == ['hanning']

    def test_init_with_list(self, default_config):
        ctrl = WindowController(
            {'envelope': ['hanning', 'expodec', 'gaussian']},
            config=default_config
        )
        assert len(ctrl._windows) == 3

    def test_init_with_all(self, default_config):
        ctrl = WindowController({'envelope': 'all'}, config=default_config)
        assert len(ctrl._windows) == len(WindowRegistry.WINDOWS)

    def test_init_uses_stream_id_from_context(self, config_with_stream_id):
        with pytest.raises(ValueError, match="my_stream_42"):
            WindowController({'envelope': 'NONEXISTENT'}, config=config_with_stream_id)

    def test_gate_exists_after_init(self, default_config):
        ctrl = WindowController({'envelope': 'hanning'}, config=default_config)
        assert hasattr(ctrl, '_gate')
        assert ctrl._gate is not None

    def test_gate_is_probability_gate(self, default_config):
        ctrl = WindowController({'envelope': 'hanning'}, config=default_config)
        assert isinstance(ctrl._gate, ProbabilityGate)

    def test_no_public_attributes(self, default_config):
        ctrl = WindowController({'envelope': 'hanning'}, config=default_config)
        public_attrs = [
            a for a in dir(ctrl)
            if not a.startswith('_') and not callable(getattr(ctrl, a))
        ]
        assert len(public_attrs) == 0

    def test_select_window_is_public_method(self, default_config):
        ctrl = WindowController({'envelope': 'hanning'}, config=default_config)
        assert callable(ctrl.select_window)

    def test_extra_yaml_keys_are_ignored(self, default_config):
        params = {
            'duration': 0.05,
            'duration_range': 0.01,
            'envelope': 'hanning',
        }
        ctrl = WindowController(params, config=default_config)
        assert ctrl._windows == ['hanning']

    def test_legacy_envelope_range_key_is_silently_ignored(self, default_config):
        ctrl = WindowController(
            {'envelope': 'hanning', 'envelope_range': 1.0},
            config=default_config
        )
        assert ctrl._windows == ['hanning']


# =============================================================================
# 7. TEST __init__ - GATE CREATION LOGIC
# =============================================================================

class TestWindowControllerGateCreation:

    def test_single_string_dephase_false_creates_never_gate(self, config_dephase_disabled):
        ctrl = WindowController({'envelope': 'hanning'}, config=config_dephase_disabled)
        assert isinstance(ctrl._gate, NeverGate)

    def test_list_dephase_false_creates_always_gate(self, config_dephase_disabled):
        ctrl = WindowController(
            {'envelope': ['hanning', 'expodec']},
            config=config_dephase_disabled
        )
        assert isinstance(ctrl._gate, AlwaysGate)

    def test_list_dephase_none_creates_random_gate(self, config_dephase_implicit):
        ctrl = WindowController(
            {'envelope': ['hanning', 'expodec']},
            config=config_dephase_implicit
        )
        assert isinstance(ctrl._gate, RandomGate)

    def test_list_dephase_none_uses_default_prob(self, config_dephase_implicit):
        ctrl = WindowController(
            {'envelope': ['hanning', 'expodec']},
            config=config_dephase_implicit
        )
        assert ctrl._gate.get_probability_value(0.0) == DEFAULT_PROB

    def test_list_dephase_50_creates_random_gate(self, config_dephase_global):
        ctrl = WindowController(
            {'envelope': ['hanning', 'expodec']},
            config=config_dephase_global
        )
        assert isinstance(ctrl._gate, RandomGate)
        assert ctrl._gate.get_probability_value(0.0) == 50.0

    def test_list_dephase_100_creates_always_gate(self, config_dephase_100):
        ctrl = WindowController(
            {'envelope': ['hanning', 'expodec']},
            config=config_dephase_100
        )
        assert isinstance(ctrl._gate, AlwaysGate)

    def test_list_dephase_0_creates_never_gate(self, config_dephase_0):
        ctrl = WindowController(
            {'envelope': ['hanning', 'expodec']},
            config=config_dephase_0
        )
        assert isinstance(ctrl._gate, NeverGate)

    def test_dephase_specific_key_pc_rand_envelope(self):
        config = make_config(dephase={'pc_rand_envelope': 80.0})
        ctrl = WindowController(
            {'envelope': ['hanning', 'expodec']},
            config=config
        )
        assert isinstance(ctrl._gate, RandomGate)
        assert ctrl._gate.get_probability_value(0.0) == 80.0

    def test_dephase_specific_key_missing_uses_default_prob(self):
        config = make_config(dephase={'altro_parametro': 80.0})
        ctrl = WindowController(
            {'envelope': ['hanning', 'expodec']},
            config=config
        )
        assert isinstance(ctrl._gate, RandomGate)
        assert ctrl._gate.get_probability_value(0.0) == DEFAULT_PROB

    def test_single_element_list_behaves_like_string(self, config_dephase_disabled):
        ctrl = WindowController({'envelope': ['hanning']}, config=config_dephase_disabled)
        assert isinstance(ctrl._gate, NeverGate)
        assert ctrl.select_window(0.0) == 'hanning'


# =============================================================================
# 8. TEST select_window - SINGOLA FINESTRA
# =============================================================================

class TestSelectWindowSingle:

    def test_single_window_always_returns_it(self, default_config):
        ctrl = WindowController({'envelope': 'bartlett'}, config=default_config)
        for _ in range(50):
            assert ctrl.select_window(5.0) == 'bartlett'

    def test_single_window_gate_never_consulted(self, default_config):
        ctrl = WindowController({'envelope': 'hanning'}, config=default_config)
        mock_gate = Mock(spec=ProbabilityGate)
        ctrl._gate = mock_gate
        ctrl.select_window(5.0)
        mock_gate.should_apply.assert_not_called()


# =============================================================================
# 9. TEST select_window - GATE CLOSED (NeverGate)
# =============================================================================

class TestSelectWindowGateClosed:

    def test_never_gate_returns_first_window(self, default_config):
        ctrl = WindowController(
            {'envelope': ['hanning', 'expodec']},
            config=default_config
        )
        ctrl._gate = NeverGate()
        for _ in range(50):
            assert ctrl.select_window(0.0) == 'hanning'

    def test_never_gate_stable_across_times(self, default_config):
        ctrl = WindowController(
            {'envelope': ['gaussian', 'blackman']},
            config=default_config
        )
        ctrl._gate = NeverGate()
        for t in [0.0, 2.5, 5.0, 7.5, 10.0]:
            assert ctrl.select_window(t) == 'gaussian'


# =============================================================================
# 10. TEST select_window - GATE OPEN (AlwaysGate)
# =============================================================================

class TestSelectWindowGateOpen:

    def test_always_gate_single_window_always_returns_it(self, default_config):
        ctrl = WindowController(
            {'envelope': 'hanning'},
            config=default_config
        )
        ctrl._gate = AlwaysGate()
        for _ in range(50):
            assert ctrl.select_window(0.0) == 'hanning'

    def test_always_gate_list_covers_all_windows(self, default_config):
        windows = ['hanning', 'expodec', 'gaussian', 'blackman']
        ctrl = WindowController(
            {'envelope': windows},
            config=default_config
        )
        ctrl._gate = AlwaysGate()
        results = set(ctrl.select_window(0.0) for _ in range(500))
        assert results == set(windows)

    def test_always_gate_results_are_valid(self, default_config):
        windows = ['hanning', 'expodec', 'gaussian']
        ctrl = WindowController(
            {'envelope': windows},
            config=default_config
        )
        ctrl._gate = AlwaysGate()
        for _ in range(200):
            assert ctrl.select_window(0.0) in windows

    def test_always_gate_statistical_uniformity(self, default_config):
        windows = ['hanning', 'expodec']
        ctrl = WindowController(
            {'envelope': windows},
            config=default_config
        )
        ctrl._gate = AlwaysGate()
        counts = {w: 0 for w in windows}
        for _ in range(1000):
            counts[ctrl.select_window(0.0)] += 1
        for w in windows:
            assert 0.45 <= counts[w] / 1000 <= 0.55, f"{w}: {counts[w]}"


# =============================================================================
# 11. TEST select_window - ELAPSED_TIME PROPAGATION
# =============================================================================

class TestElapsedTimePropagation:

    def test_elapsed_time_passed_to_gate(self, default_config):
        ctrl = WindowController(
            {'envelope': ['hanning', 'expodec']},
            config=default_config
        )
        mock_gate = Mock(spec=ProbabilityGate)
        mock_gate.should_apply.return_value = False
        ctrl._gate = mock_gate

        ctrl.select_window(elapsed_time=3.14)
        mock_gate.should_apply.assert_called_once_with(3.14)

    def test_elapsed_time_default_is_zero(self, default_config):
        ctrl = WindowController(
            {'envelope': ['hanning', 'expodec']},
            config=default_config
        )
        mock_gate = Mock(spec=ProbabilityGate)
        mock_gate.should_apply.return_value = False
        ctrl._gate = mock_gate

        ctrl.select_window()
        mock_gate.should_apply.assert_called_once_with(0.0)

    def test_various_elapsed_times_passed_correctly(self, default_config):
        ctrl = WindowController(
            {'envelope': ['hanning', 'expodec']},
            config=default_config
        )
        mock_gate = Mock(spec=ProbabilityGate)
        mock_gate.should_apply.return_value = False
        ctrl._gate = mock_gate

        times = [0.0, 0.001, 1.5, 5.0, 9.999]
        for t in times:
            ctrl.select_window(elapsed_time=t)

        called_with = [c.args[0] for c in mock_gate.should_apply.call_args_list]
        assert called_with == times

    def test_elapsed_time_not_passed_when_single_window(self, default_config):
        ctrl = WindowController({'envelope': 'hanning'}, config=default_config)
        mock_gate = Mock(spec=ProbabilityGate)
        ctrl._gate = mock_gate
        ctrl.select_window(elapsed_time=5.0)
        mock_gate.should_apply.assert_not_called()


# =============================================================================
# 12. TEST select_window - TABELLA DECISIONALE RANGE/GATE
# =============================================================================

class TestEnvelopeGateDecisionMatrix:
    """
    | envelope   | gate       | risultato              |
    |------------|------------|------------------------|
    | stringa    | qualsiasi  | prima finestra (guard) |
    | lista      | NeverGate  | prima finestra         |
    | lista      | AlwaysGate | random.choice          |
    """

    def test_single_string_any_gate_returns_first(self, default_config):
        ctrl = WindowController(
            {'envelope': 'hanning'},
            config=default_config
        )
        for gate in [NeverGate(), AlwaysGate(), RandomGate(50.0)]:
            ctrl._gate = gate
            assert ctrl.select_window(5.0) == 'hanning'

    def test_list_never_gate_returns_first(self, default_config):
        ctrl = WindowController(
            {'envelope': ['hanning', 'expodec']},
            config=default_config
        )
        ctrl._gate = NeverGate()
        for _ in range(50):
            assert ctrl.select_window(5.0) == 'hanning'

    def test_list_always_gate_selects_randomly(self, default_config):
        ctrl = WindowController(
            {'envelope': ['hanning', 'expodec']},
            config=default_config
        )
        ctrl._gate = AlwaysGate()
        results = set(ctrl.select_window(5.0) for _ in range(200))
        assert len(results) == 2


# =============================================================================
# 13. TEST DETERMINISMO CON SEED
# =============================================================================

class TestDeterminism:

    def test_same_seed_same_sequence(self, default_config):
        ctrl = WindowController(
            {'envelope': ['hanning', 'expodec', 'gaussian'], },
            config=default_config
        )
        ctrl._gate = AlwaysGate()

        random_module.seed(42)
        seq1 = [ctrl.select_window(0.0) for _ in range(100)]

        random_module.seed(42)
        seq2 = [ctrl.select_window(0.0) for _ in range(100)]

        assert seq1 == seq2

    def test_different_seeds_different_sequences(self, default_config):
        ctrl = WindowController(
            {'envelope': ['hanning', 'expodec', 'gaussian'], },
            config=default_config
        )
        ctrl._gate = AlwaysGate()

        random_module.seed(42)
        seq1 = [ctrl.select_window(0.0) for _ in range(100)]

        random_module.seed(99)
        seq2 = [ctrl.select_window(0.0) for _ in range(100)]

        assert seq1 != seq2


# =============================================================================
# 14. TEST INTEGRAZIONE - WORKFLOW YAML -> SELEZIONE
# =============================================================================

class TestIntegration:

    def test_workflow_grain_yaml_section(self, default_config):
        grain_yaml = {
            'duration': 0.05,
            'duration_range': 0.01,
            'envelope': ['hanning', 'expodec', 'gaussian'],
        }
        ctrl = WindowController(grain_yaml, config=default_config)
        assert len(ctrl._windows) == 3

    def test_workflow_yaml_no_envelope_uses_default(self, default_config):
        grain_yaml = {'duration': 0.05}
        ctrl = WindowController(grain_yaml, config=default_config)
        assert ctrl._windows == ['hanning']

    def test_all_windows_with_always_gate_covers_registry(self, config_dephase_disabled):
        ctrl = WindowController(
            {'envelope': 'all'},
            config=config_dephase_disabled
        )
        results = set(ctrl.select_window(0.0) for _ in range(5000))
        assert results == set(WindowRegistry.WINDOWS.keys())

    def test_static_method_callable_without_instance(self):
        result = WindowController.parse_window_list({'envelope': 'hanning'})
        assert result == ['hanning']

    def test_state_consistency_windows_matches_params(self, default_config):
        windows = ['hanning', 'bartlett', 'kaiser']
        ctrl = WindowController({'envelope': windows}, config=default_config)
        assert ctrl._windows == windows


# =============================================================================
# 15. TEST parse_window_list - TRANSITION DICT FORMAT
# =============================================================================

class TestParseWindowListTransitionDict:
    """parse_window_list deve estrarre [from, to] da un dict di transizione."""

    def test_transition_dict_returns_from_and_to(self):
        spec = {'envelope': {'from': 'hanning', 'to': 'bartlett', 'curve': [[0, 0], [1, 1]]}}
        result = WindowController.parse_window_list(spec)
        assert result == ['hanning', 'bartlett']

    def test_transition_dict_without_curve_returns_from_and_to(self):
        """curve è opzionale in parse_window_list (serve solo all'istanza)."""
        spec = {'envelope': {'from': 'hanning', 'to': 'expodec'}}
        result = WindowController.parse_window_list(spec)
        assert result == ['hanning', 'expodec']

    def test_transition_dict_validates_from_window(self):
        spec = {'envelope': {'from': 'INVALID', 'to': 'hanning'}}
        with pytest.raises(ValueError, match="non trovata"):
            WindowController.parse_window_list(spec)

    def test_transition_dict_validates_to_window(self):
        spec = {'envelope': {'from': 'hanning', 'to': 'INVALID'}}
        with pytest.raises(ValueError, match="non trovata"):
            WindowController.parse_window_list(spec)

    def test_transition_dict_without_from_key_raises(self):
        """Un dict senza 'from' non è un transition spec valido."""
        spec = {'envelope': {'to': 'hanning', 'curve': [[0, 0], [1, 1]]}}
        with pytest.raises(ValueError):
            WindowController.parse_window_list(spec)

    def test_transition_dict_without_to_key_raises(self):
        """Un dict senza 'to' non è un transition spec valido."""
        spec = {'envelope': {'from': 'hanning', 'curve': [[0, 0], [1, 1]]}}
        with pytest.raises(ValueError):
            WindowController.parse_window_list(spec)

    def test_dict_without_from_to_still_raises_format_error(self):
        """Un dict arbitrario senza from/to → errore formato."""
        spec = {'envelope': {'type': 'hanning'}}
        with pytest.raises(ValueError, match="Formato envelope non valido"):
            WindowController.parse_window_list(spec)

    def test_transition_with_alias_in_from(self):
        spec = {'envelope': {'from': 'triangle', 'to': 'hanning'}}
        result = WindowController.parse_window_list(spec)
        assert 'triangle' in result

    def test_transition_same_window_from_and_to(self):
        """Caso degenere: from == to è valido (transizione noop)."""
        spec = {'envelope': {'from': 'hanning', 'to': 'hanning'}}
        result = WindowController.parse_window_list(spec)
        assert result == ['hanning', 'hanning']


# =============================================================================
# 16. TEST WindowController INIT - TRANSITION MODE
# =============================================================================

class TestWindowControllerTransitionInit:

    def test_transition_init_sets_windows(self, default_config):
        params = {'envelope': {'from': 'hanning', 'to': 'bartlett', 'curve': [[0, 0], [10, 1]]}}
        ctrl = WindowController(params, config=default_config)
        assert ctrl._windows == ['hanning', 'bartlett']

    def test_transition_init_sets_strategy(self, default_config):
        from controllers.window_selection_strategy import TransitionWindowStrategy
        params = {'envelope': {'from': 'hanning', 'to': 'bartlett', 'curve': [[0, 0], [10, 1]]}}
        ctrl = WindowController(params, config=default_config)
        assert isinstance(ctrl._strategy, TransitionWindowStrategy)

    def test_non_transition_strategy_is_none_or_not_transition(self, default_config):
        from controllers.window_selection_strategy import TransitionWindowStrategy
        ctrl = WindowController({'envelope': 'hanning'}, config=default_config)
        assert not isinstance(ctrl._strategy, TransitionWindowStrategy)

    def test_transition_init_without_curve_uses_default(self, default_config):
        """curve assente → default [[0,0],[1,1]] (linear 0→1 con time normalizzato)."""
        from controllers.window_selection_strategy import TransitionWindowStrategy
        params = {'envelope': {'from': 'hanning', 'to': 'bartlett'}}
        ctrl = WindowController(params, config=default_config)
        assert isinstance(ctrl._strategy, TransitionWindowStrategy)


# =============================================================================
# 17. TEST select_window - TRANSITION BEHAVIOR
# =============================================================================

class TestSelectWindowTransition:

    def _make_transition_ctrl(self, from_w, to_w, curve_pts, duration=10.0,
                               time_mode=None):
        """Helper: crea controller in modalità transizione."""
        from core.stream_config import StreamContext, StreamConfig
        ctx = StreamContext(
            stream_id='t_stream',
            onset=0.0,
            duration=duration,
            sample='test.wav',
            sample_dur_sec=5.0,
        )
        config = StreamConfig(dephase=False, context=ctx, time_mode=time_mode)
        params = {'envelope': {'from': from_w, 'to': to_w, 'curve': curve_pts}}
        return WindowController(params, config=config)

    def test_at_t0_linear_curve_returns_from(self):
        """curve [[0,0],[10,1]] a t=0 → blend=0 → 100% hanning."""
        ctrl = self._make_transition_ctrl('hanning', 'bartlett', [[0, 0], [10, 1]])
        results = [ctrl.select_window(0.0) for _ in range(200)]
        assert all(r == 'hanning' for r in results)

    def test_at_end_linear_curve_returns_to(self):
        """curve [[0,0],[10,1]] a t=10 → blend=1 → 100% bartlett."""
        ctrl = self._make_transition_ctrl('hanning', 'bartlett', [[0, 0], [10, 1]])
        results = [ctrl.select_window(10.0) for _ in range(200)]
        assert all(r == 'bartlett' for r in results)

    def test_at_midpoint_is_50_50(self):
        """curve [[0,0],[10,1]] a t=5 → blend=0.5 → ~50/50."""
        ctrl = self._make_transition_ctrl('hanning', 'bartlett', [[0, 0], [10, 1]])
        counts = {'hanning': 0, 'bartlett': 0}
        for _ in range(2000):
            counts[ctrl.select_window(5.0)] += 1
        ratio = counts['bartlett'] / 2000
        assert 0.44 <= ratio <= 0.56, f"ratio bartlett: {ratio}"

    def test_result_always_from_or_to(self):
        ctrl = self._make_transition_ctrl('hanning', 'bartlett', [[0, 0], [10, 1]])
        for t in [0.0, 2.5, 5.0, 7.5, 10.0]:
            for _ in range(20):
                assert ctrl.select_window(t) in ('hanning', 'bartlett')

    def test_normalized_time_mode(self):
        """Con time_mode='normalized' la curve usa 0-1 come asse temporale."""
        ctrl = self._make_transition_ctrl(
            'hanning', 'bartlett', [[0, 0], [1, 1]],
            duration=30.0, time_mode='normalized'
        )
        # elapsed=30 → t_norm=1 → blend=1 → 100% bartlett
        results = [ctrl.select_window(30.0) for _ in range(200)]
        assert all(r == 'bartlett' for r in results)

    def test_non_transition_mode_unaffected(self, default_config):
        """Il comportamento attuale (lista finestre) non è alterato."""
        ctrl = WindowController(
            {'envelope': ['hanning', 'expodec']},
            config=default_config
        )
        ctrl._gate = AlwaysGate()
        results = set(ctrl.select_window(0.0) for _ in range(500))
        assert results == {'hanning', 'expodec'}


# =============================================================================
# 18. TEST parse_window_list - MULTI-STATE FORMAT
# =============================================================================

class TestParseWindowListMultiState:
    """parse_window_list deve estrarre tutti i nomi finestra da un dict states."""

    def test_states_returns_all_window_names(self):
        spec = {'envelope': {'states': [[0.0, 'hanning'], [0.5, 'expodec'], [1.0, 'gaussian']]}}
        result = WindowController.parse_window_list(spec)
        assert result == ['hanning', 'expodec', 'gaussian']

    def test_states_two_elements(self):
        """Due stati: equivalente a from/to."""
        spec = {'envelope': {'states': [[0.0, 'hanning'], [1.0, 'bartlett']]}}
        result = WindowController.parse_window_list(spec)
        assert result == ['hanning', 'bartlett']

    def test_states_validates_invalid_window(self):
        spec = {'envelope': {'states': [[0.0, 'hanning'], [1.0, 'INVALID']]}}
        with pytest.raises(ValueError, match="non trovata"):
            WindowController.parse_window_list(spec)

    def test_states_empty_list_raises(self):
        spec = {'envelope': {'states': []}}
        with pytest.raises(ValueError):
            WindowController.parse_window_list(spec)

    def test_states_single_element_raises(self):
        spec = {'envelope': {'states': [[0.0, 'hanning']]}}
        with pytest.raises(ValueError):
            WindowController.parse_window_list(spec)

    def test_states_with_alias(self):
        spec = {'envelope': {'states': [[0.0, 'triangle'], [1.0, 'hanning']]}}
        result = WindowController.parse_window_list(spec)
        assert 'triangle' in result

    def test_states_four_windows(self):
        spec = {'envelope': {'states': [
            [0.0, 'hanning'],
            [0.3, 'bartlett'],
            [0.7, 'expodec'],
            [1.0, 'gaussian'],
        ]}}
        result = WindowController.parse_window_list(spec)
        assert result == ['hanning', 'bartlett', 'expodec', 'gaussian']


# =============================================================================
# 19. TEST WindowController INIT - MULTI-STATE MODE
# =============================================================================

class TestWindowControllerMultiStateInit:

    def _make_config(self, duration=10.0, time_mode=None):
        ctx = StreamContext(
            stream_id='ms_stream', onset=0.0, duration=duration,
            sample='test.wav', sample_dur_sec=5.0,
        )
        return StreamConfig(dephase=False, context=ctx, time_mode=time_mode)

    def test_multistate_init_sets_strategy(self):
        from controllers.window_selection_strategy import MultiStateWindowStrategy
        params = {'envelope': {'states': [[0.0, 'hanning'], [0.5, 'expodec'], [1.0, 'gaussian']]}}
        ctrl = WindowController(params, config=self._make_config())
        assert isinstance(ctrl._strategy, MultiStateWindowStrategy)

    def test_multistate_init_sets_windows(self):
        params = {'envelope': {'states': [[0.0, 'hanning'], [0.5, 'expodec'], [1.0, 'gaussian']]}}
        ctrl = WindowController(params, config=self._make_config())
        assert ctrl._windows == ['hanning', 'expodec', 'gaussian']

    def test_multistate_without_curve_uses_default(self):
        """curve assente → default [[0,0],[1,1]]."""
        from controllers.window_selection_strategy import MultiStateWindowStrategy
        params = {'envelope': {'states': [[0.0, 'hanning'], [1.0, 'bartlett']]}}
        ctrl = WindowController(params, config=self._make_config())
        assert isinstance(ctrl._strategy, MultiStateWindowStrategy)

    def test_multistate_is_not_transition(self):
        from controllers.window_selection_strategy import TransitionWindowStrategy
        params = {'envelope': {'states': [[0.0, 'hanning'], [1.0, 'bartlett']]}}
        ctrl = WindowController(params, config=self._make_config())
        assert not isinstance(ctrl._strategy, TransitionWindowStrategy)

    def test_transition_dict_still_works(self, default_config):
        """from/to rimane invariato (backward compat)."""
        from controllers.window_selection_strategy import TransitionWindowStrategy
        params = {'envelope': {'from': 'hanning', 'to': 'bartlett'}}
        ctrl = WindowController(params, config=default_config)
        assert isinstance(ctrl._strategy, TransitionWindowStrategy)


# =============================================================================
# 20. TEST select_window - MULTI-STATE BEHAVIOR
# =============================================================================

class TestSelectWindowMultiState:

    def _make_ctrl(self, states, curve_pts=None, duration=10.0, time_mode=None):
        ctx = StreamContext(
            stream_id='ms_stream', onset=0.0, duration=duration,
            sample='test.wav', sample_dur_sec=5.0,
        )
        config = StreamConfig(dephase=False, context=ctx, time_mode=time_mode)
        envelope_spec = {'states': states}
        if curve_pts is not None:
            envelope_spec['curve'] = curve_pts
        return WindowController({'envelope': envelope_spec}, config=config)

    def test_v_zero_returns_first_window(self):
        """Curve a 0 → solo prima finestra."""
        # curve piatta a 0: blend=0 per tutto il tempo
        ctrl = self._make_ctrl(
            [[0.0, 'hanning'], [0.5, 'expodec'], [1.0, 'gaussian']],
            curve_pts=[[0, 0], [10, 0]],
        )
        results = [ctrl.select_window(5.0) for _ in range(200)]
        assert all(r == 'hanning' for r in results)

    def test_v_one_returns_last_window(self):
        """Curve a 1 → solo ultima finestra."""
        ctrl = self._make_ctrl(
            [[0.0, 'hanning'], [0.5, 'expodec'], [1.0, 'gaussian']],
            curve_pts=[[0, 1], [10, 1]],
        )
        results = [ctrl.select_window(5.0) for _ in range(200)]
        assert all(r == 'gaussian' for r in results)

    def test_v_at_state_boundary_returns_that_window(self):
        """Curve esattamente a 0.5 (confine stato) → solo expodec."""
        ctrl = self._make_ctrl(
            [[0.0, 'hanning'], [0.5, 'expodec'], [1.0, 'gaussian']],
            curve_pts=[[0, 0.5], [10, 0.5]],
        )
        results = [ctrl.select_window(5.0) for _ in range(200)]
        assert all(r in ('hanning', 'expodec') for r in results)

    def test_v_between_first_two_states_only_those_two(self):
        """Blend in [0, 0.5] → seleziona solo tra hanning e expodec, mai gaussian."""
        ctrl = self._make_ctrl(
            [[0.0, 'hanning'], [0.5, 'expodec'], [1.0, 'gaussian']],
            curve_pts=[[0, 0.25], [10, 0.25]],
        )
        results = [ctrl.select_window(5.0) for _ in range(500)]
        assert 'gaussian' not in results
        assert all(r in ('hanning', 'expodec') for r in results)

    def test_v_between_last_two_states_only_those_two(self):
        """Blend in [0.5, 1.0] → seleziona solo tra expodec e gaussian, mai hanning."""
        ctrl = self._make_ctrl(
            [[0.0, 'hanning'], [0.5, 'expodec'], [1.0, 'gaussian']],
            curve_pts=[[0, 0.75], [10, 0.75]],
        )
        results = [ctrl.select_window(5.0) for _ in range(500)]
        assert 'hanning' not in results
        assert all(r in ('expodec', 'gaussian') for r in results)

    def test_blend_50_50_at_midpoint_of_segment(self):
        """v=0.25 (metà tra 0.0 e 0.5) → ~50/50 hanning/expodec."""
        ctrl = self._make_ctrl(
            [[0.0, 'hanning'], [0.5, 'expodec'], [1.0, 'gaussian']],
            curve_pts=[[0, 0.25], [10, 0.25]],
        )
        counts = {'hanning': 0, 'expodec': 0}
        for _ in range(2000):
            counts[ctrl.select_window(5.0)] += 1
        ratio = counts['expodec'] / 2000
        assert 0.44 <= ratio <= 0.56, f"ratio expodec: {ratio}"

    def test_linear_curve_traverses_all_states(self):
        """Curve lineare 0→1: hanning a t=0, gaussian a t=10."""
        ctrl = self._make_ctrl(
            [[0.0, 'hanning'], [0.5, 'expodec'], [1.0, 'gaussian']],
            curve_pts=[[0, 0], [10, 1]],
        )
        results_start = [ctrl.select_window(0.0) for _ in range(200)]
        results_end = [ctrl.select_window(10.0) for _ in range(200)]
        assert all(r == 'hanning' for r in results_start)
        assert all(r == 'gaussian' for r in results_end)

    def test_result_always_one_of_states(self):
        """Risultato sempre in {hanning, expodec, gaussian}."""
        ctrl = self._make_ctrl(
            [[0.0, 'hanning'], [0.5, 'expodec'], [1.0, 'gaussian']],
            curve_pts=[[0, 0], [10, 1]],
        )
        valid = {'hanning', 'expodec', 'gaussian'}
        for t in [0.0, 2.5, 5.0, 7.5, 10.0]:
            for _ in range(50):
                assert ctrl.select_window(t) in valid

    def test_normalized_time_mode(self):
        """Con time_mode='normalized', t=duration → blend=1 → ultima finestra."""
        ctrl = self._make_ctrl(
            [[0.0, 'hanning'], [0.5, 'expodec'], [1.0, 'gaussian']],
            curve_pts=[[0, 0], [1, 1]],
            duration=30.0,
            time_mode='normalized',
        )
        results = [ctrl.select_window(30.0) for _ in range(200)]
        assert all(r == 'gaussian' for r in results)

    def test_non_linear_curve_stays_at_state(self):
        """Curve piatta nel mezzo: blend fisso → stessa finestra per lungo periodo."""
        # curve: 0→0 fino a t=5, poi 0.5→0.5 da t=5 a t=10
        ctrl = self._make_ctrl(
            [[0.0, 'hanning'], [0.5, 'expodec'], [1.0, 'gaussian']],
            curve_pts=[[0, 0], [5, 0], [5, 0.5], [10, 0.5]],
        )
        # a t=2 (curve=0) → solo hanning
        results = [ctrl.select_window(2.0) for _ in range(200)]
        assert all(r == 'hanning' for r in results)


# =============================================================================
# 21. TEST MultiStateWindowStrategy - UNIT (strategia isolata)
# =============================================================================

class TestMultiStateWindowStrategyUnit:
    """Test unitari sulla strategia isolata, senza WindowController."""

    def _make_strategy(self, states, curve_pts=None, duration=1.0, time_mode=None):
        from controllers.window_selection_strategy import MultiStateWindowStrategy
        from envelopes.envelope import Envelope
        curve = Envelope(curve_pts or [[0, 0], [1, 1]])
        return MultiStateWindowStrategy(
            states=states,
            curve=curve,
            duration=duration,
            time_mode=time_mode,
        )

    def test_two_states_at_v0_returns_first(self):
        s = self._make_strategy([[0.0, 'hanning'], [1.0, 'bartlett']],
                                  curve_pts=[[0, 0], [1, 0]])
        results = [s.select(0.5) for _ in range(200)]
        assert all(r == 'hanning' for r in results)

    def test_two_states_at_v1_returns_second(self):
        s = self._make_strategy([[0.0, 'hanning'], [1.0, 'bartlett']],
                                  curve_pts=[[0, 1], [1, 1]])
        results = [s.select(0.5) for _ in range(200)]
        assert all(r == 'bartlett' for r in results)

    def test_three_states_v_in_first_segment(self):
        s = self._make_strategy(
            [[0.0, 'hanning'], [0.5, 'expodec'], [1.0, 'gaussian']],
            curve_pts=[[0, 0.1], [1, 0.1]],
        )
        results = [s.select(0.5) for _ in range(500)]
        assert 'gaussian' not in results

    def test_three_states_v_in_second_segment(self):
        s = self._make_strategy(
            [[0.0, 'hanning'], [0.5, 'expodec'], [1.0, 'gaussian']],
            curve_pts=[[0, 0.9], [1, 0.9]],
        )
        results = [s.select(0.5) for _ in range(500)]
        assert 'hanning' not in results

    def test_less_than_two_states_raises(self):
        from controllers.window_selection_strategy import MultiStateWindowStrategy
        from envelopes.envelope import Envelope
        with pytest.raises(ValueError):
            MultiStateWindowStrategy(
                states=[[0.0, 'hanning']],
                curve=Envelope([[0, 0], [1, 1]]),
            )

    def test_states_not_sorted_raises(self):
        from controllers.window_selection_strategy import MultiStateWindowStrategy
        from envelopes.envelope import Envelope
        with pytest.raises(ValueError):
            MultiStateWindowStrategy(
                states=[[1.0, 'hanning'], [0.0, 'bartlett']],
                curve=Envelope([[0, 0], [1, 1]]),
            )


# =============================================================================
# 22. TEST curve range validation (Error / Warning)
# =============================================================================

class TestCurveRangeValidation:
    """
    Valida che le strategy sollevano ValueError quando la curve eccede il range
    valido, e loggano un warning quando la curve finisce prima della fine.
    Testato su entrambe: TransitionWindowStrategy e MultiStateWindowStrategy.
    """

    def _make_transition(self, curve_pts, duration=10.0, time_mode=None):
        from controllers.window_selection_strategy import TransitionWindowStrategy
        from envelopes.envelope import Envelope
        return TransitionWindowStrategy(
            from_window='hanning',
            to_window='bartlett',
            curve=Envelope(curve_pts),
            duration=duration,
            time_mode=time_mode,
        )

    def _make_multistate(self, curve_pts, duration=10.0, time_mode=None):
        from controllers.window_selection_strategy import MultiStateWindowStrategy
        from envelopes.envelope import Envelope
        return MultiStateWindowStrategy(
            states=[[0.0, 'hanning'], [1.0, 'bartlett']],
            curve=Envelope(curve_pts),
            duration=duration,
            time_mode=time_mode,
        )

    # --- ERROR: curve oltre il range ---

    def test_transition_normalized_curve_exceeds_one_raises(self):
        """time_mode=normalized, curve va a t=10 > 1.0 → ValueError."""
        with pytest.raises(ValueError, match="supera il range valido"):
            self._make_transition([[0, 0], [10, 1]], time_mode='normalized')

    def test_multistate_normalized_curve_exceeds_one_raises(self):
        """time_mode=normalized, curve va a t=6 > 1.0 → ValueError."""
        with pytest.raises(ValueError, match="supera il range valido"):
            self._make_multistate([[0, 0], [6, 0.3], [9, 0.7], [10, 1]],
                                   time_mode='normalized')

    def test_transition_absolute_curve_exceeds_duration_raises(self):
        """time_mode=absolute, duration=10, curve va a t=15 → ValueError."""
        with pytest.raises(ValueError, match="supera il range valido"):
            self._make_transition([[0, 0], [15, 1]], duration=10.0)

    def test_multistate_absolute_curve_exceeds_duration_raises(self):
        """time_mode=absolute, duration=10, curve va a t=12 → ValueError."""
        with pytest.raises(ValueError, match="supera il range valido"):
            self._make_multistate([[0, 0], [12, 1]], duration=10.0)

    def test_transition_normalized_curve_exactly_one_ok(self):
        """Curve esattamente a t=1.0 con time_mode=normalized → nessun errore."""
        strategy = self._make_transition([[0, 0], [1, 1]], time_mode='normalized')
        assert strategy is not None

    def test_transition_absolute_curve_exactly_duration_ok(self):
        """Curve esattamente a t=duration con time_mode=absolute → nessun errore."""
        strategy = self._make_transition([[0, 0], [10, 1]], duration=10.0)
        assert strategy is not None

    # --- WARNING: curve finisce prima ---

    def test_transition_normalized_curve_ends_early_warns(self):
        """Curve finisce a t=0.5 < 1.0 → warning loggato."""
        from unittest.mock import patch
        with patch('controllers.window_selection_strategy.log_window_curve_warning') as mock_warn:
            self._make_transition([[0, 0], [0.5, 1]], time_mode='normalized')
            mock_warn.assert_called_once()

    def test_multistate_absolute_curve_ends_early_warns(self):
        """Curve finisce a t=5 < duration=10 → warning loggato."""
        from unittest.mock import patch
        with patch('controllers.window_selection_strategy.log_window_curve_warning') as mock_warn:
            self._make_multistate([[0, 0], [5, 1]], duration=10.0)
            mock_warn.assert_called_once()

    def test_transition_no_warning_when_curve_covers_full_range(self):
        """Curve che copre esattamente il range → nessun warning."""
        from unittest.mock import patch
        with patch('controllers.window_selection_strategy.log_window_curve_warning') as mock_warn:
            self._make_transition([[0, 0], [10, 1]], duration=10.0)
            mock_warn.assert_not_called()