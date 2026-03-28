# tests/rendering/test_sample_registry.py
"""
TDD suite per SampleRegistry.

RED phase: questi test falliranno finche' non creiamo
src/rendering/sample_registry.py con la classe SampleRegistry.

SampleRegistry carica e cachea file audio sorgente come array NumPy,
conservando il sample rate nativo (file_sr) di ciascun file.
Questo e' necessario per il calcolo corretto del pitch nel
NumpyAudioRenderer: pitch_ratio * file_sr / output_sr.

Coverage:
1. TestSampleRegistryInit   - costruzione e stato iniziale
2. TestLoadSample           - caricamento singolo file
3. TestMonoConversion       - stereo -> mono
4. TestCaching              - deduplicazione, nessuna rilettura
5. TestSampleRate           - file_sr conservato per ogni sample
6. TestErrorHandling        - file non trovato, errori I/O
7. TestGetSample            - accesso ai dati cachati
"""

import pytest
import numpy as np
from unittest.mock import patch, MagicMock

from rendering.sample_registry import SampleRegistry


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def registry():
    """SampleRegistry fresco, cache vuota."""
    return SampleRegistry()


@pytest.fixture
def mono_audio():
    """Array mono 1 secondo a 48000 Hz: sinusoide 440 Hz."""
    sr = 48000
    t = np.linspace(0, 1.0, sr, endpoint=False)
    return np.sin(2 * np.pi * 440 * t).astype(np.float32), sr


@pytest.fixture
def stereo_audio():
    """Array stereo 1 secondo a 44100 Hz: due canali."""
    sr = 44100
    n_samples = sr
    left = np.sin(2 * np.pi * 440 * np.linspace(0, 1, n_samples, endpoint=False))
    right = np.sin(2 * np.pi * 880 * np.linspace(0, 1, n_samples, endpoint=False))
    audio = np.column_stack([left, right]).astype(np.float32)
    return audio, sr


# =============================================================================
# 1. TEST SAMPLE REGISTRY INIT
# =============================================================================

class TestSampleRegistryInit:
    """Test per la costruzione e lo stato iniziale."""

    def test_creates_instance(self, registry):
        """SampleRegistry si puo' istanziare."""
        assert registry is not None

    def test_cache_starts_empty(self, registry):
        """La cache interna e' vuota alla creazione."""
        assert len(registry) == 0

    def test_custom_base_path(self):
        """Si puo' passare un base_path custom."""
        reg = SampleRegistry(base_path='/custom/path/')
        assert reg.base_path == '/custom/path/'

    def test_default_base_path(self, registry):
        """Il base_path di default e' './refs/'."""
        assert registry.base_path == './refs/'


# =============================================================================
# 2. TEST LOAD SAMPLE
# =============================================================================

class TestLoadSample:
    """Test per il caricamento di un file audio."""

    @patch('rendering.sample_registry.sf.read')
    def test_load_returns_numpy_array(self, mock_read, registry, mono_audio):
        """load() ritorna un array NumPy."""
        audio, sr = mono_audio
        mock_read.return_value = (audio, sr)

        samples, file_sr = registry.load('test.wav')

        assert isinstance(samples, np.ndarray)

    @patch('rendering.sample_registry.sf.read')
    def test_load_returns_sample_rate(self, mock_read, registry, mono_audio):
        """load() ritorna il sample rate nativo del file."""
        audio, sr = mono_audio
        mock_read.return_value = (audio, sr)

        samples, file_sr = registry.load('test.wav')

        assert file_sr == sr

    @patch('rendering.sample_registry.sf.read')
    def test_load_constructs_full_path(self, mock_read, registry, mono_audio):
        """load() costruisce il path completo con base_path."""
        audio, sr = mono_audio
        mock_read.return_value = (audio, sr)

        registry.load('piano.wav')

        mock_read.assert_called_once_with('./refs/piano.wav')

    @patch('rendering.sample_registry.sf.read')
    def test_load_custom_base_path(self, mock_read, mono_audio):
        """load() usa il base_path custom."""
        audio, sr = mono_audio
        mock_read.return_value = (audio, sr)
        reg = SampleRegistry(base_path='/samples/')

        reg.load('voice.wav')

        mock_read.assert_called_once_with('/samples/voice.wav')

    @patch('rendering.sample_registry.sf.read')
    def test_load_returns_float32(self, mock_read, registry, mono_audio):
        """I campioni caricati sono in float32."""
        audio, sr = mono_audio
        mock_read.return_value = (audio, sr)

        samples, _ = registry.load('test.wav')

        assert samples.dtype == np.float32

    @patch('rendering.sample_registry.sf.read')
    def test_load_mono_preserves_shape(self, mock_read, registry, mono_audio):
        """Un file mono ritorna un array 1D."""
        audio, sr = mono_audio
        mock_read.return_value = (audio, sr)

        samples, _ = registry.load('test.wav')

        assert samples.ndim == 1


