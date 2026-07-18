"""
Test suite per BP group [points, interp] negli envelope (issue #64).

Formato:
- Item misto: [[[t, v], [t, v], ...], interp] — macrozona di breakpoint
  con interpolazione propria, simmetrica al loop block.
- Forma diretta: Envelope([points, interp]).

Semantica: il group interp si applica ai segmenti INTERNI della zona
(n punti → n-1 segmenti). Il gap in uscita dall'ultimo punto resta al
default globale. Desugar su breakpoint 3-tuple (issue #54).
"""

import logging

import pytest
from pge.envelopes.envelope import (
    Envelope,
    create_scaled_envelope,
    scale_raw_param_values,
    _scale_time_recursive,
)
from pge.envelopes.envelope_builder import EnvelopeBuilder
from pge.shared.exceptions import InvalidFieldValueError


class TestBPGroupZoneSemantics:
    """La zona interpola col proprio interp; il gap in uscita no."""

    def test_step_zone_then_linear_gap(self):
        # Zona step su [0, 0.5]; gap 0.5→1.0 fuori zona al default linear
        env = Envelope([[[[0.0, 0], [0.5, 1]], 'step'], [1.0, 0]])
        assert env.evaluate(0.25) == pytest.approx(0.0)   # dentro zona: step hold
        assert env.evaluate(0.5) == pytest.approx(1.0)
        assert env.evaluate(0.75) == pytest.approx(0.5)   # gap: linear

    def test_two_zones_with_different_interp(self):
        # Zona A step [0, 0.4], gap linear 0.4→0.6, zona B linear [0.6, 1.0]
        env = Envelope([
            [[[0.0, 0], [0.4, 0.8]], 'step'],
            [[[0.6, 0.4], [1.0, 0]], 'linear'],
        ])
        assert env.evaluate(0.2) == pytest.approx(0.0)    # zona A: step hold
        assert env.evaluate(0.4) == pytest.approx(0.8)
        assert env.evaluate(0.5) == pytest.approx(0.6)    # gap: linear 0.8→0.4
        assert env.evaluate(0.8) == pytest.approx(0.2)    # zona B: linear 0.4→0
        assert env.evaluate(1.0) == pytest.approx(0.0)

    def test_three_zone_run_inside_bare_breakpoints(self):
        # BP nudi prima e dopo la zona: la zona non altera i tratti fuori
        env = Envelope([
            [0.0, 0],
            [0.2, 10],
            [[[0.4, 4], [0.6, 8]], 'step'],
            [1.0, 0],
        ])
        assert env.evaluate(0.1) == pytest.approx(5.0)    # BP nudi: linear
        assert env.evaluate(0.3) == pytest.approx(7.0)    # gap 0.2→0.4: linear 10→4
        assert env.evaluate(0.5) == pytest.approx(4.0)    # zona: step hold
        assert env.evaluate(0.8) == pytest.approx(4.0)    # gap 0.6→1.0: linear 8→0


class TestBPGroupDirectForm:
    """Forma diretta Envelope([points, interp]), simmetrica al compatto diretto."""

    def test_direct_step_group(self):
        env = Envelope([[[0.0, 0], [0.5, 1], [1.0, 0]], 'step'])
        assert env.evaluate(0.25) == pytest.approx(0.0)   # step hold
        assert env.evaluate(0.75) == pytest.approx(1.0)   # step hold del secondo seg
        assert env.evaluate(1.0) == pytest.approx(0.0)


class TestBPGroupValidation:
    """Errori precisi su interp invalido e zona degenere."""

    def test_invalid_interp_raises_invalid_field_value_error(self):
        with pytest.raises(InvalidFieldValueError) as exc:
            Envelope([[[0.0, 0], [1.0, 1]], 'qubic'])
        assert 'linear' in exc.value.hint
        assert 'cubic' in exc.value.hint
        assert 'step' in exc.value.hint

    def test_invalid_interp_in_mixed_raises(self):
        with pytest.raises(InvalidFieldValueError):
            Envelope([[0.0, 0], [[[0.5, 1], [1.0, 0]], 'bezier']])

    def test_single_point_group_raises(self):
        with pytest.raises(ValueError):
            Envelope([[[0.5, 1]], 'cubic'])

    def test_empty_points_group_raises(self):
        with pytest.raises(ValueError):
            Envelope([[], 'cubic'])


