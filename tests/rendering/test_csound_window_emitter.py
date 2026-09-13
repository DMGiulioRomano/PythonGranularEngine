"""
La traduzione dal catalogo alle GEN routine di Csound.

`CsoundWindowEmitter` e' meta' di cio' che prima stava dentro la `WindowSpec`:
il catalogo descriveva le finestre *nei termini di Csound* (`gen_routine`,
`gen_params`), cioe' un target si era preso il posto della descrizione. Qui
quei numeri tornano a essere una traduzione, e la tabella degli attesi -- che
prima era il test del catalogo -- diventa il test della traduzione.

L'emitter non scrive sintassi: produce una `GenTable` (routine + p-field), e
gli statement li scrive `CsoundEmitter`. La guardia strutturale su questa
divisione sta in `test_csound_emitter.py`.

## Le due divergenze dichiarate

Cosa questa suite verifica: che a ogni forma del catalogo corrisponda la GEN
che Csound documenta per quella finestra. Cosa **non** puo' verificare: che la
tabella che Csound genera davvero abbia la stessa forma dell'array NumPy. Le
GEN le esegue Csound, e la suite gira senza. Restano quindi due divergenze
possibili, entrambe dichiarate e nessuna delle due osservabile da qui:

1. **L'apertura della gaussiana.** Il catalogo dichiara `sigma`, GEN20 opt 6
   vuole il suo parametro di apertura, e la corrispondenza fra le due
   grandezze la definisce l'implementazione di Csound. La traduzione e' una
   tabella di valori noti (`sigma 0.4 -> 3`, il numero che il catalogo
   scriveva prima della #202): una sigma che non c'e' dentro e' fuori
   copertura, non un numero inventato.

2. **La convenzione di campionamento.** Il catalogo dichiara l'intervallo
   chiuso (primo campione in x=0, ultimo in x=1); se GEN20 campionasse in modo
   periodico, le due forme differirebbero di un campione agli estremi. Deciderlo
   richiede una tabella generata da Csound e confrontata con l'array: e' fuori
   dalla suite unitaria, che gira su macchine senza Csound.
"""

import pytest

from pge.controllers.window_registry import (
    WindowRegistry,
    WindowShape,
    WindowSpec,
)
from pge.rendering.csound_window_emitter import CsoundWindowEmitter, GenTable
from pge.shared.exceptions import InvalidWindowError


SIZE = 1024

# (routine, p-field) attesi per ogni nome, a tabella di 1024 punti.
# E' la trascrizione di cio' che il catalogo emetteva prima della #202: il
# refactoring non deve muovere un byte degli score gia' scritti.
EXPECTED = {
    'hamming':         (20, (1, 1)),
    'hanning':         (20, (2, 1)),
    'bartlett':        (20, (3, 1)),
    'blackman':        (20, (4, 1)),
    'blackman_harris': (20, (5, 1)),
    'gaussian':        (20, (6, 1, 3)),
    'kaiser':          (20, (7, 1, 6)),
    'rectangle':       (20, (8, 1)),
    'sinc':            (20, (9, 1, 1)),
    'half_sine':       (9,  (0.5, 1, 0)),
    'expodec':         (16, (1, SIZE, 4, 0)),
    'expodec_strong':  (16, (1, SIZE, 10, 0)),
    'exporise':        (16, (0, SIZE, -4, 1)),
    'exporise_strong': (16, (0, SIZE, -10, 1)),
    'rexpodec':        (16, (1, SIZE, -4, 0)),
    'rexporise':       (16, (0, SIZE, 4, 1)),
}


@pytest.fixture
def emitter():
    return CsoundWindowEmitter()


# =============================================================================
# 1. LA TRADUZIONE
# =============================================================================

class TestTranslation:

    @pytest.mark.parametrize("name", sorted(EXPECTED))
    def test_routine_and_params(self, emitter, name):
        routine, params = EXPECTED[name]
        table = emitter.materialize(WindowRegistry.get(name), SIZE)

        assert table.routine == routine, name
        assert table.params == params, name

    def test_the_expected_table_covers_the_catalogue(self):
        """Una finestra nuova senza attesi qui non e' coperta dalla suite."""
        assert set(EXPECTED) == set(WindowRegistry.WINDOWS)

    def test_alias_translates_as_its_canonical(self, emitter):
        assert emitter.materialize(WindowRegistry.get('triangle'), SIZE) == \
            emitter.materialize(WindowRegistry.get('bartlett'), SIZE)

    def test_gen_table_is_comparable_by_value(self, emitter):
        assert emitter.materialize(WindowRegistry.get('hanning'), SIZE) == \
            GenTable(routine=20, params=(2, 1))


