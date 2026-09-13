# tests/controllers/test_window_registry_new.py
"""
Suite di test per src/controllers/window_registry.py

Classi testate:
    - WindowSpec  (dataclass)
    - WindowRegistry (classe con classmethod)

Struttura:
    1.  TestWindowSpecCreation          - istanziazione e valori default
    2.  TestWindowSpecFieldTypes        - tipi dei campi
    3.  TestWindowSpecEquality          - confronto tra istanze
    4.  TestWindowSpecImmutability      - comportamento dataclass
    5.  TestWindowRegistryGet           - get(): lookup diretto, alias, fallback
    6.  TestWindowRegistryGetCaseSensitivity - case sensitivity di get()
    7.  TestWindowRegistryAllNames      - all_names(): contenuto e tipo
    8.  TestWindowRegistryGetByFamily   - get_by_family(): filtro famiglie
    9. TestWindowRegistryDataIntegrity - invarianti strutturali di WINDOWS e ALIASES
    10. TestWindowRegistryParametrized  - test parametrizzati su ogni window
    11. TestWindowRegistryIntegration   - workflow end-to-end

L'f-statement Csound non e' piu' materia del catalogo (issue #203): i test
sulla sua forma stanno in tests/rendering/test_csound_emitter.py.

E dalla issue #202 non lo sono nemmeno la GEN routine e i suoi parametri: il
catalogo descrive la finestra in termini propri -- forma, coefficienti,
simmetria -- e sono gli emitter a tradurla per un target. La tabella degli
attesi qui sotto e' quindi diventata la tabella delle *forme*; quella delle
GEN e' il test del traduttore Csound
(tests/rendering/test_csound_window_emitter.py), e la parita' fra forma
dichiarata e forma prodotta sta in
tests/rendering/test_window_shape_parity.py.
"""

from dataclasses import replace

import numpy as np
import pytest

from pge.controllers.window_registry import (
    ASYMMETRIC,
    SYMMETRIC,
    WindowRegistry,
    WindowShape,
    WindowSpec,
    missing_shape_fields,
)
from pge.rendering.numpy_window_emitter import NumpyWindowEmitter


# ===========================================================================
# COSTANTI DI RIFERIMENTO
# ===========================================================================

ALL_WINDOW_NAMES = {
    'hamming', 'hanning', 'bartlett', 'blackman', 'blackman_harris',
    'gaussian', 'kaiser', 'rectangle', 'sinc',
    'half_sine',
    'expodec', 'expodec_strong', 'exporise', 'exporise_strong',
    'rexpodec', 'rexporise',
}

FAMILY_WINDOW = {
    'hamming', 'hanning', 'bartlett', 'blackman', 'blackman_harris',
    'gaussian', 'kaiser', 'rectangle', 'sinc',
}
FAMILY_ASYMMETRIC = {
    'expodec', 'expodec_strong', 'exporise', 'exporise_strong',
    'rexpodec', 'rexporise',
}
FAMILY_CUSTOM = {'half_sine'}

VALID_FAMILIES = {'window', 'asymmetric', 'custom'}

