# tests/test_exclusive_selector.py
"""
Suite di test completa per ExclusiveGroupSelector (src/exclusive_selector.py).

Copre:
- select_parameters: logica di selezione per gruppi esclusivi
- _is_specified: rilevamento parametri presenti in YAML
- gestione parametri non-esclusivi
- edge cases: schema vuoto, gruppo singleton, tutti i default None
- integrazione con gli schema reali del progetto (pitch_mode, density_mode, loop_bounds)
"""

import pytest

from parameters.exclusive_selector import ExclusiveGroupSelector
from parameters.parameter_schema import (
    ParameterSpec,
    PITCH_PARAMETER_SCHEMA,
    DENSITY_PARAMETER_SCHEMA,
    POINTER_PARAMETER_SCHEMA,
)


# =============================================================================
# FIXTURES
# =============================================================================

def make_spec(
    name: str,
    yaml_path: str,
    default=None,
    exclusive_group: str = None,
    group_priority: int = 99,
    is_smart: bool = True,
) -> ParameterSpec:
    """Factory helper per creare ParameterSpec nei test."""
    return ParameterSpec(
        name=name,
        yaml_path=yaml_path,
        default=default,
        exclusive_group=exclusive_group,
        group_priority=group_priority,
        is_smart=is_smart,
    )


# =============================================================================
# GRUPPO 1: _is_specified
# =============================================================================

class TestIsSpecified:
    """Test del metodo statico _is_specified."""

    def test_chiave_presente_con_valore_non_none(self):
        """Chiave presente con valore numerico -> True."""
        spec = make_spec('ratio', 'ratio', default=1.0)
        yaml_data = {'ratio': 2.0}
        assert ExclusiveGroupSelector._is_specified(spec, yaml_data) is True

    def test_chiave_assente(self):
        """Chiave non presente nel dict -> False."""
        spec = make_spec('ratio', 'ratio', default=1.0)
        yaml_data = {}
        assert ExclusiveGroupSelector._is_specified(spec, yaml_data) is False

    def test_chiave_presente_con_valore_zero(self):
        """Zero e' un valore valido, non None -> True."""
        spec = make_spec('semitones', 'semitones', default=None)
        yaml_data = {'semitones': 0}
        assert ExclusiveGroupSelector._is_specified(spec, yaml_data) is True

    def test_chiave_presente_con_stringa_vuota(self):
        """Stringa vuota e' non-None -> True."""
        spec = make_spec('envelope', 'envelope', default='hanning')
        yaml_data = {'envelope': ''}
        assert ExclusiveGroupSelector._is_specified(spec, yaml_data) is True

    def test_chiave_presente_con_false(self):
        """False e' non-None -> True."""
        spec = make_spec('enabled', 'enabled', default=True)
        yaml_data = {'enabled': False}
        assert ExclusiveGroupSelector._is_specified(spec, yaml_data) is True

    def test_chiave_presente_con_lista(self):
        """Lista e' non-None -> True."""
        spec = make_spec('points', 'points', default=None)
        yaml_data = {'points': [0.0, 1.0]}
        assert ExclusiveGroupSelector._is_specified(spec, yaml_data) is True

    def test_chiave_presente_con_valore_none_esplicito(self):
        """Chiave presente ma con valore None esplicito nello YAML -> True
        (la chiave esiste, l'utente l'ha scritta intenzionalmente)."""
        spec = make_spec('semitones', 'semitones', default=None)
        yaml_data = {'semitones': None}
        assert ExclusiveGroupSelector._is_specified(spec, yaml_data) is True

    def test_yaml_path_nested_presente(self):
        """Path annidato con dot notation, valore presente -> True."""
        spec = make_spec('loop_start', 'loop.start', default=None)
        yaml_data = {'loop': {'start': 0.5}}
        assert ExclusiveGroupSelector._is_specified(spec, yaml_data) is True

    def test_yaml_path_nested_assente(self):
        """Path annidato mancante -> False."""
        spec = make_spec('loop_start', 'loop.start', default=None)
        yaml_data = {'loop': {}}
        assert ExclusiveGroupSelector._is_specified(spec, yaml_data) is False

    def test_yaml_path_nested_nodo_intermedio_mancante(self):
        """Nodo intermedio assente nel path annidato -> False."""
        spec = make_spec('loop_start', 'loop.start', default=None)
        yaml_data = {}
        assert ExclusiveGroupSelector._is_specified(spec, yaml_data) is False

    def test_yaml_path_nested_none_esplicito(self):
        """Path annidato con valore None esplicito -> True (chiave esiste)."""
        spec = make_spec('loop_start', 'loop.start', default=None)
        yaml_data = {'loop': {'start': None}}
        assert ExclusiveGroupSelector._is_specified(spec, yaml_data) is True

    def test_yaml_path_nested_intermedio_non_dict(self):
        """Nodo intermedio e' un primitivo, non un dict -> False."""
        spec = make_spec('val', 'level1.level2', default=0)
        yaml_data = {'level1': 42}
        assert ExclusiveGroupSelector._is_specified(spec, yaml_data) is False

    def test_yaml_data_vuoto(self):
        """Dict YAML completamente vuoto -> False."""
        spec = make_spec('ratio', 'ratio', default=1.0)
        assert ExclusiveGroupSelector._is_specified(spec, {}) is False


