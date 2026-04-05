# tests/strategies/test_voice_pointer_strategy.py
"""
test_voice_pointer_strategy.py

Suite TDD per voice_pointer_strategy.py

Moduli sotto test (da scrivere):
- VoicePointerStrategy (ABC)
- LinearPointerStrategy    → voce i = i × step (normalizzato 0.0-1.0)
- StochasticPointerStrategy → offset fisso per voce, seed deterministico

Principi di design:
- Voce 0 restituisce SEMPRE 0.0 (riferimento immutato)
- Il valore restituito è un offset normalizzato (0.0-1.0) sulla posizione nel sample
- Additivo con il pointer base di PointerController e il grain jitter (già esistente)
- StochasticPointerStrategy: seed = hash(stream_id + str(voice_index))

Organizzazione:
  1.  VoicePointerStrategy ABC
  2.  LinearPointerStrategy
  3.  StochasticPointerStrategy
  4.  Invariante voce 0
  5.  Edge cases
  6.  VOICE_POINTER_STRATEGIES registry
  7.  register_voice_pointer_strategy()
  8.  VoicePointerStrategyFactory
"""

import pytest


# =============================================================================
# IMPORT LAZY
# =============================================================================

def _get_module():
    from strategies.voice_pointer_strategy import (
        VoicePointerStrategy,
        LinearPointerStrategy,
        StochasticPointerStrategy,
        VOICE_POINTER_STRATEGIES,
        register_voice_pointer_strategy,
        VoicePointerStrategyFactory,
    )
    return (
        VoicePointerStrategy,
        LinearPointerStrategy,
        StochasticPointerStrategy,
        VOICE_POINTER_STRATEGIES,
        register_voice_pointer_strategy,
        VoicePointerStrategyFactory,
    )


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(autouse=True)
def restore_registry():
    try:
        _, _, _, registry, _, _ = _get_module()
        original = dict(registry)
        yield
        registry.clear()
        registry.update(original)
    except ImportError:
        yield


# =============================================================================
# 1. VoicePointerStrategy ABC
# =============================================================================

class TestVoicePointerStrategyABC:

    def test_is_abstract(self):
        VoicePointerStrategy, *_ = _get_module()
        with pytest.raises(TypeError):
            VoicePointerStrategy()

    def test_get_pointer_offset_is_abstract(self):
        VoicePointerStrategy, *_ = _get_module()
        assert hasattr(VoicePointerStrategy, 'get_pointer_offset')

    def test_concrete_must_implement_get_pointer_offset(self):
        VoicePointerStrategy, *_ = _get_module()
        class Incomplete(VoicePointerStrategy):
            pass
        with pytest.raises(TypeError):
            Incomplete()

    def test_signature(self):
        VoicePointerStrategy, *_ = _get_module()
        import inspect
        sig = inspect.signature(VoicePointerStrategy.get_pointer_offset)
        params = list(sig.parameters.keys())
        assert 'voice_index' in params
        assert 'num_voices' in params


# =============================================================================
# 2. LinearPointerStrategy
# =============================================================================

