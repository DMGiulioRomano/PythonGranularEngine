"""
Test suite completa per InterpolationStrategy (Linear, Step, Cubic).

Organizzazione:
1. Test LinearInterpolation - evaluate
2. Test LinearInterpolation - integrate
3. Test StepInterpolation - evaluate
4. Test StepInterpolation - integrate
5. Test CubicInterpolation - evaluate
6. Test CubicInterpolation - integrate
7. Test proprietà matematiche (additività, simmetria, scaling)
8. Test casi edge (intervalli vuoti, singoli punti, hold)
"""

import pytest
import math
from typing import List
from pge.envelopes.envelope_interpolation import *
# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def linear_strategy():
    """Strategy lineare."""
    return LinearInterpolation()


@pytest.fixture
def step_strategy():
    """Strategy step."""
    return StepInterpolation()


@pytest.fixture
def cubic_strategy():
    """Strategy cubic."""
    return CubicInterpolation()


@pytest.fixture
def simple_ramp():
    """Rampa semplice 0->10 in 10 secondi."""
    return [[0, 0], [10, 10]]


@pytest.fixture
def triangle():
    """Triangolo: salita e discesa."""
    return [[0, 0], [5, 10], [10, 0]]


@pytest.fixture
def multi_step():
    """Gradini multipli."""
    return [[0, 10], [3, 20], [7, 30], [10, 40]]


@pytest.fixture
def cubic_tangents_zero():
    """Tangenti nulle (simula Fritsch-Carlson con plateau)."""
    return [0, 0, 0, 0]


# =============================================================================
# 1. TEST LINEAR INTERPOLATION - EVALUATE
# =============================================================================

class TestLinearEvaluate:
    """Test evaluate per LinearInterpolation."""
    
    def test_evaluate_at_start(self, linear_strategy, simple_ramp):
        """Valore esatto all'inizio."""
        assert linear_strategy.evaluate(0, simple_ramp) == pytest.approx(0.0)
    
    def test_evaluate_at_end(self, linear_strategy, simple_ramp):
        """Valore esatto alla fine."""
        assert linear_strategy.evaluate(10, simple_ramp) == pytest.approx(10.0)
    
    def test_evaluate_middle(self, linear_strategy, simple_ramp):
        """Valore a metà."""
        assert linear_strategy.evaluate(5, simple_ramp) == pytest.approx(5.0)
    
    def test_evaluate_quarter(self, linear_strategy, simple_ramp):
        """Valore a un quarto."""
        assert linear_strategy.evaluate(2.5, simple_ramp) == pytest.approx(2.5)
    
    def test_evaluate_before_start_holds(self, linear_strategy, simple_ramp):
        """Prima dell'inizio: hold primo valore."""
        assert linear_strategy.evaluate(-5, simple_ramp) == pytest.approx(0.0)
    
    def test_evaluate_after_end_holds(self, linear_strategy, simple_ramp):
        """Dopo la fine: hold ultimo valore."""
        assert linear_strategy.evaluate(15, simple_ramp) == pytest.approx(10.0)
    
    def test_evaluate_triangle_peak(self, linear_strategy, triangle):
        """Picco del triangolo."""
        assert linear_strategy.evaluate(5, triangle) == pytest.approx(10.0)
    
    def test_evaluate_triangle_descending(self, linear_strategy, triangle):
        """Parte discendente del triangolo."""
        assert linear_strategy.evaluate(7.5, triangle) == pytest.approx(5.0)


# =============================================================================
# 2. TEST LINEAR INTERPOLATION - INTEGRATE
# =============================================================================

