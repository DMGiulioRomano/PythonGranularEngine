# tests/test_parameter_schema.py
"""
Test suite completa per parameter_schema.py

Modulo sotto test:
- ParameterSpec (dataclass frozen)
- 5 schema costanti (STREAM, POINTER, PITCH, DENSITY)
- ALL_SCHEMAS registry
- _SCHEMA_BY_NAME flat index
- Helper functions: get_schema, get_all_schema_names,
  get_parameter_spec_from_schema, get_parameter_spec, get_all_parameter_names

Organizzazione:
1. ParameterSpec - costruzione, immutabilita', defaults, repr
2. STREAM_PARAMETER_SCHEMA - contenuto e invarianti
3. POINTER_PARAMETER_SCHEMA - contenuto e gruppi esclusivi
4. PITCH_PARAMETER_SCHEMA - contenuto e gruppi esclusivi
5. DENSITY_PARAMETER_SCHEMA - contenuto e gruppi esclusivi
7. ALL_SCHEMAS registry - completezza e consistenza
8. _SCHEMA_BY_NAME flat index - unicita' e coerenza
9. get_schema() - successo e errore
10. get_all_schema_names() - completezza
11. get_parameter_spec_from_schema() - successo e errori
12. get_parameter_spec() - successo e errore
13. get_all_parameter_names() - coerenza con STREAM schema
14. Cross-schema invarianti - nomi unici, gruppi esclusivi, coerenza
"""

import pytest
from dataclasses import fields, FrozenInstanceError

from parameters.parameter_schema import (
    ParameterSpec,
    STREAM_PARAMETER_SCHEMA,
    POINTER_PARAMETER_SCHEMA,
    PITCH_PARAMETER_SCHEMA,
    DENSITY_PARAMETER_SCHEMA,
    ALL_SCHEMAS,
    get_schema,
    get_all_schema_names,
    get_parameter_spec_from_schema,
    get_parameter_spec,
    get_all_parameter_names,
    _SCHEMA_BY_NAME,
)


# =============================================================================
# 1. PARAMETERSPEC DATACLASS
# =============================================================================

class TestParameterSpecConstruction:
    """Costruzione e proprieta' del dataclass ParameterSpec."""

    def test_minimal_construction(self):
        """Costruzione con soli campi obbligatori."""
        spec = ParameterSpec(name='test', yaml_path='test.path', default=0.0)

        assert spec.name == 'test'
        assert spec.yaml_path == 'test.path'
        assert spec.default == 0.0

    def test_default_optional_fields(self):
        """I campi opzionali hanno i default corretti."""
        spec = ParameterSpec(name='x', yaml_path='x', default=1)

        assert spec.range_path is None
        assert spec.dephase_key is None
        assert spec.is_smart is True
        assert spec.exclusive_group is None
        assert spec.group_priority == 99

    def test_full_construction(self):
        """Costruzione con tutti i campi espliciti."""
        spec = ParameterSpec(
            name='volume',
            yaml_path='volume',
            default=-6.0,
            range_path='volume_range',
            dephase_key='volume',
            is_smart=True,
            exclusive_group='output_mode',
            group_priority=1,
        )

        assert spec.name == 'volume'
        assert spec.yaml_path == 'volume'
        assert spec.default == -6.0
        assert spec.range_path == 'volume_range'
        assert spec.dephase_key == 'volume'
        assert spec.is_smart is True
        assert spec.exclusive_group == 'output_mode'
        assert spec.group_priority == 1

    def test_is_smart_false(self):
        """Parametro raw (non-smart)."""
        spec = ParameterSpec(name='env', yaml_path='grain.envelope',
                             default='hanning', is_smart=False)

        assert spec.is_smart is False

    def test_default_none(self):
        """default puo' essere None."""
        spec = ParameterSpec(name='opt', yaml_path='opt', default=None)

        assert spec.default is None

    def test_default_various_types(self):
        """default accetta vari tipi: int, float, str, None, list."""
        for val in [0, 1.5, 'hanning', None, [1, 2]]:
            spec = ParameterSpec(name='t', yaml_path='t', default=val)
            assert spec.default == val