# (shape, coefficients, params, symmetry) per ogni window - ground truth.
# E' la descrizione, non la sua traduzione: qui non compare nessun numero di
# GEN routine, ed e' esattamente cio' che la issue #202 chiedeva.
EXPECTED_SHAPES = {
    'hamming':         (WindowShape.COSINE_SUM,
                        (0.54, 0.46), {}, SYMMETRIC),
    'hanning':         (WindowShape.COSINE_SUM,
                        (0.5, 0.5), {}, SYMMETRIC),
    'bartlett':        (WindowShape.TRIANGULAR,
                        (), {}, SYMMETRIC),
    'blackman':        (WindowShape.COSINE_SUM,
                        (0.42, 0.5, 0.08), {}, SYMMETRIC),
    'blackman_harris': (WindowShape.COSINE_SUM,
                        (0.35875, 0.48829, 0.14128, 0.01168), {}, SYMMETRIC),
    'gaussian':        (WindowShape.GAUSSIAN,
                        (), {'sigma': 0.4}, SYMMETRIC),
    'kaiser':          (WindowShape.KAISER,
                        (), {'beta': 6.0}, SYMMETRIC),
    'rectangle':       (WindowShape.RECTANGULAR,
                        (), {}, SYMMETRIC),
    'sinc':            (WindowShape.SINC_LOBE,
                        (), {}, SYMMETRIC),
    'half_sine':       (WindowShape.SINE_LOBE,
                        (), {}, SYMMETRIC),
    'expodec':         (WindowShape.EXPONENTIAL_SEGMENT, (),
                        {'start': 1.0, 'curve': 4.0, 'end': 0.0}, ASYMMETRIC),
    'expodec_strong':  (WindowShape.EXPONENTIAL_SEGMENT, (),
                        {'start': 1.0, 'curve': 10.0, 'end': 0.0}, ASYMMETRIC),
    'exporise':        (WindowShape.EXPONENTIAL_SEGMENT, (),
                        {'start': 0.0, 'curve': -4.0, 'end': 1.0}, ASYMMETRIC),
    'exporise_strong': (WindowShape.EXPONENTIAL_SEGMENT, (),
                        {'start': 0.0, 'curve': -10.0, 'end': 1.0}, ASYMMETRIC),
    'rexpodec':        (WindowShape.EXPONENTIAL_SEGMENT, (),
                        {'start': 1.0, 'curve': -4.0, 'end': 0.0}, ASYMMETRIC),
    'rexporise':       (WindowShape.EXPONENTIAL_SEGMENT, (),
                        {'start': 0.0, 'curve': 4.0, 'end': 1.0}, ASYMMETRIC),
}

KNOWN_ALIASES = {
    'triangle': 'bartlett',
}


# ===========================================================================
# 1. TestWindowSpecCreation
# ===========================================================================

class TestWindowSpecCreation:

    def test_full_instantiation(self):
        spec = WindowSpec(
            name='test_window',
            shape=WindowShape.COSINE_SUM,
            coefficients=(0.5, 0.5),
            description="Test window",
            family="window",
        )
        assert spec.name == 'test_window'
        assert spec.shape == WindowShape.COSINE_SUM
        assert spec.coefficients == (0.5, 0.5)
        assert spec.description == "Test window"
        assert spec.family == "window"

    def test_family_default_is_window(self):
        spec = WindowSpec(
            name='x',
            shape=WindowShape.RECTANGULAR,
            description="desc",
        )
        assert spec.family == "window"

    def test_symmetry_default_is_symmetric(self):
        """La maggioranza del catalogo e' simmetrica; l'asimmetria si
        dichiara."""
        spec = WindowSpec(
            name='x',
            shape=WindowShape.RECTANGULAR,
            description="desc",
        )
        assert spec.symmetry == SYMMETRIC

    def test_params_accept_floats(self):
        spec = WindowSpec(
            name='gaussian_wide',
            shape=WindowShape.GAUSSIAN,
            params={'sigma': 0.9},
            description="Gaussian",
        )
        assert spec.param('sigma') == 0.9

    def test_params_accept_negative_values(self):
        spec = WindowSpec(
            name='exporise',
            shape=WindowShape.EXPONENTIAL_SEGMENT,
            params={'start': 0.0, 'curve': -4.0, 'end': 1.0},
            description="Exporise",
            family="asymmetric",
            symmetry=ASYMMETRIC,
        )
        assert spec.param('curve') == -4.0

    def test_param_returns_the_default_when_absent(self):
        spec = WindowSpec(name='x', shape=WindowShape.RECTANGULAR,
                          description="d")
        assert spec.param('sigma') is None
        assert spec.param('sigma', 0.4) == 0.4

    def test_coefficients_default_is_empty(self):
        spec = WindowSpec(name='x', shape=WindowShape.RECTANGULAR,
                          description="d")
        assert spec.coefficients == ()


# ===========================================================================
# 2. TestWindowSpecFieldTypes
# ===========================================================================

class TestWindowSpecFieldTypes:

    @pytest.fixture
    def spec(self):
        return WindowSpec(name='hanning', shape=WindowShape.COSINE_SUM,
                          coefficients=(0.5, 0.5), description="desc")

    def test_name_is_str(self, spec):
        assert isinstance(spec.name, str)

    def test_shape_is_str(self, spec):
        assert isinstance(spec.shape, str)

    def test_coefficients_is_a_tuple(self, spec):
        """Anche quando arrivano come lista: la spec e' un dato condiviso fra
        tutti gli emitter, e una lista dentro un dict di classe e' scrivibile
        da chiunque la legga."""
        from_list = WindowSpec(name='x', shape=WindowShape.COSINE_SUM,
                               coefficients=[0.5, 0.5], description="d")

        assert isinstance(spec.coefficients, tuple)
        assert isinstance(from_list.coefficients, tuple)

    def test_description_is_str(self, spec):
        assert isinstance(spec.description, str)

    def test_family_is_str(self, spec):
        assert isinstance(spec.family, str)

    def test_symmetry_is_str(self, spec):
        assert isinstance(spec.symmetry, str)


