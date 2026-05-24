"""
test_envelope.py

Test suite completa per il modulo envelope.py (classe Envelope come facade).

Coverage:
1.  __init__ con breakpoints standard (lista)
2.  __init__ con formato dict
3.  __init__ con formato compatto
4.  __init__ con formato misto
5.  __init__ con input invalido
6.  __init__ estrazione tipo interpolazione
7.  _parse_segments - validazione e creazione
8.  _create_context_for_segment - linear vs cubic
9.  _compute_fritsch_carlson_tangents - algoritmo completo
10. evaluate() - delegazione a NormalSegment
11. integrate() - delegazione, inversione, intervallo nullo
12. breakpoints property - singolo segmento, multi-segmento
13. is_envelope_like() - type checker centralizzato
14. Integrazione end-to-end
"""

import pytest
import sys
import os

# Aggiungi src al path

from envelopes.envelope_builder import EnvelopeBuilder
from envelopes.envelope import Envelope
from envelopes.envelope_segment import NormalSegment
from envelopes.envelope_interpolation import (
    LinearInterpolation, StepInterpolation, CubicInterpolation
)
from envelopes.envelope_builder import EnvelopeBuilder
from unittest.mock import MagicMock


# =============================================================================
# 1. TEST __init__ CON BREAKPOINTS STANDARD
# =============================================================================

class TestEnvelopeInitStandard:
    """Test costruttore con liste standard [[t, v], ...]."""

    def test_simple_ramp(self):
        """Rampa semplice da 0 a 10."""
        env = Envelope([[0, 0], [1, 10]])
        assert len(env.segments) == 1
        assert env.type == 'linear'

    def test_triangle(self):
        """Envelope triangolare con 3 breakpoints."""
        env = Envelope([[0, 0], [5, 100], [10, 0]])
        assert len(env.segments) == 1
        assert len(env.breakpoints) == 3

    def test_single_breakpoint(self):
        """Singolo breakpoint: valore costante."""
        env = Envelope([[0, 42]])
        assert env.evaluate(0.0) == pytest.approx(42.0)
        assert env.evaluate(100.0) == pytest.approx(42.0)

    def test_many_breakpoints(self):
        """Molti breakpoints preservati."""
        points = [[i, i * 10] for i in range(20)]
        env = Envelope(points)
        assert len(env.breakpoints) == 20

    def test_preserves_values(self):
        """I valori dei breakpoints sono preservati esattamente."""
        env = Envelope([[0, 3.14], [1, 2.71], [2, 1.41]])
        assert env.breakpoints[0][1] == pytest.approx(3.14)
        assert env.breakpoints[1][1] == pytest.approx(2.71)
        assert env.breakpoints[2][1] == pytest.approx(1.41)

    def test_default_type_is_linear(self):
        """Tipo default e' 'linear' per liste standard."""
        env = Envelope([[0, 0], [1, 1]])
        assert env.type == 'linear'

    def test_strategy_is_linear(self):
        """Strategy assegnata e' LinearInterpolation."""
        env = Envelope([[0, 0], [1, 1]])
        assert isinstance(env.strategy, LinearInterpolation)

    def test_negative_values(self):
        """Breakpoints con valori negativi."""
        env = Envelope([[0, -50], [1, 50]])
        assert env.evaluate(0.0) == pytest.approx(-50.0)
        assert env.evaluate(0.5) == pytest.approx(0.0)
        assert env.evaluate(1.0) == pytest.approx(50.0)

    def test_zero_duration_envelope(self):
        """Due breakpoints allo stesso tempo."""
        env = Envelope([[5, 10], [5, 20]])
        # Deve creare senza errori
        assert env.segments[0].duration == 0.0


# =============================================================================
# 2. TEST __init__ CON FORMATO DICT
# =============================================================================

