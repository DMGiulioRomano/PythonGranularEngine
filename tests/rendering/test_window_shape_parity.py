"""
Parita' di forma fra il catalogo delle finestre e la sua materializzazione.

Prima della #202 la forma di una finestra era scritta due volte -- una in
termini di GEN Csound (`WindowRegistry`), una in termini di NumPy
(`NumpyWindowRegistry`) -- e la guardia che le teneva insieme confrontava i
*nomi*: lunghezza giusta, valori finiti. Due implementazioni della stessa
finestra potevano quindi divergere nella forma (il caso classico e' simmetrica
contro periodica, che si vede su un campione agli estremi) e nessun test se ne
sarebbe accorto.

Questa suite chiude quel buco con due oracoli, che devono dire la stessa cosa:

1. **Oracolo esterno** -- `np.hanning`, `np.kaiser`, le formule scritte a mano
   qui sotto. Non passa dal catalogo, quindi e' il lucchetto sul *suono*: se il
   refactoring avesse cambiato una finestra di un campione, e' rosso qui. Vale
   anche come misura della divergenza, che e' il primo test chiesto dalla #202.

2. **Oracolo derivato dalla spec** -- la forma matematica *dichiarata* dal
   catalogo, valutata qui a partire dai suoi campi (coefficienti, parametri) e
   non dal codice dell'emitter. E' la forma eseguibile della tabella nel
   docstring di `window_registry`: un emitter che sostituisse alla somma di
   coseni una built-in periodica passerebbe l'oracolo esterno solo se la
   built-in coincide, e comunque fallirebbe la simmetria dichiarata.

Il terzo asse e' la `symmetry` dichiarata, riletta sull'array: e' verificabile
solo perche' il catalogo dichiara anche la convenzione di campionamento
(intervallo chiuso, primo campione in x=0 e ultimo in x=1).

Cosa questa suite **non** puo' dire: se le tabelle che Csound genera davvero
per quegli stessi GEN abbiano la stessa forma. Le GEN le esegue Csound, non
noi; l'equivalenza fra la forma dichiarata e la routine scelta e' fissata come
traduzione in `tests/rendering/test_csound_window_emitter.py`, e le due
divergenze note (l'apertura della gaussiana, la convenzione di campionamento)
sono dichiarate li'.
"""

import numpy as np
import pytest

from pge.controllers.window_registry import (
    ASYMMETRIC,
    SYMMETRIC,
    WindowRegistry,
    WindowShape,
)
from pge.rendering.numpy_window_emitter import NumpyWindowEmitter
from pge.rendering.numpy_window_registry import (
    NumpyWindowRegistry,
    WINDOW_MIN_SHAPE_SAMPLES,
)


# Lunghezze di prova: sopra la soglia sotto la quale non si finestra (#225),
# pari e dispari, piccole e reali.
LENGTHS = [WINDOW_MIN_SHAPE_SAMPLES, 11, 64, 127, 1024]

# La tolleranza non e' un margine di comodo: le due scritture della stessa
# formula differiscono per l'ordine delle operazioni in virgola mobile
# (`np.hanning` calcola `0.5 + 0.5 cos(pi n/(M-1))` su `arange(1-M, M, 2)`,
# la somma di coseni calcola `a0 - a1 cos(2 pi k/(M-1))`), che vale ~1e-16.
# Un campione di scarto -- la divergenza che questa suite cerca -- e' 1e-2 o
# piu' su qualunque finestra del catalogo.
TOL = 1e-12

ALL_NAMES = sorted(WindowRegistry.WINDOWS.keys())


# =============================================================================
# ORACOLO 1: esterno al catalogo
# =============================================================================

