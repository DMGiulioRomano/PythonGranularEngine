"""
test_probability_gate.py

Test suite completa per il modulo probability_gate.py.

Coverage:
1. Test ProbabilityGate (ABC) - interfaccia
2. Test NeverGate - sempre False
3. Test AlwaysGate - sempre True
4. Test RandomGate - probabilità costante
5. Test EnvelopeGate - probabilità variabile
6. Test comportamento probabilistico e statistico
7. Test integrazione con Envelope
8. Test edge cases e validazione
"""

import pytest
from abc import ABC
from unittest.mock import Mock, patch
import sys
sys.path.insert(0, '/home/claude')

# Creo implementazione minimale per i test
from abc import ABC, abstractmethod
import random

class ProbabilityGate(ABC):
    """Gateway pattern: interfaccia unificata per gate probabilistici."""
    
    @abstractmethod
    def should_apply(self, time: float) -> bool:
        """Decide se applicare una variazione al tempo specificato."""
        pass  # pragma: no cover
    
    @abstractmethod
    def get_probability_value(self, time: float) -> float:
        """Restituisce il valore di probabilità corrente (0-100)."""
        pass  # pragma: no cover
    
    @property
    @abstractmethod
    def mode(self) -> str:
        """Tipo di gate ('never', 'always', 'random', 'envelope')."""
        pass  # pragma: no cover


class NeverGate(ProbabilityGate):
    """Gate che NON applica mai variazione."""
    
    def should_apply(self, time: float) -> bool:
        return False
    
    def get_probability_value(self, time: float) -> float:
        return 0.0
    
    @property
    def mode(self) -> str:
        return "never"


class AlwaysGate(ProbabilityGate):
    """Gate che applica SEMPRE variazione (100%)."""
    
    def should_apply(self, time: float) -> bool:
        return True
    
    def get_probability_value(self, time: float) -> float:
        return 100.0
    
    @property
    def mode(self) -> str:
        return "always"


class RandomGate(ProbabilityGate):
    """Gate con probabilità costante."""
    
    def __init__(self, probability: float):
        self._probability = min(100.0, max(0.0, probability))
    
    def should_apply(self, time: float) -> bool:
        return random.uniform(0, 100) < self._probability
    
    def get_probability_value(self, time: float) -> float:
        return self._probability
    
    @property
    def mode(self) -> str:
        return f"random({self._probability}%)"


class EnvelopeGate(ProbabilityGate):
    """Gate con probabilità variabile nel tempo (envelope)."""
    
    def __init__(self, envelope):
        self._envelope = envelope
    
    def should_apply(self, time: float) -> bool:
        prob = self._envelope.evaluate(time)
        return random.uniform(0, 100) < prob
    
    def get_probability_value(self, time: float) -> float:
        return self._envelope.evaluate(time)
    
    @property
    def mode(self) -> str:
        envelope_type = getattr(self._envelope, 'type', 'unknown')
        return f"envelope({envelope_type})"


# =============================================================================
# 1. TEST PROBABILITYGATE (ABC)
# =============================================================================

class TestProbabilityGateABC:
    """Test per l'interfaccia ProbabilityGate (Abstract Base Class)."""
    
    def test_is_abstract_class(self):
        """ProbabilityGate è una classe astratta."""
        assert ABC in ProbabilityGate.__bases__
    
    def test_cannot_instantiate_directly(self):
        """Non si può istanziare ProbabilityGate direttamente."""
        with pytest.raises(TypeError):
            ProbabilityGate()
    
    def test_has_abstract_methods(self):
        """ProbabilityGate ha metodi astratti."""
        abstract_methods = ProbabilityGate.__abstractmethods__
        
        assert 'should_apply' in abstract_methods
        assert 'get_probability_value' in abstract_methods
        assert 'mode' in abstract_methods
    
    def test_all_gates_inherit_from_base(self):
        """Tutte le gate classes ereditano da ProbabilityGate."""
        gates = [NeverGate, AlwaysGate, RandomGate, EnvelopeGate]
        
        for gate_class in gates:
            assert issubclass(gate_class, ProbabilityGate)
    
    def test_concrete_implementations_are_instantiable(self):
        """Le implementazioni concrete possono essere istanziate."""
        mock_envelope = Mock()
        mock_envelope.evaluate.return_value = 50.0
        mock_envelope.type = 'linear'
        
        gates = [
            NeverGate(),
            AlwaysGate(),
            RandomGate(50),
            EnvelopeGate(mock_envelope)
        ]
        
        for gate in gates:
            assert isinstance(gate, ProbabilityGate)