# =============================================================================
# GRUPPO 2: select_parameters - schema senza gruppi esclusivi
# =============================================================================

class TestSelectParametersNoExclusiveGroups:
    """Comportamento con schema privo di gruppi esclusivi."""

    def test_tutti_i_parametri_non_esclusivi_inclusi(self):
        """Tutti i parametri senza gruppo vengono inclusi incondizionatamente."""
        schema = [
            make_spec('volume', 'volume', default=-6.0),
            make_spec('pan', 'pan', default=0.0),
            make_spec('duration', 'duration', default=0.05),
        ]
        yaml_data = {'volume': -12.0}

        selected, groups = ExclusiveGroupSelector.select_parameters(schema, yaml_data)

        assert 'volume' in selected
        assert 'pan' in selected
        assert 'duration' in selected
        assert groups == {}

    def test_schema_vuoto(self):
        """Schema vuoto restituisce dizionari vuoti."""
        selected, groups = ExclusiveGroupSelector.select_parameters([], {})
        assert selected == {}
        assert groups == {}

    def test_yaml_vuoto_non_esclusivi(self):
        """YAML vuoto non influisce sui parametri non-esclusivi."""
        schema = [make_spec('volume', 'volume', default=-6.0)]
        selected, groups = ExclusiveGroupSelector.select_parameters(schema, {})
        assert 'volume' in selected


# =============================================================================
# GRUPPO 3: select_parameters - logica di priorita'
# =============================================================================

class TestSelectParametersPriority:
    """Logica di selezione basata su group_priority (piu' bassa = piu' alta priorita')."""

    def test_entrambi_presenti_vince_priorita_piu_alta(self):
        """Se entrambi specificati in YAML, vince il piu' basso group_priority."""
        schema = [
            make_spec('option_a', 'a', default=1, exclusive_group='grp', group_priority=2),
            make_spec('option_b', 'b', default=2, exclusive_group='grp', group_priority=1),
        ]
        yaml_data = {'a': 10, 'b': 20}

        selected, _ = ExclusiveGroupSelector.select_parameters(schema, yaml_data)

        assert 'option_b' in selected
        assert 'option_a' not in selected

    def test_entrambi_presenti_vince_priority_1_su_99(self):
        """Priority 1 vince su priority 99."""
        schema = [
            make_spec('winner', 'win', default=0, exclusive_group='grp', group_priority=1),
            make_spec('loser', 'lose', default=0, exclusive_group='grp', group_priority=99),
        ]
        yaml_data = {'win': 5, 'lose': 10}

        selected, _ = ExclusiveGroupSelector.select_parameters(schema, yaml_data)

        assert 'winner' in selected
        assert 'loser' not in selected

    def test_solo_bassa_priorita_presente_viene_selezionata(self):
        """Se solo il parametro a bassa priorita' e' nel YAML, viene selezionato."""
        schema = [
            make_spec('high_prio', 'high', default=None, exclusive_group='grp', group_priority=1),
            make_spec('low_prio', 'low', default=5, exclusive_group='grp', group_priority=2),
        ]
        yaml_data = {'low': 10}

        selected, _ = ExclusiveGroupSelector.select_parameters(schema, yaml_data)

        assert 'low_prio' in selected
        assert 'high_prio' not in selected

    def test_solo_alta_priorita_presente_viene_selezionata(self):
        """Se solo il parametro ad alta priorita' e' nel YAML, viene selezionato."""
        schema = [
            make_spec('high_prio', 'high', default=None, exclusive_group='grp', group_priority=1),
            make_spec('low_prio', 'low', default=5, exclusive_group='grp', group_priority=2),
        ]
        yaml_data = {'high': 42}

        selected, _ = ExclusiveGroupSelector.select_parameters(schema, yaml_data)

        assert 'high_prio' in selected
        assert 'low_prio' not in selected