# ===========================================================================
# 3. TestWindowSpecEquality
# ===========================================================================

def _spec(**overrides):
    fields = dict(name='x', shape=WindowShape.COSINE_SUM,
                  coefficients=(0.5, 0.5), description="d", family="window")
    fields.update(overrides)
    return WindowSpec(**fields)


class TestWindowSpecEquality:

    def test_equal_instances(self):
        assert _spec(name='hanning') == _spec(name='hanning')

    def test_different_name_not_equal(self):
        assert _spec(name='hanning') != _spec(name='hamming')

    def test_different_shape_not_equal(self):
        assert _spec() != _spec(shape=WindowShape.TRIANGULAR, coefficients=())

    def test_different_coefficients_not_equal(self):
        assert _spec() != _spec(coefficients=(0.54, 0.46))

    def test_different_params_not_equal(self):
        gaussian = dict(shape=WindowShape.GAUSSIAN, coefficients=())
        assert _spec(params={'sigma': 0.4}, **gaussian) != \
            _spec(params={'sigma': 0.9}, **gaussian)

    def test_different_symmetry_not_equal(self):
        assert _spec() != _spec(symmetry=ASYMMETRIC)

    def test_different_family_not_equal(self):
        assert _spec() != _spec(family='asymmetric')


# ===========================================================================
# 4. TestWindowSpecImmutability
# ===========================================================================

class TestWindowSpecImmutability:
    """La spec e' la descrizione da cui *ogni* target deriva la sua finestra,
    e vive in un dict di classe: se fosse scrivibile, un emitter potrebbe
    riscriverla sotto gli altri. Prima della #202 era una dataclass normale
    con dentro una lista."""

    def test_fields_are_not_assignable(self):
        import dataclasses

        spec = _spec()
        with pytest.raises(dataclasses.FrozenInstanceError):
            spec.name = 'y'

    def test_coefficients_cannot_be_appended_to(self):
        spec = _spec()
        with pytest.raises(AttributeError):
            spec.coefficients.append(0.1)

    def test_params_are_read_only(self):
        spec = _spec(shape=WindowShape.GAUSSIAN, coefficients=(),
                     params={'sigma': 0.4})
        with pytest.raises(TypeError):
            spec.params['sigma'] = 0.9

    def test_params_do_not_alias_the_dict_they_came_from(self):
        source = {'sigma': 0.4}
        spec = _spec(shape=WindowShape.GAUSSIAN, coefficients=(),
                     params=source)

        source['sigma'] = 0.9

        assert spec.param('sigma') == 0.4


# ===========================================================================
# 4bis. TestWindowSpecValidation
# ===========================================================================

