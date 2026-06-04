# tests/strategies/test_voice_pitch_strategy.py
"""
test_voice_pitch_strategy.py

Suite TDD per voice_pitch_strategy.py

Moduli sotto test:
- VoicePitchStrategy (ABC)
- StepPitchStrategy    → voce i = materialize(i, step(t))
- RangePitchStrategy   → distribuiti nell'intervallo, materialize(i/(n-1), range)
- ChordPitchStrategy   → offsets da nome accordo, extend se num_voices > chord
- StochasticPitchStrategy → fattore per voce, seed deterministico, magnitudine time-varying
- VOICE_PITCH_STRATEGIES (registry dict)
- register_voice_pitch_strategy()
- VoicePitchStrategyFactory

Principi di design (contratto unit-driven):
- Voce 0 restituisce SEMPRE 1.0 (riferimento immutato = ratio identità)
- Il valore restituito è un FATTORE DI RATIO prodotto via PitchUnit
- get_pitch_factor(voice_index, num_voices, time, unit) — time + unit required
- Per le unità EDO il fattore equivale a 2^(offset_semitoni/divisions): i test
  asseriscono in semitoni convertendo il fattore con l'helper `_st`.
- StochasticPitchStrategy: cache memorizza fattore normalizzato [-1,1]

Organizzazione:
  1.  VoicePitchStrategy ABC — interfaccia e contratto
  2.  StepPitchStrategy — distribuzione lineare per step
  3.  RangePitchStrategy — distribuzione nel range
  4.  ChordPitchStrategy — offsets da accordo nominale
  5.  ChordPitchStrategy extend — ottava superiore se num_voices > chord
  6.  StochasticPitchStrategy — fattore deterministico per voce
  7.  Invariante voce 0 — tutte le strategy restituiscono 1.0
  8.  Edge cases — num_voices=1, step=0, range=0
  9.  VOICE_PITCH_STRATEGIES registry
  10. register_voice_pitch_strategy()
  11. VoicePitchStrategyFactory
  12. Parametri dinamici (Envelope)
  13. Geometria ratio — step/range/stochastic sotto unit: ratio
"""

import math

import pytest

from parameters.pitch_unit import EdoUnit, RatioUnit


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
        SpectralPitchStrategy,
    )
    return (
        VoicePitchStrategy,       # m[0]
        StepPitchStrategy,        # m[1]
        RangePitchStrategy,       # m[2]
        ChordPitchStrategy,       # m[3]
        StochasticPitchStrategy,  # m[4]
        VOICE_PITCH_STRATEGIES,   # m[5]
        register_voice_pitch_strategy,  # m[6]
        VoicePitchStrategyFactory,      # m[7]
        SpectralPitchStrategy,          # m[8]
    )


# =============================================================================
# HELPERS — fattore di ratio <-> semitoni (EDO 12)
# =============================================================================

ST = EdoUnit(12)  # unità di default per i test in semitoni


def _factor(s, vi, nv, t, unit=ST):
    """Chiama il nuovo contratto get_pitch_factor con un'unità esplicita."""
    return s.get_pitch_factor(vi, nv, t, unit)


def _st(s, vi, nv, t, unit=ST):
    """Fattore di ratio -> offset in semitoni (inversa di EDO12).

    Voce identità (factor 1.0) -> 0.0 semitoni.
    """
    f = _factor(s, vi, nv, t, unit)
    return 0.0 if f == 1.0 else round(12.0 * math.log2(f), 9)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(autouse=True)
def restore_registry():
    try:
        _, _, _, _, _, registry, _, _, _ = _get_module()
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

    def test_get_pitch_factor_is_abstract(self):
        """get_pitch_factor deve essere abstractmethod."""
        VoicePitchStrategy, *_ = _get_module()
        assert hasattr(VoicePitchStrategy, 'get_pitch_factor')

    def test_concrete_must_implement_get_pitch_factor(self):
        """Sottoclasse senza get_pitch_factor non è istanziabile."""
        VoicePitchStrategy, *_ = _get_module()
        class Incomplete(VoicePitchStrategy):
            pass
        with pytest.raises(TypeError):
            Incomplete()

    def test_signature(self):
        """get_pitch_factor(voice_index, num_voices, time, unit) → float."""
        VoicePitchStrategy, *_ = _get_module()
        import inspect
        sig = inspect.signature(VoicePitchStrategy.get_pitch_factor)
        params = list(sig.parameters.keys())
        assert 'voice_index' in params
        assert 'num_voices' in params
        assert 'time' in params
        assert 'unit' in params


# =============================================================================
# 2. StepPitchStrategy
# =============================================================================

