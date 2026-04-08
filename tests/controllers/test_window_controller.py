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