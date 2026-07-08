# tests/strategies/test_voice_pan_strategy.py
"""
test_voice_pan_strategy.py

Suite TDD per voice_pan_strategy.py

Moduli sotto test:
- VoicePanStrategy (ABC)
- RangePanStrategy      → distribuzione deterministica equidistante in [-spread/2, +spread/2]
- StochasticPanStrategy → posizioni casuali stabili per voce, seed deterministico
- StepPanStrategy       → voce i → i × step gradi
- VOICE_PAN_STRATEGIES (registry dict)
- register_voice_pan_strategy() (funzione di registrazione)
- VoicePanStrategyFactory (factory con create() statico)

Principio di design (uniformato a onset/pointer/pitch):
- get_pan_offset(voice_index, num_voices, time) — il parametro (spread/step) è
  posseduto dalla strategy come StrategyParam e risolto internamente.
- StochasticPanStrategy: stabilità per-voce garantita dalla cache interna (stream_id).
- Voce 0 → sempre 0.0 (Voice-0 invariant).
- I parametri accettano Union[float, Envelope] (time-varying).

Organizzazione:
  1.  VoicePanStrategy ABC - interfaccia e contratto
  2.  RangePanStrategy - distribuzione deterministica equidistante
  3.  StochasticPanStrategy - distribuzione stocastica stabile per voce
  4.  StepPanStrategy - voce i → i × step
  5.  Invariante voce 0 - tutte le strategy rispettano il riferimento
  6.  Edge cases comuni - spread=0, num_voices=1
  7.  VOICE_PAN_STRATEGIES registry - completezza e struttura
  8.  register_voice_pan_strategy() - registrazione dinamica
  9.  VoicePanStrategyFactory - creazione e gestione errori
  10. Pattern architetturale - coerenza con il resto del sistema
  11. Integrazione Factory-Registry
  12. Parametri dinamici (Envelope)
  13. StochasticPanStrategy — seed riproducibile (issue #81)
"""

import pytest


# =============================================================================
# IMPORT LAZY
# =============================================================================

def _get_module():
    """Import lazy per permettere RED phase senza errori di import."""
    from pge.strategies.voice_pan_strategy import (
        VoicePanStrategy,
        RangePanStrategy,
        StochasticPanStrategy,
        StepPanStrategy,
        VOICE_PAN_STRATEGIES,
        register_voice_pan_strategy,
        VoicePanStrategyFactory,
    )
    return (
        VoicePanStrategy,
        RangePanStrategy,
        StochasticPanStrategy,
        StepPanStrategy,
        VOICE_PAN_STRATEGIES,
        register_voice_pan_strategy,
        VoicePanStrategyFactory,
    )


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(autouse=True)
def restore_registry():
    """Ripristina VOICE_PAN_STRATEGIES dopo ogni test che lo modifica."""
    try:
        _, _, _, _, registry, _, _ = _get_module()
        original = dict(registry)
        yield
        registry.clear()
        registry.update(original)
    except ImportError:
        yield


@pytest.fixture
def range_strat():
    _, RangePanStrategy, _, _, _, _, _ = _get_module()
    return RangePanStrategy(spread=120.0)


@pytest.fixture
def stochastic_strat():
    _, _, StochasticPanStrategy, _, _, _, _ = _get_module()
    return StochasticPanStrategy(spread=180.0, stream_id='test_stream')


@pytest.fixture
def step_strat():
    _, _, _, StepPanStrategy, _, _, _ = _get_module()
    return StepPanStrategy(step=15.0)


# =============================================================================
# 1. VOICEPANSTRATEGY ABC - INTERFACCIA E CONTRATTO
# =============================================================================

