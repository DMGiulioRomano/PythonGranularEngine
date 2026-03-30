# tests/rendering/test_numpy_window_registry.py
"""
TDD suite per NumpyWindowRegistry.

RED phase: questi test falliranno finche' non creiamo
src/rendering/numpy_window_registry.py con la classe NumpyWindowRegistry.

NumpyWindowRegistry genera e cachea array NumPy per le finestre grano,
indicizzati per (name, N). E' l'equivalente NumPy di cio' che Csound fa
con GEN20 (window functions) e GEN16 (curve asimmetriche).

Coverage:
1. TestNumpyWindowRegistryInit  - costruzione e stato iniziale
2. TestGetWindow                - generazione finestra per nome e lunghezza
3. TestWindowShape              - forma corretta degli array
4. TestCaching                  - deduplicazione per (name, N)
5. TestAsymmetricWindows        - expodec, rexpodec, exporise
6. TestInvalidWindow            - nome non valido
7. TestHalfSine                 - half_sine custom
"""

import pytest
import numpy as np

from rendering.numpy_window_registry import NumpyWindowRegistry


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def registry():
    """NumpyWindowRegistry fresco, cache vuota."""
    return NumpyWindowRegistry()


# =============================================================================
# 1. TEST INIT
# =============================================================================

class TestNumpyWindowRegistryInit:
    """Test per la costruzione e lo stato iniziale."""

    def test_creates_instance(self, registry):
        """NumpyWindowRegistry si puo' istanziare."""
        assert registry is not None

    def test_cache_starts_empty(self, registry):
        """La cache interna e' vuota alla creazione."""
        assert len(registry) == 0

    def test_available_windows_not_empty(self, registry):
        """La lista delle finestre disponibili non e' vuota."""
        assert len(registry.available_windows()) > 0

    def test_available_windows_contains_hanning(self, registry):
        """hanning e' tra le finestre disponibili."""
        assert 'hanning' in registry.available_windows()


# =============================================================================
# 2. TEST GET WINDOW
# =============================================================================

class TestGetWindow:
    """Test per la generazione di finestre."""

    def test_returns_numpy_array(self, registry):
        """get() ritorna un array NumPy."""
        window = registry.get('hanning', 1024)
        assert isinstance(window, np.ndarray)

    def test_returns_correct_length(self, registry):
        """L'array ha la lunghezza richiesta."""
        window = registry.get('hanning', 512)
        assert len(window) == 512

    def test_returns_float64(self, registry):
        """L'array e' in float64 (precisione per moltiplicazione grano)."""
        window = registry.get('hanning', 256)
        assert window.dtype == np.float64

    def test_returns_1d_array(self, registry):
        """L'array e' monodimensionale."""
        window = registry.get('hamming', 1024)
        assert window.ndim == 1

    @pytest.mark.parametrize("name", [
        'hanning', 'hamming', 'blackman', 'bartlett', 'kaiser',
    ])
    def test_numpy_builtin_windows(self, registry, name):
        """Le finestre built-in di NumPy sono disponibili."""
        window = registry.get(name, 1024)
        assert len(window) == 1024

    @pytest.mark.parametrize("name", [
        'expodec', 'expodec_strong', 'exporise', 'exporise_strong',
        'rexpodec', 'rexporise',
    ])
    def test_asymmetric_windows_available(self, registry, name):
        """Le finestre asimmetriche (GEN16 equivalenti) sono disponibili."""
        window = registry.get(name, 1024)
        assert len(window) == 1024

    def test_half_sine_available(self, registry):
        """half_sine e' disponibile."""
        window = registry.get('half_sine', 1024)
        assert len(window) == 1024

    @pytest.mark.parametrize("n", [64, 128, 256, 512, 1024, 2048, 4096])
    def test_various_lengths(self, registry, n):
        """Funziona con diverse lunghezze."""
        window = registry.get('hanning', n)
        assert len(window) == n


# =============================================================================
# 3. TEST WINDOW SHAPE
# =============================================================================

