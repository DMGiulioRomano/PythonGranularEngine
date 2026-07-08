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

from pge.envelopes.envelope import Envelope
from pge.envelopes.envelope_interpolation import (
    StepInterpolation, LinearInterpolation, CubicInterpolation
)
from pge.rendering.score_visualizer import ScoreVisualizer


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
            'envelope_display': {'pad_ratio': 0.05, 'samples': 128},
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

    def test_linear_segment_after_step_boundary_renders_diagonal(self):
        # Bug: precisione float al boundary step→linear faceva collassare v_a
        # al valore del segmento step precedente (hold-left), producendo linea
        # orizzontale invece di diagonale.
        # Repro: stream_start grande (precisione persa) + compact 3 reps con
        # pattern step→linear→step→linear→step→linear.
        from pge.envelopes.envelope import create_scaled_envelope
        env = create_scaled_envelope(
            [[[0, 5, 'step'], [50, 30, 'linear'], [100, 5]], 1.0, 3, 'cubic'],
            duration=4.0,
            time_mode='normalized',
        )
        stream = MagicMock()
        stream.onset = 65.0
        stream.duration = 4.0
        stream.density = env

        viz, ax = self._make_viz()
        viz.config['envelope_ranges'] = {'density': (0, 100)}
        viz._normalize_envelope_value = lambda name, v: v / 100.0

        viz._draw_envelope_per_segment(
            ax, env, 'density', '#000000',
            stream_start=65.0, y_base=0.0, y_height=1.0,
            t_start=65.0, t_end=69.0,
        )

        # Per ogni segmento linear, raccogli (y_a, y_b) della linea disegnata.
        # Linear: bp[0]=30, bp[-1]=5 (post-scaling: tempi diversi, valori uguali).
        # Y atteso: y_a = 0.30, y_b = 0.05 (diagonale).
        linear_segs = [s for s in env.segments
                       if type(s.strategy).__name__ == 'LinearInterpolation']
        assert len(linear_segs) == 3

        # Ogni linear segment deve produrre linea diagonale (y_a > y_b)
        # con y_a ≈ 0.30 (da v=30) e y_b ≈ 0.05 (da v=5).
        linear_lines = []
        for line in ax.lines:
            xs, ys = line.get_xdata(), line.get_ydata()
            if len(xs) == 2 and xs[0] != xs[1] and abs(ys[0] - ys[1]) > 1e-6:
                linear_lines.append((xs, ys))

        # Devono esserci 3 linee diagonali (una per linear segment)
        assert len(linear_lines) >= 3, (
            f"Atteso almeno 3 linee diagonali (una per linear segment), "
            f"trovate {len(linear_lines)}. ax.lines={[(l.get_xdata().tolist(), l.get_ydata().tolist()) for l in ax.lines]}"
        )

        # Ogni linea diagonale linear deve andare da y≈0.30 a y≈0.05
        for xs, ys in linear_lines:
            assert abs(ys[0] - 0.30) < 1e-3, f"y_a atteso ≈ 0.30, ottenuto {ys[0]}"
            assert abs(ys[1] - 0.05) < 1e-3, f"y_b atteso ≈ 0.05, ottenuto {ys[1]}"