class TestWindowSpecValidation:
    """Una forma inventata e' un errore di catalogo, non una lacuna di
    target: va rifiutata alla costruzione, altrimenti diventerebbe una
    finestra che *nessun* emitter copre e il messaggio parlerebbe del
    target sbagliato."""

    def test_unknown_shape_is_refused(self):
        with pytest.raises(ValueError) as exc_info:
            WindowSpec(name='x', shape='tapered_cosine', description="d")

        assert 'tapered_cosine' in str(exc_info.value)

    def test_unknown_symmetry_is_refused(self):
        with pytest.raises(ValueError):
            WindowSpec(name='x', shape=WindowShape.RECTANGULAR,
                       description="d", symmetry='periodic')

    @pytest.mark.parametrize("shape", sorted(WindowShape.REQUIRED_PARAMS))
    def test_a_shape_without_its_params_is_refused(self, shape):
        """Il catalogo non puo' contenere una descrizione che nessun target
        sa leggere.

        Il prezzo di lasciarla passare lo pagava chi rendeva: NumPy valuta la
        formula con un `None` dentro (`TypeError`, non l'`InvalidWindowError`
        che il contratto promette) e Csound scrive quel `None` in un p-field,
        producendo `f 7 0 1024 20 7 1 None` -- una riga che muore a meta'
        render. E' il modo di fallire che la #202 esiste per togliere di
        mezzo, un livello piu' in basso: non un nome che un target non copre,
        ma una descrizione che non descrive.
        """
        with pytest.raises(ValueError) as exc_info:
            WindowSpec(name='incompleta', shape=shape, description="d",
                       symmetry=ASYMMETRIC)

        for key in WindowShape.REQUIRED_PARAMS[shape]:
            assert key in str(exc_info.value)

    @pytest.mark.parametrize("shape", sorted(WindowShape.REQUIRES_COEFFICIENTS))
    def test_a_shape_without_its_coefficients_is_refused(self, shape):
        """Una somma di coseni vuota vale zero ovunque: il grano esce come
        silenzio digitale, e senza nemmeno un errore -- il caso degenere
        della #225 per una strada che nessuna soglia sorveglia."""
        with pytest.raises(ValueError) as exc_info:
            WindowSpec(name='vuota', shape=shape, description="d")

        assert 'coefficients' in str(exc_info.value)

    def test_a_partial_declaration_names_only_what_is_missing(self):
        """Il messaggio serve a sapere cosa scrivere, quindi nomina i campi
        che mancano e non quelli gia' dichiarati."""
        with pytest.raises(ValueError) as exc_info:
            WindowSpec(name='mezza_curva',
                       shape=WindowShape.EXPONENTIAL_SEGMENT,
                       params={'start': 0.0, 'curve': 4.0},
                       description="d", family="asymmetric",
                       symmetry=ASYMMETRIC)

        message = str(exc_info.value)
        assert 'end' in message
        assert 'start' not in message
        assert 'curve' not in message

    def test_a_declared_none_counts_as_missing(self):
        """`params={'sigma': None}` e' la chiave scritta e il valore no: per
        `param()` -- e quindi per la formula -- e' identica all'assenza."""
        with pytest.raises(ValueError):
            WindowSpec(name='x', shape=WindowShape.GAUSSIAN,
                       params={'sigma': None}, description="d")

    @pytest.mark.parametrize(
        "shape",
        sorted(WindowShape.ALL - set(WindowShape.REQUIRED_PARAMS)
               - WindowShape.REQUIRES_COEFFICIENTS))
    def test_a_shape_that_needs_nothing_is_built_bare(self, shape):
        """L'altra meta': la guardia rifiuta le descrizioni incomplete, non
        quelle spoglie. Senza questo, `REQUIRED_PARAMS` potrebbe crescere
        fino a chiedere qualcosa a tutti e il test sopra resterebbe verde."""
        spec = WindowSpec(name='nuda', shape=shape, description="d")

        assert missing_shape_fields(spec) == ()


# ===========================================================================
# 5. TestWindowRegistryGet
# ===========================================================================

class TestWindowRegistryGet:

    def test_get_existing_window_returns_spec(self):
        spec = WindowRegistry.get('hanning')
        assert spec is not None
        assert isinstance(spec, WindowSpec)

    def test_get_returns_correct_name(self):
        spec = WindowRegistry.get('hamming')
        assert spec.name == 'hamming'

    def test_get_nonexistent_returns_none(self):
        assert WindowRegistry.get('nonexistent_window') is None

    def test_get_empty_string_returns_none(self):
        assert WindowRegistry.get('') is None

    def test_get_alias_resolves_correctly(self):
        # 'triangle' -> 'bartlett'
        spec = WindowRegistry.get('triangle')
        assert spec is not None
        assert spec.name == 'bartlett'

    def test_get_alias_returns_same_spec_as_target(self):
        via_alias = WindowRegistry.get('triangle')
        direct = WindowRegistry.get('bartlett')
        assert via_alias == direct

    def test_get_all_16_windows(self):
        for name in ALL_WINDOW_NAMES:
            spec = WindowRegistry.get(name)
            assert spec is not None, f"get('{name}') ha restituito None"

    def test_get_returns_windowspec_instance(self):
        for name in ALL_WINDOW_NAMES:
            spec = WindowRegistry.get(name)
            assert isinstance(spec, WindowSpec)


# ===========================================================================
# 6. TestWindowRegistryGetCaseSensitivity
# ===========================================================================

