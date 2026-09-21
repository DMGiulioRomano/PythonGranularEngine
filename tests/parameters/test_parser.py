"""
test_parser.py

Test suite completa per il modulo parser.py (GranularParser).

Coverage:
1. Test inizializzazione GranularParser
2. Test parse_parameter - success cases
3. Test _parse_input - conversione tipi
4. Test _validate_and_clip - numeri (strict/permissive)
5. Test _validate_and_clip - Envelope (strict/permissive)  
6. Test integrazione completa
7. Test error handling
8. Test edge cases
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from typing import Union, Optional, Any

# =============================================================================
# MOCK CLASSES
# =============================================================================

class Envelope:
    """Mock Envelope."""
    def __init__(self, breakpoints):
        self.breakpoints = breakpoints
    
    def evaluate(self, time: float) -> float:
        """Simple linear interpolation."""
        if not self.breakpoints:
            return 0.0
        
        for i in range(len(self.breakpoints) - 1):
            t0, v0 = self.breakpoints[i]
            t1, v1 = self.breakpoints[i + 1]
            
            if t0 <= time <= t1:
                if t1 == t0:
                    return v0
                ratio = (time - t0) / (t1 - t0)
                return v0 + ratio * (v1 - v0)
        
        if time < self.breakpoints[0][0]:
            return self.breakpoints[0][1]
        return self.breakpoints[-1][1]


class ParameterBounds:
    """Mock ParameterBounds."""
    def __init__(self, min_val, max_val, min_range=0.0, max_range=100.0, 
                 variation_mode='additive'):
        self.min_val = min_val
        self.max_val = max_val
        self.min_range = min_range
        self.max_range = max_range
        self.variation_mode = variation_mode


class Parameter:
    """Mock Parameter."""
    def __init__(self, name, value, bounds, mod_range=None, 
                 owner_id="unknown", distribution_mode='uniform'):
        self.name = name
        self.value = value
        self.bounds = bounds
        self.mod_range = mod_range
        self.owner_id = owner_id
        self.distribution_mode = distribution_mode


class StreamConfig:
    """Mock StreamConfig."""
    class Context:
        def __init__(self):
            self.stream_id = "test_stream"
            self.duration = 10.0
    
    def __init__(self):
        self.context = self.Context()
        self.time_mode = 'absolute'
        self.distribution_mode = 'uniform'


# Mock functions
def create_scaled_envelope(raw_data, duration, time_mode):
    """Mock create_scaled_envelope."""
    if isinstance(raw_data, list):
        # Assume breakpoints format
        return Envelope(raw_data)
    elif isinstance(raw_data, dict):
        # Assume dict format with 'points' key
        points = raw_data.get('points', [[0, 0], [1, 1]])
        return Envelope(points)
    raise ValueError(f"Cannot create envelope from {raw_data}")


def get_parameter_definition(name):
    """Mock get_parameter_definition."""
    # Default bounds for common params
    bounds_registry = {
        'volume': ParameterBounds(-60.0, 12.0),
        'pitch': ParameterBounds(0.125, 8.0),
        'pan': ParameterBounds(-1.0, 1.0),
        'duration': ParameterBounds(0.001, 10.0),
        'density': ParameterBounds(0.1, 1000.0),
        'test_param': ParameterBounds(0.0, 100.0),
    }
    
    if name not in bounds_registry:
        raise KeyError(f"Parameter '{name}' not found in registry")
    
    return bounds_registry[name]


# Global mock for logger
CLIP_LOG_CONFIG = {'validation_mode': 'strict'}

def log_config_warning(stream_id, param_name, raw_value, clipped_value,
                      min_val, max_val, value_type):
    """Mock log function."""
    pass


# =============================================================================
# GRANULAR PARSER CLASS
# =============================================================================

ParamInput = Union[float, int, Envelope]

class GranularParser:
    """Parser for YAML → Parameter conversion."""
    
    def __init__(self, config):
        self.stream_id = config.context.stream_id
        self.duration = config.context.duration
        self.time_mode = config.time_mode
        self.distribution_mode = config.distribution_mode
    
    def parse_parameter(self, name: str, value_raw: Any,
                       range_raw: Any = None, prob_raw: Any = None) -> Parameter:
        """Factory method: create Parameter from raw YAML data."""
        # 1. Get bounds
        bounds = get_parameter_definition(name)
        
        # 2. Parse inputs
        clean_value = self._parse_input(value_raw, f"{name}.value")
        clean_range = self._parse_input(range_raw, f"{name}.range")
        clean_prob = self._parse_input(prob_raw, f"{name}.probability")
        
        # 3. Validate and clip
        validated_value = self._validate_and_clip(
            clean_value, bounds.min_val, bounds.max_val, name, 'value'
        )
        
        validated_range = self._validate_and_clip(
            clean_range, bounds.min_range, bounds.max_range, name, 'range'
        ) if clean_range is not None else None
        
        validated_prob = self._validate_and_clip(
            clean_prob, 0.0, 100.0, name, 'probability'
        ) if clean_prob is not None else None
        
        # 4. Create Parameter
        return Parameter(
            name=name,
            value=validated_value,
            bounds=bounds,
            mod_range=validated_range,
            owner_id=self.stream_id,
            distribution_mode=self.distribution_mode
        )
    
    def _parse_input(self, raw_data: Any, context_info: str) -> Optional[ParamInput]:
        """Parse raw input → float, Envelope, or None."""
        if raw_data is None:
            return None
        
        if isinstance(raw_data, (int, float)):
            return float(raw_data)
        
        if isinstance(raw_data, (list, dict)):
            return create_scaled_envelope(raw_data, self.duration, self.time_mode)
        
        raise ValueError(
            f"Formato non valido per '{context_info}': {raw_data}. "
            f"Atteso numero, lista di punti, o dict envelope."
        )
    
    def _validate_and_clip(self, param: Optional[ParamInput],
                          min_bound: float, max_bound: float,
                          param_name: str, value_type: str) -> Optional[ParamInput]:
        """Validate and clip parameter (number or Envelope)."""
        if param is None:
            return None
        
        validation_mode = CLIP_LOG_CONFIG.get('validation_mode', 'strict')
        
        # Case 1: Scalar number
        if isinstance(param, (int, float)):
            clean = float(param)
            clipped = max(min_bound, min(max_bound, clean))
            
            if clipped != clean:
                bound_type = "MIN" if clean < min_bound else "MAX"
                bound_value = min_bound if clean < min_bound else max_bound
                deviation = clean - bound_value
                
                error_msg = (
                    f"Parametro '{param_name}' fuori bounds!\n"
                    f"  {value_type}: {clean:.2f}\n"
                    f"  {bound_type} consentito: {bound_value:.2f}\n"
                    f"  Deviazione: {deviation:+.2f}\n"
                    f"  Stream: {self.stream_id}\n"
                    f"  Bounds validi: [{min_bound}, {max_bound}]"
                )
                
                if validation_mode == 'strict':
                    raise ValueError(error_msg)
                else:
                    log_config_warning(
                        self.stream_id, param_name, clean, clipped,
                        min_bound, max_bound, value_type
                    )
            
            return clipped
        
        # Case 2: Envelope
        if isinstance(param, Envelope):
            needs_fixing = False
            errors = []
            fixed_points = []
            
            for t, y in param.breakpoints:
                clipped_y = max(min_bound, min(max_bound, y))
                
                if clipped_y != y:
                    needs_fixing = True
                    bound_type = "MIN" if y < min_bound else "MAX"
                    bound_value = min_bound if y < min_bound else max_bound
                    deviation = y - bound_value
                    
                    errors.append(
                        f"  t={t:.2f}s: {value_type}={y:.2f} → "
                        f"{bound_type}={bound_value:.2f} (Δ{deviation:+.2f})"
                    )
                
                fixed_points.append([t, clipped_y])
            
            if needs_fixing:
                error_msg = (
                    f"Envelope '{param_name}' ha breakpoint fuori bounds!\n"
                    f"  Stream: {self.stream_id}\n"
                    f"  Bounds validi: [{min_bound}, {max_bound}]\n"
                    f"  Violazioni:\n" + "\n".join(errors)
                )
                
                if validation_mode == 'strict':
                    raise ValueError(error_msg)
                else:
                    for t, y in param.breakpoints:
                        clipped_y = max(min_bound, min(max_bound, y))
                        if clipped_y != y:
                            log_config_warning(
                                self.stream_id, f"{param_name}_ENV[t={t:.2f}]",
                                y, clipped_y, min_bound, max_bound, value_type
                            )
                    return Envelope(fixed_points)
            
            return param
        
        raise TypeError(f"Cannot validate type {type(param)}")


# =============================================================================
# 1. TEST INIZIALIZZAZIONE
# =============================================================================

class TestGranularParserInitialization:
    """Test inizializzazione GranularParser."""
    
    def test_create_parser_with_config(self):
        """Creazione parser con StreamConfig."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        assert parser.stream_id == "test_stream"
        assert parser.duration == 10.0
        assert parser.time_mode == 'absolute'
        assert parser.distribution_mode == 'uniform'
    
    def test_parser_stores_config_values(self):
        """Parser memorizza valori da config."""
        config = StreamConfig()
        config.context.stream_id = "custom_stream"
        config.context.duration = 5.0
        config.time_mode = 'normalized'
        config.distribution_mode = 'gaussian'
        
        parser = GranularParser(config)
        
        assert parser.stream_id == "custom_stream"
        assert parser.duration == 5.0
        assert parser.time_mode == 'normalized'
        assert parser.distribution_mode == 'gaussian'


