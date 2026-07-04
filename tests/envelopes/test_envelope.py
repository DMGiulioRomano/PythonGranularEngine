"""
Test suite completa per classe Envelope.

Organizzazione:
1. Test inizializzazione - formato standard
2. Test inizializzazione - formato compatto
3. Test inizializzazione - formato dict
4. Test inizializzazione - formato misto
5. Test evaluate() - vari tipi interpolazione
6. Test integrate() - vari tipi interpolazione
7. Test tipo interpolazione (linear, step, cubic)
8. Test tangenti Fritsch-Carlson per cubic
9. Test gestione errori
10. Test type checker (is_envelope_like)
11. Test backward compatibility
12. Test casi edge
"""

import pytest
import math
from typing import List
from envelopes.envelope import Envelope
from envelopes.envelope_interpolation import LinearInterpolation, StepInterpolation, CubicInterpolation


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def simple_linear_breakpoints():
    """Breakpoints lineari semplici."""
    return [[0, 0], [1, 10], [2, 0]]


@pytest.fixture
def compact_format_simple():
    """Formato compatto semplice: 4 cicli in 0.4s."""
    return [[[0, 0], [100, 1]], 0.4, 4]


@pytest.fixture
def compact_format_cubic():
    """Formato compatto con interpolazione cubic."""
    return [[[0, 0], [50, 0.5], [100, 1]], 0.3, 3, 'cubic']


@pytest.fixture
def dict_format_linear():
    """Formato dict con linear."""
    return {
        'type': 'linear',
        'points': [[0, 0], [1, 10]]
    }


@pytest.fixture
def dict_format_compact():
    """Formato dict con formato compatto."""
    return {
        'type': 'step',
        'points': [[[0, 0], [100, 1]], 0.2, 2]
    }


@pytest.fixture
def mixed_format():
    """Formato misto: compatto + standard."""
    return [
        [[[0, 0], [100, 1]], 0.2, 2],  # Compatto
        [0.5, 0.5],                     # Standard
        [1.0, 0]                        # Standard
    ]


# =============================================================================
# 1. TEST INIZIALIZZAZIONE - FORMATO STANDARD
# =============================================================================

class TestInitializationStandard:
    """Test inizializzazione con formato standard."""
    
    def test_init_simple_breakpoints(self, simple_linear_breakpoints):
        """Inizializzazione con breakpoints standard."""
        env = Envelope(simple_linear_breakpoints)
        
        assert env.type == 'linear'
        assert isinstance(env.strategy, LinearInterpolation)
        assert len(env.segments) == 1
        assert env.segments[0].start_time == 0
        assert env.segments[0].end_time == 2
    
    def test_init_single_breakpoint(self):
        """Inizializzazione con singolo breakpoint."""
        env = Envelope([[0, 5]])
        
        assert env.type == 'linear'
        assert len(env.segments) == 1
    
    def test_init_two_breakpoints(self):
        """Inizializzazione con due breakpoints."""
        env = Envelope([[0, 0], [1, 10]])
        
        assert env.segments[0].start_time == 0
        assert env.segments[0].end_time == 1
    
    def test_init_multiple_breakpoints(self):
        """Inizializzazione con molti breakpoints."""
        points = [[0, 0], [1, 5], [2, 10], [3, 5], [4, 0]]
        env = Envelope(points)
        
        assert len(env.segments) == 1
        assert env.segments[0].start_time == 0
        assert env.segments[0].end_time == 4


# =============================================================================
# 2. TEST INIZIALIZZAZIONE - FORMATO COMPATTO
# =============================================================================

