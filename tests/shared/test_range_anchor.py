"""
test_range_anchor.py

Test suite per l'ancora del range nelle DistributionStrategy.

`range_anchor` decide come una coppia (base, range) diventa una banda:

- 'center' (default, storico): la banda e' [base - range/2, base + range/2];
- 'min': la banda e' [base, base + range] — `base` e' il minimo e `range`
  la forbice di apertura verso l'alto (semantica di granulation-studies,
  `value_generators._band_at`).

Coverage:
1. Default 'center' — identita' bit-per-bit con il comportamento storico
2. Uniform in modalita' 'min' — banda [base, base+range]
3. Gaussian in modalita' 'min' — mu al centro banda, sigma = range/6, clamp
4. get_bounds coerente con l'ancora
5. Validazione dell'ancora sconosciuta
6. Edge case: spread <= 0 e' no-op in entrambe le modalita'
"""

import random

import pytest

from pge.shared.distribution_strategy import (
    ANCHOR_CENTER,
    ANCHOR_MIN,
    VALID_RANGE_ANCHORS,
    DistributionFactory,
    GaussianDistribution,
    UniformDistribution,
)
from pge.shared.exceptions import StrategyNotFoundError


# =============================================================================
# 1. DEFAULT 'center' — NESSUN CAMBIAMENTO
# =============================================================================

class TestDefaultAnchorIsCenter:
    """Il default e' 'center': il comportamento storico non cambia."""

    def test_uniform_default_anchor_is_center(self):
        assert UniformDistribution().anchor == ANCHOR_CENTER

    def test_gaussian_default_anchor_is_center(self):
        assert GaussianDistribution().anchor == ANCHOR_CENTER

    def test_factory_default_anchor_is_center(self):
        assert DistributionFactory.create('uniform').anchor == ANCHOR_CENTER

    def test_uniform_center_is_bit_identical_to_legacy_formula(self):
        """Il path 'center' resta la formula storica, bit per bit."""
        dist = UniformDistribution(rng=random.Random(1234), anchor=ANCHOR_CENTER)
        expected_rng = random.Random(1234)

        for _ in range(200):
            got = dist.sample(10.0, 4.0)
            expected = 10.0 + expected_rng.uniform(-0.5, 0.5) * 4.0
            assert got == expected

    def test_gaussian_center_is_bit_identical_to_legacy_formula(self):
        dist = GaussianDistribution(rng=random.Random(99), anchor=ANCHOR_CENTER)
        expected_rng = random.Random(99)

        for _ in range(200):
            got = dist.sample(10.0, 4.0)
            assert got == expected_rng.gauss(10.0, 4.0)


# =============================================================================
# 2. UNIFORM IN MODALITA' 'min'
# =============================================================================

class TestUniformAnchorMin:
    """Uniform con anchor='min': banda [base, base+range]."""

    def test_all_samples_inside_band(self):
        dist = UniformDistribution(rng=random.Random(7), anchor=ANCHOR_MIN)
        base, width = 300.0, 200.0

        for _ in range(2000):
            v = dist.sample(base, width)
            assert base <= v <= base + width

    def test_no_sample_below_base(self):
        """La promessa della modalita': mai sotto base."""
        dist = UniformDistribution(rng=random.Random(11), anchor=ANCHOR_MIN)

        assert all(dist.sample(1.0, 5.0) >= 1.0 for _ in range(2000))

    def test_mean_sits_at_band_centre(self):
        dist = UniformDistribution(rng=random.Random(3), anchor=ANCHOR_MIN)
        samples = [dist.sample(0.0, 10.0) for _ in range(20000)]

        assert abs(sum(samples) / len(samples) - 5.0) < 0.15

    def test_band_matches_granstudies_uniform_draw(self):
        """Fedelta' a granulation-studies `_draw`: rng.uniform(lo, hi)."""
        dist = UniformDistribution(rng=random.Random(555), anchor=ANCHOR_MIN)
        expected_rng = random.Random(555)
        base, width = 300.0, 200.0

        for _ in range(200):
            assert dist.sample(base, width) == expected_rng.uniform(base, base + width)

    def test_zero_spread_is_noop(self):
        dist = UniformDistribution(rng=random.Random(1), anchor=ANCHOR_MIN)

        assert dist.sample(42.0, 0.0) == 42.0

    def test_negative_spread_is_noop(self):
        dist = UniformDistribution(rng=random.Random(1), anchor=ANCHOR_MIN)

        assert dist.sample(42.0, -3.0) == 42.0


# =============================================================================
# 3. GAUSSIAN IN MODALITA' 'min'
# =============================================================================

