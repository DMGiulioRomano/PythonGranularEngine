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

from pge.rendering.numpy_window_registry import NumpyWindowRegistry


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


# =============================================================================
# 8. TEST RECTANGLE WINDOW
# =============================================================================

class TestRectangleWindow:
    """Test per la finestra rectangle (GEN20 opt 8 — finestra piatta)."""

    def test_rectangle_available(self, registry):
        """rectangle e' nella lista delle finestre disponibili."""
        assert 'rectangle' in registry.available_windows()

    def test_rectangle_returns_array(self, registry):
        """get() ritorna un array NumPy."""
        w = registry.get('rectangle', 1024)
        assert isinstance(w, np.ndarray)
        assert len(w) == 1024

    def test_rectangle_all_ones(self, registry):
        """Tutti i valori sono 1.0 (finestra piatta)."""
        w = registry.get('rectangle', 256)
        np.testing.assert_array_almost_equal(w, np.ones(256))

    def test_rectangle_dtype_float64(self, registry):
        """Array in float64."""
        w = registry.get('rectangle', 512)
        assert w.dtype == np.float64

    def test_rectangle_is_symmetric(self, registry):
        """rectangle e' simmetrica."""
        w = registry.get('rectangle', 512)
        np.testing.assert_array_equal(w, w[::-1])


# =============================================================================
# 9. TEST SINC WINDOW
# =============================================================================

class TestSincWindow:
    """Test per la finestra sinc (GEN20 opt 9 — lobo centrale sin(πx)/(πx))."""

    def test_sinc_available(self, registry):
        """sinc e' nella lista delle finestre disponibili."""
        assert 'sinc' in registry.available_windows()

    def test_sinc_returns_array(self, registry):
        """get() ritorna un array NumPy."""
        w = registry.get('sinc', 1024)
        assert isinstance(w, np.ndarray)
        assert len(w) == 1024

    def test_sinc_peak_value_near_one(self, registry):
        """sinc raggiunge quasi 1.0 al centro (per n pari il picco non tocca x=0 esatto)."""
        w = registry.get('sinc', 1024)
        assert np.max(w) > 0.9999

    def test_sinc_peak_value_exact_for_odd_n(self, registry):
        """Per n dispari il campione centrale e' x=0 esatto: sinc(0)=1.0."""
        w = registry.get('sinc', 1025)
        assert abs(np.max(w) - 1.0) < 1e-10
        assert np.argmax(w) == 512

    def test_sinc_peak_at_center(self, registry):
        """Il picco e' vicino al campione centrale (tolleranza 1 campione per n pari)."""
        w = registry.get('sinc', 1024)
        center = len(w) // 2
        assert abs(np.argmax(w) - center) <= 1

    def test_sinc_edges_near_zero(self, registry):
        """Primo e ultimo campione sono vicini a zero."""
        w = registry.get('sinc', 1024)
        assert abs(w[0]) < 1e-10
        assert abs(w[-1]) < 1e-10

    def test_sinc_is_symmetric(self, registry):
        """sinc e' simmetrica."""
        w = registry.get('sinc', 1024)
        np.testing.assert_array_almost_equal(w, w[::-1], decimal=10)

    def test_sinc_all_non_negative(self, registry):
        """Tutti i valori sono >= 0 (solo lobo centrale, x in [-1,1])."""
        w = registry.get('sinc', 1024)
        assert np.all(w >= -1e-15)


# =============================================================================
# 10. TEST BLACKMAN-HARRIS WINDOW
# =============================================================================

