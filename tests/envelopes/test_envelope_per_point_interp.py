"""
Test suite per envelope con interp type per-punto (issue #54).

Formato:
- Lista 3-tuple: [[t, v, type], ...] dove type ∈ {linear, cubic, step}
- Dict per-punto: {type: ..., points: [{t, v, type}, ...]}

Semantica: type su punto i = strategia segmento i → i+1.
Ultimo punto: type ignorato (warning).
"""

import pytest
from pge.envelopes.envelope import Envelope, create_scaled_envelope, _scale_time_recursive
from pge.envelopes.envelope_builder import EnvelopeBuilder
from pge.shared.exceptions import InvalidFieldValueError


class TestThreeTupleAcceptance:
    """Costruttore accetta breakpoint 3-tuple [t, v, type]."""

    def test_simple_3tuple_does_not_raise(self):
        Envelope([[0, 0, 'cubic'], [1, 1]])

    def test_mixed_2_and_3_tuple_does_not_raise(self):
        Envelope([[0, 0, 'cubic'], [0.5, 1], [1, 0, 'step']])

    def test_all_3tuple_does_not_raise(self):
        Envelope([[0, 0, 'linear'], [0.5, 1, 'step'], [1, 0, 'cubic']])


class TestInvalidInterpType:
    """Validazione type per-punto."""

    def test_invalid_type_raises_invalid_field_value_error(self):
        with pytest.raises(InvalidFieldValueError):
            Envelope([[0, 0, 'foo'], [1, 1]])

    def test_invalid_type_error_message_lists_valid_types(self):
        with pytest.raises(InvalidFieldValueError) as exc:
            Envelope([[0, 0, 'bezier'], [1, 1]])
        assert 'linear' in exc.value.hint
        assert 'cubic' in exc.value.hint
        assert 'step' in exc.value.hint


class TestParserDisambiguation:
    """Disambiguazione tra compact format e 3-tuple breakpoint."""

    def test_3tuple_not_recognized_as_compact(self):
        assert EnvelopeBuilder._is_compact_format([0.5, 1.0, 'cubic']) is False

    def test_compact_not_recognized_as_3tuple(self):
        assert EnvelopeBuilder._is_3tuple_breakpoint(
            [[[0, 0], [100, 1]], 0.4, 4]
        ) is False

    def test_compact_still_recognized(self):
        assert EnvelopeBuilder._is_compact_format(
            [[[0, 0], [100, 1]], 0.4, 4]
        ) is True

    def test_3tuple_recognized(self):
        assert EnvelopeBuilder._is_3tuple_breakpoint([0.5, 1.0, 'cubic']) is True

    def test_2elem_not_3tuple(self):
        assert EnvelopeBuilder._is_3tuple_breakpoint([0.5, 1.0]) is False

    def test_invalid_2elem_with_string_raises(self):
        # Forma vietata: [0.5, 'cubic'] — elem[1] non numerico
        with pytest.raises(ValueError):
            Envelope([[0.5, 'cubic'], [1, 1]])

    def test_compact_4elem_not_3tuple(self):
        # Compact con interp: 4 elem → non confondibile con 3-tuple
        item = [[[0, 0], [100, 1]], 0.4, 4, 'cubic']
        assert EnvelopeBuilder._is_compact_format(item) is True
        assert EnvelopeBuilder._is_3tuple_breakpoint(item) is False

    def test_compact_5elem_not_3tuple(self):
        # Compact con time_dist: 5 elem
        item = [[[0, 0], [100, 1]], 0.4, 4, 'cubic', 'exponential']
        assert EnvelopeBuilder._is_compact_format(item) is True
        assert EnvelopeBuilder._is_3tuple_breakpoint(item) is False

    def test_3tuple_with_negative_time(self):
        # 3-tuple con t negativo riconosciuto
        assert EnvelopeBuilder._is_3tuple_breakpoint([-0.5, 1, 'cubic']) is True

    def test_3tuple_with_int_time_and_value(self):
        # 3-tuple con int (non float) riconosciuto
        assert EnvelopeBuilder._is_3tuple_breakpoint([0, 1, 'step']) is True

    def test_3tuple_with_bool_rejected(self):
        # bool è sottoclasse di int — non deve passare
        assert EnvelopeBuilder._is_3tuple_breakpoint([True, 1, 'step']) is False
        assert EnvelopeBuilder._is_3tuple_breakpoint([0, True, 'step']) is False

    def test_3tuple_with_invalid_type_string_still_recognized_as_3tuple(self):
        # _is_3tuple_breakpoint solo struttura; validazione type avviene dopo
        assert EnvelopeBuilder._is_3tuple_breakpoint([0, 1, 'foo']) is True

    def test_legacy_dict_format_still_works(self):
        # Vecchio dict {type, points} con bare [t,v] continua a funzionare
        env = Envelope({'type': 'cubic', 'points': [[0, 0], [1, 1]]})
        assert env.type == 'cubic'

    def test_dict_with_t_v_keys_normalized_only_when_both_present(self):
        # Dict che NON ha 't' e 'v' → non normalizzato (caso compact-style? no, compact è lista)
        # Verifica che dict senza 't' o senza 'v' non venga frainteso come point
        with pytest.raises((ValueError, KeyError)):
            Envelope([{'only_t': 0}, [1, 1]])

    def test_4elem_breakpoint_rejected(self):
        # Breakpoint con 4 elementi → errore
        with pytest.raises(ValueError):
            Envelope([[0, 0, 'cubic', 'extra'], [1, 1]])

    def test_1elem_breakpoint_rejected(self):
        # Breakpoint con 1 elemento → errore
        with pytest.raises(ValueError):
            Envelope([[0], [1, 1]])

    def test_empty_3tuple_breakpoint(self):
        # Lista vuota non confondibile
        assert EnvelopeBuilder._is_3tuple_breakpoint([]) is False
        assert EnvelopeBuilder._is_compact_format([]) is False

    def test_3tuple_passed_as_raw_envelope_not_misread(self):
        # Envelope([0.5, 1, 'cubic']) → iter sugli elementi 0.5, 1, 'cubic' → errore
        with pytest.raises((ValueError, TypeError, AttributeError)):
            Envelope([0.5, 1, 'cubic'])


