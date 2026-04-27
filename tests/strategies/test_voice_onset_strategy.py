# tests/strategies/test_voice_onset_strategy.py
"""
test_voice_onset_strategy.py

Suite TDD per voice_onset_strategy.py

Moduli sotto test:
- VoiceOnsetStrategy (ABC)
- LinearOnsetStrategy    → voce i = i × step(t) (secondi)
- GeometricOnsetStrategy → spaziatura esponenziale: step(t) * base(t)^(i-1)
- StochasticOnsetStrategy → offset per voce, seed deterministico, magnitudine time-varying
- VOICE_ONSET_STRATEGIES (registry dict)
- register_voice_onset_strategy()
- VoiceOnsetStrategyFactory

Principi di design:
- Voce 0 restituisce SEMPRE 0.0 (riferimento immutato)
- Il valore restituito è un offset in SECONDI
- get_onset_offset(voice_index, num_voices, time) — time required
- StochasticOnsetStrategy: cache memorizza fattore normalizzato [0,1]

Organizzazione:
  1.  VoiceOnsetStrategy ABC
  2.  LinearOnsetStrategy
  3.  GeometricOnsetStrategy
  4.  StochasticOnsetStrategy
  5.  Invariante voce 0
  6.  Edge cases
  7.  VOICE_ONSET_STRATEGIES registry
  8.  register_voice_onset_strategy()
  9.  VoiceOnsetStrategyFactory
  10. Parametri dinamici (Envelope)
"""

import pytest


# =============================================================================
# IMPORT LAZY
# =============================================================================

def _get_module():
    from strategies.voice_onset_strategy import (
        VoiceOnsetStrategy,
        LinearOnsetStrategy,
        GeometricOnsetStrategy,
        StochasticOnsetStrategy,
        VOICE_ONSET_STRATEGIES,
        register_voice_onset_strategy,
        VoiceOnsetStrategyFactory,
    )
    return (
        VoiceOnsetStrategy,
        LinearOnsetStrategy,
        GeometricOnsetStrategy,
        StochasticOnsetStrategy,
        VOICE_ONSET_STRATEGIES,
        register_voice_onset_strategy,
        VoiceOnsetStrategyFactory,
    )


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(autouse=True)
def restore_registry():
    try:
        _, _, _, _, registry, _, _ = _get_module()
        original = dict(registry)
        yield
        registry.clear()
        registry.update(original)
    except ImportError:
        yield


# =============================================================================
# 1. VoiceOnsetStrategy ABC
# =============================================================================

class TestVoiceOnsetStrategyABC:

    def test_is_abstract(self):
        VoiceOnsetStrategy, *_ = _get_module()
        with pytest.raises(TypeError):
            VoiceOnsetStrategy()

    def test_get_onset_offset_is_abstract(self):
        VoiceOnsetStrategy, *_ = _get_module()
        assert hasattr(VoiceOnsetStrategy, 'get_onset_offset')

    def test_concrete_must_implement_get_onset_offset(self):
        VoiceOnsetStrategy, *_ = _get_module()
        class Incomplete(VoiceOnsetStrategy):
            pass
        with pytest.raises(TypeError):
            Incomplete()

    def test_signature(self):
        VoiceOnsetStrategy, *_ = _get_module()
        import inspect
        sig = inspect.signature(VoiceOnsetStrategy.get_onset_offset)
        params = list(sig.parameters.keys())
        assert 'voice_index' in params
        assert 'num_voices' in params
        assert 'time' in params


# =============================================================================
# 2. LinearOnsetStrategy
# =============================================================================