class TestWindowShape:
    """Test per la forma corretta degli array finestra."""

    def test_hanning_starts_near_zero(self, registry):
        """Hanning inizia vicino a zero."""
        window = registry.get('hanning', 1024)
        assert window[0] < 0.01

    def test_hanning_ends_near_zero(self, registry):
        """Hanning finisce vicino a zero."""
        window = registry.get('hanning', 1024)
        assert window[-1] < 0.01

    def test_hanning_peak_near_one(self, registry):
        """Hanning ha il picco vicino a 1.0."""
        window = registry.get('hanning', 1024)
        assert np.max(window) > 0.99

    def test_hanning_is_symmetric(self, registry):
        """Hanning e' simmetrica."""
        window = registry.get('hanning', 1024)
        np.testing.assert_array_almost_equal(window, window[::-1])

    def test_all_values_non_negative(self, registry):
        """Tutti i valori della finestra sono >= 0 (tolleranza floating point)."""
        for name in ['hanning', 'hamming', 'blackman', 'expodec', 'half_sine']:
            window = registry.get(name, 1024)
            assert np.all(window >= -1e-15), f"{name} ha valori negativi"

    def test_all_values_at_most_one(self, registry):
        """Tutti i valori della finestra sono <= 1.0."""
        for name in ['hanning', 'hamming', 'blackman', 'expodec', 'half_sine']:
            window = registry.get(name, 1024)
            assert np.all(window <= 1.0 + 1e-10), f"{name} ha valori > 1.0"

    def test_expodec_starts_at_one(self, registry):
        """expodec inizia a 1.0 (decadimento esponenziale)."""
        window = registry.get('expodec', 1024)
        assert window[0] > 0.99

    def test_expodec_ends_near_zero(self, registry):
        """expodec finisce vicino a 0.0."""
        window = registry.get('expodec', 1024)
        assert window[-1] < 0.05

    def test_exporise_starts_near_zero(self, registry):
        """exporise inizia vicino a 0.0."""
        window = registry.get('exporise', 1024)
        assert window[0] < 0.05

    def test_exporise_ends_at_one(self, registry):
        """exporise finisce a 1.0."""
        window = registry.get('exporise', 1024)
        assert window[-1] > 0.99

    def test_expodec_is_monotonically_decreasing(self, registry):
        """expodec e' monotonicamente decrescente."""
        window = registry.get('expodec', 1024)
        diffs = np.diff(window)
        assert np.all(diffs <= 1e-10), "expodec non e' monotonicamente decrescente"

    def test_exporise_is_monotonically_increasing(self, registry):
        """exporise e' monotonicamente crescente."""
        window = registry.get('exporise', 1024)
        diffs = np.diff(window)
        assert np.all(diffs >= -1e-10), "exporise non e' monotonicamente crescente"


# =============================================================================
# 4. TEST CACHING
# =============================================================================

class TestCaching:
    """Test per la deduplicazione e il caching."""

    def test_same_name_and_length_returns_cached(self, registry):
        """Stessa (name, N) ritorna lo stesso oggetto array."""
        w1 = registry.get('hanning', 1024)
        w2 = registry.get('hanning', 1024)
        assert w1 is w2

    def test_different_length_creates_new_entry(self, registry):
        """Stessa name ma N diverso crea entry separate."""
        w1 = registry.get('hanning', 512)
        w2 = registry.get('hanning', 1024)
        assert w1 is not w2
        assert len(w1) == 512
        assert len(w2) == 1024

    def test_different_name_creates_new_entry(self, registry):
        """Nomi diversi creano entry separate."""
        w1 = registry.get('hanning', 1024)
        w2 = registry.get('hamming', 1024)
        assert w1 is not w2

    def test_len_reflects_cache_size(self, registry):
        """len(registry) riflette il numero di entry cachate."""
        assert len(registry) == 0
        registry.get('hanning', 1024)
        assert len(registry) == 1
        registry.get('hanning', 512)
        assert len(registry) == 2
        registry.get('hanning', 1024)  # gia' cachato
        assert len(registry) == 2
        registry.get('hamming', 1024)
        assert len(registry) == 3