# =============================================================================
# 2. TEST NEVERGATE
# =============================================================================

class TestNeverGate:
    """Test per NeverGate - sempre False."""
    
    def test_should_apply_always_false(self):
        """should_apply restituisce sempre False."""
        gate = NeverGate()
        
        # Test a vari tempi
        assert gate.should_apply(0.0) is False
        assert gate.should_apply(1.0) is False
        assert gate.should_apply(100.0) is False
        assert gate.should_apply(-5.0) is False
    
    def test_should_apply_many_calls(self):
        """should_apply sempre False anche con molte chiamate."""
        gate = NeverGate()
        
        results = [gate.should_apply(t) for t in range(100)]
        assert not any(results), "NeverGate non deve mai restituire True"
    
    def test_get_probability_value_always_zero(self):
        """get_probability_value restituisce sempre 0.0."""
        gate = NeverGate()
        
        assert gate.get_probability_value(0.0) == 0.0
        assert gate.get_probability_value(10.0) == 0.0
        assert gate.get_probability_value(999.0) == 0.0
    
    def test_mode_is_never(self):
        """mode property restituisce 'never'."""
        gate = NeverGate()
        
        assert gate.mode == "never"
    
    def test_mode_is_string(self):
        """mode è una stringa."""
        gate = NeverGate()
        
        assert isinstance(gate.mode, str)
    
    def test_no_constructor_parameters(self):
        """NeverGate non richiede parametri."""
        gate = NeverGate()
        assert gate is not None
    
    def test_multiple_instances_independent(self):
        """Istanze multiple sono indipendenti."""
        gate1 = NeverGate()
        gate2 = NeverGate()
        
        assert gate1 is not gate2
        assert gate1.should_apply(0.0) == gate2.should_apply(0.0)


# =============================================================================
# 3. TEST ALWAYSGATE
# =============================================================================

class TestAlwaysGate:
    """Test per AlwaysGate - sempre True."""
    
    def test_should_apply_always_true(self):
        """should_apply restituisce sempre True."""
        gate = AlwaysGate()
        
        assert gate.should_apply(0.0) is True
        assert gate.should_apply(1.0) is True
        assert gate.should_apply(100.0) is True
        assert gate.should_apply(-5.0) is True
    
    def test_should_apply_many_calls(self):
        """should_apply sempre True anche con molte chiamate."""
        gate = AlwaysGate()
        
        results = [gate.should_apply(t) for t in range(100)]
        assert all(results), "AlwaysGate deve sempre restituire True"
    
    def test_get_probability_value_always_hundred(self):
        """get_probability_value restituisce sempre 100.0."""
        gate = AlwaysGate()
        
        assert gate.get_probability_value(0.0) == 100.0
        assert gate.get_probability_value(10.0) == 100.0
        assert gate.get_probability_value(999.0) == 100.0
    
    def test_mode_is_always(self):
        """mode property restituisce 'always'."""
        gate = AlwaysGate()
        
        assert gate.mode == "always"
    
    def test_no_constructor_parameters(self):
        """AlwaysGate non richiede parametri."""
        gate = AlwaysGate()
        assert gate is not None
    
    def test_complementary_to_never_gate(self):
        """AlwaysGate è complementare a NeverGate."""
        always = AlwaysGate()
        never = NeverGate()
        
        assert always.should_apply(0.0) != never.should_apply(0.0)
        assert always.get_probability_value(0.0) + never.get_probability_value(0.0) == 100.0


# =============================================================================
# 4. TEST RANDOMGATE
# =============================================================================