class TestStepPitchStrategy:

    def test_voice_0_returns_identity(self):
        _, StepPitchStrategy, *_ = _get_module()
        s = StepPitchStrategy(step=3.0)
        assert _factor(s, 0, 4, 0.0) == 1.0

    def test_voice_1_returns_one_step(self):
        _, StepPitchStrategy, *_ = _get_module()
        s = StepPitchStrategy(step=3.0)
        assert _st(s, 1, 4, 0.0) == pytest.approx(3.0)

    def test_voice_2_returns_two_steps(self):
        _, StepPitchStrategy, *_ = _get_module()
        s = StepPitchStrategy(step=3.0)
        assert _st(s, 2, 4, 0.0) == pytest.approx(6.0)

    def test_voice_3_returns_three_steps(self):
        _, StepPitchStrategy, *_ = _get_module()
        s = StepPitchStrategy(step=3.0)
        assert _st(s, 3, 4, 0.0) == pytest.approx(9.0)

    def test_negative_step(self):
        _, StepPitchStrategy, *_ = _get_module()
        s = StepPitchStrategy(step=-2.0)
        assert _st(s, 2, 4, 0.0) == pytest.approx(-4.0)

    def test_step_zero_all_voices_identity(self):
        _, StepPitchStrategy, *_ = _get_module()
        s = StepPitchStrategy(step=0.0)
        for i in range(4):
            assert _factor(s, i, 4, 0.0) == pytest.approx(1.0)

    def test_fractional_step(self):
        _, StepPitchStrategy, *_ = _get_module()
        s = StepPitchStrategy(step=0.5)
        assert _st(s, 3, 4, 0.0) == pytest.approx(1.5)

    def test_num_voices_one(self):
        _, StepPitchStrategy, *_ = _get_module()
        s = StepPitchStrategy(step=5.0)
        assert _factor(s, 0, 1, 0.0) == 1.0


# =============================================================================
# 3. RangePitchStrategy
# =============================================================================

class TestRangePitchStrategy:

    def test_voice_0_returns_identity(self):
        _, _, RangePitchStrategy, *_ = _get_module()
        s = RangePitchStrategy(pitch_range=12.0)
        assert _factor(s, 0, 4, 0.0) == 1.0

    def test_last_voice_returns_range(self):
        """Con 4 voci e range=12: voce 3 → 12.0 semitoni."""
        _, _, RangePitchStrategy, *_ = _get_module()
        s = RangePitchStrategy(pitch_range=12.0)
        assert _st(s, 3, 4, 0.0) == pytest.approx(12.0)

    def test_middle_voice_interpolated(self):
        """Con 4 voci e range=12: voce 1 → 4.0, voce 2 → 8.0."""
        _, _, RangePitchStrategy, *_ = _get_module()
        s = RangePitchStrategy(pitch_range=12.0)
        assert _st(s, 1, 4, 0.0) == pytest.approx(4.0)
        assert _st(s, 2, 4, 0.0) == pytest.approx(8.0)

    def test_two_voices_only_zero_and_range(self):
        _, _, RangePitchStrategy, *_ = _get_module()
        s = RangePitchStrategy(pitch_range=7.0)
        assert _factor(s, 0, 2, 0.0) == 1.0
        assert _st(s, 1, 2, 0.0) == pytest.approx(7.0)

    def test_num_voices_one_returns_identity(self):
        _, _, RangePitchStrategy, *_ = _get_module()
        s = RangePitchStrategy(pitch_range=12.0)
        assert _factor(s, 0, 1, 0.0) == 1.0


# =============================================================================
# 4. ChordPitchStrategy — accordi nominali
# =============================================================================