def external_oracle(name: str, n: int) -> np.ndarray:
    """La finestra come la scriverebbe chi non ha letto il catalogo.

    Built-in NumPy dove esistono, formula esplicita dove no. E' la forma che
    il motore rendeva prima della #202: se cambia, e' cambiato il suono.
    """
    x = np.linspace(0.0, 1.0, n)

    if name == 'hanning':
        return np.hanning(n)
    if name == 'hamming':
        return np.hamming(n)
    if name == 'blackman':
        return np.blackman(n)
    if name == 'bartlett':
        return np.bartlett(n)
    if name == 'kaiser':
        return np.kaiser(n, beta=6.0)
    if name == 'rectangle':
        return np.ones(n, dtype=np.float64)
    if name == 'sinc':
        return np.sinc(np.linspace(-1.0, 1.0, n))
    if name == 'half_sine':
        return np.sin(np.linspace(0.0, np.pi, n))
    if name == 'gaussian':
        u = np.linspace(-1.0, 1.0, n)
        return np.exp(-0.5 * (u / 0.4) ** 2)
    if name == 'blackman_harris':
        return (0.35875
                - 0.48829 * np.cos(2.0 * np.pi * x)
                + 0.14128 * np.cos(4.0 * np.pi * x)
                - 0.01168 * np.cos(6.0 * np.pi * x))

    curves = {
        'expodec':         (1.0,   4.0, 0.0),
        'expodec_strong':  (1.0,  10.0, 0.0),
        'exporise':        (0.0,  -4.0, 1.0),
        'exporise_strong': (0.0, -10.0, 1.0),
        'rexpodec':        (1.0,  -4.0, 0.0),
        'rexporise':       (0.0,   4.0, 1.0),
    }
    if name in curves:
        start, curve, end = curves[name]
        normalized = (1.0 - np.exp(curve * x)) / (1.0 - np.exp(curve))
        return start + (end - start) * normalized

    raise AssertionError(
        f"'{name}' e' nel catalogo e non nell'oracolo esterno: una finestra "
        f"nuova va aggiunta qui, altrimenti la parita' non la copre."
    )


# =============================================================================
# ORACOLO 2: derivato dalla spec dichiarata
# =============================================================================

def spec_oracle(spec, n: int) -> np.ndarray:
    """La finestra come la dichiara il catalogo, valutata dai suoi campi.

    E' la tabella delle forme del docstring di `window_registry` resa
    eseguibile. Legge la spec, mai l'emitter.
    """
    x = np.linspace(0.0, 1.0, n)
    u = np.linspace(-1.0, 1.0, n)          # u = 2x - 1

    if spec.shape == WindowShape.COSINE_SUM:
        out = np.zeros(n, dtype=np.float64)
        for k, coefficient in enumerate(spec.coefficients):
            out = out + ((-1.0) ** k) * coefficient * np.cos(2.0 * np.pi * k * x)
        return out

    if spec.shape == WindowShape.TRIANGULAR:
        return 1.0 - np.abs(2.0 * x - 1.0)

    if spec.shape == WindowShape.GAUSSIAN:
        return np.exp(-0.5 * (u / spec.param('sigma')) ** 2)

    if spec.shape == WindowShape.KAISER:
        return np.kaiser(n, beta=spec.param('beta'))

    if spec.shape == WindowShape.RECTANGULAR:
        return np.ones(n, dtype=np.float64)

    if spec.shape == WindowShape.SINC_LOBE:
        return np.sinc(u)

    if spec.shape == WindowShape.SINE_LOBE:
        return np.sin(np.pi * x)

    if spec.shape == WindowShape.EXPONENTIAL_SEGMENT:
        start = spec.param('start')
        curve = spec.param('curve')
        end = spec.param('end')
        if abs(curve) < 1e-10:
            return start + (end - start) * x
        normalized = (1.0 - np.exp(curve * x)) / (1.0 - np.exp(curve))
        return start + (end - start) * normalized

    raise AssertionError(
        f"forma '{spec.shape}' non prevista dall'oracolo: una forma nuova va "
        f"aggiunta qui insieme al ramo dell'emitter."
    )


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def emitter():
    return NumpyWindowEmitter()


@pytest.fixture
def registry():
    return NumpyWindowRegistry()


# =============================================================================
# 1. IL LUCCHETTO SUL SUONO
# =============================================================================