class TestPerSegmentEvaluate:
    """Semantica per-segmento su evaluate()."""

    def test_step_then_linear(self):
        # Segmento 0→0.5: step (hold 0). Segmento 0.5→1: linear (0→1→0? no: 1→0).
        # Più chiaro: [[0,0,'step'],[0.5,1,'linear'],[1,0]]
        # 0→0.5: step su [0,0]→[0.5,1] → hold 0 fino a 0.5
        # 0.5→1: linear su [0.5,1]→[1,0]
        env = Envelope([[0, 0, 'step'], [0.5, 1, 'linear'], [1, 0]])
        assert env.evaluate(0.0) == pytest.approx(0.0)
        assert env.evaluate(0.25) == pytest.approx(0.0)  # step hold
        assert env.evaluate(0.5) == pytest.approx(1.0)
        assert env.evaluate(0.75) == pytest.approx(0.5)  # linear midpoint
        assert env.evaluate(1.0) == pytest.approx(0.0)

    def test_all_linear_equivalent_to_2elem(self):
        env_3 = Envelope([[0, 0, 'linear'], [0.5, 0.5, 'linear'], [1, 1]])
        env_2 = Envelope([[0, 0], [0.5, 0.5], [1, 1]])
        for t in [0.0, 0.25, 0.5, 0.75, 1.0]:
            assert env_3.evaluate(t) == pytest.approx(env_2.evaluate(t))


