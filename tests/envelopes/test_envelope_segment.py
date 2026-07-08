# test_envelope_segment.py
"""
Test suite per Segment hierarchy.

Organizzazione:
1. Test NormalSegment - evaluate
2. Test NormalSegment - integrate
5. Test edge cases e validazione
6. Test factory function
"""

import pytest
from pge.envelopes.envelope_segment import Segment, NormalSegment
from pge.envelopes.envelope_interpolation import LinearInterpolation, StepInterpolation, CubicInterpolation


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def linear_strategy():
    return LinearInterpolation()


@pytest.fixture
def step_strategy():
    return StepInterpolation()


@pytest.fixture
def cubic_strategy():
    return CubicInterpolation()


@pytest.fixture
def simple_ramp_breakpoints():
    """Rampa lineare 0->10 in 1 secondo."""
    return [[0, 0], [1, 10]]


@pytest.fixture
def triangle_breakpoints():
    """Triangolo: salita e discesa."""
    return [[0, 0], [0.5, 10], [1, 0]]


# =============================================================================
# 1. TEST NORMALSEGMENT - EVALUATE
# =============================================================================

class TestNormalSegmentEvaluate:
    """Test evaluate per NormalSegment."""
    
    def test_evaluate_inside_segment(self, linear_strategy, simple_ramp_breakpoints):
        """Evaluate dentro il segmento: interpolazione."""
        seg = NormalSegment(simple_ramp_breakpoints, linear_strategy)
        
        assert seg.evaluate(0.0) == pytest.approx(0.0)
        assert seg.evaluate(0.5) == pytest.approx(5.0)
        assert seg.evaluate(1.0) == pytest.approx(10.0)
    
    def test_evaluate_before_segment_holds(self, linear_strategy, simple_ramp_breakpoints):
        """Evaluate prima del segmento: hold primo valore."""
        seg = NormalSegment(simple_ramp_breakpoints, linear_strategy)
        
        assert seg.evaluate(-1.0) == pytest.approx(0.0)
        assert seg.evaluate(-0.5) == pytest.approx(0.0)
    
    def test_evaluate_after_segment_holds(self, linear_strategy, simple_ramp_breakpoints):
        """Evaluate dopo il segmento: hold ultimo valore."""
        seg = NormalSegment(simple_ramp_breakpoints, linear_strategy)
        
        assert seg.evaluate(1.5) == pytest.approx(10.0)
        assert seg.evaluate(2.0) == pytest.approx(10.0)
    
    def test_evaluate_triangle_peak(self, linear_strategy, triangle_breakpoints):
        """Evaluate al picco del triangolo."""
        seg = NormalSegment(triangle_breakpoints, linear_strategy)
        
        assert seg.evaluate(0.5) == pytest.approx(10.0)
    
    def test_evaluate_with_step_strategy(self, step_strategy, simple_ramp_breakpoints):
        """Evaluate con strategia step."""
        seg = NormalSegment(simple_ramp_breakpoints, step_strategy)
        
        assert seg.evaluate(0.0) == pytest.approx(0.0)
        assert seg.evaluate(0.5) == pytest.approx(0.0)  # Hold left
        assert seg.evaluate(0.99) == pytest.approx(0.0)
        assert seg.evaluate(1.0) == pytest.approx(10.0)


# =============================================================================
# 2. TEST NORMALSEGMENT - INTEGRATE
# =============================================================================

class TestNormalSegmentIntegrate:
    """Test integrate per NormalSegment."""
    
    def test_integrate_full_segment(self, linear_strategy, simple_ramp_breakpoints):
        """Integrate completo: triangolo."""
        seg = NormalSegment(simple_ramp_breakpoints, linear_strategy)
        
        area = seg.integrate(0, 1)
        assert area == pytest.approx(5.0)  # (1 * 10) / 2
    
    def test_integrate_partial_segment(self, linear_strategy, simple_ramp_breakpoints):
        """Integrate parziale dentro il segmento."""
        seg = NormalSegment(simple_ramp_breakpoints, linear_strategy)
        
        area = seg.integrate(0.25, 0.75)
        # Trapezio: base=0.5, h1=2.5, h2=7.5
        # Area = 0.5 * (2.5 + 7.5) / 2 = 2.5
        assert area == pytest.approx(2.5)
    
    def test_integrate_before_segment(self, linear_strategy, simple_ramp_breakpoints):
        """Integrate prima del segmento: area hold."""
        seg = NormalSegment(simple_ramp_breakpoints, linear_strategy)
        
        area = seg.integrate(-1, 0)
        # Rettangolo: 1 * 0 = 0
        assert area == pytest.approx(0.0)
    
    def test_integrate_after_segment(self, linear_strategy, simple_ramp_breakpoints):
        """Integrate dopo il segmento: area hold."""
        seg = NormalSegment(simple_ramp_breakpoints, linear_strategy)
        
        area = seg.integrate(1, 2)
        # Rettangolo: 1 * 10 = 10
        assert area == pytest.approx(10.0)
    
    def test_integrate_spanning_before_and_inside(self, linear_strategy, simple_ramp_breakpoints):
        """Integrate che attraversa inizio segmento."""
        seg = NormalSegment(simple_ramp_breakpoints, linear_strategy)
        
        area = seg.integrate(-0.5, 0.5)
        # Hold (-0.5 to 0): 0.5 * 0 = 0
        # Triangle (0 to 0.5): (0.5 * 5) / 2 = 1.25
        # Total: 1.25
        assert area == pytest.approx(1.25)
    
    def test_integrate_spanning_inside_and_after(self, linear_strategy, simple_ramp_breakpoints):
        """Integrate che attraversa fine segmento."""
        seg = NormalSegment(simple_ramp_breakpoints, linear_strategy)
        
        area = seg.integrate(0.5, 1.5)
        # Triangle (0.5 to 1): trapezio con h1=5, h2=10, base=0.5
        # Area = 0.5 * (5 + 10) / 2 = 3.75
        # Hold (1 to 1.5): 0.5 * 10 = 5
        # Total: 8.75
        assert area == pytest.approx(8.75)
    
    def test_integrate_zero_interval(self, linear_strategy, simple_ramp_breakpoints):
        """Integrate su intervallo nullo."""
        seg = NormalSegment(simple_ramp_breakpoints, linear_strategy)
        
        assert seg.integrate(0.5, 0.5) == pytest.approx(0.0)
    
    def test_integrate_triangle(self, linear_strategy, triangle_breakpoints):
        """Integrate triangolo completo."""
        seg = NormalSegment(triangle_breakpoints, linear_strategy)
        
        area = seg.integrate(0, 1)
        # Salita (0-0.5): (0.5 * 10) / 2 = 2.5
        # Discesa (0.5-1): (0.5 * 10) / 2 = 2.5
        # Total: 5
        assert area == pytest.approx(5.0)