# =============================================================================
# 3. TEST MONO CONVERSION
# =============================================================================

class TestMonoConversion:
    """Test per la conversione stereo -> mono."""

    @patch('rendering.sample_registry.sf.read')
    def test_stereo_converted_to_mono(self, mock_read, registry, stereo_audio):
        """Un file stereo viene convertito a mono (1D)."""
        audio, sr = stereo_audio
        mock_read.return_value = (audio, sr)

        samples, _ = registry.load('stereo.wav')

        assert samples.ndim == 1

    @patch('rendering.sample_registry.sf.read')
    def test_stereo_mono_length_matches(self, mock_read, registry, stereo_audio):
        """La lunghezza mono corrisponde al numero di frame originali."""
        audio, sr = stereo_audio
        mock_read.return_value = (audio, sr)

        samples, _ = registry.load('stereo.wav')

        assert len(samples) == audio.shape[0]

    @patch('rendering.sample_registry.sf.read')
    def test_stereo_mono_is_mean_of_channels(self, mock_read, registry, stereo_audio):
        """La conversione mono usa la media dei canali."""
        audio, sr = stereo_audio
        mock_read.return_value = (audio, sr)

        samples, _ = registry.load('stereo.wav')
        expected = np.mean(audio, axis=1).astype(np.float32)

        np.testing.assert_array_almost_equal(samples, expected)

    @patch('rendering.sample_registry.sf.read')
    def test_mono_not_affected(self, mock_read, registry, mono_audio):
        """Un file gia' mono non viene modificato."""
        audio, sr = mono_audio
        mock_read.return_value = (audio, sr)

        samples, _ = registry.load('mono.wav')

        np.testing.assert_array_almost_equal(samples, audio)


# =============================================================================
# 4. TEST CACHING
# =============================================================================

class TestCaching:
    """Test per la deduplicazione e il caching."""

    @patch('rendering.sample_registry.sf.read')
    def test_second_load_uses_cache(self, mock_read, registry, mono_audio):
        """Il secondo load() dello stesso file non rilegge da disco."""
        audio, sr = mono_audio
        mock_read.return_value = (audio, sr)

        registry.load('test.wav')
        registry.load('test.wav')

        assert mock_read.call_count == 1

    @patch('rendering.sample_registry.sf.read')
    def test_cached_returns_same_data(self, mock_read, registry, mono_audio):
        """I dati cachati sono identici a quelli originali."""
        audio, sr = mono_audio
        mock_read.return_value = (audio, sr)

        samples1, sr1 = registry.load('test.wav')
        samples2, sr2 = registry.load('test.wav')

        np.testing.assert_array_equal(samples1, samples2)
        assert sr1 == sr2

    @patch('rendering.sample_registry.sf.read')
    def test_different_files_loaded_separately(self, mock_read, registry, mono_audio):
        """File diversi vengono caricati separatamente."""
        audio, sr = mono_audio
        mock_read.return_value = (audio, sr)

        registry.load('a.wav')
        registry.load('b.wav')

        assert mock_read.call_count == 2

    @patch('rendering.sample_registry.sf.read')
    def test_len_reflects_cached_count(self, mock_read, registry, mono_audio):
        """len(registry) riflette il numero di file cachati."""
        audio, sr = mono_audio
        mock_read.return_value = (audio, sr)

        assert len(registry) == 0
        registry.load('a.wav')
        assert len(registry) == 1
        registry.load('b.wav')
        assert len(registry) == 2
        registry.load('a.wav')  # duplicato
        assert len(registry) == 2


