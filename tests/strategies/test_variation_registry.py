# tests/test_variation_registry.py
"""
Test suite completa per variation_registry.py

Modulo sotto test:
- VARIATION_STRATEGIES (Registry dict: str -> Type[VariationStrategy])
- register_variation_strategy() (funzione di registrazione dinamica)
- VariationFactory (Factory class con metodo statico create())

Dipendenze:
- variation_strategy.py: VariationStrategy (ABC), AdditiveVariation,
  QuantizedVariation, InvertVariation, ChoiceVariation

Organizzazione:
  1. VARIATION_STRATEGIES Registry - completezza, tipi, struttura
  2. Registry Integrity - invarianti strutturali del dizionario
  3. register_variation_strategy() - registrazione dinamica, sovrascrittura, print
  4. VariationFactory.create() - creazione valida per ogni modo
  5. VariationFactory.create() - gestione errori (ValueError)
  6. Factory Output Type Validation - isinstance checks sulle istanze
  7. Integrazione Factory-Registry - coerenza end-to-end
  8. Edge Cases e Robustezza
  9. Cleanup e Isolamento - ripristino stato registry tra test
"""

import pytest
from typing import Dict, Type

from pge.shared.distribution_strategy import DistributionStrategy
from pge.strategies.variation_strategy import (
    VariationStrategy,
    AdditiveVariation,
    QuantizedVariation,
    InvertVariation,
    NegateVariation,
    ChoiceVariation,
)
from pge.strategies.variation_registry import (
    VARIATION_STRATEGIES,
    register_variation_strategy,
    VariationFactory,
)


# =============================================================================
# MOCK DISTRIBUTION PER TEST DETERMINISTICI
# =============================================================================

class MockDistribution(DistributionStrategy):
    """Distribuzione mock deterministica per test di integrazione."""
    def sample(self, center: float, spread: float) -> float:
        return center  # Ritorna sempre center, deterministico

    @property
    def name(self) -> str:
        return "mock"

    def get_bounds(self, center: float, spread: float):
        return (center, center)


# =============================================================================
# COSTANTI DI RIFERIMENTO
# =============================================================================

# La mappa nome -> classe non vive qui: e' asserita direttamente da
# `test_each_mode_maps_correctly` e dai cinque test per singolo modo. Una
# tabella in piu' sarebbe una terza copia dello stesso contratto, che nessuno
# legge e che si scorda di crescere.
EXPECTED_MODE_NAMES = {'additive', 'quantized', 'invert', 'negate', 'choice'}


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(autouse=True)
def restore_registry():
    """
    Ripristina lo stato originale di VARIATION_STRATEGIES dopo ogni test.
    Fondamentale per isolamento: register_variation_strategy() modifica
    il dict globale, e senza cleanup i test si inquinerebbero a vicenda.
    """
    original = dict(VARIATION_STRATEGIES)
    yield
    VARIATION_STRATEGIES.clear()
    VARIATION_STRATEGIES.update(original)


@pytest.fixture
def mock_dist():
    """Distribuzione mock deterministica per test di integrazione."""
    return MockDistribution()


# =============================================================================
# 1. VARIATION_STRATEGIES REGISTRY - COMPLETEZZA E CONTENUTO
# =============================================================================

