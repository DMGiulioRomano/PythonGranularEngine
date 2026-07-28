"""
test_stream_config.py

Test suite completa per StreamContext e StreamConfig.

Coverage:
  1. StreamContext - costruzione diretta
  2. StreamContext.from_yaml - parsing completo
  3. StreamContext.from_yaml - allow_none semantics
  4. StreamContext - immutabilita' (frozen)
  5. StreamConfig - costruzione diretta con defaults
  6. StreamConfig - costruzione diretta con valori custom
  7. StreamConfig.from_yaml - parsing completo
  8. StreamConfig.from_yaml - allow_none semantics
  9. StreamConfig.from_yaml - iniezione context
 10. StreamConfig - tipi polimorfi di dephase (dict, bool, int, float, list)
 11. StreamConfig - immutabilita' (frozen)
 12. Integrazione StreamContext + StreamConfig
 13. Edge cases e error handling
 14. __eq__ e __hash__ (frozen dataclass)
 15. Annotazione type hint errata in StreamContext.from_yaml
"""

import pytest
from dataclasses import FrozenInstanceError, fields
from pge.core.stream_config import StreamConfig, StreamContext


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def full_yaml_context():
    """YAML completo per StreamContext."""
    return {
        'stream_id': 'stream_01',
        'onset': 0.5,
        'duration': 10.0,
        'sample': 'water.wav',
    }


@pytest.fixture
def full_yaml_config():
    """YAML completo per StreamConfig (campi di processo)."""
    return {
        'dephase': True,
        'range_always_active': True,
        'distribution_mode': 'gaussian',
        'time_mode': 'normalized',
        'time_scale': 2.0,
    }


@pytest.fixture
def sample_dur():
    """Durata sample di riferimento."""
    return 5.0


@pytest.fixture
def stream_context(full_yaml_context, sample_dur):
    """StreamContext pre-costruito."""
    return StreamContext.from_yaml(full_yaml_context, sample_dur_sec=sample_dur)


# =============================================================================
# 1. STREAM CONTEXT - COSTRUZIONE DIRETTA
# =============================================================================

class TestStreamContextDirect:
    """Test costruzione diretta di StreamContext."""

    def test_create_with_all_fields(self):
        """Costruzione con tutti i campi espliciti."""
        ctx = StreamContext(
            stream_id='s1',
            onset=1.0,
            duration=5.0,
            sample='voice.wav',
            sample_dur_sec=3.2
        )
        assert ctx.stream_id == 's1'
        assert ctx.onset == 1.0
        assert ctx.duration == 5.0
        assert ctx.sample == 'voice.wav'
        assert ctx.sample_dur_sec == 3.2

    def test_field_count(self):
        """StreamContext ha esattamente 7 campi."""
        assert len(fields(StreamContext)) == 7

    def test_field_names(self):
        """Nomi campi corretti e nell'ordine atteso."""
        names = [f.name for f in fields(StreamContext)]
        assert names == ['stream_id', 'onset', 'duration', 'sample',
                         'sample_dur_sec', 'output_sr', 'rng_group']

    def test_missing_required_field_raises(self):
        """Campi mancanti nella costruzione diretta -> TypeError."""
        with pytest.raises(TypeError):
            StreamContext(stream_id='s1', onset=0.0)


class TestStreamContextOutputSr:
    """Il context espone il sample rate di output del motore."""

    def test_default_output_sr_is_engine_constant(self):
        """Senza indicazioni, output_sr e' la costante di sistema (48000)."""
        from pge.shared.constants import DEFAULT_OUTPUT_SR

        ctx = StreamContext(
            stream_id='s1', onset=0.0, duration=5.0,
            sample='voice.wav', sample_dur_sec=3.2,
        )
        assert DEFAULT_OUTPUT_SR == 48000
        assert ctx.output_sr == DEFAULT_OUTPUT_SR

    def test_from_yaml_defaults_output_sr(self):
        """from_yaml senza chiave output_sr usa il default di sistema."""
        from pge.shared.constants import DEFAULT_OUTPUT_SR

        ctx = StreamContext.from_yaml(
            {'stream_id': 's1', 'onset': 0.0, 'duration': 5.0,
             'sample': 'voice.wav'},
            sample_dur_sec=3.2,
        )
        assert ctx.output_sr == DEFAULT_OUTPUT_SR

    def test_from_yaml_ignores_per_stream_output_sr(self):
        """output_sr e' una config GLOBALE del motore, non un campo per-stream:
        una chiave nello YAML dello stream NON deve entrare nel context.

        Altrimenti divergerebbe dal sample rate con cui il renderer viene
        costruito (main.py lo passa a DEFAULT_OUTPUT_SR): la conversione
        samples->secondi e il bound minimo userebbero un SR, il rendering un
        altro, producendo grani di lunghezza sbagliata.
        """
        from pge.shared.constants import DEFAULT_OUTPUT_SR

        ctx = StreamContext.from_yaml(
            {'stream_id': 's1', 'onset': 0.0, 'duration': 5.0,
             'sample': 'voice.wav', 'output_sr': 96000},
            sample_dur_sec=3.2,
        )
        assert ctx.output_sr == DEFAULT_OUTPUT_SR