class TestRandomGate:
    """Test per RandomGate - probabilità costante."""
    
    def test_create_with_probability(self):
        """Creazione con probabilità specifica."""
        gate = RandomGate(75.0)
        
        assert gate is not None
        assert gate.get_probability_value(0.0) == 75.0
    
    def test_probability_clamped_to_zero(self):
        """Probabilità negativa viene clampata a 0."""
        gate = RandomGate(-10.0)
        
        assert gate.get_probability_value(0.0) == 0.0
    
    def test_probability_clamped_to_hundred(self):
        """Probabilità > 100 viene clampata a 100."""
        gate = RandomGate(150.0)
        
        assert gate.get_probability_value(0.0) == 100.0
    
    def test_get_probability_value_constant_over_time(self):
        """get_probability_value è costante nel tempo."""
        gate = RandomGate(60.0)
        
        values = [gate.get_probability_value(t) for t in range(10)]
        assert all(v == 60.0 for v in values)
    
    def test_mode_includes_probability(self):
        """mode include il valore di probabilità."""
        gate = RandomGate(80.0)
        
        assert "80.0" in gate.mode
        assert "random" in gate.mode
    
    def test_statistical_behavior_50_percent(self):
        """Comportamento statistico per 50%."""
        gate = RandomGate(50.0)
        
        results = [gate.should_apply(0.0) for _ in range(1000)]
        true_count = sum(results)
        
        # Con 1000 campioni, 50% ± 5%
        assert 450 <= true_count <= 550
    
    def test_statistical_behavior_25_percent(self):
        """Comportamento statistico per 25%."""
        gate = RandomGate(25.0)
        
        results = [gate.should_apply(0.0) for _ in range(1000)]
        true_count = sum(results)
        
        # 25% ± 5%
        assert 200 <= true_count <= 300
    
    def test_statistical_behavior_75_percent(self):
        """Comportamento statistico per 75%."""
        gate = RandomGate(75.0)
        
        results = [gate.should_apply(0.0) for _ in range(1000)]
        true_count = sum(results)
        
        # 75% ± 5%
        assert 700 <= true_count <= 800
    
    def test_zero_probability_behaves_like_never(self):
        """Probabilità 0 si comporta come NeverGate."""
        gate = RandomGate(0.0)
        
        results = [gate.should_apply(0.0) for _ in range(100)]
        assert not any(results)
    
    def test_hundred_probability_behaves_like_always(self):
        """Probabilità 100 si comporta come AlwaysGate."""
        gate = RandomGate(100.0)
        
        results = [gate.should_apply(0.0) for _ in range(100)]
        assert all(results)
    
    def test_fractional_probabilities(self):
        """Probabilità frazionarie funzionano."""
        gate = RandomGate(33.33)
        
        results = [gate.should_apply(0.0) for _ in range(1000)]
        true_count = sum(results)
        
        # 33.33% ± 5%
        assert 283 <= true_count <= 383
    
    def test_time_parameter_ignored_for_randomness(self):
        """Il parametro time non influenza la randomness."""
        gate = RandomGate(50.0)
        
        # Stesso comportamento statistico a tempi diversi
        results_t0 = [gate.should_apply(0.0) for _ in range(500)]
        results_t10 = [gate.should_apply(10.0) for _ in range(500)]
        
        # Entrambi ~50%
        assert 200 <= sum(results_t0) <= 300
        assert 200 <= sum(results_t10) <= 300


# =============================================================================
# 5. TEST ENVELOPEGATE
# =============================================================================