class TestEnvelopeInitDict:
    """Test costruttore con formato dict."""

    def test_dict_with_type_cubic(self):
        """Dict con type='cubic' usa CubicInterpolation."""
        env = Envelope({
            'type': 'cubic',
            'points': [[0, 0], [5, 50], [10, 100]]
        })
        assert env.type == 'cubic'
        assert isinstance(env.strategy, CubicInterpolation)

    def test_dict_with_type_step(self):
        """Dict con type='step' usa StepInterpolation."""
        env = Envelope({
            'type': 'step',
            'points': [[0, 0], [5, 50], [10, 100]]
        })
        assert env.type == 'step'
        assert isinstance(env.strategy, StepInterpolation)

    def test_dict_with_type_linear(self):
        """Dict con type='linear' usa LinearInterpolation."""
        env = Envelope({
            'type': 'linear',
            'points': [[0, 0], [1, 10]]
        })
        assert env.type == 'linear'
        assert isinstance(env.strategy, LinearInterpolation)

    def test_dict_default_type_is_linear(self):
        """Dict senza 'type' usa default 'linear'."""
        env = Envelope({
            'points': [[0, 0], [1, 10]]
        })
        assert env.type == 'linear'

    def test_dict_with_compact_points(self):
        """Dict con points in formato compatto."""
        env = Envelope({
            'type': 'linear',
            'points': [[[0, 0], [100, 1]], 0.4, 4]
        })
        # 4 ripetizioni * 2 punti = 8 breakpoints espansi
        assert len(env.breakpoints) == 8

    def test_dict_preserves_breakpoint_values(self):
        """Dict preserva i valori dei breakpoints."""
        env = Envelope({
            'type': 'linear',
            'points': [[0, 42], [10, 99]]
        })
        assert env.breakpoints[0][1] == 42
        assert env.breakpoints[1][1] == 99


# =============================================================================
# 3. TEST __init__ CON FORMATO COMPATTO
# =============================================================================

class TestEnvelopeInitCompact:
    """Test costruttore con formato compatto diretto."""

    def test_compact_creates_correct_breakpoints(self):
        """Formato compatto espande correttamente."""
        env = Envelope([[[0, 0], [100, 1]], 0.4, 4])
        assert len(env.breakpoints) == 8

    def test_compact_with_interp_type(self):
        """Compatto con 4 elementi estrae tipo interpolazione."""
        env = Envelope([[[0, 0], [100, 1]], 0.4, 4, 'cubic'])
        assert env.type == 'cubic'
        assert isinstance(env.strategy, CubicInterpolation)

    def test_compact_without_interp_defaults_linear(self):
        """Compatto senza tipo usa default 'linear'."""
        env = Envelope([[[0, 0], [100, 1]], 0.2, 2])
        assert env.type == 'linear'

    def test_compact_single_rep(self):
        """Compatto con 1 ripetizione."""
        env = Envelope([[[0, 0], [100, 10]], 1.0, 1])
        assert len(env.breakpoints) == 2
        assert env.breakpoints[0] == pytest.approx([0.0, 0])
        assert env.breakpoints[1] == pytest.approx([1.0, 10])

    def test_compact_time_range(self):
        """I tempi espansi coprono il total_time."""
        env = Envelope([[[0, 0], [100, 1]], 2.0, 5])
        assert env.breakpoints[0][0] == pytest.approx(0.0)
        assert env.breakpoints[-1][0] <= 2.0


# =============================================================================
# 4. TEST __init__ CON FORMATO MISTO
# =============================================================================

class TestEnvelopeInitMixed:
    """Test costruttore con formato misto (compatto + standard)."""

    def test_mixed_format(self):
        """Compatto dentro lista con breakpoints standard."""
        env = Envelope([
            [[[0, 0], [100, 1]], 0.2, 2],
            [1.0, 0]
        ])
        # 2 cicli * 2 punti = 4 compatti + 1 standard = 5
        assert len(env.breakpoints) == 5

    def test_mixed_preserves_standard_points(self):
        """Standard breakpoints dopo compatto sono preservati."""
        env = Envelope([
            [[[0, 0], [100, 10]], 0.5, 1],
            [1.0, 0]
        ])
        # Ultimo breakpoint deve essere [1.0, 0]
        assert env.breakpoints[-1] == pytest.approx([1.0, 0])


# =============================================================================
# 5. TEST __init__ CON INPUT INVALIDO
# =============================================================================

class TestEnvelopeInitInvalid:
    """Test costruttore con input non validi."""

    def test_string_raises_valueerror(self):
        """Stringa come input solleva ValueError."""
        with pytest.raises(ValueError, match="Formato envelope non valido"):
            Envelope("not_an_envelope")

    def test_number_raises_valueerror(self):
        """Numero come input solleva ValueError."""
        with pytest.raises(ValueError, match="Formato envelope non valido"):
            Envelope(42)

    def test_none_raises_valueerror(self):
        """None come input solleva ValueError."""
        with pytest.raises(ValueError, match="Formato envelope non valido"):
            Envelope(None)

    def test_bool_raises_valueerror(self):
        """Bool come input solleva ValueError."""
        with pytest.raises(ValueError, match="Formato envelope non valido"):
            Envelope(True)

    def test_tuple_raises_valueerror(self):
        """Tupla come input solleva ValueError."""
        with pytest.raises(ValueError, match="Formato envelope non valido"):
            Envelope((0, 1))

    def test_empty_list_raises(self):
        """Lista vuota solleva ValueError."""
        with pytest.raises(ValueError):
            Envelope([])


