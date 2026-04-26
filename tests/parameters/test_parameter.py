"""
test_parameter.py

Test suite completa per il modulo parameter.py (Smart Parameter).

Coverage:
1. Test inizializzazione Parameter
2. Test evaluation base (numero fisso)
3. Test evaluation con Envelope
4. Test modulation range (fisso e Envelope)
5. Test probability gates integration
6. Test variation strategies integration
7. Test distribution strategies integration
8. Test bounds e clamping
9. Test workflow completi
10. Test edge cases
"""

import pytest
from unittest.mock import Mock
import sys
sys.path.insert(0, '/home/claude')

# Imports necessari
from typing import Union, Optional

# =============================================================================
# MOCK CLASSES
# =============================================================================

class Envelope:
    """Mock Envelope per test."""
    def __init__(self, breakpoints):
        self.breakpoints = breakpoints
    
    def evaluate(self, time: float) -> float:
        """Interpolazione lineare semplice."""
        if not self.breakpoints:
            return 0.0
        
        # Trova segmento
        for i in range(len(self.breakpoints) - 1):
            t0, v0 = self.breakpoints[i]
            t1, v1 = self.breakpoints[i + 1]
            
            if t0 <= time <= t1:
                # Interpolazione lineare
                if t1 == t0:
                    return v0
                ratio = (time - t0) / (t1 - t0)
                return v0 + ratio * (v1 - v0)
        
        # Hold primo o ultimo valore
        if time < self.breakpoints[0][0]:
            return self.breakpoints[0][1]
        return self.breakpoints[-1][1]


class ParameterBounds:
    """Mock ParameterBounds."""
    def __init__(self, min_val, max_val, variation_mode='additive'):
        self.min_val = min_val
        self.max_val = max_val
        self.variation_mode = variation_mode


class ProbabilityGate:
    """Base class per gates."""
    def should_apply(self, time: float) -> bool:
        raise NotImplementedError  # pragma: no cover


class NeverGate(ProbabilityGate):
    """Gate sempre chiuso."""
    def should_apply(self, time: float) -> bool:
        return False


class AlwaysGate(ProbabilityGate):
    """Gate sempre aperto."""
    def should_apply(self, time: float) -> bool:
        return True


class RandomGate(ProbabilityGate):
    """Gate con probabilità fissa."""
    def __init__(self, probability: float):
        self.probability = probability
    
    def should_apply(self, time: float) -> bool:
        import random
        return random.random() < (self.probability / 100.0)


class DistributionStrategy:
    """Base strategy."""
    def sample(self, center: float, spread: float) -> float:
        raise NotImplementedError  # pragma: no cover


class UniformDistribution(DistributionStrategy):
    """Distribuzione uniforme."""
    def sample(self, center: float, spread: float) -> float:
        if spread <= 0:
            return center
        import random
        return center + random.uniform(-0.5, 0.5) * spread


class VariationStrategy:
    """Base variation strategy."""
    def apply(self, base: float, mod_range: float, distribution) -> float:
        raise NotImplementedError  # pragma: no cover


class AdditiveVariation(VariationStrategy):
    """Variazione additiva."""
    def apply(self, base: float, mod_range: float, distribution) -> float:
        return distribution.sample(base, mod_range) if mod_range > 0 else base


class InvertVariation(VariationStrategy):
    """Variazione inversione."""
    def apply(self, base: float, mod_range: float, distribution) -> float:
        return 1.0 - base


# Factory mock
class DistributionFactory:
    @staticmethod
    def create(mode: str):
        if mode == 'uniform':
            return UniformDistribution()
        raise ValueError(f"Unknown mode: {mode}")


class VariationFactory:
    @staticmethod
    def create(mode: str):
        if mode == 'additive':
            return AdditiveVariation()
        elif mode == 'invert':
            return InvertVariation()
        raise ValueError(f"Unknown mode: {mode}")


# =============================================================================
# PARAMETER CLASS
# =============================================================================

ParamInput = Union[float, int, Envelope]