class TestLinearOnsetStrategy:

    def test_voice_0_returns_zero(self):
        _, LinearOnsetStrategy, *_ = _get_module()
        s = LinearOnsetStrategy(step=0.05)
        assert s.get_onset_offset(voice_index=0, num_voices=4, time=0.0) == 0.0

    def test_voice_1_returns_one_step(self):
        _, LinearOnsetStrategy, *_ = _get_module()
        s = LinearOnsetStrategy(step=0.05)
        assert s.get_onset_offset(voice_index=1, num_voices=4, time=0.0) == pytest.approx(0.05)

    def test_voice_2_returns_two_steps(self):
        _, LinearOnsetStrategy, *_ = _get_module()
        s = LinearOnsetStrategy(step=0.05)
        assert s.get_onset_offset(voice_index=2, num_voices=4, time=0.0) == pytest.approx(0.10)

    def test_voice_3_returns_three_steps(self):
        _, LinearOnsetStrategy, *_ = _get_module()
        s = LinearOnsetStrategy(step=0.05)
        assert s.get_onset_offset(voice_index=3, num_voices=4, time=0.0) == pytest.approx(0.15)

    def test_step_zero_all_voices_zero(self):
        _, LinearOnsetStrategy, *_ = _get_module()
        s = LinearOnsetStrategy(step=0.0)
        for i in range(4):
            assert s.get_onset_offset(voice_index=i, num_voices=4, time=0.0) == 0.0

    def test_large_step(self):
        _, LinearOnsetStrategy, *_ = _get_module()
        s = LinearOnsetStrategy(step=1.0)
        assert s.get_onset_offset(voice_index=5, num_voices=6, time=0.0) == pytest.approx(5.0)

    def test_num_voices_one(self):
        _, LinearOnsetStrategy, *_ = _get_module()
        s = LinearOnsetStrategy(step=0.1)
        assert s.get_onset_offset(voice_index=0, num_voices=1, time=0.0) == 0.0

    def test_offset_is_always_non_negative(self):
        _, LinearOnsetStrategy, *_ = _get_module()
        s = LinearOnsetStrategy(step=0.03)
        for i in range(8):
            assert s.get_onset_offset(voice_index=i, num_voices=8, time=0.0) >= 0.0


# =============================================================================
# 3. GeometricOnsetStrategy
# =============================================================================

class TestGeometricOnsetStrategy:

    def test_voice_0_returns_zero(self):
        _, _, GeometricOnsetStrategy, *_ = _get_module()
        s = GeometricOnsetStrategy(step=0.05, base=2.0)
        assert s.get_onset_offset(voice_index=0, num_voices=4, time=0.0) == 0.0

    def test_voice_1_returns_step(self):
        """Voce 1 → step * base^0 = step."""
        _, _, GeometricOnsetStrategy, *_ = _get_module()
        s = GeometricOnsetStrategy(step=0.1, base=2.0)
        assert s.get_onset_offset(voice_index=1, num_voices=4, time=0.0) == pytest.approx(0.1)

    def test_voice_2_geometric_growth(self):
        """Voce 2 → step * base^1 = 0.1 * 2 = 0.2."""
        _, _, GeometricOnsetStrategy, *_ = _get_module()
        s = GeometricOnsetStrategy(step=0.1, base=2.0)
        assert s.get_onset_offset(voice_index=2, num_voices=4, time=0.0) == pytest.approx(0.2)

    def test_voice_3_geometric_growth(self):
        """Voce 3 → step * base^2 = 0.1 * 4 = 0.4."""
        _, _, GeometricOnsetStrategy, *_ = _get_module()
        s = GeometricOnsetStrategy(step=0.1, base=2.0)
        assert s.get_onset_offset(voice_index=3, num_voices=4, time=0.0) == pytest.approx(0.4)

    def test_base_one_equals_linear_step(self):
        """Base=1 → ogni voce ha lo stesso step (uguale a linear)."""
        _, _, GeometricOnsetStrategy, *_ = _get_module()
        s = GeometricOnsetStrategy(step=0.1, base=1.0)
        assert s.get_onset_offset(voice_index=1, num_voices=4, time=0.0) == pytest.approx(0.1)
        assert s.get_onset_offset(voice_index=2, num_voices=4, time=0.0) == pytest.approx(0.1)
        assert s.get_onset_offset(voice_index=3, num_voices=4, time=0.0) == pytest.approx(0.1)

    def test_offsets_increase_with_voice_index(self):
        """Con base>1 gli offset crescono monotonicamente."""
        _, _, GeometricOnsetStrategy, *_ = _get_module()
        s = GeometricOnsetStrategy(step=0.05, base=1.5)
        offsets = [s.get_onset_offset(i, 5, 0.0) for i in range(5)]
        for a, b in zip(offsets, offsets[1:]):
            assert b >= a

    def test_num_voices_one(self):
        _, _, GeometricOnsetStrategy, *_ = _get_module()
        s = GeometricOnsetStrategy(step=0.1, base=2.0)
        assert s.get_onset_offset(voice_index=0, num_voices=1, time=0.0) == 0.0


# =============================================================================
# 4. StochasticOnsetStrategy
# =============================================================================