class TestParameterSpecFrozen:
    """Immutabilita' del dataclass frozen."""

    def test_cannot_modify_name(self):
        """Tentare di modificare name solleva FrozenInstanceError."""
        spec = ParameterSpec(name='vol', yaml_path='vol', default=0)
        with pytest.raises(FrozenInstanceError):
            spec.name = 'pan'

    def test_cannot_modify_yaml_path(self):
        spec = ParameterSpec(name='vol', yaml_path='vol', default=0)
        with pytest.raises(FrozenInstanceError):
            spec.yaml_path = 'new.path'

    def test_cannot_modify_default(self):
        spec = ParameterSpec(name='vol', yaml_path='vol', default=0)
        with pytest.raises(FrozenInstanceError):
            spec.default = 99

    def test_cannot_modify_is_smart(self):
        spec = ParameterSpec(name='vol', yaml_path='vol', default=0)
        with pytest.raises(FrozenInstanceError):
            spec.is_smart = False

    def test_cannot_modify_exclusive_group(self):
        spec = ParameterSpec(name='vol', yaml_path='vol', default=0)
        with pytest.raises(FrozenInstanceError):
            spec.exclusive_group = 'grp'

    def test_cannot_add_new_attribute(self):
        """Non si possono aggiungere attributi extra."""
        spec = ParameterSpec(name='vol', yaml_path='vol', default=0)
        with pytest.raises(FrozenInstanceError):
            spec.extra = 'nope'


class TestParameterSpecEquality:
    """Equality e hashing (dataclass frozen e' hashable)."""

    def test_equal_specs(self):
        """Due ParameterSpec identici sono uguali."""
        a = ParameterSpec(name='vol', yaml_path='vol', default=-6.0)
        b = ParameterSpec(name='vol', yaml_path='vol', default=-6.0)
        assert a == b

    def test_different_specs(self):
        """ParameterSpec con campi diversi non sono uguali."""
        a = ParameterSpec(name='vol', yaml_path='vol', default=-6.0)
        b = ParameterSpec(name='pan', yaml_path='pan', default=0.0)
        assert a != b

    def test_hashable(self):
        """ParameterSpec frozen e' hashable (usabile in set/dict)."""
        spec = ParameterSpec(name='vol', yaml_path='vol', default=0)
        s = {spec}
        assert spec in s

    def test_hash_consistency(self):
        """Due spec uguali hanno lo stesso hash."""
        a = ParameterSpec(name='vol', yaml_path='vol', default=-6.0)
        b = ParameterSpec(name='vol', yaml_path='vol', default=-6.0)
        assert hash(a) == hash(b)


class TestParameterSpecFieldDefinition:
    """Verifica che la struttura del dataclass sia corretta."""

    def test_field_count(self):
        """ParameterSpec ha esattamente 8 campi."""
        assert len(fields(ParameterSpec)) == 8

    def test_field_names(self):
        """I nomi dei campi sono quelli attesi."""
        expected = {
            'name', 'yaml_path', 'default', 'range_path',
            'dephase_key', 'is_smart', 'exclusive_group', 'group_priority'
        }
        actual = {f.name for f in fields(ParameterSpec)}
        assert actual == expected

    def test_repr_contains_name(self):
        """__repr__ include il nome del parametro."""
        spec = ParameterSpec(name='volume', yaml_path='vol', default=0)
        r = repr(spec)
        assert 'volume' in r
        assert 'ParameterSpec' in r


# =============================================================================
# 2. STREAM_PARAMETER_SCHEMA
# =============================================================================