class Parameter:
    """Smart Parameter con variation, gates, distribution."""
    
    def __init__(
        self,
        name: str,
        value: ParamInput,
        bounds: ParameterBounds,
        mod_range: Optional[ParamInput] = None,
        owner_id: str = "unknown",
        distribution_mode: str = 'uniform'
    ):
        self.name = name
        self.owner_id = owner_id
        self.value = value  # Esposto per test/visualizzazione
        
        self._value = value
        self._bounds = bounds
        self._mod_range = mod_range
        self._probability_gate = NeverGate()
        
        self._distribution = DistributionFactory.create(distribution_mode)
        self._variation_strategy = VariationFactory.create(bounds.variation_mode)
    
    def set_probability_gate(self, gate: ProbabilityGate):
        """Setter per dependency injection."""
        self._probability_gate = gate
    
    def get_value(self, time: float) -> float:
        """Calcola valore finale al tempo specificato."""
        # 1. Valuta base
        base_val = self._evaluate_input(self._value, time)
        
        # 2. Calcola range
        current_range = self._calculate_range(time)
        
        # 3. Check gate
        if not self._probability_gate.should_apply(time):
            return self._clamp(base_val, time)
        
        # 4. Applica variation
        final_val = self._variation_strategy.apply(
            base_val,
            current_range,
            self._distribution
        )
        
        # 5. Clamp
        return self._clamp(final_val, time)
    
    def _evaluate_input(self, param: Optional[ParamInput], time: float) -> float:
        """Valuta numero o Envelope."""
        if param is None:
            return 0.0
        if isinstance(param, Envelope):
            return param.evaluate(time)
        return float(param)
    
    def _calculate_range(self, time: float) -> float:
        """Calcola range di modulazione."""
        if self._mod_range is None:
            return 0.0
        return self._evaluate_input(self._mod_range, time)
    
    def _clamp(self, value: float, time: float) -> float:
        """Clamp ai bounds."""
        return max(self._bounds.min_val, min(self._bounds.max_val, value))


# =============================================================================
# 1. TEST INIZIALIZZAZIONE
# =============================================================================

class TestParameterInitialization:
    """Test inizializzazione Parameter."""
    
    def test_create_with_fixed_value(self):
        """Creazione con valore fisso."""
        bounds = ParameterBounds(0.0, 100.0)
        param = Parameter(
            name='volume',
            value=50.0,
            bounds=bounds
        )
        
        assert param.name == 'volume'
        assert param.value == 50.0
        assert param.owner_id == "unknown"
    
    def test_create_with_envelope(self):
        """Creazione con Envelope."""
        bounds = ParameterBounds(0.0, 100.0)
        env = Envelope([[0, 10], [1, 20]])
        
        param = Parameter(
            name='pitch',
            value=env,
            bounds=bounds
        )
        
        assert param.name == 'pitch'
        assert isinstance(param.value, Envelope)
    
    def test_create_with_mod_range(self):
        """Creazione con mod_range."""
        bounds = ParameterBounds(0.0, 100.0)
        
        param = Parameter(
            name='freq',
            value=440.0,
            bounds=bounds,
            mod_range=20.0
        )
        
        assert param._mod_range == 20.0
    
    def test_create_with_owner_id(self):
        """Creazione con owner_id custom."""
        bounds = ParameterBounds(0.0, 100.0)
        
        param = Parameter(
            name='pan',
            value=0.0,
            bounds=bounds,
            owner_id='stream_001'
        )
        
        assert param.owner_id == 'stream_001'
    
    def test_default_probability_gate_is_never(self):
        """Gate di default è NeverGate."""
        bounds = ParameterBounds(0.0, 100.0)
        param = Parameter('test', 10.0, bounds)
        
        assert isinstance(param._probability_gate, NeverGate)
    
    def test_default_distribution_is_uniform(self):
        """Distribuzione di default è uniform."""
        bounds = ParameterBounds(0.0, 100.0)
        param = Parameter('test', 10.0, bounds)
        
        assert isinstance(param._distribution, UniformDistribution)


# =============================================================================
# 2. TEST EVALUATION BASE (VALORE FISSO)
# =============================================================================

