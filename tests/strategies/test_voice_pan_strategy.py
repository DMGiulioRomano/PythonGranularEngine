# tests/controllers/test_voice_pan_strategy.py
"""
test_voice_pan_strategy.py

Suite TDD per voice_pan_strategy.py

Moduli sotto test:
- VoicePanStrategy (ABC)
- LinearPanStrategy
- RandomPanStrategy (ora con stream_id e cache per-voce)
- AdditivePanStrategy
- VOICE_PAN_STRATEGIES (registry dict)
- register_voice_pan_strategy() (funzione di registrazione)
- VoicePanStrategyFactory (factory con create() statico)

Principio di design:
- get_pan_offset(voice_index, num_voices, spread, time) — time required
- RandomPanStrategy: stabilità per-voce garantita dalla cache interna (stream_id)
- spread già risolto da VoiceManager; time accettato ma ignorato da Linear e Additive

Organizzazione:
  1.  VoicePanStrategy ABC - interfaccia e contratto
  2.  LinearPanStrategy - distribuzione deterministica equidistante
  3.  RandomPanStrategy - distribuzione stocastica stabile per voce
  4.  AdditivePanStrategy - offset additivo diretto
  5.  Invariante voce 0 - tutte le strategy rispettano il riferimento
  6.  Edge cases comuni - spread=0, num_voices=1
  7.  VOICE_PAN_STRATEGIES registry - completezza e struttura
  8.  register_voice_pan_strategy() - registrazione dinamica
  9.  VoicePanStrategyFactory - creazione e gestione errori
  10. Pattern architetturale - coerenza con il resto del sistema
  11. Integrazione Factory-Registry
"""

import pytest
from abc import ABC, abstractmethod


# =============================================================================
# IMPORT LAZY
# =============================================================================

def _get_module():
    """Import lazy per permettere RED phase senza errori di import."""
    from strategies.voice_pan_strategy import (
        VoicePanStrategy,
        LinearPanStrategy,
        RandomPanStrategy,
        AdditivePanStrategy,
        VOICE_PAN_STRATEGIES,
        register_voice_pan_strategy,
        VoicePanStrategyFactory,
    )
    return (
        VoicePanStrategy,
        LinearPanStrategy,
        RandomPanStrategy,
        AdditivePanStrategy,
        VOICE_PAN_STRATEGIES,
        register_voice_pan_strategy,
        VoicePanStrategyFactory,
    )


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(autouse=True)
def restore_registry():
    """
    Ripristina VOICE_PAN_STRATEGIES dopo ogni test che lo modifica.
    """
    try:
        _, _, _, _, registry, _, _ = _get_module()
        original = dict(registry)
        yield
        registry.clear()
        registry.update(original)
    except ImportError:
        yield


@pytest.fixture
def linear():
    _, LinearPanStrategy, _, _, _, _, _ = _get_module()
    return LinearPanStrategy()


@pytest.fixture
def random_strat():
    _, _, RandomPanStrategy, _, _, _, _ = _get_module()
    return RandomPanStrategy(stream_id='test_stream')


@pytest.fixture
def additive():
    _, _, _, AdditivePanStrategy, _, _, _ = _get_module()
    return AdditivePanStrategy()


# =============================================================================
# 1. VOICEPANSTRATEGY ABC - INTERFACCIA E CONTRATTO
# =============================================================================

