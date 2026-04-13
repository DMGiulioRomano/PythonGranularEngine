"""
test_window_selection_strategy.py

Suite TDD per controllers/window_selection_strategy.py.

Coverage:
1. SingleWindowStrategy - sempre ritorna la stessa finestra
2. RandomWindowStrategy - gate closed → prima finestra, gate open → random.choice
3. TransitionWindowStrategy - blend probabilistico from→to basato su Envelope
4. Integrazione: time_mode normalized vs assoluto
"""

import pytest
import random as random_module
from unittest.mock import patch

from controllers.window_selection_strategy import (
    WindowSelectionStrategy,
    SingleWindowStrategy,
    RandomWindowStrategy,
    TransitionWindowStrategy,
)
from shared.probability_gate import NeverGate, AlwaysGate, RandomGate
from envelopes.envelope import Envelope


# =============================================================================
# 1. SingleWindowStrategy
# =============================================================================

class TestSingleWindowStrategy:

    def _make(self, window='hanning'):
        from shared.probability_gate import NeverGate
        return SingleWindowStrategy(window, gate=NeverGate())

    def test_always_returns_configured_window(self):
        s = self._make('hanning')
        for _ in range(50):
            assert s.select(0.0) == 'hanning'

    def test_returns_correct_window_for_different_names(self):
        for name in ('hanning', 'bartlett', 'expodec', 'gaussian'):
            s = self._make(name)
            assert s.select(0.0) == name

    def test_elapsed_time_has_no_effect(self):
        s = self._make('hanning')
        for t in [0.0, 1.0, 5.0, 100.0]:
            assert s.select(t) == 'hanning'

    def test_is_subclass_of_strategy(self):
        assert issubclass(SingleWindowStrategy, WindowSelectionStrategy)


# =============================================================================
# 2. RandomWindowStrategy
# =============================================================================

class TestRandomWindowStrategy:

    def test_never_gate_returns_first_window(self):
        s = RandomWindowStrategy(['hanning', 'expodec'], NeverGate())
        for _ in range(50):
            assert s.select(0.0) == 'hanning'

    def test_always_gate_single_window_returns_it(self):
        s = RandomWindowStrategy(['hanning'], AlwaysGate())
        for _ in range(50):
            assert s.select(0.0) == 'hanning'

    def test_always_gate_covers_all_windows(self):
        windows = ['hanning', 'expodec', 'gaussian']
        s = RandomWindowStrategy(windows, AlwaysGate())
        results = set(s.select(0.0) for _ in range(500))
        assert results == set(windows)

    def test_never_gate_stable_across_times(self):
        s = RandomWindowStrategy(['gaussian', 'blackman'], NeverGate())
        for t in [0.0, 2.5, 5.0, 9.9]:
            assert s.select(t) == 'gaussian'

    def test_elapsed_time_passed_to_gate(self):
        from unittest.mock import Mock
        from shared.probability_gate import ProbabilityGate
        mock_gate = Mock(spec=ProbabilityGate)
        mock_gate.should_apply.return_value = False
        s = RandomWindowStrategy(['hanning', 'expodec'], mock_gate)
        s.select(3.14)
        mock_gate.should_apply.assert_called_once_with(3.14)

    def test_is_subclass_of_strategy(self):
        assert issubclass(RandomWindowStrategy, WindowSelectionStrategy)

    def test_statistical_uniformity_with_always_gate(self):
        windows = ['hanning', 'expodec']
        s = RandomWindowStrategy(windows, AlwaysGate())
        counts = {w: 0 for w in windows}
        for _ in range(1000):
            counts[s.select(0.0)] += 1
        for w in windows:
            assert 0.45 <= counts[w] / 1000 <= 0.55, f"{w}: {counts[w]}"

    def test_determinism_with_seed(self):
        windows = ['hanning', 'expodec', 'gaussian']
        s = RandomWindowStrategy(windows, AlwaysGate())
        random_module.seed(42)
        seq1 = [s.select(0.0) for _ in range(100)]
        random_module.seed(42)
        seq2 = [s.select(0.0) for _ in range(100)]
        assert seq1 == seq2


# =============================================================================
# 3. TransitionWindowStrategy
# =============================================================================