class TestStreamParameterSchema:
    """Contenuto e invarianti di STREAM_PARAMETER_SCHEMA."""

    def test_is_list(self):
        assert isinstance(STREAM_PARAMETER_SCHEMA, list)

    def test_not_empty(self):
        assert len(STREAM_PARAMETER_SCHEMA) > 0

    def test_all_elements_are_parameter_spec(self):
        for spec in STREAM_PARAMETER_SCHEMA:
            assert isinstance(spec, ParameterSpec)

    def test_expected_parameters_present(self):
        """I parametri core di Stream sono presenti."""
        names = {s.name for s in STREAM_PARAMETER_SCHEMA}
        expected_core = {'volume', 'pan', 'grain_duration', 'grain_envelope', 'reverse'}
        assert expected_core.issubset(names), (
            f"Mancanti: {expected_core - names}"
        )

    def test_volume_spec(self):
        """volume ha la configurazione corretta."""
        spec = next(s for s in STREAM_PARAMETER_SCHEMA if s.name == 'volume')
        assert spec.yaml_path == 'volume'
        assert spec.default == -6.0
        assert spec.range_path == 'volume_range'
        assert spec.dephase_key == 'volume'
        assert spec.is_smart is True

    def test_pan_spec(self):
        spec = next(s for s in STREAM_PARAMETER_SCHEMA if s.name == 'pan')
        assert spec.yaml_path == 'pan'
        assert spec.default == 0.0
        assert spec.range_path == 'pan_range'
        assert spec.dephase_key == 'pan'
        assert spec.is_smart is True

    def test_grain_duration_spec(self):
        spec = next(s for s in STREAM_PARAMETER_SCHEMA if s.name == 'grain_duration')
        assert spec.yaml_path == 'grain.duration'
        assert spec.default == 0.05
        assert spec.range_path == 'grain.duration_range'
        assert spec.dephase_key == 'duration'
        assert spec.is_smart is True

    def test_grain_envelope_is_raw(self):
        """grain_envelope e' is_smart=False (stringa, non Parameter)."""
        spec = next(s for s in STREAM_PARAMETER_SCHEMA if s.name == 'grain_envelope')
        assert spec.yaml_path == 'grain.envelope'
        assert spec.default == 'hanning'
        assert spec.is_smart is False

    def test_reverse_spec(self):
        spec = next(s for s in STREAM_PARAMETER_SCHEMA if s.name == 'reverse')
        assert spec.yaml_path == 'grain.reverse'
        assert spec.default == 0
        assert spec.dephase_key == 'reverse'

    def test_no_exclusive_groups(self):
        """STREAM schema non ha gruppi esclusivi."""
        for spec in STREAM_PARAMETER_SCHEMA:
            assert spec.exclusive_group is None, (
                f"'{spec.name}' ha exclusive_group='{spec.exclusive_group}'"
            )

    def test_unique_names(self):
        """Tutti i nomi nello schema sono unici."""
        names = [s.name for s in STREAM_PARAMETER_SCHEMA]
        assert len(names) == len(set(names))

    def test_unique_yaml_paths(self):
        """Tutti i yaml_path nello schema sono unici."""
        paths = [s.yaml_path for s in STREAM_PARAMETER_SCHEMA]
        assert len(paths) == len(set(paths))


# =============================================================================
# 3. POINTER_PARAMETER_SCHEMA
# =============================================================================

class TestPointerParameterSchema:
    """Contenuto e gruppi esclusivi di POINTER_PARAMETER_SCHEMA."""

    def test_is_list_of_specs(self):
        assert isinstance(POINTER_PARAMETER_SCHEMA, list)
        for spec in POINTER_PARAMETER_SCHEMA:
            assert isinstance(spec, ParameterSpec)

    def test_expected_parameters(self):
        names = {s.name for s in POINTER_PARAMETER_SCHEMA}
        expected = {
            'pointer_start', 'pointer_speed_ratio', 'pointer_deviation',
            'loop_start', 'loop_end', 'loop_dur'
        }
        assert expected == names

    def test_pointer_start_is_raw(self):
        """pointer_start e' is_smart=False."""
        spec = next(s for s in POINTER_PARAMETER_SCHEMA if s.name == 'pointer_start')
        assert spec.is_smart is False
        assert spec.default == 0.0

    def test_pointer_deviation_has_range_and_dephase(self):
        spec = next(s for s in POINTER_PARAMETER_SCHEMA if s.name == 'pointer_deviation')
        assert spec.range_path == 'offset_range'
        assert spec.dephase_key == 'pointer'
        assert spec.default == 0.0

    def test_loop_bounds_exclusive_group(self):
        """loop_end e loop_dur appartengono a 'loop_bounds'."""
        loop_end = next(s for s in POINTER_PARAMETER_SCHEMA if s.name == 'loop_end')
        loop_dur = next(s for s in POINTER_PARAMETER_SCHEMA if s.name == 'loop_dur')

        assert loop_end.exclusive_group == 'loop_bounds'
        assert loop_dur.exclusive_group == 'loop_bounds'

    def test_loop_end_has_higher_priority(self):
        """loop_end ha priorita' piu' alta (priority=1)."""
        loop_end = next(s for s in POINTER_PARAMETER_SCHEMA if s.name == 'loop_end')
        loop_dur = next(s for s in POINTER_PARAMETER_SCHEMA if s.name == 'loop_dur')

        assert loop_end.group_priority < loop_dur.group_priority

    def test_loop_start_not_exclusive(self):
        """loop_start non appartiene a nessun gruppo esclusivo."""
        spec = next(s for s in POINTER_PARAMETER_SCHEMA if s.name == 'loop_start')
        assert spec.exclusive_group is None

    def test_loop_defaults_are_none(self):
        """I parametri loop hanno default None (opzionali)."""
        for name in ('loop_start', 'loop_end', 'loop_dur'):
            spec = next(s for s in POINTER_PARAMETER_SCHEMA if s.name == name)
            assert spec.default is None, f"{name} default dovrebbe essere None"

    def test_unique_names(self):
        names = [s.name for s in POINTER_PARAMETER_SCHEMA]
        assert len(names) == len(set(names))


