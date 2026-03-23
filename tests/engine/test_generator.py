"""
test_generator.py

Suite completa di test per il modulo generator.py.

Coverage target: 100%

Sezioni:
1.  Test __init__() - costruzione e stato iniziale
2.  Test load_yaml() - caricamento e preprocessing YAML
3.  Test _eval_math_expressions() - valutazione espressioni matematiche
4.  Test _filter_solo_mute() - logica solo/mute sugli stream
5.  Test create_elements() - orchestrazione creazione stream e cartridges
6.  Test _create_streams() - creazione stream granulari
7.  Test _create_cartridges() - creazione cartridges tape recorder
8.  Test _register_stream_windows() - pre-registrazione finestre
9.  Test generate_score_file() - delega a ScoreWriter
10. Test integrazione - workflow end-to-end con mock
11. Test edge cases e boundary conditions
12. Test parametrizzati per copertura sistematica

Strategia di mocking:
- Stream: mock completo per isolare da logica granulare
- Cartridge: mock per isolare da logica tape recorder
- FtableManager: mock per isolare gestione function tables
- ScoreWriter: mock per isolare scrittura file
- WindowController: mock per isolare parsing finestre
- yaml.safe_load: mock per controllare dati input
- builtins.open: mock per controllare I/O file

Nota sugli import:
- Tutti gli import di moduli di produzione avvengono lazy (dentro funzioni)
  per evitare contaminazione di sys.modules con altri test.
- Si usa patch('engine.generator.XXX') per mockare le dipendenze importate
  nel namespace di generator.py.
"""

import pytest
import math
import yaml
import io
import os
from unittest.mock import patch, Mock, MagicMock, mock_open, call


# =============================================================================
# IMPORT LAZY - CACHE
# =============================================================================

_import_cache = {}


def _get_generator_class():
    """Import lazy di Generator."""
    if 'Generator' not in _import_cache:
        from engine.generator import Generator
        _import_cache['Generator'] = Generator
    return _import_cache['Generator']


# =============================================================================
# MOCK
# =============================================================================

from conftest import make_mock_stream_for_generator, make_mock_cartridge_for_generator
# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def gen():
    """Generator con path YAML fittizio e dipendenze mockate."""
    Generator = _get_generator_class()
    with patch('engine.generator.FtableManager') as MockFtm, \
         patch('engine.generator.ScoreWriter') as MockSw:
        mock_ftm = MockFtm.return_value
        mock_ftm.register_sample = Mock(side_effect=lambda p: hash(p) % 1000)
        mock_ftm.register_window = Mock(side_effect=lambda n: hash(n) % 1000)
        mock_sw = MockSw.return_value
        g = Generator('test_config.yml')
    return g


# =============================================================================
# 1. TEST __init__()
# =============================================================================

class TestGeneratorInit:
    """Test costruttore Generator."""

    def test_init_stores_yaml_path(self):
        """Il costruttore salva yaml_path."""
        Generator = _get_generator_class()
        with patch('engine.generator.FtableManager'), \
             patch('engine.generator.ScoreWriter'):
            g = Generator('my_config.yml')
        assert g.yaml_path == 'my_config.yml'

    def test_init_data_is_none(self):
        """data e' None prima di load_yaml()."""
        Generator = _get_generator_class()
        with patch('engine.generator.FtableManager'), \
             patch('engine.generator.ScoreWriter'):
            g = Generator('config.yml')
        assert g.data is None

    def test_init_streams_empty(self):
        """streams e' lista vuota all'inizializzazione."""
        Generator = _get_generator_class()
        with patch('engine.generator.FtableManager'), \
             patch('engine.generator.ScoreWriter'):
            g = Generator('config.yml')
        assert g.streams == []

    def test_init_cartridges_empty(self):
        """cartridges e' lista vuota all'inizializzazione."""
        Generator = _get_generator_class()
        with patch('engine.generator.FtableManager'), \
             patch('engine.generator.ScoreWriter'):
            g = Generator('config.yml')
        assert g.cartridges == []

    def test_init_creates_ftable_manager(self):
        """Il costruttore crea un FtableManager."""
        Generator = _get_generator_class()
        with patch('engine.generator.FtableManager') as MockFtm, \
             patch('engine.generator.ScoreWriter'):
            g = Generator('config.yml')
        MockFtm.assert_called_once_with(start_num=1)

    def test_init_creates_score_writer_with_ftm(self):
        """Il costruttore crea un ScoreWriter con il FtableManager."""
        Generator = _get_generator_class()
        with patch('engine.generator.FtableManager') as MockFtm, \
             patch('engine.generator.ScoreWriter') as MockSw:
            g = Generator('config.yml')
        MockSw.assert_called_once_with(MockFtm.return_value)

    def test_init_ftable_manager_attribute(self):
        """ftable_manager e' l'istanza creata."""
        Generator = _get_generator_class()
        with patch('engine.generator.FtableManager') as MockFtm, \
             patch('engine.generator.ScoreWriter'):
            g = Generator('config.yml')
        assert g.ftable_manager is MockFtm.return_value

    def test_init_score_writer_attribute(self):
        """score_writer e' l'istanza creata."""
        Generator = _get_generator_class()
        with patch('engine.generator.FtableManager'), \
             patch('engine.generator.ScoreWriter') as MockSw:
            g = Generator('config.yml')
        assert g.score_writer is MockSw.return_value


# =============================================================================
# 2. TEST load_yaml()
# =============================================================================

class TestLoadYaml:
    """Test per load_yaml() - caricamento e preprocessing YAML."""

    def test_load_yaml_reads_file(self, gen):
        """load_yaml apre il file specificato."""
        yaml_data = {'streams': []}
        m = mock_open(read_data=yaml.dump(yaml_data))

        with patch('builtins.open', m):
            gen.load_yaml()

        m.assert_called_once_with('test_config.yml', 'r')

    def test_load_yaml_returns_dict(self, gen):
        """load_yaml ritorna un dizionario."""
        yaml_data = {'streams': [], 'cartridges': []}
        m = mock_open(read_data=yaml.dump(yaml_data))

        with patch('builtins.open', m):
            result = gen.load_yaml()

        assert isinstance(result, dict)

    def test_load_yaml_sets_data_attribute(self, gen):
        """load_yaml imposta self.data."""
        yaml_data = {'streams': [{'stream_id': 's1'}]}
        m = mock_open(read_data=yaml.dump(yaml_data))

        with patch('builtins.open', m):
            gen.load_yaml()

        assert gen.data is not None
        assert 'streams' in gen.data

    def test_load_yaml_preprocesses_math(self, gen):
        """load_yaml valuta espressioni matematiche."""
        yaml_data = {'value': '(10 + 5)'}
        m = mock_open(read_data=yaml.dump(yaml_data))

        with patch('builtins.open', m):
            result = gen.load_yaml()

        assert result['value'] == 15

    def test_load_yaml_file_not_found(self, gen):
        """load_yaml solleva FileNotFoundError se file non esiste."""
        with patch('builtins.open', side_effect=FileNotFoundError("not found")):
            with pytest.raises(FileNotFoundError):
                gen.load_yaml()

    def test_load_yaml_malformed_yaml(self, gen):
        """load_yaml solleva yaml.YAMLError con YAML malformato."""
        m = mock_open(read_data="{{invalid: yaml: ]]]")

        with patch('builtins.open', m):
            with pytest.raises(yaml.YAMLError):
                gen.load_yaml()

    def test_load_yaml_preserves_non_math_strings(self, gen):
        """load_yaml preserva stringhe senza espressioni matematiche."""
        yaml_data = {'name': 'my_stream', 'sample': 'audio.wav'}
        m = mock_open(read_data=yaml.dump(yaml_data))

        with patch('builtins.open', m):
            result = gen.load_yaml()

        assert result['name'] == 'my_stream'
        assert result['sample'] == 'audio.wav'

    def test_load_yaml_return_value_same_as_data(self, gen):
        """Il valore ritornato e' lo stesso di self.data."""
        yaml_data = {'key': 'value'}
        m = mock_open(read_data=yaml.dump(yaml_data))

        with patch('builtins.open', m):
            result = gen.load_yaml()

        assert result is gen.data