class TestTransitionWindowStrategyBlend:
    """Testa la logica di blend con curve fisse (controllo diretto)."""

    def _make(self, from_w, to_w, curve_pts, duration=10.0, time_mode=None):
        curve = Envelope(curve_pts)
        return TransitionWindowStrategy(
            from_window=from_w,
            to_window=to_w,
            curve=curve,
            duration=duration,
            time_mode=time_mode,
        )

    # ---  blend = 0.0 → 100% from_window ---

    def test_blend_zero_always_returns_from(self):
        """curve = [[0,0],[10,0]] → blend sempre 0 → sempre from."""
        s = self._make('hanning', 'bartlett', [[0, 0], [10, 0]], duration=10.0)
        for _ in range(100):
            assert s.select(0.0) == 'hanning'

    def test_blend_one_always_returns_to(self):
        """curve = [[0,1],[10,1]] → blend sempre 1 → sempre to."""
        s = self._make('hanning', 'bartlett', [[0, 1], [10, 1]], duration=10.0)
        for _ in range(100):
            assert s.select(0.0) == 'bartlett'

    def test_at_t0_with_linear_curve_returns_from(self):
        """curve [[0,0],[10,1]] a t=0 → blend=0 → 100% hanning."""
        s = self._make('hanning', 'bartlett', [[0, 0], [10, 1]], duration=10.0)
        random_module.seed(42)
        results = [s.select(0.0) for _ in range(200)]
        assert all(r == 'hanning' for r in results)

    def test_at_end_with_linear_curve_returns_to(self):
        """curve [[0,0],[10,1]] a t=10 → blend=1 → 100% bartlett."""
        s = self._make('hanning', 'bartlett', [[0, 0], [10, 1]], duration=10.0)
        random_module.seed(42)
        results = [s.select(10.0) for _ in range(200)]
        assert all(r == 'bartlett' for r in results)

    def test_at_midpoint_distribution_is_roughly_50_50(self):
        """curve [[0,0],[10,1]] a t=5 → blend=0.5 → ~50/50."""
        s = self._make('hanning', 'bartlett', [[0, 0], [10, 1]], duration=10.0)
        counts = {'hanning': 0, 'bartlett': 0}
        for _ in range(2000):
            counts[s.select(5.0)] += 1
        ratio = counts['bartlett'] / 2000
        assert 0.44 <= ratio <= 0.56, f"ratio bartlett: {ratio}"

    def test_result_is_always_from_or_to(self):
        s = self._make('hanning', 'bartlett', [[0, 0], [10, 1]], duration=10.0)
        for t in [0.0, 2.5, 5.0, 7.5, 10.0]:
            for _ in range(20):
                assert s.select(t) in ('hanning', 'bartlett')

    def test_is_subclass_of_strategy(self):
        assert issubclass(TransitionWindowStrategy, WindowSelectionStrategy)


# =============================================================================
# 4. TransitionWindowStrategy - time_mode normalized
# =============================================================================

class TestTransitionWindowStrategyTimeMode:

    def _make_normalized(self, from_w, to_w, curve_pts, duration=10.0):
        return TransitionWindowStrategy(
            from_window=from_w,
            to_window=to_w,
            curve=Envelope(curve_pts),
            duration=duration,
            time_mode='normalized',
        )

    def _make_absolute(self, from_w, to_w, curve_pts, duration=10.0):
        return TransitionWindowStrategy(
            from_window=from_w,
            to_window=to_w,
            curve=Envelope(curve_pts),
            duration=duration,
            time_mode=None,  # default: secondi assoluti
        )

    def test_normalized_t0_returns_from(self):
        """normalized: curve [[0,0],[1,1]] a elapsed=0 → blend=0 → 100% from."""
        s = self._make_normalized('hanning', 'bartlett', [[0, 0], [1, 1]], duration=10.0)
        results = [s.select(0.0) for _ in range(200)]
        assert all(r == 'hanning' for r in results)

    def test_normalized_at_duration_returns_to(self):
        """normalized: curve [[0,0],[1,1]] a elapsed=duration → blend=1 → 100% to."""
        s = self._make_normalized('hanning', 'bartlett', [[0, 0], [1, 1]], duration=10.0)
        results = [s.select(10.0) for _ in range(200)]  # elapsed=duration=10 → t_norm=1
        assert all(r == 'bartlett' for r in results)

    def test_normalized_midpoint(self):
        """normalized: curve [[0,0],[1,1]] a elapsed=5 (=0.5 normalizzato) → ~50/50."""
        s = self._make_normalized('hanning', 'bartlett', [[0, 0], [1, 1]], duration=10.0)
        counts = {'hanning': 0, 'bartlett': 0}
        for _ in range(2000):
            counts[s.select(5.0)] += 1
        ratio = counts['bartlett'] / 2000
        assert 0.44 <= ratio <= 0.56, f"ratio bartlett: {ratio}"

    def test_absolute_curve_uses_seconds_directly(self):
        """Absolute (no time_mode): curve [[0,0],[10,1]] a elapsed=10 → blend=1."""
        s = self._make_absolute('hanning', 'bartlett', [[0, 0], [10, 1]], duration=10.0)
        results = [s.select(10.0) for _ in range(200)]
        assert all(r == 'bartlett' for r in results)

    def test_absolute_curve_at_t0(self):
        """Absolute: a elapsed=0 → blend=0 → 100% from."""
        s = self._make_absolute('hanning', 'bartlett', [[0, 0], [10, 1]], duration=10.0)
        results = [s.select(0.0) for _ in range(200)]
        assert all(r == 'hanning' for r in results)

    def test_normalized_different_duration(self):
        """normalized con duration=30: elapsed=30 → blend=1 → 100% to."""
        s = self._make_normalized('hanning', 'bartlett', [[0, 0], [1, 1]], duration=30.0)
        results = [s.select(30.0) for _ in range(200)]
        assert all(r == 'bartlett' for r in results)


# =============================================================================
# 5. TransitionWindowStrategy - determinismo
# =============================================================================

class TestTransitionWindowStrategyDeterminism:

    def test_same_seed_same_sequence(self):
        s = TransitionWindowStrategy(
            from_window='hanning',
            to_window='bartlett',
            curve=Envelope([[0, 0], [10, 1]]),
            duration=10.0,
        )
        random_module.seed(77)
        seq1 = [s.select(5.0) for _ in range(100)]
        random_module.seed(77)
        seq2 = [s.select(5.0) for _ in range(100)]
        assert seq1 == seq2