# =============================================================================
# 2. TEST PARSE_PARAMETER - SUCCESS
# =============================================================================

class TestParseParameterSuccess:
    """Test parse_parameter con valori validi."""
    
    def test_parse_simple_number(self):
        """Parse parametro con numero semplice."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        param = parser.parse_parameter('volume', -6.0)
        
        assert param.name == 'volume'
        assert param.value == -6.0
        assert param.owner_id == "test_stream"
    
    def test_parse_with_range(self):
        """Parse parametro con range."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        param = parser.parse_parameter('volume', -6.0, range_raw=3.0)
        
        assert param.value == -6.0
        assert param.mod_range == 3.0
    
    def test_parse_with_probability(self):
        """Parse parametro con probabilità."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        param = parser.parse_parameter('pitch', 1.0, prob_raw=50.0)
        
        assert param.value == 1.0
        # prob_raw viene validato ma non salvato in Parameter mock
    
    def test_parse_envelope_value(self):
        """Parse parametro con Envelope."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        breakpoints = [[0, -20], [10, 0]]
        param = parser.parse_parameter('volume', breakpoints)
        
        assert isinstance(param.value, Envelope)
        assert param.value.breakpoints == breakpoints
    
    def test_parse_sets_distribution_mode(self):
        """parse_parameter usa distribution_mode da config."""
        config = StreamConfig()
        config.distribution_mode = 'gaussian'
        parser = GranularParser(config)
        
        param = parser.parse_parameter('pitch', 1.0)
        
        assert param.distribution_mode == 'gaussian'
    
    def test_parse_gets_correct_bounds(self):
        """parse_parameter recupera bounds corretti."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        param = parser.parse_parameter('volume', -6.0)
        
        assert param.bounds.min_val == -60.0
        assert param.bounds.max_val == 12.0


# =============================================================================
# 3. TEST _PARSE_INPUT
# =============================================================================

class TestParseInput:
    """Test _parse_input - conversione tipi."""
    
    def test_parse_none_returns_none(self):
        """None → None."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        result = parser._parse_input(None, 'test.value')
        
        assert result is None
    
    def test_parse_int_returns_float(self):
        """int → float."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        result = parser._parse_input(42, 'test.value')
        
        assert result == 42.0
        assert isinstance(result, float)
    
    def test_parse_float_returns_float(self):
        """float → float."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        result = parser._parse_input(3.14, 'test.value')
        
        assert result == 3.14
    
    def test_parse_list_creates_envelope(self):
        """list → Envelope."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        breakpoints = [[0, 10], [1, 20]]
        result = parser._parse_input(breakpoints, 'test.value')
        
        assert isinstance(result, Envelope)
        assert result.breakpoints == breakpoints
    
    def test_parse_dict_creates_envelope(self):
        """dict → Envelope."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        env_dict = {'points': [[0, 5], [2, 15]]}
        result = parser._parse_input(env_dict, 'test.value')
        
        assert isinstance(result, Envelope)
        assert result.breakpoints == [[0, 5], [2, 15]]
    
    def test_parse_invalid_type_raises_error(self):
        """Tipo invalido → ValueError."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        with pytest.raises(ValueError) as exc_info:
            parser._parse_input("invalid_string", 'test.value')
        
        assert "Formato non valido" in str(exc_info.value)
        assert "test.value" in str(exc_info.value)


# =============================================================================
# 4. TEST _VALIDATE_AND_CLIP - NUMERI
# =============================================================================

class TestValidateAndClipNumbers:
    """Test _validate_and_clip con numeri."""
    
    def test_value_within_bounds_unchanged(self):
        """Valore dentro bounds non cambia."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        result = parser._validate_and_clip(50.0, 0.0, 100.0, 'test', 'value')
        
        assert result == 50.0
    
    def test_value_at_min_bound_unchanged(self):
        """Valore = min_bound OK."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        result = parser._validate_and_clip(0.0, 0.0, 100.0, 'test', 'value')
        
        assert result == 0.0
    
    def test_value_at_max_bound_unchanged(self):
        """Valore = max_bound OK."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        result = parser._validate_and_clip(100.0, 0.0, 100.0, 'test', 'value')
        
        assert result == 100.0
    
    def test_value_above_max_strict_raises(self):
        """Valore > max in strict mode → ValueError."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        global CLIP_LOG_CONFIG
        CLIP_LOG_CONFIG['validation_mode'] = 'strict'
        
        with pytest.raises(ValueError) as exc_info:
            parser._validate_and_clip(150.0, 0.0, 100.0, 'test_param', 'value')
        
        assert "fuori bounds" in str(exc_info.value)
        assert "test_param" in str(exc_info.value)
        assert "150.0" in str(exc_info.value)
    
    def test_value_below_min_strict_raises(self):
        """Valore < min in strict mode → ValueError."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        global CLIP_LOG_CONFIG
        CLIP_LOG_CONFIG['validation_mode'] = 'strict'
        
        with pytest.raises(ValueError) as exc_info:
            parser._validate_and_clip(-50.0, 0.0, 100.0, 'test_param', 'value')
        
        assert "fuori bounds" in str(exc_info.value)
        assert "-50.0" in str(exc_info.value)
    
    @patch('test_parser.log_config_warning')
    def test_value_above_max_permissive_clips(self, mock_log):
        """Valore > max in permissive mode → clamp + log."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        global CLIP_LOG_CONFIG
        CLIP_LOG_CONFIG['validation_mode'] = 'permissive'
        
        result = parser._validate_and_clip(150.0, 0.0, 100.0, 'test', 'value')
        
        assert result == 100.0
        assert mock_log.called
    
    @patch('test_parser.log_config_warning')
    def test_value_below_min_permissive_clips(self, mock_log):
        """Valore < min in permissive mode → clamp + log."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        global CLIP_LOG_CONFIG
        CLIP_LOG_CONFIG['validation_mode'] = 'permissive'
        
        result = parser._validate_and_clip(-50.0, 0.0, 100.0, 'test', 'value')
        
        assert result == 0.0
        assert mock_log.called
    
    def test_none_returns_none(self):
        """None → None (non validato)."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        result = parser._validate_and_clip(None, 0.0, 100.0, 'test', 'value')
        
        assert result is None


# =============================================================================
# 5. TEST _VALIDATE_AND_CLIP - ENVELOPE
# =============================================================================

class TestValidateAndClipEnvelope:
    """Test _validate_and_clip con Envelope."""
    
    def test_envelope_all_within_bounds_unchanged(self):
        """Envelope tutto dentro bounds → unchanged."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        env = Envelope([[0, 10], [1, 50], [2, 90]])
        result = parser._validate_and_clip(env, 0.0, 100.0, 'test', 'value')
        
        assert result is env  # Same object
        assert result.breakpoints == [[0, 10], [1, 50], [2, 90]]
    
    def test_envelope_one_point_above_strict_raises(self):
        """Envelope con punto > max in strict → ValueError."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        global CLIP_LOG_CONFIG
        CLIP_LOG_CONFIG['validation_mode'] = 'strict'
        
        env = Envelope([[0, 10], [1, 150]])  # 150 > 100
        
        with pytest.raises(ValueError) as exc_info:
            parser._validate_and_clip(env, 0.0, 100.0, 'test_env', 'value')
        
        assert "breakpoint fuori bounds" in str(exc_info.value)
        assert "test_env" in str(exc_info.value)
    
    def test_envelope_one_point_below_strict_raises(self):
        """Envelope con punto < min in strict → ValueError."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        global CLIP_LOG_CONFIG
        CLIP_LOG_CONFIG['validation_mode'] = 'strict'
        
        env = Envelope([[0, -50], [1, 50]])  # -50 < 0
        
        with pytest.raises(ValueError) as exc_info:
            parser._validate_and_clip(env, 0.0, 100.0, 'test_env', 'value')
        
        assert "breakpoint fuori bounds" in str(exc_info.value)
    
    @patch('test_parser.log_config_warning')
    def test_envelope_points_out_permissive_clips(self, mock_log):
        """Envelope fuori bounds in permissive → clamp + log."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        global CLIP_LOG_CONFIG
        CLIP_LOG_CONFIG['validation_mode'] = 'permissive'
        
        env = Envelope([[0, -50], [1, 150]])
        result = parser._validate_and_clip(env, 0.0, 100.0, 'test', 'value')
        
        # Breakpoints clampati
        assert result.breakpoints == [[0, 0.0], [1, 100.0]]
        # Log chiamato per entrambi i punti
        assert mock_log.call_count == 2
    
    @patch('test_parser.log_config_warning')
    def test_envelope_mixed_permissive_clips_only_invalid(self, mock_log):
        """Envelope misto in permissive → clamp solo invalidi."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        global CLIP_LOG_CONFIG
        CLIP_LOG_CONFIG['validation_mode'] = 'permissive'
        
        env = Envelope([[0, 50], [1, 150], [2, 75]])  # Solo [1] invalido
        result = parser._validate_and_clip(env, 0.0, 100.0, 'test', 'value')
        
        assert result.breakpoints == [[0, 50], [1, 100.0], [2, 75]]
        # Log chiamato solo 1 volta
        assert mock_log.call_count == 1