class TestBPGroupNoGlobalLeak:
    """Il group interp non contamina il tipo globale dell'envelope."""

    def test_group_interp_does_not_become_global_type(self):
        env = Envelope([[[[0.0, 0], [0.5, 1]], 'step'], [1.0, 0]])
        assert env.type == 'linear'

    def test_direct_group_keeps_global_linear(self):
        env = Envelope([[[0.0, 0], [1.0, 1]], 'cubic'])
        assert env.type == 'linear'

    def test_loop_block_interp_still_global(self):
        # Comportamento pre-esistente invariato: l'interp del loop block
        # resta il default globale via extract_interp_type
        env = Envelope([[0, 0], [0.3, 30], [[[0, 5], [100, 10]], 1.0, 2, 'step']])
        assert env.type == 'step'


class TestBPGroupPerPointOverride:
    """Punto 3-tuple dentro la zona: override del group interp."""

    def test_3tuple_point_overrides_group_interp(self):
        env = Envelope([[[0.0, 0], [0.5, 1, 'linear'], [1.0, 0]], 'step'])
        assert env.evaluate(0.25) == pytest.approx(0.0)   # group step
        assert env.evaluate(0.75) == pytest.approx(0.5)   # override linear

    def test_explicit_type_on_last_group_point_governs_outgoing_gap(self):
        # L'utente puo' taggare esplicitamente l'ultimo punto della zona:
        # il type si applica al segmento in uscita (semantica per-punto #54)
        env = Envelope([[[[0.0, 0], [0.5, 1, 'step']], 'linear'], [1.0, 0]])
        assert env.evaluate(0.25) == pytest.approx(0.5)   # zona: linear
        assert env.evaluate(0.75) == pytest.approx(1.0)   # gap: step hold


class TestBPGroupCubicPchip:
    """Zona cubic = PCHIP Fritsch-Carlson, identica al cubic globale."""

    def test_direct_cubic_group_matches_dict_cubic(self):
        points = [[0.0, 0], [0.3, 1], [0.7, 0.2], [1.0, 0.8]]
        env_group = Envelope([points, 'cubic'])
        env_dict = Envelope({'type': 'cubic', 'points': points})
        for i in range(101):
            t = i / 100.0
            assert env_group.evaluate(t) == pytest.approx(env_dict.evaluate(t)), t

    def test_cubic_group_is_monotone_between_monotone_points(self):
        # Fritsch-Carlson non fa overshoot su dati monotoni
        env = Envelope([[[0.0, 0], [0.4, 0.5], [1.0, 1]], 'cubic'])
        prev = env.evaluate(0.0)
        for i in range(1, 101):
            cur = env.evaluate(i / 100.0)
            assert cur >= prev - 1e-12
            prev = cur
        assert env.evaluate(1.0) == pytest.approx(1.0)

    def test_all_linear_group_equivalent_to_bare_breakpoints(self):
        points = [[0.0, 0], [0.4, 0.7], [1.0, 0.1]]
        env_group = Envelope([points, 'linear'])
        env_bare = Envelope(points)
        for i in range(101):
            t = i / 100.0
            assert env_group.evaluate(t) == pytest.approx(env_bare.evaluate(t))


class TestBPGroupIntegrate:
    """Integrale analitico su envelope con zona."""

    def test_step_zone_plus_linear_gap_integral(self):
        # Zona step [0,0]→[0.5,1]: hold 0 → area 0.
        # Gap linear [0.5,1]→[1,0]: triangolo 0.5*1/2 = 0.25.
        env = Envelope([[[[0.0, 0], [0.5, 1]], 'step'], [1.0, 0]])
        assert env.integrate(0, 1) == pytest.approx(0.25)

    def test_partial_range_inside_zone(self):
        env = Envelope([[[[0.0, 0], [0.5, 1]], 'step'], [1.0, 0]])
        assert env.integrate(0, 0.25) == pytest.approx(0.0)
        assert env.integrate(0.5, 0.75) == pytest.approx(0.1875)  # trapezio 1→0.5


class TestBPGroupWithLoopBlock:
    """Struttura completa della issue #64: zona + loop + zona."""

    def test_issue_shaped_envelope(self):
        env = Envelope([
            [[[0.0, 0], [0.2, 12], [0.4, 8]], 'cubic'],
            [[[0, 8], [100, 18]], 0.7, 2, 'linear'],
            [[[0.75, 6], [0.9, 6], [1.0, 0]], 'step'],
        ])
        # Zona A (cubic): passa per i suoi punti
        assert env.evaluate(0.2) == pytest.approx(12.0)
        assert env.evaluate(0.4) == pytest.approx(8.0)
        # Loop: 2 cicli 8→18 su [0.4, 0.7], midpoint ciclo 0 a 0.475
        assert env.evaluate(0.475) == pytest.approx(13.0, abs=1e-3)
        assert env.evaluate(0.7) == pytest.approx(18.0)
        # Gap 0.7→0.75 al default globale (linear del loop): 18→6
        assert env.evaluate(0.72) == pytest.approx(13.2, abs=1e-3)
        # Zona B (step): hold 6 fino a 1.0
        assert env.evaluate(0.75) == pytest.approx(6.0)
        assert env.evaluate(0.95) == pytest.approx(6.0)
        assert env.evaluate(1.0) == pytest.approx(0.0)