class TestVariationStrategiesRegistry:
    """Verifica contenuto e completezza del registry dict."""

    def test_registry_is_dict(self):
        """VARIATION_STRATEGIES e' un dizionario."""
        assert isinstance(VARIATION_STRATEGIES, dict)

    def test_registry_entries_match_expected_modes(self):
        """Il registry contiene esattamente le strategie attese."""
        assert len(VARIATION_STRATEGIES) == len(EXPECTED_MODE_NAMES)

    def test_registry_contains_all_expected_modes(self):
        """Tutti i modi attesi sono presenti nel registry."""
        assert set(VARIATION_STRATEGIES.keys()) == EXPECTED_MODE_NAMES

    def test_additive_maps_to_correct_class(self):
        """'additive' mappa a AdditiveVariation."""
        assert VARIATION_STRATEGIES['additive'] is AdditiveVariation

    def test_quantized_maps_to_correct_class(self):
        """'quantized' mappa a QuantizedVariation."""
        assert VARIATION_STRATEGIES['quantized'] is QuantizedVariation

    def test_invert_maps_to_correct_class(self):
        """'invert' mappa a InvertVariation."""
        assert VARIATION_STRATEGIES['invert'] is InvertVariation

    def test_negate_maps_to_correct_class(self):
        """'negate' mappa a NegateVariation (flip su dominio con segno)."""
        assert VARIATION_STRATEGIES['negate'] is NegateVariation

    def test_choice_maps_to_correct_class(self):
        """'choice' mappa a ChoiceVariation."""
        assert VARIATION_STRATEGIES['choice'] is ChoiceVariation

    @pytest.mark.parametrize("mode_name,expected_class", [
        ('additive', AdditiveVariation),
        ('quantized', QuantizedVariation),
        ('invert', InvertVariation),
        ('negate', NegateVariation),
        ('choice', ChoiceVariation),
    ])
    def test_each_mode_maps_correctly(self, mode_name, expected_class):
        """Test parametrizzato: ogni modo mappa alla classe corretta."""
        assert VARIATION_STRATEGIES[mode_name] is expected_class


# =============================================================================
# 2. REGISTRY INTEGRITY - INVARIANTI STRUTTURALI
# =============================================================================

class TestRegistryIntegrity:
    """Invarianti strutturali che il registry deve sempre rispettare."""

    def test_all_keys_are_strings(self):
        """Tutte le chiavi del registry sono stringhe."""
        for key in VARIATION_STRATEGIES:
            assert isinstance(key, str), f"Chiave non-stringa: {key!r}"

    def test_all_keys_are_lowercase(self):
        """Tutte le chiavi sono lowercase (convenzione naming)."""
        for key in VARIATION_STRATEGIES:
            assert key == key.lower(), f"Chiave non lowercase: {key!r}"

    def test_all_keys_are_non_empty(self):
        """Nessuna chiave vuota nel registry."""
        for key in VARIATION_STRATEGIES:
            assert len(key) > 0, "Trovata chiave vuota nel registry"

    def test_all_values_are_types(self):
        """Tutti i valori sono classi (Type), non istanze."""
        for mode, cls in VARIATION_STRATEGIES.items():
            assert isinstance(cls, type), (
                f"'{mode}' mappa a {type(cls).__name__}, non a una classe"
            )

    def test_all_values_are_variation_strategy_subclasses(self):
        """Tutti i valori sono sottoclassi di VariationStrategy."""
        for mode, cls in VARIATION_STRATEGIES.items():
            assert issubclass(cls, VariationStrategy), (
                f"'{mode}' -> {cls.__name__} non e' sottoclasse di VariationStrategy"
            )

    def test_no_abstract_classes_in_registry(self):
        """Nessuna classe astratta nel registry (tutte istanziabili)."""
        for mode, cls in VARIATION_STRATEGIES.items():
            # Verifica che si possa istanziare (non sia ABC pura)
            try:
                instance = cls()
                assert instance is not None
            except TypeError as e:
                pytest.fail(
                    f"'{mode}' -> {cls.__name__} non istanziabile: {e}"
                )

    def test_no_duplicate_classes(self):
        """Ogni classe appare una sola volta nel registry."""
        classes = list(VARIATION_STRATEGIES.values())
        unique_classes = set(id(c) for c in classes)
        assert len(classes) == len(unique_classes), (
            "Trovate classi duplicate nel registry"
        )

    def test_registry_keys_contain_no_spaces(self):
        """Nessuna chiave contiene spazi."""
        for key in VARIATION_STRATEGIES:
            assert ' ' not in key, f"Chiave con spazi: '{key}'"

    def test_registry_is_not_empty(self):
        """Il registry non e' mai vuoto."""
        assert len(VARIATION_STRATEGIES) > 0


# =============================================================================
# 3. register_variation_strategy() - REGISTRAZIONE DINAMICA
# =============================================================================