# =============================================================================
# 6. TEST ESTRAZIONE TIPO INTERPOLAZIONE
# =============================================================================

class TestEnvelopeTypeExtraction:
    """Test che il tipo venga estratto correttamente da tutti i formati."""

    def test_list_no_compact_defaults_linear(self):
        """Lista standard senza compatto -> 'linear'."""
        env = Envelope([[0, 0], [1, 1]])
        assert env.type == 'linear'

    def test_compact_with_step(self):
        """Compatto con tipo 'step' viene estratto."""
        env = Envelope([[[0, 0], [100, 1]], 1.0, 1, 'step'])
        assert env.type == 'step'

    def test_compact_in_list_with_type(self):
        """Compatto annidato in lista con tipo viene estratto."""
        env = Envelope([
            [0, 0],
            [[[0, 5], [100, 10]], 0.5, 1, 'cubic'],
            [1, 0]
        ])
        assert env.type == 'cubic'

    def test_dict_type_overrides(self):
        """Il tipo dal dict ha precedenza."""
        env = Envelope({
            'type': 'step',
            'points': [[0, 0], [1, 1]]
        })
        assert env.type == 'step'


# =============================================================================
# 7. TEST _parse_segments
# =============================================================================

class TestParseSegments:
    """Test metodo _parse_segments (validazione interna)."""

    def test_creates_single_normal_segment(self):
        """Crea esattamente un NormalSegment."""
        env = Envelope([[0, 0], [1, 10]])
        assert len(env.segments) == 1
        assert isinstance(env.segments[0], NormalSegment)

    def test_segment_has_correct_bounds(self):
        """Il segmento ha start_time e end_time corretti."""
        env = Envelope([[2, 0], [5, 10], [8, 0]])
        seg = env.segments[0]
        assert seg.start_time == pytest.approx(2.0)
        assert seg.end_time == pytest.approx(8.0)

    def test_segment_has_strategy(self):
        """Il segmento ha la strategy dell'envelope."""
        env = Envelope([[0, 0], [1, 1]])
        assert env.segments[0].strategy is env.strategy

    def test_invalid_breakpoint_format_raises(self):
        """Breakpoint con formato invalido solleva ValueError.

        Nota: questo puo' accadere se il Builder produce output inatteso
        o se si chiama _parse_segments direttamente con dati malformati.
        """
        env = Envelope([[0, 0], [1, 1]])
        with pytest.raises(ValueError, match="Formato breakpoint non valido"):
            env._parse_segments([[0, 1, 2]])  # 3 elementi

    def test_invalid_breakpoint_string_raises(self):
        """Breakpoint non-lista solleva ValueError."""
        env = Envelope([[0, 0], [1, 1]])
        with pytest.raises(ValueError, match="Formato breakpoint non valido"):
            env._parse_segments(["not_a_breakpoint"])

    def test_empty_breakpoints_raises(self):
        """Lista vuota di breakpoints solleva ValueError."""
        env = Envelope([[0, 0], [1, 1]])
        with pytest.raises(ValueError, match="Lista breakpoints vuota"):
            env._parse_segments([])


# =============================================================================
# 8. TEST _create_context_for_segment
# =============================================================================

class TestCreateContextForSegment:
    """Test creazione context (tangenti per cubic, vuoto per altri)."""

    def test_linear_returns_empty_context(self):
        """Per tipo 'linear' il context e' vuoto."""
        env = Envelope([[0, 0], [1, 10]])
        context = env._create_context_for_segment([[0, 0], [1, 10]])
        assert context == {}

    def test_step_returns_empty_context(self):
        """Per tipo 'step' il context e' vuoto."""
        env = Envelope({'type': 'step', 'points': [[0, 0], [1, 10]]})
        context = env._create_context_for_segment([[0, 0], [1, 10]])
        assert context == {}

    def test_cubic_returns_tangents(self):
        """Per tipo 'cubic' il context contiene 'tangents'."""
        env = Envelope({
            'type': 'cubic',
            'points': [[0, 0], [5, 50], [10, 100]]
        })
        context = env._create_context_for_segment([[0, 0], [5, 50], [10, 100]])
        assert 'tangents' in context
        assert len(context['tangents']) == 3

    def test_cubic_context_stored_in_segment(self):
        """Tangenti cubic sono effettivamente nel segmento."""
        env = Envelope({
            'type': 'cubic',
            'points': [[0, 0], [5, 50], [10, 100]]
        })
        seg = env.segments[0]
        assert 'tangents' in seg.context
        assert isinstance(seg.context['tangents'], list)


# =============================================================================
# 9. TEST _compute_fritsch_carlson_tangents
# =============================================================================