# =============================================================================
# 2. STREAM CONTEXT - FROM_YAML PARSING
# =============================================================================

class TestStreamContextFromYaml:
    """Test StreamContext.from_yaml()."""

    def test_full_yaml_parsing(self, full_yaml_context, sample_dur):
        """Parsing completo con tutti i campi presenti."""
        ctx = StreamContext.from_yaml(full_yaml_context, sample_dur_sec=sample_dur)

        assert ctx.stream_id == 'stream_01'
        assert ctx.onset == 0.5
        assert ctx.duration == 10.0
        assert ctx.sample == 'water.wav'
        assert ctx.sample_dur_sec == sample_dur

    def test_sample_dur_sec_injected_not_from_yaml(self, sample_dur):
        """sample_dur_sec viene dal parametro, NON dallo YAML."""
        yaml_data = {
            'stream_id': 's1',
            'onset': 0.0,
            'duration': 5.0,
            'sample': 'test.wav',
            'sample_dur_sec': 999.0,  # Presente nello YAML ma ignorato
        }
        ctx = StreamContext.from_yaml(yaml_data, sample_dur_sec=sample_dur)
        # Il valore YAML viene sovrascritto dall'argomento
        assert ctx.sample_dur_sec == sample_dur

    def test_extra_fields_ignored(self, sample_dur):
        """Campi extra nello YAML vengono ignorati."""
        yaml_data = {
            'stream_id': 's1',
            'onset': 0.0,
            'duration': 5.0,
            'sample': 'test.wav',
            'volume': -6.0,           # extra
            'pitch_ratio': 1.0,       # extra
            'unknown_field': 'foo',   # extra
        }
        ctx = StreamContext.from_yaml(yaml_data, sample_dur_sec=sample_dur)
        assert ctx.stream_id == 's1'
        assert not hasattr(ctx, 'volume')

    def test_missing_yaml_field_raises(self, sample_dur):
        """Campo obbligatorio mancante nello YAML -> TypeError."""
        yaml_data = {
            'stream_id': 's1',
            'onset': 0.0,
            # 'duration' mancante
            # 'sample' mancante
        }
        with pytest.raises(TypeError):
            StreamContext.from_yaml(yaml_data, sample_dur_sec=sample_dur)

    def test_returns_streamcontext_instance(self, full_yaml_context, sample_dur):
        """from_yaml ritorna un'istanza di StreamContext."""
        ctx = StreamContext.from_yaml(full_yaml_context, sample_dur_sec=sample_dur)
        assert isinstance(ctx, StreamContext)

    def test_numeric_types_preserved(self, sample_dur):
        """Tipi numerici preservati (int onset resta int se passato)."""
        yaml_data = {
            'stream_id': 's1',
            'onset': 0,        # int
            'duration': 10,    # int
            'sample': 'test.wav',
        }
        ctx = StreamContext.from_yaml(yaml_data, sample_dur_sec=sample_dur)
        assert ctx.onset == 0
        assert ctx.duration == 10


# =============================================================================
# 3. STREAM CONTEXT - ALLOW_NONE SEMANTICS
# =============================================================================

class TestStreamContextAllowNone:
    """Test allow_none su StreamContext.from_yaml()."""

    def test_allow_none_true_includes_none_values(self, sample_dur):
        """allow_none=True include campi con valore None."""
        yaml_data = {
            'stream_id': 's1',
            'onset': None,       # None esplicito
            'duration': 5.0,
            'sample': 'test.wav',
        }
        # Con allow_none=True, onset=None viene incluso
        ctx = StreamContext.from_yaml(yaml_data, sample_dur_sec=sample_dur, allow_none=True)
        assert ctx.onset is None

    def test_allow_none_false_excludes_none_values(self, sample_dur):
        """allow_none=False esclude campi con valore None -> TypeError se obbligatori."""
        yaml_data = {
            'stream_id': 's1',
            'onset': None,       # Escluso con allow_none=False
            'duration': 5.0,
            'sample': 'test.wav',
        }
        # onset escluso -> TypeError (campo obbligatorio senza default)
        with pytest.raises(TypeError):
            StreamContext.from_yaml(yaml_data, sample_dur_sec=sample_dur, allow_none=False)

    def test_allow_none_default_is_true(self, full_yaml_context, sample_dur):
        """Il default di allow_none e' True."""
        # Verifica che il comportamento default sia allow_none=True
        ctx_default = StreamContext.from_yaml(full_yaml_context, sample_dur_sec=sample_dur)
        ctx_explicit = StreamContext.from_yaml(
            full_yaml_context, sample_dur_sec=sample_dur, allow_none=True
        )
        assert ctx_default == ctx_explicit

    def test_allow_none_false_with_all_non_none(self, full_yaml_context, sample_dur):
        """allow_none=False con tutti valori non-None funziona."""
        ctx = StreamContext.from_yaml(
            full_yaml_context, sample_dur_sec=sample_dur, allow_none=False
        )
        assert ctx.stream_id == 'stream_01'
        assert ctx.onset == 0.5