class TestChordPitchStrategyKnownChords:

    def test_voice_0_always_identity(self):
        _, _, _, ChordPitchStrategy, *_ = _get_module()
        s = ChordPitchStrategy(chord="maj")
        assert _factor(s, 0, 3, 0.0) == 1.0

    def test_major_triad(self):
        """maj → [0, 4, 7]."""
        _, _, _, ChordPitchStrategy, *_ = _get_module()
        s = ChordPitchStrategy(chord="maj")
        assert _st(s, 0, 3, 0.0) == pytest.approx(0)
        assert _st(s, 1, 3, 0.0) == pytest.approx(4)
        assert _st(s, 2, 3, 0.0) == pytest.approx(7)

    def test_minor_triad(self):
        """min → [0, 3, 7]."""
        _, _, _, ChordPitchStrategy, *_ = _get_module()
        s = ChordPitchStrategy(chord="min")
        assert _st(s, 1, 3, 0.0) == pytest.approx(3)
        assert _st(s, 2, 3, 0.0) == pytest.approx(7)

    def test_dominant_seventh(self):
        """dom7 → [0, 4, 7, 10]."""
        _, _, _, ChordPitchStrategy, *_ = _get_module()
        s = ChordPitchStrategy(chord="dom7")
        assert _st(s, 1, 4, 0.0) == pytest.approx(4)
        assert _st(s, 2, 4, 0.0) == pytest.approx(7)
        assert _st(s, 3, 4, 0.0) == pytest.approx(10)

    def test_major_seventh(self):
        """maj7 → [0, 4, 7, 11]."""
        _, _, _, ChordPitchStrategy, *_ = _get_module()
        s = ChordPitchStrategy(chord="maj7")
        assert _st(s, 3, 4, 0.0) == pytest.approx(11)

    def test_minor_seventh(self):
        """min7 → [0, 3, 7, 10]."""
        _, _, _, ChordPitchStrategy, *_ = _get_module()
        s = ChordPitchStrategy(chord="min7")
        assert _st(s, 1, 4, 0.0) == pytest.approx(3)
        assert _st(s, 3, 4, 0.0) == pytest.approx(10)

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
        assert _st(s, 4, 6, 0.0) == pytest.approx(12)

    def test_dom7_6_voices_extends(self):
        """dom7. Voce 5 → 16 (4+ottava)."""
        _, _, _, ChordPitchStrategy, *_ = _get_module()
        s = ChordPitchStrategy(chord="dom7")
        assert _st(s, 5, 6, 0.0) == pytest.approx(16)

    def test_maj_triad_4_voices(self):
        """maj=[0,4,7]. Voce 3 → 12 (0+ottava)."""
        _, _, _, ChordPitchStrategy, *_ = _get_module()
        s = ChordPitchStrategy(chord="maj")
        assert _st(s, 3, 4, 0.0) == pytest.approx(12)

    def test_maj_triad_7_voices_two_octaves(self):
        """maj=[0,4,7]. Voci 3-5 = [12,16,19]. Voce 6 = 24 (0+2 ottave)."""
        _, _, _, ChordPitchStrategy, *_ = _get_module()
        s = ChordPitchStrategy(chord="maj")
        assert _st(s, 5, 7, 0.0) == pytest.approx(19)
        assert _st(s, 6, 7, 0.0) == pytest.approx(24)


# =============================================================================
# 6. StochasticPitchStrategy
# =============================================================================

class TestStochasticPitchStrategy:

    def test_voice_0_always_identity(self):
        _, _, _, _, StochasticPitchStrategy, *_ = _get_module()
        s = StochasticPitchStrategy(pitch_range=2.0, stream_id="s1")
        assert _factor(s, 0, 4, 0.0) == 1.0

    def test_offset_within_range(self):
        _, _, _, _, StochasticPitchStrategy, *_ = _get_module()
        s = StochasticPitchStrategy(pitch_range=3.0, stream_id="s1")
        for i in range(1, 8):
            offset = _st(s, i, 8, 0.0)
            assert -3.0 <= offset <= 3.0

    def test_deterministic_same_stream(self):
        """Stesso stream_id e voice_index → stesso fattore."""
        _, _, _, _, StochasticPitchStrategy, *_ = _get_module()
        s1 = StochasticPitchStrategy(pitch_range=5.0, stream_id="my_stream")
        s2 = StochasticPitchStrategy(pitch_range=5.0, stream_id="my_stream")
        for i in range(1, 5):
            assert _factor(s1, i, 5, 0.0) == _factor(s2, i, 5, 0.0)

    def test_different_stream_ids_different_offsets(self):
        """stream_id diversi → offsets diversi (con alta probabilità)."""
        _, _, _, _, StochasticPitchStrategy, *_ = _get_module()
        s1 = StochasticPitchStrategy(pitch_range=5.0, stream_id="stream_A")
        s2 = StochasticPitchStrategy(pitch_range=5.0, stream_id="stream_B")
        offsets1 = [_factor(s1, i, 4, 0.0) for i in range(1, 4)]
        offsets2 = [_factor(s2, i, 4, 0.0) for i in range(1, 4)]
        assert offsets1 != offsets2

    def test_different_voices_different_offsets(self):
        """voice_index diversi → offsets diversi (con alta probabilità)."""
        _, _, _, _, StochasticPitchStrategy, *_ = _get_module()
        s = StochasticPitchStrategy(pitch_range=5.0, stream_id="s1")
        offsets = [_factor(s, i, 6, 0.0) for i in range(1, 6)]
        assert len(set(offsets)) > 1

    def test_range_zero_all_identity(self):
        _, _, _, _, StochasticPitchStrategy, *_ = _get_module()
        s = StochasticPitchStrategy(pitch_range=0.0, stream_id="s1")
        for i in range(4):
            assert _factor(s, i, 4, 0.0) == 1.0

    def test_fixed_range_same_at_any_time(self):
        """Float range: stesso risultato a qualsiasi time."""
        _, _, _, _, StochasticPitchStrategy, *_ = _get_module()
        s = StochasticPitchStrategy(pitch_range=5.0, stream_id="s1")
        assert _factor(s, 1, 4, 0.0) == _factor(s, 1, 4, 1.0)

    def test_direction_invariant_with_envelope_range(self):
        """Con range envelope, il segno dell'offset rimane invariato."""
        from envelopes.envelope import Envelope
        _, _, _, _, StochasticPitchStrategy, *_ = _get_module()
        env = Envelope([[0, 1.0], [1, 12.0]])
        s = StochasticPitchStrategy(pitch_range=env, stream_id="s1")
        sign_at_0 = _st(s, 1, 4, 0.0) > 0
        sign_at_1 = _st(s, 1, 4, 1.0) > 0
        assert sign_at_0 == sign_at_1

    def test_envelope_range_varies_magnitude(self):
        """Con range envelope crescente, la magnitudine varia."""
        from envelopes.envelope import Envelope
        _, _, _, _, StochasticPitchStrategy, *_ = _get_module()
        env = Envelope([[0, 1.0], [1, 12.0]])
        s = StochasticPitchStrategy(pitch_range=env, stream_id="s1")
        v0 = abs(_st(s, 1, 4, 0.0))
        v1 = abs(_st(s, 1, 4, 1.0))
        assert v1 > v0


