# tests/strategies/test_grain_clip_strategy.py
"""
Suite TDD per grain_clip_strategy.py

Plan riferimento: docs/plans/2026-05-03-001-fix-grain-clip-strategy-plan.md (U1)

Moduli sotto test:
- GrainClipStrategy (ABC)
- OverflowMarginClipStrategy(margin=0.0)  default
- PassthroughClipStrategy
- GRAIN_CLIP_STRATEGIES (registry)
- GrainClipStrategyFactory.create

Contratto:
- strategy.apply(voices, stream) -> List[List[Grain]]
- voices: List[List[Grain]] (struttura per-voce)
- stream: oggetto con `.onset` e `.duration` (float, secondi)
"""

import pytest
from types import SimpleNamespace

from pge.core.grain import Grain


def make_grain(onset: float, duration: float = 0.05) -> Grain:
    """Helper per costruire grain minimi con valori validi."""
    return Grain(
        onset=onset,
        duration=duration,
        pointer_pos=0.0,
        pitch_ratio=1.0,
        volume=1.0,
        pan=0.5,
        sample_table=1,
        envelope_table=2,
    )


def make_stream(onset: float = 0.0, duration: float = 1.0):
    return SimpleNamespace(onset=onset, duration=duration)


# =============================================================================
# 1. OverflowMarginClipStrategy — comportamento base
# =============================================================================

class TestOverflowMarginClipStrategy:

    def test_grain_completely_inside_stream_is_kept(self):
        from pge.strategies.grain_clip_strategy import OverflowMarginClipStrategy
        strategy = OverflowMarginClipStrategy(margin=0.0)
        stream = make_stream(onset=0.0, duration=1.0)
        grain = make_grain(onset=0.5, duration=0.05)

        result = strategy.apply([[grain]], stream)

        assert result == [[grain]]

    def test_grain_with_onset_at_or_past_stream_end_is_excluded(self):
        """R1: grain.onset >= stream_end -> escluso (strict <)."""
        from pge.strategies.grain_clip_strategy import OverflowMarginClipStrategy
        strategy = OverflowMarginClipStrategy(margin=0.0)
        stream = make_stream(onset=0.0, duration=1.0)
        g_at = make_grain(onset=1.0, duration=0.05)
        g_past = make_grain(onset=1.5, duration=0.05)

        result = strategy.apply([[g_at, g_past]], stream)

        assert result == [[]]

    def test_grain_tail_overflows_with_zero_margin_is_excluded(self):
        """R2: onset < stream_end ma onset+duration > stream_end+margin (margin=0) -> escluso."""
        from pge.strategies.grain_clip_strategy import OverflowMarginClipStrategy
        strategy = OverflowMarginClipStrategy(margin=0.0)
        stream = make_stream(onset=0.0, duration=1.0)
        grain = make_grain(onset=0.99, duration=0.05)  # tail = 1.04 > 1.0

        result = strategy.apply([[grain]], stream)

        assert result == [[]]

    def test_grain_tail_within_margin_is_kept(self):
        """Grain coda dentro margin -> incluso."""
        from pge.strategies.grain_clip_strategy import OverflowMarginClipStrategy
        strategy = OverflowMarginClipStrategy(margin=0.5)
        stream = make_stream(onset=0.0, duration=1.0)
        grain = make_grain(onset=0.99, duration=0.05)  # tail 1.04 <= 1.5

        result = strategy.apply([[grain]], stream)

        assert result == [[grain]]

    def test_grain_tail_exactly_equals_stream_end_is_kept(self):
        """Boundary: onset + duration == stream_end -> incluso (<= su limit)."""
        from pge.strategies.grain_clip_strategy import OverflowMarginClipStrategy
        strategy = OverflowMarginClipStrategy(margin=0.0)
        stream = make_stream(onset=0.0, duration=1.0)
        grain = make_grain(onset=0.95, duration=0.05)  # tail = 1.0 esatto

        result = strategy.apply([[grain]], stream)

        assert result == [[grain]]

    def test_empty_voice_returns_empty(self):
        from pge.strategies.grain_clip_strategy import OverflowMarginClipStrategy
        strategy = OverflowMarginClipStrategy(margin=0.0)
        stream = make_stream(onset=0.0, duration=1.0)

        result = strategy.apply([[]], stream)

        assert result == [[]]

    def test_filters_each_voice_independently(self):
        """Multi-voice: solo voice non valide filtrate, struttura preservata."""
        from pge.strategies.grain_clip_strategy import OverflowMarginClipStrategy
        strategy = OverflowMarginClipStrategy(margin=0.0)
        stream = make_stream(onset=0.0, duration=1.0)
        v0_keep = make_grain(onset=0.1, duration=0.05)
        v1_keep = make_grain(onset=0.2, duration=0.05)
        v1_drop = make_grain(onset=2.0, duration=0.05)

        result = strategy.apply([[v0_keep], [v1_keep, v1_drop]], stream)

        assert result == [[v0_keep], [v1_keep]]

    def test_stream_with_nonzero_onset(self):
        """stream.onset != 0: bounds calcolati su offset assoluto."""
        from pge.strategies.grain_clip_strategy import OverflowMarginClipStrategy
        strategy = OverflowMarginClipStrategy(margin=0.0)
        stream = make_stream(onset=10.0, duration=1.0)  # stream_end=11.0
        g_in = make_grain(onset=10.5, duration=0.05)
        g_out = make_grain(onset=11.5, duration=0.05)

        result = strategy.apply([[g_in, g_out]], stream)

        assert result == [[g_in]]