class TestVoicePanStrategyABC:
    """Verifica che VoicePanStrategy sia un ABC correttamente definito."""

    def test_is_abstract_class(self):
        VoicePanStrategy, *_ = _get_module()
        with pytest.raises(TypeError):
            VoicePanStrategy()

    def test_get_pan_offset_is_abstract(self):
        VoicePanStrategy, *_ = _get_module()
        assert hasattr(VoicePanStrategy, 'get_pan_offset')
        assert getattr(VoicePanStrategy.get_pan_offset, '__isabstractmethod__', False)

    def test_name_is_abstract_property(self):
        VoicePanStrategy, *_ = _get_module()
        assert hasattr(VoicePanStrategy, 'name')
        assert getattr(VoicePanStrategy.name, '__isabstractmethod__', False)

    def test_concrete_subclass_requires_both_methods(self):
        VoicePanStrategy, *_ = _get_module()

        class IncompleteStrategy(VoicePanStrategy):
            pass

        with pytest.raises(TypeError):
            IncompleteStrategy()

    def test_concrete_subclass_with_all_methods_works(self):
        VoicePanStrategy, *_ = _get_module()

        class ConcreteStrategy(VoicePanStrategy):
            def get_pan_offset(self, voice_index, num_voices, time):
                return 0.0

            @property
            def name(self):
                return 'concrete'

        strategy = ConcreteStrategy()
        assert strategy is not None
        assert strategy.name == 'concrete'

    def test_signature(self):
        VoicePanStrategy, *_ = _get_module()
        import inspect
        sig = inspect.signature(VoicePanStrategy.get_pan_offset)
        params = list(sig.parameters.keys())
        assert 'voice_index' in params
        assert 'num_voices' in params
        assert 'time' in params

    def test_signature_excludes_spread(self):
        """Il parametro è ora posseduto dalla strategy: niente spread nella firma."""
        VoicePanStrategy, *_ = _get_module()
        import inspect
        sig = inspect.signature(VoicePanStrategy.get_pan_offset)
        assert 'spread' not in sig.parameters


# =============================================================================
# 2. RANGEPANSTRATEGY - DISTRIBUZIONE DETERMINISTICA EQUIDISTANTE
# =============================================================================

class TestRangePanStrategy:

    def test_name_is_range(self, range_strat):
        assert range_strat.name == 'range'

    def test_single_voice_returns_zero(self):
        _, RangePanStrategy, *_ = _get_module()
        s = RangePanStrategy(spread=180.0)
        assert s.get_pan_offset(0, 1, 0.0) == pytest.approx(0.0)

    def test_two_voices_spread_100(self):
        _, RangePanStrategy, *_ = _get_module()
        s = RangePanStrategy(spread=100.0)
        assert s.get_pan_offset(0, 2, 0.0) == pytest.approx(0.0)
        assert s.get_pan_offset(1, 2, 0.0) == pytest.approx(50.0)

    def test_four_voices_spread_120(self):
        _, RangePanStrategy, *_ = _get_module()
        s = RangePanStrategy(spread=120.0)
        assert s.get_pan_offset(0, 4, 0.0) == pytest.approx(0.0)
        assert s.get_pan_offset(1, 4, 0.0) == pytest.approx(-20.0)
        assert s.get_pan_offset(2, 4, 0.0) == pytest.approx(20.0)
        assert s.get_pan_offset(3, 4, 0.0) == pytest.approx(60.0)

    def test_voice_zero_always_zero(self):
        _, RangePanStrategy, *_ = _get_module()
        for spread in [60.0, 90.0, 180.0, 360.0]:
            s = RangePanStrategy(spread=spread)
            assert s.get_pan_offset(0, 4, 0.0) == pytest.approx(0.0)

    def test_last_voice_at_positive_half_spread(self):
        _, RangePanStrategy, *_ = _get_module()
        for n in [2, 3, 4, 5]:
            s = RangePanStrategy(spread=180.0)
            assert s.get_pan_offset(n - 1, n, 0.0) == pytest.approx(90.0)

    def test_spread_zero_all_voices_at_zero(self):
        _, RangePanStrategy, *_ = _get_module()
        s = RangePanStrategy(spread=0.0)
        for v in range(4):
            assert s.get_pan_offset(v, 4, 0.0) == pytest.approx(0.0)

    def test_deterministic_same_call_same_result(self):
        _, RangePanStrategy, *_ = _get_module()
        s = RangePanStrategy(spread=180.0)
        assert s.get_pan_offset(2, 5, 0.0) == pytest.approx(s.get_pan_offset(2, 5, 0.0))

    def test_offsets_are_equidistant_for_nonzero_voices(self):
        _, RangePanStrategy, *_ = _get_module()
        n = 5
        s = RangePanStrategy(spread=200.0)
        offsets = [s.get_pan_offset(v, n, 0.0) for v in range(1, n)]
        gaps = [offsets[i + 1] - offsets[i] for i in range(len(offsets) - 1)]
        for gap in gaps:
            assert gap == pytest.approx(gaps[0])

    def test_fixed_spread_same_at_any_time(self):
        _, RangePanStrategy, *_ = _get_module()
        s = RangePanStrategy(spread=120.0)
        assert s.get_pan_offset(1, 4, 0.0) == pytest.approx(s.get_pan_offset(1, 4, 1.0))