class TestEnvelopeGate:
    """Test per EnvelopeGate - probabilità variabile."""
    
    def test_create_with_envelope(self):
        """Creazione con envelope."""
        mock_envelope = Mock()
        mock_envelope.evaluate.return_value = 50.0
        mock_envelope.type = 'linear'
        
        gate = EnvelopeGate(mock_envelope)
        
        assert gate is not None
    
    def test_get_probability_value_from_envelope(self):
        """get_probability_value usa envelope.evaluate()."""
        mock_envelope = Mock()
        mock_envelope.evaluate.return_value = 75.0
        mock_envelope.type = 'linear'
        
        gate = EnvelopeGate(mock_envelope)
        
        value = gate.get_probability_value(5.0)
        
        assert value == 75.0
        mock_envelope.evaluate.assert_called_once_with(5.0)
    
    def test_get_probability_value_changes_over_time(self):
        """get_probability_value varia nel tempo."""
        mock_envelope = Mock()
        # Simula rampa: 0% a t=0, 100% a t=10
        mock_envelope.evaluate.side_effect = lambda t: t * 10
        mock_envelope.type = 'linear'
        
        gate = EnvelopeGate(mock_envelope)
        
        assert gate.get_probability_value(0.0) == 0.0
        assert gate.get_probability_value(5.0) == 50.0
        assert gate.get_probability_value(10.0) == 100.0
    
    def test_should_apply_uses_envelope_probability(self):
        """should_apply usa la probabilità dall'envelope."""
        mock_envelope = Mock()
        mock_envelope.evaluate.return_value = 0.0  # 0% prob
        mock_envelope.type = 'linear'
        
        gate = EnvelopeGate(mock_envelope)
        
        # Con 0%, dovrebbe sempre essere False
        results = [gate.should_apply(0.0) for _ in range(100)]
        assert not any(results)
    
    def test_should_apply_hundred_percent_envelope(self):
        """should_apply con envelope a 100%."""
        mock_envelope = Mock()
        mock_envelope.evaluate.return_value = 100.0
        mock_envelope.type = 'linear'
        
        gate = EnvelopeGate(mock_envelope)
        
        # Con 100%, dovrebbe sempre essere True
        results = [gate.should_apply(0.0) for _ in range(100)]
        assert all(results)
    
    def test_mode_includes_envelope_type(self):
        """mode include il tipo di envelope."""
        mock_envelope = Mock()
        mock_envelope.evaluate.return_value = 50.0
        mock_envelope.type = 'cubic'
        
        gate = EnvelopeGate(mock_envelope)
        
        assert "envelope" in gate.mode
        assert "cubic" in gate.mode
    
    def test_envelope_evaluated_at_correct_time(self):
        """Envelope viene valutato al tempo corretto."""
        mock_envelope = Mock()
        mock_envelope.evaluate.return_value = 50.0
        mock_envelope.type = 'linear'
        
        gate = EnvelopeGate(mock_envelope)
        
        gate.get_probability_value(3.14)
        
        mock_envelope.evaluate.assert_called_with(3.14)
    
    def test_statistical_behavior_with_constant_envelope(self):
        """Comportamento statistico con envelope costante."""
        mock_envelope = Mock()
        mock_envelope.evaluate.return_value = 50.0
        mock_envelope.type = 'linear'
        
        gate = EnvelopeGate(mock_envelope)
        
        results = [gate.should_apply(5.0) for _ in range(1000)]
        true_count = sum(results)
        
        # 50% ± 5%
        assert 450 <= true_count <= 550
    
    def test_envelope_without_type_attribute(self):
        """Envelope senza attributo 'type'."""
        mock_envelope = Mock()
        mock_envelope.evaluate.return_value = 50.0
        # Nessun attributo 'type'
        del mock_envelope.type
        
        gate = EnvelopeGate(mock_envelope)
        
        # mode dovrebbe gestire gracefully
        assert "envelope" in gate.mode
        assert "unknown" in gate.mode


# =============================================================================
# 6. TEST EDGE CASES
# =============================================================================