# =============================================================================
# GRUPPO 4: select_parameters - fallback su default
# =============================================================================

class TestSelectParametersDefaultFallback:
    """Comportamento quando nessun parametro e' specificato nello YAML."""

    def test_nessuno_presente_usa_primo_con_default_non_none(self):
        """Nessuno specificato -> usa primo (per priorita') con default non-None."""
        schema = [
            make_spec('opt_a', 'a', default=1.0, exclusive_group='grp', group_priority=1),
            make_spec('opt_b', 'b', default=2.0, exclusive_group='grp', group_priority=2),
        ]
        yaml_data = {}

        selected, _ = ExclusiveGroupSelector.select_parameters(schema, yaml_data)

        assert 'opt_a' in selected
        assert 'opt_b' not in selected

    def test_nessuno_presente_salta_default_none_cerca_non_none(self):
        """Se priorita' piu' alta ha default=None, usa il prossimo con default non-None."""
        schema = [
            make_spec('opt_a', 'a', default=None, exclusive_group='grp', group_priority=1),
            make_spec('opt_b', 'b', default=2.0, exclusive_group='grp', group_priority=2),
        ]
        yaml_data = {}

        selected, _ = ExclusiveGroupSelector.select_parameters(schema, yaml_data)

        assert 'opt_b' in selected
        assert 'opt_a' not in selected

    def test_tutti_default_none_nessun_vincitore(self):
        """Se tutti i default sono None e nessuno e' nel YAML,
        il gruppo non produce nessun vincitore (nessuna chiave inserita)."""
        schema = [
            make_spec('opt_a', 'a', default=None, exclusive_group='grp', group_priority=1),
            make_spec('opt_b', 'b', default=None, exclusive_group='grp', group_priority=2),
        ]
        yaml_data = {}

        selected, _ = ExclusiveGroupSelector.select_parameters(schema, yaml_data)

        assert 'opt_a' not in selected
        assert 'opt_b' not in selected

    def test_tutti_default_none_ma_uno_specificato_vince(self):
        """Se tutti i default sono None ma uno e' nel YAML, quello vince."""
        schema = [
            make_spec('opt_a', 'a', default=None, exclusive_group='grp', group_priority=1),
            make_spec('opt_b', 'b', default=None, exclusive_group='grp', group_priority=2),
        ]
        yaml_data = {'b': 3.0}

        selected, _ = ExclusiveGroupSelector.select_parameters(schema, yaml_data)

        assert 'opt_b' in selected
        assert 'opt_a' not in selected

    def test_pointer_solo_loop_start_loop_bounds_nessun_vincitore(self):
        """Caso reale: YAML con solo loop_start -> loop_bounds non produce vincitore,
        loop_end e loop_dur assenti dal selected."""
        yaml_data = {'loop_start': 0.5}

        selected, _ = ExclusiveGroupSelector.select_parameters(
            POINTER_PARAMETER_SCHEMA, yaml_data
        )

        assert 'loop_end' not in selected
        assert 'loop_dur' not in selected
        # loop_start e' non-esclusivo, deve essere presente
        assert 'loop_start' in selected

    def test_yaml_ha_chiavi_irrilevanti_usa_default(self):
        """YAML con chiavi non pertinenti -> fallback a default."""
        schema = [
            make_spec('opt_a', 'a', default=1.0, exclusive_group='grp', group_priority=1),
            make_spec('opt_b', 'b', default=2.0, exclusive_group='grp', group_priority=2),
        ]
        yaml_data = {'other_key': 99}

        selected, _ = ExclusiveGroupSelector.select_parameters(schema, yaml_data)

        assert 'opt_a' in selected


# =============================================================================
# GRUPPO 5: select_parameters - struttura del ritorno
# =============================================================================