# =============================================================================
# 3. STOCHASTICPANSTRATEGY - DISTRIBUZIONE STOCASTICA STABILE PER VOCE
# =============================================================================

class TestStochasticPanStrategy:
    """
    StochasticPanStrategy assegna un offset stabile a ogni voce nel range
    [-spread/2, +spread/2], seed deterministico da stream_id.
    Voce 0 → sempre 0.0.
    """

    def test_name_is_stochastic(self, stochastic_strat):
        assert stochastic_strat.name == 'stochastic'

    def test_offset_within_range(self, stochastic_strat):
        for v in range(1, 10):
            offset = stochastic_strat.get_pan_offset(v, 10, 0.0)
            assert -90.0 <= offset <= 90.0

    def test_spread_zero_returns_zero(self):
        _, _, StochasticPanStrategy, *_ = _get_module()
        s = StochasticPanStrategy(spread=0.0, stream_id='s1')
        assert s.get_pan_offset(0, 4, 0.0) == pytest.approx(0.0)
        assert s.get_pan_offset(3, 4, 0.0) == pytest.approx(0.0)

    def test_voice_0_always_zero(self):
        _, _, StochasticPanStrategy, *_ = _get_module()
        for spread in [60.0, 120.0, 180.0]:
            s = StochasticPanStrategy(spread=spread, stream_id='s1')
            assert s.get_pan_offset(0, 4, 0.0) == pytest.approx(0.0)

    def test_stable_per_voice_same_call(self, stochastic_strat):
        r1 = stochastic_strat.get_pan_offset(1, 4, 0.0)
        r2 = stochastic_strat.get_pan_offset(1, 4, 0.0)
        assert r1 == pytest.approx(r2)

    def test_stable_per_voice_same_stream_id(self):
        _, _, StochasticPanStrategy, *_ = _get_module()
        s1 = StochasticPanStrategy(spread=120.0, stream_id='stream_X')
        s2 = StochasticPanStrategy(spread=120.0, stream_id='stream_X')
        for v in range(1, 5):
            assert s1.get_pan_offset(v, 8, 0.0) == s2.get_pan_offset(v, 8, 0.0)

    def test_different_stream_ids_different_offsets(self):
        _, _, StochasticPanStrategy, *_ = _get_module()
        s1 = StochasticPanStrategy(spread=120.0, stream_id='A')
        s2 = StochasticPanStrategy(spread=120.0, stream_id='B')
        offsets1 = [s1.get_pan_offset(v, 8, 0.0) for v in range(1, 5)]
        offsets2 = [s2.get_pan_offset(v, 8, 0.0) for v in range(1, 5)]
        assert offsets1 != offsets2

    def test_different_voices_generally_different(self):
        _, _, StochasticPanStrategy, *_ = _get_module()
        s = StochasticPanStrategy(spread=360.0, stream_id='test_stream')
        offsets = [s.get_pan_offset(v, 8, 0.0) for v in range(1, 8)]
        assert len(set(round(o, 6) for o in offsets)) > 1

    def test_negative_spread_raises(self):
        _, _, StochasticPanStrategy, *_ = _get_module()
        from pge.shared.exceptions import InvalidStrategyConfigError
        s = StochasticPanStrategy(spread=-10.0, stream_id='s1')
        with pytest.raises(InvalidStrategyConfigError):
            s.get_pan_offset(1, 4, 0.0)

    def test_fixed_spread_same_at_any_time(self, stochastic_strat):
        r0 = stochastic_strat.get_pan_offset(1, 4, 0.0)
        r1 = stochastic_strat.get_pan_offset(1, 4, 1.0)
        assert r0 == pytest.approx(r1)


