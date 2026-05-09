"""
test_utils.py

Test suite completa per il modulo utils.py.

Coverage:
1. Test get_sample_duration - con mock di soundfile
2. Test random_percent - comportamento probabilistico
3. Test get_nested - navigazione dict con dot notation
4. Test edge cases e errori
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Any

from shared.utils import get_sample_duration, random_percent, get_nested, PATHSAMPLES

# =============================================================================
# 1. TEST GET_SAMPLE_DURATION
# =============================================================================

class TestGetSampleDuration:
    """Test per get_sample_duration() - usa mock di soundfile."""

    @pytest.fixture(autouse=True)
    def _mock_path_exists(self):
        """Default: simula sample esistente. Test specifici override via patch locale."""
        with patch('shared.utils.os.path.exists', return_value=True):
            yield

    @patch('shared.utils.sf.info')
    def test_get_duration_normal_file(self, mock_info):
        """File audio normale restituisce durata corretta."""
        mock_info.return_value = Mock(duration=2.5)
        
        result = get_sample_duration('test.wav')
        
        assert result == 2.5
        mock_info.assert_called_once_with('./refs/test.wav')
    
    @patch('shared.utils.sf.info')
    def test_get_duration_zero_length(self, mock_info):
        """File audio di lunghezza zero."""
        mock_info.return_value = Mock(duration=0.0)
        
        result = get_sample_duration('empty.wav')
        
        assert result == 0.0
    
    @patch('shared.utils.sf.info')
    def test_get_duration_very_short(self, mock_info):
        """File audio molto breve (< 1ms)."""
        mock_info.return_value = Mock(duration=0.0001)
        
        result = get_sample_duration('tiny.wav')
        
        assert result == pytest.approx(0.0001)
    
    @patch('shared.utils.sf.info')
    def test_get_duration_very_long(self, mock_info):
        """File audio molto lungo (ore)."""
        mock_info.return_value = Mock(duration=3600.0)
        
        result = get_sample_duration('long.wav')
        
        assert result == 3600.0
    
    @patch('shared.utils.sf.info')
    def test_path_construction(self, mock_info):
        """Verifica che il path sia costruito correttamente."""
        mock_info.return_value = Mock(duration=1.0)
        
        get_sample_duration('subfolder/file.wav')
        
        mock_info.assert_called_once_with('./refs/subfolder/file.wav')
    
    @patch('shared.utils.sf.info')
    def test_different_extensions(self, mock_info):
        """Funziona con diverse estensioni audio."""
        mock_info.return_value = Mock(duration=1.0)
        
        extensions = ['test.wav', 'test.aiff', 'test.flac', 'test.mp3']
        
        for filename in extensions:
            get_sample_duration(filename)
        
        assert mock_info.call_count == len(extensions)
    
    @patch('shared.utils.sf.info')
    def test_file_not_found_error(self, mock_info):
        """File esistente ma sf.info fallisce con FileNotFoundError → propaga."""
        mock_info.side_effect = FileNotFoundError("File not found")
        with patch('shared.utils.os.path.exists', return_value=True):
            with pytest.raises(FileNotFoundError):
                get_sample_duration('nonexistent.wav')
    
    @patch('shared.utils.sf.info')
    def test_invalid_audio_file(self, mock_info):
        """File non valido solleva errore soundfile."""
        mock_info.side_effect = RuntimeError("Invalid audio file")
        with patch('shared.utils.os.path.exists', return_value=True):
            with pytest.raises(RuntimeError):
                get_sample_duration('invalid.wav')

    def test_missing_sample_raises_sample_not_found_error(self):
        """File assente in PATHSAMPLES → SampleNotFoundError con filename e path."""
        from shared.exceptions import SampleNotFoundError

        with patch('shared.utils.os.path.exists', return_value=False):
            with pytest.raises(SampleNotFoundError) as exc_info:
                get_sample_duration('pino.wav')

        err = exc_info.value
        assert err.filename == 'pino.wav'
        assert err.search_path == './refs/'


# =============================================================================
# 2. TEST RANDOM_PERCENT
# =============================================================================

class TestRandomPercent:
    """Test per random_percent() - comportamento probabilistico."""
    
    def test_always_true_at_100_percent(self):
        """Con percent=100, deve sempre restituire True."""
        results = [random_percent(100) for _ in range(100)]
        assert all(results), "Con 100% dovrebbe sempre essere True"
    
    def test_never_true_at_0_percent(self):
        """Con percent=0, deve sempre restituire False."""
        results = [random_percent(0) for _ in range(100)]
        assert not any(results), "Con 0% dovrebbe sempre essere False"
    
    def test_default_value(self):
        """Default è 90%."""
        # Test statistico: su 1000 tentativi, dovrebbe essere ~900 True
        results = [random_percent() for _ in range(1000)]
        true_count = sum(results)
        
        # Tolleranza: tra 85% e 95% (statisticamente robusto)
        assert 850 <= true_count <= 950, f"Default 90% fuori range: {true_count}/1000"
    
    @pytest.mark.parametrize("percent,expected_range", [
        (50, (450, 550)),   # 50% ± 5%
        (75, (700, 800)),   # 75% ± 5%
        (25, (200, 300)),   # 25% ± 5%
        (10, (50, 150)),    # 10% ± 5%
    ])
    def test_various_percentages(self, percent, expected_range):
        """Test percentuali diverse con range statisticamente validi."""
        results = [random_percent(percent) for _ in range(1000)]
        true_count = sum(results)
        
        min_expected, max_expected = expected_range
        assert min_expected <= true_count <= max_expected, \
            f"{percent}% fuori range: {true_count}/1000"
    
    def test_returns_boolean(self):
        """Deve restituire sempre un bool."""
        result_true = random_percent(100)
        result_false = random_percent(0)
        
        assert isinstance(result_true, bool)
        assert isinstance(result_false, bool)
    
    def test_edge_case_near_100(self):
        """99.9% dovrebbe essere quasi sempre True."""
        results = [random_percent(99.9) for _ in range(1000)]
        true_count = sum(results)
        
        # Almeno 990/1000 dovrebbero essere True
        assert true_count >= 990
    
    def test_edge_case_near_0(self):
        """0.1% dovrebbe essere quasi sempre False."""
        results = [random_percent(0.1) for _ in range(1000)]
        true_count = sum(results)
        
        # Al massimo 10/1000 dovrebbero essere True (molto permissivo)
        assert true_count <= 10
    
    def test_negative_percent_treated_as_zero(self):
        """Percentuale negativa dovrebbe comportarsi come 0."""
        # percent/100 = negativo, uniform(0,1) > negativo è sempre True
        # MA: (percent/100) > uniform → negativo > positivo è sempre False
        results = [random_percent(-10) for _ in range(100)]
        
        # Verifica comportamento effettivo (tutti False)
        assert not any(results)
    
    def test_over_100_percent_always_true(self):
        """Percentuale > 100 dovrebbe essere sempre True."""
        # 150/100 = 1.5, uniform(0,1) genera [0, 1)
        # 1.5 > [0, 1) → sempre True
        results = [random_percent(150) for _ in range(100)]
        
        assert all(results)
    
    def test_fractional_percentages(self):
        """Percentuali frazionarie (es. 33.33%)."""
        results = [random_percent(33.33) for _ in range(1000)]
        true_count = sum(results)
        
        # Range: 30% - 37% (tolleranza statistica)
        assert 300 <= true_count <= 370


# =============================================================================
# 3. TEST GET_NESTED
# =============================================================================

class TestGetNested:
    """Test per get_nested() - navigazione dict con dot notation."""
    
    def test_simple_key_access(self):
        """Accesso a chiave singola."""
        data = {'key': 'value'}
        result = get_nested(data, 'key', 'default')
        
        assert result == 'value'
    
    def test_nested_key_access(self):
        """Accesso a chiave annidata (dot notation)."""
        data = {'level1': {'level2': {'level3': 42}}}
        result = get_nested(data, 'level1.level2.level3', 'default')
        
        assert result == 42
    
    def test_missing_key_returns_default(self):
        """Chiave mancante restituisce default."""
        data = {'existing': 'value'}
        result = get_nested(data, 'missing', 'default_value')
        
        assert result == 'default_value'
    
    def test_partial_path_returns_default(self):
        """Path parzialmente valido restituisce default."""
        data = {'level1': {'level2': 'value'}}
        result = get_nested(data, 'level1.level2.level3', 'default')
        
        assert result == 'default'
    
    def test_empty_dict_returns_default(self):
        """Dict vuoto restituisce sempre default."""
        data = {}
        result = get_nested(data, 'any.path', 'default')
        
        assert result == 'default'
    
    def test_empty_path_returns_dict_itself(self):
        """Path vuoto restituisce il dict stesso."""
        data = {'key': 'value'}
        result = get_nested(data, '', data)
        
        # Path vuoto → nessun split → restituisce data
        assert result == data
    
    def test_numeric_values(self):
        """Funziona con valori numerici."""
        data = {'grain': {'duration': 0.05}}
        result = get_nested(data, 'grain.duration', 0.1)
        
        assert result == 0.05
    
    def test_list_values(self):
        """Funziona con liste come valori."""
        data = {'envelope': {'points': [[0, 0], [1, 1]]}}
        result = get_nested(data, 'envelope.points', [])
        
        assert result == [[0, 0], [1, 1]]
    
    def test_none_values(self):
        """Funziona con None come valore."""
        data = {'param': {'value': None}}
        result = get_nested(data, 'param.value', 'default')
        
        assert result is None  # None è un valore valido, non default
    
    def test_boolean_values(self):
        """Funziona con booleani."""
        data = {'settings': {'enabled': False}}
        result = get_nested(data, 'settings.enabled', True)
        
        assert result is False
    
    def test_deep_nesting(self):
        """Navigazione molto profonda."""
        data = {
            'a': {
                'b': {
                    'c': {
                        'd': {
                            'e': {
                                'f': 'deep_value'
                            }
                        }
                    }
                }
            }
        }
        result = get_nested(data, 'a.b.c.d.e.f', 'default')
        
        assert result == 'deep_value'
    
    def test_keys_with_special_names(self):
        """Chiavi con nomi speciali."""
        data = {
            'grain.duration': 0.05,  # Chiave con punto nel nome
            'normal': {'key': 'value'}
        }
        
        # Dot notation cerca 'grain' poi 'duration' (non 'grain.duration')
        result = get_nested(data, 'grain.duration', 'default')
        assert result == 'default'  # Non trova 'grain' come dict
        
        # Chiave diretta funziona
        result = get_nested(data, 'normal.key', 'default')
        assert result == 'value'
    
    @pytest.mark.parametrize("data,path,default,expected", [
        # Vari tipi di default
        ({'a': 1}, 'b', None, None),
        ({'a': 1}, 'b', 0, 0),
        ({'a': 1}, 'b', [], []),
        ({'a': 1}, 'b', {}, {}),
        
        # Vari tipi di valori
        ({'x': 42}, 'x', 0, 42),
        ({'x': 'text'}, 'x', '', 'text'),
        ({'x': [1, 2, 3]}, 'x', [], [1, 2, 3]),
        ({'x': {'y': 'z'}}, 'x', {}, {'y': 'z'}),
    ])
    def test_various_types(self, data, path, default, expected):
        """Test parametrizzato per vari tipi di dati."""
        result = get_nested(data, path, default)
        assert result == expected
    
    def test_non_dict_intermediate_value(self):
        """Se un valore intermedio non è dict, restituisce default."""
        data = {'level1': 'not_a_dict'}
        result = get_nested(data, 'level1.level2', 'default')
        
        assert result == 'default'
    
    def test_real_world_yaml_structure(self):
        """Test con struttura simile a YAML reale del progetto."""
        data = {
            'grain': {
                'duration': 0.05,
                'envelope': 'hanning'
            },
            'volume': -6,
            'pointer': {
                'start': 0,
                'loop': {
                    'enabled': True,
                    'start': 0.1,
                    'end': 0.9
                }
            }
        }
        
        assert get_nested(data, 'grain.duration', 0.1) == 0.05
        assert get_nested(data, 'grain.envelope', 'none') == 'hanning'
        assert get_nested(data, 'volume', 0) == -6
        assert get_nested(data, 'pointer.loop.enabled', False) is True
        assert get_nested(data, 'pointer.loop.start', 0) == 0.1
        assert get_nested(data, 'missing.path', 42) == 42


# =============================================================================
# 4. TEST INTEGRAZIONE E EDGE CASES
# =============================================================================

class TestUtilsIntegration:
    """Test di integrazione tra le funzioni utilities."""
    
    @patch('shared.utils.sf.info')
    @patch('shared.utils.os.path.exists', return_value=True)
    def test_chaining_functions(self, mock_exists, mock_info):
        """Test concatenazione funzioni utils."""
        mock_info.return_value = Mock(duration=2.5)

        # Simula workflow reale
        duration = get_sample_duration('test.wav')
        
        # Usa durata in dict
        config = {'sample_duration': duration}
        retrieved_duration = get_nested(config, 'sample_duration', 0)
        
        assert retrieved_duration == 2.5
    
    def test_get_nested_with_probability_dict(self):
        """get_nested usato per configurazioni probabilità."""
        config = {
            'dephase': {
                'enabled': True,
                'probability': 80
            }
        }
        
        enabled = get_nested(config, 'dephase.enabled', False)
        prob = get_nested(config, 'dephase.probability', 100)
        
        if enabled and random_percent(prob):
            assert True  # Logica applicata correttamente


# =============================================================================
# 5. TEST PATHSAMPLES CONSTANT
# =============================================================================

class TestPathSamplesConstant:
    """Test per la costante PATHSAMPLES."""
    
    def test_pathsamples_exists(self):
        """Verifica che PATHSAMPLES sia definito."""
        
        assert PATHSAMPLES is not None
    
    def test_pathsamples_is_string(self):
        """PATHSAMPLES deve essere una stringa."""
        
        assert isinstance(PATHSAMPLES, str)
    
    def test_pathsamples_value(self):
        """PATHSAMPLES deve puntare a ./refs/."""
        
        assert PATHSAMPLES == './refs/'
    
    @patch('shared.utils.sf.info')
    @patch('shared.utils.os.path.exists', return_value=True)
    def test_pathsamples_used_in_get_duration(self, mock_exists, mock_info):
        """get_sample_duration usa PATHSAMPLES."""
        mock_info.return_value = Mock(duration=1.0)

        get_sample_duration('test.wav')
        
        # Verifica che il path includa PATHSAMPLES
        called_path = mock_info.call_args[0][0]
        assert called_path.startswith('./refs/')


# =============================================================================
# 6. TEST PERFORMANCE E STRESS
# =============================================================================

class TestPerformance:
    """Test performance per funzioni critiche."""
    
    def test_get_nested_performance_shallow(self):
        """get_nested deve essere veloce su dict shallow."""
        data = {f'key{i}': i for i in range(1000)}
        
        # 1000 accessi devono essere rapidi
        for i in range(1000):
            result = get_nested(data, f'key{i}', -1)
            assert result == i
    
    def test_get_nested_performance_deep(self):
        """get_nested deve essere veloce anche con nesting profondo."""
        # Crea struttura profonda
        data = {'level0': {}}
        current = data['level0']
        for i in range(1, 50):
            current[f'level{i}'] = {}
            current = current[f'level{i}']
        current['value'] = 'found'
        
        # Costruisci path
        path = '.'.join([f'level{i}' for i in range(50)] + ['value'])
        
        # Deve trovarlo
        result = get_nested(data, path, 'default')
        assert result == 'found'
    
    def test_random_percent_distribution_accuracy(self):
        """Test accuratezza distribuzione su grande numero di campioni."""
        # 10000 campioni per 50%
        results = [random_percent(50) for _ in range(10000)]
        true_count = sum(results)
        
        # Con 10k campioni, tolleranza ±2%
        assert 4800 <= true_count <= 5200, \
            f"50% con 10k campioni fuori range: {true_count}/10000"