# =============================================================================
# 4. STREAM CONTEXT - IMMUTABILITA'
# =============================================================================

class TestStreamContextFrozen:
    """Test immutabilita' (frozen=True)."""

    def test_cannot_set_attribute(self, stream_context):
        """Assegnamento diretto solleva FrozenInstanceError."""
        with pytest.raises(FrozenInstanceError):
            stream_context.stream_id = 'modified'

    def test_cannot_set_onset(self, stream_context):
        """Onset non modificabile."""
        with pytest.raises(FrozenInstanceError):
            stream_context.onset = 99.0

    def test_cannot_delete_attribute(self, stream_context):
        """Cancellazione attributo solleva FrozenInstanceError."""
        with pytest.raises(FrozenInstanceError):
            del stream_context.duration

    def test_cannot_add_new_attribute(self, stream_context):
        """Aggiunta nuovo attributo solleva FrozenInstanceError."""
        with pytest.raises(FrozenInstanceError):
            stream_context.new_field = 'nope'


# =============================================================================
# 5. STREAM CONFIG - COSTRUZIONE DIRETTA CON DEFAULTS
# =============================================================================

class TestStreamConfigDefaults:
    """Test valori di default di StreamConfig."""

    def test_all_defaults(self):
        """Costruzione senza argomenti usa tutti i defaults."""
        config = StreamConfig()
        assert config.dephase is False
        assert config.range_always_active is False
        assert config.distribution_mode == 'uniform'
        assert config.time_mode == 'absolute'
        assert config.time_scale == 1.0
        assert config.clip_strategy == 'overflow_margin'
        assert config.clip_margin == 0.0
        assert config.seed is None
        assert config.context is None

    def test_field_count(self):
        """StreamConfig ha esattamente 9 campi (issue #154: +seed)."""
        assert len(fields(StreamConfig)) == 9

    def test_field_names(self):
        """Nomi campi nell'ordine atteso."""
        names = [f.name for f in fields(StreamConfig)]
        expected = [
            'dephase', 'range_always_active', 'distribution_mode',
            'time_mode', 'time_scale', 'clip_strategy', 'clip_margin',
            'seed', 'context'
        ]
        assert names == expected

    def test_seed_injected_via_from_yaml_kwarg(self, stream_context):
        """Il seed arriva dal kwarg esplicito (top-level YAML), non dal dict
        per-stream: una chiave 'seed' nel dict dello stream viene ignorata."""
        config = StreamConfig.from_yaml({'seed': 99}, context=stream_context, seed=42)
        assert config.seed == 42

    def test_seed_default_none_from_yaml(self, stream_context):
        """from_yaml senza kwarg seed → None (fallback legacy)."""
        config = StreamConfig.from_yaml({}, context=stream_context)
        assert config.seed is None

    def test_clip_strategy_from_yaml_passthrough(self, stream_context):
        """from_yaml legge clip_strategy=passthrough."""
        config = StreamConfig.from_yaml({'clip_strategy': 'passthrough'}, context=stream_context)
        assert config.clip_strategy == 'passthrough'

    def test_clip_margin_from_yaml(self, stream_context):
        """from_yaml legge clip_margin float."""
        config = StreamConfig.from_yaml({'clip_margin': 0.5}, context=stream_context)
        assert config.clip_margin == 0.5

    def test_clip_strategy_default_when_omitted(self, stream_context):
        """YAML senza clip_strategy: default preservato."""
        config = StreamConfig.from_yaml({}, context=stream_context)
        assert config.clip_strategy == 'overflow_margin'
        assert config.clip_margin == 0.0


# =============================================================================
# 6. STREAM CONFIG - COSTRUZIONE DIRETTA CON VALORI CUSTOM
# =============================================================================

class TestStreamConfigDirect:
    """Test costruzione diretta di StreamConfig con valori personalizzati."""

    def test_create_with_all_fields(self, stream_context):
        """Costruzione con tutti i campi espliciti."""
        config = StreamConfig(
            dephase={'volume': 0.8},
            range_always_active=True,
            distribution_mode='gaussian',
            time_mode='normalized',
            time_scale=0.5,
            context=stream_context
        )
        assert config.dephase == {'volume': 0.8}
        assert config.range_always_active is True
        assert config.distribution_mode == 'gaussian'
        assert config.time_mode == 'normalized'
        assert config.time_scale == 0.5
        assert config.context is stream_context

    def test_partial_override(self, stream_context):
        """Override parziale, il resto usa defaults."""
        config = StreamConfig(
            dephase=True,
            context=stream_context
        )
        assert config.dephase is True
        assert config.range_always_active is False  # default
        assert config.distribution_mode == 'uniform'  # default
        assert config.context is stream_context