# =============================================================================
# 4. PITCH_PARAMETER_SCHEMA
# =============================================================================

class TestPitchParameterSchema:
    """Il pitch base non è più schema-driven: PITCH_PARAMETER_SCHEMA è vuoto.
    L'unità (semitones/cents/quarter_tone/eighth_tone/edo/ratio) e i suoi bounds
    sono gestiti da PitchController tramite PitchUnit."""

    def test_is_list_of_specs(self):
        assert isinstance(PITCH_PARAMETER_SCHEMA, list)
        for spec in PITCH_PARAMETER_SCHEMA:
            assert isinstance(spec, ParameterSpec)

    def test_is_empty(self):
        assert PITCH_PARAMETER_SCHEMA == []

    def test_both_are_smart(self):
        for spec in PITCH_PARAMETER_SCHEMA:
            assert spec.is_smart is True


# =============================================================================
# 5. DENSITY_PARAMETER_SCHEMA
# =============================================================================

class TestDensityParameterSchema:
    """Contenuto e gruppi esclusivi di DENSITY_PARAMETER_SCHEMA."""

    def test_is_list_of_specs(self):
        assert isinstance(DENSITY_PARAMETER_SCHEMA, list)
        for spec in DENSITY_PARAMETER_SCHEMA:
            assert isinstance(spec, ParameterSpec)

    def test_expected_parameters(self):
        names = {s.name for s in DENSITY_PARAMETER_SCHEMA}
        assert names == {'fill_factor', 'density', 'distribution', 'effective_density'}

    def test_density_mode_exclusive_group(self):
        """fill_factor e density appartengono a 'density_mode'."""
        ff = next(s for s in DENSITY_PARAMETER_SCHEMA if s.name == 'fill_factor')
        dens = next(s for s in DENSITY_PARAMETER_SCHEMA if s.name == 'density')

        assert ff.exclusive_group == 'density_mode'
        assert dens.exclusive_group == 'density_mode'

    def test_fill_factor_has_higher_priority(self):
        """fill_factor ha priority=1 (prioritario su density)."""
        ff = next(s for s in DENSITY_PARAMETER_SCHEMA if s.name == 'fill_factor')
        dens = next(s for s in DENSITY_PARAMETER_SCHEMA if s.name == 'density')
        assert ff.group_priority < dens.group_priority

    def test_fill_factor_default_not_none(self):
        """fill_factor ha default non-None (2), density ha None."""
        ff = next(s for s in DENSITY_PARAMETER_SCHEMA if s.name == 'fill_factor')
        dens = next(s for s in DENSITY_PARAMETER_SCHEMA if s.name == 'density')
        assert ff.default == 2
        assert dens.default is None

    def test_distribution_not_exclusive(self):
        spec = next(s for s in DENSITY_PARAMETER_SCHEMA if s.name == 'distribution')
        assert spec.exclusive_group is None
        assert spec.default == 0.0

    def test_effective_density_is_raw(self):
        """effective_density e' is_smart=False (calcolato internamente)."""
        spec = next(s for s in DENSITY_PARAMETER_SCHEMA if s.name == 'effective_density')
        assert spec.is_smart is False
        assert spec.yaml_path == '_internal_calc_'

    def test_unique_names(self):
        names = [s.name for s in DENSITY_PARAMETER_SCHEMA]
        assert len(names) == len(set(names))

# =============================================================================
# 7. ALL_SCHEMAS REGISTRY
# =============================================================================