class TestMaterializationMatchesTheExternalOracle:
    """Nessun campione si e' mosso: il refactoring della #202 e' una
    riscrittura della descrizione, non della forma."""

    @pytest.mark.parametrize("name", ALL_NAMES)
    @pytest.mark.parametrize("n", LENGTHS)
    def test_registry_output_is_unchanged(self, registry, name, n):
        np.testing.assert_allclose(
            registry.get(name, n), external_oracle(name, n),
            atol=TOL, rtol=0, err_msg=f"{name} n={n}"
        )

    @pytest.mark.parametrize("name", ALL_NAMES)
    def test_emitter_output_is_unchanged(self, emitter, name):
        spec = WindowRegistry.get(name)
        np.testing.assert_allclose(
            emitter.materialize(spec, 512), external_oracle(name, 512),
            atol=TOL, rtol=0, err_msg=name
        )

    def test_the_oracle_can_actually_see_a_difference(self):
        """La guardia sopra non e' verde perche' cieca.

        Un campione di scarto -- la finestra periodica al posto della
        simmetrica -- e' ordini di grandezza sopra la tolleranza.
        """
        symmetric = external_oracle('hanning', 64)
        periodic = 0.5 - 0.5 * np.cos(2.0 * np.pi * np.arange(64) / 64)

        assert np.max(np.abs(symmetric - periodic)) > 1e-3


# =============================================================================
# 2. IL CATALOGO DICHIARA LA FORMA CHE IL TARGET PRODUCE
# =============================================================================

class TestMaterializationMatchesTheDeclaredShape:
    """La parita' che la #202 chiedeva: cio' che il catalogo dichiara e cio'
    che il target produce sono la stessa funzione."""

    @pytest.mark.parametrize("name", ALL_NAMES)
    @pytest.mark.parametrize("n", LENGTHS)
    def test_emitter_materializes_the_declared_shape(self, emitter, name, n):
        spec = WindowRegistry.get(name)
        np.testing.assert_allclose(
            emitter.materialize(spec, n), spec_oracle(spec, n),
            atol=TOL, rtol=0, err_msg=f"{name} n={n}"
        )

    @pytest.mark.parametrize("name", ALL_NAMES)
    def test_the_two_oracles_agree(self, name):
        """La chiusura del triangolo: la forma dichiarata dal catalogo e' la
        stessa che il motore rendeva prima che il catalogo la dichiarasse.

        E' qui che si vede che i coefficienti scritti nel catalogo *sono*
        hamming, hanning, blackman e blackman-harris, e non quattro numeri
        plausibili.
        """
        spec = WindowRegistry.get(name)
        np.testing.assert_allclose(
            spec_oracle(spec, 256), external_oracle(name, 256),
            atol=TOL, rtol=0, err_msg=name
        )

    def test_alias_materializes_as_its_canonical(self, registry):
        np.testing.assert_array_equal(
            registry.get('triangle', 64), registry.get('bartlett', 64))


# =============================================================================
# 3. LA SIMMETRIA DICHIARATA E' QUELLA MATERIALIZZATA
# =============================================================================

class TestDeclaredSymmetry:
    """`symmetry` non e' un commento: e' una proprieta' che si rilegge
    sull'array, ed e' l'asse su cui una finestra periodica al posto di una
    simmetrica si vede."""

    @pytest.mark.parametrize("name", ALL_NAMES)
    @pytest.mark.parametrize("n", [64, 65])
    def test_symmetry_holds_as_declared(self, emitter, name, n):
        spec = WindowRegistry.get(name)
        window = emitter.materialize(spec, n)
        gap = float(np.max(np.abs(window - window[::-1])))

        if spec.symmetry == SYMMETRIC:
            assert gap < TOL, f"{name}: dichiarata simmetrica, scarto {gap:.3g}"
        else:
            assert gap > 1e-3, f"{name}: dichiarata asimmetrica, scarto {gap:.3g}"

    def test_both_verdicts_are_represented(self):
        """Il test sopra sarebbe verde a vuoto se il catalogo fosse tutto
        simmetrico o tutto asimmetrico."""
        declared = {spec.symmetry for spec in WindowRegistry.WINDOWS.values()}
        assert declared == {SYMMETRIC, ASYMMETRIC}