class TestStochasticOnsetStrategy:

    def test_voice_0_always_zero(self):
        _, _, _, StochasticOnsetStrategy, *_ = _get_module()
        s = StochasticOnsetStrategy(max_offset=0.1, stream_id="s1")
        assert s.get_onset_offset(voice_index=0, num_voices=4, time=0.0) == 0.0

    def test_offset_within_range(self):
        _, _, _, StochasticOnsetStrategy, *_ = _get_module()
        s = StochasticOnsetStrategy(max_offset=0.2, stream_id="s1")
        for i in range(1, 8):
            offset = s.get_onset_offset(voice_index=i, num_voices=8, time=0.0)
            assert 0.0 <= offset <= 0.2

    def test_deterministic_same_stream(self):
        _, _, _, StochasticOnsetStrategy, *_ = _get_module()
        s1 = StochasticOnsetStrategy(max_offset=0.5, stream_id="my_stream")
        s2 = StochasticOnsetStrategy(max_offset=0.5, stream_id="my_stream")
        for i in range(1, 5):
            assert s1.get_onset_offset(i, 5, 0.0) == s2.get_onset_offset(i, 5, 0.0)

    def test_different_stream_ids_different_offsets(self):
        _, _, _, StochasticOnsetStrategy, *_ = _get_module()
        s1 = StochasticOnsetStrategy(max_offset=0.5, stream_id="stream_A")
        s2 = StochasticOnsetStrategy(max_offset=0.5, stream_id="stream_B")
        offsets1 = [s1.get_onset_offset(i, 4, 0.0) for i in range(1, 4)]
        offsets2 = [s2.get_onset_offset(i, 4, 0.0) for i in range(1, 4)]
        assert offsets1 != offsets2

    def test_max_offset_zero_all_zero(self):
        _, _, _, StochasticOnsetStrategy, *_ = _get_module()
        s = StochasticOnsetStrategy(max_offset=0.0, stream_id="s1")
        for i in range(4):
            assert s.get_onset_offset(i, 4, 0.0) == 0.0

    def test_offset_non_negative(self):
        """L'onset offset è sempre >= 0 (non si può andare prima della voce 0)."""
        _, _, _, StochasticOnsetStrategy, *_ = _get_module()
        s = StochasticOnsetStrategy(max_offset=0.3, stream_id="s1")
        for i in range(1, 6):
            assert s.get_onset_offset(i, 6, 0.0) >= 0.0

    def test_fixed_max_offset_same_at_any_time(self):
        """Float max_offset: stesso risultato a qualsiasi time."""
        _, _, _, StochasticOnsetStrategy, *_ = _get_module()
        s = StochasticOnsetStrategy(max_offset=0.3, stream_id="s1")
        assert s.get_onset_offset(1, 4, 0.0) == s.get_onset_offset(1, 4, 1.0)


# =============================================================================
# 5. Invariante voce 0 — tutte le strategy
# =============================================================================

class TestVoiceZeroInvariant:

    @pytest.mark.parametrize("strategy_fixture", [
        lambda m: m[1](step=0.05),
        lambda m: m[2](step=0.05, base=2.0),
        lambda m: m[3](max_offset=0.1, stream_id="s1"),
    ])
    def test_voice_0_is_always_zero(self, strategy_fixture):
        mod = _get_module()
        strategy = strategy_fixture(mod)
        assert strategy.get_onset_offset(voice_index=0, num_voices=4, time=0.0) == 0.0


# =============================================================================
# 6. Edge cases
# =============================================================================

class TestEdgeCases:

    def test_linear_num_voices_1(self):
        _, LinearOnsetStrategy, *_ = _get_module()
        s = LinearOnsetStrategy(step=0.1)
        assert s.get_onset_offset(0, 1, 0.0) == 0.0

    def test_geometric_num_voices_1(self):
        _, _, GeometricOnsetStrategy, *_ = _get_module()
        s = GeometricOnsetStrategy(step=0.1, base=2.0)
        assert s.get_onset_offset(0, 1, 0.0) == 0.0

    def test_stochastic_num_voices_1(self):
        _, _, _, StochasticOnsetStrategy, *_ = _get_module()
        s = StochasticOnsetStrategy(max_offset=0.1, stream_id="s1")
        assert s.get_onset_offset(0, 1, 0.0) == 0.0


# =============================================================================
# 7. VOICE_ONSET_STRATEGIES registry
# =============================================================================

class TestVoiceOnsetStrategiesRegistry:

    def test_registry_exists(self):
        *_, VOICE_ONSET_STRATEGIES, _, _ = _get_module()
        assert isinstance(VOICE_ONSET_STRATEGIES, dict)

    def test_registry_contains_linear(self):
        *_, VOICE_ONSET_STRATEGIES, _, _ = _get_module()
        assert 'linear' in VOICE_ONSET_STRATEGIES

    def test_registry_contains_geometric(self):
        *_, VOICE_ONSET_STRATEGIES, _, _ = _get_module()
        assert 'geometric' in VOICE_ONSET_STRATEGIES

    def test_registry_contains_stochastic(self):
        *_, VOICE_ONSET_STRATEGIES, _, _ = _get_module()
        assert 'stochastic' in VOICE_ONSET_STRATEGIES

    def test_registry_values_are_classes(self):
        *_, VOICE_ONSET_STRATEGIES, _, _ = _get_module()
        for name, cls in VOICE_ONSET_STRATEGIES.items():
            assert isinstance(cls, type), f"{name} non è una classe"