class TestLinearPointerStrategy:

    def test_voice_0_returns_zero(self):
        _, LinearPointerStrategy, *_ = _get_module()
        s = LinearPointerStrategy(step=0.1)
        assert s.get_pointer_offset(voice_index=0, num_voices=4) == 0.0

    def test_voice_1_returns_one_step(self):
        _, LinearPointerStrategy, *_ = _get_module()
        s = LinearPointerStrategy(step=0.1)
        assert s.get_pointer_offset(voice_index=1, num_voices=4) == pytest.approx(0.1)

    def test_voice_2_returns_two_steps(self):
        _, LinearPointerStrategy, *_ = _get_module()
        s = LinearPointerStrategy(step=0.1)
        assert s.get_pointer_offset(voice_index=2, num_voices=4) == pytest.approx(0.2)

    def test_voice_3_returns_three_steps(self):
        _, LinearPointerStrategy, *_ = _get_module()
        s = LinearPointerStrategy(step=0.1)
        assert s.get_pointer_offset(voice_index=3, num_voices=4) == pytest.approx(0.3)

    def test_negative_step(self):
        _, LinearPointerStrategy, *_ = _get_module()
        s = LinearPointerStrategy(step=-0.05)
        assert s.get_pointer_offset(voice_index=2, num_voices=4) == pytest.approx(-0.10)

    def test_step_zero_all_voices_zero(self):
        _, LinearPointerStrategy, *_ = _get_module()
        s = LinearPointerStrategy(step=0.0)
        for i in range(4):
            assert s.get_pointer_offset(voice_index=i, num_voices=4) == 0.0

    def test_num_voices_one(self):
        _, LinearPointerStrategy, *_ = _get_module()
        s = LinearPointerStrategy(step=0.1)
        assert s.get_pointer_offset(voice_index=0, num_voices=1) == 0.0

    def test_small_step_fine_spread(self):
        _, LinearPointerStrategy, *_ = _get_module()
        s = LinearPointerStrategy(step=0.01)
        assert s.get_pointer_offset(voice_index=5, num_voices=8) == pytest.approx(0.05)


# =============================================================================
# 3. StochasticPointerStrategy
# =============================================================================

class TestStochasticPointerStrategy:

    def test_voice_0_always_zero(self):
        _, _, StochasticPointerStrategy, *_ = _get_module()
        s = StochasticPointerStrategy(pointer_range=0.2, stream_id="s1")
        assert s.get_pointer_offset(voice_index=0, num_voices=4) == 0.0

    def test_offset_within_range(self):
        _, _, StochasticPointerStrategy, *_ = _get_module()
        s = StochasticPointerStrategy(pointer_range=0.3, stream_id="s1")
        for i in range(1, 8):
            offset = s.get_pointer_offset(voice_index=i, num_voices=8)
            assert -0.3 <= offset <= 0.3

    def test_deterministic_same_stream(self):
        _, _, StochasticPointerStrategy, *_ = _get_module()
        s1 = StochasticPointerStrategy(pointer_range=0.5, stream_id="my_stream")
        s2 = StochasticPointerStrategy(pointer_range=0.5, stream_id="my_stream")
        for i in range(1, 5):
            assert s1.get_pointer_offset(i, 5) == s2.get_pointer_offset(i, 5)

    def test_different_stream_ids_different_offsets(self):
        _, _, StochasticPointerStrategy, *_ = _get_module()
        s1 = StochasticPointerStrategy(pointer_range=0.5, stream_id="stream_A")
        s2 = StochasticPointerStrategy(pointer_range=0.5, stream_id="stream_B")
        offsets1 = [s1.get_pointer_offset(i, 4) for i in range(1, 4)]
        offsets2 = [s2.get_pointer_offset(i, 4) for i in range(1, 4)]
        assert offsets1 != offsets2

    def test_pointer_range_zero_all_zero(self):
        _, _, StochasticPointerStrategy, *_ = _get_module()
        s = StochasticPointerStrategy(pointer_range=0.0, stream_id="s1")
        for i in range(4):
            assert s.get_pointer_offset(i, 4) == 0.0

    def test_different_voices_different_offsets(self):
        _, _, StochasticPointerStrategy, *_ = _get_module()
        s = StochasticPointerStrategy(pointer_range=0.5, stream_id="s1")
        offsets = [s.get_pointer_offset(i, 6) for i in range(1, 6)]
        assert len(set(offsets)) > 1


# =============================================================================
# 4. Invariante voce 0
# =============================================================================

class TestVoiceZeroInvariant:

    @pytest.mark.parametrize("strategy_fixture", [
        lambda m: m[1](step=0.1),
        lambda m: m[2](pointer_range=0.2, stream_id="s1"),
    ])
    def test_voice_0_is_always_zero(self, strategy_fixture):
        mod = _get_module()
        strategy = strategy_fixture(mod)
        assert strategy.get_pointer_offset(voice_index=0, num_voices=4) == 0.0