class TestWindowRegistryGetCaseSensitivity:

    def test_uppercase_name_returns_none(self):
        assert WindowRegistry.get('HANNING') is None

    def test_capitalized_name_returns_none(self):
        assert WindowRegistry.get('Hanning') is None

    def test_mixed_case_returns_none(self):
        assert WindowRegistry.get('HaNnInG') is None

    def test_uppercase_alias_returns_none(self):
        assert WindowRegistry.get('TRIANGLE') is None


# ===========================================================================
# 7. TestWindowRegistryAllNames
# ===========================================================================

class TestWindowRegistryAllNames:

    def test_all_names_returns_list(self):
        assert isinstance(WindowRegistry.all_names(), list)

    def test_all_names_contains_all_16_windows(self):
        names = set(WindowRegistry.all_names())
        assert ALL_WINDOW_NAMES.issubset(names)

    def test_all_names_contains_aliases(self):
        names = set(WindowRegistry.all_names())
        for alias in KNOWN_ALIASES:
            assert alias in names, f"Alias '{alias}' mancante da all_names()"

    def test_all_names_total_count(self):
        # 16 window + 1 alias = 17
        assert len(WindowRegistry.all_names()) == 17

    def test_all_names_elements_are_strings(self):
        for name in WindowRegistry.all_names():
            assert isinstance(name, str)

    def test_all_names_no_duplicates(self):
        names = WindowRegistry.all_names()
        assert len(names) == len(set(names))

    def test_all_names_no_empty_strings(self):
        for name in WindowRegistry.all_names():
            assert len(name) > 0


# ===========================================================================
# 8. TestWindowRegistryGetByFamily
# ===========================================================================

class TestWindowRegistryGetByFamily:

    def test_get_by_family_returns_list(self):
        result = WindowRegistry.get_by_family('window')
        assert isinstance(result, list)

    def test_get_by_family_window_count(self):
        result = WindowRegistry.get_by_family('window')
        assert len(result) == 9

    def test_get_by_family_asymmetric_count(self):
        result = WindowRegistry.get_by_family('asymmetric')
        assert len(result) == 6

    def test_get_by_family_custom_count(self):
        result = WindowRegistry.get_by_family('custom')
        assert len(result) == 1

    def test_get_by_family_unknown_returns_empty(self):
        result = WindowRegistry.get_by_family('nonexistent')
        assert result == []

    def test_get_by_family_window_names(self):
        result = {spec.name for spec in WindowRegistry.get_by_family('window')}
        assert result == FAMILY_WINDOW

    def test_get_by_family_asymmetric_names(self):
        result = {spec.name for spec in WindowRegistry.get_by_family('asymmetric')}
        assert result == FAMILY_ASYMMETRIC

    def test_get_by_family_custom_names(self):
        result = {spec.name for spec in WindowRegistry.get_by_family('custom')}
        assert result == FAMILY_CUSTOM

    def test_get_by_family_all_elements_are_windowspec(self):
        for family in VALID_FAMILIES:
            for spec in WindowRegistry.get_by_family(family):
                assert isinstance(spec, WindowSpec)

    def test_get_by_family_all_have_correct_family_tag(self):
        for family in VALID_FAMILIES:
            for spec in WindowRegistry.get_by_family(family):
                assert spec.family == family


# ===========================================================================
# 9. TestWindowRegistryDataIntegrity
# ===========================================================================