# =============================================================================
# 7. Invariante voce 0 — tutte le strategy
# =============================================================================

class TestVoiceZeroInvariant:

    @pytest.mark.parametrize("strategy_fixture", [
        lambda m: m[1](step=3.0),                            # StepPitchStrategy
        lambda m: m[2](pitch_range=12.0),                  # RangePitchStrategy
        lambda m: m[3](chord="dom7"),                         # ChordPitchStrategy
        lambda m: m[4](pitch_range=2.0, stream_id="s1"),   # StochasticPitchStrategy
        lambda m: m[8](max_partial=4),                        # SpectralPitchStrategy
    ])
    def test_voice_0_is_always_identity(self, strategy_fixture):
        mod = _get_module()
        strategy = strategy_fixture(mod)
        assert _factor(strategy, 0, 4, 0.0) == 1.0

    @pytest.mark.parametrize("strategy_fixture", [
        lambda m: m[1](step=3.0),
        lambda m: m[2](pitch_range=12.0),
        lambda m: m[3](chord="dom7"),
        lambda m: m[4](pitch_range=2.0, stream_id="s1"),
        lambda m: m[8](max_partial=4),
    ])
    def test_voice_0_is_identity_at_any_time(self, strategy_fixture):
        """Invariante voce 0 non dipende da time."""
        mod = _get_module()
        strategy = strategy_fixture(mod)
        for t in [0.0, 0.5, 1.0]:
            assert _factor(strategy, 0, 4, t) == 1.0


# =============================================================================
# 8. Edge cases
# =============================================================================

class TestEdgeCases:

    def test_step_num_voices_1(self):
        _, StepPitchStrategy, *_ = _get_module()
        s = StepPitchStrategy(step=7.0)
        assert _factor(s, 0, 1, 0.0) == 1.0

    def test_range_num_voices_1(self):
        _, _, RangePitchStrategy, *_ = _get_module()
        s = RangePitchStrategy(pitch_range=12.0)
        assert _factor(s, 0, 1, 0.0) == 1.0

    def test_chord_num_voices_1(self):
        _, _, _, ChordPitchStrategy, *_ = _get_module()
        s = ChordPitchStrategy(chord="maj")
        assert _factor(s, 0, 1, 0.0) == 1.0


# =============================================================================
# 9. VOICE_PITCH_STRATEGIES registry
# =============================================================================

class TestVoicePitchStrategiesRegistry:

    def test_registry_exists(self):
        *_, VOICE_PITCH_STRATEGIES, _, _, _ = _get_module()
        assert isinstance(VOICE_PITCH_STRATEGIES, dict)

    def test_registry_contains_step(self):
        *_, VOICE_PITCH_STRATEGIES, _, _, _ = _get_module()
        assert 'step' in VOICE_PITCH_STRATEGIES

    def test_registry_contains_range(self):
        *_, VOICE_PITCH_STRATEGIES, _, _, _ = _get_module()
        assert 'range' in VOICE_PITCH_STRATEGIES

    def test_registry_contains_chord(self):
        *_, VOICE_PITCH_STRATEGIES, _, _, _ = _get_module()
        assert 'chord' in VOICE_PITCH_STRATEGIES

    def test_registry_contains_stochastic(self):
        *_, VOICE_PITCH_STRATEGIES, _, _, _ = _get_module()
        assert 'stochastic' in VOICE_PITCH_STRATEGIES

    def test_registry_contains_spectral(self):
        *_, VOICE_PITCH_STRATEGIES, _, _, _ = _get_module()
        assert 'spectral' in VOICE_PITCH_STRATEGIES

    def test_registry_values_are_classes(self):
        *_, VOICE_PITCH_STRATEGIES, _, _, _ = _get_module()
        for name, cls in VOICE_PITCH_STRATEGIES.items():
            assert isinstance(cls, type), f"{name} non è una classe"