class TestInitializationCompact:
    """Test inizializzazione con formato compatto."""
    
    def test_init_compact_simple(self, compact_format_simple):
        """Inizializzazione con formato compatto semplice."""
        env = Envelope(compact_format_simple)
        
        assert env.type == 'linear'
        assert isinstance(env.strategy, LinearInterpolation)
        assert len(env.segments) == 1
        
        # 4 cicli * 2 punti = 8 breakpoints espansi
        assert len(env.segments[0].breakpoints) == 8
    
    def test_init_compact_with_interp(self, compact_format_cubic):
        """Inizializzazione con formato compatto + tipo."""
        env = Envelope(compact_format_cubic)
        
        assert env.type == 'cubic'
        assert isinstance(env.strategy, CubicInterpolation)
        
        # 3 cicli * 3 punti = 9 breakpoints
        assert len(env.segments[0].breakpoints) == 9
    
    def test_init_compact_single_rep(self):
        """Formato compatto con singola ripetizione."""
        compact = [[[0, 0], [100, 1]], 0.1, 1]
        env = Envelope(compact)
        
        # 1 ciclo * 2 punti = 2 breakpoints
        assert len(env.segments[0].breakpoints) == 2
    
    def test_compact_time_expansion(self):
        """Verifica espansione temporale formato compatto."""
        compact = [[[0, 0], [100, 1]], 0.4, 2]
        env = Envelope(compact)
        
        # Primo punto primo ciclo
        assert env.segments[0].breakpoints[0][0] == pytest.approx(0.0)
        # Ultimo punto primo ciclo
        assert env.segments[0].breakpoints[1][0] == pytest.approx(0.2)
        # Primo punto secondo ciclo (con offset)
        assert env.segments[0].breakpoints[2][0] > 0.2
        # Ultimo punto secondo ciclo
        assert env.segments[0].breakpoints[3][0] == pytest.approx(0.4)


# =============================================================================
# 3. TEST INIZIALIZZAZIONE - FORMATO DICT
# =============================================================================

class TestInitializationDict:
    """Test inizializzazione con formato dict."""
    
    def test_init_dict_linear(self, dict_format_linear):
        """Inizializzazione con dict format linear."""
        env = Envelope(dict_format_linear)
        
        assert env.type == 'linear'
        assert isinstance(env.strategy, LinearInterpolation)
    
    def test_init_dict_step(self):
        """Inizializzazione con dict format step."""
        dict_data = {
            'type': 'step',
            'points': [[0, 0], [1, 10]]
        }
        env = Envelope(dict_data)
        
        assert env.type == 'step'
        assert isinstance(env.strategy, StepInterpolation)
    
    def test_init_dict_cubic(self):
        """Inizializzazione con dict format cubic."""
        dict_data = {
            'type': 'cubic',
            'points': [[0, 0], [1, 5], [2, 10]]
        }
        env = Envelope(dict_data)
        
        assert env.type == 'cubic'
        assert isinstance(env.strategy, CubicInterpolation)
    
    def test_init_dict_with_compact(self, dict_format_compact):
        """Dict format con formato compatto nei points."""
        env = Envelope(dict_format_compact)
        
        assert env.type == 'step'
        # 2 cicli * 2 punti = 4 breakpoints
        assert len(env.segments[0].breakpoints) == 4
    
    def test_init_dict_default_type(self):
        """Dict senza tipo specificato: default a linear."""
        dict_data = {'points': [[0, 0], [1, 10]]}
        env = Envelope(dict_data)
        
        assert env.type == 'linear'


# =============================================================================
# 4. TEST INIZIALIZZAZIONE - FORMATO MISTO
# =============================================================================

class TestInitializationMixed:
    """Test inizializzazione con formato misto."""
    
    def test_init_mixed_compact_and_standard(self, mixed_format):
        """Formato misto: compatto + standard."""
        env = Envelope(mixed_format)
        
        # Compatto: 2 cicli * 2 punti = 4
        # Standard: 2 punti
        # Totale: 6 breakpoints
        assert len(env.segments[0].breakpoints) == 6
    
    def test_init_mixed_preserves_order(self):
        """Formato misto preserva ordine temporale."""
        mixed = [
            [0, 0],
            [[[0, 0], [100, 1]], 0.2, 2],
            [0.5, 0.5],
            [1.0, 0]
        ]
        env = Envelope(mixed)
        
        # Verifica ordinamento temporale
        times = [bp[0] for bp in env.segments[0].breakpoints]
        assert times == sorted(times)


# =============================================================================
# 5. TEST EVALUATE() - VARI TIPI INTERPOLAZIONE
# =============================================================================