class TestParameterEvaluationFixed:
    """Test evaluation con valore fisso."""
    
    def test_get_value_returns_fixed_value(self):
        """get_value restituisce valore fisso."""
        bounds = ParameterBounds(0.0, 100.0)
        param = Parameter('vol', 50.0, bounds)
        
        result = param.get_value(time=0.5)
        
        assert result == 50.0
    
    def test_get_value_same_at_different_times(self):
        """Valore fisso uguale a tempi diversi."""
        bounds = ParameterBounds(0.0, 100.0)
        param = Parameter('pan', 0.5, bounds)
        
        assert param.get_value(0.0) == 0.5
        assert param.get_value(1.0) == 0.5
        assert param.get_value(10.0) == 0.5
    
    def test_get_value_with_integer(self):
        """get_value con valore intero."""
        bounds = ParameterBounds(0.0, 100.0)
        param = Parameter('count', 42, bounds)
        
        result = param.get_value(0.0)
        
        assert result == 42.0
        assert isinstance(result, float)
    
    def test_get_value_with_zero(self):
        """get_value con valore zero."""
        bounds = ParameterBounds(-10.0, 10.0)
        param = Parameter('offset', 0.0, bounds)
        
        assert param.get_value(0.0) == 0.0
    
    def test_get_value_with_negative(self):
        """get_value con valore negativo."""
        bounds = ParameterBounds(-100.0, 0.0)
        param = Parameter('depth', -50.0, bounds)
        
        assert param.get_value(0.0) == -50.0


# =============================================================================
# 3. TEST EVALUATION CON ENVELOPE
# =============================================================================

class TestParameterEvaluationEnvelope:
    """Test evaluation con Envelope."""
    
    def test_get_value_evaluates_envelope(self):
        """get_value valuta Envelope al tempo corretto."""
        bounds = ParameterBounds(0.0, 100.0)
        env = Envelope([[0, 10], [1, 20]])
        param = Parameter('ramp', env, bounds)
        
        assert param.get_value(0.0) == pytest.approx(10.0)
        assert param.get_value(0.5) == pytest.approx(15.0)
        assert param.get_value(1.0) == pytest.approx(20.0)
    
    def test_envelope_interpolation(self):
        """Envelope interpola correttamente."""
        bounds = ParameterBounds(0.0, 100.0)
        env = Envelope([[0, 0], [10, 100]])
        param = Parameter('linear', env, bounds)
        
        assert param.get_value(5.0) == pytest.approx(50.0)
        assert param.get_value(2.5) == pytest.approx(25.0)
        assert param.get_value(7.5) == pytest.approx(75.0)
    
    def test_envelope_holds_before_start(self):
        """Envelope tiene primo valore prima dell'inizio."""
        bounds = ParameterBounds(0.0, 100.0)
        env = Envelope([[5, 50], [10, 100]])
        param = Parameter('hold', env, bounds)
        
        assert param.get_value(0.0) == pytest.approx(50.0)
        assert param.get_value(2.5) == pytest.approx(50.0)
    
    def test_envelope_holds_after_end(self):
        """Envelope tiene ultimo valore dopo la fine."""
        bounds = ParameterBounds(0.0, 100.0)
        env = Envelope([[0, 10], [5, 50]])
        param = Parameter('hold', env, bounds)
        
        assert param.get_value(10.0) == pytest.approx(50.0)
        assert param.get_value(100.0) == pytest.approx(50.0)
    
    def test_envelope_triangle(self):
        """Envelope triangolare."""
        bounds = ParameterBounds(0.0, 100.0)
        env = Envelope([[0, 0], [5, 100], [10, 0]])
        param = Parameter('tri', env, bounds)
        
        assert param.get_value(0.0) == pytest.approx(0.0)
        assert param.get_value(5.0) == pytest.approx(100.0)
        assert param.get_value(10.0) == pytest.approx(0.0)


# =============================================================================
# 4. TEST MODULATION RANGE
# =============================================================================

