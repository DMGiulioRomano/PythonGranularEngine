# tests/test_envelope_factory.py
"""
Test suite per InterpolationStrategyFactory.

Organizzazione:
1. Test creazione strategy valide
2. Test case-insensitivity
3. Test errori con tipi non validi
4. Test passaggio istanza già creata
5. Test get_supported_types()
"""

import pytest
from pge.envelopes.envelope_factory import InterpolationStrategyFactory
from pge.envelopes.envelope_interpolation import (
    InterpolationStrategy,
    LinearInterpolation,
    StepInterpolation,
    CubicInterpolation
)


# =============================================================================
# 1. TEST CREAZIONE STRATEGY VALIDE
# =============================================================================

class TestStrategyCreation:
    """Test creazione strategy base."""
    
    def test_create_linear(self):
        """Crea LinearInterpolation."""
        strategy = InterpolationStrategyFactory.create('linear')
        assert isinstance(strategy, LinearInterpolation)
        assert isinstance(strategy, InterpolationStrategy)
    
    def test_create_step(self):
        """Crea StepInterpolation."""
        strategy = InterpolationStrategyFactory.create('step')
        assert isinstance(strategy, StepInterpolation)
        assert isinstance(strategy, InterpolationStrategy)
    
    def test_create_cubic(self):
        """Crea CubicInterpolation."""
        strategy = InterpolationStrategyFactory.create('cubic')
        assert isinstance(strategy, CubicInterpolation)
        assert isinstance(strategy, InterpolationStrategy)
    
    def test_each_call_creates_new_instance(self):
        """Ogni chiamata crea una nuova istanza."""
        strategy1 = InterpolationStrategyFactory.create('linear')
        strategy2 = InterpolationStrategyFactory.create('linear')
        
        assert strategy1 is not strategy2
        assert type(strategy1) == type(strategy2)


# =============================================================================
# 2. TEST CASE-INSENSITIVITY
# =============================================================================

class TestCaseInsensitivity:
    """Test robustezza case-insensitive."""
    
    def test_uppercase(self):
        """Tipi in uppercase."""
        assert isinstance(
            InterpolationStrategyFactory.create('LINEAR'),
            LinearInterpolation
        )
        assert isinstance(
            InterpolationStrategyFactory.create('STEP'),
            StepInterpolation
        )
        assert isinstance(
            InterpolationStrategyFactory.create('CUBIC'),
            CubicInterpolation
        )
    
    def test_mixed_case(self):
        """Tipi in mixed case."""
        assert isinstance(
            InterpolationStrategyFactory.create('LiNeAr'),
            LinearInterpolation
        )
        assert isinstance(
            InterpolationStrategyFactory.create('StEp'),
            StepInterpolation
        )
        assert isinstance(
            InterpolationStrategyFactory.create('CuBiC'),
            CubicInterpolation
        )
    
    def test_with_whitespace(self):
        """Tipi con whitespace ai bordi."""
        assert isinstance(
            InterpolationStrategyFactory.create('  linear  '),
            LinearInterpolation
        )
        assert isinstance(
            InterpolationStrategyFactory.create('\tstep\n'),
            StepInterpolation
        )


# =============================================================================
# 3. TEST ERRORI CON TIPI NON VALIDI
# =============================================================================

class TestInvalidTypes:
    """Test gestione errori."""
    
    def test_invalid_string_type(self):
        """Tipo stringa non riconosciuto."""
        with pytest.raises(ValueError) as exc_info:
            InterpolationStrategyFactory.create('exponential')
        
        assert 'non riconosciuto' in str(exc_info.value).lower()
        assert 'exponential' in str(exc_info.value)
        assert 'linear' in str(exc_info.value)  # Suggerimento
    
    def test_empty_string(self):
        """Stringa vuota."""
        with pytest.raises(ValueError) as exc_info:
            InterpolationStrategyFactory.create('')
        
        assert 'non riconosciuto' in str(exc_info.value).lower()
    
    def test_none_type(self):
        """Passa None."""
        with pytest.raises(ValueError) as exc_info:
            InterpolationStrategyFactory.create(None)
        
        assert 'deve essere str' in str(exc_info.value)
    
    def test_numeric_type(self):
        """Passa numero invece di stringa."""
        with pytest.raises(ValueError) as exc_info:
            InterpolationStrategyFactory.create(42)
        
        assert 'deve essere str' in str(exc_info.value)
    
    def test_list_type(self):
        """Passa lista invece di stringa."""
        with pytest.raises(ValueError) as exc_info:
            InterpolationStrategyFactory.create(['linear'])
        
        assert 'deve essere str' in str(exc_info.value)


# =============================================================================
# 4. TEST PASSAGGIO ISTANZA GIÀ CREATA
# =============================================================================

class TestPassExistingInstance:
    """Test passaggio di strategy già istanziata."""
    
    def test_pass_linear_instance(self):
        """Passa LinearInterpolation già creata."""
        existing = LinearInterpolation()
        result = InterpolationStrategyFactory.create(existing)
        
        assert result is existing  # Stessa istanza
    
    def test_pass_step_instance(self):
        """Passa StepInterpolation già creata."""
        existing = StepInterpolation()
        result = InterpolationStrategyFactory.create(existing)
        
        assert result is existing
    
    def test_pass_cubic_instance(self):
        """Passa CubicInterpolation già creata."""
        existing = CubicInterpolation()
        result = InterpolationStrategyFactory.create(existing)
        
        assert result is existing


# =============================================================================
# 5. TEST GET_SUPPORTED_TYPES
# =============================================================================

class TestSupportedTypes:
    """Test recupero tipi supportati."""
    
    def test_get_supported_types(self):
        """Ritorna lista tipi corretti."""
        supported = InterpolationStrategyFactory.get_supported_types()
        
        assert isinstance(supported, list)
        assert len(supported) == 3
        assert 'linear' in supported
        assert 'step' in supported
        assert 'cubic' in supported
    
    def test_supported_types_are_lowercase(self):
        """Tipi ritornati sono lowercase."""
        supported = InterpolationStrategyFactory.get_supported_types()
        
        for t in supported:
            assert t == t.lower()


# =============================================================================
# 6. TEST INTEGRAZIONE CON STRATEGY
# =============================================================================

class TestIntegrationWithStrategy:
    """Test che le strategy create funzionino correttamente."""
    
    def test_created_strategy_can_evaluate(self):
        """Strategy creata può chiamare evaluate()."""
        strategy = InterpolationStrategyFactory.create('linear')
        breakpoints = [[0, 0], [1, 10]]
        
        result = strategy.evaluate(0.5, breakpoints)
        assert result == pytest.approx(5.0)
    
    def test_created_strategy_can_integrate(self):
        """Strategy creata può chiamare integrate()."""
        strategy = InterpolationStrategyFactory.create('linear')
        breakpoints = [[0, 0], [1, 10]]
        
        area = strategy.integrate(0, 1, breakpoints)
        assert area == pytest.approx(5.0)  # Triangolo
    
    def test_all_types_work(self):
        """Tutte le strategy create funzionano."""
        breakpoints = [[0, 0], [1, 10]]
        
        for interp_type in ['linear', 'step', 'cubic']:
            strategy = InterpolationStrategyFactory.create(interp_type)
            
            # evaluate deve funzionare
            val = strategy.evaluate(0.5, breakpoints)
            assert isinstance(val, (int, float))
            
            # integrate deve funzionare
            if interp_type == 'cubic':
                area = strategy.integrate(0, 1, breakpoints, tangents=[1, 1])
            else:
                area = strategy.integrate(0, 1, breakpoints)
            assert isinstance(area, (int, float))