# =============================================================================
# 7. STREAM CONFIG - FROM_YAML PARSING
# =============================================================================

class TestStreamConfigFromYaml:
    """Test StreamConfig.from_yaml()."""

    def test_full_yaml_parsing(self, full_yaml_config, stream_context):
        """Parsing completo con tutti i campi di processo."""
        config = StreamConfig.from_yaml(full_yaml_config, context=stream_context)

        assert config.dephase is True
        assert config.range_always_active is True
        assert config.distribution_mode == 'gaussian'
        assert config.time_mode == 'normalized'
        assert config.time_scale == 2.0
        assert config.context is stream_context

    def test_empty_yaml_uses_all_defaults(self, stream_context):
        """YAML vuoto -> tutti i defaults + context iniettato."""
        config = StreamConfig.from_yaml({}, context=stream_context)

        assert config.dephase is False
        assert config.range_always_active is False
        assert config.distribution_mode == 'uniform'
        assert config.time_mode == 'absolute'
        assert config.time_scale == 1.0
        assert config.context is stream_context

    def test_partial_yaml_uses_defaults_for_missing(self, stream_context):
        """Campi parziali: quelli presenti override, il resto default."""
        yaml_data = {'time_mode': 'normalized', 'dephase': True}
        config = StreamConfig.from_yaml(yaml_data, context=stream_context)

        assert config.time_mode == 'normalized'
        assert config.dephase is True
        assert config.distribution_mode == 'uniform'  # default
        assert config.time_scale == 1.0  # default

    def test_extra_fields_ignored(self, stream_context):
        """Campi extra nello YAML vengono ignorati."""
        yaml_data = {
            'dephase': True,
            'volume': -6.0,           # extra
            'pointer_speed': 1.0,     # extra
        }
        config = StreamConfig.from_yaml(yaml_data, context=stream_context)
        assert config.dephase is True
        assert not hasattr(config, 'volume')

    def test_context_injection_overrides_yaml_context(self, stream_context):
        """Il context passato come argomento sovrascrive quello YAML."""
        fake_context = StreamContext(
            stream_id='fake', onset=0.0, duration=1.0,
            sample='fake.wav', sample_dur_sec=1.0
        )
        yaml_data = {'context': fake_context}  # presente nello YAML

        config = StreamConfig.from_yaml(yaml_data, context=stream_context)

        # L'argomento vince sempre
        assert config.context is stream_context
        assert config.context.stream_id == 'stream_01'

    def test_returns_streamconfig_instance(self, stream_context):
        """from_yaml ritorna un'istanza di StreamConfig."""
        config = StreamConfig.from_yaml({}, context=stream_context)
        assert isinstance(config, StreamConfig)


# =============================================================================
# 8. STREAM CONFIG - ALLOW_NONE SEMANTICS
# =============================================================================

class TestStreamConfigAllowNone:
    """Test allow_none su StreamConfig.from_yaml()."""

    def test_allow_none_true_includes_none_values(self, stream_context):
        """allow_none=True include campi con valore None."""
        yaml_data = {
            'dephase': None,
            'time_mode': None,
        }
        config = StreamConfig.from_yaml(
            yaml_data, context=stream_context, allow_none=True
        )
        assert config.dephase is None
        assert config.time_mode is None

    def test_allow_none_false_excludes_none_values(self, stream_context):
        """allow_none=False esclude None -> usa defaults."""
        yaml_data = {
            'dephase': None,
            'time_mode': None,
            'time_scale': 3.0,  # non-None, incluso
        }
        config = StreamConfig.from_yaml(
            yaml_data, context=stream_context, allow_none=False
        )
        # dephase e time_mode esclusi -> defaults
        assert config.dephase is False
        assert config.time_mode == 'absolute'
        # time_scale incluso
        assert config.time_scale == 3.0

    def test_allow_none_default_is_true(self, stream_context):
        """Il default di allow_none e' True."""
        yaml_data = {'dephase': None}
        config_default = StreamConfig.from_yaml(yaml_data, context=stream_context)
        config_explicit = StreamConfig.from_yaml(
            yaml_data, context=stream_context, allow_none=True
        )
        assert config_default == config_explicit

    def test_allow_none_false_all_none_uses_defaults(self, stream_context):
        """Tutti None con allow_none=False -> tutti defaults."""
        yaml_data = {
            'dephase': None,
            'range_always_active': None,
            'distribution_mode': None,
            'time_mode': None,
            'time_scale': None,
        }
        config = StreamConfig.from_yaml(
            yaml_data, context=stream_context, allow_none=False
        )
        default = StreamConfig(context=stream_context)
        assert config == default


