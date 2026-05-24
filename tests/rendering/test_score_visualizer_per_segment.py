"""
Test rendering per-segmento envelope (issue #68).

Verifica che il visualizer rilevi envelope con strategie eterogenee
(misto step/linear/cubic) e adatti il rendering per-segmento.
"""

import sys
import types
from unittest.mock import MagicMock

import matplotlib
matplotlib.use('Agg')

# Block heavy deps
sys.modules.setdefault('soundfile', types.ModuleType('soundfile'))

from envelopes.envelope import Envelope
from envelopes.envelope_interpolation import (
    StepInterpolation, LinearInterpolation, CubicInterpolation
)
from rendering.score_visualizer import ScoreVisualizer


class TestHeterogeneousDetection:
    """Helper rileva envelope con strategie miste."""

    def test_uniform_linear_not_heterogeneous(self):
        env = Envelope([[0, 0], [1, 1]])
        assert ScoreVisualizer._is_per_segment_heterogeneous(env) is False

    def test_uniform_step_global_not_heterogeneous(self):
        env = Envelope({'type': 'step', 'points': [[0, 0], [0.5, 1], [1, 0]]})
        assert ScoreVisualizer._is_per_segment_heterogeneous(env) is False

    def test_per_point_mixed_is_heterogeneous(self):
        env = Envelope([[0, 0, 'step'], [0.5, 1, 'linear'], [1, 0]])
        assert ScoreVisualizer._is_per_segment_heterogeneous(env) is True

    def test_per_point_all_same_strategy_not_heterogeneous(self):
        env = Envelope([[0, 0, 'step'], [0.5, 1, 'step'], [1, 0]])
        assert ScoreVisualizer._is_per_segment_heterogeneous(env) is False


class TestSegmentStrategyName:
    """Helper mappa strategy a nome canonico."""

    def test_step_strategy_name(self):
        seg = MagicMock()
        seg.strategy = StepInterpolation()
        assert ScoreVisualizer._segment_strategy_name(seg) == 'step'

    def test_linear_strategy_name(self):
        seg = MagicMock()
        seg.strategy = LinearInterpolation()
        assert ScoreVisualizer._segment_strategy_name(seg) == 'linear'

    def test_cubic_strategy_name(self):
        seg = MagicMock()
        seg.strategy = CubicInterpolation()
        assert ScoreVisualizer._segment_strategy_name(seg) == 'cubic'


class TestPerSegmentDrawing:
    """_draw_envelopes con envelope eterogeneo invoca rendering per-segmento."""

    def _make_stream(self, env):
        stream = MagicMock()
        stream.onset = 0.0
        stream.duration = 1.0
        stream.density = env
        return stream

    def _make_viz(self):
        import matplotlib.pyplot as plt
        viz = ScoreVisualizer.__new__(ScoreVisualizer)
        viz.config = {
            'envelope_ranges': {'density': (0, 100)},
            'envelope_colors': {'density': '#000000'},
        }
        viz._get_stream_envelopes = lambda s: {'density': s.density}
        viz._normalize_envelope_value = lambda name, v: v / 100.0
        viz._annotate_breakpoints = lambda *a, **k: None
        fig, ax = plt.subplots()
        return viz, ax

    def test_heterogeneous_envelope_draws_multiple_lines(self):
        # Per-segmento misto: dispatch per-strategy → almeno 1 plot per segmento
        env = Envelope([[0, 0, 'step'], [0.5, 1, 'linear'], [1, 0]])
        stream = self._make_stream(env)
        viz, ax = self._make_viz()
        viz._draw_envelopes(ax, stream, 0.0, 1.0, 0.0, 1.0)
        # Almeno 2 chiamate plot (una per segmento step + una per linear)
        assert len(ax.lines) >= 2

    def test_uniform_linear_unchanged(self):
        # Uniforme: 1 sola line come prima del fix
        env = Envelope([[0, 0], [0.5, 1], [1, 0]])
        stream = self._make_stream(env)
        viz, ax = self._make_viz()
        viz._draw_envelopes(ax, stream, 0.0, 1.0, 0.0, 1.0)
        assert len(ax.lines) == 1