# =============================================================================
# 4. STEPPANSTRATEGY - VOCE i → i × step
# =============================================================================

class TestStepPanStrategy:

    def test_name_is_step(self, step_strat):
        assert step_strat.name == 'step'

    def test_voice_0_returns_zero(self, step_strat):
        assert step_strat.get_pan_offset(0, 4, 0.0) == pytest.approx(0.0)

    def test_voice_1_returns_one_step(self, step_strat):
        assert step_strat.get_pan_offset(1, 4, 0.0) == pytest.approx(15.0)

    def test_voice_2_returns_two_steps(self, step_strat):
        assert step_strat.get_pan_offset(2, 4, 0.0) == pytest.approx(30.0)

    def test_voice_3_returns_three_steps(self, step_strat):
        assert step_strat.get_pan_offset(3, 4, 0.0) == pytest.approx(45.0)

    def test_step_zero_all_voices_zero(self):
        _, _, _, StepPanStrategy, *_ = _get_module()
        s = StepPanStrategy(step=0.0)
        for i in range(4):
            assert s.get_pan_offset(i, 4, 0.0) == pytest.approx(0.0)

    def test_negative_step_allowed(self):
        """step negativo → pan verso sinistra, ammesso."""
        _, _, _, StepPanStrategy, *_ = _get_module()
        s = StepPanStrategy(step=-20.0)
        assert s.get_pan_offset(2, 4, 0.0) == pytest.approx(-40.0)

    def test_num_voices_one(self):
        _, _, _, StepPanStrategy, *_ = _get_module()
        s = StepPanStrategy(step=10.0)
        assert s.get_pan_offset(0, 1, 0.0) == pytest.approx(0.0)

    def test_fixed_step_same_at_any_time(self, step_strat):
        assert step_strat.get_pan_offset(2, 4, 0.0) == pytest.approx(step_strat.get_pan_offset(2, 4, 1.0))


# =============================================================================
# 5. INVARIANTE VOCE 0
# =============================================================================

class TestVoiceZeroInvariant:

    def test_range_voice_zero_any_spread_any_num_voices(self):
        _, RangePanStrategy, *_ = _get_module()
        for n in [1, 2, 3, 4]:
            for spread in [0.0, 60.0, 120.0, 180.0]:
                s = RangePanStrategy(spread=spread)
                assert s.get_pan_offset(0, n, 0.0) == pytest.approx(0.0)

    def test_stochastic_voice_zero_always_zero(self):
        _, _, StochasticPanStrategy, *_ = _get_module()
        for spread in [60.0, 120.0, 180.0]:
            s = StochasticPanStrategy(spread=spread, stream_id='s1')
            assert s.get_pan_offset(0, 4, 0.0) == pytest.approx(0.0)

    def test_step_voice_zero_always_zero(self):
        _, _, _, StepPanStrategy, *_ = _get_module()
        for step in [0.0, 15.0, -20.0, 90.0]:
            s = StepPanStrategy(step=step)
            assert s.get_pan_offset(0, 4, 0.0) == pytest.approx(0.0)


# =============================================================================
# 6. EDGE CASES COMUNI
# =============================================================================