class TestAllSchemasRegistry:
    """Completezza e consistenza del registry ALL_SCHEMAS."""

    def test_is_dict(self):
        assert isinstance(ALL_SCHEMAS, dict)

    def test_expected_keys(self):
        assert set(ALL_SCHEMAS.keys()) == {
            'stream', 'pointer', 'pitch', 'density'
        }

    def test_stream_reference(self):
        """ALL_SCHEMAS['stream'] e' lo stesso oggetto di STREAM_PARAMETER_SCHEMA."""
        assert ALL_SCHEMAS['stream'] is STREAM_PARAMETER_SCHEMA

    def test_pointer_reference(self):
        assert ALL_SCHEMAS['pointer'] is POINTER_PARAMETER_SCHEMA

    def test_pitch_reference(self):
        assert ALL_SCHEMAS['pitch'] is PITCH_PARAMETER_SCHEMA

    def test_density_reference(self):
        assert ALL_SCHEMAS['density'] is DENSITY_PARAMETER_SCHEMA

    def test_all_values_are_lists(self):
        for name, schema in ALL_SCHEMAS.items():
            assert isinstance(schema, list), f"'{name}' non e' una lista"

    def test_all_values_contain_specs(self):
        for name, schema in ALL_SCHEMAS.items():
            for spec in schema:
                assert isinstance(spec, ParameterSpec), (
                    f"'{name}' contiene un elemento non-ParameterSpec: {type(spec)}"
                )

    def test_no_empty_schemas(self):
        """Gli schema sono non vuoti, eccetto PITCH (unit-driven, gestito dal controller)."""
        for name, schema in ALL_SCHEMAS.items():
            if name == 'pitch':
                assert schema == [], "PITCH_PARAMETER_SCHEMA deve essere vuoto (unit-driven)"
                continue
            assert len(schema) > 0, f"Schema '{name}' e' vuoto"


# =============================================================================
# 8. _SCHEMA_BY_NAME FLAT INDEX
# =============================================================================

class TestSchemaByNameIndex:
    """Unicita' e coerenza del flat index _SCHEMA_BY_NAME."""

    def test_is_dict(self):
        assert isinstance(_SCHEMA_BY_NAME, dict)

    def test_contains_all_parameters_from_all_schemas(self):
        """Ogni parametro di ogni schema e' nel flat index."""
        for schema_name, schema_list in ALL_SCHEMAS.items():
            for spec in schema_list:
                assert spec.name in _SCHEMA_BY_NAME, (
                    f"'{spec.name}' da schema '{schema_name}' mancante in _SCHEMA_BY_NAME"
                )

    def test_values_are_parameter_specs(self):
        for name, spec in _SCHEMA_BY_NAME.items():
            assert isinstance(spec, ParameterSpec)

    def test_key_matches_spec_name(self):
        """La chiave nel dict corrisponde a spec.name."""
        for key, spec in _SCHEMA_BY_NAME.items():
            assert key == spec.name

    def test_total_count_matches_all_schemas(self):
        """Il conteggio corrisponde (assumendo nomi unici cross-schema)."""
        total_in_schemas = sum(len(s) for s in ALL_SCHEMAS.values())
        # Se ci fossero duplicati cross-schema, _SCHEMA_BY_NAME ne avrebbe meno
        assert len(_SCHEMA_BY_NAME) <= total_in_schemas

    def test_stream_params_in_index(self):
        """I parametri stream sono tutti accessibili dal flat index."""
        for spec in STREAM_PARAMETER_SCHEMA:
            assert spec.name in _SCHEMA_BY_NAME

    def test_controller_params_in_index(self):
        """I parametri dei controller sono nel flat index."""
        controller_names = ['pointer_start', 'fill_factor']
        for name in controller_names:
            assert name in _SCHEMA_BY_NAME


# =============================================================================
# 9. get_schema()
# =============================================================================

class TestGetSchema:
    """Test per la funzione get_schema()."""

    @pytest.mark.parametrize("schema_name,expected_schema", [
        ('stream', STREAM_PARAMETER_SCHEMA),
        ('pointer', POINTER_PARAMETER_SCHEMA),
        ('pitch', PITCH_PARAMETER_SCHEMA),
        ('density', DENSITY_PARAMETER_SCHEMA),
    ])
    def test_returns_correct_schema(self, schema_name, expected_schema):
        result = get_schema(schema_name)
        assert result is expected_schema

    def test_invalid_schema_raises_key_error(self):
        with pytest.raises(KeyError, match="non trovato"):
            get_schema('nonexistent')

    def test_error_message_lists_available(self):
        """Il messaggio di errore elenca gli schema disponibili."""
        with pytest.raises(KeyError) as exc_info:
            get_schema('invalid')
        error_msg = str(exc_info.value)
        for name in ALL_SCHEMAS.keys():
            assert name in error_msg

    @pytest.mark.parametrize("bad_name", [
        '', 'Stream', 'STREAM', 'streams', 'pitch_mode',
        'pointer_schema', None,
    ])
    def test_various_invalid_names(self, bad_name):
        """Nomi invalidi (case-sensitive, typos, None) sollevano errore."""
        with pytest.raises((KeyError, TypeError)):
            get_schema(bad_name)