# =============================================================================
# 9. STREAM CONFIG - TIPI POLIMORFI DI DEPHASE
# =============================================================================

class TestStreamConfigDephaseTypes:
    """Test che dephase accetta tipi diversi come dichiarato nel type hint."""

    def test_dephase_bool(self, stream_context):
        """dephase come bool."""
        config = StreamConfig.from_yaml({'dephase': True}, context=stream_context)
        assert config.dephase is True

    def test_dephase_false(self, stream_context):
        """dephase False (default)."""
        config = StreamConfig.from_yaml({'dephase': False}, context=stream_context)
        assert config.dephase is False

    def test_dephase_dict(self, stream_context):
        """dephase come dict (configurazione per parametro)."""
        dephase_dict = {'volume': 0.8, 'pan': 0.5, 'duration': 1.0}
        config = StreamConfig.from_yaml(
            {'dephase': dephase_dict}, context=stream_context
        )
        assert config.dephase == dephase_dict
        assert config.dephase['volume'] == 0.8

    def test_dephase_int(self, stream_context):
        """dephase come int."""
        config = StreamConfig.from_yaml({'dephase': 1}, context=stream_context)
        assert config.dephase == 1

    def test_dephase_float(self, stream_context):
        """dephase come float (probabilita' uniforme)."""
        config = StreamConfig.from_yaml({'dephase': 0.75}, context=stream_context)
        assert config.dephase == 0.75

    def test_dephase_list(self, stream_context):
        """dephase come list."""
        dephase_list = [0.5, 0.8, 1.0]
        config = StreamConfig.from_yaml(
            {'dephase': dephase_list}, context=stream_context
        )
        assert config.dephase == dephase_list

    def test_dephase_none(self, stream_context):
        """dephase None esplicito (con allow_none=True)."""
        config = StreamConfig.from_yaml(
            {'dephase': None}, context=stream_context, allow_none=True
        )
        assert config.dephase is None

    def test_dephase_empty_dict(self, stream_context):
        """dephase dict vuoto."""
        config = StreamConfig.from_yaml(
            {'dephase': {}}, context=stream_context
        )
        assert config.dephase == {}

    def test_dephase_nested_dict(self, stream_context):
        """dephase con struttura annidata."""
        nested = {'groups': {'output': 0.8, 'grain': 0.5}, 'global': True}
        config = StreamConfig.from_yaml(
            {'dephase': nested}, context=stream_context
        )
        assert config.dephase['groups']['output'] == 0.8


# =============================================================================
# 10. STREAM CONFIG - IMMUTABILITA'
# =============================================================================

class TestStreamConfigFrozen:
    """Test immutabilita' (frozen=True)."""

    def test_cannot_set_dephase(self):
        """dephase non modificabile."""
        config = StreamConfig()
        with pytest.raises(FrozenInstanceError):
            config.dephase = True

    def test_cannot_set_time_mode(self):
        """time_mode non modificabile."""
        config = StreamConfig()
        with pytest.raises(FrozenInstanceError):
            config.time_mode = 'normalized'

    def test_cannot_set_context(self, stream_context):
        """context non modificabile dopo creazione."""
        config = StreamConfig(context=stream_context)
        with pytest.raises(FrozenInstanceError):
            config.context = None

    def test_cannot_delete_field(self):
        """Cancellazione campo solleva FrozenInstanceError."""
        config = StreamConfig()
        with pytest.raises(FrozenInstanceError):
            del config.dephase

    def test_cannot_add_new_field(self):
        """Aggiunta nuovo campo solleva FrozenInstanceError."""
        config = StreamConfig()
        with pytest.raises(FrozenInstanceError):
            config.extra = 'nope'


# =============================================================================
# 11. INTEGRAZIONE STREAMCONTEXT + STREAMCONFIG
# =============================================================================