class TestFritschCarlsonTangents:
    """Test algoritmo Fritsch-Carlson per tangenti cubic."""

    def _make_cubic_env(self, points):
        """Helper per creare envelope cubic e accedere al metodo."""
        env = Envelope({'type': 'cubic', 'points': points})
        return env

    def test_single_point_returns_zero(self):
        """Un solo punto -> tangente [0.0]."""
        env = self._make_cubic_env([[0, 0], [1, 1]])  # servono almeno 2 per init
        tangents = env._compute_fritsch_carlson_tangents([[5, 42]])
        assert tangents == [0.0]

    def test_empty_points_returns_empty(self):
        """Zero punti -> lista vuota."""
        env = self._make_cubic_env([[0, 0], [1, 1]])
        tangents = env._compute_fritsch_carlson_tangents([])
        assert tangents == []

    def test_two_points_linear(self):
        """Due punti: tangente iniziale = tangente finale = pendenza."""
        env = self._make_cubic_env([[0, 0], [10, 100]])
        tangents = env._compute_fritsch_carlson_tangents([[0, 0], [10, 100]])
        # Pendenza = 100/10 = 10
        assert tangents[0] == pytest.approx(10.0)
        assert tangents[1] == pytest.approx(10.0)

    def test_three_points_monotone_increasing(self):
        """Tre punti monotoni crescenti: tangenti interne non-zero."""
        points = [[0, 0], [5, 50], [10, 100]]
        env = self._make_cubic_env(points)
        tangents = env._compute_fritsch_carlson_tangents(points)

        assert len(tangents) == 3
        # Pendenze: 10.0 e 10.0 -> media armonica = 10.0
        assert tangents[0] == pytest.approx(10.0)
        assert tangents[1] == pytest.approx(10.0)
        assert tangents[2] == pytest.approx(10.0)

    def test_sign_change_gives_zero_tangent(self):
        """Cambio di segno nelle pendenze -> tangente interna = 0."""
        # Sale poi scende: punto critico al picco
        points = [[0, 0], [5, 100], [10, 0]]
        env = self._make_cubic_env(points)
        tangents = env._compute_fritsch_carlson_tangents(points)

        # Al punto 1 (picco): d_left=+20, d_right=-20 -> segni opposti -> 0
        assert tangents[1] == pytest.approx(0.0)

    def test_harmonic_mean_different_slopes(self):
        """Pendenze diverse ma stesso segno: media armonica ponderata."""
        # Pendenza 1: (20-0)/(5-0) = 4
        # Pendenza 2: (100-20)/(10-5) = 16
        # Media armonica: 2 / (1/4 + 1/16) = 2 / 0.3125 = 6.4
        points = [[0, 0], [5, 20], [10, 100]]
        env = self._make_cubic_env(points)
        tangents = env._compute_fritsch_carlson_tangents(points)

        assert tangents[1] == pytest.approx(6.4)

    def test_zero_duration_segment_gives_zero_delta(self):
        """Segmento con dt=0 produce delta=0."""
        points = [[0, 0], [0, 10], [5, 50]]
        env = self._make_cubic_env([[0, 0], [5, 50]])
        tangents = env._compute_fritsch_carlson_tangents(points)

        # Prima delta: dt=0 -> delta=0
        # Seconda delta: (50-10)/5 = 8
        # Punto 1: d_left=0, d_right=8 -> 0*8=0 <= 0 -> tangente 0
        assert tangents[1] == pytest.approx(0.0)

    def test_flat_region(self):
        """Regione piatta: tutte le tangenti = 0."""
        points = [[0, 10], [5, 10], [10, 10]]
        env = self._make_cubic_env(points)
        tangents = env._compute_fritsch_carlson_tangents(points)

        # Pendenze: 0, 0 -> tangenti: 0, 0, 0
        assert all(t == pytest.approx(0.0) for t in tangents)

    def test_four_points_mixed(self):
        """Quattro punti con monotonia mista: verifica correttezza."""
        # Sale, piatto, scende
        points = [[0, 0], [3, 30], [7, 30], [10, 0]]
        env = self._make_cubic_env(points)
        tangents = env._compute_fritsch_carlson_tangents(points)

        assert len(tangents) == 4
        # Punto 0: tangente iniziale = pendenza primo segmento = 10
        assert tangents[0] == pytest.approx(10.0)
        # Punto 1: d_left=10, d_right=0 -> prodotto=0 -> tangente=0
        assert tangents[1] == pytest.approx(0.0)
        # Punto 2: d_left=0, d_right=-10 -> prodotto=0 -> tangente=0
        assert tangents[2] == pytest.approx(0.0)
        # Punto 3: tangente finale = pendenza ultimo segmento = -10
        assert tangents[3] == pytest.approx(-10.0)

    def test_negative_slopes(self):
        """Pendenze negative: tangenti negative."""
        points = [[0, 100], [10, 0]]
        env = self._make_cubic_env([[0, 100], [10, 0]])
        tangents = env._compute_fritsch_carlson_tangents(points)

        assert tangents[0] == pytest.approx(-10.0)
        assert tangents[1] == pytest.approx(-10.0)

    def test_many_points_all_tangents_computed(self):
        """Con molti punti, ogni punto ottiene una tangente."""
        n = 50
        points = [[i, i ** 2] for i in range(n)]
        env = self._make_cubic_env([[0, 0], [1, 1]])
        tangents = env._compute_fritsch_carlson_tangents(points)

        assert len(tangents) == n
        # Tutte le tangenti devono essere finite
        assert all(abs(t) < 1e10 for t in tangents)