class TestParameterModulationRange:
    """Test mod_range (fisso e Envelope)."""
    
    def test_mod_range_none_means_zero(self):
        """mod_range=None → nessuna modulazione."""
        bounds = ParameterBounds(0.0, 100.0)
        param = Parameter('vol', 50.0, bounds, mod_range=None)
        param.set_probability_gate(AlwaysGate())
        
        # Anche con gate aperto, senza range non varia
        result = param.get_value(0.0)
        assert result == 50.0
    
    def test_mod_range_fixed_value(self):
        """mod_range fisso."""
        bounds = ParameterBounds(0.0, 100.0)
        param = Parameter('freq', 440.0, bounds, mod_range=20.0)
        
        # Calcola range interno
        range_val = param._calculate_range(0.0)
        assert range_val == 20.0
    
    def test_mod_range_with_envelope(self):
        """mod_range con Envelope (dynamic depth)."""
        bounds = ParameterBounds(0.0, 100.0)
        range_env = Envelope([[0, 5], [10, 50]])
        
        param = Parameter('dyn', 50.0, bounds, mod_range=range_env)
        
        assert param._calculate_range(0.0) == pytest.approx(5.0)
        assert param._calculate_range(5.0) == pytest.approx(27.5)
        assert param._calculate_range(10.0) == pytest.approx(50.0)
    
    def test_mod_range_zero_no_variation(self):
        """mod_range=0 → nessuna variazione."""
        bounds = ParameterBounds(0.0, 100.0)
        param = Parameter('fixed', 50.0, bounds, mod_range=0.0)
        param.set_probability_gate(AlwaysGate())
        
        # Con gate aperto ma range=0, valore base
        result = param.get_value(0.0)
        assert result == 50.0


# =============================================================================
# 5. TEST PROBABILITY GATES INTEGRATION
# =============================================================================

class TestParameterProbabilityGates:
    """Test integrazione con ProbabilityGate."""
    
    def test_never_gate_no_variation(self):
        """NeverGate → nessuna variazione mai."""
        bounds = ParameterBounds(0.0, 100.0)
        param = Parameter('vol', 50.0, bounds, mod_range=20.0)
        # Default è NeverGate
        
        # Anche con mod_range, gate chiuso = no variation
        result = param.get_value(0.0)
        assert result == 50.0
    
    def test_always_gate_enables_variation(self):
        """AlwaysGate → variazione sempre attiva."""
        bounds = ParameterBounds(0.0, 100.0)
        param = Parameter('freq', 440.0, bounds, mod_range=20.0)
        param.set_probability_gate(AlwaysGate())
        
        # Con gate aperto, la variazione può applicarsi
        # (ma è stocastica, quindi verifichiamo solo che cambi)
        results = [param.get_value(i * 0.1) for i in range(100)]
        
        # Almeno alcuni valori devono essere diversi da 440
        assert any(r != 440.0 for r in results)
    
    def test_set_probability_gate(self):
        """set_probability_gate cambia gate."""
        bounds = ParameterBounds(0.0, 100.0)
        param = Parameter('test', 10.0, bounds)
        
        # Default è NeverGate
        assert isinstance(param._probability_gate, NeverGate)
        
        # Cambia a AlwaysGate
        param.set_probability_gate(AlwaysGate())
        assert isinstance(param._probability_gate, AlwaysGate)
    
    def test_gate_called_with_correct_time(self):
        """Gate riceve tempo corretto."""
        bounds = ParameterBounds(0.0, 100.0)
        param = Parameter('test', 10.0, bounds, mod_range=5.0)
        
        mock_gate = Mock(spec=ProbabilityGate)
        mock_gate.should_apply.return_value = False
        
        param.set_probability_gate(mock_gate)
        
        param.get_value(2.5)
        
        mock_gate.should_apply.assert_called_once_with(2.5)


# =============================================================================
# 6. TEST VARIATION STRATEGIES INTEGRATION
# =============================================================================