# =============================================================================
# 10. get_all_schema_names()
# =============================================================================

class TestGetAllSchemaNames:
    """Test per la funzione get_all_schema_names()."""

    def test_returns_list(self):
        result = get_all_schema_names()
        assert isinstance(result, list)

    def test_contains_all_expected_names(self):
        result = get_all_schema_names()
        assert set(result) == {'stream', 'pointer', 'pitch', 'density'}

    def test_count_matches_all_schemas(self):
        assert len(get_all_schema_names()) == len(ALL_SCHEMAS)

    def test_consistent_with_all_schemas_keys(self):
        """Il risultato corrisponde esattamente a ALL_SCHEMAS.keys()."""
        assert set(get_all_schema_names()) == set(ALL_SCHEMAS.keys())


# =============================================================================
# 11. get_parameter_spec_from_schema()
# =============================================================================

class TestGetParameterSpecFromSchema:
    """Test per la funzione get_parameter_spec_from_schema()."""

    @pytest.mark.parametrize("schema_name,param_name", [
        ('stream', 'volume'),
        ('stream', 'pan'),
        ('stream', 'grain_duration'),
        ('stream', 'grain_envelope'),
        ('stream', 'reverse'),
        ('pointer', 'pointer_start'),
        ('pointer', 'pointer_speed_ratio'),
        ('pointer', 'pointer_deviation'),
        ('pointer', 'loop_end'),
        ('pointer', 'loop_dur'),
        ('density', 'fill_factor'),
        ('density', 'density'),
        ('density', 'distribution'),
        ('density', 'effective_density'),
    ])
    def test_returns_correct_spec(self, schema_name, param_name):
        """Recupera la spec corretta per ogni combinazione schema/parametro."""
        spec = get_parameter_spec_from_schema(schema_name, param_name)
        assert isinstance(spec, ParameterSpec)
        assert spec.name == param_name

    def test_invalid_schema_raises_key_error(self):
        with pytest.raises(KeyError):
            get_parameter_spec_from_schema('nonexistent', 'volume')

    def test_invalid_param_raises_key_error(self):
        with pytest.raises(KeyError, match="non trovato"):
            get_parameter_spec_from_schema('stream', 'nonexistent_param')

    def test_cross_schema_param_not_found(self):
        """Un parametro di uno schema non e' accessibile da un altro."""
        # 'volume' e' in 'stream', non in 'pitch'
        with pytest.raises(KeyError):
            get_parameter_spec_from_schema('pitch', 'volume')

    def test_returns_same_object_as_schema_list(self):
        """L'oggetto restituito e' lo stesso presente nella lista schema."""
        spec = get_parameter_spec_from_schema('stream', 'volume')
        schema_spec = next(s for s in STREAM_PARAMETER_SCHEMA if s.name == 'volume')
        assert spec is schema_spec


# =============================================================================
# 12. get_parameter_spec()
# =============================================================================

class TestGetParameterSpec:
    """Test per la funzione get_parameter_spec() (flat lookup)."""

    @pytest.mark.parametrize("param_name", [
        'volume', 'pan', 'grain_duration', 'grain_envelope', 'reverse',
        'pointer_start', 'pointer_speed_ratio', 'pointer_deviation',
        'loop_start', 'loop_end', 'loop_dur',
        'fill_factor', 'density', 'distribution', 'effective_density',
    ])
    def test_returns_spec_for_all_known_params(self, param_name):
        spec = get_parameter_spec(param_name)
        assert isinstance(spec, ParameterSpec)
        assert spec.name == param_name

    def test_invalid_name_raises_key_error(self):
        with pytest.raises(KeyError, match="non definito"):
            get_parameter_spec('nonexistent_parameter')

    def test_error_message_content(self):
        """Il messaggio menziona il nome cercato."""
        with pytest.raises(KeyError) as exc_info:
            get_parameter_spec('foo_bar')
        assert 'foo_bar' in str(exc_info.value)

    def test_consistent_with_schema_by_name(self):
        """Restituisce lo stesso oggetto di _SCHEMA_BY_NAME."""
        for name, expected_spec in _SCHEMA_BY_NAME.items():
            assert get_parameter_spec(name) is expected_spec