class TestRegisterVariationStrategy:
    """Test della funzione di registrazione dinamica."""

    def test_register_new_strategy(self):
        """Registrazione di una nuova strategia aggiunge al registry."""
        class LogarithmicVariation(VariationStrategy):
            def apply(self, base, mod_range, distribution):
                return base

        register_variation_strategy('logarithmic', LogarithmicVariation)

        assert 'logarithmic' in VARIATION_STRATEGIES
        assert VARIATION_STRATEGIES['logarithmic'] is LogarithmicVariation

    def test_register_increases_count(self):
        """La registrazione incrementa il conteggio del registry."""
        initial_count = len(VARIATION_STRATEGIES)

        class NewVariation(VariationStrategy):
            def apply(self, base, mod_range, distribution):
                return base

        register_variation_strategy('new_mode', NewVariation)
        assert len(VARIATION_STRATEGIES) == initial_count + 1

    def test_register_overwrite_existing(self):
        """La registrazione con nome esistente sovrascrive la strategia."""
        class CustomAdditive(VariationStrategy):
            def apply(self, base, mod_range, distribution):
                return base * 2

        original_class = VARIATION_STRATEGIES['additive']
        register_variation_strategy('additive', CustomAdditive)

        assert VARIATION_STRATEGIES['additive'] is CustomAdditive
        assert VARIATION_STRATEGIES['additive'] is not original_class

    def test_register_prints_confirmation(self, capsys):
        """La registrazione stampa messaggio di conferma."""
        class TestVariation(VariationStrategy):
            def apply(self, base, mod_range, distribution):
                return base

        register_variation_strategy('test_mode', TestVariation)
        captured = capsys.readouterr()

        assert 'test_mode' in captured.out
        assert 'TestVariation' in captured.out

    def test_register_print_contains_emoji(self, capsys):
        """Il messaggio di conferma contiene l'emoji di check."""
        class DemoVariation(VariationStrategy):
            def apply(self, base, mod_range, distribution):
                return base

        register_variation_strategy('demo', DemoVariation)
        captured = capsys.readouterr()

        # Il codice di produzione usa questo formato specifico
        assert captured.out.startswith('\u2705')  # emoji check verde

    def test_register_multiple_strategies(self):
        """Registrazione multipla aggiunge tutte le strategie."""
        class StratA(VariationStrategy):
            def apply(self, b, m, d): return b

        class StratB(VariationStrategy):
            def apply(self, b, m, d): return b

        register_variation_strategy('strat_a', StratA)
        register_variation_strategy('strat_b', StratB)

        assert 'strat_a' in VARIATION_STRATEGIES
        assert 'strat_b' in VARIATION_STRATEGIES

    def test_registered_strategy_usable_by_factory(self):
        """Una strategia registrata dinamicamente e' usabile dalla Factory."""
        class ExponentialVariation(VariationStrategy):
            def apply(self, base, mod_range, distribution):
                return base ** 2

        register_variation_strategy('exponential', ExponentialVariation)

        instance = VariationFactory.create('exponential')
        assert isinstance(instance, ExponentialVariation)

    def test_register_with_empty_name(self):
        """Registrazione con nome vuoto (il sistema non lo impedisce)."""
        class EmptyNameVariation(VariationStrategy):
            def apply(self, b, m, d): return b

        # Il codice di produzione non valida il nome, registra comunque
        register_variation_strategy('', EmptyNameVariation)
        assert '' in VARIATION_STRATEGIES


# =============================================================================
# 4. VariationFactory.create() - CREAZIONE VALIDA
# =============================================================================