# =============================================================================
# 10. register_voice_pitch_strategy()
# =============================================================================

class TestRegisterVoicePitchStrategy:

    def test_register_new_strategy(self):
        VoicePitchStrategy, _, _, _, _, VOICE_PITCH_STRATEGIES, register_voice_pitch_strategy, _, _ = _get_module()

        class MyStrategy(VoicePitchStrategy):
            def get_pitch_factor(self, voice_index, num_voices, time, unit):
                return unit.materialize(float(voice_index), 2.0)

        register_voice_pitch_strategy('my_semi', MyStrategy)
        assert 'my_semi' in VOICE_PITCH_STRATEGIES

    def test_registered_strategy_usable_via_factory(self):
        VoicePitchStrategy, _, _, _, _, VOICE_PITCH_STRATEGIES, register_voice_pitch_strategy, VoicePitchStrategyFactory, _ = _get_module()

        class FixedStrategy(VoicePitchStrategy):
            def get_pitch_factor(self, voice_index, num_voices, time, unit):
                return 99.0 if voice_index > 0 else 1.0

        register_voice_pitch_strategy('fixed99', FixedStrategy)
        s = VoicePitchStrategyFactory.create('fixed99')
        assert s.get_pitch_factor(1, 2, 0.0, ST) == 99.0


# =============================================================================
# 11. VoicePitchStrategyFactory
# =============================================================================

class TestVoicePitchStrategyFactory:

    def test_create_step(self):
        _, _, _, _, _, _, _, VoicePitchStrategyFactory, _ = _get_module()
        _, StepPitchStrategy, *_ = _get_module()
        s = VoicePitchStrategyFactory.create('step', step=4.0)
        assert isinstance(s, StepPitchStrategy)

    def test_create_range(self):
        _, _, _, _, _, _, _, VoicePitchStrategyFactory, _ = _get_module()
        _, _, RangePitchStrategy, *_ = _get_module()
        s = VoicePitchStrategyFactory.create('range', pitch_range=12.0)
        assert isinstance(s, RangePitchStrategy)

    def test_create_chord(self):
        _, _, _, _, _, _, _, VoicePitchStrategyFactory, _ = _get_module()
        _, _, _, ChordPitchStrategy, *_ = _get_module()
        s = VoicePitchStrategyFactory.create('chord', chord='maj7')
        assert isinstance(s, ChordPitchStrategy)

    def test_create_stochastic(self):
        _, _, _, _, _, _, _, VoicePitchStrategyFactory, _ = _get_module()
        _, _, _, _, StochasticPitchStrategy, *_ = _get_module()
        s = VoicePitchStrategyFactory.create('stochastic', pitch_range=2.0, stream_id='s1')
        assert isinstance(s, StochasticPitchStrategy)

    def test_unknown_strategy_raises(self):
        _, _, _, _, _, _, _, VoicePitchStrategyFactory, _ = _get_module()
        with pytest.raises((KeyError, ValueError)):
            VoicePitchStrategyFactory.create('nonexistent_xyz')

    def test_factory_returns_voice_pitch_strategy_instance(self):
        VoicePitchStrategy, _, _, _, _, _, _, VoicePitchStrategyFactory, _ = _get_module()
        s = VoicePitchStrategyFactory.create('step', step=1.0)
        assert isinstance(s, VoicePitchStrategy)


# =============================================================================
# 12. Parametri dinamici (Envelope)
# =============================================================================