# =============================================================================
# 2. LA RISOLUZIONE ENTRA NELLA TRADUZIONE (GEN16)
# =============================================================================

class TestResolution:
    """GEN16 descrive un segmento alla volta e la sua durata e' in *punti*:
    e' un numero che il catalogo non puo' dichiarare, perche' dipende dalla
    tabella che il target sta scrivendo."""

    @pytest.mark.parametrize("size", [128, 512, 2048, 8192])
    def test_gen16_segment_is_the_table_size(self, emitter, size):
        table = emitter.materialize(WindowRegistry.get('expodec'), size)

        assert table.params == (1, size, 4, 0)

    @pytest.mark.parametrize("size", [128, 8192])
    def test_gen20_ignores_the_resolution(self, emitter, size):
        """Le GEN20 riempiono la tabella che trovano: la loro traduzione non
        dipende dalla dimensione."""
        assert emitter.materialize(WindowRegistry.get('hanning'), size) == \
            emitter.materialize(WindowRegistry.get('hanning'), SIZE)

    @pytest.mark.parametrize("size", [256, 4096])
    def test_every_asymmetric_window_follows_the_size(self, emitter, size):
        for spec in WindowRegistry.get_by_family('asymmetric'):
            table = emitter.materialize(spec, size)
            assert table.params[1] == size, spec.name


# =============================================================================
# 3. LA COPERTURA E' PARZIALE, E LO DICE
# =============================================================================

class TestCoverage:

    def test_the_catalogue_is_fully_covered(self, emitter):
        assert emitter.uncovered_names() == []

    def test_an_unknown_cosine_sum_is_not_supported(self, emitter):
        """GEN20 e' un menu chiuso: hamming, hanning, blackman e
        blackman-harris hanno la loro opzione, una somma di coseni qualsiasi
        no."""
        nuttall = WindowSpec(
            name='nuttall',
            shape=WindowShape.COSINE_SUM,
            coefficients=(0.355768, 0.487396, 0.144232, 0.012604),
            description="Nuttall window",
        )

        assert emitter.supports(nuttall) is False

        with pytest.raises(InvalidWindowError) as exc_info:
            emitter.materialize(nuttall, SIZE)
        assert 'csound' in str(exc_info.value)

    def test_an_unknown_gaussian_openness_is_not_supported(self, emitter):
        """La divergenza dichiarata numero 1: fra sigma e apertura GEN20 non
        c'e' una formula che possiamo derivare, quindi c'e' una tabella -- e
        fuori dalla tabella si dichiara, non si inventa."""
        wide = WindowSpec(
            name='gaussian_wide',
            shape=WindowShape.GAUSSIAN,
            params={'sigma': 0.9},
            description="Gaussian window (sigma 0.9)",
        )

        assert emitter.supports(wide) is False

    def test_any_kaiser_beta_is_supported(self, emitter):
        """L'altra meta' del confronto: per Kaiser i due target parlano della
        stessa grandezza, beta e' beta, e la traduzione e' l'identita'."""
        sharp = WindowSpec(
            name='kaiser_sharp',
            shape=WindowShape.KAISER,
            params={'beta': 14.0},
            description="Kaiser window (beta 14)",
        )

        assert emitter.supports(sharp) is True
        assert emitter.materialize(sharp, SIZE).params == (7, 1, 14.0)

    def test_any_exponential_segment_is_supported(self, emitter):
        """GEN16 prende i valori che le dai: la famiglia asimmetrica e'
        parametrica per davvero, non un menu."""
        odd = WindowSpec(
            name='odd_curve',
            shape=WindowShape.EXPONENTIAL_SEGMENT,
            params={'start': 0.25, 'curve': 2.5, 'end': 0.75},
            description="Curva qualsiasi",
            family="asymmetric",
            symmetry='asymmetric',
        )

        assert emitter.supports(odd) is True
        assert emitter.materialize(odd, 64).params == (0.25, 64, 2.5, 0.75)
