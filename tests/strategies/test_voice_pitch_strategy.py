# tests/strategies/test_voice_pitch_strategy.py
"""
test_voice_pitch_strategy.py

Suite TDD per voice_pitch_strategy.py

Moduli sotto test (da scrivere):
- VoicePitchStrategy (ABC)
- StepPitchStrategy    → voce i = i × step
- RangePitchStrategy   → distribuiti nell'intervallo [0, range]
- ChordPitchStrategy   → offsets da nome accordo, extend se num_voices > chord
- StochasticPitchStrategy → offset fisso per voce, seed deterministico
- VOICE_PITCH_STRATEGIES (registry dict)
- register_voice_pitch_strategy()
- VoicePitchStrategyFactory

Principi di design:
- Voce 0 restituisce SEMPRE 0.0 (riferimento immutato)
- Il valore restituito è un offset in SEMITONI
- StochasticPitchStrategy: seed = hash(stream_id + str(voice_index))
- ChordPitchStrategy: se num_voices > len(chord) → extend all'ottava superiore

Organizzazione:
  1.  VoicePitchStrategy ABC — interfaccia e contratto
  2.  StepPitchStrategy — distribuzione lineare per step
  3.  RangePitchStrategy — distribuzione nel range
  4.  ChordPitchStrategy — offsets da accordo nominale
  5.  ChordPitchStrategy extend — ottava superiore se num_voices > chord
  6.  StochasticPitchStrategy — offset deterministico per voce
  7.  Invariante voce 0 — tutte le strategy restituiscono 0.0
  8.  Edge cases — num_voices=1, step=0, range=0
  9.  VOICE_PITCH_STRATEGIES registry
  10. register_voice_pitch_strategy()
  11. VoicePitchStrategyFactory
"""

import pytest


# =============================================================================
# IMPORT LAZY
# =============================================================================

def _get_module():
    from strategies.voice_pitch_strategy import (
        VoicePitchStrategy,
        StepPitchStrategy,
        RangePitchStrategy,
        ChordPitchStrategy,
        StochasticPitchStrategy,
        VOICE_PITCH_STRATEGIES,
        register_voice_pitch_strategy,
        VoicePitchStrategyFactory,
    )
    return (
        VoicePitchStrategy,
        StepPitchStrategy,
        RangePitchStrategy,
        ChordPitchStrategy,
        StochasticPitchStrategy,
        VOICE_PITCH_STRATEGIES,
        register_voice_pitch_strategy,
        VoicePitchStrategyFactory,
    )


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(autouse=True)
def restore_registry():
    try:
        _, _, _, _, _, registry, _, _ = _get_module()
        original = dict(registry)
        yield
        registry.clear()
        registry.update(original)
    except ImportError:
        yield


# =============================================================================
# 1. VoicePitchStrategy ABC
# =============================================================================

class TestVoicePitchStrategyABC:

    def test_is_abstract(self):
        """VoicePitchStrategy non è istanziabile direttamente."""
        VoicePitchStrategy, *_ = _get_module()
        with pytest.raises(TypeError):
            VoicePitchStrategy()

    def test_get_pitch_offset_is_abstract(self):
        """get_pitch_offset deve essere abstractmethod."""
        VoicePitchStrategy, *_ = _get_module()
        assert hasattr(VoicePitchStrategy, 'get_pitch_offset')

    def test_concrete_must_implement_get_pitch_offset(self):
        """Sottoclasse senza get_pitch_offset non è istanziabile."""
        VoicePitchStrategy, *_ = _get_module()
        class Incomplete(VoicePitchStrategy):
            pass
        with pytest.raises(TypeError):
            Incomplete()

    def test_signature(self):
        """get_pitch_offset(voice_index, num_voices) → float."""
        VoicePitchStrategy, *_ = _get_module()
        import inspect
        sig = inspect.signature(VoicePitchStrategy.get_pitch_offset)
        params = list(sig.parameters.keys())
        assert 'voice_index' in params
        assert 'num_voices' in params


# =============================================================================
# 2. StepPitchStrategy
# =============================================================================