class TestIntegration:
    """Test integrazione tra StreamContext e StreamConfig."""

    def test_full_pipeline_yaml_to_config(self, sample_dur):
        """Pipeline completo: YAML -> StreamContext -> StreamConfig."""
        yaml_data = {
            'stream_id': 'grain_stream_01',
            'onset': 2.0,
            'duration': 15.0,
            'sample': 'forest.wav',
            'dephase': {'volume': 0.9, 'pan': 0.5},
            'range_always_active': True,
            'time_mode': 'normalized',
            'time_scale': 0.8,
        }

        context = StreamContext.from_yaml(yaml_data, sample_dur_sec=sample_dur)
        config = StreamConfig.from_yaml(yaml_data, context=context)

        # Context corretto
        assert config.context.stream_id == 'grain_stream_01'
        assert config.context.duration == 15.0
        assert config.context.sample_dur_sec == sample_dur

        # Config corretto
        assert config.dephase == {'volume': 0.9, 'pan': 0.5}
        assert config.range_always_active is True
        assert config.time_mode == 'normalized'

    def test_shared_config_different_contexts(self, sample_dur):
        """Due context diversi possono usare la stessa config di processo."""
        ctx1 = StreamContext(
            stream_id='s1', onset=0.0, duration=5.0,
            sample='a.wav', sample_dur_sec=sample_dur
        )
        ctx2 = StreamContext(
            stream_id='s2', onset=5.0, duration=10.0,
            sample='b.wav', sample_dur_sec=sample_dur
        )

        yaml_process = {'dephase': True, 'time_mode': 'normalized'}

        config1 = StreamConfig.from_yaml(yaml_process, context=ctx1)
        config2 = StreamConfig.from_yaml(yaml_process, context=ctx2)

        # Stessi parametri di processo
        assert config1.dephase == config2.dephase
        assert config1.time_mode == config2.time_mode

        # Contesti diversi
        assert config1.context.stream_id != config2.context.stream_id
        assert config1 != config2

    def test_context_accessible_through_config(self, stream_context):
        """I dati del context sono accessibili via config."""
        config = StreamConfig(context=stream_context)

        assert config.context.stream_id == 'stream_01'
        assert config.context.sample == 'water.wav'
        assert config.context.sample_dur_sec == 5.0

    def test_multiple_streams_same_sample(self, sample_dur):
        """Stream multipli con lo stesso sample, onset diversi."""
        contexts = []
        for i in range(3):
            ctx = StreamContext.from_yaml(
                {'stream_id': f's{i}', 'onset': float(i * 5),
                 'duration': 5.0, 'sample': 'pge.shared.wav'},
                sample_dur_sec=sample_dur
            )
            contexts.append(ctx)

        configs = [
            StreamConfig.from_yaml({'dephase': True}, context=ctx)
            for ctx in contexts
        ]

        assert len(configs) == 3
        assert all(c.context.sample == 'pge.shared.wav' for c in configs)
        onsets = [c.context.onset for c in configs]
        assert onsets == [0.0, 5.0, 10.0]


# =============================================================================
# 12. EQUALITY E HASH (frozen dataclass)
# =============================================================================

class TestEqualityAndHash:
    """Test __eq__ e __hash__ generati da frozen dataclass."""

    def test_streamcontext_equality(self, sample_dur):
        """Due StreamContext con stessi valori sono uguali."""
        data = {
            'stream_id': 's1', 'onset': 0.0,
            'duration': 5.0, 'sample': 'a.wav'
        }
        ctx1 = StreamContext.from_yaml(data, sample_dur_sec=sample_dur)
        ctx2 = StreamContext.from_yaml(data, sample_dur_sec=sample_dur)
        assert ctx1 == ctx2

    def test_streamcontext_inequality(self, sample_dur):
        """StreamContext con valori diversi non sono uguali."""
        data1 = {
            'stream_id': 's1', 'onset': 0.0,
            'duration': 5.0, 'sample': 'a.wav'
        }
        data2 = {
            'stream_id': 's2', 'onset': 1.0,
            'duration': 5.0, 'sample': 'a.wav'
        }
        ctx1 = StreamContext.from_yaml(data1, sample_dur_sec=sample_dur)
        ctx2 = StreamContext.from_yaml(data2, sample_dur_sec=sample_dur)
        assert ctx1 != ctx2

    def test_streamcontext_hashable(self, sample_dur):
        """StreamContext e' hashable (frozen) e usabile in set/dict."""
        data = {
            'stream_id': 's1', 'onset': 0.0,
            'duration': 5.0, 'sample': 'a.wav'
        }
        ctx1 = StreamContext.from_yaml(data, sample_dur_sec=sample_dur)
        ctx2 = StreamContext.from_yaml(data, sample_dur_sec=sample_dur)

        context_set = {ctx1, ctx2}
        assert len(context_set) == 1

    def test_streamconfig_equality_with_same_context(self, stream_context):
        """Due StreamConfig identici sono uguali."""
        config1 = StreamConfig(dephase=True, context=stream_context)
        config2 = StreamConfig(dephase=True, context=stream_context)
        assert config1 == config2

    def test_streamconfig_inequality(self, stream_context):
        """StreamConfig con valori diversi non sono uguali."""
        config1 = StreamConfig(dephase=True, context=stream_context)
        config2 = StreamConfig(dephase=False, context=stream_context)
        assert config1 != config2

    def test_streamconfig_hashable(self):
        """StreamConfig e' hashable (se tutti i campi lo sono)."""
        # Con dephase=False (hashable), il config e' hashable
        config = StreamConfig(dephase=False)
        config_set = {config}
        assert len(config_set) == 1

    def test_streamconfig_with_dict_dephase_not_hashable(self, stream_context):
        """StreamConfig con dephase dict non e' hashable (dict non hashable)."""
        config = StreamConfig(dephase={'volume': 0.8}, context=stream_context)
        with pytest.raises(TypeError):
            hash(config)