def _times_strictly_increasing(env):
    times = [bp[0] for bp in env.breakpoints]
    return all(t1 > t0 for t0, t1 in zip(times, times[1:]))


class TestBPGroupDiscontinuityOffset:
    """Collisione al bordo zona → DISCONTINUITY_OFFSET, come i loop block."""

    def test_collision_with_previous_bare_breakpoint(self):
        # Salto verticale intenzionale 8→2 a t=0.5
        env = Envelope([[0.0, 0], [0.5, 8], [[[0.5, 2], [1.0, 0]], 'linear']])
        assert _times_strictly_increasing(env)
        assert env.evaluate(0.5) == pytest.approx(8.0)          # valore sinistro
        assert env.evaluate(0.501) == pytest.approx(2.0, abs=0.01)  # dopo il salto

    def test_no_shift_without_collision(self):
        env = Envelope([[0.0, 0], [0.5, 8], [[[0.6, 2], [1.0, 0]], 'linear']])
        times = [bp[0] for bp in env.breakpoints]
        assert 0.6 in times                                      # nessuno shift

    def test_collision_between_two_groups(self):
        env = Envelope([
            [[[0.0, 0], [0.5, 1]], 'step'],
            [[[0.5, 3], [1.0, 0]], 'linear'],
        ])
        assert _times_strictly_increasing(env)
        assert env.evaluate(0.5) == pytest.approx(1.0)
        assert env.evaluate(0.75) == pytest.approx(1.5, abs=0.01)

    def test_collision_after_loop_block(self):
        env = Envelope([
            [[[0, 0], [100, 1]], 0.5, 1],
            [[[0.5, 0.2], [1.0, 0]], 'step'],
        ])
        assert _times_strictly_increasing(env)
        assert env.evaluate(0.75) == pytest.approx(0.2)          # zona: step hold


class TestBPGroupEnvelopeLike:
    """is_envelope_like riconosce forma diretta e item misto.

    Nota: i casi a 2 punti passano gia' per il check lasco pre-esistente
    (`len(item) == 2`); il contratto nuovo sono i gruppi con 3+ punti.
    """

    def test_direct_group_is_envelope_like(self):
        assert Envelope.is_envelope_like(
            [[[0.0, 0], [0.5, 1], [1.0, 0]], 'cubic']
        ) is True

    def test_mixed_list_with_group_is_envelope_like(self):
        assert Envelope.is_envelope_like([
            [[[0.0, 0], [0.4, 1], [0.5, 1]], 'step'],
            [[[0.6, 1], [0.8, 0.5], [1.0, 0]], 'linear'],
        ]) is True


class TestBPGroupTimeScaling:
    """time_mode: normalized scala i tempi del gruppo, preservando i type."""

    def test_scale_time_recursive_scales_group_points_and_keeps_interp(self):
        raw = [[[[0.0, 0], [0.5, 1, 'linear'], [1.0, 0]], 'step']]
        scaled = _scale_time_recursive(raw, factor=4.0)
        assert scaled == [[[[0.0, 0], [2.0, 1, 'linear'], [4.0, 0]], 'step']]

    def test_create_scaled_envelope_normalized_direct_group(self):
        env = create_scaled_envelope(
            [[[0.0, 0], [0.5, 1], [1.0, 0]], 'step'],
            duration=2.0,
            time_mode='normalized',
        )
        # Zona scalata su [0, 2]: punti a 0, 1, 2 secondi
        assert env.evaluate(0.5) == pytest.approx(0.0)   # step hold
        assert env.evaluate(1.5) == pytest.approx(1.0)   # step hold del secondo seg
        assert env.evaluate(2.0) == pytest.approx(0.0)

    def test_create_scaled_envelope_normalized_mixed_with_group(self):
        env = create_scaled_envelope(
            [[0.0, 5], [[[0.5, 1], [1.0, 0]], 'step']],
            duration=2.0,
            time_mode='normalized',
        )
        assert env.evaluate(0.5) == pytest.approx(3.0)   # gap linear 5→1 su [0, 1]
        assert env.evaluate(1.5) == pytest.approx(1.0)   # zona step su [1, 2]