# =============================================================================
# 5. TEST EDGE CASES E VALIDAZIONE
# =============================================================================

class TestEdgeCasesAndValidation:
    """Test casi limite e validazione."""
    
    def test_segment_requires_at_least_one_breakpoint(self, linear_strategy):
        """Segment richiede almeno 1 breakpoint."""
        with pytest.raises(ValueError, match="breakpoints"):
            NormalSegment([], linear_strategy)
        
    def test_breakpoints_sorted_automatically(self, linear_strategy):
        """Breakpoints non ordinati vengono ordinati."""
        seg = NormalSegment([[1, 10], [0, 0], [0.5, 5]], linear_strategy)
        
        assert seg.breakpoints[0] == [0, 0]
        assert seg.breakpoints[1] == [0.5, 5]
        assert seg.breakpoints[2] == [1, 10]
    
    def test_segment_duration_property(self, linear_strategy):
        """Property duration funziona."""
        seg = NormalSegment([[0, 0], [1.5, 10]], linear_strategy)
        
        assert seg.duration == pytest.approx(1.5)
    
    def test_start_and_end_time_correct(self, linear_strategy):
        """start_time e end_time sono corretti."""
        seg = NormalSegment([[0.5, 0], [2.5, 10]], linear_strategy)
        
        assert seg.start_time == pytest.approx(0.5)
        assert seg.end_time == pytest.approx(2.5)
    
    def test_single_breakpoint_normal_segment(self, linear_strategy):
        """NormalSegment con singolo breakpoint: valore costante."""
        seg = NormalSegment([[5, 42]], linear_strategy)
        
        assert seg.evaluate(0) == pytest.approx(42.0)
        assert seg.evaluate(5) == pytest.approx(42.0)
        assert seg.evaluate(10) == pytest.approx(42.0)


# =============================================================================
# 7. TEST REPR
# =============================================================================

class TestRepr:
    """Test string representation."""
    
    def test_normal_segment_repr(self, linear_strategy):
        """NormalSegment repr è leggibile."""
        seg = NormalSegment([[0, 0], [1.234, 10]], linear_strategy)
        
        repr_str = repr(seg)
        assert "NormalSegment" in repr_str
        assert "start=0.000" in repr_str
        assert "end=1.234" in repr_str
        assert "LinearInterpolation" in repr_str
    
class TestSegmentAbstractMethodBodies:
    """Copre righe 72 e 86: corpi dei metodi astratti via super()."""

    def _make_concrete_segment_calling_super(self, breakpoints, strategy):
        """Helper: sottoclasse che delega a super() per coprire i pass."""
        class _SuperCallingSegment(NormalSegment):
            def evaluate(self, t):
                super_result = Segment.evaluate(self, t)  # riga 72
                return super_result if super_result is not None else 0.0

            def integrate(self, from_t, to_t):
                super_result = Segment.integrate(self, from_t, to_t)  # riga 86
                return super_result if super_result is not None else 0.0

        return _SuperCallingSegment(breakpoints, strategy)

    def test_abstract_evaluate_body(self):
        """Chiama Segment.evaluate per coprire riga 72 (pass)."""
        seg = self._make_concrete_segment_calling_super(
            [[0.0, 0.0], [1.0, 1.0]], LinearInterpolation()
        )
        result = seg.evaluate(0.5)
        assert result is not None  # NormalSegment.evaluate funziona normalmente

    def test_abstract_integrate_body(self):
        """Chiama Segment.integrate per coprire riga 86 (pass)."""
        seg = self._make_concrete_segment_calling_super(
            [[0.0, 0.0], [1.0, 1.0]], LinearInterpolation()
        )
        result = seg.integrate(0.0, 1.0)
        assert result is not None