# =============================================================================
# 13. EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Test casi limite."""

    def test_streamcontext_empty_yaml(self, sample_dur):
        """YAML vuoto -> TypeError (campi obbligatori senza default)."""
        with pytest.raises(TypeError):
            StreamContext.from_yaml({}, sample_dur_sec=sample_dur)

    def test_streamcontext_zero_values(self, sample_dur):
        """Valori zero sono validi."""
        data = {
            'stream_id': 's0',
            'onset': 0.0,
            'duration': 0.0,
            'sample': 'zero.wav',
        }
        ctx = StreamContext.from_yaml(data, sample_dur_sec=0.0)
        assert ctx.onset == 0.0
        assert ctx.duration == 0.0
        assert ctx.sample_dur_sec == 0.0

    def test_streamcontext_negative_values(self, sample_dur):
        """Valori negativi sono accettati (nessuna validazione nel dataclass)."""
        data = {
            'stream_id': 's_neg',
            'onset': -1.0,
            'duration': -5.0,
            'sample': 'neg.wav',
        }
        ctx = StreamContext.from_yaml(data, sample_dur_sec=sample_dur)
        assert ctx.onset == -1.0

    def test_streamconfig_extreme_time_scale(self, stream_context):
        """time_scale con valori estremi."""
        config = StreamConfig.from_yaml(
            {'time_scale': 0.001}, context=stream_context
        )
        assert config.time_scale == 0.001

        config2 = StreamConfig.from_yaml(
            {'time_scale': 1000.0}, context=stream_context
        )
        assert config2.time_scale == 1000.0

    def test_streamcontext_unicode_stream_id(self, sample_dur):
        """stream_id con caratteri unicode."""
        data = {
            'stream_id': 'flusso_acqua_01',
            'onset': 0.0,
            'duration': 5.0,
            'sample': 'acqua.wav',
        }
        ctx = StreamContext.from_yaml(data, sample_dur_sec=sample_dur)
        assert ctx.stream_id == 'flusso_acqua_01'

    def test_streamcontext_long_sample_name(self, sample_dur):
        """Sample con percorso lungo."""
        long_path = '/very/long/path/to/samples/directory/sound_file_01.wav'
        data = {
            'stream_id': 's1',
            'onset': 0.0,
            'duration': 5.0,
            'sample': long_path,
        }
        ctx = StreamContext.from_yaml(data, sample_dur_sec=sample_dur)
        assert ctx.sample == long_path

    def test_streamconfig_none_context_default(self):
        """StreamConfig senza context ha context=None di default."""
        config = StreamConfig()
        assert config.context is None

    def test_from_yaml_with_boolean_like_values(self, stream_context):
        """Valori che sembrano booleani ma sono numerici."""
        yaml_data = {
            'range_always_active': 1,   # truthy int
            'time_scale': 0,            # falsy int
        }
        config = StreamConfig.from_yaml(yaml_data, context=stream_context)
        assert config.range_always_active == 1
        assert config.time_scale == 0


# =============================================================================
# 14. PARAMETRIZED TESTS
# =============================================================================

class TestParametrized:
    """Test parametrizzati per copertura sistematica."""

    @pytest.mark.parametrize("time_mode", ['absolute', 'normalized'])
    def test_valid_time_modes(self, time_mode, stream_context):
        """Entrambi i time_mode funzionano."""
        config = StreamConfig.from_yaml(
            {'time_mode': time_mode}, context=stream_context
        )
        assert config.time_mode == time_mode

    @pytest.mark.parametrize("dist_mode", ['uniform', 'gaussian', 'custom'])
    def test_distribution_modes(self, dist_mode, stream_context):
        """Diversi distribution_mode accettati."""
        config = StreamConfig.from_yaml(
            {'distribution_mode': dist_mode}, context=stream_context
        )
        assert config.distribution_mode == dist_mode

    @pytest.mark.parametrize("scale", [0.01, 0.5, 1.0, 2.0, 10.0, 100.0])
    def test_various_time_scales(self, scale, stream_context):
        """Vari valori di time_scale."""
        config = StreamConfig.from_yaml(
            {'time_scale': scale}, context=stream_context
        )
        assert config.time_scale == scale

    @pytest.mark.parametrize("onset,duration", [
        (0.0, 1.0),
        (0.5, 10.0),
        (100.0, 0.001),
        (0.0, 300.0),
    ])
    def test_various_context_timing(self, onset, duration, sample_dur):
        """Varie combinazioni onset/duration per StreamContext."""
        data = {
            'stream_id': 'param_test',
            'onset': onset,
            'duration': duration,
            'sample': 'test.wav',
        }
        ctx = StreamContext.from_yaml(data, sample_dur_sec=sample_dur)
        assert ctx.onset == onset
        assert ctx.duration == duration

    @pytest.mark.parametrize("dephase_val,expected_type", [
        (True, bool),
        (False, bool),
        (0.5, float),
        (1, int),
        ({}, dict),
        ([], list),
        ({'vol': 0.8}, dict),
        ([0.1, 0.9], list),
    ])
    def test_dephase_type_preservation(self, dephase_val, expected_type, stream_context):
        """Il tipo del dephase viene preservato."""
        config = StreamConfig.from_yaml(
            {'dephase': dephase_val}, context=stream_context
        )
        assert isinstance(config.dephase, expected_type)