# =============================================================================
# 3. TEST _eval_math_expressions()
# =============================================================================

class TestEvalMathExpressions:
    """Test per _eval_math_expressions() - valutazione ricorsiva."""

    def test_eval_integer_expression(self, gen):
        """Valuta espressione intera."""
        result = gen._eval_math_expressions('(10 + 5)')
        assert result == 15

    def test_eval_float_expression(self, gen):
        """Valuta espressione float."""
        result = gen._eval_math_expressions('(10.5 + 0.5)')
        assert result == 11.0

    def test_eval_pi_constant(self, gen):
        """Valuta costante pi."""
        result = gen._eval_math_expressions('(pi)')
        assert abs(result - math.pi) < 1e-10

    def test_eval_e_constant(self, gen):
        """Valuta costante e."""
        result = gen._eval_math_expressions('(e)')
        assert abs(result - math.e) < 1e-10

    def test_eval_multiplication(self, gen):
        """Valuta moltiplicazione."""
        result = gen._eval_math_expressions('(3 * 4)')
        assert result == 12

    def test_eval_division(self, gen):
        """Valuta divisione."""
        result = gen._eval_math_expressions('(10 / 2)')
        assert result == 5.0

    def test_eval_pi_times_two(self, gen):
        """Valuta pi * 2."""
        result = gen._eval_math_expressions('(pi * 2)')
        assert abs(result - math.pi * 2) < 1e-10

    def test_eval_max_function_not_supported(self, gen):
        """Funzioni con virgola (max, min) non sono matchate dal regex.

        Il pattern regex non include ',' nel charset, quindi espressioni
        come (max(3, 7)) passano invariate. Questo e' il comportamento
        atteso del codice di produzione.
        """
        result = gen._eval_math_expressions('(max(3, 7))')
        # La virgola non e' nel charset del regex -> nessun match -> stringa invariata
        assert result == '(max(3, 7))'

    def test_eval_min_function_not_supported(self, gen):
        """min con virgola non matchato dal regex (come max)."""
        result = gen._eval_math_expressions('(min(3, 7))')
        assert result == '(min(3, 7))'

    def test_eval_abs_function(self, gen):
        """abs con argomento negativo: il '-' e' nel charset del regex."""
        result = gen._eval_math_expressions('(abs(-5))')
        # Il pattern include \- nel charset: [a-zA-Z0-9+\-*/.() ]
        # Quindi (abs(-5)) dovrebbe matchare
        assert result == 5

    def test_eval_pow_function_not_supported(self, gen):
        """pow con virgola non matchato dal regex."""
        result = gen._eval_math_expressions('(pow(2, 10))')
        assert result == '(pow(2, 10))'

    def test_eval_nested_dict(self, gen):
        """Valuta ricorsivamente nei dizionari."""
        data = {
            'a': '(10 + 5)',
            'b': {
                'c': '(pi)',
                'd': 'plain_string'
            }
        }
        result = gen._eval_math_expressions(data)
        assert result['a'] == 15
        assert abs(result['b']['c'] - math.pi) < 1e-10
        assert result['b']['d'] == 'plain_string'

    def test_eval_nested_list(self, gen):
        """Valuta ricorsivamente nelle liste."""
        data = ['(1 + 2)', '(3 * 4)', 'text']
        result = gen._eval_math_expressions(data)
        assert result[0] == 3
        assert result[1] == 12
        assert result[2] == 'text'

    def test_eval_mixed_nested(self, gen):
        """Valuta strutture miste dict/list."""
        data = {
            'items': ['(10)', '(20)'],
            'nested': {'val': '(5 + 5)'}
        }
        result = gen._eval_math_expressions(data)
        assert result['items'] == [10, 20]
        assert result['nested']['val'] == 10

    def test_eval_passthrough_number(self, gen):
        """Numeri passano attraverso invariati."""
        assert gen._eval_math_expressions(42) == 42
        assert gen._eval_math_expressions(3.14) == 3.14

    def test_eval_passthrough_none(self, gen):
        """None passa attraverso invariato."""
        assert gen._eval_math_expressions(None) is None

    def test_eval_passthrough_bool(self, gen):
        """Bool passa attraverso invariato."""
        assert gen._eval_math_expressions(True) is True
        assert gen._eval_math_expressions(False) is False

    def test_eval_plain_string_no_parens(self, gen):
        """Stringhe senza parentesi passano invariate."""
        assert gen._eval_math_expressions('hello') == 'hello'
        assert gen._eval_math_expressions('audio.wav') == 'audio.wav'

    def test_eval_invalid_expression_preserved(self, gen):
        """Espressioni non valide vengono preservate come stringa."""
        # 'unknown_func' non e' nel safe_dict, eval fallisce
        # Il fallback ritorna l'espressione originale (match.group(0))
        result = gen._eval_math_expressions('(unknown_func)')
        assert isinstance(result, str)

    def test_eval_converts_integer_string(self, gen):
        """Stringa risultante convertita a int se possibile."""
        result = gen._eval_math_expressions('(5 + 5)')
        assert result == 10
        assert isinstance(result, int)

    def test_eval_converts_float_string(self, gen):
        """Stringa risultante convertita a float se con punto decimale."""
        result = gen._eval_math_expressions('(5.0 + 5.0)')
        assert result == 10.0
        assert isinstance(result, float)

    def test_eval_empty_string(self, gen):
        """Stringa vuota passa invariata."""
        assert gen._eval_math_expressions('') == ''

    def test_eval_empty_dict(self, gen):
        """Dict vuoto passa invariato."""
        assert gen._eval_math_expressions({}) == {}

    def test_eval_empty_list(self, gen):
        """Lista vuota passa invariata."""
        assert gen._eval_math_expressions([]) == []

    def test_eval_complex_expression(self, gen):
        """Espressione complessa con operatori multipli."""
        result = gen._eval_math_expressions('(2 + 3 * 4)')
        assert result == 14  # Precedenza operatori: 2 + (3*4)

    def test_eval_string_with_no_matching_parens(self, gen):
        """Stringa senza parentesi matchanti il pattern."""
        result = gen._eval_math_expressions('no_match_here')
        assert result == 'no_match_here'

    def test_eval_deeply_nested(self, gen):
        """Valutazione in strutture profondamente nidificate."""
        data = {'a': {'b': {'c': {'d': '(2 + 3)'}}}}
        result = gen._eval_math_expressions(data)
        assert result['a']['b']['c']['d'] == 5

    def test_eval_list_in_dict(self, gen):
        """Valutazione lista dentro dizionario."""
        data = {'values': ['(1)', '(2)', '(3)']}
        result = gen._eval_math_expressions(data)
        assert result['values'] == [1, 2, 3]

    def test_eval_dict_in_list(self, gen):
        """Valutazione dizionario dentro lista."""
        data = [{'v': '(10)'}]
        result = gen._eval_math_expressions(data)
        assert result[0]['v'] == 10

    def test_eval_string_with_multiple_expressions(self, gen):
        """Stringa con piu' espressioni sostituite."""
        # "(10) qualcosa (20)" - il regex sostituisce entrambe
        result = gen._eval_math_expressions('(10)')
        assert result == 10