# =============================================================================
# 5. Edge cases
# =============================================================================

class TestEdgeCases:

    def test_linear_num_voices_1(self):
        _, LinearPointerStrategy, *_ = _get_module()
        s = LinearPointerStrategy(step=0.1)
        assert s.get_pointer_offset(0, 1) == 0.0

    def test_stochastic_num_voices_1(self):
        _, _, StochasticPointerStrategy, *_ = _get_module()
        s = StochasticPointerStrategy(pointer_range=0.2, stream_id="s1")
        assert s.get_pointer_offset(0, 1) == 0.0


# =============================================================================
# 6. VOICE_POINTER_STRATEGIES registry
# =============================================================================

class TestVoicePointerStrategiesRegistry:

    def test_registry_exists(self):
        _, _, _, VOICE_POINTER_STRATEGIES, _, _ = _get_module()
        assert isinstance(VOICE_POINTER_STRATEGIES, dict)

    def test_registry_contains_linear(self):
        _, _, _, VOICE_POINTER_STRATEGIES, _, _ = _get_module()
        assert 'linear' in VOICE_POINTER_STRATEGIES

    def test_registry_contains_stochastic(self):
        _, _, _, VOICE_POINTER_STRATEGIES, _, _ = _get_module()
        assert 'stochastic' in VOICE_POINTER_STRATEGIES

    def test_registry_values_are_classes(self):
        _, _, _, VOICE_POINTER_STRATEGIES, _, _ = _get_module()
        for name, cls in VOICE_POINTER_STRATEGIES.items():
            assert isinstance(cls, type), f"{name} non è una classe"


# =============================================================================
# 7. register_voice_pointer_strategy()
# =============================================================================

class TestRegisterVoicePointerStrategy:

    def test_register_new_strategy(self):
        VoicePointerStrategy, _, _, VOICE_POINTER_STRATEGIES, register_voice_pointer_strategy, _ = _get_module()

        class FixedPointer(VoicePointerStrategy):
            def get_pointer_offset(self, voice_index, num_voices):
                return 0.0 if voice_index == 0 else 0.5

        register_voice_pointer_strategy('fixed', FixedPointer)
        assert 'fixed' in VOICE_POINTER_STRATEGIES

    def test_registered_strategy_usable_via_factory(self):
        VoicePointerStrategy, _, _, _, register_voice_pointer_strategy, VoicePointerStrategyFactory = _get_module()

        class HalfPointer(VoicePointerStrategy):
            def get_pointer_offset(self, voice_index, num_voices):
                return 0.0 if voice_index == 0 else 0.25

        register_voice_pointer_strategy('quarter', HalfPointer)
        s = VoicePointerStrategyFactory.create('quarter')
        assert s.get_pointer_offset(1, 2) == 0.25


# =============================================================================
# 8. VoicePointerStrategyFactory
# =============================================================================

class TestVoicePointerStrategyFactory:

    def test_create_linear(self):
        _, LinearPointerStrategy, _, _, _, VoicePointerStrategyFactory = _get_module()
        s = VoicePointerStrategyFactory.create('linear', step=0.05)
        assert isinstance(s, LinearPointerStrategy)

    def test_create_stochastic(self):
        _, _, StochasticPointerStrategy, _, _, VoicePointerStrategyFactory = _get_module()
        s = VoicePointerStrategyFactory.create('stochastic', pointer_range=0.2, stream_id='s1')
        assert isinstance(s, StochasticPointerStrategy)

    def test_unknown_strategy_raises(self):
        *_, VoicePointerStrategyFactory = _get_module()
        with pytest.raises((KeyError, ValueError)):
            VoicePointerStrategyFactory.create('nonexistent_xyz')

    def test_factory_returns_voice_pointer_strategy_instance(self):
        VoicePointerStrategy, *_, VoicePointerStrategyFactory = _get_module()
        s = VoicePointerStrategyFactory.create('linear', step=0.1)
        assert isinstance(s, VoicePointerStrategy)