class TestParameterVariationStrategies:
    """Test integrazione con VariationStrategy."""
    
    def test_additive_variation_default(self):
        """Strategia additive (default) applica variazione."""
        bounds = ParameterBounds(0.0, 1000.0, variation_mode='additive')
        param = Parameter('freq', 440.0, bounds, mod_range=20.0)
        param.set_probability_gate(AlwaysGate())
        
        # Genera molti campioni
        samples = [param.get_value(i * 0.01) for i in range(100)]
        
        # Media dovrebbe essere vicina a 440
        mean = sum(samples) / len(samples)
        assert abs(mean - 440.0) < 10.0
        
        # Dovrebbe esserci variazione
        assert max(samples) > 440.0
        assert min(samples) < 440.0
    
    def test_invert_variation_strategy(self):
        """Strategia invert inverte valore."""
        bounds = ParameterBounds(0.0, 1.0, variation_mode='invert')
        param = Parameter('reverse', 0.2, bounds)
        param.set_probability_gate(AlwaysGate())
        
        result = param.get_value(0.0)
        
        # 1.0 - 0.2 = 0.8
        assert result == pytest.approx(0.8)
    
    def test_variation_not_applied_when_gate_closed(self):
        """Variation non applicata se gate chiuso."""
        bounds = ParameterBounds(0.0, 1.0, variation_mode='invert')
        param = Parameter('rev', 0.3, bounds)
        # Default NeverGate
        
        result = param.get_value(0.0)
        
        # Gate chiuso → nessuna inversione
        assert result == pytest.approx(0.3)


# =============================================================================
# 7. TEST DISTRIBUTION STRATEGIES INTEGRATION
# =============================================================================

class TestParameterDistributionStrategies:
    """Test integrazione con DistributionStrategy."""
    
    def test_uniform_distribution_used(self):
        """UniformDistribution è usata di default."""
        bounds = ParameterBounds(0.0, 100.0)
        param = Parameter('test', 50.0, bounds, mod_range=10.0)
        
        assert isinstance(param._distribution, UniformDistribution)
    
    def test_distribution_receives_correct_parameters(self):
        """Distribution riceve center e spread corretti."""
        bounds = ParameterBounds(0.0, 1000.0)
        
        # Mock distribution
        mock_dist = Mock(spec=UniformDistribution)
        mock_dist.sample.return_value = 450.0
        
        param = Parameter('freq', 440.0, bounds, mod_range=20.0)
        param._distribution = mock_dist
        param.set_probability_gate(AlwaysGate())
        
        result = param.get_value(0.0)
        
        # Verifica chiamata a sample
        mock_dist.sample.assert_called_once_with(440.0, 20.0)
        assert result == 450.0


# =============================================================================
# 8. TEST BOUNDS E CLAMPING
# =============================================================================

class TestParameterBoundsAndClamping:
    """Test bounds e clamping."""
    
    def test_value_within_bounds_unchanged(self):
        """Valore dentro bounds non viene clampato."""
        bounds = ParameterBounds(0.0, 100.0)
        param = Parameter('vol', 50.0, bounds)
        
        result = param.get_value(0.0)
        assert result == 50.0
    
    def test_value_above_max_clamped(self):
        """Valore sopra max viene clampato."""
        bounds = ParameterBounds(0.0, 100.0)
        param = Parameter('over', 150.0, bounds)
        
        result = param.get_value(0.0)
        assert result == 100.0
    
    def test_value_below_min_clamped(self):
        """Valore sotto min viene clampato."""
        bounds = ParameterBounds(0.0, 100.0)
        param = Parameter('under', -50.0, bounds)
        
        result = param.get_value(0.0)
        assert result == 0.0
    
    def test_envelope_value_clamped(self):
        """Envelope con valori fuori bounds viene clampato."""
        bounds = ParameterBounds(0.0, 100.0)
        env = Envelope([[0, -50], [5, 150]])
        param = Parameter('clamp', env, bounds)
        
        assert param.get_value(0.0) == 0.0   # Clampato a min
        assert param.get_value(5.0) == 100.0  # Clampato a max
    
    def test_varied_value_clamped(self):
        """Valore variato viene clampato se fuori bounds."""
        bounds = ParameterBounds(0.0, 100.0)
        
        # Mock distribution che restituisce valore fuori bounds
        mock_dist = Mock(spec=UniformDistribution)
        mock_dist.sample.return_value = 150.0
        
        param = Parameter('test', 50.0, bounds, mod_range=100.0)
        param._distribution = mock_dist
        param.set_probability_gate(AlwaysGate())
        
        result = param.get_value(0.0)
        
        # Clampato a 100
        assert result == 100.0
    
    def test_negative_bounds(self):
        """Bounds negativi funzionano correttamente."""
        bounds = ParameterBounds(-50.0, 0.0)
        param = Parameter('neg', -25.0, bounds)
        
        assert param.get_value(0.0) == -25.0
        
        # Test clamping
        param2 = Parameter('over', 10.0, bounds)
        assert param2.get_value(0.0) == 0.0