class TestBPGroupValueScaling:
    """Scaling Y (pointer normalized, grain.duration samples) sul gruppo."""

    def test_scale_y_direct_group_preserves_times_and_types(self):
        raw = [[[0.0, 0], [0.5, 1, 'linear'], [1.0, 0.5]], 'step']
        scaled = scale_raw_param_values(raw, 2.0)
        assert scaled == [[[0.0, 0], [0.5, 2.0, 'linear'], [1.0, 1.0]], 'step']

    def test_scale_y_mixed_with_group(self):
        raw = [[0.0, 4], [[[0.5, 1], [0.8, 2], [1.0, 0.5]], 'step']]
        scaled = scale_raw_param_values(raw, 2.0)
        assert scaled == [[0.0, 8.0], [[[0.5, 2.0], [0.8, 4.0], [1.0, 1.0]], 'step']]


class TestBPGroupInsideDictPoints:
    """Gruppo dentro points del dict {type, points}: il type del dict
    resta il default dei segmenti fuori zona."""

    def test_group_in_dict_points_with_global_step(self):
        env = Envelope({
            'type': 'step',
            'points': [
                [[[0.0, 0], [0.5, 1]], 'linear'],
                [1.0, 0],
            ],
        })
        assert env.evaluate(0.25) == pytest.approx(0.5)   # zona: linear
        assert env.evaluate(0.75) == pytest.approx(1.0)   # gap: step (dict type)


class TestBPGroupNoSpuriousWarning:
    """La zona in coda all'envelope non produce il warning 'ultimo punto'."""

    def test_no_warning_when_group_closes_envelope(self, caplog):
        with caplog.at_level(logging.WARNING):
            Envelope([[0.0, 0], [[[0.5, 1], [1.0, 0]], 'step']])
        assert 'ultimo punto ignorato' not in caplog.text

    def test_explicit_trailing_3tuple_in_group_still_warns(self, caplog):
        # Type esplicito dell'utente sull'ultimo punto assoluto: il warning
        # pre-esistente resta corretto
        with caplog.at_level(logging.WARNING):
            Envelope([[[[0.0, 0], [1.0, 1, 'step']], 'linear']])
        assert 'ultimo punto ignorato' in caplog.text


class TestBPGroupRecognition:
    """Disambiguazione shape: gruppo vs breakpoint vs 3-tuple vs loop block."""

    def test_group_recognized(self):
        assert EnvelopeBuilder._is_bp_group([[[0.0, 0], [1.0, 1]], 'cubic']) is True

    def test_group_with_3tuple_point_recognized(self):
        assert EnvelopeBuilder._is_bp_group(
            [[[0.0, 0], [1.0, 1, 'step']], 'cubic']
        ) is True

    def test_group_with_invalid_interp_still_structurally_group(self):
        # Come _is_3tuple_breakpoint: check strutturale, validazione dopo
        assert EnvelopeBuilder._is_bp_group([[[0.0, 0], [1.0, 1]], 'qubic']) is True

    def test_bare_breakpoint_not_group(self):
        assert EnvelopeBuilder._is_bp_group([0.5, 1.0]) is False

    def test_2elem_with_string_value_not_group(self):
        assert EnvelopeBuilder._is_bp_group([0.5, 'cubic']) is False

    def test_single_point_with_marker_not_group(self):
        # elem[0] è UN punto [t, v], non una lista di punti
        assert EnvelopeBuilder._is_bp_group([[0, 5], 'cycle']) is False

    def test_3tuple_breakpoint_not_group(self):
        assert EnvelopeBuilder._is_bp_group([0.5, 1.0, 'cubic']) is False

    def test_loop_blocks_not_group(self):
        assert EnvelopeBuilder._is_bp_group([[[0, 0], [100, 1]], 0.4, 4]) is False
        assert EnvelopeBuilder._is_bp_group(
            [[[0, 0], [100, 1]], 0.4, 4, 'cubic', 'exponential']
        ) is False

    def test_group_not_compact_nor_3tuple(self):
        group = [[[0.0, 0], [1.0, 1]], 'cubic']
        assert EnvelopeBuilder._is_compact_format(group) is False
        assert EnvelopeBuilder._is_3tuple_breakpoint(group) is False

    def test_group_with_non_string_interp_not_group(self):
        assert EnvelopeBuilder._is_bp_group([[[0.0, 0], [1.0, 1]], 4]) is False

    def test_bool_poisoned_points_not_group(self):
        assert EnvelopeBuilder._is_bp_group([[[True, 0], [1.0, 1]], 'cubic']) is False
        assert EnvelopeBuilder._is_bp_group([[[0.0, True], [1.0, 1]], 'cubic']) is False

    def test_plain_two_breakpoint_envelope_not_group(self):
        # Envelope nudo a 2 breakpoint: elem[1] non è stringa
        assert EnvelopeBuilder._is_bp_group([[0.0, 0], [1.0, 1]]) is False
