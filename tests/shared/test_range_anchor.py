# tests/shared/test_range_anchor.py
"""
test_range_anchor.py

Semantica dell'ancora del range nelle distribuzioni.

Contratto in tre frasi ortogonali:

1. `range` (lo `spread` delle distribuzioni) e' SEMPRE la larghezza della banda.
2. `distribution_mode` dice COME la banda viene riempita: `uniform` piatta,
   `gaussian` a campana con i bordi a 3 sigma (sigma = larghezza/6) e clamp
   ai bordi.
3. `range_anchor` dice DOVE sta `base` dentro la banda: `center` (default,
   banda `[base - range/2, base + range/2]`) o `min` (banda
   `[base, base + range]`).

Con `base = 300` e `range = 200`:

    uniform  + center -> 200..400 piatta
    uniform  + min    -> 300..500 piatta
    gaussian + center -> 200..400, picco a 300
    gaussian + min    -> 300..500, picco a 400
"""

import random

import pytest

from pge.shared.distribution_strategy import (
    ANCHOR_CENTER,
    ANCHOR_MIN,
    RANGE_ANCHORS,
    DistributionFactory,
    DistributionStrategy,
    GaussianDistribution,
    UniformDistribution,
)
from pge.shared.exceptions import InvalidFieldValueError


BASE = 300.0
WIDTH = 200.0
N = 2000


def _rng():
    return random.Random(20260729)


# =============================================================================
# 1. COSTANTI E VALIDAZIONE
# =============================================================================

class TestAnchorConstants:
    """Le ancore disponibili sono un'enumerazione chiusa e scopribile."""

    def test_anchor_values(self):
        assert ANCHOR_CENTER == 'center'
        assert ANCHOR_MIN == 'min'

    def test_range_anchors_registry(self):
        """RANGE_ANCHORS e' la lista che PGE-ls/PGE-ui possono leggere."""
        assert tuple(RANGE_ANCHORS) == (ANCHOR_CENTER, ANCHOR_MIN)

    def test_default_anchor_is_center(self):
        """Senza ancora esplicita si resta sul comportamento storico."""
        assert UniformDistribution().anchor == ANCHOR_CENTER
        assert GaussianDistribution().anchor == ANCHOR_CENTER
        assert DistributionFactory.create('uniform').anchor == ANCHOR_CENTER

    def test_invalid_anchor_raises(self):
        """Un'ancora sconosciuta e' un errore di configurazione YAML."""
        with pytest.raises(InvalidFieldValueError) as exc:
            UniformDistribution(anchor='massimo')

        assert 'range_anchor' in str(exc.value.field)
        assert 'massimo' in repr(exc.value.value)

    def test_invalid_anchor_from_factory_raises(self):
        with pytest.raises(InvalidFieldValueError):
            DistributionFactory.create('gaussian', anchor='min_value')

    def test_factory_propagates_anchor(self):
        dist = DistributionFactory.create('uniform', anchor=ANCHOR_MIN)

        assert dist.anchor == ANCHOR_MIN


# =============================================================================
# 2. BANDA — get_bounds e' la fonte di verita' della banda
# =============================================================================

class TestBandBounds:
    """get_bounds descrive la banda effettiva, per ogni combinazione."""

    def test_uniform_center_band(self):
        assert UniformDistribution().get_bounds(BASE, WIDTH) == (200.0, 400.0)

    def test_uniform_min_band(self):
        dist = UniformDistribution(anchor=ANCHOR_MIN)

        assert dist.get_bounds(BASE, WIDTH) == (300.0, 500.0)

    def test_gaussian_center_band(self):
        """La gaussiana non usa piu' la regola 3-sigma su `spread`: `spread`
        E' la larghezza, e i bordi cadono a 3 sigma perche' sigma = width/6."""
        assert GaussianDistribution().get_bounds(BASE, WIDTH) == (200.0, 400.0)

    def test_gaussian_min_band(self):
        dist = GaussianDistribution(anchor=ANCHOR_MIN)

        assert dist.get_bounds(BASE, WIDTH) == (300.0, 500.0)

    def test_zero_width_band_collapses_on_base(self):
        """Larghezza nulla: la banda e' il punto `base`, in entrambe le ancore."""
        for anchor in RANGE_ANCHORS:
            for cls in (UniformDistribution, GaussianDistribution):
                assert cls(anchor=anchor).get_bounds(BASE, 0.0) == (BASE, BASE)


# =============================================================================
# 3. UNIFORM
# =============================================================================