class TestWindowRegistryDataIntegrity:

    def test_windows_dict_is_not_empty(self):
        assert len(WindowRegistry.WINDOWS) > 0

    def test_windows_dict_has_16_entries(self):
        assert len(WindowRegistry.WINDOWS) == 16

    def test_aliases_dict_has_one_entry(self):
        assert len(WindowRegistry.ALIASES) == 1

    def test_all_keys_are_strings(self):
        for key in WindowRegistry.WINDOWS:
            assert isinstance(key, str)

    def test_all_keys_are_lowercase(self):
        for key in WindowRegistry.WINDOWS:
            assert key == key.lower(), f"Chiave non lowercase: '{key}'"

    def test_no_empty_key(self):
        for key in WindowRegistry.WINDOWS:
            assert len(key) > 0

    def test_all_values_are_windowspec(self):
        for name, spec in WindowRegistry.WINDOWS.items():
            assert isinstance(spec, WindowSpec), f"'{name}' non e' WindowSpec"

    def test_spec_name_matches_dict_key(self):
        for key, spec in WindowRegistry.WINDOWS.items():
            assert spec.name == key, f"Chiave '{key}' ha spec.name='{spec.name}'"

    def test_all_shapes_are_valid(self):
        for name, spec in WindowRegistry.WINDOWS.items():
            assert spec.shape in WindowShape.ALL, \
                f"'{name}' ha shape={spec.shape}"

    def test_every_shape_declares_what_it_needs(self):
        """Una forma senza i suoi parametri e' una descrizione incompleta:
        l'emitter la materializzerebbe con un `None` dentro la formula.

        La domanda la pone `missing_shape_fields`, non un elenco trascritto
        qui: l'elenco viveva in questo test, e una forma parametrica nuova --
        il solo momento in cui la guardia serve -- non ci sarebbe finita
        dentro. Ora la risposta viene dalla stessa dichiarazione che gli
        emitter leggono.
        """
        for name, spec in WindowRegistry.WINDOWS.items():
            assert missing_shape_fields(spec) == (), \
                f"'{name}' non dichiara {missing_shape_fields(spec)}"

    def test_the_requirements_are_declared_beside_the_shapes(self):
        """`REQUIRED_PARAMS` parla solo di forme che esistono.

        Una voce per una forma cancellata resterebbe a chiedere un parametro
        che nessuno legge, ed e' il modo in cui una dichiarazione smette di
        descrivere il codice restando verde.
        """
        assert set(WindowShape.REQUIRED_PARAMS) <= WindowShape.ALL
        assert WindowShape.REQUIRES_COEFFICIENTS <= WindowShape.ALL

    def test_every_required_field_is_actually_read(self):
        """La misura della dichiarazione, dal lato opposto: un parametro
        dichiarato obbligatorio dev'essere un parametro che la forma *legge*.

        Si verifica togliendolo: se la materializzazione non cambia, quel
        parametro era obbligatorio per abitudine e la dichiarazione dice una
        cosa che il codice non fa.
        """
        emitter = NumpyWindowEmitter()

        for shape, keys in WindowShape.REQUIRED_PARAMS.items():
            specs = WindowRegistry.get_by_shape(shape)
            assert specs, f"nessuna finestra di forma '{shape}' nel catalogo"
            spec = specs[0]
            reference = emitter.materialize(spec, 32)

            for key in keys:
                moved = dict(spec.params)
                moved[key] = moved[key] + 0.5
                nudged = replace(spec, params=moved)

                assert not np.array_equal(emitter.materialize(nudged, 32),
                                          reference), \
                    f"'{shape}' dichiara '{key}' ma la forma non lo legge"

    def test_only_cosine_sums_carry_coefficients(self):
        """I coefficienti sono di una forma sola: trovarli altrove vuol dire
        che qualcuno li sta leggendo per una forma che non li usa."""
        for name, spec in WindowRegistry.WINDOWS.items():
            if spec.shape != WindowShape.COSINE_SUM:
                assert spec.coefficients == (), name

    def test_all_families_are_valid(self):
        for name, spec in WindowRegistry.WINDOWS.items():
            assert spec.family in VALID_FAMILIES, \
                f"'{name}' ha family='{spec.family}'"

    def test_all_descriptions_non_empty(self):
        for name, spec in WindowRegistry.WINDOWS.items():
            assert spec.description, f"'{name}' ha description vuota"

    def test_no_duplicate_keys(self):
        keys = list(WindowRegistry.WINDOWS.keys())
        assert len(keys) == len(set(keys))

    def test_aliases_targets_exist_in_windows(self):
        for alias, target in WindowRegistry.ALIASES.items():
            assert target in WindowRegistry.WINDOWS, \
                f"Alias '{alias}' punta a '{target}' che non esiste in WINDOWS"

    def test_aliases_not_overlap_with_windows(self):
        for alias in WindowRegistry.ALIASES:
            assert alias not in WindowRegistry.WINDOWS, \
                f"'{alias}' e' sia ALIAS che chiave in WINDOWS"

    def test_triangle_alias_target(self):
        assert WindowRegistry.ALIASES.get('triangle') == 'bartlett'

    def test_cosine_sum_count(self):
        """Quattro finestre, una forma: e' il guadagno della #202 in numeri.

        hamming, hanning, blackman e blackman-harris erano quattro casi in
        ciascuno dei due back-end; adesso sono quattro terne di coefficienti
        e un ramo solo.
        """
        assert len(WindowRegistry.get_by_shape(WindowShape.COSINE_SUM)) == 4

    def test_exponential_segment_count(self):
        assert len(
            WindowRegistry.get_by_shape(WindowShape.EXPONENTIAL_SEGMENT)) == 6

    def test_every_declared_shape_is_used(self):
        """Il vocabolario delle forme non e' un elenco di intenzioni: una
        forma che nessuna finestra usa e' un ramo di emitter che nessun test
        esercita."""
        used = {spec.shape for spec in WindowRegistry.WINDOWS.values()}
        assert used == set(WindowShape.ALL)

    def test_asymmetric_family_declares_asymmetry(self):
        """Le due letture della stessa finestra devono concordare: `family`
        e' il raggruppamento di catalogo, `symmetry` la proprieta' che si
        rilegge sull'array."""
        for spec in WindowRegistry.WINDOWS.values():
            if spec.family == 'asymmetric':
                assert spec.symmetry == ASYMMETRIC, spec.name
            else:
                assert spec.symmetry == SYMMETRIC, spec.name

    def test_windows_dict_not_modified_by_copy(self):
        original_count = len(WindowRegistry.WINDOWS)
        local = WindowRegistry.WINDOWS.copy()
        local['injected'] = WindowSpec(
            name='injected', shape=WindowShape.RECTANGULAR, description="Fake")
        assert len(WindowRegistry.WINDOWS) == original_count

    def test_get_injected_key_returns_none(self):
        assert WindowRegistry.get('injected') is None