class TestVoicePanStrategyABC:
    """Verifica che VoicePanStrategy sia un ABC correttamente definito."""

    def test_is_abstract_class(self):
        """VoicePanStrategy non puo' essere istanziata direttamente."""
        VoicePanStrategy, _, _, _, _, _, _ = _get_module()

        with pytest.raises(TypeError):
            VoicePanStrategy()

    def test_get_pan_offset_is_abstract(self):
        """get_pan_offset deve essere un abstractmethod."""
        VoicePanStrategy, _, _, _, _, _, _ = _get_module()

        assert hasattr(VoicePanStrategy, 'get_pan_offset')
        assert getattr(VoicePanStrategy.get_pan_offset, '__isabstractmethod__', False)

    def test_name_is_abstract_property(self):
        """name deve essere una abstract property."""
        VoicePanStrategy, _, _, _, _, _, _ = _get_module()

        assert hasattr(VoicePanStrategy, 'name')
        assert getattr(VoicePanStrategy.name, '__isabstractmethod__', False)

    def test_concrete_subclass_requires_both_methods(self):
        """Una sottoclasse senza get_pan_offset o name non puo' essere istanziata."""
        VoicePanStrategy, _, _, _, _, _, _ = _get_module()

        class IncompleteStrategy(VoicePanStrategy):
            pass

        with pytest.raises(TypeError):
            IncompleteStrategy()

    def test_concrete_subclass_with_all_methods_works(self):
        """Una sottoclasse completa puo' essere istanziata."""
        VoicePanStrategy, _, _, _, _, _, _ = _get_module()

        class ConcreteStrategy(VoicePanStrategy):
            def get_pan_offset(self, voice_index, num_voices, spread, time):
                return 0.0

            @property
            def name(self):
                return 'concrete'

        strategy = ConcreteStrategy()
        assert strategy is not None
        assert strategy.name == 'concrete'

    def test_get_pan_offset_signature(self):
        """get_pan_offset accetta voice_index, num_voices, spread, time."""
        VoicePanStrategy, _, _, _, _, _, _ = _get_module()

        class TestStrategy(VoicePanStrategy):
            def get_pan_offset(self, voice_index: int, num_voices: int, spread: float, time: float) -> float:
                return float(voice_index)

            @property
            def name(self):
                return 'test'

        s = TestStrategy()
        result = s.get_pan_offset(2, 4, 90.0, 0.0)
        assert result == 2.0

    def test_signature_includes_time(self):
        """get_pan_offset deve includere il parametro time."""
        VoicePanStrategy, _, _, _, _, _, _ = _get_module()
        import inspect
        sig = inspect.signature(VoicePanStrategy.get_pan_offset)
        params = list(sig.parameters.keys())
        assert 'time' in params


# =============================================================================
# 2. LINEARPANSTRATEGY - DISTRIBUZIONE DETERMINISTICA EQUIDISTANTE
# =============================================================================