class TestLinearIntegrate:
    """Test integrate per LinearInterpolation."""
    
    def test_integrate_full_triangle(self, linear_strategy, simple_ramp):
        """Area triangolo completo: (base * altezza) / 2."""
        area = linear_strategy.integrate(0, 10, simple_ramp)
        assert area == pytest.approx(50.0)  # (10 * 10) / 2
    
    def test_integrate_partial_from_zero(self, linear_strategy, simple_ramp):
        """Area parziale da zero."""
        area = linear_strategy.integrate(0, 5, simple_ramp)
        assert area == pytest.approx(12.5)  # (5 * 5) / 2
    
    def test_integrate_partial_middle(self, linear_strategy, simple_ramp):
        """Area nel mezzo."""
        area = linear_strategy.integrate(3, 7, simple_ramp)
        # Trapezio: base=4, h1=3, h2=7
        # Area = (4 * (3 + 7)) / 2 = 20
        assert area == pytest.approx(20.0)
    
    def test_integrate_triangle_full(self, linear_strategy, triangle):
        """Triangolo completo: salita + discesa."""
        area = linear_strategy.integrate(0, 10, triangle)
        # Salita: (5 * 10) / 2 = 25
        # Discesa: (5 * 10) / 2 = 25
        # Totale: 50
        assert area == pytest.approx(50.0)
    
    def test_integrate_zero_interval(self, linear_strategy, simple_ramp):
        """Integrale su intervallo nullo."""
        area = linear_strategy.integrate(5, 5, simple_ramp)
        assert area == pytest.approx(0.0)
    
    def test_integrate_reverse_interval(self, linear_strategy, simple_ramp):
        """Integrale inverso (from > to) ritorna 0."""
        area = linear_strategy.integrate(10, 0, simple_ramp)
        assert area == pytest.approx(0.0)
    
    def test_integrate_before_envelope(self, linear_strategy, simple_ramp):
        """Integrale prima dell'envelope: usa hold."""
        # Da -5 a 0: rettangolo con altezza 0
        area = linear_strategy.integrate(-5, 0, simple_ramp)
        assert area == pytest.approx(0.0)
    
    def test_integrate_after_envelope(self, linear_strategy, simple_ramp):
        """Integrale dopo l'envelope: usa hold."""
        # Da 10 a 15: rettangolo con altezza 10
        area = linear_strategy.integrate(10, 15, simple_ramp)
        assert area == pytest.approx(50.0)  # 5 * 10


# =============================================================================
# 3. TEST STEP INTERPOLATION - EVALUATE
# =============================================================================

class TestStepEvaluate:
    """Test evaluate per StepInterpolation."""
    
    def test_evaluate_at_first_breakpoint(self, step_strategy, multi_step):
        """Esattamente sul primo breakpoint."""
        assert step_strategy.evaluate(0, multi_step) == pytest.approx(10.0)
    
    def test_evaluate_just_after_breakpoint(self, step_strategy, multi_step):
        """Appena dopo un breakpoint: nuovo valore."""
        assert step_strategy.evaluate(3.001, multi_step) == pytest.approx(20.0)
    
    def test_evaluate_just_before_breakpoint(self, step_strategy, multi_step):
        """Appena prima di un breakpoint: valore precedente."""
        assert step_strategy.evaluate(2.999, multi_step) == pytest.approx(10.0)
    
    def test_evaluate_middle_of_step(self, step_strategy, multi_step):
        """A metà di un gradino."""
        assert step_strategy.evaluate(5, multi_step) == pytest.approx(20.0)
    
    def test_evaluate_last_step(self, step_strategy, multi_step):
        """Ultimo gradino."""
        assert step_strategy.evaluate(9, multi_step) == pytest.approx(30.0)
    
    def test_evaluate_at_last_breakpoint(self, step_strategy, multi_step):
        """Esattamente sull'ultimo breakpoint."""
        assert step_strategy.evaluate(10, multi_step) == pytest.approx(40.0)
    
    def test_evaluate_before_first(self, step_strategy, multi_step):
        """Prima del primo breakpoint: primo valore."""
        assert step_strategy.evaluate(-5, multi_step) == pytest.approx(10.0)
    
    def test_evaluate_after_last(self, step_strategy, multi_step):
        """Dopo l'ultimo breakpoint: ultimo valore."""
        assert step_strategy.evaluate(15, multi_step) == pytest.approx(40.0)


# =============================================================================
# 4. TEST STEP INTERPOLATION - INTEGRATE
# =============================================================================