class TestVariationFactoryCreate:
    """Test del metodo factory create() per tutti i modi validi."""

    def test_create_additive(self):
        """Factory crea istanza AdditiveVariation."""
        result = VariationFactory.create('additive')
        assert isinstance(result, AdditiveVariation)

    def test_create_quantized(self):
        """Factory crea istanza QuantizedVariation."""
        result = VariationFactory.create('quantized')
        assert isinstance(result, QuantizedVariation)

    def test_create_invert(self):
        """Factory crea istanza InvertVariation."""
        result = VariationFactory.create('invert')
        assert isinstance(result, InvertVariation)

    def test_create_choice(self):
        """Factory crea istanza ChoiceVariation."""
        result = VariationFactory.create('choice')
        assert isinstance(result, ChoiceVariation)

    @pytest.mark.parametrize("mode_name,expected_class", [
        ('additive', AdditiveVariation),
        ('quantized', QuantizedVariation),
        ('invert', InvertVariation),
        ('negate', NegateVariation),
        ('choice', ChoiceVariation),
    ])
    def test_create_parametrized(self, mode_name, expected_class):
        """Test parametrizzato: factory crea il tipo corretto per ogni modo."""
        result = VariationFactory.create(mode_name)
        assert isinstance(result, expected_class)

    def test_create_returns_new_instance_each_call(self):
        """Ogni chiamata a create() produce un'istanza nuova (no singleton)."""
        inst_a = VariationFactory.create('additive')
        inst_b = VariationFactory.create('additive')
        assert inst_a is not inst_b

    def test_create_returns_variation_strategy_subclass(self):
        """L'istanza creata e' sempre sottoclasse di VariationStrategy."""
        for mode in EXPECTED_MODE_NAMES:
            result = VariationFactory.create(mode)
            assert isinstance(result, VariationStrategy), (
                f"'{mode}' ha creato {type(result).__name__}, "
                f"non sottoclasse di VariationStrategy"
            )

    def test_create_is_static_method(self):
        """create() e' un metodo statico (chiamabile senza istanza)."""
        # Verifica che funzioni sia su classe che su istanza
        result_class = VariationFactory.create('additive')
        result_instance = VariationFactory().create('additive')

        assert isinstance(result_class, AdditiveVariation)
        assert isinstance(result_instance, AdditiveVariation)


# =============================================================================
# 5. VariationFactory.create() - GESTIONE ERRORI
# =============================================================================

class TestVariationFactoryErrors:
    """Test della gestione errori nella Factory."""

    def test_invalid_mode_raises_value_error(self):
        """Modo non registrato causa ValueError."""
        with pytest.raises(ValueError):
            VariationFactory.create('nonexistent')

    def test_error_message_contains_invalid_mode(self):
        """Il messaggio di errore contiene il modo invalido."""
        with pytest.raises(ValueError, match="nonexistent"):
            VariationFactory.create('nonexistent')

    def test_error_message_contains_available_strategies(self):
        """Il messaggio di errore elenca le strategie disponibili."""
        with pytest.raises(ValueError, match="additive"):
            VariationFactory.create('invalid')

    def test_error_message_format(self):
        """Verifica formato completo del messaggio di errore."""
        with pytest.raises(ValueError) as exc_info:
            VariationFactory.create('xyz')

        msg = str(exc_info.value)
        assert "variation" in msg
        assert "'xyz'" in msg
        assert "Disponibili" in msg
        # Verifica che elenca tutte le strategie
        for mode in EXPECTED_MODE_NAMES:
            assert mode in msg

    def test_case_sensitive_mode_name(self):
        """I nomi dei modi sono case-sensitive."""
        with pytest.raises(ValueError):
            VariationFactory.create('Additive')

    def test_uppercase_mode_raises_error(self):
        """Nome tutto maiuscolo causa errore."""
        with pytest.raises(ValueError):
            VariationFactory.create('ADDITIVE')

    def test_mode_with_leading_space_raises_error(self):
        """Spazio iniziale causa errore (no stripping)."""
        with pytest.raises(ValueError):
            VariationFactory.create(' additive')

    def test_mode_with_trailing_space_raises_error(self):
        """Spazio finale causa errore."""
        with pytest.raises(ValueError):
            VariationFactory.create('additive ')

    def test_empty_string_raises_error(self):
        """Stringa vuota causa errore (a meno che non sia registrata)."""
        # Prima rimuovi eventuale registrazione da altri test
        VARIATION_STRATEGIES.pop('', None)
        with pytest.raises(ValueError):
            VariationFactory.create('')

    def test_none_raises_error(self):
        """None come modo causa errore (TypeError o ValueError)."""
        # 'not in' su dict con None come chiave non causa errore,
        # ma None non sara' nel registry, quindi ValueError
        with pytest.raises((ValueError, TypeError)):
            VariationFactory.create(None)

    def test_numeric_mode_raises_error(self):
        """Valore numerico come modo causa errore."""
        with pytest.raises((ValueError, TypeError)):
            VariationFactory.create(42)

    def test_similar_but_wrong_name(self):
        """Nome simile ma sbagliato causa errore (no fuzzy matching)."""
        with pytest.raises(ValueError):
            VariationFactory.create('aditiv')  # Typo

    def test_similar_name_quantize_without_d(self):
        """'quantize' (senza d) causa errore."""
        with pytest.raises(ValueError):
            VariationFactory.create('quantize')