# =============================================================================
# 13. get_all_parameter_names()
# =============================================================================

class TestGetAllParameterNames:
    """Test per la funzione get_all_parameter_names()."""

    def test_returns_list(self):
        result = get_all_parameter_names()
        assert isinstance(result, list)

    def test_returns_only_stream_params(self):
        """Ritorna i nomi SOLO di STREAM_PARAMETER_SCHEMA."""
        result = get_all_parameter_names()
        stream_names = [s.name for s in STREAM_PARAMETER_SCHEMA]
        assert result == stream_names

    def test_preserves_order(self):
        """L'ordine corrisponde all'ordine nella lista schema."""
        result = get_all_parameter_names()
        expected = [s.name for s in STREAM_PARAMETER_SCHEMA]
        assert result == expected

    def test_does_not_include_controller_params(self):
        """Non include parametri dai controller (pointer, pitch, etc.)."""
        result = set(get_all_parameter_names())
        controller_only = {'pointer_start', 'pitch_ratio', 'fill_factor'}
        assert result.isdisjoint(controller_only), (
            f"Parametri controller trovati: {result & controller_only}"
        )

    def test_all_returned_names_are_strings(self):
        for name in get_all_parameter_names():
            assert isinstance(name, str)


# =============================================================================
# 14. CROSS-SCHEMA INVARIANTI
# =============================================================================

class TestCrossSchemaInvariants:
    """Invarianti che devono valere attraverso tutti gli schema."""

    def test_unique_names_across_all_schemas(self):
        """Nessun nome parametro duplicato tra schema diversi."""
        all_names = []
        for schema_list in ALL_SCHEMAS.values():
            for spec in schema_list:
                all_names.append(spec.name)

        duplicates = [n for n in all_names if all_names.count(n) > 1]
        assert len(duplicates) == 0, f"Nomi duplicati: {set(duplicates)}"

    def test_exclusive_groups_within_same_schema(self):
        """
        Ogni gruppo esclusivo esiste solo in un singolo schema,
        non spalmato su schema diversi.
        """
        group_to_schema = {}
        for schema_name, schema_list in ALL_SCHEMAS.items():
            for spec in schema_list:
                if spec.exclusive_group:
                    grp = spec.exclusive_group
                    if grp not in group_to_schema:
                        group_to_schema[grp] = schema_name
                    else:
                        assert group_to_schema[grp] == schema_name, (
                            f"Gruppo '{grp}' trovato in '{group_to_schema[grp]}' "
                            f"e '{schema_name}'"
                        )

    def test_exclusive_groups_have_multiple_members(self):
        """Ogni gruppo esclusivo ha almeno 2 membri (altrimenti non serve)."""
        for schema_name, schema_list in ALL_SCHEMAS.items():
            groups = {}
            for spec in schema_list:
                if spec.exclusive_group:
                    groups.setdefault(spec.exclusive_group, []).append(spec.name)
            for grp, members in groups.items():
                assert len(members) >= 2, (
                    f"Gruppo '{grp}' in '{schema_name}' ha solo {len(members)} membro: {members}"
                )

    def test_exclusive_group_priorities_are_distinct(self):
        """
        All'interno di ogni gruppo esclusivo, le priorita' sono distinte
        (altrimenti la selezione sarebbe ambigua).
        """
        for schema_name, schema_list in ALL_SCHEMAS.items():
            groups = {}
            for spec in schema_list:
                if spec.exclusive_group:
                    groups.setdefault(spec.exclusive_group, []).append(spec)
            for grp, specs in groups.items():
                priorities = [s.group_priority for s in specs]
                assert len(priorities) == len(set(priorities)), (
                    f"Priorita' duplicate nel gruppo '{grp}' ({schema_name}): {priorities}"
                )

    def test_all_smart_params_have_valid_names(self):
        """Ogni parametro smart ha un nome non vuoto."""
        for schema_list in ALL_SCHEMAS.values():
            for spec in schema_list:
                assert spec.name, f"Parametro con nome vuoto trovato"
                assert len(spec.name) > 0

    def test_all_yaml_paths_are_strings(self):
        """Ogni yaml_path e' una stringa non vuota."""
        for schema_list in ALL_SCHEMAS.values():
            for spec in schema_list:
                assert isinstance(spec.yaml_path, str)
                assert len(spec.yaml_path) > 0

    def test_dephase_key_consistency(self):
        """
        Se un parametro ha dephase_key, deve essere is_smart=True
        (i parametri raw non possono avere probabilita').
        Eccezione: grain_envelope che ha dephase_key ma is_smart=False
        (trattamento speciale per envelope categorico).
        """
        exceptions = {'grain_envelope'}
        for schema_list in ALL_SCHEMAS.values():
            for spec in schema_list:
                if spec.dephase_key and spec.name not in exceptions:
                    assert spec.is_smart is True, (
                        f"'{spec.name}' ha dephase_key='{spec.dephase_key}' "
                        f"ma is_smart=False"
                    )

    def test_range_path_implies_smart(self):
        """
        Se un parametro ha range_path, dovrebbe essere is_smart=True
        (i parametri raw non gestiscono range).
        Eccezione: grain_envelope.
        """
        exceptions = {'grain_envelope'}
        for schema_list in ALL_SCHEMAS.values():
            for spec in schema_list:
                if spec.range_path and spec.name not in exceptions:
                    assert spec.is_smart is True, (
                        f"'{spec.name}' ha range_path='{spec.range_path}' "
                        f"ma is_smart=False"
                    )

    def test_known_exclusive_groups(self):
        """Verifica che i gruppi esclusivi siano quelli attesi."""
        all_groups = set()
        for schema_list in ALL_SCHEMAS.values():
            for spec in schema_list:
                if spec.exclusive_group:
                    all_groups.add(spec.exclusive_group)
        expected_groups = {'loop_bounds', 'density_mode'}
        assert all_groups == expected_groups, (
            f"Gruppi esclusivi inattesi: {all_groups - expected_groups} "
            f"o mancanti: {expected_groups - all_groups}"
        )

    def test_non_exclusive_default_priority(self):
        """Parametri senza exclusive_group hanno group_priority=99 (default)."""
        for schema_list in ALL_SCHEMAS.values():
            for spec in schema_list:
                if spec.exclusive_group is None:
                    assert spec.group_priority == 99, (
                        f"'{spec.name}' non ha gruppo esclusivo ma "
                        f"group_priority={spec.group_priority} (atteso 99)"
                    )