class TestEvaluate:
    """Test metodo evaluate() con vari tipi."""
    
    def test_evaluate_linear_at_breakpoints(self):
        """Evaluate lineare esattamente sui breakpoints."""
        env = Envelope([[0, 0], [1, 10], [2, 0]])
        
        assert env.evaluate(0) == pytest.approx(0.0)
        assert env.evaluate(1) == pytest.approx(10.0)
        assert env.evaluate(2) == pytest.approx(0.0)
    
    def test_evaluate_linear_interpolated(self):
        """Evaluate lineare su punti interpolati."""
        env = Envelope([[0, 0], [1, 10]])
        
        assert env.evaluate(0.5) == pytest.approx(5.0)
        assert env.evaluate(0.25) == pytest.approx(2.5)
        assert env.evaluate(0.75) == pytest.approx(7.5)
    
    def test_evaluate_step_at_breakpoints(self):
        """Evaluate step sui breakpoints."""
        env = Envelope({'type': 'step', 'points': [[0, 10], [1, 20], [2, 30]]})
        
        assert env.evaluate(0) == pytest.approx(10.0)
        assert env.evaluate(1) == pytest.approx(20.0)
    
    def test_evaluate_step_between_breakpoints(self):
        """Evaluate step tra breakpoints (hold left)."""
        env = Envelope({'type': 'step', 'points': [[0, 10], [1, 20]]})
        
        assert env.evaluate(0.5) == pytest.approx(10.0)
        assert env.evaluate(0.99) == pytest.approx(10.0)
    
    def test_evaluate_cubic_smooth(self):
        """Evaluate cubic con interpolazione smooth."""
        env = Envelope({'type': 'cubic', 'points': [[0, 0], [1, 10], [2, 0]]})
        
        # Cubic dovrebbe essere smooth, non lineare
        mid_value = env.evaluate(1)
        assert mid_value == pytest.approx(10.0)  # Sul breakpoint
        
        # Tra breakpoints
        assert isinstance(env.evaluate(0.5), float)
        assert isinstance(env.evaluate(1.5), float)
    
    def test_evaluate_hold_before_start(self):
        """Evaluate prima dell'inizio: hold primo valore."""
        env = Envelope([[0, 5], [1, 10]])
        assert env.evaluate(-1) == pytest.approx(5.0)
        assert env.evaluate(-10) == pytest.approx(5.0)
    
    def test_evaluate_hold_after_end(self):
        """Evaluate dopo la fine: hold ultimo valore."""
        env = Envelope([[0, 5], [1, 10]])
        
        assert env.evaluate(2) == pytest.approx(10.0)
        assert env.evaluate(100) == pytest.approx(10.0)


# =============================================================================
# 6. TEST INTEGRATE() - VARI TIPI INTERPOLAZIONE
# =============================================================================

class TestIntegrate:
    """Test metodo integrate() con vari tipi."""
    
    def test_integrate_linear_full_range(self):
        """Integrate lineare su intero range."""
        env = Envelope([[0, 0], [1, 10]])
        
        # Triangolo: area = 0.5 * base * altezza = 0.5 * 1 * 10 = 5
        area = env.integrate(0, 1)
        assert area == pytest.approx(5.0)
    
    def test_integrate_linear_partial_range(self):
        """Integrate lineare su range parziale."""
        env = Envelope([[0, 0], [1, 10]])
        
        # Prima metà
        area_first_half = env.integrate(0, 0.5)
        assert area_first_half == pytest.approx(1.25)  # Triangolo più piccolo
    
    def test_integrate_constant_envelope(self):
        """Integrate envelope costante."""
        env = Envelope([[0, 5], [1, 5]])
        
        # Rettangolo: area = base * altezza = 1 * 5 = 5
        area = env.integrate(0, 1)
        assert area == pytest.approx(5.0)
    
    def test_integrate_step_envelope(self):
        """Integrate step envelope."""
        env = Envelope({'type': 'step', 'points': [[0, 10], [1, 20]]})
        
        # Step: hold 10 per 1 secondo = 10
        area = env.integrate(0, 1)
        assert area == pytest.approx(10.0)
    
    def test_integrate_symmetric(self):
        """Integrate con limiti invertiti: segno negativo."""
        env = Envelope([[0, 0], [1, 10]])
        
        area_forward = env.integrate(0, 1)
        area_backward = env.integrate(1, 0)
        
        assert area_backward == pytest.approx(-area_forward)
    
    def test_integrate_zero_duration(self):
        """Integrate con durata zero."""
        env = Envelope([[0, 0], [1, 10]])
        
        area = env.integrate(0.5, 0.5)
        assert area == pytest.approx(0.0)
    
    def test_integrate_hold_regions(self):
        """Integrate con regioni hold."""
        env = Envelope([[0, 0], [1, 10]])
        
        # Prima dell'inizio (hold primo valore = 0)
        area_before = env.integrate(-1, 0)
        assert area_before == pytest.approx(0.0)
        
        # Dopo la fine (hold ultimo valore = 10)
        area_after = env.integrate(1, 2)
        assert area_after == pytest.approx(10.0)
    
    def test_integrate_across_boundaries(self):
        """Integrate attraverso boundaries (hold + interpolato + hold)."""
        env = Envelope([[0, 0], [1, 10]])
        
        # Da prima dell'inizio a dopo la fine
        area_total = env.integrate(-1, 2)
        
        # -1 a 0: hold 0 → area = 0
        # 0 a 1: triangolo → area = 5
        # 1 a 2: hold 10 → area = 10
        # Totale: 15
        assert area_total == pytest.approx(15.0)