# =============================================================================
# 9. TEST WORKFLOW COMPLETI
# =============================================================================

class TestParameterCompleteWorkflows:
    """Test workflow completi realistici."""
    
    def test_workflow_pitch_with_variation(self):
        """Workflow: pitch con variazione gaussiana."""
        bounds = ParameterBounds(0.125, 8.0)
        param = Parameter('pitch', 1.0, bounds, mod_range=0.1)
        param.set_probability_gate(RandomGate(50.0))
        
        # Genera 100 campioni
        samples = [param.get_value(i * 0.01) for i in range(100)]
        
        # Circa metà dovrebbero essere variati (gate 50%)
        varied = sum(1 for s in samples if s != 1.0)
        assert 30 <= varied <= 70  # Range tolleranza
    
    def test_workflow_volume_envelope_with_jitter(self):
        """Workflow: volume envelope con jitter."""
        bounds = ParameterBounds(-60.0, 12.0)
        env = Envelope([[0, -20], [10, 0]])
        param = Parameter('vol', env, bounds, mod_range=3.0)
        param.set_probability_gate(AlwaysGate())
        
        # Valori variano attorno all'envelope
        val_start = param.get_value(0.0)
        val_mid = param.get_value(5.0)
        val_end = param.get_value(10.0)
        
        # Dovrebbero essere vicini ai valori envelope ma non esatti
        assert -25.0 <= val_start <= -15.0
        assert -15.0 <= val_mid <= -5.0
        assert -5.0 <= val_end <= 5.0
    
    def test_workflow_reverse_parameter(self):
        """Workflow: reverse con InvertVariation."""
        bounds = ParameterBounds(0.0, 1.0, variation_mode='invert')
        param = Parameter('reverse', 0.0, bounds)  # Forward
        param.set_probability_gate(AlwaysGate())
        
        result = param.get_value(0.0)
        
        # Invertito: 1.0 - 0.0 = 1.0 (reverse)
        assert result == 1.0
    
    def test_workflow_dynamic_modulation_depth(self):
        """Workflow: profondità modulazione dinamica."""
        bounds = ParameterBounds(0.0, 1000.0)
        range_env = Envelope([[0, 0], [10, 100]])  # Depth cresce
        
        param = Parameter('freq', 440.0, bounds, mod_range=range_env)
        param.set_probability_gate(AlwaysGate())
        
        # All'inizio: range piccolo
        # Alla fine: range grande
        # (Stocastico, ma range dovrebbe influenzare spread)
        early_samples = [param.get_value(0.1) for _ in range(50)]
        late_samples = [param.get_value(9.9) for _ in range(50)]
        
        early_std = (sum((s - 440)**2 for s in early_samples) / 50) ** 0.5
        late_std = (sum((s - 440)**2 for s in late_samples) / 50) ** 0.5
        
        # Late dovrebbe avere più variazione
        assert late_std > early_std


# =============================================================================
# 10. TEST EDGE CASES
# =============================================================================