class TestBlackmanHarrisWindow:
    """Test per la finestra blackman_harris (GEN20 opt 5 — campana a 4 termini).

    Parita' col registry Csound (WindowRegistry): blackman_harris era definita
    solo lato Csound, qui colmiamo il gap nel renderer NumPy.
    """

    def test_blackman_harris_available(self, registry):
        """blackman_harris e' nella lista delle finestre disponibili."""
        assert 'blackman_harris' in registry.available_windows()

    def test_blackman_harris_returns_array(self, registry):
        """get() ritorna un array NumPy della lunghezza richiesta."""
        w = registry.get('blackman_harris', 1024)
        assert isinstance(w, np.ndarray)
        assert len(w) == 1024

    def test_blackman_harris_dtype_float64(self, registry):
        """Array in float64."""
        w = registry.get('blackman_harris', 512)
        assert w.dtype == np.float64

    def test_blackman_harris_starts_near_zero(self, registry):
        """Inizia vicino a zero (bordo)."""
        w = registry.get('blackman_harris', 1024)
        assert w[0] < 0.01

    def test_blackman_harris_ends_near_zero(self, registry):
        """Finisce vicino a zero (bordo)."""
        w = registry.get('blackman_harris', 1024)
        assert w[-1] < 0.01

    def test_blackman_harris_peak_near_one(self, registry):
        """Picco ~1.0 al centro."""
        w = registry.get('blackman_harris', 1024)
        assert np.max(w) > 0.99

    def test_blackman_harris_peak_at_center(self, registry):
        """Il picco e' vicino al campione centrale."""
        w = registry.get('blackman_harris', 1024)
        center = len(w) // 2
        assert abs(np.argmax(w) - center) <= 1

    def test_blackman_harris_is_symmetric(self, registry):
        """La finestra e' simmetrica."""
        w = registry.get('blackman_harris', 1024)
        np.testing.assert_array_almost_equal(w, w[::-1])

    def test_blackman_harris_all_non_negative(self, registry):
        """Tutti i valori sono >= 0 (tolleranza floating point)."""
        w = registry.get('blackman_harris', 1024)
        assert np.all(w >= -1e-12)

    def test_blackman_harris_all_at_most_one(self, registry):
        """Tutti i valori sono <= 1.0."""
        w = registry.get('blackman_harris', 1024)
        assert np.all(w <= 1.0 + 1e-10)

    def test_blackman_harris_narrower_than_blackman(self, registry):
        """blackman_harris e' piu' stretta di blackman: a un quarto della
        finestra ha valore piu' basso (lobi laterali piu' soppressi)."""
        bh = registry.get('blackman_harris', 1024)
        bk = registry.get('blackman', 1024)
        quarter = 256
        assert bh[quarter] < bk[quarter]

    def test_blackman_harris_cached(self, registry):
        """Stessa (name, N) ritorna l'oggetto cachato."""
        w1 = registry.get('blackman_harris', 1024)
        w2 = registry.get('blackman_harris', 1024)
        assert w1 is w2


# =============================================================================
# FINESTRE A LUNGHEZZE MINIME (GRANI A PRECISIONE DI CAMPIONE)
# =============================================================================

class TestSmallWindows:
    """Tutte le finestre devono essere generabili per n in {1, 2, 3}:
    nessuna eccezione, lunghezza esatta, valori finiti e limitati."""

    @pytest.mark.parametrize("n", [1, 2, 3])
    def test_all_windows_small_n(self, n):
        registry = NumpyWindowRegistry()
        for name in registry.available_windows():
            window = registry.get(name, n)
            assert len(window) == n, f"{name} n={n}"
            assert np.all(np.isfinite(window)), f"{name} n={n}"
            assert np.all(window >= -1e-9), f"{name} n={n}"
            assert np.all(window <= 1.0 + 1e-9), f"{name} n={n}"

    def test_hanning_single_sample_is_unit(self):
        """np.hanning(1) = [1.0]: un grano di 1 campione con hanning
        passa intero, non azzerato."""
        registry = NumpyWindowRegistry()
        assert registry.get('hanning', 1)[0] == pytest.approx(1.0)

    def test_rectangle_small_n_is_flat_unit(self):
        """rectangle e' la finestra consigliata per grani ultra-corti:
        piatta a 1.0 anche a n minimi."""
        registry = NumpyWindowRegistry()
        for n in (1, 2, 3):
            assert np.all(registry.get('rectangle', n) == 1.0)


# =============================================================================
# PARITA' COL CATALOGO (WindowRegistry)
# =============================================================================

class TestCatalogueParity:
    """Il catalogo delle finestre e' uno solo: WindowRegistry dice quali nomi
    lo YAML puo' scrivere, questo registry e' l'adapter che li materializza in
    array. Se i due divergono, un nome accettato dalla validazione esplode al
    momento del render."""

    def test_triangle_alias_renders_as_bartlett(self, registry):
        """`triangle` e' l'alias documentato di `bartlett`: il renderer numpy
        deve produrre la stessa finestra, non un errore."""
        assert np.array_equal(registry.get('triangle', 64),
                              registry.get('bartlett', 64))

    def test_every_catalogue_name_is_renderable(self, registry):
        """Guardia anti-drift: ogni nome che la validazione YAML accetta deve
        produrre un array. Finche' i due elenchi erano indipendenti, `triangle`
        passava la validazione e poi esplodeva al render con RENDERER=numpy."""
        from pge.controllers.window_registry import WindowRegistry

        for name in WindowRegistry.all_names():
            window = registry.get(name, 128)
            assert len(window) == 128, name
            assert np.all(np.isfinite(window)), name

    def test_alias_and_canonical_share_one_cache_entry(self, registry):
        """`triangle` e `bartlett` sono la stessa finestra: una sola voce in
        cache, non due array identici."""
        registry.get('bartlett', 64)
        registry.get('triangle', 64)
        assert len(registry) == 1

    def test_available_windows_are_the_catalogue_names(self, registry):
        """`available_windows()` e' cio' che finisce nel messaggio d'errore di
        un nome sbagliato: deve elencare i nomi scrivibili nello YAML, alias
        compresi, non l'elenco privato dei generatori."""
        from pge.controllers.window_registry import WindowRegistry

        assert set(registry.available_windows()) == set(WindowRegistry.all_names())