class TestSelectParametersReturnStructure:
    """Verifica la struttura del valore di ritorno."""

    def test_ritorna_tupla_di_due_elementi(self):
        """select_parameters ritorna esattamente una tupla di 2 elementi."""
        schema = [make_spec('v', 'v', default=0)]
        result = ExclusiveGroupSelector.select_parameters(schema, {})
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_primo_elemento_e_dict(self):
        """Il primo elemento e' un dict {str: ParameterSpec}."""
        schema = [make_spec('v', 'v', default=0)]
        selected, _ = ExclusiveGroupSelector.select_parameters(schema, {})
        assert isinstance(selected, dict)

    def test_secondo_elemento_e_dict_dei_gruppi(self):
        """Il secondo elemento e' un dict dei gruppi esclusivi."""
        schema = [
            make_spec('opt_a', 'a', default=1, exclusive_group='grp', group_priority=1),
            make_spec('opt_b', 'b', default=2, exclusive_group='grp', group_priority=2),
        ]
        _, groups = ExclusiveGroupSelector.select_parameters(schema, {})
        assert isinstance(groups, dict)
        assert 'grp' in groups
        assert len(groups['grp']) == 2

    def test_group_members_contiene_tutti_i_membri_del_gruppo(self):
        """Il secondo dict contiene tutti i membri del gruppo, non solo il vincitore."""
        schema = [
            make_spec('opt_a', 'a', default=1, exclusive_group='grp', group_priority=1),
            make_spec('opt_b', 'b', default=2, exclusive_group='grp', group_priority=2),
        ]
        yaml_data = {'a': 5}

        selected, groups = ExclusiveGroupSelector.select_parameters(schema, yaml_data)

        # Il vincitore e' opt_a (specificato + priority 1)
        assert 'opt_a' in selected
        # Ma il gruppo contiene entrambi
        member_names = [s.name for s in groups['grp']]
        assert 'opt_a' in member_names
        assert 'opt_b' in member_names

    def test_i_valori_del_selected_sono_parameter_spec(self):
        """I valori del dict selected sono istanze di ParameterSpec."""
        schema = [
            make_spec('v', 'v', default=0, exclusive_group='grp', group_priority=1),
            make_spec('w', 'w', default=1, exclusive_group='grp', group_priority=2),
        ]
        selected, _ = ExclusiveGroupSelector.select_parameters(schema, {})
        for spec in selected.values():
            assert isinstance(spec, ParameterSpec)


# =============================================================================
# GRUPPO 6: select_parameters - piu' gruppi esclusivi
# =============================================================================

class TestSelectParametersMultipleGroups:
    """Comportamento con piu' gruppi esclusivi nello stesso schema."""

    def test_due_gruppi_indipendenti(self):
        """Due gruppi esclusivi vengono gestiti indipendentemente."""
        schema = [
            make_spec('pitch_ratio', 'ratio', default=1.0, exclusive_group='pitch_mode', group_priority=2),
            make_spec('pitch_semitones', 'semitones', default=None, exclusive_group='pitch_mode', group_priority=1),
            make_spec('fill_factor', 'fill_factor', default=2, exclusive_group='density_mode', group_priority=1),
            make_spec('density', 'density', default=None, exclusive_group='density_mode', group_priority=2),
        ]
        yaml_data = {'semitones': 12, 'density': 50}

        selected, groups = ExclusiveGroupSelector.select_parameters(schema, yaml_data)

        # pitch_mode: semitones specificato e priority 1 -> vince
        assert 'pitch_semitones' in selected
        assert 'pitch_ratio' not in selected
        # density_mode: density specificato, fill_factor non specificato -> density vince
        assert 'density' in selected
        assert 'fill_factor' not in selected

        assert 'pitch_mode' in groups
        assert 'density_mode' in groups

    def test_due_gruppi_mix_presente_e_default(self):
        """Un gruppo usa YAML, l'altro usa il default."""
        schema = [
            make_spec('a1', 'a1', default=1.0, exclusive_group='group_a', group_priority=1),
            make_spec('a2', 'a2', default=2.0, exclusive_group='group_a', group_priority=2),
            make_spec('b1', 'b1', default=None, exclusive_group='group_b', group_priority=1),
            make_spec('b2', 'b2', default=5.0, exclusive_group='group_b', group_priority=2),
        ]
        yaml_data = {'a2': 99}  # Solo a2 specificato, nessuno di group_b

        selected, _ = ExclusiveGroupSelector.select_parameters(schema, yaml_data)

        # group_a: a2 specificato -> vince anche se priorita' piu' bassa
        assert 'a2' in selected
        assert 'a1' not in selected
        # group_b: nessuno specificato, b1 ha default None -> usa b2
        assert 'b2' in selected
        assert 'b1' not in selected

    def test_non_esclusivi_presenti_insieme_ai_vincitori(self):
        """I parametri non-esclusivi compaiono nel selected insieme ai vincitori dei gruppi."""
        schema = [
            make_spec('opt_a', 'a', default=1, exclusive_group='grp', group_priority=1),
            make_spec('opt_b', 'b', default=2, exclusive_group='grp', group_priority=2),
            make_spec('volume', 'volume', default=-6.0),
            make_spec('pan', 'pan', default=0.0),
        ]
        yaml_data = {}

        selected, _ = ExclusiveGroupSelector.select_parameters(schema, yaml_data)

        assert 'opt_a' in selected
        assert 'volume' in selected
        assert 'pan' in selected
        assert len(selected) == 3  # opt_a + volume + pan