# =============================================================================
# 7. TEST TIPO INTERPOLAZIONE
# =============================================================================

class TestInterpolationType:
    """Test tipo interpolazione corretto."""
    
    def test_type_linear_default(self):
        """Tipo default è linear."""
        env = Envelope([[0, 0], [1, 10]])
        
        assert env.type == 'linear'
    
    def test_type_from_dict(self):
        """Tipo estratto da dict."""
        for interp_type in ['linear', 'step', 'cubic']:
            env = Envelope({'type': interp_type, 'points': [[0, 0], [1, 10]]})
            assert env.type == interp_type
    
    def test_type_from_compact_format(self):
        """Tipo estratto da formato compatto."""
        compact = [[[0, 0], [100, 1]], 0.2, 2, 'cubic']
        env = Envelope(compact)
        
        assert env.type == 'cubic'
    
    def test_strategy_matches_type(self):
        """Strategy corrisponde al tipo."""
        type_to_strategy = {
            'linear': LinearInterpolation,
            'step': StepInterpolation,
            'cubic': CubicInterpolation
        }
        
        for interp_type, strategy_class in type_to_strategy.items():
            env = Envelope({'type': interp_type, 'points': [[0, 0], [1, 10]]})
            assert isinstance(env.strategy, strategy_class)


# =============================================================================
# 8. TEST TANGENTI FRITSCH-CARLSON PER CUBIC
# =============================================================================

class TestFritschCarlsonTangents:
    """Test calcolo tangenti Fritsch-Carlson per cubic."""
    
    def test_tangents_computed_for_cubic(self):
        """Tangenti calcolate per interpolazione cubic."""
        env = Envelope({'type': 'cubic', 'points': [[0, 0], [1, 5], [2, 10]]})
        
        # Context dovrebbe contenere tangenti
        assert 'tangents' in env.segments[0].context
        tangents = env.segments[0].context['tangents']
        assert len(tangents) == 3  # Una per ogni breakpoint
    
    def test_tangents_not_computed_for_linear(self):
        """Tangenti NON calcolate per linear."""
        env = Envelope({'type': 'linear', 'points': [[0, 0], [1, 5], [2, 10]]})
        
        # Context dovrebbe essere vuoto o senza tangenti
        assert 'tangents' not in env.segments[0].context
    
    def test_tangents_monotone_ramp(self):
        """Tangenti per rampa monotona."""
        env = Envelope({'type': 'cubic', 'points': [[0, 0], [1, 5], [2, 10]]})
        
        tangents = env.segments[0].context['tangents']
        
        # Tutte tangenti dovrebbero essere positive (rampa crescente)
        assert all(t >= 0 for t in tangents)
    
    def test_tangents_zero_at_extrema(self):
        """Tangenti zero agli estremi (peak/valley)."""
        # Triangolo: 0 → 10 → 0
        env = Envelope({'type': 'cubic', 'points': [[0, 0], [1, 10], [2, 0]]})
        
        tangents = env.segments[0].context['tangents']
        
        # Tangente centrale dovrebbe essere circa zero (peak)
        # (Fritsch-Carlson pone tangenti zero quando segni cambiano)
        assert tangents[1] == pytest.approx(0.0, abs=0.1)
    
    def test_tangents_few_points(self):
        """Tangenti con pochi punti."""
        env = Envelope({'type': 'cubic', 'points': [[0, 0], [1, 10]]})
        
        tangents = env.segments[0].context['tangents']
        assert len(tangents) == 2
    
    def test_tangents_single_point(self):
        """Tangenti con singolo punto."""
        env = Envelope({'type': 'cubic', 'points': [[0, 5]]})

        tangents = env.segments[0].context['tangents']
        assert len(tangents) == 1
        assert tangents[0] == pytest.approx(0.0)