# =============================================================================
# 15. TYPE HINT ANNOTATION BUG
# =============================================================================

class TestTypeHintAnnotation:
    """
    Documenta il type hint errato in StreamContext.from_yaml.
    
    Il metodo dichiara -> 'StreamConfig' ma ritorna StreamContext.
    Questo test verifica il comportamento REALE (corretto) e
    documenta l'annotazione imprecisa.
    """

    def test_from_yaml_returns_streamcontext_not_streamconfig(self, sample_dur):
        """
        StreamContext.from_yaml dichiara -> 'StreamConfig' nel type hint
        ma ritorna correttamente un StreamContext.
        
        BUG NOTO: annotazione type hint errata.
        """
        data = {
            'stream_id': 's1',
            'onset': 0.0,
            'duration': 5.0,
            'sample': 'test.wav',
        }
        result = StreamContext.from_yaml(data, sample_dur_sec=sample_dur)

        # Il comportamento REALE e' corretto:
        assert isinstance(result, StreamContext)
        assert not isinstance(result, StreamConfig)


# =============================================================================
# 16. REPR (frozen dataclass genera __repr__)
# =============================================================================

class TestRepr:
    """Test __repr__ generato automaticamente."""

    def test_streamcontext_repr_contains_fields(self, stream_context):
        """repr contiene i valori dei campi."""
        r = repr(stream_context)
        assert 'stream_01' in r
        assert 'water.wav' in r
        assert 'StreamContext' in r

    def test_streamconfig_repr_contains_fields(self):
        """repr contiene i valori di default."""
        config = StreamConfig()
        r = repr(config)
        assert 'StreamConfig' in r
        assert 'absolute' in r
        assert 'uniform' in r

    def test_streamconfig_repr_with_context(self, stream_context):
        """repr include il context annidato."""
        config = StreamConfig(context=stream_context)
        r = repr(config)
        assert 'stream_01' in r


# =============================================================================
# 17. RNG_GROUP / RNG_ID (issue #169)
# =============================================================================

class TestRngGroup:
    """Identità RNG condivisibile fra stream (issue #169).

    `rng_group` è opzionale: assente → `rng_id` coincide con `stream_id`
    (derivazione hash identica a prima, retrocompatibilità bit-per-bit);
    presente → `rng_id` è il nome del gruppo, così stream diversi possono
    pescare la stessa sequenza pseudo-casuale.
    """

    def test_default_rng_group_is_none(self, sample_dur):
        ctx = StreamContext(
            stream_id='s1', onset=0.0, duration=1.0,
            sample='a.wav', sample_dur_sec=sample_dur,
        )
        assert ctx.rng_group is None

    def test_rng_id_falls_back_to_stream_id(self, sample_dur):
        """Senza rng_group l'identità RNG resta lo stream_id."""
        ctx = StreamContext(
            stream_id='s1', onset=0.0, duration=1.0,
            sample='a.wav', sample_dur_sec=sample_dur,
        )
        assert ctx.rng_id == 's1'

    def test_rng_id_uses_rng_group_when_set(self, sample_dur):
        ctx = StreamContext(
            stream_id='s1', onset=0.0, duration=1.0,
            sample='a.wav', sample_dur_sec=sample_dur,
            rng_group='cugini',
        )
        assert ctx.rng_id == 'cugini'

    def test_from_yaml_reads_rng_group(self, full_yaml_context, sample_dur):
        """from_yaml legge rng_group dal dict per-stream."""
        data = dict(full_yaml_context, rng_group='cugini')
        ctx = StreamContext.from_yaml(data, sample_dur_sec=sample_dur)
        assert ctx.rng_group == 'cugini'
        assert ctx.rng_id == 'cugini'

    def test_from_yaml_without_key_defaults_none(self, full_yaml_context, sample_dur):
        ctx = StreamContext.from_yaml(full_yaml_context, sample_dur_sec=sample_dur)
        assert ctx.rng_group is None
        assert ctx.rng_id == ctx.stream_id

    def test_same_rng_group_same_rng_id_across_streams(self, sample_dur):
        """Due stream con lo stesso rng_group condividono l'identità RNG."""
        a = StreamContext(
            stream_id='cugini_1', onset=0.0, duration=1.0,
            sample='a.wav', sample_dur_sec=sample_dur, rng_group='cugini',
        )
        b = StreamContext(
            stream_id='cugini_2', onset=0.0, duration=1.0,
            sample='a.wav', sample_dur_sec=sample_dur, rng_group='cugini',
        )
        assert a.rng_id == b.rng_id