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
"""

import pytest
from pge.controllers.window_registry import WindowSpec, WindowRegistry


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

VALID_GEN_ROUTINES = {9, 16, 20}
VALID_FAMILIES = {'window', 'asymmetric', 'custom'}

# (gen_routine, gen_params) per ogni window - ground truth
EXPECTED_SPECS = {
    'hamming':         (20, [1, 1]),
    'hanning':         (20, [2, 1]),
    'bartlett':        (20, [3, 1]),
    'blackman':        (20, [4, 1]),
    'blackman_harris': (20, [5, 1]),
    'gaussian':        (20, [6, 1, 3]),
    'kaiser':          (20, [7, 1, 6]),
    'rectangle':       (20, [8, 1]),
    'sinc':            (20, [9, 1, 1]),
    'half_sine':       (9,  [0.5, 1, 0]),
    'expodec':         (16, [1, 1024, 4, 0]),
    'expodec_strong':  (16, [1, 1024, 10, 0]),
    'exporise':        (16, [0, 1024, -4, 1]),
    'exporise_strong': (16, [0, 1024, -10, 1]),
    'rexpodec':        (16, [1, 1024, -4, 0]),
    'rexporise':       (16, [0, 1024, 4, 1]),
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
            gen_routine=20,
            gen_params=[1, 1],
            description="Test window",
            family="window",
        )
        assert spec.name == 'test_window'
        assert spec.gen_routine == 20
        assert spec.gen_params == [1, 1]
        assert spec.description == "Test window"
        assert spec.family == "window"

    def test_family_default_is_window(self):
        spec = WindowSpec(
            name='x',
            gen_routine=20,
            gen_params=[1],
            description="desc",
        )
        assert spec.family == "window"

    def test_gen_params_accepts_floats(self):
        spec = WindowSpec(
            name='half_sine',
            gen_routine=9,
            gen_params=[0.5, 1, 0],
            description="Half sine",
        )
        assert spec.gen_params[0] == 0.5

    def test_gen_params_accepts_negative_values(self):
        spec = WindowSpec(
            name='exporise',
            gen_routine=16,
            gen_params=[0, 1024, -4, 1],
            description="Exporise",
            family="asymmetric",
        )
        assert -4 in spec.gen_params

    def test_gen_params_list_is_stored_by_reference(self):
        params = [1, 2, 3]
        spec = WindowSpec(name='x', gen_routine=20, gen_params=params, description="d")
        assert spec.gen_params is params


# ===========================================================================
# 2. TestWindowSpecFieldTypes
# ===========================================================================

class TestWindowSpecFieldTypes:

    def test_name_is_str(self):
        spec = WindowSpec(name='hanning', gen_routine=20, gen_params=[2, 1], description="d")
        assert isinstance(spec.name, str)

    def test_gen_routine_is_int(self):
        spec = WindowSpec(name='hanning', gen_routine=20, gen_params=[2, 1], description="d")
        assert isinstance(spec.gen_routine, int)

    def test_gen_params_is_list(self):
        spec = WindowSpec(name='hanning', gen_routine=20, gen_params=[2, 1], description="d")
        assert isinstance(spec.gen_params, list)

    def test_description_is_str(self):
        spec = WindowSpec(name='hanning', gen_routine=20, gen_params=[2, 1], description="desc")
        assert isinstance(spec.description, str)

    def test_family_is_str(self):
        spec = WindowSpec(name='hanning', gen_routine=20, gen_params=[2, 1], description="d")
        assert isinstance(spec.family, str)


# ===========================================================================
# 3. TestWindowSpecEquality
# ===========================================================================

class TestWindowSpecEquality:

    def test_equal_instances(self):
        a = WindowSpec('hanning', 20, [2, 1], "desc", "window")
        b = WindowSpec('hanning', 20, [2, 1], "desc", "window")
        assert a == b

    def test_different_name_not_equal(self):
        a = WindowSpec('hanning', 20, [2, 1], "desc", "window")
        b = WindowSpec('hamming', 20, [2, 1], "desc", "window")
        assert a != b

    def test_different_gen_routine_not_equal(self):
        a = WindowSpec('x', 20, [1, 1], "d", "window")
        b = WindowSpec('x', 16, [1, 1], "d", "window")
        assert a != b

    def test_different_gen_params_not_equal(self):
        a = WindowSpec('x', 20, [1, 1], "d", "window")
        b = WindowSpec('x', 20, [2, 1], "d", "window")
        assert a != b

    def test_different_family_not_equal(self):
        a = WindowSpec('x', 20, [1, 1], "d", "window")
        b = WindowSpec('x', 20, [1, 1], "d", "asymmetric")
        assert a != b


# ===========================================================================
# 4. TestWindowSpecImmutability
# ===========================================================================

class TestWindowSpecImmutability:

    def test_fields_are_assignable(self):
        # dataclass senza frozen=True: i campi sono modificabili
        spec = WindowSpec('x', 20, [1], "d")
        spec.name = 'y'
        assert spec.name == 'y'

    def test_gen_params_list_is_mutable(self):
        spec = WindowSpec('x', 20, [1, 2], "d")
        spec.gen_params.append(3)
        assert len(spec.gen_params) == 3


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

    def test_all_gen_routines_are_valid(self):
        for name, spec in WindowRegistry.WINDOWS.items():
            assert spec.gen_routine in VALID_GEN_ROUTINES, \
                f"'{name}' ha gen_routine={spec.gen_routine}"

    def test_all_gen_params_non_empty(self):
        for name, spec in WindowRegistry.WINDOWS.items():
            assert len(spec.gen_params) > 0, f"'{name}' ha gen_params vuoto"

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

    def test_gen20_count(self):
        count = sum(1 for s in WindowRegistry.WINDOWS.values() if s.gen_routine == 20)
        assert count == 9

    def test_gen16_count(self):
        count = sum(1 for s in WindowRegistry.WINDOWS.values() if s.gen_routine == 16)
        assert count == 6

    def test_gen09_count(self):
        count = sum(1 for s in WindowRegistry.WINDOWS.values() if s.gen_routine == 9)
        assert count == 1

    def test_gen16_specs_have_four_params(self):
        for name, spec in WindowRegistry.WINDOWS.items():
            if spec.gen_routine == 16:
                assert len(spec.gen_params) == 4, \
                    f"'{name}' GEN16 ha {len(spec.gen_params)} parametri"

    def test_gen20_specs_have_at_least_two_params(self):
        for name, spec in WindowRegistry.WINDOWS.items():
            if spec.gen_routine == 20:
                assert len(spec.gen_params) >= 2, \
                    f"'{name}' GEN20 ha solo {len(spec.gen_params)} parametro/i"

    def test_windows_dict_not_modified_by_copy(self):
        original_count = len(WindowRegistry.WINDOWS)
        local = WindowRegistry.WINDOWS.copy()
        local['injected'] = WindowSpec('injected', 20, [1, 1], "Fake")
        assert len(WindowRegistry.WINDOWS) == original_count

    def test_get_injected_key_returns_none(self):
        assert WindowRegistry.get('injected') is None


# ===========================================================================
# 10. TestWindowRegistryParametrized - ogni window individualmente
# ===========================================================================

class TestWindowRegistryParametrized:

    @pytest.mark.parametrize("name,expected_gen,expected_params", [
        (name, gen, params)
        for name, (gen, params) in EXPECTED_SPECS.items()
    ])
    def test_gen_routine_correct(self, name, expected_gen, expected_params):
        spec = WindowRegistry.get(name)
        assert spec is not None
        assert spec.gen_routine == expected_gen, \
            f"'{name}': gen_routine atteso={expected_gen}, trovato={spec.gen_routine}"

    @pytest.mark.parametrize("name,expected_gen,expected_params", [
        (name, gen, params)
        for name, (gen, params) in EXPECTED_SPECS.items()
    ])
    def test_gen_params_correct(self, name, expected_gen, expected_params):
        spec = WindowRegistry.get(name)
        assert spec.gen_params == expected_params, \
            f"'{name}': gen_params attesi={expected_params}, trovati={spec.gen_params}"

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