# =============================================================================
# 6. FACTORY OUTPUT - VALIDAZIONE TIPO E COMPORTAMENTO
# =============================================================================

class TestFactoryOutputBehavior:
    """Verifica che le istanze create abbiano il comportamento atteso."""

    def test_additive_instance_has_apply_method(self):
        """Istanza additive ha metodo apply()."""
        inst = VariationFactory.create('additive')
        assert hasattr(inst, 'apply')
        assert callable(inst.apply)

    def test_quantized_instance_has_apply_method(self):
        """Istanza quantized ha metodo apply()."""
        inst = VariationFactory.create('quantized')
        assert hasattr(inst, 'apply')
        assert callable(inst.apply)

    def test_invert_instance_has_apply_method(self):
        """Istanza invert ha metodo apply()."""
        inst = VariationFactory.create('invert')
        assert hasattr(inst, 'apply')
        assert callable(inst.apply)

    def test_choice_instance_has_apply_method(self):
        """Istanza choice ha metodo apply()."""
        inst = VariationFactory.create('choice')
        assert hasattr(inst, 'apply')
        assert callable(inst.apply)

    def test_additive_apply_with_zero_range(self, mock_dist):
        """Additive con range 0 ritorna base invariato."""
        inst = VariationFactory.create('additive')
        result = inst.apply(440.0, 0.0, mock_dist)
        assert result == 440.0

    def test_additive_apply_with_positive_range(self, mock_dist):
        """Additive con range positivo applica distribuzione."""
        inst = VariationFactory.create('additive')
        # MockDistribution.sample() ritorna center, quindi base
        result = inst.apply(440.0, 10.0, mock_dist)
        assert result == 440.0  # mock ritorna center

    def test_quantized_apply_below_threshold(self, mock_dist):
        """Quantized con range < 1.0 ritorna base invariato."""
        inst = VariationFactory.create('quantized')
        result = inst.apply(5.0, 0.5, mock_dist)
        assert result == 5.0

    def test_quantized_apply_at_threshold(self, mock_dist):
        """Quantized con range >= 1.0 applica variazione arrotondata."""
        inst = VariationFactory.create('quantized')
        # MockDistribution.sample(0.0, range) ritorna 0.0, round(0.0)=0
        result = inst.apply(5.0, 2.0, mock_dist)
        assert result == 5.0  # 5.0 + round(0.0) = 5.0

    def test_invert_apply_zero(self, mock_dist):
        """Invert di 0.0 produce 1.0."""
        inst = VariationFactory.create('invert')
        result = inst.apply(0.0, 0.0, mock_dist)
        assert result == 1.0

    def test_invert_apply_one(self, mock_dist):
        """Invert di 1.0 produce 0.0."""
        inst = VariationFactory.create('invert')
        result = inst.apply(1.0, 0.0, mock_dist)
        assert result == 0.0

    def test_invert_apply_half(self, mock_dist):
        """Invert di 0.5 produce 0.5."""
        inst = VariationFactory.create('invert')
        result = inst.apply(0.5, 0.0, mock_dist)
        assert result == pytest.approx(0.5)

    def test_choice_apply_string_returns_same(self, mock_dist):
        """Choice con stringa singola ritorna la stessa stringa."""
        inst = VariationFactory.create('choice')
        result = inst.apply('hanning', 0.0, mock_dist)
        assert result == 'hanning'

    def test_choice_apply_list_zero_range(self, mock_dist):
        """Choice con lista e range 0 ritorna primo elemento."""
        inst = VariationFactory.create('choice')
        result = inst.apply(['hanning', 'hamming', 'gaussian'], 0.0, mock_dist)
        assert result == 'hanning'

    @pytest.mark.parametrize("mode", list(EXPECTED_MODE_NAMES))
    def test_all_strategies_callable_without_error(self, mode, mock_dist):
        """Ogni strategia creata e' invocabile senza errore."""
        inst = VariationFactory.create(mode)
        # ChoiceVariation richiede stringa/lista, non float
        if mode == 'choice':
            test_value = 'hanning'
        else:
            test_value = 0.5
        try:
            inst.apply(test_value, 0.0, mock_dist)
        except Exception as e:
            pytest.fail(f"'{mode}' apply() ha sollevato {type(e).__name__}: {e}")