class TestUniformAnchor:

    def test_center_is_bit_identical_to_legacy_formula(self):
        """Il ramo default deve restare la stessa identica espressione."""
        expected = [
            BASE + random.Random(1).uniform(-0.5, 0.5) * WIDTH
        ]
        got = [UniformDistribution(rng=random.Random(1)).sample(BASE, WIDTH)]

        assert got == expected

    def test_min_never_below_base(self):
        dist = UniformDistribution(rng=_rng(), anchor=ANCHOR_MIN)

        samples = [dist.sample(BASE, WIDTH) for _ in range(N)]

        assert min(samples) >= BASE
        assert max(samples) <= BASE + WIDTH

    def test_min_covers_the_whole_band(self):
        """Piatta: dopo N draw deve avvicinarsi a entrambi i bordi."""
        dist = UniformDistribution(rng=_rng(), anchor=ANCHOR_MIN)

        samples = [dist.sample(BASE, WIDTH) for _ in range(N)]

        assert min(samples) < BASE + 0.05 * WIDTH
        assert max(samples) > BASE + 0.95 * WIDTH

    def test_min_mean_is_band_center(self):
        dist = UniformDistribution(rng=_rng(), anchor=ANCHOR_MIN)

        samples = [dist.sample(BASE, WIDTH) for _ in range(N)]
        mean = sum(samples) / len(samples)

        assert abs(mean - (BASE + WIDTH / 2)) < 0.05 * WIDTH

    def test_min_shifts_the_band_by_half_width(self):
        """Stesso RNG, stessa sequenza: min = center + width/2, esattamente."""
        centered = UniformDistribution(rng=random.Random(7))
        anchored = UniformDistribution(rng=random.Random(7), anchor=ANCHOR_MIN)

        for _ in range(50):
            assert (anchored.sample(BASE, WIDTH)
                    == pytest.approx(centered.sample(BASE, WIDTH) + WIDTH / 2))

    def test_zero_width_returns_base_in_both_anchors(self):
        for anchor in RANGE_ANCHORS:
            dist = UniformDistribution(rng=_rng(), anchor=anchor)

            assert dist.sample(BASE, 0.0) == BASE
            assert dist.sample(BASE, -5.0) == BASE


# =============================================================================
# 4. GAUSSIAN — banda troncata, `range` e' la larghezza
# =============================================================================

class TestGaussianBand:

    def test_center_stays_inside_the_band(self):
        """Il cambio di semantica: con range 200 su base 300 la gaussiana non
        esce piu' da 200..400 (prima sigma=200 la portava grosso modo 0..600)."""
        dist = GaussianDistribution(rng=_rng())

        samples = [dist.sample(BASE, WIDTH) for _ in range(N)]

        assert min(samples) >= BASE - WIDTH / 2
        assert max(samples) <= BASE + WIDTH / 2

    def test_center_peaks_on_base(self):
        """Campana centrata su `base`: la meta' centrale della banda raccoglie
        la maggioranza netta dei campioni (~68% entro 1 sigma = width/6)."""
        dist = GaussianDistribution(rng=_rng())

        samples = [dist.sample(BASE, WIDTH) for _ in range(N)]
        within_one_sigma = sum(
            1 for s in samples if abs(s - BASE) <= WIDTH / 6
        )

        assert 0.60 < within_one_sigma / N < 0.76

    def test_min_never_below_base(self):
        dist = GaussianDistribution(rng=_rng(), anchor=ANCHOR_MIN)

        samples = [dist.sample(BASE, WIDTH) for _ in range(N)]

        assert min(samples) >= BASE
        assert max(samples) <= BASE + WIDTH

    def test_min_peaks_on_band_center(self):
        dist = GaussianDistribution(rng=_rng(), anchor=ANCHOR_MIN)

        samples = [dist.sample(BASE, WIDTH) for _ in range(N)]
        mean = sum(samples) / len(samples)

        assert abs(mean - (BASE + WIDTH / 2)) < 0.02 * WIDTH

    def test_sigma_is_one_sixth_of_the_width(self):
        """I bordi della banda cadono a 3 sigma: e' la definizione scelta."""
        dist = GaussianDistribution(rng=_rng())

        samples = [dist.sample(BASE, WIDTH) for _ in range(N)]
        mean = sum(samples) / len(samples)
        var = sum((s - mean) ** 2 for s in samples) / len(samples)

        assert var ** 0.5 == pytest.approx(WIDTH / 6, rel=0.12)

    def test_tails_are_clamped_not_dropped(self):
        """La coda oltre 3 sigma si appiattisce sul bordo invece di uscire:
        con una banda strettissima i bordi devono comparire davvero."""
        dist = GaussianDistribution(rng=_rng(), anchor=ANCHOR_MIN)

        samples = [dist.sample(0.0, 1.0) for _ in range(20000)]

        assert min(samples) == 0.0 or max(samples) == 1.0

    def test_zero_width_returns_base_in_both_anchors(self):
        for anchor in RANGE_ANCHORS:
            dist = GaussianDistribution(rng=_rng(), anchor=anchor)

            assert dist.sample(BASE, 0.0) == BASE
            assert dist.sample(BASE, -5.0) == BASE


# =============================================================================
# 5. ESTENSIBILITA' — le distribuzioni di terze parti non si rompono
# =============================================================================

class TestThirdPartyDistributions:
    """`DistributionFactory.register` e' superficie pubblica: una distribuzione
    esterna che non conosce l'ancora deve continuare a costruirsi."""

    def test_registered_distribution_without_anchor_awareness(self):
        class ConstantDistribution(DistributionStrategy):
            def sample(self, center, spread):
                return center

            @property
            def name(self):
                return "constant"

            def get_bounds(self, center, spread):
                return (center, center)

        DistributionFactory.register('constant_test', ConstantDistribution)
        try:
            dist = DistributionFactory.create('constant_test', anchor=ANCHOR_MIN)

            assert dist.sample(BASE, WIDTH) == BASE
            assert dist.anchor == ANCHOR_MIN
        finally:
            DistributionFactory._registry.pop('constant_test', None)
