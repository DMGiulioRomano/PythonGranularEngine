"""
test_parameter_orchestrator.py

Test suite completa per parameter_orchestrator.py.

Fino all'issue #183 questo file era test_parameter_factory.py e copriva anche
ParameterFactory, che si e' rivelata un inoltro verso GranularParser: e'
sparita, l'orchestratore parla direttamente col parser, e la navigazione del
path YAML vive in parameter_schema.resolve_yaml_path (testata li').

Coverage:
1. Test ParameterOrchestrator - costruzione
2. Test create_parameter_with_gate - estrazione dallo spec + gate injection
3. Test create_constant_parameter
4. Test parametri raw (is_smart=False)
5. Test create_all_parameters - orchestrazione completa
6. Test ExclusiveGroupSelector - gruppi mutuamente esclusivi
7. Test integrazione schema completi
8. Test error handling
9. Test edge cases
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from typing import Dict, List, Any, Optional
from dataclasses import dataclass
# Import reali per test su create_constant_parameter
from pge.shared.probability_gate import ProbabilityGate
from pge.core.stream_config import StreamConfig, StreamContext
from pge.parameters.parameter import Parameter
from pge.parameters.parameter_schema import ParameterSpec
from pge.parameters.exclusive_selector import ExclusiveGroupSelector
from pge.parameters.parser import GranularParser
from pge.parameters.parameter_orchestrator import ParameterOrchestrator
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
# 1. TEST PARAMETER ORCHESTRATOR - COSTRUZIONE
# =============================================================================

class TestParameterOrchestratorInitialization:
    """L'orchestratore tiene il parser, senza intermediari (issue #183)."""

    def test_holds_the_parser_directly(self):
        config = make_config()
        orchestrator = ParameterOrchestrator(config)

        assert isinstance(orchestrator._parser, GranularParser)
        assert orchestrator._parser.stream_id == "test_stream"

    def test_keeps_the_config(self):
        config = make_config()
        orchestrator = ParameterOrchestrator(config)

        assert orchestrator._config is config

    def test_no_factory_in_the_middle(self):
        """La catena e' Orchestrator -> Parser: niente factory interposta."""
        orchestrator = ParameterOrchestrator(make_config())

        assert not hasattr(orchestrator, '_param_factory')

    def test_config_is_required(self):
        """Senza config non si costruisce, e lo si scopre subito.

        Il default None che c'era prima era morto: il primo uso e'
        GranularParser(config), che dereferenzia config.context e sollevava
        AttributeError un attimo dopo. Meglio un TypeError sulla firma, che
        dice quale argomento manca.
        """
        with pytest.raises(TypeError):
            ParameterOrchestrator()


# =============================================================================
# 2. TEST ESTRAZIONE DALLO SPEC (create_parameter_with_gate)
# =============================================================================

class TestParameterFromSpec:
    """Dallo ParameterSpec al Parameter: estrazione dal YAML + parsing."""

    def test_create_parameter_from_simple_value(self):
        """Create Parameter from simple value."""
        orchestrator = ParameterOrchestrator(make_config())

        spec = ParameterSpec(
            name='volume',
            yaml_path='volume',
            default=-6.0
        )
        yaml_data = {'volume': -12.0}

        param = orchestrator.create_parameter_with_gate(yaml_data, spec)

        assert param.name == 'volume'
        assert param.value == -12.0

    def test_create_parameter_with_default(self):
        """Create Parameter using default value."""
        orchestrator = ParameterOrchestrator(make_config())

        spec = ParameterSpec(
            name='pan',
            yaml_path='pan',
            default=0.0
        )
        yaml_data = {}  # Empty

        param = orchestrator.create_parameter_with_gate(yaml_data, spec)

        assert param.value == 0.0

    def test_create_parameter_with_range(self):
        """Create Parameter with range."""
        orchestrator = ParameterOrchestrator(make_config())

        spec = ParameterSpec(
            name='volume',
            yaml_path='volume',
            default=-6.0,
            range_path='volume_range'
        )
        yaml_data = {'volume': -12.0, 'volume_range': 3.0}

        param = orchestrator.create_parameter_with_gate(yaml_data, spec)

        assert param.value == -12.0
        assert param._mod_range == 3.0

    def test_create_parameter_nested_path(self):
        """Create Parameter from nested YAML path."""
        orchestrator = ParameterOrchestrator(make_config())

        spec = ParameterSpec(
            name='grain_duration',
            yaml_path='grain.duration',
            default=0.05
        )
        yaml_data = {'grain': {'duration': 0.1}}

        param = orchestrator.create_parameter_with_gate(yaml_data, spec)

        assert param.value == 0.1


# =============================================================================
# 3. TEST CREATE_CONSTANT_PARAMETER
# =============================================================================