class TestStepPitchStrategy:

    def test_voice_0_returns_zero(self):
        _, StepPitchStrategy, *_ = _get_module()
        s = StepPitchStrategy(step=3.0)
        assert s.get_pitch_offset(voice_index=0, num_voices=4) == 0.0

    def test_voice_1_returns_one_step(self):
        _, StepPitchStrategy, *_ = _get_module()
        s = StepPitchStrategy(step=3.0)
        assert s.get_pitch_offset(voice_index=1, num_voices=4) == 3.0

    def test_voice_2_returns_two_steps(self):
        _, StepPitchStrategy, *_ = _get_module()
        s = StepPitchStrategy(step=3.0)
        assert s.get_pitch_offset(voice_index=2, num_voices=4) == 6.0

    def test_voice_3_returns_three_steps(self):
        _, StepPitchStrategy, *_ = _get_module()
        s = StepPitchStrategy(step=3.0)
        assert s.get_pitch_offset(voice_index=3, num_voices=4) == 9.0

    def test_negative_step(self):
        _, StepPitchStrategy, *_ = _get_module()
        s = StepPitchStrategy(step=-2.0)
        assert s.get_pitch_offset(voice_index=2, num_voices=4) == -4.0

    def test_step_zero_all_voices_zero(self):
        _, StepPitchStrategy, *_ = _get_module()
        s = StepPitchStrategy(step=0.0)
        for i in range(4):
            assert s.get_pitch_offset(voice_index=i, num_voices=4) == 0.0

    def test_fractional_step(self):
        _, StepPitchStrategy, *_ = _get_module()
        s = StepPitchStrategy(step=0.5)
        assert s.get_pitch_offset(voice_index=3, num_voices=4) == pytest.approx(1.5)

    def test_num_voices_one(self):
        _, StepPitchStrategy, *_ = _get_module()
        s = StepPitchStrategy(step=5.0)
        assert s.get_pitch_offset(voice_index=0, num_voices=1) == 0.0


# =============================================================================
# 3. RangePitchStrategy
# =============================================================================

class TestRangePitchStrategy:

    def test_voice_0_returns_zero(self):
        _, _, RangePitchStrategy, *_ = _get_module()
        s = RangePitchStrategy(semitone_range=12.0)
        assert s.get_pitch_offset(voice_index=0, num_voices=4) == 0.0

    def test_last_voice_returns_range(self):
        """Con 4 voci e range=12: voce 3 → 12.0."""
        _, _, RangePitchStrategy, *_ = _get_module()
        s = RangePitchStrategy(semitone_range=12.0)
        assert s.get_pitch_offset(voice_index=3, num_voices=4) == pytest.approx(12.0)

    def test_middle_voice_interpolated(self):
        """Con 4 voci e range=12: voce 1 → 4.0, voce 2 → 8.0."""
        _, _, RangePitchStrategy, *_ = _get_module()
        s = RangePitchStrategy(semitone_range=12.0)
        assert s.get_pitch_offset(voice_index=1, num_voices=4) == pytest.approx(4.0)
        assert s.get_pitch_offset(voice_index=2, num_voices=4) == pytest.approx(8.0)

    def test_two_voices_only_zero_and_range(self):
        _, _, RangePitchStrategy, *_ = _get_module()
        s = RangePitchStrategy(semitone_range=7.0)
        assert s.get_pitch_offset(voice_index=0, num_voices=2) == 0.0
        assert s.get_pitch_offset(voice_index=1, num_voices=2) == pytest.approx(7.0)

    def test_num_voices_one_returns_zero(self):
        _, _, RangePitchStrategy, *_ = _get_module()
        s = RangePitchStrategy(semitone_range=12.0)
        assert s.get_pitch_offset(voice_index=0, num_voices=1) == 0.0


# =============================================================================
# 4. ChordPitchStrategy — accordi nominali
# =============================================================================