# =============================================================================
# 10. TEST evaluate()
# =============================================================================

class TestEnvelopeEvaluate:
    """Test evaluate() - delegazione al NormalSegment."""

    def test_evaluate_at_breakpoints(self):
        """Evaluate ai breakpoints restituisce valori esatti."""
        env = Envelope([[0, 0], [5, 50], [10, 100]])
        assert env.evaluate(0) == pytest.approx(0.0)
        assert env.evaluate(5) == pytest.approx(50.0)
        assert env.evaluate(10) == pytest.approx(100.0)

    def test_evaluate_linear_interpolation(self):
        """Interpolazione lineare tra breakpoints."""
        env = Envelope([[0, 0], [10, 100]])
        assert env.evaluate(2.5) == pytest.approx(25.0)
        assert env.evaluate(7.5) == pytest.approx(75.0)

    def test_evaluate_hold_before(self):
        """Hold primo valore prima dell'inizio."""
        env = Envelope([[5, 42], [10, 100]])
        assert env.evaluate(0) == pytest.approx(42.0)
        assert env.evaluate(-100) == pytest.approx(42.0)

    def test_evaluate_hold_after(self):
        """Hold ultimo valore dopo la fine."""
        env = Envelope([[0, 0], [5, 42]])
        assert env.evaluate(10) == pytest.approx(42.0)
        assert env.evaluate(1000) == pytest.approx(42.0)

    def test_evaluate_step(self):
        """Evaluate con strategia step."""
        env = Envelope({'type': 'step', 'points': [[0, 10], [5, 20]]})
        assert env.evaluate(0) == pytest.approx(10.0)
        assert env.evaluate(2.5) == pytest.approx(10.0)
        assert env.evaluate(5) == pytest.approx(20.0)

    def test_evaluate_cubic(self):
        """Evaluate con strategia cubic produce valori ragionevoli."""
        env = Envelope({
            'type': 'cubic',
            'points': [[0, 0], [5, 50], [10, 100]]
        })
        # Ai breakpoints deve essere esatto
        assert env.evaluate(0) == pytest.approx(0.0)
        assert env.evaluate(5) == pytest.approx(50.0)
        assert env.evaluate(10) == pytest.approx(100.0)
        # A meta' deve essere ragionevole (non fuori range)
        mid = env.evaluate(2.5)
        assert 0 <= mid <= 100

    def test_evaluate_compact_envelope(self):
        """Evaluate su envelope creato da formato compatto."""
        env = Envelope([[[0, 0], [100, 100]], 1.0, 1])
        assert env.evaluate(0.0) == pytest.approx(0.0)
        assert env.evaluate(0.5) == pytest.approx(50.0)
        assert env.evaluate(1.0) == pytest.approx(100.0)


# =============================================================================
# 11. TEST integrate()
# =============================================================================