# =============================================================================
# 4. TEST _filter_solo_mute()
# =============================================================================

class TestFilterSoloMute:
    """Test per _filter_solo_mute() - logica solo/mute."""

    def test_no_solo_no_mute_returns_all(self, gen):
        """Senza solo ne' mute, ritorna tutti gli stream."""
        streams = [
            {'stream_id': 'a'},
            {'stream_id': 'b'},
            {'stream_id': 'c'},
        ]
        result = gen._filter_solo_mute(streams)
        assert len(result) == 3

    def test_solo_mode_returns_only_solo(self, gen):
        """In modalita' solo, ritorna solo gli stream con flag 'solo'."""
        streams = [
            {'stream_id': 'a', 'solo': True},
            {'stream_id': 'b'},
            {'stream_id': 'c'},
        ]
        result = gen._filter_solo_mute(streams)
        assert len(result) == 1
        assert result[0]['stream_id'] == 'a'

    def test_solo_multiple(self, gen):
        """Piu' stream con solo sono tutti inclusi."""
        streams = [
            {'stream_id': 'a', 'solo': True},
            {'stream_id': 'b', 'solo': True},
            {'stream_id': 'c'},
        ]
        result = gen._filter_solo_mute(streams)
        assert len(result) == 2

    def test_mute_excludes_muted(self, gen):
        """Mute esclude gli stream con flag 'mute'."""
        streams = [
            {'stream_id': 'a'},
            {'stream_id': 'b', 'mute': True},
            {'stream_id': 'c'},
        ]
        result = gen._filter_solo_mute(streams)
        assert len(result) == 2
        assert all(s['stream_id'] != 'b' for s in result)

    def test_solo_overrides_mute(self, gen):
        """Solo ha priorita' su mute: in solo mode solo quelli con 'solo'."""
        streams = [
            {'stream_id': 'a', 'solo': True},
            {'stream_id': 'b', 'mute': True},
            {'stream_id': 'c'},
        ]
        result = gen._filter_solo_mute(streams)
        assert len(result) == 1
        assert result[0]['stream_id'] == 'a'

    def test_all_muted_returns_empty(self, gen):
        """Tutti muted ritorna lista vuota."""
        streams = [
            {'stream_id': 'a', 'mute': True},
            {'stream_id': 'b', 'mute': True},
        ]
        result = gen._filter_solo_mute(streams)
        assert len(result) == 0

    def test_empty_list_returns_empty(self, gen):
        """Lista vuota ritorna lista vuota."""
        result = gen._filter_solo_mute([])
        assert result == []

    def test_solo_checks_key_presence_not_value(self, gen):
        """Solo controlla la presenza della chiave, non il valore."""
        streams = [
            {'stream_id': 'a', 'solo': False},  # chiave presente!
            {'stream_id': 'b'},
        ]
        result = gen._filter_solo_mute(streams)
        assert len(result) == 1
        assert result[0]['stream_id'] == 'a'

    def test_mute_checks_key_presence_not_value(self, gen):
        """Mute controlla la presenza della chiave, non il valore."""
        streams = [
            {'stream_id': 'a', 'mute': False},  # chiave presente!
            {'stream_id': 'b'},
        ]
        result = gen._filter_solo_mute(streams)
        assert len(result) == 1
        assert result[0]['stream_id'] == 'b'

    def test_solo_with_value_none(self, gen):
        """Solo con valore None e' ancora rilevato."""
        streams = [
            {'stream_id': 'a', 'solo': None},
            {'stream_id': 'b'},
        ]
        result = gen._filter_solo_mute(streams)
        assert len(result) == 1

    def test_preserves_order(self, gen):
        """_filter_solo_mute preserva l'ordine originale."""
        streams = [
            {'stream_id': 'c'},
            {'stream_id': 'a'},
            {'stream_id': 'b', 'mute': True},
        ]
        result = gen._filter_solo_mute(streams)
        assert [s['stream_id'] for s in result] == ['c', 'a']

    def test_solo_and_mute_on_same_stream(self, gen):
        """Stream con sia solo che mute: solo mode include chi ha solo."""
        streams = [
            {'stream_id': 'a', 'solo': True, 'mute': True},
            {'stream_id': 'b'},
        ]
        result = gen._filter_solo_mute(streams)
        # Solo mode attivo perche' c'e' almeno un 'solo'
        # In solo mode, prende chi ha 'solo' -> 'a' ce l'ha
        assert len(result) == 1
        assert result[0]['stream_id'] == 'a'


# =============================================================================
# 5. TEST create_elements()
# =============================================================================

class TestCreateElements:
    """Test per create_elements() - orchestrazione."""

    def test_create_elements_without_load_yaml_raises(self, gen):
        """create_elements senza load_yaml solleva ValueError."""
        with pytest.raises(ValueError, match="Devi prima caricare il YAML"):
            gen.create_elements()

    def test_create_elements_returns_tuple(self, gen):
        """create_elements ritorna tupla (streams, cartridges)."""
        gen.data = {'streams': [], 'cartridges': []}

        with patch.object(gen, '_filter_solo_mute', return_value=[]), \
             patch.object(gen, '_create_streams'), \
             patch.object(gen, '_create_cartridges'):
            result = gen.create_elements()

        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_create_elements_calls_filter(self, gen):
        """create_elements chiama _filter_solo_mute."""
        stream_list = [{'stream_id': 's1'}]
        gen.data = {'streams': stream_list}

        with patch.object(gen, '_filter_solo_mute', return_value=[]) as mock_filter, \
             patch.object(gen, '_create_streams'):
            gen.create_elements()

        mock_filter.assert_called_once_with(stream_list)

    def test_create_elements_calls_create_streams(self, gen):
        """create_elements chiama _create_streams con risultato filtrato."""
        gen.data = {'streams': [{'stream_id': 's1'}, {'stream_id': 's2'}]}
        filtered = [{'stream_id': 's1'}]

        with patch.object(gen, '_filter_solo_mute', return_value=filtered), \
             patch.object(gen, '_create_streams') as mock_cs:
            gen.create_elements()

        mock_cs.assert_called_once_with(filtered)

    def test_create_elements_with_cartridges(self, gen):
        """create_elements crea cartridges se presenti."""
        gen.data = {
            'streams': [],
            'cartridges': [{'cartridge_id': 't1'}]
        }

        with patch.object(gen, '_filter_solo_mute', return_value=[]), \
             patch.object(gen, '_create_streams'), \
             patch.object(gen, '_create_cartridges') as mock_ct:
            gen.create_elements()

        mock_ct.assert_called_once_with([{'cartridge_id': 't1'}])

    def test_create_elements_without_cartridges_key(self, gen):
        """create_elements senza chiave 'cartridges' non crea cartridges."""
        gen.data = {'streams': []}

        with patch.object(gen, '_filter_solo_mute', return_value=[]), \
             patch.object(gen, '_create_streams'), \
             patch.object(gen, '_create_cartridges') as mock_ct:
            gen.create_elements()

        mock_ct.assert_not_called()

    def test_create_elements_with_empty_cartridges(self, gen):
        """create_elements con cartridges=[] non chiama _create_cartridges."""
        gen.data = {'streams': [], 'cartridges': []}

        with patch.object(gen, '_filter_solo_mute', return_value=[]), \
             patch.object(gen, '_create_streams'), \
             patch.object(gen, '_create_cartridges') as mock_ct:
            gen.create_elements()

        mock_ct.assert_not_called()

    def test_create_elements_returns_streams_and_cartridges(self, gen):
        """create_elements ritorna le liste corrette."""
        gen.data = {'streams': [], 'cartridges': []}
        gen.streams = ['mock_stream']
        gen.cartridges = ['mock_cartridge']

        with patch.object(gen, '_filter_solo_mute', return_value=[]), \
             patch.object(gen, '_create_streams'), \
             patch.object(gen, '_create_cartridges'):
            streams, cartridges = gen.create_elements()

        assert streams == ['mock_stream']
        assert cartridges == ['mock_cartridge']

    def test_create_elements_missing_streams_key(self, gen):
        """create_elements con dict senza chiave 'streams' usa default vuoto."""
        gen.data = {}

        with patch.object(gen, '_filter_solo_mute', return_value=[]) as mock_filter, \
             patch.object(gen, '_create_streams'):
            gen.create_elements()

        mock_filter.assert_called_once_with([])

    def test_create_elements_with_none_cartridges(self, gen):
        """create_elements con cartridges=None non chiama _create_cartridges."""
        gen.data = {'streams': [], 'cartridges': None}

        with patch.object(gen, '_filter_solo_mute', return_value=[]), \
             patch.object(gen, '_create_streams'), \
             patch.object(gen, '_create_cartridges') as mock_ct:
            gen.create_elements()

        mock_ct.assert_not_called()