class TestEdgeCases:

    def test_range_spread_zero_all_return_zero(self):
        _, RangePanStrategy, *_ = _get_module()
        s = RangePanStrategy(spread=0.0)
        for v in range(4):
            assert s.get_pan_offset(v, 4, 0.0) == pytest.approx(0.0)

    def test_step_step_zero_returns_zero(self):
        _, _, _, StepPanStrategy, *_ = _get_module()
        s = StepPanStrategy(step=0.0)
        for v in range(4):
            assert s.get_pan_offset(v, 4, 0.0) == pytest.approx(0.0)

    def test_stochastic_spread_zero_returns_zero(self):
        _, _, StochasticPanStrategy, *_ = _get_module()
        s = StochasticPanStrategy(spread=0.0, stream_id='s1')
        for v in range(4):
            assert s.get_pan_offset(v, 4, 0.0) == pytest.approx(0.0)

    def test_range_num_voices_one_no_exception(self):
        _, RangePanStrategy, *_ = _get_module()
        s = RangePanStrategy(spread=90.0)
        assert isinstance(s.get_pan_offset(0, 1, 0.0), (int, float))

    def test_step_num_voices_one_no_exception(self):
        _, _, _, StepPanStrategy, *_ = _get_module()
        s = StepPanStrategy(step=15.0)
        assert isinstance(s.get_pan_offset(0, 1, 0.0), (int, float))

    def test_range_large_spread_no_exception(self):
        _, RangePanStrategy, *_ = _get_module()
        s = RangePanStrategy(spread=3600.0)
        assert isinstance(s.get_pan_offset(2, 4, 0.0), (int, float))

    def test_many_voices_no_exception_range(self):
        _, RangePanStrategy, *_ = _get_module()
        s = RangePanStrategy(spread=360.0)
        for v in range(64):
            assert isinstance(s.get_pan_offset(v, 64, 0.0), (int, float))


# =============================================================================
# 7. VOICE_PAN_STRATEGIES REGISTRY - COMPLETEZZA E STRUTTURA
# =============================================================================

class TestRegistry:

    EXPECTED_STRATEGIES = {'range', 'stochastic', 'step'}

    def test_registry_is_dict(self):
        _, _, _, _, registry, _, _ = _get_module()
        assert isinstance(registry, dict)

    def test_registry_contains_expected_strategies(self):
        _, _, _, _, registry, _, _ = _get_module()
        assert self.EXPECTED_STRATEGIES.issubset(set(registry.keys()))

    def test_registry_does_not_contain_old_names(self):
        """linear/random/additive sono stati rinominati/rimossi (hard break)."""
        _, _, _, _, registry, _, _ = _get_module()
        assert 'linear' not in registry
        assert 'random' not in registry
        assert 'additive' not in registry

    def test_registry_values_are_classes(self):
        _, _, _, _, registry, _, _ = _get_module()
        for name, cls in registry.items():
            assert isinstance(cls, type), f"'{name}' non e' una classe"

    def test_registry_classes_are_voicepanstrategy(self):
        VoicePanStrategy, _, _, _, registry, _, _ = _get_module()
        for name, cls in registry.items():
            assert issubclass(cls, VoicePanStrategy), (
                f"'{name}' ({cls.__name__}) non eredita da VoicePanStrategy"
            )

    def test_range_maps_to_rangepanstrategy(self):
        _, RangePanStrategy, _, _, registry, _, _ = _get_module()
        assert registry['range'] is RangePanStrategy

    def test_stochastic_maps_to_stochasticpanstrategy(self):
        _, _, StochasticPanStrategy, _, registry, _, _ = _get_module()
        assert registry['stochastic'] is StochasticPanStrategy

    def test_step_maps_to_steppanstrategy(self):
        _, _, _, StepPanStrategy, registry, _, _ = _get_module()
        assert registry['step'] is StepPanStrategy


# =============================================================================
# 8. REGISTER_VOICE_PAN_STRATEGY() - REGISTRAZIONE DINAMICA
# =============================================================================

class TestRegisterFunction:

    def test_register_new_strategy(self):
        VoicePanStrategy, _, _, _, registry, register_voice_pan_strategy, _ = _get_module()

        class CustomPanStrategy(VoicePanStrategy):
            def get_pan_offset(self, voice_index, num_voices, time):
                return float(voice_index)

            @property
            def name(self):
                return 'custom'

        register_voice_pan_strategy('custom', CustomPanStrategy)
        assert 'custom' in registry
        assert registry['custom'] is CustomPanStrategy

    def test_register_overwrites_existing(self):
        VoicePanStrategy, _, _, _, registry, register_voice_pan_strategy, _ = _get_module()

        class NewRange(VoicePanStrategy):
            custom_marker = True

            def get_pan_offset(self, voice_index, num_voices, time):
                return 0.0

            @property
            def name(self):
                return 'range'

        register_voice_pan_strategy('range', NewRange)
        assert registry['range'] is NewRange
        assert hasattr(registry['range'], 'custom_marker')

    def test_register_function_is_callable(self):
        _, _, _, _, _, register_voice_pan_strategy, _ = _get_module()
        assert callable(register_voice_pan_strategy)

    def test_register_function_has_docstring(self):
        _, _, _, _, _, register_voice_pan_strategy, _ = _get_module()
        assert register_voice_pan_strategy.__doc__ is not None