class TestChordPitchStrategyKnownChords:

    def test_voice_0_always_zero(self):
        _, _, _, ChordPitchStrategy, *_ = _get_module()
        s = ChordPitchStrategy(chord="maj")
        assert s.get_pitch_offset(voice_index=0, num_voices=3) == 0.0

    def test_major_triad(self):
        """maj → [0, 4, 7]."""
        _, _, _, ChordPitchStrategy, *_ = _get_module()
        s = ChordPitchStrategy(chord="maj")
        assert s.get_pitch_offset(voice_index=0, num_voices=3) == 0
        assert s.get_pitch_offset(voice_index=1, num_voices=3) == 4
        assert s.get_pitch_offset(voice_index=2, num_voices=3) == 7

    def test_minor_triad(self):
        """min → [0, 3, 7]."""
        _, _, _, ChordPitchStrategy, *_ = _get_module()
        s = ChordPitchStrategy(chord="min")
        assert s.get_pitch_offset(voice_index=1, num_voices=3) == 3
        assert s.get_pitch_offset(voice_index=2, num_voices=3) == 7

    def test_dominant_seventh(self):
        """dom7 → [0, 4, 7, 10]."""
        _, _, _, ChordPitchStrategy, *_ = _get_module()
        s = ChordPitchStrategy(chord="dom7")
        assert s.get_pitch_offset(voice_index=1, num_voices=4) == 4
        assert s.get_pitch_offset(voice_index=2, num_voices=4) == 7
        assert s.get_pitch_offset(voice_index=3, num_voices=4) == 10

    def test_major_seventh(self):
        """maj7 → [0, 4, 7, 11]."""
        _, _, _, ChordPitchStrategy, *_ = _get_module()
        s = ChordPitchStrategy(chord="maj7")
        assert s.get_pitch_offset(voice_index=3, num_voices=4) == 11

    def test_minor_seventh(self):
        """min7 → [0, 3, 7, 10]."""
        _, _, _, ChordPitchStrategy, *_ = _get_module()
        s = ChordPitchStrategy(chord="min7")
        assert s.get_pitch_offset(voice_index=1, num_voices=4) == 3
        assert s.get_pitch_offset(voice_index=3, num_voices=4) == 10

    def test_unknown_chord_raises(self):
        _, _, _, ChordPitchStrategy, *_ = _get_module()
        with pytest.raises((ValueError, KeyError)):
            ChordPitchStrategy(chord="unknown_chord_xyz")


# =============================================================================
# 5. ChordPitchStrategy — extend all'ottava superiore
# =============================================================================

class TestChordPitchStrategyExtend:

    def test_dom7_5_voices_extends(self):
        """dom7 = [0,4,7,10]. Voce 4 → 12 (0+ottava)."""
        _, _, _, ChordPitchStrategy, *_ = _get_module()
        s = ChordPitchStrategy(chord="dom7")
        assert s.get_pitch_offset(voice_index=4, num_voices=6) == 12

    def test_dom7_6_voices_extends(self):
        """dom7. Voce 5 → 16 (4+ottava)."""
        _, _, _, ChordPitchStrategy, *_ = _get_module()
        s = ChordPitchStrategy(chord="dom7")
        assert s.get_pitch_offset(voice_index=5, num_voices=6) == 16

    def test_maj_triad_4_voices(self):
        """maj=[0,4,7]. Voce 3 → 12 (0+ottava)."""
        _, _, _, ChordPitchStrategy, *_ = _get_module()
        s = ChordPitchStrategy(chord="maj")
        assert s.get_pitch_offset(voice_index=3, num_voices=4) == 12

    def test_maj_triad_7_voices_two_octaves(self):
        """maj=[0,4,7]. Voci 3-5 = [12,16,19]. Voce 6 = 24 (0+2 ottave)."""
        _, _, _, ChordPitchStrategy, *_ = _get_module()
        s = ChordPitchStrategy(chord="maj")
        assert s.get_pitch_offset(voice_index=5, num_voices=7) == 19
        assert s.get_pitch_offset(voice_index=6, num_voices=7) == 24


# =============================================================================
# 6. StochasticPitchStrategy
# =============================================================================