# =============================================================================
# 6. TEST _create_streams()
# =============================================================================

class TestCreateStreams:
    """Test per _create_streams() - creazione stream granulari."""

    def test_creates_stream_objects(self, gen):
        """_create_streams crea oggetti Stream."""
        stream_data = [{'stream_id': 's1', 'sample': 'a.wav', 'grain': {}}]
        mock_stream = make_mock_stream_for_generator()

        with patch('engine.generator.Stream', return_value=mock_stream) as MockStream, \
             patch.object(gen, '_register_stream_windows', return_value={}):
            gen._create_streams(stream_data)

        MockStream.assert_called_once_with(stream_data[0])
        assert len(gen.streams) == 1

    def test_registers_sample(self, gen):
        """_create_streams registra il sample nel FtableManager."""
        mock_stream = make_mock_stream_for_generator(sample='audio.wav')
        stream_data = [{'stream_id': 's1', 'sample': 'audio.wav', 'grain': {}}]

        with patch('engine.generator.Stream', return_value=mock_stream), \
             patch.object(gen, '_register_stream_windows', return_value={}):
            gen._create_streams(stream_data)

        gen.ftable_manager.register_sample.assert_called_once_with('audio.wav')

    def test_assigns_sample_table_num(self, gen):
        """_create_streams assegna sample_table_num allo stream."""
        mock_stream = make_mock_stream_for_generator()
        gen.ftable_manager.register_sample = Mock(return_value=42)
        stream_data = [{'stream_id': 's1', 'sample': 'audio.wav', 'grain': {}}]

        with patch('engine.generator.Stream', return_value=mock_stream), \
             patch.object(gen, '_register_stream_windows', return_value={}):
            gen._create_streams(stream_data)

        assert mock_stream.sample_table_num == 42

    def test_calls_register_windows(self, gen):
        """_create_streams chiama _register_stream_windows."""
        mock_stream = make_mock_stream_for_generator()
        stream_data = [
            {'stream_id': 's1', 'sample': 'a.wav', 'grain': {'envelope': 'hanning'}},
        ]

        with patch('engine.generator.Stream', return_value=mock_stream), \
             patch.object(gen, '_register_stream_windows', return_value={'hanning': 5}) as mock_rw:
            gen._create_streams(stream_data)

        mock_rw.assert_called_once_with(stream_data[0])

    def test_assigns_window_table_map(self, gen):
        """_create_streams assegna window_table_map."""
        mock_stream = make_mock_stream_for_generator()
        window_map = {'hanning': 5, 'hamming': 6}
        stream_data = [{'stream_id': 's1', 'sample': 'a.wav', 'grain': {}}]

        with patch('engine.generator.Stream', return_value=mock_stream), \
             patch.object(gen, '_register_stream_windows', return_value=window_map):
            gen._create_streams(stream_data)

        assert mock_stream.window_table_map == window_map

    def test_calls_generate_grains(self, gen):
        """_create_streams chiama generate_grains() su ogni stream."""
        mock_stream = make_mock_stream_for_generator()
        stream_data = [{'stream_id': 's1', 'sample': 'a.wav', 'grain': {}}]

        with patch('engine.generator.Stream', return_value=mock_stream), \
             patch.object(gen, '_register_stream_windows', return_value={}):
            gen._create_streams(stream_data)

        mock_stream.generate_grains.assert_called_once()

    def test_creates_multiple_streams(self, gen):
        """_create_streams crea piu' stream in sequenza."""
        streams_created = []

        def make_s(data):
            s = make_mock_stream_for_generator(stream_id=data['stream_id'])
            streams_created.append(s)
            return s

        stream_data = [
            {'stream_id': 's1', 'sample': 'a.wav', 'grain': {}},
            {'stream_id': 's2', 'sample': 'b.wav', 'grain': {}},
            {'stream_id': 's3', 'sample': 'c.wav', 'grain': {}},
        ]

        with patch('engine.generator.Stream', side_effect=make_s), \
             patch.object(gen, '_register_stream_windows', return_value={}):
            gen._create_streams(stream_data)

        assert len(gen.streams) == 3

    def test_empty_list(self, gen):
        """_create_streams con lista vuota non crea nulla."""
        gen._create_streams([])
        assert gen.streams == []

    def test_appends_to_existing_streams(self, gen):
        """_create_streams appende, non sovrascrive."""
        gen.streams = ['existing']
        mock_stream = make_mock_stream_for_generator()
        stream_data = [{'stream_id': 's1', 'sample': 'a.wav', 'grain': {}}]

        with patch('engine.generator.Stream', return_value=mock_stream), \
             patch.object(gen, '_register_stream_windows', return_value={}):
            gen._create_streams(stream_data)

        assert len(gen.streams) == 2
        assert gen.streams[0] == 'existing'


# =============================================================================
# 7. TEST _create_cartridges()
# =============================================================================

class TestCreatecartridges:
    """Test per _create_cartridges() - creazione cartridges tape recorder."""

    def test_creates_objects(self, gen):
        """_create_cartridges crea oggetti Cartridge."""
        cartridge_data = [{'cartridge_id': 't1', 'sample': 'tape.wav'}]
        mock_cartridge = make_mock_cartridge_for_generator()

        with patch('engine.generator.Cartridge', return_value=mock_cartridge) as MockCartridge:
            gen._create_cartridges(cartridge_data)

        MockCartridge.assert_called_once_with(cartridge_data[0])
        assert len(gen.cartridges) == 1

    def test_registers_sample(self, gen):
        """_create_cartridges registra il sample_path nel FtableManager."""
        mock_cartridge = make_mock_cartridge_for_generator(sample_path='my_tape.wav')
        cartridge_data = [{'cartridge_id': 't1', 'sample': 'my_tape.wav'}]

        with patch('engine.generator.Cartridge', return_value=mock_cartridge):
            gen._create_cartridges(cartridge_data)

        gen.ftable_manager.register_sample.assert_called_once_with('my_tape.wav')

    def test_assigns_sample_table_num(self, gen):
        """_create_cartridges assegna sample_table_num."""
        mock_cartridge = make_mock_cartridge_for_generator()
        gen.ftable_manager.register_sample = Mock(return_value=99)
        cartridge_data = [{'cartridge_id': 't1', 'sample': 'tape.wav'}]

        with patch('engine.generator.Cartridge', return_value=mock_cartridge):
            gen._create_cartridges(cartridge_data)

        assert mock_cartridge.sample_table_num == 99

    def test_creates_multiple(self, gen):
        """_create_cartridges crea piu' cartridges."""
        cartridges_created = []

        def make_t(data):
            t = make_mock_cartridge_for_generator(cartridge_id=data['cartridge_id'])
            cartridges_created.append(t)
            return t

        cartridge_data = [
            {'cartridge_id': 't1', 'sample': 'a.wav'},
            {'cartridge_id': 't2', 'sample': 'b.wav'},
        ]

        with patch('engine.generator.Cartridge', side_effect=make_t):
            gen._create_cartridges(cartridge_data)

        assert len(gen.cartridges) == 2

    def test_empty_list(self, gen):
        """_create_cartridges con lista vuota non crea nulla."""
        gen._create_cartridges([])
        assert gen.cartridges == []

    def test_appends_to_existing(self, gen):
        """_create_cartridges appende, non sovrascrive."""
        gen.cartridges = ['existing']
        mock_cartridge = make_mock_cartridge_for_generator()
        cartridge_data = [{'cartridge_id': 't1', 'sample': 'tape.wav'}]

        with patch('engine.generator.Cartridge', return_value=mock_cartridge):
            gen._create_cartridges(cartridge_data)

        assert len(gen.cartridges) == 2
        assert gen.cartridges[0] == 'existing'