# =============================================================================
# 7. INTEGRAZIONE FACTORY-REGISTRY
# =============================================================================

class TestFactoryRegistryIntegration:
    """Test di integrazione tra Factory e Registry dict."""

    def test_factory_reads_from_registry(self):
        """La Factory legge effettivamente dal dizionario VARIATION_STRATEGIES."""
        # Registra una nuova strategia e verifica che la Factory la trovi
        class CustomVariation(VariationStrategy):
            def apply(self, b, m, d):
                return 999.0

        VARIATION_STRATEGIES['custom'] = CustomVariation
        result = VariationFactory.create('custom')
        assert isinstance(result, CustomVariation)

    def test_factory_reflects_registry_removal(self):
        """Se una strategia viene rimossa dal registry, la Factory fallisce."""
        # Rimuovi temporaneamente 'invert'
        saved = VARIATION_STRATEGIES.pop('invert')

        with pytest.raises(ValueError):
            VariationFactory.create('invert')

        # Ripristina (il fixture autouse ripristinera' comunque)
        VARIATION_STRATEGIES['invert'] = saved

    def test_factory_reflects_registry_overwrite(self):
        """Se una strategia viene sovrascritta, la Factory usa la nuova."""
        class NewAdditive(VariationStrategy):
            custom_marker = True
            def apply(self, b, m, d): return b

        VARIATION_STRATEGIES['additive'] = NewAdditive
        result = VariationFactory.create('additive')
        assert hasattr(result, 'custom_marker')
        assert result.custom_marker is True

    def test_all_registry_entries_creatable(self):
        """Ogni entry del registry puo' essere creata dalla Factory."""
        for mode_name in VARIATION_STRATEGIES:
            instance = VariationFactory.create(mode_name)
            assert instance is not None, f"Factory ha creato None per '{mode_name}'"
            assert isinstance(instance, VariationStrategy), (
                f"'{mode_name}' non produce VariationStrategy"
            )

    def test_registered_strategy_appears_in_error_message(self):
        """Una strategia appena registrata appare nel messaggio di errore."""
        class TempVariation(VariationStrategy):
            def apply(self, b, m, d): return b

        register_variation_strategy('temporary', TempVariation)

        with pytest.raises(ValueError) as exc_info:
            VariationFactory.create('wrong_name')

        assert 'temporary' in str(exc_info.value)

    def test_workflow_register_then_create(self):
        """Workflow completo: registra + crea + usa."""
        class DoubleVariation(VariationStrategy):
            def apply(self, base, mod_range, distribution):
                return base * 2

        register_variation_strategy('double', DoubleVariation)
        instance = VariationFactory.create('double')
        result = instance.apply(5.0, 0.0, MockDistribution())

        assert result == 10.0


# =============================================================================
# 8. EDGE CASES E ROBUSTEZZA
# =============================================================================