class TestLinearPanStrategy:

    def test_name_is_linear(self, linear):
        assert linear.name == 'linear'

    def test_single_voice_returns_zero(self, linear):
        assert linear.get_pan_offset(0, 1, 180.0, 0.0) == pytest.approx(0.0)
        assert linear.get_pan_offset(0, 1, 0.0, 0.0) == pytest.approx(0.0)

    def test_two_voices_spread_100(self, linear):
        assert linear.get_pan_offset(0, 2, 100.0, 0.0) == pytest.approx(0.0)
        assert linear.get_pan_offset(1, 2, 100.0, 0.0) == pytest.approx(50.0)

    def test_four_voices_spread_120(self, linear):
        assert linear.get_pan_offset(0, 4, 120.0, 0.0) == pytest.approx(0.0)
        assert linear.get_pan_offset(1, 4, 120.0, 0.0) == pytest.approx(-20.0)
        assert linear.get_pan_offset(2, 4, 120.0, 0.0) == pytest.approx(20.0)
        assert linear.get_pan_offset(3, 4, 120.0, 0.0) == pytest.approx(60.0)

    def test_three_voices_voice_zero_is_zero(self, linear):
        """Voice 0 → 0.0 invariant; voci 1..N-1 distribuite linearmente."""
        assert linear.get_pan_offset(0, 3, 180.0, 0.0) == pytest.approx(0.0)
        assert linear.get_pan_offset(1, 3, 180.0, 0.0) == pytest.approx(0.0)
        assert linear.get_pan_offset(2, 3, 180.0, 0.0) == pytest.approx(90.0)

    def test_voice_zero_always_zero(self, linear):
        """Voice 0 ritorna 0.0 indipendentemente da spread e num_voices."""
        for spread in [60.0, 90.0, 180.0, 360.0]:
            assert linear.get_pan_offset(0, 4, spread, 0.0) == pytest.approx(0.0)

    def test_last_voice_at_positive_half_spread(self, linear):
        for n in [2, 3, 4, 5]:
            spread = 180.0
            assert linear.get_pan_offset(n - 1, n, spread, 0.0) == pytest.approx(spread / 2.0)

    def test_spread_zero_all_voices_at_zero(self, linear):
        for v in range(4):
            assert linear.get_pan_offset(v, 4, 0.0, 0.0) == pytest.approx(0.0)

    def test_deterministic_same_call_same_result(self, linear):
        r1 = linear.get_pan_offset(2, 5, 180.0, 0.0)
        r2 = linear.get_pan_offset(2, 5, 180.0, 0.0)
        assert r1 == pytest.approx(r2)

    def test_offsets_are_equidistant_for_nonzero_voices(self, linear):
        """Voci 1..N-1 equidistanti; voce 0 è riferimento fisso a 0.0."""
        n = 5
        spread = 200.0
        offsets = [linear.get_pan_offset(v, n, spread, 0.0) for v in range(1, n)]
        gaps = [offsets[i + 1] - offsets[i] for i in range(len(offsets) - 1)]

        for gap in gaps:
            assert gap == pytest.approx(gaps[0])

    def test_time_param_ignored(self, linear):
        """LinearPanStrategy ignora time — stessa risposta a qualsiasi time."""
        r0 = linear.get_pan_offset(1, 4, 120.0, 0.0)
        r1 = linear.get_pan_offset(1, 4, 120.0, 1.0)
        assert r0 == pytest.approx(r1)


# =============================================================================
# 3. RANDOMPANSTRATEGY - DISTRIBUZIONE STOCASTICA STABILE PER VOCE
# =============================================================================

class TestRandomPanStrategy:
    """
    RandomPanStrategy assegna un offset stabile a ogni voce nel range
    [-spread/2, +spread/2], seed deterministico da stream_id.
    Voce 0 → sempre 0.0.
    """

    def test_name_is_random(self, random_strat):
        assert random_strat.name == 'random'

    def test_offset_within_range(self, random_strat):
        spread = 180.0
        for v in range(1, 10):
            offset = random_strat.get_pan_offset(v, 10, spread, 0.0)
            assert -spread / 2.0 <= offset <= spread / 2.0

    def test_spread_zero_returns_zero(self, random_strat):
        assert random_strat.get_pan_offset(0, 4, 0.0, 0.0) == pytest.approx(0.0)
        assert random_strat.get_pan_offset(3, 4, 0.0, 0.0) == pytest.approx(0.0)

    def test_voice_0_always_zero(self, random_strat):
        """Voce 0 → 0.0 indipendentemente da spread."""
        for spread in [60.0, 120.0, 180.0]:
            assert random_strat.get_pan_offset(0, 4, spread, 0.0) == pytest.approx(0.0)

    def test_stable_per_voice_same_call(self, random_strat):
        """La stessa voce restituisce sempre lo stesso offset (cache)."""
        r1 = random_strat.get_pan_offset(1, 4, 180.0, 0.0)
        r2 = random_strat.get_pan_offset(1, 4, 180.0, 0.0)
        assert r1 == pytest.approx(r2)

    def test_stable_per_voice_same_stream_id(self):
        """Stesso stream_id → stessa cache → stessi offset."""
        _, _, RandomPanStrategy, _, _, _, _ = _get_module()
        s1 = RandomPanStrategy(stream_id='stream_X')
        s2 = RandomPanStrategy(stream_id='stream_X')
        for v in range(1, 5):
            assert s1.get_pan_offset(v, 8, 120.0, 0.0) == s2.get_pan_offset(v, 8, 120.0, 0.0)

    def test_different_stream_ids_different_offsets(self):
        """stream_id diversi → offsets diversi (con alta probabilità)."""
        _, _, RandomPanStrategy, _, _, _, _ = _get_module()
        s1 = RandomPanStrategy(stream_id='A')
        s2 = RandomPanStrategy(stream_id='B')
        offsets1 = [s1.get_pan_offset(v, 8, 120.0, 0.0) for v in range(1, 5)]
        offsets2 = [s2.get_pan_offset(v, 8, 120.0, 0.0) for v in range(1, 5)]
        assert offsets1 != offsets2

    def test_different_voices_generally_different(self, random_strat):
        offsets = [random_strat.get_pan_offset(v, 8, 360.0, 0.0) for v in range(1, 8)]
        assert len(set(round(o, 6) for o in offsets)) > 1

    def test_negative_spread_raises_or_handles_gracefully(self, random_strat):
        try:
            result = random_strat.get_pan_offset(1, 4, -10.0, 0.0)
            assert result == pytest.approx(0.0) or isinstance(result, float)
        except ValueError:
            pass

    def test_time_param_ignored(self, random_strat):
        """RandomPanStrategy ignora time — stessa risposta a qualsiasi time."""
        r0 = random_strat.get_pan_offset(1, 4, 120.0, 0.0)
        r1 = random_strat.get_pan_offset(1, 4, 120.0, 1.0)
        assert r0 == pytest.approx(r1)