# =============================================================================
# GRUPPO 7: select_parameters - gruppo con un solo membro
# =============================================================================

class TestSelectParametersSingletonGroup:
    """Gruppo esclusivo con un solo membro (caso degenere)."""

    def test_gruppo_singolo_membro_viene_sempre_selezionato(self):
        """Un gruppo con un solo membro lo seleziona sempre."""
        schema = [
            make_spec('solo', 'solo', default=1.0, exclusive_group='grp', group_priority=1),
        ]
        yaml_data = {}

        selected, _ = ExclusiveGroupSelector.select_parameters(schema, yaml_data)

        assert 'solo' in selected

    def test_gruppo_singolo_membro_specificato(self):
        """Gruppo singleton con membro specificato -> selezionato."""
        schema = [
            make_spec('solo', 'solo', default=1.0, exclusive_group='grp', group_priority=1),
        ]
        yaml_data = {'solo': 42}

        selected, _ = ExclusiveGroupSelector.select_parameters(schema, yaml_data)

        assert 'solo' in selected
        assert selected['solo'].name == 'solo'


# =============================================================================
# GRUPPO 8: integrazione con schema reali del progetto
# =============================================================================

class TestIntegrationWithRealSchemas:
    """Test di integrazione con gli schema reali definiti in parameter_schema.py."""

    # --- PITCH_PARAMETER_SCHEMA ---

    def test_pitch_yaml_semitones_seleziona_semitones(self):
        """YAML con semitones -> pitch_semitones selezionato (priority 1)."""
        yaml_data = {'semitones': 12}
        selected, _ = ExclusiveGroupSelector.select_parameters(PITCH_PARAMETER_SCHEMA, yaml_data)
        assert 'pitch_semitones' in selected
        assert 'pitch_ratio' not in selected

    def test_pitch_yaml_ratio_seleziona_ratio(self):
        """YAML con ratio -> pitch_ratio selezionato (unico specificato)."""
        yaml_data = {'ratio': 2.0}
        selected, _ = ExclusiveGroupSelector.select_parameters(PITCH_PARAMETER_SCHEMA, yaml_data)
        assert 'pitch_ratio' in selected
        assert 'pitch_semitones' not in selected

    def test_pitch_yaml_entrambi_vince_semitones(self):
        """YAML con entrambi -> pitch_semitones vince (priority 1)."""
        yaml_data = {'semitones': 12, 'ratio': 2.0}
        selected, _ = ExclusiveGroupSelector.select_parameters(PITCH_PARAMETER_SCHEMA, yaml_data)
        assert 'pitch_semitones' in selected
        assert 'pitch_ratio' not in selected

    def test_pitch_yaml_vuoto_usa_ratio_come_default(self):
        """YAML vuoto -> pitch_ratio selezionato (ha default=1.0, semitones ha default=None)."""
        yaml_data = {}
        selected, _ = ExclusiveGroupSelector.select_parameters(PITCH_PARAMETER_SCHEMA, yaml_data)
        assert 'pitch_ratio' in selected
        assert 'pitch_semitones' not in selected

    # --- DENSITY_PARAMETER_SCHEMA ---

    def test_density_yaml_fill_factor_vince(self):
        """fill_factor specificato -> selezionato (priority 1)."""
        yaml_data = {'fill_factor': 3}
        selected, _ = ExclusiveGroupSelector.select_parameters(DENSITY_PARAMETER_SCHEMA, yaml_data)
        assert 'fill_factor' in selected
        assert 'density' not in selected

    def test_density_yaml_density_vince_se_solo_presente(self):
        """Solo density specificato -> selezionato."""
        yaml_data = {'density': 50}
        selected, _ = ExclusiveGroupSelector.select_parameters(DENSITY_PARAMETER_SCHEMA, yaml_data)
        assert 'density' in selected
        assert 'fill_factor' not in selected

    def test_density_yaml_entrambi_vince_fill_factor(self):
        """Entrambi specificati -> fill_factor vince (priority 1)."""
        yaml_data = {'fill_factor': 3, 'density': 50}
        selected, _ = ExclusiveGroupSelector.select_parameters(DENSITY_PARAMETER_SCHEMA, yaml_data)
        assert 'fill_factor' in selected
        assert 'density' not in selected

    def test_density_yaml_vuoto_usa_fill_factor_come_default(self):
        """YAML vuoto -> fill_factor selezionato (default=2, priority 1)."""
        yaml_data = {}
        selected, _ = ExclusiveGroupSelector.select_parameters(DENSITY_PARAMETER_SCHEMA, yaml_data)
        assert 'fill_factor' in selected
        assert 'density' not in selected

    def test_density_parametri_non_esclusivi_sempre_presenti(self):
        """distribution e effective_density (non-esclusivi) sempre nel selected."""
        yaml_data = {}
        selected, _ = ExclusiveGroupSelector.select_parameters(DENSITY_PARAMETER_SCHEMA, yaml_data)
        assert 'distribution' in selected
        assert 'effective_density' in selected

    # --- POINTER_PARAMETER_SCHEMA ---

    def test_pointer_loop_end_specificato_vince(self):
        """loop_end specificato -> selezionato (priority 1 nel gruppo loop_bounds)."""
        yaml_data = {'loop_end': 0.9}
        selected, _ = ExclusiveGroupSelector.select_parameters(POINTER_PARAMETER_SCHEMA, yaml_data)
        assert 'loop_end' in selected
        assert 'loop_dur' not in selected

    def test_pointer_loop_dur_specificato_quando_loop_end_assente(self):
        """Solo loop_dur specificato -> selezionato."""
        yaml_data = {'loop_dur': 3.0}
        selected, _ = ExclusiveGroupSelector.select_parameters(POINTER_PARAMETER_SCHEMA, yaml_data)
        assert 'loop_dur' in selected
        assert 'loop_end' not in selected

    def test_pointer_entrambi_specificati_vince_loop_end(self):
        """Entrambi specificati -> loop_end vince (priority 1)."""
        yaml_data = {'loop_end': 0.9, 'loop_dur': 3.0}
        selected, _ = ExclusiveGroupSelector.select_parameters(POINTER_PARAMETER_SCHEMA, yaml_data)
        assert 'loop_end' in selected
        assert 'loop_dur' not in selected

    def test_pointer_yaml_vuoto_loop_bounds_nessun_vincitore(self):
        """YAML vuoto: loop_end e loop_dur hanno entrambi default=None ->
        il gruppo loop_bounds non produce nessun vincitore."""
        yaml_data = {}
        selected, _ = ExclusiveGroupSelector.select_parameters(
            POINTER_PARAMETER_SCHEMA, yaml_data
        )
        assert 'loop_end' not in selected
        assert 'loop_dur' not in selected

    def test_pointer_parametri_non_esclusivi_sempre_presenti(self):
        """pointer_start, pointer_speed_ratio etc. sempre nel selected."""
        yaml_data = {}
        selected, _ = ExclusiveGroupSelector.select_parameters(POINTER_PARAMETER_SCHEMA, yaml_data)
        assert 'pointer_start' in selected
        assert 'pointer_speed_ratio' in selected
        assert 'pointer_deviation' in selected
        assert 'loop_start' in selected