class TestEdgeCases:
    """Test edge cases e scenari limite."""

    def test_registry_survives_failed_creation(self):
        """Il registry resta intatto dopo un tentativo di creazione fallito."""
        original_keys = set(VARIATION_STRATEGIES.keys())

        with pytest.raises(ValueError):
            VariationFactory.create('does_not_exist')

        assert set(VARIATION_STRATEGIES.keys()) == original_keys

    def test_register_non_subclass_accepted(self):
        """
        register_variation_strategy() non valida il tipo della classe.
        Una classe non-VariationStrategy viene accettata (no type check).
        La Factory la istanzia, ma l'errore emerge all'uso.
        """
        class NotAStrategy:
            pass

        register_variation_strategy('not_strategy', NotAStrategy)
        assert 'not_strategy' in VARIATION_STRATEGIES

        # La Factory la crea (no type check)
        instance = VariationFactory.create('not_strategy')
        assert instance is not None

    def test_register_with_special_characters(self):
        """Nomi con caratteri speciali vengono accettati."""
        class SpecialVariation(VariationStrategy):
            def apply(self, b, m, d): return b

        register_variation_strategy('my-variation_v2.0', SpecialVariation)
        assert 'my-variation_v2.0' in VARIATION_STRATEGIES

    def test_create_preserves_class_identity(self):
        """La classe dell'istanza creata corrisponde a quella nel registry."""
        for mode_name, expected_class in VARIATION_STRATEGIES.items():
            instance = VariationFactory.create(mode_name)
            assert type(instance) is expected_class, (
                f"'{mode_name}': atteso {expected_class.__name__}, "
                f"ottenuto {type(instance).__name__}"
            )

    def test_factory_class_has_no_instance_state(self):
        """VariationFactory non ha stato d'istanza (stateless factory)."""
        f1 = VariationFactory()
        f2 = VariationFactory()
        # Entrambe producono lo stesso risultato
        assert type(f1.create('additive')) == type(f2.create('additive'))

    def test_registry_dict_is_mutable(self):
        """Il registry e' un dict mutabile (design choice per estensibilita')."""
        assert isinstance(VARIATION_STRATEGIES, dict)
        # Verifica mutabilita' (il fixture ripristinera')
        VARIATION_STRATEGIES['temp_test'] = AdditiveVariation
        assert 'temp_test' in VARIATION_STRATEGIES

    def test_concurrent_reads_safe(self):
        """Letture multiple dello stesso modo sono sicure."""
        results = [VariationFactory.create('additive') for _ in range(100)]
        assert all(isinstance(r, AdditiveVariation) for r in results)
        # Tutti diversi (istanze separate)
        ids = [id(r) for r in results]
        assert len(set(ids)) == 100


# =============================================================================
# 9. COERENZA CON parameter_definitions.py
# =============================================================================

class TestCoerenceWithParameterDefinitions:
    """
    Verifica che i variation_mode usati in parameter_definitions.py
    siano tutti presenti nel registry di variation_registry.py.
    
    Questo e' un test di invariante cross-modulo: se qualcuno aggiunge
    un nuovo variation_mode in parameter_definitions senza registrarlo
    qui, il sistema fallira' a runtime.
    """

    VALID_VARIATION_MODES = {'additive', 'quantized', 'invert', 'negate', 'choice'}

    def test_all_valid_modes_in_registry(self):
        """Ogni variation_mode valido ha una strategia registrata."""
        for mode in self.VALID_VARIATION_MODES:
            assert mode in VARIATION_STRATEGIES, (
                f"variation_mode '{mode}' usato in parameter_definitions "
                f"non ha strategia in VARIATION_STRATEGIES"
            )

    def test_registry_only_contains_valid_modes_by_default(self):
        """Il registry di default contiene solo modi validi."""
        assert set(VARIATION_STRATEGIES.keys()) == self.VALID_VARIATION_MODES


# =============================================================================
# 10. TEST PATTERN ARCHITETTURALE
# =============================================================================

class TestArchitecturalPattern:
    """Verifica che il modulo rispetti i pattern architetturali del sistema."""

    def test_follows_same_pattern_as_strategy_registry(self):
        """
        variation_registry segue lo stesso pattern di strategy_registry.py:
        - Dict globale come registry
        - Funzione register_*() per estensione
        - Classe Factory con metodo statico create()
        """
        # Registry e' un dict globale
        assert isinstance(VARIATION_STRATEGIES, dict)

        # Funzione di registrazione esiste ed e' callable
        assert callable(register_variation_strategy)

        # Factory e' una classe con create() statico
        assert isinstance(VariationFactory, type)
        assert hasattr(VariationFactory, 'create')

    def test_factory_create_is_staticmethod(self):
        """create() e' decorato come @staticmethod."""
        # staticmethod: accessibile sia da classe che da istanza
        assert callable(VariationFactory.create)
        assert callable(VariationFactory().create)

    def test_factory_has_docstring(self):
        """La Factory e la sua create() hanno docstring."""
        assert VariationFactory.__doc__ is not None
        assert VariationFactory.create.__doc__ is not None

    def test_register_function_has_docstring(self):
        """register_variation_strategy() ha docstring."""
        assert register_variation_strategy.__doc__ is not None