class TestEnvelopeIntegrate:
    """Test integrate() - delegazione con logica di inversione."""

    def test_integrate_linear_ramp(self):
        """Integrale di rampa lineare: area triangolo."""
        env = Envelope([[0, 0], [10, 10]])
        area = env.integrate(0, 10)
        assert area == pytest.approx(50.0)  # (10 * 10) / 2

    def test_integrate_constant(self):
        """Integrale di valore costante: rettangolo."""
        env = Envelope([[0, 5], [10, 5]])
        area = env.integrate(0, 10)
        assert area == pytest.approx(50.0)  # 5 * 10

    def test_integrate_partial(self):
        """Integrale parziale."""
        env = Envelope([[0, 0], [10, 10]])
        area = env.integrate(0, 5)
        # Trapezio: base=5, h1=0, h2=5 -> area = 12.5
        assert area == pytest.approx(12.5)

    def test_integrate_inverted_interval(self):
        """from_time > to_time: restituisce negativo."""
        env = Envelope([[0, 0], [10, 10]])
        area_forward = env.integrate(0, 10)
        area_backward = env.integrate(10, 0)
        assert area_backward == pytest.approx(-area_forward)

    def test_integrate_equal_times(self):
        """from_time == to_time: restituisce 0."""
        env = Envelope([[0, 0], [10, 10]])
        assert env.integrate(5, 5) == pytest.approx(0.0)

    def test_integrate_before_envelope(self):
        """Integrale prima dell'envelope: hold del primo valore."""
        env = Envelope([[5, 10], [10, 10]])
        area = env.integrate(0, 5)
        # Hold valore 10 per 5 secondi = 50
        assert area == pytest.approx(50.0)

    def test_integrate_after_envelope(self):
        """Integrale dopo l'envelope: hold dell'ultimo valore."""
        env = Envelope([[0, 0], [5, 10]])
        area = env.integrate(5, 10)
        # Hold valore 10 per 5 secondi = 50
        assert area == pytest.approx(50.0)

    def test_integrate_spanning_entire_range(self):
        """Integrale che copre prima + dentro + dopo."""
        env = Envelope([[2, 0], [4, 10]])
        # Prima (0-2): hold 0 -> 0
        # Dentro (2-4): triangolo -> 10
        # Dopo (4-6): hold 10 * 2 = 20
        # Totale: 30
        area = env.integrate(0, 6)
        assert area == pytest.approx(30.0)

    def test_integrate_triangle(self):
        """Integrale di triangolo: salita + discesa."""
        env = Envelope([[0, 0], [5, 10], [10, 0]])
        area = env.integrate(0, 10)
        # Due triangoli: 25 + 25 = 50
        assert area == pytest.approx(50.0)


# =============================================================================
# 12. TEST breakpoints PROPERTY
# =============================================================================

class TestBreakpointsProperty:
    """Test property breakpoints (backward compatibility)."""

    def test_single_segment_returns_breakpoints(self):
        """Singolo segmento: ritorna breakpoints del segmento."""
        env = Envelope([[0, 0], [5, 50], [10, 100]])
        bp = env.breakpoints
        assert len(bp) == 3
        assert bp[0] == pytest.approx([0, 0])
        assert bp[2] == pytest.approx([10, 100])

    def test_breakpoints_are_sorted(self):
        """I breakpoints sono ordinati per tempo."""
        env = Envelope([[10, 100], [0, 0], [5, 50]])
        bp = env.breakpoints
        assert bp[0][0] <= bp[1][0] <= bp[2][0]

    def test_breakpoints_match_evaluate(self):
        """I breakpoints restituiti sono coerenti con evaluate()."""
        env = Envelope([[0, 10], [5, 50], [10, 90]])
        for t, v in env.breakpoints:
            assert env.evaluate(t) == pytest.approx(v)

    def test_multi_segment_concatenation(self):
        """Multi-segmento (simulato): breakpoints concatenati.

        Nota: attualmente _parse_segments crea sempre 1 segmento.
        Testiamo il percorso multi-segmento forzando segments manualmente.
        """
        env = Envelope([[0, 0], [1, 1]])
        # Simula multi-segmento
        seg2 = NormalSegment([[2, 2], [3, 3]], LinearInterpolation())
        env.segments.append(seg2)

        bp = env.breakpoints
        assert len(bp) == 4
        assert bp[0] == [0, 0]
        assert bp[1] == [1, 1]
        assert bp[2] == [2, 2]
        assert bp[3] == [3, 3]


# =============================================================================
# 13. TEST is_envelope_like() - TYPE CHECKER CENTRALIZZATO
# =============================================================================