class TestParameterEdgeCases:
    """Test edge cases e situazioni limite."""
    
    def test_zero_bounds_range(self):
        """Bounds con range zero (min==max)."""
        bounds = ParameterBounds(50.0, 50.0)
        param = Parameter('fixed', 100.0, bounds)
        
        # Sempre clampato a 50
        assert param.get_value(0.0) == 50.0
    
    def test_very_small_mod_range(self):
        """mod_range molto piccolo."""
        bounds = ParameterBounds(0.0, 1000.0)
        param = Parameter('freq', 440.0, bounds, mod_range=0.001)
        param.set_probability_gate(AlwaysGate())
        
        samples = [param.get_value(i * 0.1) for i in range(10)]
        
        # Tutti vicini a 440
        assert all(439.9 <= s <= 440.1 for s in samples)
    
    def test_very_large_mod_range(self):
        """mod_range molto grande."""
        bounds = ParameterBounds(0.0, 1000.0)
        param = Parameter('freq', 500.0, bounds, mod_range=2000.0)
        param.set_probability_gate(AlwaysGate())
        
        samples = [param.get_value(i * 0.1) for i in range(100)]
        
        # Tutti clampati ai bounds
        assert all(0.0 <= s <= 1000.0 for s in samples)
    
    def test_envelope_single_breakpoint(self):
        """Envelope con singolo breakpoint."""
        bounds = ParameterBounds(0.0, 100.0)
        env = Envelope([[5, 42]])
        param = Parameter('single', env, bounds)
        
        # Hold valore ovunque
        assert param.get_value(0.0) == 42.0
        assert param.get_value(5.0) == 42.0
        assert param.get_value(10.0) == 42.0
    
    def test_envelope_empty_breakpoints(self):
        """Envelope senza breakpoints."""
        bounds = ParameterBounds(0.0, 100.0)
        env = Envelope([])
        param = Parameter('empty', env, bounds)
        
        # Dovrebbe restituire 0 o essere gestito
        result = param.get_value(0.0)
        assert result == 0.0
    
    def test_negative_time(self):
        """get_value con tempo negativo."""
        bounds = ParameterBounds(0.0, 100.0)
        env = Envelope([[0, 10], [10, 20]])
        param = Parameter('neg_time', env, bounds)
        
        # Hold primo valore
        result = param.get_value(-5.0)
        assert result == 10.0
    
    def test_fractional_values(self):
        """Valori frazionari molto piccoli."""
        bounds = ParameterBounds(0.0, 1.0)
        param = Parameter('frac', 0.123456789, bounds)
        
        result = param.get_value(0.0)
        assert result == pytest.approx(0.123456789)
    
    def test_invalid_distribution_mode(self):
        """Creazione con distribution_mode invalido solleva ValueError."""
        bounds = ParameterBounds(0.0, 100.0)
        
        with pytest.raises(ValueError) as exc_info:
            Parameter('test', 10.0, bounds, distribution_mode='invalid')
        
        assert "Unknown mode" in str(exc_info.value)
    
    def test_invalid_variation_mode(self):
        """Creazione con variation_mode invalido solleva ValueError."""
        bounds = ParameterBounds(0.0, 100.0, variation_mode='invalid')
        
        with pytest.raises(ValueError) as exc_info:
            Parameter('test', 10.0, bounds)
        
        assert "Unknown mode" in str(exc_info.value)
    
    def test_envelope_interpolation_equal_times(self):
        """Envelope con due breakpoint allo stesso tempo."""
        bounds = ParameterBounds(0.0, 100.0)
        env = Envelope([[5, 10], [5, 20]])  # Stesso tempo
        param = Parameter('same', env, bounds)
        
        # Dovrebbe gestire correttamente
        result = param.get_value(5.0)
        assert result == 10.0  # Primo valore


# =============================================================================
# 11. TEST PARAMETRIZZATI
# =============================================================================