class TestDynamicPitchParams:

    def test_step_envelope_varies_over_time(self):
        """StepPitchStrategy con Envelope: offset varia nel tempo."""
        from envelopes.envelope import Envelope
        _, StepPitchStrategy, *_ = _get_module()
        env = Envelope([[0, 0.0], [1, 12.0]])
        s = StepPitchStrategy(step=env)
        assert _st(s, 1, 4, 0.0) == pytest.approx(0.0)
        assert _st(s, 1, 4, 0.5) == pytest.approx(6.0)
        assert _st(s, 1, 4, 1.0) == pytest.approx(12.0)

    def test_step_envelope_voice_0_always_identity(self):
        """Voice 0 invariant preservato anche con step Envelope."""
        from envelopes.envelope import Envelope
        _, StepPitchStrategy, *_ = _get_module()
        env = Envelope([[0, 0.0], [1, 12.0]])
        s = StepPitchStrategy(step=env)
        assert _factor(s, 0, 4, 0.5) == 1.0

    def test_range_envelope_varies_over_time(self):
        """RangePitchStrategy con Envelope: offset varia nel tempo."""
        from envelopes.envelope import Envelope
        _, _, RangePitchStrategy, *_ = _get_module()
        env = Envelope([[0, 0.0], [1, 12.0]])
        s = RangePitchStrategy(pitch_range=env)
        assert _st(s, 3, 4, 0.0) == pytest.approx(0.0)
        assert _st(s, 3, 4, 1.0) == pytest.approx(12.0)


# =============================================================================
# 13. Geometria ratio — step/range/stochastic sotto unit: ratio
# =============================================================================

class TestRatioGeometry:
    """Sotto unit: ratio la distribuzione è geometrica (amount^position).
    Identità nativa (factor 1.0), nessun fattore negativo o sub-zero."""

    RU = RatioUnit()

    def test_step_ratio_is_geometric(self):
        """step=2 → [1, 2, 4, 8] (ottave pulite, non lineare [1,2,4,6])."""
        _, StepPitchStrategy, *_ = _get_module()
        s = StepPitchStrategy(step=2.0)
        assert [s.get_pitch_factor(i, 4, 0.0, self.RU) for i in range(4)] == \
            pytest.approx([1.0, 2.0, 4.0, 8.0])

    def test_step_ratio_voice_0_identity(self):
        _, StepPitchStrategy, *_ = _get_module()
        s = StepPitchStrategy(step=2.0)
        assert s.get_pitch_factor(0, 4, 0.0, self.RU) == 1.0

    def test_range_ratio_is_geometric_monotone(self):
        """range=2, 4 voci → 2^[0,⅓,⅔,1] ≈ [1, 1.26, 1.587, 2], monotono crescente."""
        _, _, RangePitchStrategy, *_ = _get_module()
        s = RangePitchStrategy(pitch_range=2.0)
        factors = [s.get_pitch_factor(i, 4, 0.0, self.RU) for i in range(4)]
        assert factors == pytest.approx([1.0, 2 ** (1 / 3), 2 ** (2 / 3), 2.0])
        for a, b in zip(factors, factors[1:]):
            assert b > a

    def test_stochastic_ratio_symmetric_positive(self):
        """stochastic range=2 → tutti i fattori in [0.5, 2], nessun negativo."""
        _, _, _, _, StochasticPitchStrategy, *_ = _get_module()
        s = StochasticPitchStrategy(pitch_range=2.0, stream_id="s1")
        for i in range(1, 8):
            f = s.get_pitch_factor(i, 8, 0.0, self.RU)
            assert 0.5 <= f <= 2.0

    def test_range_ratio_below_one_amount_raises(self):
        """range<=0 con ratio è errore di dominio (materialize valida amount>0)."""
        from shared.exceptions import InvalidFieldValueError
        _, _, RangePitchStrategy, *_ = _get_module()
        s = RangePitchStrategy(pitch_range=0.0)
        # voce 0 resta identità (non chiama materialize); voce 1 con amount 0 -> errore
        assert s.get_pitch_factor(0, 4, 0.0, self.RU) == 1.0
        with pytest.raises(InvalidFieldValueError):
            s.get_pitch_factor(1, 4, 0.0, self.RU)


# =============================================================================
# TEST accordi jazz estesi (issue: 5, 6, 7 voci)
# =============================================================================