# =============================================================================
# 15. PARAMETRIZED: Tutti i parametri di ogni schema
# =============================================================================

def _all_specs_with_schema():
    """Helper: genera (schema_name, spec) per test parametrizzati."""
    pairs = []
    for schema_name, schema_list in ALL_SCHEMAS.items():
        for spec in schema_list:
            pairs.append((schema_name, spec))
    return pairs


class TestParametrizedAllSpecs:
    """Test parametrizzati su ogni singola spec di ogni schema."""

    @pytest.mark.parametrize("schema_name,spec", _all_specs_with_schema(),
                             ids=lambda x: x.name if isinstance(x, ParameterSpec) else x)
    def test_spec_accessible_via_flat_index(self, schema_name, spec):
        """Ogni spec e' accessibile via get_parameter_spec()."""
        retrieved = get_parameter_spec(spec.name)
        assert retrieved.name == spec.name

    @pytest.mark.parametrize("schema_name,spec", _all_specs_with_schema(),
                             ids=lambda x: x.name if isinstance(x, ParameterSpec) else x)
    def test_spec_accessible_via_schema_lookup(self, schema_name, spec):
        """Ogni spec e' accessibile via get_parameter_spec_from_schema()."""
        retrieved = get_parameter_spec_from_schema(schema_name, spec.name)
        assert retrieved is spec

    @pytest.mark.parametrize("schema_name,spec", _all_specs_with_schema(),
                             ids=lambda x: x.name if isinstance(x, ParameterSpec) else x)
    def test_spec_name_is_nonempty_string(self, schema_name, spec):
        assert isinstance(spec.name, str) and len(spec.name) > 0

    @pytest.mark.parametrize("schema_name,spec", _all_specs_with_schema(),
                             ids=lambda x: x.name if isinstance(x, ParameterSpec) else x)
    def test_spec_is_smart_is_bool(self, schema_name, spec):
        assert isinstance(spec.is_smart, bool)