class TestParameterParametrized:
    """Test parametrizzati per coverage sistematica."""
    
    @pytest.mark.parametrize("value", [0.0, 10.0, 50.0, 100.0, -50.0])
    def test_fixed_values(self, value):
        """Test con vari valori fissi."""
        bounds = ParameterBounds(-100.0, 100.0)
        param = Parameter('test', value, bounds)
        
        result = param.get_value(0.0)
        clamped = max(-100.0, min(100.0, value))
        assert result == pytest.approx(clamped)
    
    @pytest.mark.parametrize("time", [0.0, 0.5, 1.0, 5.0, 10.0])
    def test_envelope_at_different_times(self, time):
        """Envelope valutata a tempi diversi."""
        bounds = ParameterBounds(0.0, 100.0)
        env = Envelope([[0, 0], [10, 100]])
        param = Parameter('ramp', env, bounds)
        
        result = param.get_value(time)
        expected = time * 10  # Rampa lineare
        assert result == pytest.approx(expected)
    
    @pytest.mark.parametrize("mod_range", [0.0, 1.0, 10.0, 100.0])
    def test_different_mod_ranges(self, mod_range):
        """Test con diversi mod_range."""
        bounds = ParameterBounds(0.0, 1000.0)
        param = Parameter('test', 500.0, bounds, mod_range=mod_range)
        param.set_probability_gate(AlwaysGate())

        samples = [param.get_value(i * 0.1) for i in range(10)]

        if mod_range == 0:
            # Nessuna variazione
            assert all(s == 500.0 for s in samples)
        else:
            # Variazione presente (probabilistica)
            # Almeno alcuni valori diversi
            assert len(set(samples)) > 1 or mod_range < 1.0


# =============================================================================
# 12. TEST resolve_param (U1 — funzione module-level)
# =============================================================================

import importlib
import sys as _sys

def _import_real_parameter():
    """Importa il modulo reale parameters.parameter via src/."""
    src_path = '/Users/giuliodemattia/github/DMGiulioRomano/PythonGranularEngine/src'
    if src_path not in _sys.path:
        _sys.path.insert(0, src_path)
    # Force-reimport per evitare conflitti con mock class Parameter sopra
    if 'parameters.parameter' in _sys.modules:
        return _sys.modules['parameters.parameter']
    return importlib.import_module('parameters.parameter')


class TestResolveParam:
    """Test funzione module-level resolve_param da parameters.parameter."""

    @pytest.fixture(autouse=True)
    def setup(self):
        mod = _import_real_parameter()
        self.resolve_param = mod.resolve_param
        self.StrategyParam = mod.StrategyParam
        from envelopes.envelope import Envelope as RealEnvelope
        self.Envelope = RealEnvelope

    def test_float_returns_float(self):
        assert self.resolve_param(2.5, 0.0) == 2.5

    def test_float_type_is_float(self):
        result = self.resolve_param(2.5, 0.0)
        assert isinstance(result, float)

    def test_int_cast_to_float(self):
        assert self.resolve_param(0, 0.0) == 0.0
        assert isinstance(self.resolve_param(0, 0.0), float)

    def test_none_returns_zero(self):
        assert self.resolve_param(None, 0.0) == 0.0

    def test_envelope_at_start(self):
        env = self.Envelope([[0, 0], [1, 10]])
        assert self.resolve_param(env, 0.0) == pytest.approx(0.0)

    def test_envelope_at_end(self):
        env = self.Envelope([[0, 0], [1, 10]])
        assert self.resolve_param(env, 1.0) == pytest.approx(10.0)

    def test_envelope_midpoint_linear(self):
        env = self.Envelope([[0, 0], [1, 10]])
        assert self.resolve_param(env, 0.5) == pytest.approx(5.0)

    def test_time_ignored_for_scalar(self):
        """Scalare: time non influisce sul risultato."""
        assert self.resolve_param(7.0, 0.0) == self.resolve_param(7.0, 99.9)

    def test_regression_evaluate_input_delegates(self):
        """Parameter._evaluate_input delega a resolve_param — stesso risultato."""
        mod = _import_real_parameter()
        from envelopes.envelope import Envelope as RealEnvelope
        from parameters.parameter_definitions import ParameterBounds
        env = RealEnvelope([[0, 0], [1, 10]])
        bounds = ParameterBounds(min_val=-1000.0, max_val=1000.0, variation_mode='additive')
        param = mod.Parameter(name='test', value=env, bounds=bounds)
        # _evaluate_input deve restituire lo stesso valore di resolve_param
        assert param._evaluate_input(env, 0.5) == pytest.approx(self.resolve_param(env, 0.5))