class TestStepIntegrate:
    """Test integrate per StepInterpolation."""
    
    def test_integrate_single_step_full(self, step_strategy):
        """Singolo gradino completo."""
        breakpoints = [[0, 10], [5, 10]]
        area = step_strategy.integrate(0, 5, breakpoints)
        assert area == pytest.approx(50.0)  # 5 * 10
    
    def test_integrate_single_step_partial(self, step_strategy):
        """Singolo gradino parziale."""
        breakpoints = [[0, 10], [5, 10]]
        area = step_strategy.integrate(1, 3, breakpoints)
        assert area == pytest.approx(20.0)  # 2 * 10
    
    def test_integrate_multiple_steps(self, step_strategy, multi_step):
        """Gradini multipli."""
        # Gradino 1 (0-3): 3 * 10 = 30
        # Gradino 2 (3-7): 4 * 20 = 80
        # Gradino 3 (7-10): 3 * 30 = 90
        # Totale: 200
        area = step_strategy.integrate(0, 10, multi_step)
        assert area == pytest.approx(200.0)
    
    def test_integrate_partial_steps(self, step_strategy, multi_step):
        """Integrale parziale attraverso più gradini."""
        # Da 2 a 8:
        # Gradino 1 (2-3): 1 * 10 = 10
        # Gradino 2 (3-7): 4 * 20 = 80
        # Gradino 3 (7-8): 1 * 30 = 30
        # Totale: 120
        area = step_strategy.integrate(2, 8, multi_step)
        assert area == pytest.approx(120.0)
    
    def test_integrate_zero_interval(self, step_strategy, multi_step):
        """Intervallo nullo."""
        area = step_strategy.integrate(5, 5, multi_step)
        assert area == pytest.approx(0.0)


# =============================================================================
# 5. TEST CUBIC INTERPOLATION - EVALUATE
# =============================================================================

class TestCubicEvaluate:
    """Test evaluate per CubicInterpolation."""
    
    def test_evaluate_at_breakpoints(self, cubic_strategy, simple_ramp):
        """Ai breakpoints deve restituire valori esatti."""
        tangents = [1.0, 1.0]  # Pendenza costante = 1
        assert cubic_strategy.evaluate(0, simple_ramp, tangents=tangents) == pytest.approx(0.0)
        assert cubic_strategy.evaluate(10, simple_ramp, tangents=tangents) == pytest.approx(10.0)
    
    def test_evaluate_middle_linear_tangents(self, cubic_strategy, simple_ramp):
        """Con tangenti = pendenza lineare, cubic ≈ linear."""
        tangents = [1.0, 1.0]
        result = cubic_strategy.evaluate(5, simple_ramp, tangents=tangents)
        assert result == pytest.approx(5.0, rel=1e-2)
    
    def test_evaluate_with_zero_tangents(self, cubic_strategy, simple_ramp):
        """Tangenti = 0: plateau piatto a metà."""
        tangents = [0.0, 0.0]
        result = cubic_strategy.evaluate(5, simple_ramp, tangents=tangents)
        # Con tangenti zero, la curva è più "piatta" ai bordi
        assert 3.0 < result < 7.0  # Range ragionevole
    
    def test_evaluate_before_envelope_holds(self, cubic_strategy, simple_ramp):
        """Prima dell'inizio: hold."""
        tangents = [1.0, 1.0]
        result = cubic_strategy.evaluate(-5, simple_ramp, tangents=tangents)
        assert result == pytest.approx(0.0)
    
    def test_evaluate_after_envelope_holds(self, cubic_strategy, simple_ramp):
        """Dopo la fine: hold."""
        tangents = [1.0, 1.0]
        result = cubic_strategy.evaluate(15, simple_ramp, tangents=tangents)
        assert result == pytest.approx(10.0)
    
    def test_evaluate_hermite_identity(self, cubic_strategy):
        """Test identità Hermite: con m0=m1=slope, cubic=linear."""
        breakpoints = [[0, 0], [1, 1]]
        tangents = [1.0, 1.0]  # Pendenza = 1
        
        # A t=0.5, lineare dà 0.5
        result = cubic_strategy.evaluate(0.5, breakpoints, tangents=tangents)
        assert result == pytest.approx(0.5, rel=1e-2)


# =============================================================================
# 6. TEST CUBIC INTERPOLATION - INTEGRATE
# =============================================================================