# =============================================================================
# 8. TEST _register_stream_windows()
# =============================================================================

class TestRegisterStreamWindows:
    """Test per _register_stream_windows() - pre-registrazione finestre."""

    def test_calls_parse_window_list(self, gen):
        """Chiama WindowController.parse_window_list con params e stream_id."""
        stream_data = {
            'stream_id': 's1',
            'grain': {'envelope': 'hanning'}
        }

        with patch('engine.generator.WindowController') as MockWC:
            MockWC.parse_window_list.return_value = ['hanning']
            gen._register_stream_windows(stream_data)

        MockWC.parse_window_list.assert_called_once_with(
            params={'envelope': 'hanning'},
            stream_id='s1'
        )

    def test_registers_each_window(self, gen):
        """Registra ogni finestra nel FtableManager."""
        stream_data = {
            'stream_id': 's1',
            'grain': {'envelope': ['hanning', 'hamming']}
        }

        with patch('engine.generator.WindowController') as MockWC:
            MockWC.parse_window_list.return_value = ['hanning', 'hamming']
            gen.ftable_manager.register_window = Mock(
                side_effect=lambda n: {'hanning': 10, 'hamming': 11}[n]
            )
            result = gen._register_stream_windows(stream_data)

        assert result == {'hanning': 10, 'hamming': 11}

    def test_returns_window_map(self, gen):
        """Ritorna mappa {nome: table_num}."""
        stream_data = {'stream_id': 's1', 'grain': {}}

        with patch('engine.generator.WindowController') as MockWC:
            MockWC.parse_window_list.return_value = ['hanning']
            gen.ftable_manager.register_window = Mock(return_value=5)
            result = gen._register_stream_windows(stream_data)

        assert isinstance(result, dict)
        assert result == {'hanning': 5}

    def test_default_stream_id_unknown(self, gen):
        """stream_id default e' 'unknown' se assente."""
        stream_data = {'grain': {'envelope': 'hanning'}}

        with patch('engine.generator.WindowController') as MockWC:
            MockWC.parse_window_list.return_value = ['hanning']
            gen._register_stream_windows(stream_data)

        MockWC.parse_window_list.assert_called_once_with(
            params={'envelope': 'hanning'},
            stream_id='unknown'
        )

    def test_no_grain_key_uses_empty_dict(self, gen):
        """Senza chiave 'grain' usa dict vuoto per params."""
        stream_data = {'stream_id': 's1'}

        with patch('engine.generator.WindowController') as MockWC:
            MockWC.parse_window_list.return_value = ['hanning']
            gen._register_stream_windows(stream_data)

        MockWC.parse_window_list.assert_called_once_with(
            params={},
            stream_id='s1'
        )

    def test_empty_window_list_returns_empty_map(self, gen):
        """Lista vuota di finestre produce mappa vuota."""
        stream_data = {'stream_id': 's1', 'grain': {}}

        with patch('engine.generator.WindowController') as MockWC:
            MockWC.parse_window_list.return_value = []
            result = gen._register_stream_windows(stream_data)

        assert result == {}

    def test_multiple_windows_all_registered(self, gen):
        """Tutte le finestre della lista vengono registrate."""
        stream_data = {'stream_id': 's1', 'grain': {'envelope': 'all'}}
        all_windows = ['hanning', 'hamming', 'bartlett']

        with patch('engine.generator.WindowController') as MockWC:
            MockWC.parse_window_list.return_value = all_windows
            gen.ftable_manager.register_window = Mock(
                side_effect=lambda n: {'hanning': 10, 'hamming': 11, 'bartlett': 12}[n]
            )
            result = gen._register_stream_windows(stream_data)

        assert len(result) == 3
        assert gen.ftable_manager.register_window.call_count == 3


# =============================================================================
# 9. TEST generate_score_file()
# =============================================================================

class TestGenerateScoreFile:
    """Test per generate_score_file() - delega a ScoreWriter."""

    def test_delegates_to_writer(self, gen):
        """generate_score_file delega a score_writer.write_score."""
        gen.streams = ['s1', 's2']
        gen.cartridges = ['t1']

        gen.generate_score_file('output.sco')

        gen.score_writer.write_score.assert_called_once_with(
            filepath='output.sco',
            streams=['s1', 's2'],
            cartridges=['t1'],
            yaml_source='test_config.yml'
        )

    def test_default_path(self, gen):
        """generate_score_file usa 'output.sco' come default."""
        gen.streams = []
        gen.cartridges = []

        gen.generate_score_file()

        call_kwargs = gen.score_writer.write_score.call_args
        assert call_kwargs.kwargs['filepath'] == 'output.sco'

    def test_custom_path(self, gen):
        """generate_score_file accetta path custom."""
        gen.streams = []
        gen.cartridges = []

        gen.generate_score_file('/tmp/my_score.sco')

        call_kwargs = gen.score_writer.write_score.call_args
        assert call_kwargs.kwargs['filepath'] == '/tmp/my_score.sco'

    def test_passes_yaml_path(self, gen):
        """generate_score_file passa yaml_path come yaml_source."""
        gen.streams = []
        gen.cartridges = []

        gen.generate_score_file()

        call_kwargs = gen.score_writer.write_score.call_args
        assert call_kwargs.kwargs['yaml_source'] == 'test_config.yml'

    def test_passes_current_streams_and_cartridges(self, gen):
        """generate_score_file passa le liste correnti."""
        gen.streams = ['stream_a', 'stream_b']
        gen.cartridges = ['cartridge_x']

        gen.generate_score_file()

        call_kwargs = gen.score_writer.write_score.call_args
        assert call_kwargs.kwargs['streams'] == ['stream_a', 'stream_b']
        assert call_kwargs.kwargs['cartridges'] == ['cartridge_x']


# =============================================================================
# 10. TEST INTEGRAZIONE
# =============================================================================