# =============================================================================
# 4. ADDITIVEPANSTRATEGY - OFFSET ADDITIVO DIRETTO
# =============================================================================

class TestAdditivePanStrategy:

    def test_name_is_additive(self, additive):
        assert additive.name == 'additive'

    def test_returns_spread_as_offset_for_nonzero_voices(self, additive):
        assert additive.get_pan_offset(1, 4, 90.0, 0.0) == pytest.approx(90.0)
        assert additive.get_pan_offset(3, 4, 90.0, 0.0) == pytest.approx(90.0)

    def test_voice_zero_always_zero(self, additive):
        assert additive.get_pan_offset(0, 4, 90.0, 0.0) == pytest.approx(0.0)
        assert additive.get_pan_offset(0, 4, -45.0, 0.0) == pytest.approx(0.0)

    def test_spread_zero_returns_zero(self, additive):
        assert additive.get_pan_offset(2, 4, 0.0, 0.0) == pytest.approx(0.0)

    def test_negative_spread_allowed_for_nonzero_voices(self, additive):
        result = additive.get_pan_offset(1, 4, -45.0, 0.0)
        assert result == pytest.approx(-45.0)

    def test_nonzero_voices_same_offset(self, additive):
        """Voci 1..N-1 ricevono tutte lo stesso offset."""
        spread = 60.0
        n = 6
        results = [additive.get_pan_offset(v, n, spread, 0.0) for v in range(1, n)]
        assert all(r == pytest.approx(spread) for r in results)

    def test_time_param_ignored(self, additive):
        r0 = additive.get_pan_offset(1, 4, 90.0, 0.0)
        r1 = additive.get_pan_offset(1, 4, 90.0, 1.0)
        assert r0 == pytest.approx(r1)


# =============================================================================
# 5. INVARIANTE VOCE 0
# =============================================================================

class TestVoiceZeroInvariant:

    def test_linear_voice_zero_any_spread_any_num_voices(self, linear):
        """LinearPanStrategy: voce 0 = 0.0 per qualsiasi spread e num_voices."""
        for n in [1, 2, 3, 4]:
            for spread in [0.0, 60.0, 120.0, 180.0]:
                assert linear.get_pan_offset(0, n, spread, 0.0) == pytest.approx(0.0)

    def test_random_voice_zero_always_zero(self, random_strat):
        """RandomPanStrategy: voce 0 sempre 0.0."""
        for spread in [60.0, 120.0, 180.0]:
            assert random_strat.get_pan_offset(0, 4, spread, 0.0) == pytest.approx(0.0)

    def test_additive_voice_zero_always_zero(self, additive):
        """AdditivePanStrategy: voce 0 sempre 0.0."""
        for spread in [0.0, 60.0, -45.0, 180.0]:
            assert additive.get_pan_offset(0, 4, spread, 0.0) == pytest.approx(0.0)