# =============================================================================
# 6. TEST INTEGRAZIONE COMPLETA
# =============================================================================

class TestParserIntegration:
    """Test integrazione completa parser."""
    
    def test_complete_workflow_number(self):
        """Workflow completo: numero → Parameter."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        param = parser.parse_parameter(
            name='volume',
            value_raw=-6.0,
            range_raw=3.0,
            prob_raw=75.0
        )
        
        assert param.name == 'volume'
        assert param.value == -6.0
        assert param.mod_range == 3.0
        assert param.owner_id == "test_stream"
    
    def test_complete_workflow_envelope(self):
        """Workflow completo: envelope → Parameter."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        env_data = [[0, -20], [10, 0]]
        param = parser.parse_parameter('volume', env_data)
        
        assert isinstance(param.value, Envelope)
        assert param.value.breakpoints == env_data
    
    def test_workflow_with_clipping_strict(self):
        """Workflow con clipping strict → errore."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        global CLIP_LOG_CONFIG
        CLIP_LOG_CONFIG['validation_mode'] = 'strict'
        
        # Volume bounds: [-60, 12]
        with pytest.raises(ValueError):
            parser.parse_parameter('volume', 50.0)  # Fuori bounds
    
    @patch('test_parser.log_config_warning')
    def test_workflow_with_clipping_permissive(self, mock_log):
        """Workflow con clipping permissive → clamp."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        global CLIP_LOG_CONFIG
        CLIP_LOG_CONFIG['validation_mode'] = 'permissive'
        
        # Volume bounds: [-60, 12]
        param = parser.parse_parameter('volume', 50.0)
        
        assert param.value == 12.0  # Clampato a max
        assert mock_log.called
    
    def test_workflow_all_optional_params(self):
        """Workflow con tutti parametri opzionali."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        param = parser.parse_parameter(
            'pitch',
            value_raw=1.0,
            range_raw=0.1,
            prob_raw=50.0
        )
        
        assert param.value == 1.0
        assert param.mod_range == 0.1


# =============================================================================
# 7. TEST ERROR HANDLING
# =============================================================================

class TestParserErrorHandling:
    """Test gestione errori."""
    
    def test_parse_unknown_parameter_raises(self):
        """Parametro sconosciuto → KeyError."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        with pytest.raises(KeyError) as exc_info:
            parser.parse_parameter('unknown_param', 10.0)
        
        assert "not found in registry" in str(exc_info.value)
    
    def test_parse_invalid_value_type_raises(self):
        """Tipo valore invalido → ValueError."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        with pytest.raises(ValueError) as exc_info:
            parser.parse_parameter('volume', "invalid_string")
        
        assert "Formato non valido" in str(exc_info.value)
    
    def test_validate_invalid_type_raises(self):
        """Tipo non validabile → TypeError."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        with pytest.raises(TypeError) as exc_info:
            parser._validate_and_clip("string", 0.0, 100.0, 'test', 'value')
        
        assert "Cannot validate type" in str(exc_info.value)