class TestCubicTwoPointSmoothstep:
    """
    Cubic a 2 punti: smoothstep visibile (tangenti 0,0) invece della retta.

    Con 2 soli punti l'unica informazione è la slope del segmento; assegnarla
    a entrambe le tangenti degenera in retta. Forzando le tangenti agli estremi
    a zero l'Hermite diventa lo smoothstep simmetrico v0+(v1-v0)(3s^2-2s^3):
    ease-in-out monotòno e senza overshoot.
    """

    def test_two_point_cubic_tangents_are_zero(self):
        env = Envelope({'type': 'cubic', 'points': [[0, 0], [1, 10]]})
        tangents = env.segments[0].context['tangents']
        assert tangents == pytest.approx([0.0, 0.0])

    def test_two_point_cubic_quarter_point_is_smoothstep_not_linear(self):
        env = Envelope({'type': 'cubic', 'points': [[0, 0], [1, 10]]})
        # smoothstep a s=0.25: 3*0.0625 - 2*0.015625 = 0.15625 -> 1.5625
        assert env.evaluate(0.25) == pytest.approx(1.5625)
        # ease-in: sotto la retta (che darebbe 2.5)
        assert env.evaluate(0.25) < 2.5

    def test_two_point_cubic_three_quarter_point_eases_out(self):
        env = Envelope({'type': 'cubic', 'points': [[0, 0], [1, 10]]})
        # smoothstep a s=0.75: 3*0.5625 - 2*0.421875 = 0.84375 -> 8.4375
        assert env.evaluate(0.75) == pytest.approx(8.4375)
        # ease-out: sopra la retta (che darebbe 7.5)
        assert env.evaluate(0.75) > 7.5

    def test_two_point_cubic_midpoint_unchanged(self):
        # A s=0.5 smoothstep e retta coincidono: il punto medio resta 5.0
        env = Envelope({'type': 'cubic', 'points': [[0, 0], [1, 10]]})
        assert env.evaluate(0.5) == pytest.approx(5.0)

    def test_two_point_cubic_symmetry(self):
        # Simmetria centrale: f(0.25)+f(0.75) = v0+v1
        env = Envelope({'type': 'cubic', 'points': [[0, 0], [1, 10]]})
        assert env.evaluate(0.25) + env.evaluate(0.75) == pytest.approx(10.0)

    def test_two_point_cubic_stays_within_bounds(self):
        # Nessun overshoot: valori sempre in [v0, v1]
        env = Envelope({'type': 'cubic', 'points': [[0, 0], [1, 10]]})
        for i in range(11):
            t = i / 10.0
            assert 0.0 <= env.evaluate(t) <= 10.0

    def test_two_point_cubic_endpoints_exact(self):
        env = Envelope({'type': 'cubic', 'points': [[0, 0], [1, 10]]})
        assert env.evaluate(0.0) == pytest.approx(0.0)
        assert env.evaluate(1.0) == pytest.approx(10.0)

    def test_multipoint_cubic_extrema_tangents_unchanged(self):
        # Regression: con 3+ punti le tangenti agli estremi restano la slope
        # Fritsch-Carlson (delta), NON zero.
        env = Envelope({'type': 'cubic', 'points': [[0, 0], [1, 5], [2, 10]]})
        tangents = env.segments[0].context['tangents']
        assert tangents[0] == pytest.approx(5.0)
        assert tangents[-1] == pytest.approx(5.0)


# =============================================================================
# 9. TEST GESTIONE ERRORI
# =============================================================================