# =============================================================================
# GRUPPO 9: parametrizzato - tabella di verita' per _is_specified
# =============================================================================

class TestIsSpecifiedParametrized:
    """Test parametrizzato per coprire la tabella di verita' di _is_specified."""

    @pytest.mark.parametrize("yaml_data,yaml_path,expected", [
        # Chiave flat presente con vari tipi
        ({'x': 1}, 'x', True),
        ({'x': 1.5}, 'x', True),
        ({'x': 'str'}, 'x', True),
        ({'x': []}, 'x', True),
        ({'x': {}}, 'x', True),
        ({'x': False}, 'x', True),
        ({'x': 0}, 'x', True),
        ({'x': 0.0}, 'x', True),
        # Chiave assente
        ({}, 'x', False),
        ({'y': 1}, 'x', False),
        # None esplicito con chiave presente
        ({'x': None}, 'x', True),
        # Path annidato presente
        ({'a': {'b': 1}}, 'a.b', True),
        ({'a': {'b': None}}, 'a.b', True),
        # Path annidato assente
        ({'a': {}}, 'a.b', False),
        ({}, 'a.b', False),
        # Nodo intermedio non-dict
        ({'a': 42}, 'a.b', False),
    ])
    def test_is_specified_table(self, yaml_data, yaml_path, expected):
        spec = make_spec('test', yaml_path, default=None)
        result = ExclusiveGroupSelector._is_specified(spec, yaml_data)
        assert result == expected, (
            f"yaml_data={yaml_data}, yaml_path='{yaml_path}' -> "
            f"atteso {expected}, ottenuto {result}"
        )