class TestPerSegmentIntegrate:
    """Integrate cross-boundary su segmenti misti."""

    def test_step_then_linear_integral(self):
        # [[0,0,'step'],[0.5,1,'linear'],[1,0]]
        # Seg 0 (step, [0,0]→[0.5,1]): valore costante = 0 (left value) su [0, 0.5] → area 0
        # Seg 1 (linear, [0.5,1]→[1,0]): triangolo da v=1 a v=0 su Δt=0.5 → area 0.25
        env = Envelope([[0, 0, 'step'], [0.5, 1, 'linear'], [1, 0]])
        assert env.integrate(0, 1) == pytest.approx(0.25)

    def test_partial_range_first_segment(self):
        env = Envelope([[0, 0, 'step'], [0.5, 1, 'linear'], [1, 0]])
        # Solo seg step su [0, 0.25] → area 0
        assert env.integrate(0, 0.25) == pytest.approx(0.0)

    def test_partial_range_second_segment(self):
        env = Envelope([[0, 0, 'step'], [0.5, 1, 'linear'], [1, 0]])
        # Solo seg linear su [0.5, 0.75]: trap da v=1 a v=0.5 su 0.25 → 0.25 * (1+0.5)/2 = 0.1875
        assert env.integrate(0.5, 0.75) == pytest.approx(0.1875)

    def test_integrate_matches_old_behavior_on_uniform_envelope(self):
        # Senza per-punto: comportamento bit-identico al pre-refactor
        env = Envelope([[0, 0], [0.5, 1], [1, 0]])
        # Triangolo simmetrico altezza 1 base 1 → area 0.5
        assert env.integrate(0, 1) == pytest.approx(0.5)


class TestDictPerPoint:
    """Formato dict con point come {t, v, type}."""

    def test_dict_per_point_accepted(self):
        env = Envelope({
            'type': 'linear',
            'points': [
                {'t': 0, 'v': 0, 'type': 'step'},
                {'t': 0.5, 'v': 1, 'type': 'linear'},
                {'t': 1, 'v': 0},
            ]
        })
        assert env.evaluate(0.25) == pytest.approx(0.0)  # step hold
        assert env.evaluate(0.75) == pytest.approx(0.5)  # linear midpoint

    def test_dict_mixed_dict_and_list_points(self):
        env = Envelope({
            'type': 'linear',
            'points': [
                {'t': 0, 'v': 0, 'type': 'step'},
                [0.5, 1],
                {'t': 1, 'v': 0},
            ]
        })
        assert env.evaluate(0.25) == pytest.approx(0.0)

    def test_compact_wrapper_with_3tuple_pattern(self):
        # Pattern compatto con 3-tuple: step segment, n_reps=2
        # [[[0,0,'step'],[50,1],[100,0]], 1.0, 2]
        # Ciclo 0 (0→0.5): step da 0→1 fissato a 0 fino 50% (t=0.25), poi linear da 1→0
        # Verifica: a 10% del ciclo (t=0.05), step ancora 0
        env = Envelope([[[0, 0, 'step'], [50, 1], [100, 0]], 1.0, 2])
        # Primo ciclo: step da t=0 a t=0.25 → tutto 0
        assert env.evaluate(0.1) == pytest.approx(0.0)

    def test_dict_point_without_type_uses_global(self):
        env = Envelope({
            'type': 'step',
            'points': [
                {'t': 0, 'v': 0},
                {'t': 1, 'v': 1},
            ]
        })
        # global step: hold left
        assert env.evaluate(0.5) == pytest.approx(0.0)