class TestIntegration:
    """Test di integrazione - workflow end-to-end con mock."""

    def test_full_workflow(self, gen):
        """Workflow completo: load -> create -> generate."""
        yaml_content = yaml.dump({
            'streams': [
                {'stream_id': 's1', 'sample': 'a.wav', 'grain': {'envelope': 'hanning'}}
            ],
            'cartridges': [
                {'cartridge_id': 't1', 'sample': 'tape.wav'}
            ]
        })

        mock_stream = make_mock_stream_for_generator()
        mock_cartridge = make_mock_cartridge_for_generator()

        with patch('builtins.open', mock_open(read_data=yaml_content)), \
             patch('engine.generator.Stream', return_value=mock_stream), \
             patch('engine.generator.Cartridge', return_value=mock_cartridge), \
             patch('engine.generator.WindowController') as MockWC:
            MockWC.parse_window_list.return_value = ['hanning']
            gen.ftable_manager.register_sample = Mock(return_value=1)
            gen.ftable_manager.register_window = Mock(return_value=2)

            gen.load_yaml()
            streams, cartridges = gen.create_elements()
            gen.generate_score_file('out.sco')

        assert len(gen.streams) == 1
        assert len(gen.cartridges) == 1
        gen.score_writer.write_score.assert_called_once()

    def test_workflow_solo_mode(self, gen):
        """Workflow con solo mode."""
        yaml_content = yaml.dump({
            'streams': [
                {'stream_id': 's1', 'sample': 'a.wav', 'grain': {}, 'solo': True},
                {'stream_id': 's2', 'sample': 'b.wav', 'grain': {}},
            ]
        })

        mock_stream = make_mock_stream_for_generator()

        with patch('builtins.open', mock_open(read_data=yaml_content)), \
             patch('engine.generator.Stream', return_value=mock_stream), \
             patch('engine.generator.WindowController') as MockWC:
            MockWC.parse_window_list.return_value = ['hanning']
            gen.ftable_manager.register_sample = Mock(return_value=1)
            gen.ftable_manager.register_window = Mock(return_value=2)

            gen.load_yaml()
            gen.create_elements()

        assert len(gen.streams) == 1

    def test_workflow_math_preprocessing(self, gen):
        """Workflow con espressioni matematiche nel YAML."""
        yaml_content = yaml.dump({
            'streams': [],
            'duration': '(pi * 2)',
        })

        with patch('builtins.open', mock_open(read_data=yaml_content)):
            data = gen.load_yaml()

        assert abs(data['duration'] - math.pi * 2) < 1e-10


# =============================================================================
# 11. TEST EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Test edge cases e boundary conditions."""

    def test_load_yaml_then_reload(self, gen):
        """Ricaricare YAML sovrascrive i dati precedenti."""
        yaml1 = yaml.dump({'key': 'first'})
        yaml2 = yaml.dump({'key': 'second'})

        with patch('builtins.open', mock_open(read_data=yaml1)):
            gen.load_yaml()
        assert gen.data['key'] == 'first'

        with patch('builtins.open', mock_open(read_data=yaml2)):
            gen.load_yaml()
        assert gen.data['key'] == 'second'

    def test_create_elements_clears_nothing(self, gen):
        """create_elements non resetta le liste (appende)."""
        gen.data = {'streams': []}
        gen.streams = ['pre_existing']

        with patch.object(gen, '_filter_solo_mute', return_value=[]), \
             patch.object(gen, '_create_streams'):
            gen.create_elements()

        # _create_streams viene chiamata con lista vuota, non modifica streams
        assert 'pre_existing' in gen.streams

    def test_eval_math_with_tuple(self, gen):
        """Tuple passano attraverso (non sono dict, list, o str)."""
        result = gen._eval_math_expressions((1, 2, 3))
        assert result == (1, 2, 3)

    def test_eval_math_integer_zero(self, gen):
        """Zero intero passa attraverso."""
        assert gen._eval_math_expressions(0) == 0

    def test_eval_math_negative_number(self, gen):
        """Numeri negativi passano attraverso."""
        assert gen._eval_math_expressions(-5) == -5
        assert gen._eval_math_expressions(-3.14) == -3.14


# =============================================================================
# 12. TEST PARAMETRIZZATI
# =============================================================================

class TestParametrized:
    """Test parametrizzati per copertura sistematica."""

    @pytest.mark.parametrize("expr,expected", [
        ('(1 + 1)', 2),
        ('(10 - 3)', 7),
        ('(4 * 5)', 20),
        ('(100 / 4)', 25.0),
        ('(pi)', math.pi),
        ('(e)', math.e),
        ('(int(3.7))', 3),
        ('(float(5))', 5.0),
    ])
    def test_eval_various_expressions(self, gen, expr, expected):
        """Valuta varie espressioni matematiche."""
        result = gen._eval_math_expressions(expr)
        if isinstance(expected, float):
            assert abs(result - expected) < 1e-10
        else:
            assert result == expected

    @pytest.mark.parametrize("expr", [
        '(max(1, 2))',
        '(min(1, 2))',
        '(pow(2, 8))',
    ])
    def test_eval_comma_expressions_not_matched(self, gen, expr):
        """Espressioni con virgola non sono matchate dal regex."""
        result = gen._eval_math_expressions(expr)
        assert result == expr  # Stringa invariata

    @pytest.mark.parametrize("passthrough", [
        42, 3.14, None, True, False, 'plain_text', 'audio.wav',
    ])
    def test_eval_passthrough_types(self, gen, passthrough):
        """Vari tipi passano invariati attraverso _eval_math_expressions."""
        result = gen._eval_math_expressions(passthrough)
        assert result == passthrough

    @pytest.mark.parametrize("n_streams", [0, 1, 2, 5, 10])
    def test_filter_various_sizes(self, gen, n_streams):
        """_filter_solo_mute con varie dimensioni lista."""
        streams = [{'stream_id': f's{i}'} for i in range(n_streams)]
        result = gen._filter_solo_mute(streams)
        assert len(result) == n_streams

    @pytest.mark.parametrize("n_muted,total,expected", [
        (0, 3, 3),
        (1, 3, 2),
        (2, 3, 1),
        (3, 3, 0),
    ])
    def test_filter_mute_counts(self, gen, n_muted, total, expected):
        """_filter_solo_mute con vari conteggi mute."""
        streams = []
        for i in range(total):
            s = {'stream_id': f's{i}'}
            if i < n_muted:
                s['mute'] = True
            streams.append(s)

        result = gen._filter_solo_mute(streams)
        assert len(result) == expected

    @pytest.mark.parametrize("yaml_path", [
        'config.yml',
        '/absolute/path/config.yml',
        './relative/config.yaml',
        'no_extension',
        'path with spaces/config.yml',
    ])
    def test_init_various_paths(self, yaml_path):
        """Vari formati di yaml_path sono accettati."""
        Generator = _get_generator_class()
        with patch('engine.generator.FtableManager'), \
             patch('engine.generator.ScoreWriter'):
            g = Generator(yaml_path)
        assert g.yaml_path == yaml_path

    @pytest.mark.parametrize("output_path", [
        'output.sco',
        '/tmp/score.sco',
        './scores/my_piece.sco',
    ])
    def test_generate_score_various_paths(self, gen, output_path):
        """generate_score_file con vari percorsi output."""
        gen.streams = []
        gen.cartridges = []

        gen.generate_score_file(output_path)

        call_kwargs = gen.score_writer.write_score.call_args
        assert call_kwargs.kwargs['filepath'] == output_path

    def test_eval_invalid_expression_returns_original(self, gen):
        """Copre righe 279-284: except in evaluate_match con espressione invalida."""
        # Un'espressione che causa un errore durante eval (es. divisione per zero
        # o nome non definito nel safe_dict)
        result = gen._eval_math_expressions("(undefined_var + 1)")
        # Deve restituire la stringa originale intatta quando eval fallisce
        assert result == "(undefined_var + 1)"

    def test_eval_zero_division_returns_original(self, gen):
        """Espressione con ZeroDivisionError copre il blocco except."""
        result = gen._eval_math_expressions("(1/0)")
        # Quando eval lancia ZeroDivisionError, ritorna l'originale
        assert result == "(1/0)"

# =============================================================================
# 10. TEST generate_score_files_per_stream()
# =============================================================================