# =============================================================================
# 6. EDGE CASES COMUNI
# =============================================================================

class TestEdgeCases:

    def test_linear_spread_zero_all_return_zero(self, linear):
        for v in range(4):
            assert linear.get_pan_offset(v, 4, 0.0, 0.0) == pytest.approx(0.0)

    def test_additive_spread_zero_returns_zero(self, additive):
        for v in range(4):
            assert additive.get_pan_offset(v, 4, 0.0, 0.0) == pytest.approx(0.0)

    def test_random_spread_zero_returns_zero(self, random_strat):
        for v in range(4):
            assert random_strat.get_pan_offset(v, 4, 0.0, 0.0) == pytest.approx(0.0)

    @pytest.mark.parametrize("strategy_name", ['linear', 'additive'])
    def test_returns_float(self, strategy_name):
        _, _, _, _, _, _, VoicePanStrategyFactory = _get_module()
        strategy = VoicePanStrategyFactory.create(strategy_name)
        result = strategy.get_pan_offset(0, 4, 90.0, 0.0)
        assert isinstance(result, (int, float))

    @pytest.mark.parametrize("strategy_name", ['linear', 'additive'])
    def test_num_voices_one_no_exception(self, strategy_name):
        _, _, _, _, _, _, VoicePanStrategyFactory = _get_module()
        strategy = VoicePanStrategyFactory.create(strategy_name)
        result = strategy.get_pan_offset(0, 1, 90.0, 0.0)
        assert isinstance(result, (int, float))

    @pytest.mark.parametrize("strategy_name", ['linear', 'additive'])
    def test_large_spread_no_exception(self, strategy_name):
        _, _, _, _, _, _, VoicePanStrategyFactory = _get_module()
        strategy = VoicePanStrategyFactory.create(strategy_name)
        result = strategy.get_pan_offset(0, 4, 3600.0, 0.0)
        assert isinstance(result, (int, float))

    def test_many_voices_no_exception_linear(self, linear):
        for v in range(64):
            result = linear.get_pan_offset(v, 64, 360.0, 0.0)
            assert isinstance(result, (int, float))


# =============================================================================
# 7. VOICE_PAN_STRATEGIES REGISTRY - COMPLETEZZA E STRUTTURA
# =============================================================================

class TestRegistry:

    EXPECTED_STRATEGIES = {'linear', 'random', 'additive'}

    def test_registry_is_dict(self):
        _, _, _, _, registry, _, _ = _get_module()
        assert isinstance(registry, dict)

    def test_registry_contains_expected_strategies(self):
        _, _, _, _, registry, _, _ = _get_module()
        assert self.EXPECTED_STRATEGIES.issubset(set(registry.keys()))

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

    def test_linear_maps_to_linearpanstrategy(self):
        _, LinearPanStrategy, _, _, registry, _, _ = _get_module()
        assert registry['linear'] is LinearPanStrategy

    def test_random_maps_to_randompanstrategy(self):
        _, _, RandomPanStrategy, _, registry, _, _ = _get_module()
        assert registry['random'] is RandomPanStrategy

    def test_additive_maps_to_additivepanstrategy(self):
        _, _, _, AdditivePanStrategy, registry, _, _ = _get_module()
        assert registry['additive'] is AdditivePanStrategy


# =============================================================================
# 8. REGISTER_VOICE_PAN_STRATEGY() - REGISTRAZIONE DINAMICA
# =============================================================================