# ===========================================================================
# 10. TestWindowRegistryParametrized - ogni window individualmente
# ===========================================================================

class TestWindowRegistryParametrized:

    @pytest.mark.parametrize("name", sorted(EXPECTED_SHAPES))
    def test_shape_correct(self, name):
        expected_shape, _, _, _ = EXPECTED_SHAPES[name]
        spec = WindowRegistry.get(name)

        assert spec is not None
        assert spec.shape == expected_shape, \
            f"'{name}': shape attesa={expected_shape}, trovata={spec.shape}"

    @pytest.mark.parametrize("name", sorted(EXPECTED_SHAPES))
    def test_coefficients_correct(self, name):
        _, expected_coefficients, _, _ = EXPECTED_SHAPES[name]
        spec = WindowRegistry.get(name)

        assert spec.coefficients == expected_coefficients, \
            f"'{name}': coefficienti attesi={expected_coefficients}, " \
            f"trovati={spec.coefficients}"

    @pytest.mark.parametrize("name", sorted(EXPECTED_SHAPES))
    def test_params_correct(self, name):
        _, _, expected_params, _ = EXPECTED_SHAPES[name]
        spec = WindowRegistry.get(name)

        assert dict(spec.params) == expected_params, \
            f"'{name}': parametri attesi={expected_params}, trovati={dict(spec.params)}"

    @pytest.mark.parametrize("name", sorted(EXPECTED_SHAPES))
    def test_symmetry_correct(self, name):
        _, _, _, expected_symmetry = EXPECTED_SHAPES[name]
        spec = WindowRegistry.get(name)

        assert spec.symmetry == expected_symmetry, name

    def test_the_expected_table_covers_the_catalogue(self):
        assert set(EXPECTED_SHAPES) == set(WindowRegistry.WINDOWS)

    @pytest.mark.parametrize("name", sorted(FAMILY_WINDOW))
    def test_family_window_tag(self, name):
        spec = WindowRegistry.get(name)
        assert spec.family == 'window'

    @pytest.mark.parametrize("name", sorted(FAMILY_ASYMMETRIC))
    def test_family_asymmetric_tag(self, name):
        spec = WindowRegistry.get(name)
        assert spec.family == 'asymmetric'

    @pytest.mark.parametrize("name", sorted(FAMILY_CUSTOM))
    def test_family_custom_tag(self, name):
        spec = WindowRegistry.get(name)
        assert spec.family == 'custom'

# ===========================================================================
# 11. TestWindowRegistryIntegration
# ===========================================================================

class TestWindowRegistryIntegration:

    def test_all_names_all_resolvable(self):
        for name in WindowRegistry.all_names():
            spec = WindowRegistry.get(name)
            assert spec is not None, f"all_names() contiene '{name}' ma get() restituisce None"

    def test_families_cover_all_windows(self):
        all_via_family = set()
        for family in VALID_FAMILIES:
            for spec in WindowRegistry.get_by_family(family):
                all_via_family.add(spec.name)
        assert all_via_family == ALL_WINDOW_NAMES
