"""
Test suite per cycle wrap mode (issue #55).

Formato compatto envelope esteso con 6° elemento bool `wrap`:
    [pattern, end_time, n_reps, interp, time_dist, wrap]

wrap=True: gap inter-ciclo interpola da v_finale a primo y ciclo successivo.
            Ultimo ciclo wrappa verso primo y del ciclo 0 (loop chiuso).
wrap=False (default): comportamento attuale (hold implicito).
"""

import pytest
from envelopes.envelope_builder import EnvelopeBuilder
from envelopes.envelope import Envelope


# =============================================================================
# FASE 1 — PARSER
# =============================================================================

class TestWrapParser:
    """Test _is_compact_format con 6° elemento wrap."""

    def test_accept_wrap_true(self):
        assert EnvelopeBuilder._is_compact_format(
            [[[0, 0], [50, 1]], 1.0, 2, 'linear', None, True]
        )

    def test_accept_wrap_false(self):
        assert EnvelopeBuilder._is_compact_format(
            [[[0, 0], [50, 1]], 1.0, 2, 'linear', None, False]
        )

    def test_accept_wrap_none(self):
        """None ammesso (default False)."""
        assert EnvelopeBuilder._is_compact_format(
            [[[0, 0], [50, 1]], 1.0, 2, 'linear', None, None]
        )

    def test_reject_wrap_non_bool(self):
        assert not EnvelopeBuilder._is_compact_format(
            [[[0, 0], [50, 1]], 1.0, 2, 'linear', None, 'wrap']
        )
        assert not EnvelopeBuilder._is_compact_format(
            [[[0, 0], [50, 1]], 1.0, 2, 'linear', None, 1]
        )

    def test_reject_7_elements(self):
        assert not EnvelopeBuilder._is_compact_format(
            [[[0, 0]], 1.0, 2, 'linear', None, True, 'extra']
        )


# =============================================================================
# FASE 2 — SEMANTICA WRAP
# =============================================================================

class TestWrapSemantics:
    """Iniezione breakpoint sintetici."""

    def test_wrap_true_injects_synthetics(self):
        """
        pattern [[0,0],[50,1]] n_reps=2 end=2 wrap=True:
        cycli duration 1 ciascuno.
        Atteso: breakpoint normali + sintetici prima della fine di ogni ciclo
        con y = first_y = 0
        """
        compact = [[[0, 0], [50, 1]], 2.0, 2, 'linear', None, True]
        expanded = EnvelopeBuilder._expand_compact_format(compact)

        # Cerca breakpoint con t vicino a 1.0 e 2.0 con y=0
        # Sintetici devono essere a cycle_end - DISCONTINUITY_OFFSET
        eps = EnvelopeBuilder.DISCONTINUITY_OFFSET
        ts = [p[0] for p in expanded]
        ys = [p[1] for p in expanded]

        # Punto sintetico fine ciclo 0: t ≈ 1.0 - eps, y = 0
        assert any(abs(t - (1.0 - eps)) < 1e-9 and y == 0 for t, y in zip(ts, ys))
        # Punto sintetico fine ciclo 1: t ≈ 2.0 - eps, y = 0
        assert any(abs(t - (2.0 - eps)) < 1e-9 and y == 0 for t, y in zip(ts, ys))

    def test_wrap_false_no_synthetics(self):
        """wrap=False produce stesso output di formato 5-elementi."""
        compact_with_false = [[[0, 0], [50, 1]], 2.0, 2, 'linear', None, False]
        compact_without = [[[0, 0], [50, 1]], 2.0, 2, 'linear', None]

        expanded_false = EnvelopeBuilder._expand_compact_format(compact_with_false)
        expanded_baseline = EnvelopeBuilder._expand_compact_format(compact_without)

        assert expanded_false == expanded_baseline

    def test_wrap_default_when_omitted(self):
        """5 elementi = wrap implicito False, output invariato."""
        compact_5 = [[[0, 0], [50, 1]], 2.0, 2, 'linear', None]
        expanded = EnvelopeBuilder._expand_compact_format(compact_5)

        # Non deve contenere sintetici a cycle_end-eps con y=0
        # Verifica: nessun punto vicino a fine ciclo (1.0 o 2.0) con y!=valore_finale_pattern
        # pattern finale: x=50% → t=0.5, 1.5 con y=1
        # senza wrap: nessun breakpoint a t≈1.0 o ≈2.0
        eps = EnvelopeBuilder.DISCONTINUITY_OFFSET
        for t, *_ in expanded:
            assert not (abs(t - (1.0 - eps)) < 1e-9)
            assert not (abs(t - (2.0 - eps)) < 1e-9)

    def test_wrap_evaluate_in_gap(self):
        """evaluate(t) a meta gap → valore interpolato linearmente tra v_finale e first_y."""
        compact = [[[0, 0], [50, 1]], 2.0, 2, 'linear', None, True]
        expanded = EnvelopeBuilder._expand_compact_format(compact)

        env = Envelope(expanded)
        # Gap ciclo 0: da t=0.5 (y=1) a t≈1.0 (y=0). Metà a t=0.75 → y ≈ 0.5
        v = env.evaluate(0.75)
        assert abs(v - 0.5) < 0.01


# =============================================================================
# FASE 3 — EDGE CASES
# =============================================================================

class TestWrapEdgeCases:
    """Casi limite."""

    def test_last_x_100_no_injection(self):
        """Pattern con ultimo x=100 → gap=0 → nessun sintetico."""
        compact_wrap = [[[0, 0], [100, 1]], 2.0, 2, 'linear', None, True]
        compact_no_wrap = [[[0, 0], [100, 1]], 2.0, 2, 'linear', None, False]

        expanded_wrap = EnvelopeBuilder._expand_compact_format(compact_wrap)
        expanded_no_wrap = EnvelopeBuilder._expand_compact_format(compact_no_wrap)

        # Stessa quantita di punti: nessun sintetico iniettato
        assert len(expanded_wrap) == len(expanded_no_wrap)

    def test_n_reps_1_with_wrap(self):
        """n_reps=1 + wrap=True → 1 sintetico a fine ciclo (fade to start)."""
        compact = [[[0, 0], [50, 1]], 1.0, 1, 'linear', None, True]
        expanded = EnvelopeBuilder._expand_compact_format(compact)

        eps = EnvelopeBuilder.DISCONTINUITY_OFFSET
        # Deve contenere sintetico a t ≈ 1.0 - eps con y=0
        assert any(abs(t - (1.0 - eps)) < 1e-9 and y == 0 for t, *rest in expanded for y in [rest[0]])

    def test_wrap_with_exponential_time_dist(self):
        """time_dist=exponential + wrap: sintetici seguono cycle_durations variabile."""
        compact = [[[0, 0], [50, 1]], 4.0, 3, 'linear', 'exponential', True]
        expanded = EnvelopeBuilder._expand_compact_format(compact)

        # Deve contenere n_reps=3 punti sintetici (con y=0=first_y)
        # I sintetici sono punti con y=0 (first_y) escludendo il punto iniziale a t=0
        synthetics = [(t, y) for t, *rest in expanded for y in [rest[0]] if y == 0 and t > 0.0]
        # Almeno 3 sintetici (uno per ciclo). Potrebbe esserci pattern point [0,0] all'inizio
        # cicli successivi, dovuto a DISCONTINUITY_OFFSET su rep>0
        # Quindi conteggio rigoroso: punti con y=0 e t = cycle_end - eps
        assert len(synthetics) >= 3