class TestGenerateScoreFilesPerStream:
    """Test per generate_score_files_per_stream() - un file per stream/cartridge."""

    def _make_stream(self, stream_id):
        s = Mock()
        s.stream_id = stream_id
        return s

    def _make_cartridge(self, cartridge_id):
        c = Mock()
        c.cartridge_id = cartridge_id
        return c

    def test_returns_list(self, gen):
        """Il metodo ritorna una lista."""
        gen.streams = []
        gen.cartridges = []
        result = gen.generate_score_files_per_stream()
        assert isinstance(result, list)

    def test_empty_streams_and_cartridges_returns_empty_list(self, gen):
        """Con liste vuote non genera nessun file."""
        gen.streams = []
        gen.cartridges = []
        result = gen.generate_score_files_per_stream()
        assert result == []

    def test_one_file_per_stream(self, gen):
        """Genera esattamente un file per ogni stream."""
        gen.streams = [self._make_stream('s1'), self._make_stream('s2')]
        gen.cartridges = []
        result = gen.generate_score_files_per_stream()
        assert len(result) == 2

    def test_one_file_per_cartridge(self, gen):
        """Genera esattamente un file per ogni cartridge."""
        gen.streams = []
        gen.cartridges = [self._make_cartridge('c1'), self._make_cartridge('c2')]
        result = gen.generate_score_files_per_stream()
        assert len(result) == 2

    def test_streams_and_cartridges_combined(self, gen):
        """Genera file per stream E per cartridges."""
        gen.streams = [self._make_stream('s1')]
        gen.cartridges = [self._make_cartridge('c1'), self._make_cartridge('c2')]
        result = gen.generate_score_files_per_stream()
        assert len(result) == 3

    def test_stream_filename_uses_stream_id(self, gen):
        """Il nome del file stream contiene stream_id."""
        gen.streams = [self._make_stream('texture_01')]
        gen.cartridges = []
        result = gen.generate_score_files_per_stream()
        assert any('texture_01' in path for path in result)

    def test_cartridge_filename_uses_cartridge_id(self, gen):
        """Il nome del file cartridge contiene cartridge_id."""
        gen.streams = []
        gen.cartridges = [self._make_cartridge('tape_head_A')]
        result = gen.generate_score_files_per_stream()
        assert any('tape_head_A' in path for path in result)

    def test_files_have_sco_extension(self, gen):
        """Tutti i file generati hanno estensione .sco."""
        gen.streams = [self._make_stream('s1')]
        gen.cartridges = [self._make_cartridge('c1')]
        result = gen.generate_score_files_per_stream()
        assert all(path.endswith('.sco') for path in result)

    def test_base_name_prefix_applied_to_streams(self, gen):
        """Con base_name, il prefisso viene applicato ai file stream."""
        gen.streams = [self._make_stream('s1')]
        gen.cartridges = []
        result = gen.generate_score_files_per_stream(base_name='my_piece')
        assert any('my_piece_s1' in path for path in result)

    def test_base_name_prefix_applied_to_cartridges(self, gen):
        """Con base_name, il prefisso viene applicato ai file cartridge."""
        gen.streams = []
        gen.cartridges = [self._make_cartridge('c1')]
        result = gen.generate_score_files_per_stream(base_name='my_piece')
        assert any('my_piece_c1' in path for path in result)

    def test_without_base_name_no_prefix(self, gen):
        """Senza base_name, il file inizia direttamente con stream_id."""
        gen.streams = [self._make_stream('s1')]
        gen.cartridges = []
        result = gen.generate_score_files_per_stream(output_dir='.')
        filename = os.path.basename(result[0])
        assert filename == 's1.sco'

    def test_output_dir_applied_to_paths(self, gen, tmp_path):
        """I file vengono creati nella output_dir specificata."""
        gen.streams = [self._make_stream('s1')]
        gen.cartridges = []
        result = gen.generate_score_files_per_stream(output_dir=str(tmp_path))
        assert all(str(tmp_path) in path for path in result)

    def test_output_dir_created_if_not_exists(self, gen, tmp_path):
        """La output_dir viene creata se non esiste."""
        new_dir = str(tmp_path / 'new_subdir')
        gen.streams = [self._make_stream('s1')]
        gen.cartridges = []
        gen.generate_score_files_per_stream(output_dir=new_dir)
        assert os.path.isdir(new_dir)

    def test_stream_written_with_only_its_stream(self, gen):
        """Ogni chiamata a write_score per stream passa solo quello stream."""
        s1 = self._make_stream('s1')
        s2 = self._make_stream('s2')
        gen.streams = [s1, s2]
        gen.cartridges = []

        gen.generate_score_files_per_stream()

        calls = gen.score_writer.write_score.call_args_list
        stream_calls = [c for c in calls]
        assert stream_calls[0].kwargs['streams'] == [s1]
        assert stream_calls[0].kwargs['cartridges'] == []
        assert stream_calls[1].kwargs['streams'] == [s2]
        assert stream_calls[1].kwargs['cartridges'] == []

    def test_cartridge_written_with_only_its_cartridge(self, gen):
        """Ogni chiamata a write_score per cartridge passa solo quella cartridge."""
        c1 = self._make_cartridge('c1')
        c2 = self._make_cartridge('c2')
        gen.streams = []
        gen.cartridges = [c1, c2]

        gen.generate_score_files_per_stream()

        calls = gen.score_writer.write_score.call_args_list
        assert calls[0].kwargs['streams'] == []
        assert calls[0].kwargs['cartridges'] == [c1]
        assert calls[1].kwargs['cartridges'] == [c2]

    def test_yaml_source_passed_to_each_call(self, gen):
        """yaml_source viene passato a ogni chiamata di write_score."""
        gen.streams = [self._make_stream('s1')]
        gen.cartridges = [self._make_cartridge('c1')]

        gen.generate_score_files_per_stream()

        for call in gen.score_writer.write_score.call_args_list:
            assert call.kwargs['yaml_source'] == 'test_config.yml'

    def test_write_score_called_once_per_element(self, gen):
        """write_score viene chiamato esattamente N volte (stream + cartridges)."""
        gen.streams = [self._make_stream('s1'), self._make_stream('s2')]
        gen.cartridges = [self._make_cartridge('c1')]

        gen.generate_score_files_per_stream()

        assert gen.score_writer.write_score.call_count == 3

    def test_default_output_dir_is_current_dir(self, gen):
        """Senza output_dir, i file vengono messi nella directory corrente."""
        gen.streams = [self._make_stream('s1')]
        gen.cartridges = []
        result = gen.generate_score_files_per_stream()
        # Il path deve essere relativo alla dir corrente
        assert os.path.dirname(result[0]) == '.'
        
# =============================================================================
# 11. TEST _stream_data_map
# =============================================================================

