# test_variation_strategy.py
"""
Suite di test completa per variation_strategy.py

Modulo sotto test:
    - VariationStrategy (ABC)
    - AdditiveVariation
    - QuantizedVariation
    - InvertVariation
    - ChoiceVariation

Copertura target: 100% linee e branch.

Strategia di mocking:
    - DistributionStrategy viene mockato per isolare il comportamento
      delle variation strategy dal campionamento stocastico.
    - WindowRegistry viene mockato tramite sys.modules injection
      per ChoiceVariation quando value=True.
    - random.choice viene patchato per test deterministici di ChoiceVariation.
"""

import sys
import types
import pytest
import random
from unittest.mock import Mock, patch, MagicMock
from abc import ABC

from shared.distribution_strategy import DistributionStrategy
from strategies.variation_strategy import (
    VariationStrategy,
    AdditiveVariation,
    QuantizedVariation,
    InvertVariation,
    ChoiceVariation,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_distribution():
    """
    DistributionStrategy mock con sample() controllabile.
    Default: sample ritorna center + spread (prevedibile per assertion).
    """
    dist = Mock(spec=DistributionStrategy)
    dist.sample.return_value = 0.0  # default safe
    return dist


@pytest.fixture
def additive():
    """Istanza AdditiveVariation."""
    return AdditiveVariation()


@pytest.fixture
def quantized():
    """Istanza QuantizedVariation."""
    return QuantizedVariation()


@pytest.fixture
def invert():
    """Istanza InvertVariation."""
    return InvertVariation()


@pytest.fixture
def choice():
    """Istanza ChoiceVariation."""
    return ChoiceVariation()


# =============================================================================
# 1. TEST VariationStrategy (ABC)
# =============================================================================

class TestVariationStrategyABC:
    """
    Test della classe base astratta VariationStrategy.
    Verifica: ereditarieta' ABC, metodo astratto apply(), impossibilita'
    di istanziare direttamente.
    """

    def test_is_abstract_class(self):
        """VariationStrategy e' una ABC."""
        assert issubclass(VariationStrategy, ABC)

    def test_cannot_instantiate_directly(self):
        """Non si puo' istanziare VariationStrategy direttamente."""
        with pytest.raises(TypeError):
            VariationStrategy()

    def test_apply_is_abstract(self):
        """apply() e' dichiarato astratto."""
        assert 'apply' in VariationStrategy.__abstractmethods__

    def test_subclass_must_implement_apply(self):
        """Sottoclasse senza apply() non e' istanziabile."""
        class IncompleteVariation(VariationStrategy):
            pass

        with pytest.raises(TypeError):
            IncompleteVariation()

    def test_subclass_with_apply_is_valid(self):
        """Sottoclasse che implementa apply() e' istanziabile."""
        class ConcreteVariation(VariationStrategy):
            def apply(self, base, mod_range, distribution):
                return base

        v = ConcreteVariation()
        assert v.apply(5.0, 1.0, None) == 5.0

    def test_all_concrete_classes_are_subclasses(self):
        """Tutte le classi concrete ereditano da VariationStrategy."""
        for cls in [AdditiveVariation, QuantizedVariation,
                    InvertVariation, ChoiceVariation]:
            assert issubclass(cls, VariationStrategy)


# =============================================================================
# 2. TEST AdditiveVariation
# =============================================================================

class TestAdditiveVariationInit:
    """Test costruzione AdditiveVariation."""

    def test_instantiation(self, additive):
        """Puo' essere istanziata."""
        assert additive is not None

    def test_is_variation_strategy(self, additive):
        """E' sottoclasse di VariationStrategy."""
        assert isinstance(additive, VariationStrategy)


class TestAdditiveVariationApply:
    """
    Test apply() di AdditiveVariation.
    Comportamento: delega a distribution.sample(base, mod_range) se mod_range > 0,
    altrimenti ritorna base invariato.
    """

    def test_mod_range_zero_returns_base(self, additive, mock_distribution):
        """mod_range=0 -> ritorna base senza chiamare distribution."""
        result = additive.apply(440.0, 0.0, mock_distribution)
        assert result == 440.0
        mock_distribution.sample.assert_not_called()

    def test_mod_range_negative_returns_base(self, additive, mock_distribution):
        """mod_range negativo -> ritorna base (condizione > 0 non soddisfatta)."""
        result = additive.apply(100.0, -5.0, mock_distribution)
        assert result == 100.0
        mock_distribution.sample.assert_not_called()

    def test_mod_range_positive_delegates_to_distribution(self, additive, mock_distribution):
        """mod_range > 0 -> chiama distribution.sample(base, mod_range)."""
        mock_distribution.sample.return_value = 445.0
        result = additive.apply(440.0, 10.0, mock_distribution)

        assert result == 445.0
        mock_distribution.sample.assert_called_once_with(440.0, 10.0)

    def test_passes_exact_args_to_sample(self, additive, mock_distribution):
        """Verifica che base e mod_range vengano passati esattamente."""
        mock_distribution.sample.return_value = 0.0
        additive.apply(123.456, 78.9, mock_distribution)
        mock_distribution.sample.assert_called_once_with(123.456, 78.9)

    def test_returns_distribution_sample_value(self, additive, mock_distribution):
        """Il valore ritornato e' esattamente quello di distribution.sample()."""
        mock_distribution.sample.return_value = -999.5
        result = additive.apply(0.0, 1.0, mock_distribution)
        assert result == -999.5

    def test_very_small_positive_range(self, additive, mock_distribution):
        """mod_range molto piccolo ma positivo -> delega comunque."""
        mock_distribution.sample.return_value = 440.001
        result = additive.apply(440.0, 0.001, mock_distribution)
        assert result == 440.001
        mock_distribution.sample.assert_called_once()

    def test_large_mod_range(self, additive, mock_distribution):
        """mod_range molto grande -> delega normalmente."""
        mock_distribution.sample.return_value = 1000.0
        result = additive.apply(500.0, 10000.0, mock_distribution)
        assert result == 1000.0
        mock_distribution.sample.assert_called_once_with(500.0, 10000.0)

    def test_base_zero_with_positive_range(self, additive, mock_distribution):
        """base=0 con mod_range > 0 -> delega normalmente."""
        mock_distribution.sample.return_value = 0.5
        result = additive.apply(0.0, 1.0, mock_distribution)
        assert result == 0.5

    def test_base_negative(self, additive, mock_distribution):
        """base negativo -> delega normalmente (nessun vincolo su base)."""
        mock_distribution.sample.return_value = -15.0
        result = additive.apply(-10.0, 10.0, mock_distribution)
        assert result == -15.0
        mock_distribution.sample.assert_called_once_with(-10.0, 10.0)


# =============================================================================
# 3. TEST QuantizedVariation
# =============================================================================

class TestQuantizedVariationInit:
    """Test costruzione QuantizedVariation."""

    def test_instantiation(self, quantized):
        """Puo' essere istanziata."""
        assert quantized is not None

    def test_is_variation_strategy(self, quantized):
        """E' sottoclasse di VariationStrategy."""
        assert isinstance(quantized, VariationStrategy)


class TestQuantizedVariationApply:
    """
    Test apply() di QuantizedVariation.
    Comportamento:
        - Se mod_range >= 1.0: chiama distribution.sample(0.0, mod_range),
          arrotonda il risultato e lo somma a base.
        - Se mod_range < 1.0: ritorna base invariato.
    """

    def test_mod_range_below_one_returns_base(self, quantized, mock_distribution):
        """mod_range < 1.0 -> ritorna base senza variazione."""
        result = quantized.apply(10.0, 0.5, mock_distribution)
        assert result == 10.0
        mock_distribution.sample.assert_not_called()

    def test_mod_range_zero_returns_base(self, quantized, mock_distribution):
        """mod_range = 0 -> ritorna base."""
        result = quantized.apply(42.0, 0.0, mock_distribution)
        assert result == 42.0
        mock_distribution.sample.assert_not_called()

    def test_mod_range_negative_returns_base(self, quantized, mock_distribution):
        """mod_range negativo -> ritorna base."""
        result = quantized.apply(42.0, -3.0, mock_distribution)
        assert result == 42.0
        mock_distribution.sample.assert_not_called()

    def test_mod_range_exactly_one(self, quantized, mock_distribution):
        """mod_range = 1.0 -> attiva variazione (condizione >=)."""
        mock_distribution.sample.return_value = 0.7
        result = quantized.apply(5.0, 1.0, mock_distribution)
        # round(0.7) = 1, result = 5.0 + 1 = 6.0
        assert result == 6.0
        mock_distribution.sample.assert_called_once_with(0.0, 1.0)

    def test_sample_center_is_zero(self, quantized, mock_distribution):
        """distribution.sample() viene chiamato con center=0.0."""
        mock_distribution.sample.return_value = 2.3
        quantized.apply(10.0, 5.0, mock_distribution)
        mock_distribution.sample.assert_called_once_with(0.0, 5.0)

    def test_rounds_positive_sample(self, quantized, mock_distribution):
        """Arrotondamento positivo: 2.7 -> 3."""
        mock_distribution.sample.return_value = 2.7
        result = quantized.apply(100.0, 5.0, mock_distribution)
        assert result == 103.0  # 100 + round(2.7) = 100 + 3

    def test_rounds_negative_sample(self, quantized, mock_distribution):
        """Arrotondamento negativo: -1.3 -> -1."""
        mock_distribution.sample.return_value = -1.3
        result = quantized.apply(100.0, 5.0, mock_distribution)
        assert result == 99.0  # 100 + round(-1.3) = 100 + (-1)

    def test_rounds_half_up(self, quantized, mock_distribution):
        """Arrotondamento .5 -> banker's rounding in Python (pari)."""
        mock_distribution.sample.return_value = 0.5
        result = quantized.apply(10.0, 2.0, mock_distribution)
        # Python round(0.5) = 0 (banker's rounding)
        assert result == 10.0

    def test_rounds_1_5_to_2(self, quantized, mock_distribution):
        """round(1.5) = 2 in Python (banker's rounding, arrotonda al pari)."""
        mock_distribution.sample.return_value = 1.5
        result = quantized.apply(10.0, 5.0, mock_distribution)
        assert result == 12.0  # 10 + round(1.5) = 10 + 2

    def test_sample_zero_no_offset(self, quantized, mock_distribution):
        """distribution ritorna 0.0 -> risultato uguale a base."""
        mock_distribution.sample.return_value = 0.0
        result = quantized.apply(50.0, 3.0, mock_distribution)
        assert result == 50.0

    def test_large_quantized_offset(self, quantized, mock_distribution):
        """Offset quantizzato grande."""
        mock_distribution.sample.return_value = 99.8
        result = quantized.apply(0.0, 200.0, mock_distribution)
        assert result == 100.0  # 0 + round(99.8) = 100

    def test_result_is_always_integer_offset(self, quantized, mock_distribution):
        """L'offset e' sempre un intero (round produce int in Python 3)."""
        mock_distribution.sample.return_value = 3.14159
        result = quantized.apply(10.0, 5.0, mock_distribution)
        offset = result - 10.0
        assert offset == round(offset)  # l'offset e' intero

    @pytest.mark.parametrize("sample_val,expected_offset", [
        (0.1, 0), (0.4, 0), (0.6, 1), (0.9, 1),
        (-0.1, 0), (-0.4, 0), (-0.6, -1), (-0.9, -1),
        (2.49, 2), (2.51, 3), (-2.49, -2), (-2.51, -3),
    ])
    def test_rounding_parametrized(self, quantized, mock_distribution,
                                    sample_val, expected_offset):
        """Verifica arrotondamento per vari valori campionati."""
        mock_distribution.sample.return_value = sample_val
        result = quantized.apply(0.0, 10.0, mock_distribution)
        assert result == expected_offset


# =============================================================================
# 4. TEST InvertVariation
# =============================================================================

class TestInvertVariationInit:
    """Test costruzione InvertVariation."""

    def test_instantiation(self, invert):
        """Puo' essere istanziata."""
        assert invert is not None

    def test_is_variation_strategy(self, invert):
        """E' sottoclasse di VariationStrategy."""
        assert isinstance(invert, VariationStrategy)


class TestInvertVariationApply:
    """
    Test apply() di InvertVariation.
    Comportamento: ritorna sempre 1.0 - base.
    Ignora mod_range e distribution.
    """

    def test_invert_zero(self, invert, mock_distribution):
        """base=0.0 -> 1.0."""
        assert invert.apply(0.0, 0.0, mock_distribution) == 1.0

    def test_invert_one(self, invert, mock_distribution):
        """base=1.0 -> 0.0."""
        assert invert.apply(1.0, 0.0, mock_distribution) == 0.0

    def test_invert_half(self, invert, mock_distribution):
        """base=0.5 -> 0.5."""
        assert invert.apply(0.5, 0.0, mock_distribution) == 0.5

    def test_invert_quarter(self, invert, mock_distribution):
        """base=0.25 -> 0.75."""
        assert invert.apply(0.25, 0.0, mock_distribution) == pytest.approx(0.75)

    def test_ignores_mod_range(self, invert, mock_distribution):
        """mod_range non influenza il risultato."""
        r1 = invert.apply(0.3, 0.0, mock_distribution)
        r2 = invert.apply(0.3, 100.0, mock_distribution)
        r3 = invert.apply(0.3, -50.0, mock_distribution)
        assert r1 == r2 == r3

    def test_ignores_distribution(self, invert):
        """distribution non viene usato (puo' essere None)."""
        result = invert.apply(0.7, 5.0, None)
        assert result == pytest.approx(0.3)

    def test_distribution_sample_never_called(self, invert, mock_distribution):
        """distribution.sample() non viene mai chiamato."""
        invert.apply(0.5, 10.0, mock_distribution)
        mock_distribution.sample.assert_not_called()

    def test_values_outside_0_1_range(self, invert, mock_distribution):
        """Funziona anche con base fuori [0,1] (nessun clamping interno)."""
        assert invert.apply(2.0, 0.0, mock_distribution) == -1.0
        assert invert.apply(-0.5, 0.0, mock_distribution) == 1.5

    def test_double_inversion_identity(self, invert, mock_distribution):
        """Doppia inversione = identita'."""
        base = 0.37
        first = invert.apply(base, 0.0, mock_distribution)
        second = invert.apply(first, 0.0, mock_distribution)
        assert second == pytest.approx(base)

    @pytest.mark.parametrize("base,expected", [
        (0.0, 1.0), (0.1, 0.9), (0.2, 0.8), (0.3, 0.7),
        (0.4, 0.6), (0.5, 0.5), (0.6, 0.4), (0.7, 0.3),
        (0.8, 0.2), (0.9, 0.1), (1.0, 0.0),
    ])
    def test_inversion_parametrized(self, invert, mock_distribution,
                                     base, expected):
        """Inversione corretta per range [0, 1] a passi di 0.1."""
        assert invert.apply(base, 0.0, mock_distribution) == pytest.approx(expected)


# =============================================================================
# 5. TEST ChoiceVariation - Caso Stringa Singola
# =============================================================================

class TestChoiceVariationInit:
    """Test costruzione ChoiceVariation."""

    def test_instantiation(self, choice):
        """Puo' essere istanziata."""
        assert choice is not None

    def test_is_variation_strategy(self, choice):
        """E' sottoclasse di VariationStrategy."""
        assert isinstance(choice, VariationStrategy)


class TestChoiceVariationStringInput:
    """
    Test con value=stringa singola.
    Comportamento: ritorna la stringa invariata (deterministico).
    """

    def test_string_returns_same_string(self, choice, mock_distribution):
        """Stringa singola -> ritorno identico."""
        assert choice.apply('hanning', 0.0, mock_distribution) == 'hanning'

    def test_string_ignores_mod_range(self, choice, mock_distribution):
        """mod_range non influenza il risultato con stringa."""
        assert choice.apply('hamming', 10.0, mock_distribution) == 'hamming'
        assert choice.apply('hamming', 0.0, mock_distribution) == 'hamming'

    def test_string_ignores_distribution(self, choice):
        """distribution non viene usato con stringa."""
        assert choice.apply('gaussian', 5.0, None) == 'gaussian'

    def test_various_strings(self, choice, mock_distribution):
        """Funziona con qualsiasi stringa."""
        for name in ['hanning', 'bartlett', 'expodec', 'custom_name']:
            assert choice.apply(name, 1.0, mock_distribution) == name

    def test_empty_string(self, choice, mock_distribution):
        """Stringa vuota e' pur sempre una stringa."""
        assert choice.apply('', 1.0, mock_distribution) == ''


# =============================================================================
# 6. TEST ChoiceVariation - Caso value=True (espansione WindowRegistry)
# =============================================================================

class TestChoiceVariationTrueExpansion:
    """
    Test con value=True -> espande a tutte le finestre di WindowRegistry.
    Richiede mock di WindowRegistry poiche' import lazy.
    """

    def _make_mock_registry(self, window_names):
        """Helper: crea modulo mock con WindowRegistry.WINDOWS."""
        fake_module = types.ModuleType('window_registry')
        mock_registry = type('WindowRegistry', (), {
            'WINDOWS': {name: f"spec_{name}" for name in window_names}
        })
        fake_module.WindowRegistry = mock_registry
        return fake_module

    def test_true_expands_to_all_windows(self, choice, mock_distribution):
        """value=True -> espande a lista di tutte le finestre."""
        window_names = ['hanning', 'hamming', 'bartlett']
        fake_module = self._make_mock_registry(window_names)

        with patch.dict('sys.modules', {'window_registry': fake_module}):
            with patch('random.choice', return_value='hamming'):
                result = choice.apply(True, 1.0, mock_distribution)
                assert result in window_names

    def test_true_with_mod_range_zero(self, choice, mock_distribution):
        """value=True + mod_range=0 -> ritorna primo elemento (default)."""
        window_names = ['hanning', 'hamming', 'bartlett']
        fake_module = self._make_mock_registry(window_names)

        with patch.dict('sys.modules', {'window_registry': fake_module}):
            result = choice.apply(True, 0, mock_distribution)
            # mod_range == 0 -> ritorna value[0], cioe' prima chiave del dict
            assert result == list(
                fake_module.WindowRegistry.WINDOWS.keys()
            )[0]

    def test_true_with_positive_mod_range_calls_random_choice(self, choice, mock_distribution):
        """value=True + mod_range > 0 -> chiama random.choice."""
        window_names = ['hanning', 'hamming']
        fake_module = self._make_mock_registry(window_names)

        with patch.dict('sys.modules', {'window_registry': fake_module}):
            with patch('random.choice', return_value='hamming') as mock_rc:
                result = choice.apply(True, 1.0, mock_distribution)
                mock_rc.assert_called_once()
                assert result == 'hamming'


# =============================================================================
# 7. TEST ChoiceVariation - Caso Lista Esplicita
# =============================================================================

class TestChoiceVariationListInput:
    """
    Test con value=lista.
    Comportamento: se mod_range > 0 -> random.choice(lista),
                   se mod_range == 0 -> ritorna lista[0].
    """

    def test_list_mod_range_zero_returns_first(self, choice, mock_distribution):
        """mod_range=0 con lista -> ritorna primo elemento."""
        result = choice.apply(['hanning', 'hamming', 'bartlett'], 0, mock_distribution)
        assert result == 'hanning'

    def test_list_mod_range_positive_random_choice(self, choice, mock_distribution):
        """mod_range > 0 con lista -> selezione random."""
        options = ['a', 'b', 'c']
        with patch('random.choice', return_value='b') as mock_rc:
            result = choice.apply(options, 1.0, mock_distribution)
            mock_rc.assert_called_once_with(options)
            assert result == 'b'

    def test_single_element_list_mod_range_zero(self, choice, mock_distribution):
        """Lista con un solo elemento + mod_range=0 -> ritorna quell'elemento."""
        result = choice.apply(['only_one'], 0, mock_distribution)
        assert result == 'only_one'

    def test_single_element_list_mod_range_positive(self, choice, mock_distribution):
        """Lista singola + mod_range > 0 -> random.choice comunque."""
        with patch('random.choice', return_value='only_one'):
            result = choice.apply(['only_one'], 1.0, mock_distribution)
            assert result == 'only_one'

    def test_empty_list_mod_range_zero_returns_default(self, choice, mock_distribution):
        """Lista vuota + mod_range=0 -> ritorna 'hanning' (default)."""
        result = choice.apply([], 0, mock_distribution)
        assert result == 'hanning'

    def test_empty_list_mod_range_positive_raises_or_handles(self, choice, mock_distribution):
        """Lista vuota + mod_range > 0 -> random.choice([]) solleva IndexError."""
        with pytest.raises(IndexError):
            choice.apply([], 1.0, mock_distribution)

    def test_list_of_numbers(self, choice, mock_distribution):
        """Lista di numeri funziona."""
        options = [1, 2, 3, 4, 5]
        with patch('random.choice', return_value=3):
            result = choice.apply(options, 1.0, mock_distribution)
            assert result == 3

    def test_list_mod_range_zero_always_deterministic(self, choice, mock_distribution):
        """mod_range=0 -> sempre primo elemento, nessuna stocasticita'."""
        options = ['x', 'y', 'z']
        results = [choice.apply(options, 0, mock_distribution) for _ in range(50)]
        assert all(r == 'x' for r in results)


# =============================================================================
# 8. TEST ChoiceVariation - Tipo Non Valido
# =============================================================================

class TestChoiceVariationInvalidType:
    """
    Test con value di tipo non supportato.
    Comportamento: solleva TypeError.
    """

    def test_integer_raises_type_error(self, choice, mock_distribution):
        """value=int -> TypeError."""
        with pytest.raises(__import__('shared.exceptions', fromlist=['InvalidParameterError']).InvalidParameterError, match="ChoiceVariation"):
            choice.apply(42, 1.0, mock_distribution)

    def test_float_raises_type_error(self, choice, mock_distribution):
        """value=float -> TypeError."""
        with pytest.raises(__import__('shared.exceptions', fromlist=['InvalidParameterError']).InvalidParameterError, match="ChoiceVariation"):
            choice.apply(3.14, 1.0, mock_distribution)

    def test_none_raises_type_error(self, choice, mock_distribution):
        """value=None -> TypeError."""
        with pytest.raises(__import__('shared.exceptions', fromlist=['InvalidParameterError']).InvalidParameterError, match="ChoiceVariation"):
            choice.apply(None, 1.0, mock_distribution)

    def test_dict_raises_type_error(self, choice, mock_distribution):
        """value=dict -> TypeError."""
        with pytest.raises(__import__('shared.exceptions', fromlist=['InvalidParameterError']).InvalidParameterError, match="ChoiceVariation"):
            choice.apply({'key': 'val'}, 1.0, mock_distribution)

    def test_tuple_raises_type_error(self, choice, mock_distribution):
        """value=tuple -> TypeError (non e' lista)."""
        with pytest.raises(__import__('shared.exceptions', fromlist=['InvalidParameterError']).InvalidParameterError, match="ChoiceVariation"):
            choice.apply(('a', 'b'), 1.0, mock_distribution)

    def test_error_message_contains_value(self, choice, mock_distribution):
        """Il messaggio di errore contiene il valore ricevuto."""
        from shared.exceptions import InvalidParameterError
        with pytest.raises(InvalidParameterError, match="42"):
            choice.apply(42, 1.0, mock_distribution)


# =============================================================================
# 9. TEST ChoiceVariation - Caso stringa 'all'
# =============================================================================

class TestChoiceVariationStringAll:
    """
    Test con value='all' -> dovrebbe espandere come True.
    Nota: il codice controlla isinstance(value, str) PRIMA del check
    value.lower() == 'all', quindi 'all' viene trattato come stringa
    singola e ritornato invariato.
    """

    def test_string_all_returns_string_all(self, choice, mock_distribution):
        """
        'all' come stringa viene intercettato dal caso 1 (isinstance str)
        e ritornato direttamente, NON espanso.
        Questo e' il comportamento attuale del codice: il check
        isinstance(value, str) ha priorita' su value.lower() == 'all'.
        """
        result = choice.apply('all', 1.0, mock_distribution)
        assert result == 'all'


# =============================================================================
# 10. TEST Integrazione Statistica (senza mock di random)
# =============================================================================

class TestChoiceVariationStatistical:
    """
    Test statistici per ChoiceVariation con random reale.
    Verifica distribuzione uniforme della selezione.
    """

    def test_list_selection_covers_all_options(self, choice, mock_distribution):
        """Con mod_range > 0, tutti gli elementi della lista vengono scelti."""
        options = ['a', 'b', 'c', 'd']
        results = set()
        for _ in range(500):
            r = choice.apply(options, 1.0, mock_distribution)
            results.add(r)
        assert results == set(options)

    def test_list_selection_roughly_uniform(self, choice, mock_distribution):
        """La distribuzione e' approssimativamente uniforme."""
        options = ['a', 'b', 'c']
        counts = {o: 0 for o in options}
        n = 3000
        for _ in range(n):
            r = choice.apply(options, 1.0, mock_distribution)
            counts[r] += 1

        expected = n / len(options)
        for option, count in counts.items():
            assert abs(count - expected) < expected * 0.15, \
                f"Opzione '{option}': {count} vs atteso ~{expected}"


# =============================================================================
# 11. TEST Cross-Strategy: Polimorfismo
# =============================================================================

class TestVariationPolymorphism:
    """
    Test polimorfismo: tutte le strategie rispondono a apply()
    con la stessa signature (anche se ChoiceVariation accetta Any).
    """

    def test_all_strategies_callable_with_same_signature(self, mock_distribution):
        """Tutte le strategie accettano (base/value, mod_range, distribution)."""
        mock_distribution.sample.return_value = 0.5

        # Strategie numeriche: stessa signature con float
        for s in [AdditiveVariation(), QuantizedVariation(), InvertVariation()]:
            result = s.apply(0.5, 1.0, mock_distribution)
            assert isinstance(result, (int, float))

        # ChoiceVariation: stessa signature ma value=stringa
        cv = ChoiceVariation()
        result = cv.apply('hanning', 1.0, mock_distribution)
        assert isinstance(result, str)

    def test_strategy_dispatch_pattern(self, mock_distribution):
        """Simula il dispatch dictionary pattern usato in Parameter."""
        mock_distribution.sample.return_value = 5.0
        dispatch = {
            'additive': AdditiveVariation(),
            'quantized': QuantizedVariation(),
            'invert': InvertVariation(),
            'choice': ChoiceVariation(),
        }

        # Additive con variazione
        assert dispatch['additive'].apply(10.0, 5.0, mock_distribution) == 5.0

        # Invert
        assert dispatch['invert'].apply(0.3, 0.0, mock_distribution) == pytest.approx(0.7)

        # Choice con stringa
        assert dispatch['choice'].apply('hanning', 1.0, mock_distribution) == 'hanning'


# =============================================================================
# 12. TEST Edge Cases Numerici
# =============================================================================

class TestEdgeCasesNumerici:
    """Test con valori numerici estremi o particolari."""

    def test_additive_with_infinity(self, additive, mock_distribution):
        """Base infinity non causa crash."""
        mock_distribution.sample.return_value = float('inf')
        result = additive.apply(float('inf'), 1.0, mock_distribution)
        assert result == float('inf')

    def test_quantized_very_large_sample(self, quantized, mock_distribution):
        """Quantized con sample enorme -> round() funziona."""
        mock_distribution.sample.return_value = 999999.9
        result = quantized.apply(0.0, 1000000.0, mock_distribution)
        assert result == 1000000.0

    def test_invert_with_nan(self, invert, mock_distribution):
        """Invert con NaN -> risultato e' NaN (1.0 - NaN = NaN)."""
        import math
        result = invert.apply(float('nan'), 0.0, mock_distribution)
        assert math.isnan(result)

    def test_additive_mod_range_exactly_zero_boundary(self, additive, mock_distribution):
        """mod_range = 0.0 esatto: condizione > 0 e' False."""
        result = additive.apply(42.0, 0.0, mock_distribution)
        assert result == 42.0

    def test_quantized_mod_range_just_below_one(self, quantized, mock_distribution):
        """mod_range = 0.999... -> < 1.0 -> nessuna variazione."""
        result = quantized.apply(10.0, 0.9999, mock_distribution)
        assert result == 10.0
        mock_distribution.sample.assert_not_called()

    def test_quantized_mod_range_exactly_one_boundary(self, quantized, mock_distribution):
        """mod_range = 1.0 esatto: condizione >= 1.0 e' True."""
        mock_distribution.sample.return_value = 0.0
        result = quantized.apply(10.0, 1.0, mock_distribution)
        assert result == 10.0  # round(0.0) = 0, 10 + 0 = 10
        mock_distribution.sample.assert_called_once()



class TestVariationStrategyAbstractBody:
    """Copre riga 14: corpo del metodo astratto apply via super()."""

    def test_abstract_apply_body_returns_none(self):
        """super().apply() esegue il pass e ritorna None."""
        from unittest.mock import MagicMock

        mock_dist = MagicMock()
        mock_dist.sample.return_value = 1.0

        class _ConcreteStrategy(VariationStrategy):
            def apply(self, base, mod_range, distribution):
                return super().apply(base, mod_range, distribution)

        strategy = _ConcreteStrategy()
        result = strategy.apply(1.0, 0.5, mock_dist)
        assert result is None