# =============================================================================
# 9. VOICEPANSTRATEGYFACTORY - CREAZIONE E GESTIONE ERRORI
# =============================================================================

class TestVoicePanStrategyFactory:

    def test_create_range(self):
        _, RangePanStrategy, _, _, _, _, VoicePanStrategyFactory = _get_module()
        result = VoicePanStrategyFactory.create('range', spread=90.0)
        assert isinstance(result, RangePanStrategy)

    def test_create_stochastic(self):
        _, _, StochasticPanStrategy, _, _, _, VoicePanStrategyFactory = _get_module()
        result = VoicePanStrategyFactory.create('stochastic', spread=120.0, stream_id='s1')
        assert isinstance(result, StochasticPanStrategy)

    def test_create_step(self):
        _, _, _, StepPanStrategy, _, _, VoicePanStrategyFactory = _get_module()
        result = VoicePanStrategyFactory.create('step', step=15.0)
        assert isinstance(result, StepPanStrategy)

    def test_create_unknown_raises_valueerror(self):
        *_, VoicePanStrategyFactory = _get_module()
        with pytest.raises(ValueError):
            VoicePanStrategyFactory.create('nonexistent_strategy', spread=0.0)

    def test_create_old_name_raises(self):
        """I vecchi nomi non sono più accettati (hard break)."""
        *_, VoicePanStrategyFactory = _get_module()
        for old in ['linear', 'random', 'additive']:
            with pytest.raises(ValueError):
                VoicePanStrategyFactory.create(old, spread=0.0)

    def test_valueerror_message_contains_name(self):
        *_, VoicePanStrategyFactory = _get_module()
        with pytest.raises(ValueError, match='invalid_name'):
            VoicePanStrategyFactory.create('invalid_name', spread=0.0)

    def test_valueerror_message_contains_available(self):
        *_, VoicePanStrategyFactory = _get_module()
        with pytest.raises(ValueError) as exc_info:
            VoicePanStrategyFactory.create('wrong', spread=0.0)
        error_msg = str(exc_info.value)
        assert any(name in error_msg for name in ['range', 'stochastic', 'step'])

    def test_create_returns_voicepanstrategy_instance(self):
        VoicePanStrategy, *_, VoicePanStrategyFactory = _get_module()
        for name, kwargs in [
            ('range', {'spread': 90.0}),
            ('stochastic', {'spread': 120.0, 'stream_id': 's1'}),
            ('step', {'step': 15.0}),
        ]:
            instance = VoicePanStrategyFactory.create(name, **kwargs)
            assert isinstance(instance, VoicePanStrategy)

    def test_create_is_staticmethod(self):
        *_, VoicePanStrategyFactory = _get_module()
        assert callable(VoicePanStrategyFactory.create)

    def test_create_has_docstring(self):
        *_, VoicePanStrategyFactory = _get_module()
        assert VoicePanStrategyFactory.create.__doc__ is not None

    def test_factory_has_docstring(self):
        *_, VoicePanStrategyFactory = _get_module()
        assert VoicePanStrategyFactory.__doc__ is not None


# =============================================================================
# 10. PATTERN ARCHITETTURALE
# =============================================================================