# =============================================================================
# 8. register_voice_onset_strategy()
# =============================================================================

class TestRegisterVoiceOnsetStrategy:

    def test_register_new_strategy(self):
        VoiceOnsetStrategy, _, _, _, VOICE_ONSET_STRATEGIES, register_voice_onset_strategy, _ = _get_module()

        class FixedOnset(VoiceOnsetStrategy):
            def get_onset_offset(self, voice_index, num_voices, time):
                return 0.0 if voice_index == 0 else 1.0

        register_voice_onset_strategy('fixed', FixedOnset)
        assert 'fixed' in VOICE_ONSET_STRATEGIES

    def test_registered_strategy_usable_via_factory(self):
        VoiceOnsetStrategy, _, _, _, _, register_voice_onset_strategy, VoiceOnsetStrategyFactory = _get_module()

        class HalfSecond(VoiceOnsetStrategy):
            def get_onset_offset(self, voice_index, num_voices, time):
                return 0.0 if voice_index == 0 else 0.5

        register_voice_onset_strategy('half', HalfSecond)
        s = VoiceOnsetStrategyFactory.create('half')
        assert s.get_onset_offset(1, 2, 0.0) == 0.5


# =============================================================================
# 9. VoiceOnsetStrategyFactory
# =============================================================================

class TestVoiceOnsetStrategyFactory:

    def test_create_linear(self):
        _, LinearOnsetStrategy, _, _, _, _, VoiceOnsetStrategyFactory = _get_module()
        s = VoiceOnsetStrategyFactory.create('linear', step=0.05)
        assert isinstance(s, LinearOnsetStrategy)

    def test_create_geometric(self):
        _, _, GeometricOnsetStrategy, _, _, _, VoiceOnsetStrategyFactory = _get_module()
        s = VoiceOnsetStrategyFactory.create('geometric', step=0.05, base=2.0)
        assert isinstance(s, GeometricOnsetStrategy)

    def test_create_stochastic(self):
        _, _, _, StochasticOnsetStrategy, _, _, VoiceOnsetStrategyFactory = _get_module()
        s = VoiceOnsetStrategyFactory.create('stochastic', max_offset=0.1, stream_id='s1')
        assert isinstance(s, StochasticOnsetStrategy)

    def test_unknown_strategy_raises(self):
        *_, VoiceOnsetStrategyFactory = _get_module()
        with pytest.raises((KeyError, ValueError)):
            VoiceOnsetStrategyFactory.create('nonexistent_xyz')

    def test_factory_returns_voice_onset_strategy_instance(self):
        VoiceOnsetStrategy, *_, VoiceOnsetStrategyFactory = _get_module()
        s = VoiceOnsetStrategyFactory.create('linear', step=0.1)
        assert isinstance(s, VoiceOnsetStrategy)


# =============================================================================
# 10. Parametri dinamici (Envelope)
# =============================================================================

class TestDynamicOnsetParams:

    def test_linear_step_envelope_varies(self):
        """LinearOnsetStrategy con Envelope: step varia nel tempo."""
        from envelopes.envelope import Envelope
        _, LinearOnsetStrategy, *_ = _get_module()
        env = Envelope([[0, 0.0], [1, 0.1]])
        s = LinearOnsetStrategy(step=env)
        assert s.get_onset_offset(1, 4, 0.0) == pytest.approx(0.0)
        assert s.get_onset_offset(1, 4, 1.0) == pytest.approx(0.1)

    def test_stochastic_envelope_varies_magnitude(self):
        """StochasticOnsetStrategy con Envelope: magnitudine varia, sempre >= 0."""
        from envelopes.envelope import Envelope
        _, _, _, StochasticOnsetStrategy, *_ = _get_module()
        env = Envelope([[0, 0.1], [1, 1.0]])
        s = StochasticOnsetStrategy(max_offset=env, stream_id="s1")
        v0 = s.get_onset_offset(1, 4, 0.0)
        v1 = s.get_onset_offset(1, 4, 1.0)
        assert v0 >= 0.0
        assert v1 >= 0.0
        assert v1 > v0