# =============================================================================
# 5. TEST ASYMMETRIC WINDOWS
# =============================================================================

class TestAsymmetricWindows:
    """Test per le finestre asimmetriche (equivalenti GEN16 Csound)."""

    def test_expodec_strong_steeper_final_drop(self, registry):
        """expodec_strong ha caduta finale piu' ripida (resta alta piu' a lungo)."""
        w_normal = registry.get('expodec', 1024)
        w_strong = registry.get('expodec_strong', 1024)

        # Con curva piu' alta, la finestra resta vicina a 1.0 piu' a lungo
        # poi crolla piu' ripidamente alla fine
        mid = 512
        assert w_strong[mid] > w_normal[mid]

    def test_rexpodec_starts_at_one(self, registry):
        """rexpodec inizia a 1.0."""
        window = registry.get('rexpodec', 1024)
        assert window[0] > 0.99

    def test_rexpodec_ends_near_zero(self, registry):
        """rexpodec finisce vicino a 0.0."""
        window = registry.get('rexpodec', 1024)
        assert window[-1] < 0.05

    def test_rexpodec_is_concave(self, registry):
        """rexpodec ha curvatura opposta a expodec (concava vs convessa)."""
        w_expo = registry.get('expodec', 1024)
        w_rexpo = registry.get('rexpodec', 1024)

        # A meta' finestra, rexpodec deve essere piu' bassa di expodec
        # perche' rexpodec ha curvatura negativa (concava, decade piu' lentamente all'inizio)
        mid = 512
        assert w_rexpo[mid] < w_expo[mid]

    def test_rexporise_ends_at_one(self, registry):
        """rexporise finisce a 1.0."""
        window = registry.get('rexporise', 1024)
        assert window[-1] > 0.99


# =============================================================================
# 6. TEST INVALID WINDOW
# =============================================================================

class TestInvalidWindow:
    """Test per nomi di finestra non validi."""

    def test_invalid_name_raises_value_error(self, registry):
        """Nome non valido solleva ValueError."""
        with pytest.raises(ValueError):
            registry.get('nonexistent', 1024)

    def test_error_message_contains_name(self, registry):
        """Il messaggio di errore contiene il nome richiesto."""
        with pytest.raises(ValueError, match="FAKENAME"):
            registry.get('FAKENAME', 1024)

    def test_invalid_not_cached(self, registry):
        """Un nome non valido non crea entry in cache."""
        with pytest.raises(ValueError):
            registry.get('invalid', 1024)
        assert len(registry) == 0

    def test_zero_length_raises(self, registry):
        """Lunghezza 0 solleva ValueError."""
        with pytest.raises(ValueError):
            registry.get('hanning', 0)

    def test_negative_length_raises(self, registry):
        """Lunghezza negativa solleva ValueError."""
        with pytest.raises(ValueError):
            registry.get('hanning', -1)


# =============================================================================
# 7. TEST HALF SINE
# =============================================================================

class TestHalfSine:
    """Test per la finestra half_sine (equivalente GEN09 Csound)."""

    def test_half_sine_starts_near_zero(self, registry):
        """half_sine inizia vicino a zero."""
        window = registry.get('half_sine', 1024)
        assert window[0] < 0.01

    def test_half_sine_ends_near_zero(self, registry):
        """half_sine finisce vicino a zero."""
        window = registry.get('half_sine', 1024)
        assert window[-1] < 0.01

    def test_half_sine_peak_at_center(self, registry):
        """half_sine ha il picco al centro."""
        window = registry.get('half_sine', 1024)
        peak_idx = np.argmax(window)
        center = 1024 // 2
        assert abs(peak_idx - center) < 5  # tolleranza di 5 campioni

    def test_half_sine_peak_value_near_one(self, registry):
        """half_sine raggiunge circa 1.0 al picco."""
        window = registry.get('half_sine', 1024)
        assert np.max(window) > 0.99

    def test_half_sine_is_symmetric(self, registry):
        """half_sine e' simmetrica."""
        window = registry.get('half_sine', 1024)
        np.testing.assert_array_almost_equal(window, window[::-1], decimal=5)