class TestGaussianAnchorMin:
    """Gaussian con anchor='min': mu al centro banda, sigma = range/6, clamp.

    Allineata a granulation-studies (`value_generators._draw`): i bordi della
    banda cadono a 3 sigma e la coda fuori banda (~0.3%) si appiattisce
    sull'estremo invece di uscire.
    """

    def test_all_samples_inside_band(self):
        dist = GaussianDistribution(rng=random.Random(17), anchor=ANCHOR_MIN)
        base, width = 300.0, 200.0

        for _ in range(5000):
            v = dist.sample(base, width)
            assert base <= v <= base + width

    def test_no_sample_below_base(self):
        dist = GaussianDistribution(rng=random.Random(23), anchor=ANCHOR_MIN)

        assert all(dist.sample(1.0, 5.0) >= 1.0 for _ in range(5000))

    def test_mean_sits_at_band_centre(self):
        dist = GaussianDistribution(rng=random.Random(5), anchor=ANCHOR_MIN)
        samples = [dist.sample(300.0, 200.0) for _ in range(20000)]

        assert abs(sum(samples) / len(samples) - 400.0) < 2.0

    def test_sigma_is_one_sixth_of_width(self):
        """sigma = range/6: ~68% dei valori entro mu +/- range/6."""
        dist = GaussianDistribution(rng=random.Random(13), anchor=ANCHOR_MIN)
        base, width = 300.0, 200.0
        sigma = width / 6.0
        mu = base + width / 2.0

        samples = [dist.sample(base, width) for _ in range(20000)]
        within = sum(1 for v in samples if abs(v - mu) <= sigma)

        assert 0.66 < within / len(samples) < 0.70

    def test_matches_granstudies_gaussian_draw(self):
        """Fedelta' a granulation-studies `_draw` ramo gaussiano."""
        dist = GaussianDistribution(rng=random.Random(2026), anchor=ANCHOR_MIN)
        expected_rng = random.Random(2026)
        lo, hi = 300.0, 500.0
        mu, sigma = (lo + hi) / 2.0, (hi - lo) / 6.0

        for _ in range(300):
            expected = min(max(expected_rng.gauss(mu, sigma), lo), hi)
            assert dist.sample(lo, hi - lo) == expected

    def test_zero_spread_is_noop(self):
        dist = GaussianDistribution(rng=random.Random(1), anchor=ANCHOR_MIN)

        assert dist.sample(42.0, 0.0) == 42.0


# =============================================================================
# 4. get_bounds COERENTE CON L'ANCORA
# =============================================================================

class TestGetBoundsFollowsAnchor:

    def test_uniform_center_bounds_unchanged(self):
        dist = UniformDistribution(anchor=ANCHOR_CENTER)

        assert dist.get_bounds(10.0, 6.0) == (7.0, 13.0)

    def test_uniform_min_bounds_are_the_band(self):
        dist = UniformDistribution(anchor=ANCHOR_MIN)

        assert dist.get_bounds(10.0, 6.0) == (10.0, 16.0)

    def test_gaussian_center_bounds_unchanged(self):
        dist = GaussianDistribution(anchor=ANCHOR_CENTER)

        assert dist.get_bounds(10.0, 2.0) == (4.0, 16.0)

    def test_gaussian_min_bounds_are_the_band(self):
        """In 'min' la banda e' finita e il clamp la rende esatta."""
        dist = GaussianDistribution(anchor=ANCHOR_MIN)

        assert dist.get_bounds(10.0, 6.0) == (10.0, 16.0)


# =============================================================================
# 5. VALIDAZIONE
# =============================================================================

class TestAnchorValidation:

    def test_valid_anchors_registry(self):
        assert VALID_RANGE_ANCHORS == frozenset({ANCHOR_CENTER, ANCHOR_MIN})

    def test_unknown_anchor_raises(self):
        with pytest.raises(StrategyNotFoundError) as exc_info:
            UniformDistribution(anchor='minimo')

        assert 'minimo' in str(exc_info.value)

    def test_unknown_anchor_lists_available(self):
        with pytest.raises(StrategyNotFoundError) as exc_info:
            UniformDistribution(anchor='sotto')

        message = str(exc_info.value)
        assert ANCHOR_CENTER in message
        assert ANCHOR_MIN in message

    def test_factory_rejects_unknown_anchor(self):
        with pytest.raises(StrategyNotFoundError):
            DistributionFactory.create('uniform', anchor='bogus')

    def test_factory_forwards_anchor(self):
        dist = DistributionFactory.create('gaussian', anchor=ANCHOR_MIN)

        assert dist.anchor == ANCHOR_MIN
        assert isinstance(dist, GaussianDistribution)
