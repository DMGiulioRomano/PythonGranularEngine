"""
test_parameter_factory.py

Test suite completa per parameter_factory.py e parameter_orchestrator.py.

Coverage:
1. Test ParameterFactory - creazione base
2. Test _get_nested - navigazione YAML
3. Test create_smart_parameter
4. Test create_raw_parameter
5. Test ParameterOrchestrator - orchestrazione completa
6. Test create_parameter_with_gate - gate injection
7. Test ExclusiveGroupSelector - gruppi mutuamente esclusivi
8. Test integrazione schema completi
9. Test error handling
10. Test edge cases
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from typing import Dict, List, Any, Optional
from dataclasses import dataclass
# Import reali per test su create_constant_parameter
from shared.probability_gate import ProbabilityGate
from core.stream_config import StreamConfig, StreamContext
from parameters.parameter import Parameter
from parameters.parameter_schema import ParameterSpec
from parameters.exclusive_selector import ExclusiveGroupSelector
from parameters.parser import GranularParser
from parameters.parameter_factory import ParameterFactory
from parameters.parameter_orchestrator import ParameterOrchestrator
# =============================================================================
# MOCK CLASSES E STRUCTURES
# =============================================================================

def make_config() -> StreamConfig:
    context = StreamContext(
        stream_id='test_stream',
        onset=0.0,
        duration=10.0,
        sample='test.wav',
        sample_dur_sec=5.0,
    )
    return StreamConfig(context=context)

# Mock functions
def get_parameter_definition(name):
    """Mock get_parameter_definition."""
    return ParameterBounds()

# =============================================================================
# 1. TEST PARAMETER FACTORY - INITIALIZATION
# =============================================================================

class TestParameterFactoryInitialization:
    """Test ParameterFactory initialization."""
    
    def test_create_factory_with_config(self):
        """Create factory with StreamConfig."""
        config = make_config()
        factory = ParameterFactory(config)
        
        assert factory._stream_id == "test_stream"
        assert isinstance(factory._parser, GranularParser)
    
    def test_factory_creates_parser(self):
        """Factory creates GranularParser internally."""
        config = make_config()
        factory = ParameterFactory(config)
        
        assert hasattr(factory, '_parser')
        assert factory._parser.stream_id == "test_stream"


# =============================================================================
# 2. TEST _GET_NESTED
# =============================================================================

class TestGetNested:
    """Test _get_nested - YAML navigation."""
    
    def test_simple_key(self):
        """Navigate simple key."""
        data = {'volume': -6.0}
        
        result = ParameterFactory._get_nested(data, 'volume', 0.0)
        
        assert result == -6.0
    
    def test_nested_key(self):
        """Navigate nested key with dot notation."""
        data = {'grain': {'duration': 0.05}}
        
        result = ParameterFactory._get_nested(data, 'grain.duration', 0.1)
        
        assert result == 0.05
    
    def test_deep_nested_key(self):
        """Navigate deeply nested key."""
        data = {'a': {'b': {'c': 42}}}
        
        result = ParameterFactory._get_nested(data, 'a.b.c', 0)
        
        assert result == 42
    
    def test_missing_key_returns_default(self):
        """Missing key returns default."""
        data = {'volume': -6.0}
        
        result = ParameterFactory._get_nested(data, 'missing', 0.0)
        
        assert result == 0.0
    
    def test_partial_path_returns_default(self):
        """Partial path (not complete) returns default."""
        data = {'grain': {'duration': 0.05}}
        
        result = ParameterFactory._get_nested(data, 'grain.missing', 0.1)
        
        assert result == 0.1
    
    def test_non_dict_in_path_returns_default(self):
        """Non-dict in path returns default."""
        data = {'grain': 42}  # Not a dict
        
        result = ParameterFactory._get_nested(data, 'grain.duration', 0.1)
        
        assert result == 0.1
    
    def test_internal_marker_returns_default(self):
        """Path starting with _ returns default."""
        data = {'test': 10}
        
        result = ParameterFactory._get_nested(data, '_internal_calc_', 0)
        
        assert result == 0


# =============================================================================
# 3. TEST CREATE_SMART_PARAMETER
# =============================================================================

class TestCreateSmartParameter:
    """Test create_smart_parameter."""
    
    def test_create_parameter_from_simple_value(self):
        """Create Parameter from simple value."""
        config = make_config()
        factory = ParameterFactory(config)
        
        spec = ParameterSpec(
            name='volume',
            yaml_path='volume',
            default=-6.0
        )
        yaml_data = {'volume': -12.0}
        
        param = factory.create_smart_parameter(spec, yaml_data)
        
        assert param.name == 'volume'
        assert param.value == -12.0
    
    def test_create_parameter_with_default(self):
        """Create Parameter using default value."""
        config = make_config()
        factory = ParameterFactory(config)
        
        spec = ParameterSpec(
            name='pan',
            yaml_path='pan',
            default=0.0
        )
        yaml_data = {}  # Empty
        
        param = factory.create_smart_parameter(spec, yaml_data)
        
        assert param.value == 0.0
    
    def test_create_parameter_with_range(self):
        """Create Parameter with range."""
        config = make_config()
        factory = ParameterFactory(config)
        
        spec = ParameterSpec(
            name='volume',
            yaml_path='volume',
            default=-6.0,
            range_path='volume_range'
        )
        yaml_data = {'volume': -12.0, 'volume_range': 3.0}
        
        params = factory.create_smart_parameter(spec, yaml_data)
        
        assert params.value == -12.0
        assert params._mod_range == 3.0
    
    def test_create_parameter_nested_path(self):
        """Create Parameter from nested YAML path."""
        config = make_config()
        factory = ParameterFactory(config)
        
        spec = ParameterSpec(
            name='grain_duration',
            yaml_path='grain.duration',
            default=0.05
        )
        yaml_data = {'grain': {'duration': 0.1}}
        
        param = factory.create_smart_parameter(spec, yaml_data)
        
        assert param.value == 0.1


# =============================================================================
# 3b. TEST CREATE_CONSTANT_PARAMETER
# =============================================================================

class TestCreateConstantParameter:
    """Test ParameterFactory.create_constant_parameter — usa la classe reale."""

    def test_restituisce_un_parameter(self):
        factory = ParameterFactory(make_config())
        result = factory.create_constant_parameter('loop_end', 4.0)
        assert isinstance(result, Parameter)

    def test_valore_corretto(self):
        factory = ParameterFactory(make_config())
        result = factory.create_constant_parameter('loop_end', 5.0)
        assert result.value == 5.0

    def test_get_value_restituisce_il_valore(self):
        factory = ParameterFactory(make_config())
        result = factory.create_constant_parameter('loop_end', 3.5)
        assert result.get_value(0.0) == pytest.approx(3.5)
        assert result.get_value(99.0) == pytest.approx(3.5)

    def test_nome_corretto(self):
        factory = ParameterFactory(make_config())
        result = factory.create_constant_parameter('loop_end', 1.0)
        assert result.name == 'loop_end'

    def test_funziona_con_qualsiasi_nome_parametro(self):
        factory = ParameterFactory(make_config())
        result = factory.create_constant_parameter('loop_dur', 2.0)
        assert result.value == 2.0
        assert result.name == 'loop_dur'


# =============================================================================
# 4. TEST CREATE_RAW_PARAMETER
# =============================================================================

class TestCreateRawParameter:
    """Test create_raw_parameter."""
    
    def test_create_raw_string(self):
        """Create raw string value."""
        config = make_config()
        factory = ParameterFactory(config)
        
        spec = ParameterSpec(
            name='envelope',
            yaml_path='envelope',
            default='hanning',
            is_smart=False
        )
        yaml_data = {'envelope': 'triangle'}
        
        result = factory.create_raw_parameter(spec, yaml_data)
        
        assert result == 'triangle'
    
    def test_create_raw_number(self):
        """Create raw number value."""
        config = make_config()
        factory = ParameterFactory(config)
        
        spec = ParameterSpec(
            name='count',
            yaml_path='count',
            default=1,
            is_smart=False
        )
        yaml_data = {'count': 5}
        
        result = factory.create_raw_parameter(spec, yaml_data)
        
        assert result == 5
    
    def test_create_raw_uses_default(self):
        """Create raw parameter uses default if missing."""
        config = make_config()
        factory = ParameterFactory(config)
        
        spec = ParameterSpec(
            name='mode',
            yaml_path='mode',
            default='auto',
            is_smart=False
        )
        yaml_data = {}
        
        result = factory.create_raw_parameter(spec, yaml_data)
        
        assert result == 'auto'


# =============================================================================
# 5. TEST PARAMETER ORCHESTRATOR
# =============================================================================

class TestParameterOrchestrator:
    """Test ParameterOrchestrator."""
    
    def test_create_orchestrator(self):
        """Create orchestrator with config."""
        config = make_config()
        orchestrator = ParameterOrchestrator(config)
        
        assert hasattr(orchestrator, '_param_factory')
        assert hasattr(orchestrator, '_config')
    
    def test_create_all_parameters_simple(self):
        """Create all parameters from simple schema."""
        config = make_config()
        orchestrator = ParameterOrchestrator(config)
        
        schema = [
            ParameterSpec('volume', 'volume', -6.0),
            ParameterSpec('pan', 'pan', 0.0)
        ]
        yaml_data = {'volume': -12.0, 'pan': 0.5}
        
        params = orchestrator.create_all_parameters(yaml_data, schema)
        
        assert 'volume' in params
        assert 'pan' in params
        assert params['volume'].value == -12.0
        assert params['pan'].value == 0.5
    
    def test_create_all_parameters_sets_none_for_missing(self):
        """Missing exclusive group members set to None."""
        config = make_config()
        orchestrator = ParameterOrchestrator(config)
        
        schema = [
            ParameterSpec('pitch_ratio', 'ratio', 1.0, 
                         exclusive_group='pitch', group_priority=2),
            ParameterSpec('pitch_semitones', 'semitones', None,
                         exclusive_group='pitch', group_priority=1)
        ]
        yaml_data = {'semitones': 7}  # Only semitones present
        
        params = orchestrator.create_all_parameters(yaml_data, schema)
        
        assert params['pitch_semitones'] is not None
        assert params['pitch_ratio'] is None  # Loser set to None

    def test_create_constant_parameter_restituisce_parameter(self):
        orchestrator = ParameterOrchestrator(make_config())
        result = orchestrator.create_constant_parameter('loop_end', 4.0)
        assert isinstance(result, Parameter)

    def test_create_constant_parameter_delega_alla_factory(self):
        orchestrator = ParameterOrchestrator(make_config())
        result = orchestrator.create_constant_parameter('loop_end', 4.0)
        assert result.value == 4.0
        assert result.get_value(0.0) == pytest.approx(4.0)
# =============================================================================
# 6. TEST CREATE_PARAMETER_WITH_GATE
# =============================================================================

class TestCreateParameterWithGate:
    """Test create_parameter_with_gate - gate injection."""
    
    def test_creates_parameter_with_gate(self):
        """Creates Parameter and injects gate."""
        config = make_config()
        orchestrator = ParameterOrchestrator(config)
        
        spec = ParameterSpec(
            name='volume',
            yaml_path='volume',
            default=-6.0,
            dephase_key='volume'
        )
        yaml_data = {'volume': -12.0}
        
        param = orchestrator.create_parameter_with_gate(yaml_data, spec)
        
        assert param._probability_gate is not None
        assert isinstance(param._probability_gate, ProbabilityGate)
    
    def test_gate_created_with_explicit_range(self):
        """Gate creation detects explicit range."""
        config = make_config()
        orchestrator = ParameterOrchestrator(config)
        
        spec = ParameterSpec(
            name='pitch_ratio',
            yaml_path='ratio',
            default=1.0,
            range_path='range',
            dephase_key='pitch'
        )
        yaml_data = {'ratio': 1.0, 'range': 0.1}
        
        param = orchestrator.create_parameter_with_gate(yaml_data, spec)
        
        assert param._mod_range == 0.1
        assert param._probability_gate is not None


# =============================================================================
# 7. TEST EXCLUSIVE GROUP SELECTOR
# =============================================================================

class TestExclusiveGroupSelector:
    """Test ExclusiveGroupSelector."""
    
    def test_select_from_exclusive_group_by_priority(self):
        """Select parameter by priority when both present."""
        schema = [
            ParameterSpec('option_a', 'a', 1, 
                         exclusive_group='test', group_priority=2),
            ParameterSpec('option_b', 'b', 2,
                         exclusive_group='test', group_priority=1)
        ]
        yaml_data = {'a': 10, 'b': 20}
        
        selected, members = ExclusiveGroupSelector.select_parameters(
            schema, yaml_data
        )
        
        # option_b has priority 1 (higher)
        assert 'option_b' in selected
        assert 'option_a' not in selected
    
    def test_select_present_over_missing(self):
        """Select present parameter over missing higher priority."""
        schema = [
            ParameterSpec('high_priority', 'high', None,
                         exclusive_group='test', group_priority=1),
            ParameterSpec('low_priority', 'low', 5,
                         exclusive_group='test', group_priority=2)
        ]
        yaml_data = {'low': 10}  # Only low present
        
        selected, members = ExclusiveGroupSelector.select_parameters(
            schema, yaml_data
        )
        
        # low_priority present, high_priority missing
        assert 'low_priority' in selected
    
    def test_select_default_if_none_present(self):
        """Select highest priority with default if none present."""
        schema = [
            ParameterSpec('option_a', 'a', 1,
                         exclusive_group='test', group_priority=1),
            ParameterSpec('option_b', 'b', 2,
                         exclusive_group='test', group_priority=2)
        ]
        yaml_data = {}  # Neither present
        
        selected, members = ExclusiveGroupSelector.select_parameters(
            schema, yaml_data
        )
        
        # option_a has priority 1 (highest)
        assert 'option_a' in selected
    
    def test_non_exclusive_always_included(self):
        """Non-exclusive parameters always included."""
        schema = [
            ParameterSpec('volume', 'volume', -6.0),  # Not exclusive
            ParameterSpec('option_a', 'a', 1,
                         exclusive_group='test', group_priority=1)
        ]
        yaml_data = {'volume': -12.0, 'a': 5}
        
        selected, members = ExclusiveGroupSelector.select_parameters(
            schema, yaml_data
        )
        
        assert 'volume' in selected
        assert 'option_a' in selected
    
    def test_multiple_exclusive_groups(self):
        """Handle multiple exclusive groups."""
        schema = [
            ParameterSpec('pitch_a', 'pitch.a', 1,
                         exclusive_group='pitch', group_priority=1),
            ParameterSpec('pitch_b', 'pitch.b', 2,
                         exclusive_group='pitch', group_priority=2),
            ParameterSpec('density_a', 'density.a', 10,
                         exclusive_group='density', group_priority=1),
            ParameterSpec('density_b', 'density.b', 20,
                         exclusive_group='density', group_priority=2)
        ]
        yaml_data = {
            'pitch': {'a': 5},
            'density': {'b': 15}
        }
        
        selected, members = ExclusiveGroupSelector.select_parameters(
            schema, yaml_data
        )
        
        assert 'pitch_a' in selected
        assert 'density_b' in selected


# =============================================================================
# 8. TEST INTEGRATION COMPLETE
# =============================================================================

class TestFactoryOrchestratorIntegration:
    """Test complete integration."""
    
    def test_complete_workflow_simple(self):
        """Complete workflow: YAML → Parameters."""
        config = make_config()
        orchestrator = ParameterOrchestrator(config)
        
        schema = [
            ParameterSpec('volume', 'volume', -6.0, 
                         range_path='volume_range', dephase_key='volume'),
            ParameterSpec('pan', 'pan', 0.0,
                         dephase_key='pan')
        ]
        yaml_data = {
            'volume': -12.0,
            'volume_range': 3.0,
            'pan': 0.5
        }
        
        params = orchestrator.create_all_parameters(yaml_data, schema)
        
        assert params['volume'].value == -12.0
        assert params['volume']._mod_range == 3.0
        assert params['pan'].value == 0.5
        assert params['volume']._probability_gate is not None
    
    def test_complete_workflow_exclusive_groups(self):
        """Complete workflow with exclusive groups."""
        config = make_config()
        orchestrator = ParameterOrchestrator(config)
        
        schema = [
            ParameterSpec('density', 'density', None,
                         exclusive_group='density_mode', group_priority=2),
            ParameterSpec('fill_factor', 'fill_factor', 2,
                         exclusive_group='density_mode', group_priority=1)
        ]
        yaml_data = {'fill_factor': 3}
        
        params = orchestrator.create_all_parameters(yaml_data, schema)
        
        assert params['fill_factor'] is not None
        assert params['fill_factor'].value == 3
        assert params['density'] is None  # Loser
    
    def test_mixed_smart_and_raw_parameters(self):
        """Mix of smart and raw parameters."""
        config = make_config()
        orchestrator = ParameterOrchestrator(config)
        
        schema = [
            ParameterSpec('volume', 'volume', -6.0, is_smart=True),
            ParameterSpec('envelope', 'envelope', 'hanning', is_smart=False)
        ]
        yaml_data = {'volume': -12.0, 'envelope': 'triangle'}
        
        params = orchestrator.create_all_parameters(yaml_data, schema)
        
        assert isinstance(params['volume'], Parameter)
        assert params['envelope'] == 'triangle'  # Raw value


# =============================================================================
# 9. TEST ERROR HANDLING
# =============================================================================

class TestFactoryOrchestratorErrors:
    """Test error handling."""
    
    def test_nested_path_on_primitive_value(self):
        """Nested path on primitive returns default."""
        config = make_config()
        factory = ParameterFactory(config)
        
        spec = ParameterSpec(
            name='volume',
            yaml_path='grain.duration',
            default=-6.0
        )
        yaml_data = {'grain': 42}
        
        param = factory.create_smart_parameter(spec, yaml_data)
        
        # Should use default
        assert param.value == -6.0

# =============================================================================
# 10. TEST EDGE CASES
# =============================================================================

class TestFactoryOrchestratorEdgeCases:
    """Test edge cases."""
    
    def test_empty_yaml_uses_all_defaults(self):
        """Empty YAML uses all defaults."""
        config = make_config()
        orchestrator = ParameterOrchestrator(config)
        
        schema = [
            ParameterSpec('volume', 'volume', -6.0),
            ParameterSpec('pan', 'pan', 0.0)
        ]
        yaml_data = {}
        
        params = orchestrator.create_all_parameters(yaml_data, schema)
        
        assert params['volume'].value == -6.0
        assert params['pan'].value == 0.0
    
    def test_empty_schema_returns_empty_dict(self):
        """Empty schema returns empty dict."""
        config = make_config()
        orchestrator = ParameterOrchestrator(config)
        
        schema = []
        yaml_data = {'volume': -12.0}
        
        params = orchestrator.create_all_parameters(yaml_data, schema)
        
        assert params == {}
    
    def test_deeply_nested_path(self):
        """Very deep nested path works."""
        data = {'a': {'b': {'c': {'d': 42}}}}
        
        result = ParameterFactory._get_nested(data, 'a.b.c.d', 0)
        
        assert result == 42
    
    def test_exclusive_group_single_member(self):
        """Exclusive group with single member."""
        schema = [
            ParameterSpec('only_one', 'value', 10,
                         exclusive_group='solo')
        ]
        yaml_data = {'value': 20}
        
        selected, members = ExclusiveGroupSelector.select_parameters(
            schema, yaml_data
        )
        
        assert 'only_one' in selected


# =============================================================================
# 11. TEST PARAMETRIZED
# =============================================================================

class TestFactoryOrchestratorParametrized:
    """Test parametrized for systematic coverage."""
    
    @pytest.mark.parametrize("path,expected", [
        ('a', 1),
        ('b.c', 2),
        ('d.e.f', 3),
        ('missing', 0)
    ])
    def test_get_nested_various_paths(self, path, expected):
        """Test _get_nested with various paths."""
        data = {
            'a': 1,
            'b': {'c': 2},
            'd': {'e': {'f': 3}}
        }
        
        result = ParameterFactory._get_nested(data, path, 0)
        
        assert result == expected
    
    @pytest.mark.parametrize("is_smart", [True, False])
    def test_create_both_parameter_types(self, is_smart):
        """Test creating both smart and raw parameters."""
        config = make_config()
        orchestrator = ParameterOrchestrator(config)

        schema = [
            ParameterSpec('volume', 'value', -6.0, is_smart=is_smart)
        ]
        yaml_data = {'value': -12.0}

        params = orchestrator.create_all_parameters(yaml_data, schema)

        if is_smart:
            assert isinstance(params['volume'], Parameter)
        else:
            assert params['volume'] == -12.0


def make_config_with_sample_dur(sample_dur_sec: float) -> StreamConfig:
    """Crea StreamConfig con sample_dur_sec specifico per test loop bounds."""
    context = StreamContext(
        stream_id='test_stream',
        onset=0.0,
        duration=10.0,
        sample='test.wav',
        sample_dur_sec=sample_dur_sec,
    )
    return StreamConfig(context=context)


# =============================================================================
# TEST INTEGRAZIONE — PARSER LOOP BOUNDS DINAMICI
# =============================================================================

class TestParserDynamicLoopBounds:
    """
    GranularParser deve validare loop_end, loop_start, loop_dur
    usando sample_dur_sec come max_val effettivo.
    """

    def test_parser_stores_sample_dur_sec(self):
        """GranularParser memorizza sample_dur_sec dal config."""
        config = make_config_with_sample_dur(8.0)
        parser = GranularParser(config)
        assert parser.sample_dur_sec == 8.0

    def test_loop_end_within_sample_dur_is_valid(self):
        """loop_end <= sample_dur_sec deve essere accettato."""
        config = make_config_with_sample_dur(10.0)
        parser = GranularParser(config)
        param = parser.parse_parameter('loop_end', 8.0)
        assert param.get_value(0) == pytest.approx(8.0)

    def test_loop_end_exceeds_sample_dur_raises(self):
        """loop_end > sample_dur_sec deve sollevare ValueError in strict mode."""
        config = make_config_with_sample_dur(10.0)
        parser = GranularParser(config)
        with pytest.raises(ValueError):
            parser.parse_parameter('loop_end', 15.0)

    def test_loop_start_within_sample_dur_is_valid(self):
        """loop_start <= sample_dur_sec deve essere accettato."""
        config = make_config_with_sample_dur(10.0)
        parser = GranularParser(config)
        param = parser.parse_parameter('loop_start', 3.0)
        assert param.get_value(0) == pytest.approx(3.0)

    def test_loop_start_exceeds_sample_dur_raises(self):
        """loop_start > sample_dur_sec deve sollevare ValueError."""
        config = make_config_with_sample_dur(10.0)
        parser = GranularParser(config)
        with pytest.raises(ValueError):
            parser.parse_parameter('loop_start', 12.0)

    def test_loop_dur_within_sample_dur_is_valid(self):
        """loop_dur <= sample_dur_sec deve essere accettato."""
        config = make_config_with_sample_dur(10.0)
        parser = GranularParser(config)
        param = parser.parse_parameter('loop_dur', 5.0)
        assert param.get_value(0) == pytest.approx(5.0)

    def test_loop_dur_exceeds_sample_dur_raises(self):
        """loop_dur > sample_dur_sec deve sollevare ValueError."""
        config = make_config_with_sample_dur(10.0)
        parser = GranularParser(config)
        with pytest.raises(ValueError):
            parser.parse_parameter('loop_dur', 20.0)

    def test_loop_bound_uses_actual_sample_duration(self):
        """Il bound effettivo dipende da sample_dur_sec, non da una costante fissa."""
        # Con sample di 200 secondi, loop_end=150 deve essere valido
        config = make_config_with_sample_dur(200.0)
        parser = GranularParser(config)
        param = parser.parse_parameter('loop_end', 150.0)
        assert param.get_value(0) == pytest.approx(150.0)

    @pytest.mark.parametrize("name", ['loop_end', 'loop_start', 'loop_dur'])
    def test_loop_param_without_sample_dur_accepts_large_value(self, name):
        """Senza sample_dur_sec (max_val=None), qualsiasi valore >= min è valido."""
        config = make_config_with_sample_dur(None)
        parser = GranularParser(config)
        param = parser.parse_parameter(name, 9999.0)
        assert param.get_value(0) == pytest.approx(9999.0)