class TestErrorHandling:
    """Test gestione errori."""
    
    def test_error_empty_breakpoints(self):
        """Errore con breakpoints vuoti."""
        with pytest.raises(ValueError, match="Lista breakpoints vuota"):
            Envelope([])
    
    def test_error_invalid_format(self):
        """Errore con formato non valido."""
        with pytest.raises((ValueError, TypeError)):
            Envelope("not a valid format")
    
    def test_error_invalid_dict_format(self):
        """Errore con dict senza 'points'."""
        with pytest.raises(KeyError):
            Envelope({'type': 'linear'})  # Missing 'points'
    
    def test_error_invalid_interp_type(self):
        """Errore con tipo interpolazione non valido."""
        with pytest.raises(ValueError):
            Envelope({'type': 'exponential', 'points': [[0, 0], [1, 10]]})


# =============================================================================
# 10. TEST TYPE CHECKER (is_envelope_like)
# =============================================================================

class TestTypeChecker:
    """Test metodo statico is_envelope_like()."""
    
    def test_is_envelope_like_list_of_pairs(self):
        """Lista di [t, v] è envelope-like."""
        assert Envelope.is_envelope_like([[0, 0], [1, 10]])
    
    def test_is_envelope_like_compact_format(self):
        """Formato compatto è envelope-like."""
        assert Envelope.is_envelope_like([[[0, 0], [100, 1]], 0.4, 4])
    
    def test_is_envelope_like_dict_format(self):
        """Dict format è envelope-like."""
        assert Envelope.is_envelope_like({'type': 'linear', 'points': [[0, 0], [1, 10]]})
    
    def test_is_envelope_like_single_breakpoint(self):
        """Singolo breakpoint è envelope-like."""
        assert Envelope.is_envelope_like([[0, 5]])
    
    def test_not_envelope_like_string(self):
        """String non è envelope-like."""
        assert not Envelope.is_envelope_like("envelope")
    
    def test_not_envelope_like_number(self):
        """Numero non è envelope-like."""
        assert not Envelope.is_envelope_like(42)
    
    def test_not_envelope_like_none(self):
        """None non è envelope-like."""
        assert not Envelope.is_envelope_like(None)
    
    def test_not_envelope_like_invalid_list(self):
        """Lista malformata non è envelope-like."""
        assert not Envelope.is_envelope_like([1, 2, 3])  # Non coppie


# =============================================================================
# 11. TEST BACKWARD COMPATIBILITY
# =============================================================================

class TestBackwardCompatibility:
    """Test backward compatibility con vecchi formati."""
    
    def test_legacy_format_still_works(self):
        """Vecchio formato standard funziona ancora."""
        env = Envelope([[0, 0], [0.5, 1], [1.0, 0]])
        
        assert env.evaluate(0.5) == pytest.approx(1.0)
    
    def test_dict_format_without_type(self):
        """Dict senza 'type' usa default linear."""
        env = Envelope({'points': [[0, 0], [1, 10]]})
        
        assert env.type == 'linear'
        assert env.evaluate(0.5) == pytest.approx(5.0)


# =============================================================================
# 12. TEST CASI EDGE
# =============================================================================