# =============================================================================
# 2. PassthroughClipStrategy
# =============================================================================

class TestPassthroughClipStrategy:

    def test_passes_all_grains_unchanged(self):
        """R5: tutti i grain restituiti, inclusi quelli che sforano."""
        from pge.strategies.grain_clip_strategy import PassthroughClipStrategy
        strategy = PassthroughClipStrategy()
        stream = make_stream(onset=0.0, duration=1.0)
        g_in = make_grain(onset=0.1)
        g_tail = make_grain(onset=0.99, duration=0.5)
        g_out = make_grain(onset=5.0)

        result = strategy.apply([[g_in, g_tail, g_out]], stream)

        assert result == [[g_in, g_tail, g_out]]

    def test_preserves_voice_structure(self):
        from pge.strategies.grain_clip_strategy import PassthroughClipStrategy
        strategy = PassthroughClipStrategy()
        stream = make_stream()
        voices = [[make_grain(0.1)], [], [make_grain(0.2), make_grain(5.0)]]

        result = strategy.apply(voices, stream)

        assert len(result) == 3
        assert result[0] == voices[0]
        assert result[1] == []
        assert result[2] == voices[2]


# =============================================================================
# 3. Registry + Factory
# =============================================================================

class TestGrainClipStrategyFactory:

    def test_creates_overflow_margin_default(self):
        from pge.strategies.grain_clip_strategy import (
            GrainClipStrategyFactory, OverflowMarginClipStrategy,
        )
        s = GrainClipStrategyFactory.create('overflow_margin')
        assert isinstance(s, OverflowMarginClipStrategy)
        assert s.margin == 0.0

    def test_creates_overflow_margin_with_margin(self):
        from pge.strategies.grain_clip_strategy import GrainClipStrategyFactory
        s = GrainClipStrategyFactory.create('overflow_margin', margin=1.0)
        assert s.margin == 1.0

    def test_creates_passthrough(self):
        from pge.strategies.grain_clip_strategy import (
            GrainClipStrategyFactory, PassthroughClipStrategy,
        )
        s = GrainClipStrategyFactory.create('passthrough')
        assert isinstance(s, PassthroughClipStrategy)

    def test_unknown_name_raises(self):
        from pge.strategies.grain_clip_strategy import GrainClipStrategyFactory
        with pytest.raises(ValueError, match="grain_clip"):
            GrainClipStrategyFactory.create('bogus')

    def test_registry_contains_both_strategies(self):
        from pge.strategies.grain_clip_strategy import GRAIN_CLIP_STRATEGIES
        assert 'overflow_margin' in GRAIN_CLIP_STRATEGIES
        assert 'passthrough' in GRAIN_CLIP_STRATEGIES