class TestTimeNormalizedWith3Tuple:
    """time_mode=normalized preserva seg_type su 3-tuple."""

    def test_scale_time_recursive_preserves_type(self):
        points = [[0, 0, 'cubic'], [0.5, 1], [1, 0, 'step']]
        scaled = _scale_time_recursive(points, factor=2.0)
        assert scaled[0] == [0.0, 0, 'cubic']
        assert scaled[1] == [1.0, 1]
        assert scaled[2] == [2.0, 0, 'step']

    def test_compact_3tuple_replicated_across_n_reps(self):
        # Pattern con step seg, 3 ripetizioni: ogni ciclo deve avere lo step
        env = Envelope([[[0, 0, 'step'], [50, 1], [100, 0]], 3.0, 3])
        # Ciclo 0: 0→1s. Step da 0→0.5s → valore 0
        assert env.evaluate(0.3) == pytest.approx(0.0)
        # Ciclo 1: 1→2s (con DISCONTINUITY_OFFSET). Step da 1→1.5s → valore 0
        assert env.evaluate(1.3) == pytest.approx(0.0)
        # Ciclo 2: 2→3s. Step da 2→2.5s → valore 0
        assert env.evaluate(2.3) == pytest.approx(0.0)

    def test_compact_3tuple_with_exponential_time_dist(self):
        # 3-tuple pattern + time_dist exponential: seg_type preservato
        env = Envelope([[[0, 0, 'step'], [50, 1], [100, 0]], 1.0, 2, 'linear', 'exponential'])
        # Esegue senza errori; valore in fase step ciclo 0 = 0
        # Ciclo 0 più lungo (exponential = decelerando) → step area maggiore
        assert env.evaluate(0.05) == pytest.approx(0.0)

    def test_compact_3tuple_overrides_wrapper_interp(self):
        # Wrapper interp='cubic' globale; per-punto 'step' override su seg 0
        env = Envelope([[[0, 0, 'step'], [50, 1], [100, 0]], 1.0, 1, 'cubic'])
        # Seg 0→0.5: step (per-punto override su cubic globale) → valore 0
        assert env.evaluate(0.25) == pytest.approx(0.0)

    def test_compact_mixed_legacy_and_3tuple_pattern(self):
        # Pattern con mix 2-elem e 3-elem
        env = Envelope([[[0, 0, 'step'], [50, 1], [100, 0]], 1.0, 1])
        # Seg 0 step, seg 1 linear (default)
        assert env.evaluate(0.25) == pytest.approx(0.0)  # step
        assert env.evaluate(0.75) == pytest.approx(0.5)  # linear midpoint

    def test_compact_pure_2elem_unchanged(self):
        # Regression: pattern 100% 2-elem dà output identico al pre-refactor
        # Pattern [[0,0],[50,1],[100,0]], end_time=1.0, n_reps=2 → cycle_dur=0.5
        # Ciclo 0: [0,0]→[0.25,1]→[0.5,0]
        env = Envelope([[[0, 0], [50, 1], [100, 0]], 1.0, 2])
        assert env.evaluate(0.0) == pytest.approx(0.0)
        assert env.evaluate(0.125) == pytest.approx(0.5)  # rampa up midpoint
        assert env.evaluate(0.25) == pytest.approx(1.0)   # peak ciclo 0
        assert env.evaluate(0.375) == pytest.approx(0.5)  # rampa down midpoint
        assert env.evaluate(0.5) == pytest.approx(0.0)    # fine ciclo 0
        # Ciclo 1 con DISCONTINUITY_OFFSET
        assert env.evaluate(0.75) == pytest.approx(1.0)   # peak ciclo 1

    def test_create_scaled_envelope_normalized_with_3tuple(self):
        env = create_scaled_envelope(
            [[0, 0, 'step'], [0.5, 1, 'linear'], [1, 0]],
            duration=2.0,
            time_mode='normalized'
        )
        # Step segment ora 0→1s, linear 1→2s
        assert env.evaluate(0.5) == pytest.approx(0.0)  # step hold
        assert env.evaluate(1.5) == pytest.approx(0.5)  # linear midpoint

    def test_scale_time_recursive_preserves_dict_per_point(self):
        # Dict per-punto deve essere scalato come list
        points = [{'t': 0, 'v': 5, 'type': 'step'}, [0.5, 30], {'t': 1, 'v': 5}]
        scaled = _scale_time_recursive(points, factor=4.0)
        # Tutti i t devono essere scalati × 4
        assert scaled[0]['t'] == 0.0
        assert scaled[1][0] == 2.0
        assert scaled[2]['t'] == 4.0

    def test_create_scaled_envelope_dict_mixed_dict_list_points(self):
        # Bug riprodotto da stream 12 di PGE_envelope_syntax_test.yml
        env = create_scaled_envelope(
            {
                'type': 'linear',
                'points': [
                    {'t': 0, 'v': 5, 'type': 'step'},
                    [0.5, 30],
                    {'t': 1, 'v': 5},
                ],
            },
            duration=4.0,
            time_mode='normalized',
        )
        # Tutti i bp devono cadere nel range [0, 4]
        for bp in env.breakpoints:
            assert 0.0 <= bp[0] <= 4.0
        # Step da 0→2: hold a 5
        assert env.evaluate(1.0) == pytest.approx(5.0)
        # Peak a t=2
        assert env.evaluate(2.0) == pytest.approx(30.0)
        # Linear da 2→4: midpoint a t=3
        assert env.evaluate(3.0) == pytest.approx(17.5)
        assert env.evaluate(4.0) == pytest.approx(5.0)