# =============================================================================
# NESSUNA FINESTRA E' MUTA (issue #225)
# =============================================================================

class TestNeverSilentWindow:
    """Un grano valido non e' mai silenzio.

    A N piccolissimi il campionamento discreto della finestra collassa: le
    simmetriche vengono campionate sugli estremi (`np.hanning(2) == [0, 0]`)
    e le asimmetriche sul solo punto di partenza (`exporise(1) == [0]`). Il
    grano viene generato, moltiplicato per zero e reso come silenzio, senza
    scarto e senza log. Con `grain.duration` che entra nella banda fatale
    (31.25-52.08 us a 48 kHz, cioe' `round(dur*sr) == 2`) il risultato e' un
    buco di silenzio digitale largo centinaia di ms.

    La guardia sta sul RISULTATO, non su `n`: si ripara la finestra che e'
    collassata, non ogni finestra corta. Cosi' `expodec` a N=2 resta `[1, 0]`
    -- una decadenza vera, non un caso degenere -- e le finestre solo
    attenuate (`hamming` 0.08, `gaussian` 0.044, `kaiser` 0.015) restano come
    sono: un grano piano porta ancora informazione, e alzarlo significherebbe
    inventare un livello che nessuno dei due renderer produce.
    """

    # Soglia di collasso: -60 dB rispetto al picco di progetto (1.0) di ogni
    # finestra del catalogo. Non e' un numero critico -- fra il picco piu' alto
    # fra quelli riparati (blackman_harris, 6e-5) e il piu' basso fra quelli
    # lasciati stare (kaiser, 0.0149) c'e' un vuoto di 248x, e la soglia ci sta
    # in mezzo con due ordini di grandezza di margine per lato.
    FLOOR = 1e-3

    @pytest.mark.parametrize("n", list(range(1, 17)))
    def test_no_window_collapses_at_small_n(self, registry, n):
        """Nessun nome del catalogo produce una finestra sotto la soglia di
        collasso, per nessun N fra 1 e 16.

        Il criterio e' il PICCO, non la somma: `sum() > 0` passerebbe per
        `sinc` a N=1 (somma 3.9e-17, inudibile) e fallirebbe per `blackman` a
        N=2 per il motivo sbagliato (somma negativa, -2.8e-17). Quello che
        conta e' se il grano si sente.
        """
        for name in registry.available_windows():
            window = registry.get(name, n)
            peak = float(np.max(np.abs(window)))
            assert peak > self.FLOOR, f"{name} n={n}: picco {peak:.4g}, grano muto"

    @pytest.mark.parametrize("name,n", [
        ('hanning', 2), ('bartlett', 2), ('triangle', 2), ('blackman', 2),
        ('sinc', 1), ('sinc', 2), ('half_sine', 1), ('half_sine', 2),
        ('blackman_harris', 1), ('blackman_harris', 2),
        ('exporise', 1), ('exporise_strong', 1), ('rexporise', 1),
    ])
    def test_collapsed_window_becomes_flat_unit(self, registry, name, n):
        """I casi degeneri noti diventano la finestra piatta a 1.0.

        Sotto i 3 campioni non c'e' forma da rappresentare: niente salita,
        picco e discesa. La finestra piatta e' l'unica lettura onesta.
        """
        np.testing.assert_array_equal(registry.get(name, n), np.ones(n))

    @pytest.mark.parametrize("name,n,expected", [
        # asimmetriche: a N=2 [1, 0] e' una decadenza vera, non un collasso
        ('expodec', 2, [1.0, 0.0]),
        ('expodec_strong', 2, [1.0, 0.0]),
        ('rexpodec', 2, [1.0, 0.0]),
        # attenuate ma udibili: restano intatte
        ('hamming', 2, [0.08, 0.08]),
        ('gaussian', 1, [0.043937]),
        ('rectangle', 2, [1.0, 1.0]),
    ])
    def test_informative_small_windows_are_untouched(self, registry, name, n, expected):
        """La guardia ripara solo cio' che e' collassato.

        Se la finestra corta porta ancora informazione -- una decadenza, o
        semplicemente un livello basso ma udibile -- resta esattamente com'e'.
        """
        np.testing.assert_allclose(registry.get(name, n), expected, atol=1e-6)

    def test_repair_does_not_touch_normal_lengths(self, registry):
        """A lunghezze normali le finestre restano la loro matematica: la
        guardia non deve poter scattare su una finestra sana."""
        w = registry.get('hanning', 1024)
        np.testing.assert_array_almost_equal(w, np.hanning(1024))