class TestArchitecturalPattern:

    def test_registry_is_global_dict(self):
        _, _, _, _, registry, _, _ = _get_module()
        assert isinstance(registry, dict)

    def test_register_function_exists_and_callable(self):
        _, _, _, _, _, register_voice_pan_strategy, _ = _get_module()
        assert callable(register_voice_pan_strategy)

    def test_factory_is_class(self):
        *_, VoicePanStrategyFactory = _get_module()
        assert isinstance(VoicePanStrategyFactory, type)

    def test_factory_create_is_accessible_from_class(self):
        *_, VoicePanStrategyFactory = _get_module()
        assert callable(VoicePanStrategyFactory.create)

    def test_range_and_step_have_name_property(self):
        _, RangePanStrategy, _, StepPanStrategy, _, _, _ = _get_module()
        for instance in [RangePanStrategy(spread=60.0), StepPanStrategy(step=15.0)]:
            assert hasattr(instance, 'name')
            assert isinstance(instance.name, str)
            assert len(instance.name) > 0

    def test_stochastic_has_name_property(self):
        _, _, StochasticPanStrategy, _, _, _, _ = _get_module()
        instance = StochasticPanStrategy(spread=120.0, stream_id='s1')
        assert hasattr(instance, 'name')
        assert isinstance(instance.name, str)
        assert len(instance.name) > 0

    def test_strategy_names_match_registry_keys(self):
        _, RangePanStrategy, StochasticPanStrategy, StepPanStrategy, registry, _, _ = _get_module()
        assert RangePanStrategy(spread=60.0).name == 'range'
        assert StochasticPanStrategy(spread=60.0, stream_id='s1').name == 'stochastic'
        assert StepPanStrategy(step=15.0).name == 'step'


# =============================================================================
# 11. INTEGRAZIONE FACTORY-REGISTRY
# =============================================================================

class TestFactoryRegistryIntegration:

    def test_factory_reads_from_registry(self):
        (VoicePanStrategy, _, _, _, registry,
         register_voice_pan_strategy, VoicePanStrategyFactory) = _get_module()

        class PingPanStrategy(VoicePanStrategy):
            custom_marker = 'ping'

            def get_pan_offset(self, voice_index, num_voices, time):
                return 999.0

            @property
            def name(self):
                return 'ping'

        register_voice_pan_strategy('ping', PingPanStrategy)
        result = VoicePanStrategyFactory.create('ping')
        assert isinstance(result, PingPanStrategy)
        assert result.custom_marker == 'ping'

    def test_factory_reflects_registry_removal(self):
        _, _, _, _, registry, _, VoicePanStrategyFactory = _get_module()
        saved = registry.pop('step')
        with pytest.raises(ValueError):
            VoicePanStrategyFactory.create('step', step=15.0)
        registry['step'] = saved

    def test_range_and_step_creatable(self):
        VoicePanStrategy, *_, VoicePanStrategyFactory = _get_module()
        for name, kwargs in [('range', {'spread': 90.0}), ('step', {'step': 15.0})]:
            instance = VoicePanStrategyFactory.create(name, **kwargs)
            assert isinstance(instance, VoicePanStrategy)

    def test_stochastic_creatable_with_stream_id(self):
        VoicePanStrategy, *_, VoicePanStrategyFactory = _get_module()
        instance = VoicePanStrategyFactory.create('stochastic', spread=120.0, stream_id='s1')
        assert isinstance(instance, VoicePanStrategy)

    def test_registered_strategy_usable(self):
        (VoicePanStrategy, _, _, _, _,
         register_voice_pan_strategy, VoicePanStrategyFactory) = _get_module()

        class MirrorPanStrategy(VoicePanStrategy):
            def __init__(self, spread):
                self.spread = spread

            def get_pan_offset(self, voice_index, num_voices, time):
                sign = 1.0 if voice_index % 2 == 0 else -1.0
                return sign * self.spread / 2.0

            @property
            def name(self):
                return 'mirror'

        register_voice_pan_strategy('mirror', MirrorPanStrategy)
        strategy = VoicePanStrategyFactory.create('mirror', spread=100.0)

        assert strategy.get_pan_offset(0, 4, 0.0) == pytest.approx(50.0)
        assert strategy.get_pan_offset(1, 4, 0.0) == pytest.approx(-50.0)


# =============================================================================
# 12. PARAMETRI DINAMICI (ENVELOPE)
# =============================================================================