class TestCreateConstantParameter:
    """Parameter costante da uno scalare, senza YAML."""

    def test_restituisce_un_parameter(self):
        orchestrator = ParameterOrchestrator(make_config())
        result = orchestrator.create_constant_parameter('loop_end', 4.0)
        assert isinstance(result, Parameter)

    def test_valore_corretto(self):
        orchestrator = ParameterOrchestrator(make_config())
        result = orchestrator.create_constant_parameter('loop_end', 5.0)
        assert result.value == 5.0

    def test_get_value_restituisce_il_valore(self):
        orchestrator = ParameterOrchestrator(make_config())
        result = orchestrator.create_constant_parameter('loop_end', 3.5)
        assert result.get_value(0.0) == pytest.approx(3.5)
        assert result.get_value(99.0) == pytest.approx(3.5)

    def test_nome_corretto(self):
        orchestrator = ParameterOrchestrator(make_config())
        result = orchestrator.create_constant_parameter('loop_end', 1.0)
        assert result.name == 'loop_end'

    def test_funziona_con_qualsiasi_nome_parametro(self):
        orchestrator = ParameterOrchestrator(make_config())
        result = orchestrator.create_constant_parameter('loop_dur', 2.0)
        assert result.value == 2.0
        assert result.name == 'loop_dur'


# =============================================================================
# 4. TEST PARAMETRI RAW (is_smart=False)
# =============================================================================

class TestRawParameters:
    """Gli spec non-smart escono come valore grezzo, non come Parameter."""

    def _raw(self, spec, yaml_data):
        orchestrator = ParameterOrchestrator(make_config())
        return orchestrator.create_all_parameters(yaml_data, [spec])[spec.name]

    def test_create_raw_string(self):
        """Create raw string value."""
        spec = ParameterSpec(
            name='envelope',
            yaml_path='envelope',
            default='hanning',
            is_smart=False
        )

        assert self._raw(spec, {'envelope': 'triangle'}) == 'triangle'

    def test_create_raw_number(self):
        """Create raw number value."""
        spec = ParameterSpec(
            name='count',
            yaml_path='count',
            default=1,
            is_smart=False
        )

        assert self._raw(spec, {'count': 5}) == 5

    def test_create_raw_uses_default(self):
        """Create raw parameter uses default if missing."""
        spec = ParameterSpec(
            name='mode',
            yaml_path='mode',
            default='auto',
            is_smart=False
        )

        assert self._raw(spec, {}) == 'auto'


# =============================================================================
# 5. TEST PARAMETER ORCHESTRATOR
# =============================================================================

class TestParameterOrchestrator:
    """Test ParameterOrchestrator."""

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
            ParameterSpec('volume', 'volume', -6.0,
                         exclusive_group='outgrp', group_priority=2),
            ParameterSpec('pan', 'pan', None,
                         exclusive_group='outgrp', group_priority=1)
        ]
        yaml_data = {'pan': 0.5}  # Only pan present

        params = orchestrator.create_all_parameters(yaml_data, schema)

        assert params['pan'] is not None
        assert params['volume'] is None  # Loser set to None


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
            deviation_probability_key='volume'
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
            name='grain_duration',
            yaml_path='grain.duration',
            default=0.05,
            range_path='grain.duration_range',
            deviation_probability_key='duration'
        )
        yaml_data = {'grain': {'duration': 0.05, 'duration_range': 0.1}}

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

class TestOrchestratorIntegration:
    """Test complete integration."""
    
    def test_complete_workflow_simple(self):
        """Complete workflow: YAML → Parameters."""
        config = make_config()
        orchestrator = ParameterOrchestrator(config)
        
        schema = [
            ParameterSpec('volume', 'volume', -6.0, 
                         range_path='volume_range', deviation_probability_key='volume'),
            ParameterSpec('pan', 'pan', 0.0,
                         deviation_probability_key='pan')
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

class TestOrchestratorErrors:
    """Test error handling."""

    def test_nested_path_on_primitive_value(self):
        """Nested path on primitive returns default."""
        orchestrator = ParameterOrchestrator(make_config())

        spec = ParameterSpec(
            name='volume',
            yaml_path='grain.duration',
            default=-6.0
        )
        yaml_data = {'grain': 42}

        param = orchestrator.create_parameter_with_gate(yaml_data, spec)

        # Should use default
        assert param.value == -6.0

# =============================================================================
# 10. TEST EDGE CASES
# =============================================================================

class TestOrchestratorEdgeCases:
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

class TestOrchestratorParametrized:
    """Test parametrized for systematic coverage."""

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

# =============================================================================
# 10. BOUND MINIMO DINAMICO GRAIN_DURATION VIA PARSER (1 CAMPIONE)
# =============================================================================

class TestParserDynamicGrainDurationMin:
    """
    GranularParser deve propagare output_sr dal context ai bounds di
    grain_duration: durata minima = 1 campione (1/output_sr), non piu' 1 ms.
    """

    def test_one_sample_duration_is_valid(self):
        config = make_config()  # context con output_sr di default (48000)
        parser = GranularParser(config)
        param = parser.parse_parameter('grain_duration', 1.0 / 48000)
        assert param.get_value(0) == pytest.approx(1.0 / 48000)

    def test_sub_millisecond_duration_now_valid(self):
        """Durate sotto il vecchio floor di 1 ms sono accettate."""
        config = make_config()
        parser = GranularParser(config)
        param = parser.parse_parameter('grain_duration', 0.0001)
        assert param.get_value(0) == pytest.approx(0.0001)

    def test_below_one_sample_raises(self):
        config = make_config()
        parser = GranularParser(config)
        with pytest.raises(ValueError):
            parser.parse_parameter('grain_duration', 0.5 / 48000)

    def test_envelope_breakpoint_below_one_sample_raises(self):
        config = make_config()
        parser = GranularParser(config)
        with pytest.raises(ValueError):
            parser.parse_parameter(
                'grain_duration', [[0.0, 0.05], [5.0, 0.5 / 48000]]
            )