class TestStochasticPitchStrategy:

    def test_voice_0_always_zero(self):
        _, _, _, _, StochasticPitchStrategy, *_ = _get_module()
        s = StochasticPitchStrategy(semitone_range=2.0, stream_id="s1")
        assert s.get_pitch_offset(voice_index=0, num_voices=4) == 0.0

    def test_offset_within_range(self):
        _, _, _, _, StochasticPitchStrategy, *_ = _get_module()
        s = StochasticPitchStrategy(semitone_range=3.0, stream_id="s1")
        for i in range(1, 8):
            offset = s.get_pitch_offset(voice_index=i, num_voices=8)
            assert -3.0 <= offset <= 3.0

    def test_deterministic_same_stream(self):
        """Stesso stream_id e voice_index → stesso offset."""
        _, _, _, _, StochasticPitchStrategy, *_ = _get_module()
        s1 = StochasticPitchStrategy(semitone_range=5.0, stream_id="my_stream")
        s2 = StochasticPitchStrategy(semitone_range=5.0, stream_id="my_stream")
        for i in range(1, 5):
            assert s1.get_pitch_offset(i, 5) == s2.get_pitch_offset(i, 5)

    def test_different_stream_ids_different_offsets(self):
        """stream_id diversi → offsets diversi (con alta probabilità)."""
        _, _, _, _, StochasticPitchStrategy, *_ = _get_module()
        s1 = StochasticPitchStrategy(semitone_range=5.0, stream_id="stream_A")
        s2 = StochasticPitchStrategy(semitone_range=5.0, stream_id="stream_B")
        offsets1 = [s1.get_pitch_offset(i, 4) for i in range(1, 4)]
        offsets2 = [s2.get_pitch_offset(i, 4) for i in range(1, 4)]
        assert offsets1 != offsets2

    def test_different_voices_different_offsets(self):
        """voice_index diversi → offsets diversi (con alta probabilità)."""
        _, _, _, _, StochasticPitchStrategy, *_ = _get_module()
        s = StochasticPitchStrategy(semitone_range=5.0, stream_id="s1")
        offsets = [s.get_pitch_offset(i, 6) for i in range(1, 6)]
        assert len(set(offsets)) > 1

    def test_range_zero_all_zero(self):
        _, _, _, _, StochasticPitchStrategy, *_ = _get_module()
        s = StochasticPitchStrategy(semitone_range=0.0, stream_id="s1")
        for i in range(4):
            assert s.get_pitch_offset(i, 4) == 0.0


# =============================================================================
# 7. Invariante voce 0 — tutte le strategy
# =============================================================================

class TestVoiceZeroInvariant:

    @pytest.mark.parametrize("strategy_fixture", [
        lambda m: m[1](step=3.0),                            # StepPitchStrategy
        lambda m: m[2](semitone_range=12.0),                  # RangePitchStrategy
        lambda m: m[3](chord="dom7"),                         # ChordPitchStrategy
        lambda m: m[4](semitone_range=2.0, stream_id="s1"),   # StochasticPitchStrategy
    ])
    def test_voice_0_is_always_zero(self, strategy_fixture):
        mod = _get_module()
        strategy = strategy_fixture(mod)
        assert strategy.get_pitch_offset(voice_index=0, num_voices=4) == 0.0


# =============================================================================
# 8. Edge cases
# =============================================================================

class TestEdgeCases:

    def test_step_num_voices_1(self):
        _, StepPitchStrategy, *_ = _get_module()
        s = StepPitchStrategy(step=7.0)
        assert s.get_pitch_offset(0, 1) == 0.0

    def test_range_num_voices_1(self):
        _, _, RangePitchStrategy, *_ = _get_module()
        s = RangePitchStrategy(semitone_range=12.0)
        assert s.get_pitch_offset(0, 1) == 0.0

    def test_chord_num_voices_1(self):
        _, _, _, ChordPitchStrategy, *_ = _get_module()
        s = ChordPitchStrategy(chord="maj")
        assert s.get_pitch_offset(0, 1) == 0.0


# =============================================================================
# 9. VOICE_PITCH_STRATEGIES registry
# =============================================================================