# =============================================================================
# GRUPPO 10: edge cases aggiuntivi
# =============================================================================

class TestEdgeCases:
    """Edge case aggiuntivi."""

    def test_tre_membri_nel_gruppo_vince_priority_1(self):
        """Tre membri in un gruppo: vince sempre il priority 1 se specificato."""
        schema = [
            make_spec('c', 'c', default=3, exclusive_group='grp', group_priority=3),
            make_spec('a', 'a', default=1, exclusive_group='grp', group_priority=1),
            make_spec('b', 'b', default=2, exclusive_group='grp', group_priority=2),
        ]
        yaml_data = {'a': 10, 'b': 20, 'c': 30}

        selected, _ = ExclusiveGroupSelector.select_parameters(schema, yaml_data)

        assert 'a' in selected
        assert 'b' not in selected
        assert 'c' not in selected

    def test_tre_membri_solo_priority_3_specificato(self):
        """Tre membri: solo priority 3 specificato -> vince lui."""
        schema = [
            make_spec('a', 'a', default=None, exclusive_group='grp', group_priority=1),
            make_spec('b', 'b', default=None, exclusive_group='grp', group_priority=2),
            make_spec('c', 'c', default=3, exclusive_group='grp', group_priority=3),
        ]
        yaml_data = {'c': 30}

        selected, _ = ExclusiveGroupSelector.select_parameters(schema, yaml_data)

        assert 'c' in selected
        assert 'a' not in selected
        assert 'b' not in selected

    def test_selected_non_contiene_perdenti_del_gruppo(self):
        """I perdenti di un gruppo esclusivo non compaiono in selected."""
        schema = [
            make_spec('winner', 'win', default=1, exclusive_group='grp', group_priority=1),
            make_spec('loser', 'lose', default=2, exclusive_group='grp', group_priority=2),
        ]
        yaml_data = {}

        selected, _ = ExclusiveGroupSelector.select_parameters(schema, yaml_data)

        assert 'winner' in selected
        assert 'loser' not in selected

    def test_spec_nel_selected_e_lo_stesso_oggetto_dallo_schema(self):
        """Il ParameterSpec nel selected e' lo stesso oggetto della lista schema."""
        spec_a = make_spec('opt_a', 'a', default=1, exclusive_group='grp', group_priority=1)
        spec_b = make_spec('opt_b', 'b', default=2, exclusive_group='grp', group_priority=2)
        schema = [spec_a, spec_b]
        yaml_data = {}

        selected, _ = ExclusiveGroupSelector.select_parameters(schema, yaml_data)

        assert selected['opt_a'] is spec_a

    def test_ordine_schema_non_influenza_selezione_priorita(self):
        """Invertire l'ordine dei member in schema non cambia il vincitore per priorita'."""
        schema_normale = [
            make_spec('a', 'a', default=1, exclusive_group='grp', group_priority=1),
            make_spec('b', 'b', default=2, exclusive_group='grp', group_priority=2),
        ]
        schema_invertito = [
            make_spec('b', 'b', default=2, exclusive_group='grp', group_priority=2),
            make_spec('a', 'a', default=1, exclusive_group='grp', group_priority=1),
        ]
        yaml_data = {'a': 5, 'b': 10}

        sel_norm, _ = ExclusiveGroupSelector.select_parameters(schema_normale, yaml_data)
        sel_inv, _ = ExclusiveGroupSelector.select_parameters(schema_invertito, yaml_data)

        assert 'a' in sel_norm
        assert 'a' in sel_inv