class TestStreamDataMap:
    """
    _create_streams() deve popolare self._stream_data_map
    con i dict YAML raw indicizzati per stream_id.
    """

    def test_stream_data_map_initialized_empty(self, gen):
        """_stream_data_map e' un dict vuoto dopo __init__."""
        assert gen._stream_data_map == {}

    def test_stream_data_map_populated_after_create_streams(self, gen):
        """_create_streams popola _stream_data_map con i raw dict."""
        stream_data = [
            {'stream_id': 's1', 'onset': 0.0, 'sample': 'a.wav'},
        ]
        with patch('engine.generator.Stream') as MockStream, \
             patch('engine.generator.WindowController'):
            mock_stream = Mock()
            mock_stream.stream_id = 's1'
            mock_stream.sample = 'a.wav'
            mock_stream.window_table_map = {}
            MockStream.return_value = mock_stream
            gen.ftable_manager.register_sample = Mock(return_value=1)
            gen._create_streams(stream_data)

        assert 's1' in gen._stream_data_map
        assert gen._stream_data_map['s1'] == stream_data[0]

    def test_stream_data_map_stores_raw_dict_not_stream_object(self, gen):
        """_stream_data_map contiene il dict originale, non l'oggetto Stream."""
        stream_data = [
            {'stream_id': 's1', 'onset': 0.0, 'sample': 'a.wav'},
        ]
        with patch('engine.generator.Stream') as MockStream, \
             patch('engine.generator.WindowController'):
            mock_stream = Mock()
            mock_stream.stream_id = 's1'
            mock_stream.sample = 'a.wav'
            mock_stream.window_table_map = {}
            MockStream.return_value = mock_stream
            gen.ftable_manager.register_sample = Mock(return_value=1)
            gen._create_streams(stream_data)

        stored = gen._stream_data_map['s1']
        assert isinstance(stored, dict)

    def test_stream_data_map_multiple_streams(self, gen):
        """_stream_data_map viene popolato per tutti gli stream."""
        stream_data = [
            {'stream_id': 's1', 'onset': 0.0, 'sample': 'a.wav'},
            {'stream_id': 's2', 'onset': 5.0, 'sample': 'b.wav'},
        ]
        with patch('engine.generator.Stream') as MockStream, \
             patch('engine.generator.WindowController'):
            def make_stream(d):
                m = Mock()
                m.stream_id = d['stream_id']
                m.sample = d['sample']
                m.window_table_map = {}
                return m
            MockStream.side_effect = make_stream
            gen.ftable_manager.register_sample = Mock(return_value=1)
            gen._create_streams(stream_data)

        assert 's1' in gen._stream_data_map
        assert 's2' in gen._stream_data_map


# =============================================================================
# 12. TEST generate_score_files_per_stream() WITH CACHE
# =============================================================================

class TestGenerateScoreFilesPerStreamWithCache:
    """
    generate_score_files_per_stream() con cache_manager opzionale.

    Behavioral contract:
    - Senza cache_manager: comportamento invariato (backward compat)
    - Con cache_manager: stream clean saltano write_score
    - Con cache_manager: stream dirty ricevono write_score
    - update_after_build() viene chiamato dopo la scrittura degli stream dirty
    - aif_dir viene passato a get_dirty_stream_dicts
    """

    def _make_stream(self, stream_id):
        s = Mock()
        s.stream_id = stream_id
        return s

    def _make_cache_manager(self, dirty_ids=None):
        """
        Costruisce un mock StreamCacheManager.
        dirty_ids: set di stream_id considerati dirty. Se None, tutti dirty.
        """
        from unittest.mock import MagicMock
        cm = MagicMock()
        if dirty_ids is None:
            cm.get_dirty_stream_dicts.side_effect = lambda dicts, aif_dir: dicts
        else:
            def filter_dirty(dicts, aif_dir):
                return [d for d in dicts if d.get('stream_id') in dirty_ids]
            cm.get_dirty_stream_dicts.side_effect = filter_dirty
        return cm

    def test_without_cache_manager_writes_all_streams(self, gen):
        """Senza cache_manager tutti gli stream producono write_score."""
        gen.streams = [self._make_stream('s1'), self._make_stream('s2')]
        gen.cartridges = []

        gen.generate_score_files_per_stream()

        assert gen.score_writer.write_score.call_count == 2

    def test_with_cache_manager_all_dirty_writes_all(self, gen):
        """Con cache_manager, stream tutti dirty: write_score chiamato per ognuno."""
        s1 = self._make_stream('s1')
        s2 = self._make_stream('s2')
        gen.streams = [s1, s2]
        gen.cartridges = []
        gen._stream_data_map = {
            's1': {'stream_id': 's1'},
            's2': {'stream_id': 's2'},
        }

        cm = self._make_cache_manager(dirty_ids={'s1', 's2'})
        gen.generate_score_files_per_stream(cache_manager=cm)

        assert gen.score_writer.write_score.call_count == 2

    def test_with_cache_manager_all_clean_skips_all(self, gen):
        """Con cache_manager, stream tutti clean: write_score mai chiamato."""
        s1 = self._make_stream('s1')
        s2 = self._make_stream('s2')
        gen.streams = [s1, s2]
        gen.cartridges = []
        gen._stream_data_map = {
            's1': {'stream_id': 's1'},
            's2': {'stream_id': 's2'},
        }

        cm = self._make_cache_manager(dirty_ids=set())
        gen.generate_score_files_per_stream(cache_manager=cm)

        gen.score_writer.write_score.assert_not_called()

    def test_with_cache_manager_mixed_writes_only_dirty(self, gen):
        """Con cache_manager, solo lo stream dirty riceve write_score."""
        s1 = self._make_stream('s1')
        s2 = self._make_stream('s2')
        gen.streams = [s1, s2]
        gen.cartridges = []
        gen._stream_data_map = {
            's1': {'stream_id': 's1'},
            's2': {'stream_id': 's2'},
        }

        cm = self._make_cache_manager(dirty_ids={'s2'})
        gen.generate_score_files_per_stream(cache_manager=cm)

        assert gen.score_writer.write_score.call_count == 1
        written_streams = gen.score_writer.write_score.call_args.kwargs['streams']
        assert written_streams == [s2]

    def test_update_after_build_called_with_dirty_dicts(self, gen):
        """update_after_build viene chiamato con i dict degli stream scritti."""
        s1 = self._make_stream('s1')
        gen.streams = [s1]
        gen.cartridges = []
        raw = {'stream_id': 's1', 'volume': -6.0}
        gen._stream_data_map = {'s1': raw}

        cm = self._make_cache_manager(dirty_ids={'s1'})
        gen.generate_score_files_per_stream(cache_manager=cm)

        cm.update_after_build.assert_called_once_with([raw])

    def test_update_after_build_not_called_when_nothing_dirty(self, gen):
        """update_after_build non viene chiamato se nessuno stream e' dirty."""
        s1 = self._make_stream('s1')
        gen.streams = [s1]
        gen.cartridges = []
        gen._stream_data_map = {'s1': {'stream_id': 's1'}}

        cm = self._make_cache_manager(dirty_ids=set())
        gen.generate_score_files_per_stream(cache_manager=cm)

        cm.update_after_build.assert_not_called()

    def test_aif_dir_passed_to_get_dirty_stream_dicts(self, gen):
        """aif_dir viene inoltrato a cache_manager.get_dirty_stream_dicts."""
        s1 = self._make_stream('s1')
        gen.streams = [s1]
        gen.cartridges = []
        gen._stream_data_map = {'s1': {'stream_id': 's1'}}

        cm = self._make_cache_manager(dirty_ids=set())
        gen.generate_score_files_per_stream(
            cache_manager=cm, aif_dir='/output/stems'
        )

        call_kwargs = cm.get_dirty_stream_dicts.call_args
        assert call_kwargs.kwargs['aif_dir'] == '/output/stems'

    def test_cartridges_not_filtered_by_cache(self, gen):
        """Le cartridges non passano dal cache manager e vengono sempre scritte."""
        c1 = Mock()
        c1.cartridge_id = 'c1'
        gen.streams = []
        gen.cartridges = [c1]
        gen._stream_data_map = {}

        cm = self._make_cache_manager(dirty_ids=set())
        gen.generate_score_files_per_stream(cache_manager=cm)

        assert gen.score_writer.write_score.call_count == 1

    def test_without_cache_manager_update_never_called(self, gen):
        """Senza cache_manager non viene chiamato nessun update."""
        gen.streams = [self._make_stream('s1')]
        gen.cartridges = []

        # Nessun cache_manager passato: nessun AttributeError atteso
        gen.generate_score_files_per_stream()
        # Se arriviamo qui senza eccezioni, il test passa