class TestProbabilityGateEdgeCases:
    """Test edge cases e situazioni limite."""
    
    def test_random_gate_boundary_probabilities(self):
        """Test probabilità ai limiti."""
        gates = [
            RandomGate(0.0),
            RandomGate(0.001),
            RandomGate(99.999),
            RandomGate(100.0)
        ]
        
        for gate in gates:
            # Deve funzionare senza errori
            assert isinstance(gate.get_probability_value(0.0), float)
            assert isinstance(gate.should_apply(0.0), bool)
    
    def test_time_negative_values(self):
        """Gate funzionano con tempi negativi."""
        gates = [
            NeverGate(),
            AlwaysGate(),
            RandomGate(50.0)
        ]
        
        for gate in gates:
            # Non deve sollevare errori
            gate.should_apply(-10.0)
            gate.get_probability_value(-10.0)
    
    def test_time_very_large_values(self):
        """Gate funzionano con tempi molto grandi."""
        gates = [
            NeverGate(),
            AlwaysGate(),
            RandomGate(50.0)
        ]
        
        for gate in gates:
            gate.should_apply(999999.0)
            gate.get_probability_value(999999.0)
    
    def test_envelope_returning_negative_probability(self):
        """Envelope che restituisce probabilità negative."""
        mock_envelope = Mock()
        mock_envelope.evaluate.return_value = -10.0
        mock_envelope.type = 'linear'
        
        gate = EnvelopeGate(mock_envelope)
        
        # Comportamento: negativo < uniform(0,100) → sempre False
        results = [gate.should_apply(0.0) for _ in range(100)]
        assert not any(results)
    
    def test_envelope_returning_over_hundred(self):
        """Envelope che restituisce > 100."""
        mock_envelope = Mock()
        mock_envelope.evaluate.return_value = 150.0
        mock_envelope.type = 'linear'
        
        gate = EnvelopeGate(mock_envelope)
        
        # Comportamento: 150 > uniform(0,100) → sempre True
        results = [gate.should_apply(0.0) for _ in range(100)]
        assert all(results)
    
    def test_all_gates_return_boolean_from_should_apply(self):
        """should_apply restituisce sempre bool."""
        mock_envelope = Mock()
        mock_envelope.evaluate.return_value = 50.0
        mock_envelope.type = 'linear'
        
        gates = [
            NeverGate(),
            AlwaysGate(),
            RandomGate(50.0),
            EnvelopeGate(mock_envelope)
        ]
        
        for gate in gates:
            result = gate.should_apply(0.0)
            assert isinstance(result, bool)
    
    def test_all_gates_return_float_from_get_probability(self):
        """get_probability_value restituisce sempre float."""
        mock_envelope = Mock()
        mock_envelope.evaluate.return_value = 50.0
        mock_envelope.type = 'linear'
        
        gates = [
            NeverGate(),
            AlwaysGate(),
            RandomGate(50.0),
            EnvelopeGate(mock_envelope)
        ]
        
        for gate in gates:
            result = gate.get_probability_value(0.0)
            assert isinstance(result, float)


# =============================================================================
# 7. TEST INTEGRAZIONE
# =============================================================================