class TestJazzChordsExtended:
    """
    Verifica gli intervalli degli 11 nuovi accordi jazz aggiunti a
    CHORD_INTERVALS. Per ogni accordo si controlla:
    - che sia presente nel registry
    - che gli intervalli (in semitoni) corrispondano alla definizione
    - che voce 0 sia sempre identità
    """

    def _chord(self, name):
        _, _, _, ChordPitchStrategy, *_ = _get_module()
        return ChordPitchStrategy(chord=name)

    def _semis(self, s, n):
        return [_st(s, i, n, 0.0) for i in range(n)]

    # --- 5 voci ---

    def test_dom9_in_registry(self):
        from strategies.voice_pitch_strategy import CHORD_INTERVALS
        assert 'dom9' in CHORD_INTERVALS

    def test_dom9_intervals(self):
        assert self._semis(self._chord('dom9'), 5) == pytest.approx([0, 4, 7, 10, 14])

    def test_maj9_in_registry(self):
        from strategies.voice_pitch_strategy import CHORD_INTERVALS
        assert 'maj9' in CHORD_INTERVALS

    def test_maj9_intervals(self):
        assert self._semis(self._chord('maj9'), 5) == pytest.approx([0, 4, 7, 11, 14])

    def test_min9_in_registry(self):
        from strategies.voice_pitch_strategy import CHORD_INTERVALS
        assert 'min9' in CHORD_INTERVALS

    def test_min9_intervals(self):
        assert self._semis(self._chord('min9'), 5) == pytest.approx([0, 3, 7, 10, 14])

    def test_9sus4_in_registry(self):
        from strategies.voice_pitch_strategy import CHORD_INTERVALS
        assert '9sus4' in CHORD_INTERVALS

    def test_9sus4_intervals(self):
        assert self._semis(self._chord('9sus4'), 5) == pytest.approx([0, 5, 7, 10, 14])

    # --- 6 voci ---

    def test_dom9s11_in_registry(self):
        from strategies.voice_pitch_strategy import CHORD_INTERVALS
        assert 'dom9s11' in CHORD_INTERVALS

    def test_dom9s11_intervals(self):
        assert self._semis(self._chord('dom9s11'), 6) == pytest.approx([0, 4, 7, 10, 14, 18])

    def test_maj9s11_in_registry(self):
        from strategies.voice_pitch_strategy import CHORD_INTERVALS
        assert 'maj9s11' in CHORD_INTERVALS

    def test_maj9s11_intervals(self):
        assert self._semis(self._chord('maj9s11'), 6) == pytest.approx([0, 4, 7, 11, 14, 18])

    def test_min11_in_registry(self):
        from strategies.voice_pitch_strategy import CHORD_INTERVALS
        assert 'min11' in CHORD_INTERVALS

    def test_min11_intervals(self):
        assert self._semis(self._chord('min11'), 6) == pytest.approx([0, 3, 7, 10, 14, 17])

    # --- 7 voci ---

    def test_dom13_in_registry(self):
        from strategies.voice_pitch_strategy import CHORD_INTERVALS
        assert 'dom13' in CHORD_INTERVALS

    def test_dom13_intervals(self):
        assert self._semis(self._chord('dom13'), 7) == pytest.approx([0, 4, 7, 10, 14, 17, 21])

    def test_min13_in_registry(self):
        from strategies.voice_pitch_strategy import CHORD_INTERVALS
        assert 'min13' in CHORD_INTERVALS

    def test_min13_intervals(self):
        assert self._semis(self._chord('min13'), 7) == pytest.approx([0, 3, 7, 10, 14, 17, 21])

    def test_maj13s11_in_registry(self):
        from strategies.voice_pitch_strategy import CHORD_INTERVALS
        assert 'maj13s11' in CHORD_INTERVALS

    def test_maj13s11_intervals(self):
        assert self._semis(self._chord('maj13s11'), 7) == pytest.approx([0, 4, 7, 11, 14, 18, 21])

    def test_altered_in_registry(self):
        from strategies.voice_pitch_strategy import CHORD_INTERVALS
        assert 'altered' in CHORD_INTERVALS

    def test_altered_intervals(self):
        assert self._semis(self._chord('altered'), 7) == pytest.approx([0, 4, 7, 10, 13, 15, 20])

    # --- voce 0 sempre identità per tutti i nuovi accordi ---

    @pytest.mark.parametrize("chord_name", [
        'dom9', 'maj9', 'min9', '9sus4',
        'dom9s11', 'maj9s11', 'min11',
        'dom13', 'min13', 'maj13s11', 'altered',
    ])
    def test_voice_0_always_identity_for_new_chords(self, chord_name):
        s = self._chord(chord_name)
        assert _factor(s, 0, 7, 0.0) == 1.0


# =============================================================================
# TEST inversioni accordo (ChordPitchStrategy.inversion)
# =============================================================================