# =============================================================================
# 5. TEST SAMPLE RATE
# =============================================================================

class TestSampleRate:
    """Test per la conservazione del file_sr nativo."""

    @patch('rendering.sample_registry.sf.read')
    def test_preserves_44100(self, mock_read, registry):
        """file_sr = 44100 viene conservato."""
        audio = np.zeros(44100, dtype=np.float32)
        mock_read.return_value = (audio, 44100)

        _, file_sr = registry.load('44k.wav')

        assert file_sr == 44100

    @patch('rendering.sample_registry.sf.read')
    def test_preserves_48000(self, mock_read, registry):
        """file_sr = 48000 viene conservato."""
        audio = np.zeros(48000, dtype=np.float32)
        mock_read.return_value = (audio, 48000)

        _, file_sr = registry.load('48k.wav')

        assert file_sr == 48000

    @patch('rendering.sample_registry.sf.read')
    def test_preserves_96000(self, mock_read, registry):
        """file_sr = 96000 viene conservato."""
        audio = np.zeros(96000, dtype=np.float32)
        mock_read.return_value = (audio, 96000)

        _, file_sr = registry.load('96k.wav')

        assert file_sr == 96000

    @patch('rendering.sample_registry.sf.read')
    def test_different_files_different_rates(self, mock_read, registry):
        """File con sample rate diversi mantengono ciascuno il proprio."""
        audio_44 = np.zeros(44100, dtype=np.float32)
        audio_48 = np.zeros(48000, dtype=np.float32)

        mock_read.side_effect = [
            (audio_44, 44100),
            (audio_48, 48000),
        ]

        _, sr1 = registry.load('file_44.wav')
        _, sr2 = registry.load('file_48.wav')

        assert sr1 == 44100
        assert sr2 == 48000


# =============================================================================
# 6. TEST ERROR HANDLING
# =============================================================================

class TestErrorHandling:
    """Test per gestione errori."""

    @patch('rendering.sample_registry.sf.read')
    def test_file_not_found_raises(self, mock_read, registry):
        """File non trovato solleva FileNotFoundError."""
        mock_read.side_effect = FileNotFoundError("No such file")

        with pytest.raises(FileNotFoundError):
            registry.load('missing.wav')

    @patch('rendering.sample_registry.sf.read')
    def test_failed_load_not_cached(self, mock_read, registry):
        """Un file che fallisce il caricamento non viene cachato."""
        mock_read.side_effect = FileNotFoundError("No such file")

        with pytest.raises(FileNotFoundError):
            registry.load('bad.wav')

        assert len(registry) == 0

    @patch('rendering.sample_registry.sf.read')
    def test_runtime_error_propagates(self, mock_read, registry):
        """Errori runtime di soundfile vengono propagati."""
        mock_read.side_effect = RuntimeError("Corrupt file")

        with pytest.raises(RuntimeError):
            registry.load('corrupt.wav')


# =============================================================================
# 7. TEST GET SAMPLE (ACCESSO DIRETTO ALLA CACHE)
# =============================================================================

class TestGetSample:
    """Test per l'accesso diretto ai dati cachati senza ricaricare."""

    @patch('rendering.sample_registry.sf.read')
    def test_get_returns_cached_data(self, mock_read, registry, mono_audio):
        """get() ritorna i dati gia' cachati."""
        audio, sr = mono_audio
        mock_read.return_value = (audio, sr)

        registry.load('test.wav')
        samples, file_sr = registry.get('test.wav')

        assert isinstance(samples, np.ndarray)
        assert file_sr == sr

    def test_get_uncached_raises_key_error(self, registry):
        """get() su un file non cachato solleva KeyError."""
        with pytest.raises(KeyError):
            registry.get('not_loaded.wav')

    @patch('rendering.sample_registry.sf.read')
    def test_get_does_not_trigger_read(self, mock_read, registry, mono_audio):
        """get() non chiama sf.read (usa solo la cache)."""
        audio, sr = mono_audio
        mock_read.return_value = (audio, sr)

        registry.load('test.wav')
        mock_read.reset_mock()

        registry.get('test.wav')

        mock_read.assert_not_called()