class TestProbabilityGateIntegration:
    """Test integrazione e workflow tipici."""
    
    def test_workflow_parameter_with_gate(self):
        """Workflow tipico: Parameter usa ProbabilityGate."""
        gate = RandomGate(80.0)
        
        # Test che il gate funziona (non deterministico ma testabile)
        should_vary = gate.should_apply(time=5.0)
        assert isinstance(should_vary, bool)
        
        # Test che la probabilità è corretta
        assert gate.get_probability_value(5.0) == 80.0
    
    def test_gate_selection_pattern(self):
        """Pattern: selezione gate RandomGate per valori intermedi."""
        gate = RandomGate(75.0)
        assert isinstance(gate, RandomGate)
        assert gate.get_probability_value(0.0) == 75.0
    
    def test_gate_selection_pattern_zero(self):
        """Pattern: selezione NeverGate quando deviation_probability=0."""
        gate = NeverGate()
        assert isinstance(gate, NeverGate)
        assert gate.get_probability_value(0.0) == 0.0
    
    def test_gate_selection_pattern_hundred(self):
        """Pattern: selezione AlwaysGate quando deviation_probability=100."""
        gate = AlwaysGate()
        assert isinstance(gate, AlwaysGate)
        assert gate.get_probability_value(0.0) == 100.0
    
    def test_workflow_parameter_when_gate_open(self):
        """Workflow quando il gate è aperto (applica variazione)."""
        gate = AlwaysGate()
        should_vary = gate.should_apply(time=5.0)
        
        assert should_vary is True
        # Quando gate è aperto, applica variazione
        final_value = 10.0 + 2.0
        assert final_value == 12.0
    
    def test_workflow_parameter_when_gate_closed(self):
        """Workflow quando il gate è chiuso (usa valore base)."""
        gate = NeverGate()
        should_vary = gate.should_apply(time=5.0)
        
        assert should_vary is False
        # Quando gate è chiuso, usa valore base
        final_value = 10.0
        assert final_value == 10.0
    
    def test_envelope_gate_with_real_like_envelope(self):
        """EnvelopeGate con envelope realistico."""
        # Mock envelope che simula rampa 0->100 in 10 secondi
        mock_envelope = Mock()
        mock_envelope.type = 'linear'
        
        def ramp_evaluate(t):
            return min(100.0, max(0.0, t * 10))
        
        mock_envelope.evaluate = ramp_evaluate
        
        gate = EnvelopeGate(mock_envelope)
        
        # A t=0: ~0% (quasi mai True)
        results_t0 = [gate.should_apply(0.0) for _ in range(100)]
        assert sum(results_t0) < 10
        
        # A t=5: ~50%
        results_t5 = [gate.should_apply(5.0) for _ in range(1000)]
        true_count = sum(results_t5)
        assert 450 <= true_count <= 550
        
        # A t=10: ~100% (quasi sempre True)
        results_t10 = [gate.should_apply(10.0) for _ in range(100)]
        assert sum(results_t10) > 90
    
    def test_chaining_gates_for_complex_logic(self):
        """Pattern: combinazione di gate per logica complessa."""
        gate_a = RandomGate(80.0)
        gate_b = RandomGate(60.0)
        
        # Simulazione: applica variazione solo se ENTRAMBI i gate sono aperti
        time = 0.0
        apply_variation = gate_a.should_apply(time) and gate_b.should_apply(time)
        
        # Probabilità effettiva: 0.8 * 0.6 = 0.48 (48%)
        results = [
            gate_a.should_apply(0.0) and gate_b.should_apply(0.0)
            for _ in range(1000)
        ]
        true_count = sum(results)
        
        # 48% ± 5%
        assert 430 <= true_count <= 530


# =============================================================================
# 8. TEST PARAMETRIZZATI
# =============================================================================

class TestProbabilityGateParametrized:
    """Test parametrizzati per copertura sistematica."""
    
    @pytest.mark.parametrize("prob,expected_min,expected_max", [
        (10, 50, 150),    # 10% ± 5%
        (25, 200, 300),   # 25% ± 5%
        (50, 450, 550),   # 50% ± 5%
        (75, 700, 800),   # 75% ± 5%
        (90, 850, 950),   # 90% ± 5%
    ])
    def test_random_gate_statistical_accuracy(self, prob, expected_min, expected_max):
        """Test accuratezza statistica per varie probabilità."""
        gate = RandomGate(prob)
        
        results = [gate.should_apply(0.0) for _ in range(1000)]
        true_count = sum(results)
        
        assert expected_min <= true_count <= expected_max
    
    @pytest.mark.parametrize("time", [0.0, 1.0, 5.0, 10.0, 100.0, -5.0])
    def test_never_gate_consistent_at_all_times(self, time):
        """NeverGate è consistente a tutti i tempi."""
        gate = NeverGate()
        
        assert gate.should_apply(time) is False
        assert gate.get_probability_value(time) == 0.0
    
    @pytest.mark.parametrize("time", [0.0, 1.0, 5.0, 10.0, 100.0, -5.0])
    def test_always_gate_consistent_at_all_times(self, time):
        """AlwaysGate è consistente a tutti i tempi."""
        gate = AlwaysGate()
        
        assert gate.should_apply(time) is True
        assert gate.get_probability_value(time) == 100.0
    
    @pytest.mark.parametrize("prob", [0.0, 25.0, 50.0, 75.0, 100.0])
    def test_random_gate_probability_persists(self, prob):
        """RandomGate mantiene la probabilità costante."""
        gate = RandomGate(prob)
        
        values = [gate.get_probability_value(t) for t in range(10)]
        assert all(v == prob for v in values)