class TestIsEnvelopeLike:
    """Test metodo statico is_envelope_like() - tutti i percorsi."""

    # --- True cases ---

    def test_envelope_instance(self):
        """Istanza di Envelope -> True."""
        env = Envelope([[0, 0], [1, 1]])
        assert Envelope.is_envelope_like(env) is True

    def test_standard_breakpoints_list(self):
        """Lista di breakpoints [[t, v], ...] -> True."""
        assert Envelope.is_envelope_like([[0, 0], [1, 1]]) is True

    def test_single_breakpoint(self):
        """Lista con un solo breakpoint -> True."""
        assert Envelope.is_envelope_like([[0, 42]]) is True

    def test_compact_format_direct(self):
        """Formato compatto diretto -> True."""
        assert Envelope.is_envelope_like(
            [[[0, 0], [100, 1]], 0.4, 4]
        ) is True

    def test_compact_with_interp(self):
        """Formato compatto con tipo interpolazione -> True."""
        assert Envelope.is_envelope_like(
            [[[0, 0], [100, 1]], 0.4, 4, 'cubic']
        ) is True

    def test_compact_inside_list(self):
        """Formato compatto annidato in una lista -> True."""
        assert Envelope.is_envelope_like([
            [[[0, 0], [100, 1]], 0.2, 2],
            [1, 0]
        ]) is True

    def test_dict_with_points(self):
        """Dict con chiave 'points' -> True."""
        assert Envelope.is_envelope_like({
            'type': 'linear',
            'points': [[0, 0], [1, 1]]
        }) is True

    def test_dict_with_only_points(self):
        """Dict con solo 'points' -> True."""
        assert Envelope.is_envelope_like({'points': [[0, 0]]}) is True

    def test_mixed_format(self):
        """Formato misto (compatto + standard) -> True."""
        assert Envelope.is_envelope_like([
            [0, 0],
            [[[0, 5], [100, 10]], 0.5, 1],
            [1, 0]
        ]) is True

    # --- False cases ---

    def test_empty_list(self):
        """Lista vuota -> False."""
        assert Envelope.is_envelope_like([]) is False

    def test_none(self):
        """None -> False."""
        assert Envelope.is_envelope_like(None) is False

    def test_number_int(self):
        """Intero -> False."""
        assert Envelope.is_envelope_like(42) is False

    def test_number_float(self):
        """Float -> False."""
        assert Envelope.is_envelope_like(3.14) is False

    def test_string(self):
        """Stringa -> False."""
        assert Envelope.is_envelope_like("hanning") is False

    def test_bool_true(self):
        """True -> False."""
        assert Envelope.is_envelope_like(True) is False

    def test_bool_false(self):
        """False -> False."""
        assert Envelope.is_envelope_like(False) is False

    def test_dict_without_points(self):
        """Dict senza chiave 'points' -> False."""
        assert Envelope.is_envelope_like({'type': 'linear'}) is False

    def test_empty_dict(self):
        """Dict vuoto -> False."""
        assert Envelope.is_envelope_like({}) is False

    def test_list_of_strings(self):
        """Lista di stringhe -> False."""
        assert Envelope.is_envelope_like(["a", "b", "c"]) is False

    def test_list_of_single_values(self):
        """Lista di numeri singoli (non breakpoints) -> False."""
        assert Envelope.is_envelope_like([1, 2, 3]) is False

    def test_list_of_triples(self):
        """Lista di triple (non breakpoints [t,v]) -> False."""
        assert Envelope.is_envelope_like([[0, 1, 2], [3, 4, 5]]) is False

    def test_tuple(self):
        """Tupla -> False."""
        assert Envelope.is_envelope_like((0, 1)) is False

    def test_set(self):
        """Set -> False."""
        assert Envelope.is_envelope_like({1, 2, 3}) is False


# =============================================================================
# 14. TEST INTEGRAZIONE END-TO-END
# =============================================================================