class TestChordInversion:
    """
    Verifica il parametro `inversion` di ChordPitchStrategy.
    """

    def _make(self, chord: str, inversion: int = 0):
        _, _, _, ChordPitchStrategy, *_ = _get_module()
        return ChordPitchStrategy(chord=chord, inversion=inversion)

    def _semis(self, s, n):
        return [_st(s, i, n, 0.0) for i in range(n)]

    def test_inversion_0_equals_root_position(self):
        s0 = self._make('dom7', inversion=0)
        s_default = self._make('dom7')
        for i in range(4):
            assert _factor(s0, i, 4, 0.0) == _factor(s_default, i, 4, 0.0)

    def test_dom7_inversion_1(self):
        s = self._make('dom7', inversion=1)
        assert self._semis(s, 4) == pytest.approx([0, 3, 6, 8])

    def test_dom7_inversion_2(self):
        s = self._make('dom7', inversion=2)
        assert self._semis(s, 4) == pytest.approx([0, 3, 5, 9])

    def test_dom7_inversion_3(self):
        s = self._make('dom7', inversion=3)
        assert self._semis(s, 4) == pytest.approx([0, 2, 6, 9])

    def test_maj_triad_inversion_1(self):
        s = self._make('maj', inversion=1)
        assert self._semis(s, 3) == pytest.approx([0, 3, 8])

    def test_maj_triad_inversion_2(self):
        s = self._make('maj', inversion=2)
        assert self._semis(s, 3) == pytest.approx([0, 5, 9])

    def test_voice_0_always_identity_with_inversion(self):
        s = self._make('dom7', inversion=2)
        assert _factor(s, 0, 4, 0.0) == 1.0

    def test_inversion_too_large_raises(self):
        _, _, _, ChordPitchStrategy, *_ = _get_module()
        with pytest.raises(ValueError, match="inversion"):
            ChordPitchStrategy(chord='dom7', inversion=4)

    def test_inversion_negative_raises(self):
        _, _, _, ChordPitchStrategy, *_ = _get_module()
        with pytest.raises(ValueError, match="inversion"):
            ChordPitchStrategy(chord='dom7', inversion=-1)

    def test_extend_policy_preserved_with_inversion(self):
        s = self._make('dom7', inversion=1)
        assert _st(s, 4, 6, 0.0) == pytest.approx(12.0)
        assert _st(s, 5, 6, 0.0) == pytest.approx(15.0)

    @pytest.mark.parametrize("chord_name,max_inv", [
        ('maj', 2), ('min', 2), ('dom7', 3), ('maj7', 3),
        ('dom9', 4), ('min11', 5), ('dom13', 6),
    ])
    def test_all_chords_all_inversions_voice_0_identity(self, chord_name, max_inv):
        for inv in range(max_inv + 1):
            s = self._make(chord_name, inversion=inv)
            assert _factor(s, 0, 8, 0.0) == 1.0


# =============================================================================
# SpectralPitchStrategy
# =============================================================================

class TestSpectralPitchStrategy:

    def _make(self, **kwargs):
        _, _, _, _, _, _, _, _, SpectralPitchStrategy = _get_module()
        return SpectralPitchStrategy(**kwargs)

    def test_voice_0_returns_identity(self):
        s = self._make()
        assert _factor(s, 0, 8, 0.0) == 1.0

    def test_voice_1_returns_12(self):
        s = self._make()
        assert _st(s, 1, 8, 0.0) == pytest.approx(12.0)

    def test_voice_2_returns_19(self):
        s = self._make()
        assert _st(s, 2, 8, 0.0) == pytest.approx(19.0)

    def test_first_8_partials(self):
        s = self._make()
        result = [_st(s, i, 8, 0.0) for i in range(8)]
        assert result == pytest.approx([0, 12, 19, 24, 28, 31, 34, 36])

    def test_offsets_are_monotonically_increasing(self):
        s = self._make()
        offsets = [_st(s, i, 16, 0.0) for i in range(16)]
        for a, b in zip(offsets, offsets[1:]):
            assert b > a

    def test_beyond_default_max_partial(self):
        s = self._make()
        expected = float(round(12 * math.log2(17)))
        assert _st(s, 16, 20, 0.0) == pytest.approx(expected)

    def test_default_max_partial_is_16(self):
        s = self._make()
        assert s.max_partial == 16

    def test_custom_max_partial(self):
        s = self._make(max_partial=8)
        assert s.max_partial == 8

    def test_in_registry(self):
        *_, VOICE_PITCH_STRATEGIES, _, _, _ = _get_module()
        assert 'spectral' in VOICE_PITCH_STRATEGIES

    def test_factory_creates_spectral(self):
        _, _, _, _, _, _, _, VoicePitchStrategyFactory, SpectralPitchStrategy = _get_module()
        s = VoicePitchStrategyFactory.create('spectral')
        assert isinstance(s, SpectralPitchStrategy)

    def test_factory_creates_spectral_with_max_partial(self):
        _, _, _, _, _, _, _, VoicePitchStrategyFactory, SpectralPitchStrategy = _get_module()
        s = VoicePitchStrategyFactory.create('spectral', max_partial=8)
        assert isinstance(s, SpectralPitchStrategy)
        assert s.max_partial == 8

    def test_time_param_ignored(self):
        """SpectralPitchStrategy ignora time — risultato identico a qualsiasi time."""
        s = self._make()
        assert _factor(s, 2, 8, 0.0) == _factor(s, 2, 8, 1.0)