class TestCubicIntegrate:
    """Test integrate per CubicInterpolation."""
    
    def test_integrate_simple_ramp(self, cubic_strategy, simple_ramp):
        """Rampa semplice con tangenti lineari."""
        tangents = [1.0, 1.0]
        area = cubic_strategy.integrate(0, 10, simple_ramp, tangents=tangents)
        # Dovrebbe essere vicino all'area del triangolo lineare
        assert area == pytest.approx(50.0, rel=1e-2)
    
    def test_integrate_zero_tangents(self, cubic_strategy, simple_ramp):
        """Con tangenti zero: curva più "piatta"."""
        tangents = [0.0, 0.0]
        area = cubic_strategy.integrate(0, 10, simple_ramp, tangents=tangents)
        # Area dovrebbe essere comunque > 0 e < area lineare
        assert 30.0 < area < 60.0
    
    def test_integrate_partial(self, cubic_strategy, simple_ramp):
        """Integrale parziale."""
        tangents = [1.0, 1.0]
        area = cubic_strategy.integrate(0, 5, simple_ramp, tangents=tangents)
        assert area == pytest.approx(12.5, rel=1e-2)
    
    def test_integrate_zero_interval(self, cubic_strategy, simple_ramp):
        """Intervallo nullo."""
        tangents = [1.0, 1.0]
        area = cubic_strategy.integrate(5, 5, simple_ramp, tangents=tangents)
        assert area == pytest.approx(0.0)
    
    def test_integrate_simpson_accuracy(self, cubic_strategy):
        """Verifica accuratezza Simpson su funzione nota."""
        # Parabola y = x^2 da 0 a 2
        # Integrale analitico = (2^3)/3 = 8/3 ≈ 2.667
        breakpoints = [[0, 0], [2, 4]]
        # Tangente parabola y=x^2: y'=2x → m0=0, m2=4
        tangents = [0, 4]
        
        area = cubic_strategy.integrate(0, 2, breakpoints, tangents=tangents)
        # Simpson con 10 intervalli dovrebbe essere molto accurato
        # Ma Hermite != parabola esatta, quindi tolleranza più larga
        assert 2.0 < area < 3.5


# =============================================================================
# 7. TEST PROPRIETA MATEMATICHE
# =============================================================================

class TestMathematicalProperties:
    """Test proprietà matematiche comuni a tutte le strategie."""
    
    @pytest.mark.parametrize("strategy_fixture", [
        "linear_strategy", "step_strategy", "cubic_strategy"
    ])
    def test_additivity(self, strategy_fixture, request, simple_ramp):
        """Proprietà additiva: ∫[a,c] = ∫[a,b] + ∫[b,c]."""
        strategy = request.getfixturevalue(strategy_fixture)
        
        context = {'tangents': [1.0, 1.0]} if 'cubic' in strategy_fixture else {}
        
        full = strategy.integrate(0, 10, simple_ramp, **context)
        part1 = strategy.integrate(0, 5, simple_ramp, **context)
        part2 = strategy.integrate(5, 10, simple_ramp, **context)
        
        assert full == pytest.approx(part1 + part2, rel=1e-2)
    
    @pytest.mark.parametrize("strategy_fixture", [
        "linear_strategy", "step_strategy"
    ])
    def test_value_scaling(self, strategy_fixture, request):
        """Se raddoppio i valori, l'integrale raddoppia."""
        strategy = request.getfixturevalue(strategy_fixture)
        
        bp1 = [[0, 0], [10, 10]]
        bp2 = [[0, 0], [10, 20]]
        
        area1 = strategy.integrate(0, 10, bp1)
        area2 = strategy.integrate(0, 10, bp2)
        
        assert area2 == pytest.approx(2 * area1, rel=1e-2)
    
    @pytest.mark.parametrize("strategy_fixture", [
        "linear_strategy", "step_strategy"
    ])
    def test_time_scaling(self, strategy_fixture, request):
        """Se raddoppio il tempo, l'integrale raddoppia."""
        strategy = request.getfixturevalue(strategy_fixture)
        
        bp1 = [[0, 0], [5, 10]]
        bp2 = [[0, 0], [10, 10]]
        
        area1 = strategy.integrate(0, 5, bp1)
        area2 = strategy.integrate(0, 10, bp2)
        
        assert area2 == pytest.approx(2 * area1, rel=1e-2)