class TestEnvelopeEndToEnd:
    """Test di integrazione che verificano l'intero flusso."""

    def test_linear_ramp_full_flow(self):
        """Flusso completo: crea, valuta, integra rampa lineare."""
        env = Envelope([[0, 0], [10, 100]])

        # Evaluate
        assert env.evaluate(0) == pytest.approx(0)
        assert env.evaluate(5) == pytest.approx(50)
        assert env.evaluate(10) == pytest.approx(100)

        # Integrate
        assert env.integrate(0, 10) == pytest.approx(500)

        # Metadata
        assert env.type == 'linear'
        assert len(env.segments) == 1

    def test_cubic_full_flow(self):
        """Flusso completo cubic: crea con tangenti, valuta, integra."""
        env = Envelope({
            'type': 'cubic',
            'points': [[0, 0], [5, 50], [10, 100]]
        })

        # Ai breakpoints esatto
        assert env.evaluate(0) == pytest.approx(0)
        assert env.evaluate(10) == pytest.approx(100)

        # Tangenti calcolate
        assert 'tangents' in env.segments[0].context
        assert len(env.segments[0].context['tangents']) == 3

        # Integrale ragionevole (dovrebbe essere ~500 per rampa lineare,
        # cubic con tangenti uniformi e' quasi uguale)
        area = env.integrate(0, 10)
        assert 400 < area < 600

    def test_step_full_flow(self):
        """Flusso completo step: valori mantenuti fino al prossimo."""
        env = Envelope({
            'type': 'step',
            'points': [[0, 10], [5, 20], [10, 30]]
        })

        # Step: mantiene il valore a sinistra
        assert env.evaluate(0) == pytest.approx(10)
        assert env.evaluate(2.5) == pytest.approx(10)
        assert env.evaluate(5) == pytest.approx(20)
        assert env.evaluate(7.5) == pytest.approx(20)
        assert env.evaluate(10) == pytest.approx(30)

    def test_compact_to_evaluate(self):
        """Da formato compatto a evaluate: coerenza."""
        env = Envelope([[[0, 0], [100, 100]], 2.0, 2])

        # Primo ciclo: 0->1s
        assert env.evaluate(0.0) == pytest.approx(0.0)
        assert env.evaluate(1.0) == pytest.approx(100.0)

        # Secondo ciclo inizia con discontinuita'
        # Il valore al tempo 1.0+epsilon torna a 0
        eps = EnvelopeBuilder.DISCONTINUITY_OFFSET
        # Appena dopo la discontinuita' il valore e' ~0
        val = env.evaluate(1.0 + eps)
        assert val == pytest.approx(0.0, abs=1.0)

    def test_is_envelope_like_round_trip(self):
        """is_envelope_like identifica correttamente un Envelope creato."""
        env = Envelope([[0, 0], [1, 1]])
        assert Envelope.is_envelope_like(env) is True

        # E identifica i raw data usati per crearlo
        assert Envelope.is_envelope_like([[0, 0], [1, 1]]) is True

    def test_dict_cubic_tangent_correctness(self):
        """Cubic con rampa perfettamente lineare: tangenti = pendenza."""
        env = Envelope({
            'type': 'cubic',
            'points': [[0, 0], [5, 50], [10, 100]]
        })
        tangents = env.segments[0].context['tangents']
        # Pendenza uniforme = 10 -> tutte le tangenti devono essere ~10
        for t in tangents:
            assert t == pytest.approx(10.0)

    def test_evaluate_consistency_with_integrate(self):
        """Integrale di costante = valore * durata."""
        env = Envelope([[0, 7], [10, 7]])
        assert env.integrate(0, 10) == pytest.approx(70.0)
        assert env.evaluate(5) == pytest.approx(7.0)



# =============================================================================
# TEST RIGHE MANCANTI: 79, 303, 399
# =============================================================================

class TestEnvelopeMissingLines:
    """Copre le righe 79, 303, 399 di envelope.py."""

    def test_invalid_input_type_raises(self):
        """
        Riga 79: raise ValueError quando breakpoints non e' ne' list ne' dict.
        Il ramo else del costruttore.
        """
        with pytest.raises(ValueError, match="Formato envelope non valido"):
            Envelope(42)  # intero: non e' list ne' dict

    def test_invalid_input_string_raises(self):
        """Riga 79: stringa come input non valido."""
        with pytest.raises(ValueError, match="Formato envelope non valido"):
            Envelope("not_valid")

    def test_scale_raw_values_y_unsupported_type_raises(self):
        """
        Riga 399: raise ValueError in _scale_raw_values_y con tipo non supportato.
        Passare un tipo che non e' ne' list ne' dict.
        """
        with pytest.raises(ValueError, match="Formato non supportato"):
            Envelope._scale_raw_values_y(42.0, 2.0)  # float diretto: non supportato

    def test_scale_raw_values_y_unsupported_string_raises(self):
        """Riga 399: stringa come raw_data non supportata."""
        with pytest.raises(ValueError, match="Formato non supportato"):
            Envelope._scale_raw_values_y("invalid", 2.0)

    def test_breakpoints_multi_segment_concatenation(self):
        """
        Riga 303: path multi-segmento nella property breakpoints.
        Serve un Envelope con len(self.segments) > 1.

        NOTA: se il tuo sistema attuale non produce mai multi-segmento,
        puoi coprire questa riga forzando manualmente segments con mock.
        """

        env = Envelope([[0, 0], [1, 10]])

        # Forza due segmenti artificiali con breakpoints diversi
        seg1 = MagicMock()
        seg1.breakpoints = [[0, 0], [0.5, 5]]
        seg2 = MagicMock()
        seg2.breakpoints = [[0.5, 5], [1.0, 10]]

        env.segments = [seg1, seg2]

        bps = env.breakpoints  # deve concatenare via il loop alla riga 303

        # Dedup boundary condiviso: [0.5, 5] appare solo 1 volta
        assert len(bps) == 3
        assert bps[0] == [0, 0]
        assert bps[1] == [0.5, 5]
        assert bps[2] == [1.0, 10]

    def test_empty_segments_after_parse_raises(self):
        """
        Riga 79: raise ValueError se self.segments e' vuoto dopo _parse_segments.
        """
        from unittest.mock import patch

        with patch.object(Envelope, '_parse_segments', return_value=[]):
            with pytest.raises(ValueError, match="almeno un breakpoint"):
                Envelope([[0, 0], [1, 1]])