class TestDynamicPanParams:

    def test_range_spread_envelope_varies(self):
        """RangePanStrategy con Envelope: spread varia nel tempo."""
        from pge.envelopes.envelope import Envelope
        _, RangePanStrategy, *_ = _get_module()
        env = Envelope([[0, 100.0], [1, 200.0]])
        s = RangePanStrategy(spread=env)
        # 2 voci → voce 1 a +spread/2
        assert s.get_pan_offset(1, 2, 0.0) == pytest.approx(50.0)
        assert s.get_pan_offset(1, 2, 1.0) == pytest.approx(100.0)

    def test_step_envelope_varies(self):
        """StepPanStrategy con Envelope: step varia nel tempo."""
        from pge.envelopes.envelope import Envelope
        _, _, _, StepPanStrategy, *_ = _get_module()
        env = Envelope([[0, 10.0], [1, 30.0]])
        s = StepPanStrategy(step=env)
        assert s.get_pan_offset(2, 4, 0.0) == pytest.approx(20.0)
        assert s.get_pan_offset(2, 4, 1.0) == pytest.approx(60.0)

    def test_stochastic_spread_envelope_varies_magnitude(self):
        """StochasticPanStrategy con Envelope: magnitudine varia col tempo."""
        from pge.envelopes.envelope import Envelope
        _, _, StochasticPanStrategy, *_ = _get_module()
        env = Envelope([[0, 60.0], [1, 360.0]])
        s = StochasticPanStrategy(spread=env, stream_id='s1')
        v0 = abs(s.get_pan_offset(1, 4, 0.0))
        v1 = abs(s.get_pan_offset(1, 4, 1.0))
        # stessa voce (stesso fattore in cache) → magnitudine cresce con lo spread
        assert v1 > v0


# =============================================================================
# 13. StochasticPanStrategy — seed riproducibile (issue #81)
# =============================================================================

import hashlib
import random as _random


def _seeded_pos(seed, stream_id, vi, lo=-1.0, hi=1.0):
    """Posizione attesa col seed fissato (hashlib + Mersenne, cross-process)."""
    h = hashlib.sha256(f"{seed}:{stream_id}:{vi}".encode()).hexdigest()
    return _random.Random(int(h, 16)).uniform(lo, hi)


class TestStochasticPanSeed:

    def test_seed_produces_deterministic_value(self):
        _, _, StochasticPanStrategy, *_ = _get_module()
        s = StochasticPanStrategy(spread=180.0, stream_id="s1", seed=42)
        expected = _seeded_pos(42, "s1", 1) * 180.0 / 2.0
        assert s.get_pan_offset(1, 4, 0.0) == pytest.approx(expected)

    def test_different_seeds_different_offsets(self):
        _, _, StochasticPanStrategy, *_ = _get_module()
        s1 = StochasticPanStrategy(spread=180.0, stream_id="s1", seed=1)
        s2 = StochasticPanStrategy(spread=180.0, stream_id="s1", seed=2)
        o1 = [s1.get_pan_offset(i, 4, 0.0) for i in range(1, 4)]
        o2 = [s2.get_pan_offset(i, 4, 0.0) for i in range(1, 4)]
        assert o1 != o2

    def test_seed_none_backward_compatible(self):
        _, _, StochasticPanStrategy, *_ = _get_module()
        s = StochasticPanStrategy(spread=180.0, stream_id="s1", seed=None)
        for i in range(1, 5):
            assert -90.0 <= s.get_pan_offset(i, 5, 0.0) <= 90.0

    def test_seed_zero_accepted(self):
        _, _, StochasticPanStrategy, *_ = _get_module()
        s = StochasticPanStrategy(spread=180.0, stream_id="s1", seed=0)
        expected = _seeded_pos(0, "s1", 1) * 180.0 / 2.0
        assert s.get_pan_offset(1, 4, 0.0) == pytest.approx(expected)

    def test_factory_propagates_seed(self):
        *_, VoicePanStrategyFactory = _get_module()
        s = VoicePanStrategyFactory.create('stochastic', spread=180.0, stream_id='s1', seed=42)
        expected = _seeded_pos(42, "s1", 1) * 180.0 / 2.0
        assert s.get_pan_offset(1, 4, 0.0) == pytest.approx(expected)