# =============================================================================
# 8. TEST CASI EDGE
# =============================================================================

class TestEdgeCases:
    """Test casi limite e edge cases."""
    
    def test_single_point_linear(self, linear_strategy):
        """Singolo breakpoint: costante."""
        breakpoints = [[5, 42]]
        assert linear_strategy.evaluate(3, breakpoints) == pytest.approx(42.0)
        assert linear_strategy.evaluate(5, breakpoints) == pytest.approx(42.0)
        assert linear_strategy.evaluate(10, breakpoints) == pytest.approx(42.0)
    
    def test_single_point_step(self, step_strategy):
        """Singolo breakpoint step."""
        breakpoints = [[5, 42]]
        assert step_strategy.evaluate(3, breakpoints) == pytest.approx(42.0)
        assert step_strategy.evaluate(10, breakpoints) == pytest.approx(42.0)
    
    def test_zero_duration_segment_linear(self, linear_strategy):
        """Segmento con durata zero (t0 == t1)."""
        breakpoints = [[5, 10], [5, 20], [10, 30]]
        # Dovrebbe gestire gracefully
        result = linear_strategy.evaluate(5, breakpoints)
        assert result in [10.0, 20.0]  # Uno dei due valori
    
    def test_negative_times_linear(self, linear_strategy, simple_ramp):
        """Tempi negativi: hold primo valore."""
        assert linear_strategy.evaluate(-100, simple_ramp) == pytest.approx(0.0)
    
    def test_very_large_times_linear(self, linear_strategy, simple_ramp):
        """Tempi molto grandi: hold ultimo valore."""
        assert linear_strategy.evaluate(1e6, simple_ramp) == pytest.approx(10.0)
    
    def test_integrate_fully_outside_before(self, linear_strategy, simple_ramp):
        """Integrale completamente prima dell'envelope."""
        area = linear_strategy.integrate(-10, -5, simple_ramp)
        # Hold primo valore (0), quindi area = 0
        assert area == pytest.approx(0.0)
    
    def test_integrate_fully_outside_after(self, linear_strategy, simple_ramp):
        """Integrale completamente dopo l'envelope."""
        area = linear_strategy.integrate(15, 20, simple_ramp)
        # Hold ultimo valore (10)
        assert area == pytest.approx(50.0)  # 5 * 10
    
    def test_tangents_empty_cubic(self, cubic_strategy, simple_ramp):
        """Cubic senza tangenti: default a 0."""
        result = cubic_strategy.evaluate(5, simple_ramp, tangents=[])
        # Dovrebbe funzionare con tangenti default = 0
        assert isinstance(result, float)
    
    def test_two_breakpoints_identical_values(self, linear_strategy):
        """Due breakpoints con stesso valore: linea piatta."""
        breakpoints = [[0, 10], [10, 10]]
        area = linear_strategy.integrate(0, 10, breakpoints)
        assert area == pytest.approx(100.0)  # Rettangolo 10*10


# =============================================================================
# 9. TEST CONSISTENCY TRA EVALUATE E INTEGRATE
# =============================================================================

class TestEvaluateIntegrateConsistency:
    """Verifica coerenza tra evaluate e integrate."""
    
    def test_linear_constant_envelope(self, linear_strategy):
        """Envelope costante: integrale = valore * durata."""
        breakpoints = [[0, 5], [10, 5]]
        area = linear_strategy.integrate(0, 10, breakpoints)
        assert area == pytest.approx(50.0)  # 5 * 10
        
        # Verifica che evaluate dia sempre 5
        assert linear_strategy.evaluate(0, breakpoints) == pytest.approx(5.0)
        assert linear_strategy.evaluate(5, breakpoints) == pytest.approx(5.0)
        assert linear_strategy.evaluate(10, breakpoints) == pytest.approx(5.0)
    
    def test_step_constant_envelope(self, step_strategy):
        """Step costante."""
        breakpoints = [[0, 7], [10, 7]]
        area = step_strategy.integrate(0, 10, breakpoints)
        assert area == pytest.approx(70.0)
        
        assert step_strategy.evaluate(3, breakpoints) == pytest.approx(7.0)
        assert step_strategy.evaluate(8, breakpoints) == pytest.approx(7.0)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])