class TestVoicePitchStrategiesRegistry:

    def test_registry_exists(self):
        *_, VOICE_PITCH_STRATEGIES, _, _ = _get_module()
        assert isinstance(VOICE_PITCH_STRATEGIES, dict)

    def test_registry_contains_step(self):
        *_, VOICE_PITCH_STRATEGIES, _, _ = _get_module()
        assert 'step' in VOICE_PITCH_STRATEGIES

    def test_registry_contains_range(self):
        *_, VOICE_PITCH_STRATEGIES, _, _ = _get_module()
        assert 'range' in VOICE_PITCH_STRATEGIES

    def test_registry_contains_chord(self):
        *_, VOICE_PITCH_STRATEGIES, _, _ = _get_module()
        assert 'chord' in VOICE_PITCH_STRATEGIES

    def test_registry_contains_stochastic(self):
        *_, VOICE_PITCH_STRATEGIES, _, _ = _get_module()
        assert 'stochastic' in VOICE_PITCH_STRATEGIES

    def test_registry_values_are_classes(self):
        *_, VOICE_PITCH_STRATEGIES, _, _ = _get_module()
        for name, cls in VOICE_PITCH_STRATEGIES.items():
            assert isinstance(cls, type), f"{name} non è una classe"


# =============================================================================
# 10. register_voice_pitch_strategy()
# =============================================================================

class TestRegisterVoicePitchStrategy:

    def test_register_new_strategy(self):
        VoicePitchStrategy, _, _, _, _, VOICE_PITCH_STRATEGIES, register_voice_pitch_strategy, _ = _get_module()

        class MySemitoneStrategy(VoicePitchStrategy):
            def get_pitch_offset(self, voice_index, num_voices):
                return float(voice_index * 2)

        register_voice_pitch_strategy('my_semi', MySemitoneStrategy)
        assert 'my_semi' in VOICE_PITCH_STRATEGIES

    def test_registered_strategy_usable_via_factory(self):
        VoicePitchStrategy, _, _, _, _, VOICE_PITCH_STRATEGIES, register_voice_pitch_strategy, VoicePitchStrategyFactory = _get_module()

        class FixedStrategy(VoicePitchStrategy):
            def get_pitch_offset(self, voice_index, num_voices):
                return 99.0 if voice_index > 0 else 0.0

        register_voice_pitch_strategy('fixed99', FixedStrategy)
        s = VoicePitchStrategyFactory.create('fixed99')
        assert s.get_pitch_offset(1, 2) == 99.0


# =============================================================================
# 11. VoicePitchStrategyFactory
# =============================================================================

class TestVoicePitchStrategyFactory:

    def test_create_step(self):
        *_, VoicePitchStrategyFactory = _get_module()
        _, StepPitchStrategy, *_ = _get_module()
        s = VoicePitchStrategyFactory.create('step', step=4.0)
        assert isinstance(s, StepPitchStrategy)

    def test_create_range(self):
        *_, VoicePitchStrategyFactory = _get_module()
        _, _, RangePitchStrategy, *_ = _get_module()
        s = VoicePitchStrategyFactory.create('range', semitone_range=12.0)
        assert isinstance(s, RangePitchStrategy)

    def test_create_chord(self):
        *_, VoicePitchStrategyFactory = _get_module()
        _, _, _, ChordPitchStrategy, *_ = _get_module()
        s = VoicePitchStrategyFactory.create('chord', chord='maj7')
        assert isinstance(s, ChordPitchStrategy)

    def test_create_stochastic(self):
        *_, VoicePitchStrategyFactory = _get_module()
        _, _, _, _, StochasticPitchStrategy, *_ = _get_module()
        s = VoicePitchStrategyFactory.create('stochastic', semitone_range=2.0, stream_id='s1')
        assert isinstance(s, StochasticPitchStrategy)

    def test_unknown_strategy_raises(self):
        *_, VoicePitchStrategyFactory = _get_module()
        with pytest.raises((KeyError, ValueError)):
            VoicePitchStrategyFactory.create('nonexistent_xyz')

    def test_factory_returns_voice_pitch_strategy_instance(self):
        VoicePitchStrategy, *_, VoicePitchStrategyFactory = _get_module()
        s = VoicePitchStrategyFactory.create('step', step=1.0)
        assert isinstance(s, VoicePitchStrategy)