class TestEdgeCases:
    """Test casi edge e situazioni limite."""
    
    def test_zero_duration_segment(self):
        """Segmento con durata zero (t0 == t1)."""
        env = Envelope([[0, 10], [0, 20], [1, 30]])
        
        # Dovrebbe gestire gracefully
        result = env.evaluate(0)
        assert isinstance(result, float)
    
    def test_negative_times(self):
        """Tempi negativi nei breakpoints."""
        env = Envelope([[-1, 0], [0, 5], [1, 10]])
        
        assert env.evaluate(-1) == pytest.approx(0.0)
        assert env.evaluate(0) == pytest.approx(5.0)
    
    def test_very_small_values(self):
        """Valori molto piccoli."""
        env = Envelope([[0, 1e-10], [1, 1e-9]])
        
        result = env.evaluate(0.5)
        assert isinstance(result, float)
        assert result >= 0
    
    def test_very_large_values(self):
        """Valori molto grandi."""
        env = Envelope([[0, 1e10], [1, 1e11]])
        
        result = env.evaluate(0.5)
        assert isinstance(result, float)
    
    def test_identical_consecutive_values(self):
        """Valori identici consecutivi."""
        env = Envelope([[0, 5], [1, 5], [2, 5]])
        
        # Dovrebbe essere piatto
        assert env.evaluate(0.5) == pytest.approx(5.0)
        assert env.evaluate(1.5) == pytest.approx(5.0)
        
        # Integrate: rettangolo
        area = env.integrate(0, 2)
        assert area == pytest.approx(10.0)  # 5 * 2
    
    def test_single_value_envelope(self):
        """Envelope con singolo valore."""
        env = Envelope([[0, 42]])
        
        # Dovrebbe essere costante a 42 ovunque
        assert env.evaluate(-10) == pytest.approx(42.0)
        assert env.evaluate(0) == pytest.approx(42.0)
        assert env.evaluate(10) == pytest.approx(42.0)
        
        # Integrate
        area = env.integrate(0, 5)
        assert area == pytest.approx(210.0)  # 42 * 5
    
    def test_unsorted_breakpoints(self):
        """Breakpoints non ordinati (dovrebbero essere ordinati internamente)."""
        # EnvelopeSegment ordina automaticamente
        env = Envelope([[1, 10], [0, 0], [2, 5]])
        
        # Dovrebbe funzionare correttamente dopo ordinamento
        assert env.evaluate(0) == pytest.approx(0.0)
        assert env.evaluate(1) == pytest.approx(10.0)
        assert env.evaluate(2) == pytest.approx(5.0)


# =============================================================================
# 13. TEST INTEGRAZIONE CON ALTRI COMPONENTI
# =============================================================================

class TestIntegrationWithComponents:
    """Test integrazione con Factory e Builder."""
    
    def test_factory_integration(self):
        """Envelope usa Factory correttamente."""
        for interp_type in ['linear', 'step', 'cubic']:
            env = Envelope({'type': interp_type, 'points': [[0, 0], [1, 10]]})
            
            # Strategy dovrebbe essere del tipo giusto
            assert env.strategy is not None
            assert hasattr(env.strategy, 'evaluate')
            assert hasattr(env.strategy, 'integrate')
    
    def test_builder_integration(self):
        """Envelope usa Builder per espansione formato compatto."""
        compact = [[[0, 0], [100, 1]], 0.4, 4]
        env = Envelope(compact)
        
        # Builder dovrebbe aver espanso correttamente
        # 4 cicli * 2 punti = 8 breakpoints
        assert len(env.segments[0].breakpoints) == 8
    
    def test_segment_integration(self):
        """Envelope crea NormalSegment correttamente."""
        env = Envelope([[0, 0], [1, 10]])
        
        # Dovrebbe avere un NormalSegment
        assert len(env.segments) == 1
        segment = env.segments[0]
        
        assert hasattr(segment, 'evaluate')
        assert hasattr(segment, 'integrate')
        assert hasattr(segment, 'start_time')
        assert hasattr(segment, 'end_time')


# =============================================================================
# 14. TEST PROPRIETÀ MATEMATICHE
# =============================================================================

class TestMathematicalProperties:
    """Test proprietà matematiche dell'envelope."""
    
    def test_integrate_additive(self):
        """Proprietà additiva dell'integrale."""
        env = Envelope([[0, 0], [2, 10]])
        
        # ∫[0,2] = ∫[0,1] + ∫[1,2]
        total = env.integrate(0, 2)
        part1 = env.integrate(0, 1)
        part2 = env.integrate(1, 2)
        
        assert total == pytest.approx(part1 + part2)
    
    def test_integrate_symmetric_negative(self):
        """∫[a,b] = -∫[b,a]."""
        env = Envelope([[0, 0], [1, 10]])
        
        forward = env.integrate(0, 1)
        backward = env.integrate(1, 0)
        
        assert forward == pytest.approx(-backward)
    
    def test_evaluate_continuity(self):
        """Continuità dell'evaluate ai breakpoints."""
        env = Envelope([[0, 0], [1, 10], [2, 0]])
        
        # Valori appena prima e dopo breakpoint dovrebbero essere vicini
        eps = 1e-6
        
        for t in [1.0]:
            left = env.evaluate(t - eps)
            center = env.evaluate(t)
            right = env.evaluate(t + eps)
            
            # Verifica continuità (per linear)
            assert abs(left - center) < 0.01
            assert abs(right - center) < 0.01