class TestRegisterFunction:

    def test_register_new_strategy(self):
        VoicePanStrategy, _, _, _, registry, register_voice_pan_strategy, _ = _get_module()

        class CustomPanStrategy(VoicePanStrategy):
            def get_pan_offset(self, voice_index, num_voices, spread, time):
                return voice_index * spread

            @property
            def name(self):
                return 'custom'

        register_voice_pan_strategy('custom', CustomPanStrategy)
        assert 'custom' in registry
        assert registry['custom'] is CustomPanStrategy

    def test_register_overwrites_existing(self):
        VoicePanStrategy, _, _, _, registry, register_voice_pan_strategy, _ = _get_module()

        class NewLinear(VoicePanStrategy):
            custom_marker = True

            def get_pan_offset(self, voice_index, num_voices, spread, time):
                return 0.0

            @property
            def name(self):
                return 'linear'

        register_voice_pan_strategy('linear', NewLinear)
        assert registry['linear'] is NewLinear
        assert hasattr(registry['linear'], 'custom_marker')

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

    def test_create_linear(self):
        _, LinearPanStrategy, _, _, _, _, VoicePanStrategyFactory = _get_module()
        result = VoicePanStrategyFactory.create('linear')
        assert isinstance(result, LinearPanStrategy)

    def test_create_random(self):
        _, _, RandomPanStrategy, _, _, _, VoicePanStrategyFactory = _get_module()
        result = VoicePanStrategyFactory.create('random', stream_id='s1')
        assert isinstance(result, RandomPanStrategy)

    def test_create_additive(self):
        _, _, _, AdditivePanStrategy, _, _, VoicePanStrategyFactory = _get_module()
        result = VoicePanStrategyFactory.create('additive')
        assert isinstance(result, AdditivePanStrategy)

    def test_create_unknown_raises_valueerror(self):
        _, _, _, _, _, _, VoicePanStrategyFactory = _get_module()
        with pytest.raises(ValueError):
            VoicePanStrategyFactory.create('nonexistent_strategy')

    def test_valueerror_message_contains_name(self):
        _, _, _, _, _, _, VoicePanStrategyFactory = _get_module()
        with pytest.raises(ValueError, match='invalid_name'):
            VoicePanStrategyFactory.create('invalid_name')

    def test_valueerror_message_contains_available(self):
        _, _, _, _, _, _, VoicePanStrategyFactory = _get_module()
        with pytest.raises(ValueError) as exc_info:
            VoicePanStrategyFactory.create('wrong')
        error_msg = str(exc_info.value)
        assert any(name in error_msg for name in ['linear', 'random', 'additive'])

    def test_create_returns_voicepanstrategy_instance(self):
        VoicePanStrategy, _, _, _, _, _, VoicePanStrategyFactory = _get_module()
        for name, kwargs in [('linear', {}), ('random', {'stream_id': 's1'}), ('additive', {})]:
            instance = VoicePanStrategyFactory.create(name, **kwargs)
            assert isinstance(instance, VoicePanStrategy)

    def test_create_is_staticmethod(self):
        _, _, _, _, _, _, VoicePanStrategyFactory = _get_module()
        assert callable(VoicePanStrategyFactory.create)
        assert callable(VoicePanStrategyFactory().create)

    def test_create_has_docstring(self):
        _, _, _, _, _, _, VoicePanStrategyFactory = _get_module()
        assert VoicePanStrategyFactory.create.__doc__ is not None

    def test_factory_has_docstring(self):
        _, _, _, _, _, _, VoicePanStrategyFactory = _get_module()
        assert VoicePanStrategyFactory.__doc__ is not None

    def test_default_strategy_is_linear(self):
        _, LinearPanStrategy, _, _, _, _, VoicePanStrategyFactory = _get_module()
        try:
            result = VoicePanStrategyFactory.create()
            assert isinstance(result, LinearPanStrategy)
        except TypeError:
            pass


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
        _, _, _, _, _, _, VoicePanStrategyFactory = _get_module()
        assert isinstance(VoicePanStrategyFactory, type)

    def test_factory_create_is_accessible_from_class(self):
        _, _, _, _, _, _, VoicePanStrategyFactory = _get_module()
        assert callable(VoicePanStrategyFactory.create)

    def test_linear_and_additive_have_name_property(self):
        """Verifica name property su LinearPanStrategy e AdditivePanStrategy."""
        (_, LinearPanStrategy, _, AdditivePanStrategy, _, _, _) = _get_module()
        for cls in [LinearPanStrategy, AdditivePanStrategy]:
            instance = cls()
            assert hasattr(instance, 'name')
            assert isinstance(instance.name, str)
            assert len(instance.name) > 0

    def test_random_has_name_property(self):
        """RandomPanStrategy richiede stream_id."""
        (_, _, RandomPanStrategy, _, _, _, _) = _get_module()
        instance = RandomPanStrategy(stream_id='s1')
        assert hasattr(instance, 'name')
        assert isinstance(instance.name, str)
        assert len(instance.name) > 0

    def test_strategy_names_match_registry_keys_linear_additive(self):
        """Il name di linear/additive corrisponde alla chiave nel registry."""
        (_, LinearPanStrategy, _, AdditivePanStrategy, registry, _, _) = _get_module()

        for key, cls in {'linear': LinearPanStrategy, 'additive': AdditivePanStrategy}.items():
            instance = cls()
            assert instance.name == key

    def test_random_name_matches_registry_key(self):
        _, _, RandomPanStrategy, _, _, _, _ = _get_module()
        instance = RandomPanStrategy(stream_id='s1')
        assert instance.name == 'random'