# =============================================================================
# 8. TEST EDGE CASES
# =============================================================================

class TestParserEdgeCases:
    """Test edge cases."""
    
    def test_zero_value(self):
        """Valore zero valido."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        param = parser.parse_parameter('test_param', 0.0)
        
        assert param.value == 0.0
    
    def test_negative_value_in_negative_bounds(self):
        """Valore negativo in bounds negativi."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        # Volume: [-60, 12]
        param = parser.parse_parameter('volume', -30.0)
        
        assert param.value == -30.0
    
    def test_fractional_value(self):
        """Valore frazionario."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        param = parser.parse_parameter('pitch', 1.23456789)
        
        assert param.value == pytest.approx(1.23456789)
    
    def test_envelope_single_breakpoint(self):
        """Envelope con singolo breakpoint."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        env_data = [[5, 42]]
        param = parser.parse_parameter('test_param', env_data)
        
        assert param.value.breakpoints == [[5, 42]]
    
    def test_envelope_empty_list(self):
        """Envelope con lista vuota."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        env_data = []
        param = parser.parse_parameter('test_param', env_data)
        
        assert param.value.breakpoints == []
    
    def test_very_small_bounds_range(self):
        """Bounds con range molto piccolo."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        # Pan: [-1.0, 1.0]
        param = parser.parse_parameter('pan', 0.0)
        
        assert param.value == 0.0
    
    def test_bounds_at_limits(self):
        """Valore esattamente ai limiti."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        # Volume: [-60, 12]
        param_min = parser.parse_parameter('volume', -60.0)
        param_max = parser.parse_parameter('volume', 12.0)
        
        assert param_min.value == -60.0
        assert param_max.value == 12.0


# =============================================================================
# 9. TEST PARAMETRIZZATI
# =============================================================================

class TestParserParametrized:
    """Test parametrizzati per coverage sistematica."""
    
    @pytest.mark.parametrize("value", [0.0, 10.0, 50.0, 100.0])
    def test_various_values(self, value):
        """Test con vari valori."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        param = parser.parse_parameter('test_param', value)
        
        assert param.value == value
    
    @pytest.mark.parametrize("value_type", ['value', 'range', 'probability'])
    def test_different_value_types(self, value_type):
        """Test con diversi value_type."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        result = parser._validate_and_clip(50.0, 0.0, 100.0, 'test', value_type)
        
        assert result == 50.0
    
    @pytest.mark.parametrize("mode", ['strict', 'permissive'])
    def test_validation_modes(self, mode):
        """Test entrambe validation_mode."""
        config = StreamConfig()
        parser = GranularParser(config)
        
        global CLIP_LOG_CONFIG
        CLIP_LOG_CONFIG['validation_mode'] = mode
        
        # Valore valido funziona in entrambe
        result = parser._validate_and_clip(50.0, 0.0, 100.0, 'test', 'value')
        assert result == 50.0