# =============================================================================
# 11. INTEGRAZIONE FACTORY-REGISTRY
# =============================================================================

class TestFactoryRegistryIntegration:

    def test_factory_reads_from_registry(self):
        (VoicePanStrategy, _, _, _, registry,
         register_voice_pan_strategy, VoicePanStrategyFactory) = _get_module()

        class PingPanStrategy(VoicePanStrategy):
            custom_marker = 'ping'

            def get_pan_offset(self, voice_index, num_voices, spread, time):
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

        saved = registry.pop('additive')
        with pytest.raises(ValueError):
            VoicePanStrategyFactory.create('additive')
        registry['additive'] = saved

    def test_linear_and_additive_creatable(self):
        """Linear e Additive non richiedono kwargs."""
        VoicePanStrategy, _, _, _, _, _, VoicePanStrategyFactory = _get_module()
        for name in ['linear', 'additive']:
            instance = VoicePanStrategyFactory.create(name)
            assert instance is not None
            assert isinstance(instance, VoicePanStrategy)

    def test_random_creatable_with_stream_id(self):
        """Random richiede stream_id."""
        VoicePanStrategy, _, _, _, _, _, VoicePanStrategyFactory = _get_module()
        instance = VoicePanStrategyFactory.create('random', stream_id='s1')
        assert isinstance(instance, VoicePanStrategy)

    def test_registered_strategy_usable(self):
        (VoicePanStrategy, _, _, _, _,
         register_voice_pan_strategy, VoicePanStrategyFactory) = _get_module()

        class MirrorPanStrategy(VoicePanStrategy):
            def get_pan_offset(self, voice_index, num_voices, spread, time):
                sign = 1.0 if voice_index % 2 == 0 else -1.0
                return sign * spread / 2.0

            @property
            def name(self):
                return 'mirror'

        register_voice_pan_strategy('mirror', MirrorPanStrategy)
        strategy = VoicePanStrategyFactory.create('mirror')

        assert strategy.get_pan_offset(0, 4, 100.0, 0.0) == pytest.approx(50.0)
        assert strategy.get_pan_offset(1, 4, 100.0, 0.0) == pytest.approx(-50.0)
        assert strategy.get_pan_offset(2, 4, 100.0, 0.0) == pytest.approx(50.0)
        assert strategy.get_pan_offset(3, 4, 100.0, 0.0) == pytest.approx(-50.0)
