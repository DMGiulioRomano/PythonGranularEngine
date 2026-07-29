"""
test_range_anchor_wiring.py

Cablaggio di `range_anchor` dallo YAML per-stream fino al singolo Parameter:

    YAML stream  →  StreamConfig.range_anchor
                 →  GranularParser
                 →  Parameter
                 →  DistributionStrategy(anchor=...)

Coverage:
1. StreamConfig — campo, default, lettura da YAML
2. Parameter — inoltro dell'ancora alla distribuzione
3. Modalita' 'min' — la banda di un range esplicito e' [base, base+range]
4. Jitter implicito — resta SEMPRE centrato, anche con anchor='min'
5. Pitch quantizzato — segue l'ancora senza modifiche a VariationStrategy
6. GranularParser — propaga l'ancora ai Parameter che costruisce
"""

import random

import pytest

from pge.core.stream_config import StreamConfig, StreamContext
from pge.parameters.parameter import Parameter
from pge.parameters.parameter_definitions import ParameterBounds
from pge.parameters.parser import GranularParser
from pge.shared.distribution_strategy import ANCHOR_CENTER, ANCHOR_MIN
from pge.shared.probability_gate import AlwaysGate


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def bounds():
    """Bounds larghi: isolano la semantica della banda dal safety clamp."""
    return ParameterBounds(
        min_val=-10000.0,
        max_val=10000.0,
        min_range=0.0,
        max_range=1000.0,
        default_jitter=0.0,
    )


@pytest.fixture
def jitter_bounds():
    """Bounds con jitter implicito: nessun range esplicito nello YAML."""
    return ParameterBounds(
        min_val=-10000.0,
        max_val=10000.0,
        min_range=0.0,
        max_range=1000.0,
        default_jitter=4.0,
    )


def make_param(bounds, anchor, mod_range, seed=1234, distribution='uniform'):
    """Parameter con gate sempre aperto e RNG seedato."""
    param = Parameter(
        name='test_param',
        value=300.0,
        bounds=bounds,
        mod_range=mod_range,
        distribution_mode=distribution,
        range_anchor=anchor,
        rng=random.Random(seed),
    )
    param.set_probability_gate(AlwaysGate())
    return param


# =============================================================================
# 1. STREAMCONFIG
# =============================================================================

class TestStreamConfigField:

    def test_default_is_center(self):
        assert StreamConfig().range_anchor == ANCHOR_CENTER

    def test_read_from_yaml(self):
        context = StreamContext(
            stream_id='s1', onset=0.0, duration=10.0,
            sample='x.wav', sample_dur_sec=5.0,
        )
        config = StreamConfig.from_yaml({'range_anchor': 'min'}, context)

        assert config.range_anchor == ANCHOR_MIN

    def test_absent_from_yaml_keeps_default(self):
        context = StreamContext(
            stream_id='s1', onset=0.0, duration=10.0,
            sample='x.wav', sample_dur_sec=5.0,
        )
        config = StreamConfig.from_yaml({'volume': -6.0}, context)

        assert config.range_anchor == ANCHOR_CENTER


# =============================================================================
# 2. PARAMETER — INOLTRO DELL'ANCORA
# =============================================================================

class TestParameterForwardsAnchor:

    def test_default_anchor_is_center(self, bounds):
        param = Parameter('p', 1.0, bounds)

        assert param._distribution.anchor == ANCHOR_CENTER

    def test_anchor_reaches_distribution(self, bounds):
        param = Parameter('p', 1.0, bounds, range_anchor=ANCHOR_MIN)

        assert param._distribution.anchor == ANCHOR_MIN


# =============================================================================
# 3. RANGE ESPLICITO IN MODALITA' 'min'
# =============================================================================

class TestExplicitRangeAnchorMin:

    def test_band_starts_at_base(self, bounds):
        """base = 300, range = 200 → [300, 500]."""
        param = make_param(bounds, ANCHOR_MIN, mod_range=200.0)

        values = [param.get_value(0.0) for _ in range(2000)]

        assert min(values) >= 300.0
        assert max(values) <= 500.0

    def test_center_mode_is_symmetric(self, bounds):
        """Il default resta [base - range/2, base + range/2]."""
        param = make_param(bounds, ANCHOR_CENTER, mod_range=200.0)

        values = [param.get_value(0.0) for _ in range(2000)]

        assert min(values) >= 200.0
        assert max(values) <= 400.0

    def test_min_is_center_shifted_by_half_range(self, bounds):
        """Stesso seed: la banda 'min' e' la banda 'center' traslata di
        range/2. Verifica che l'ancora sposti e basta (per uniform)."""
        centered = make_param(bounds, ANCHOR_CENTER, mod_range=200.0, seed=77)
        anchored = make_param(bounds, ANCHOR_MIN, mod_range=200.0, seed=77)

        for _ in range(200):
            assert anchored.get_value(0.0) == pytest.approx(
                centered.get_value(0.0) + 100.0
            )

    def test_gaussian_min_stays_in_band(self, bounds):
        param = make_param(bounds, ANCHOR_MIN, mod_range=200.0,
                           distribution='gaussian')

        values = [param.get_value(0.0) for _ in range(3000)]

        assert min(values) >= 300.0
        assert max(values) <= 500.0

    def test_zero_range_is_noop(self, bounds):
        param = make_param(bounds, ANCHOR_MIN, mod_range=0.0)

        assert all(param.get_value(0.0) == 300.0 for _ in range(50))


# =============================================================================
# 4. JITTER IMPLICITO — SEMPRE CENTRATO
# =============================================================================

class TestImplicitJitterStaysCentred:
    """Il jitter implicito (`ParameterBounds.default_jitter`, attivo quando
    l'utente NON ha dichiarato un range) e' un tremolio simmetrico attorno al
    valore, non una banda dichiarata: `range_anchor` non lo tocca.

    Senza questa regola ogni parametro con jitter acquisterebbe un bias
    sistematico verso l'alto per il solo fatto di stare su uno stream in
    modalita' 'min'.
    """

    def test_jitter_is_symmetric_in_min_mode(self, jitter_bounds):
        param = make_param(jitter_bounds, ANCHOR_MIN, mod_range=None)

        values = [param.get_value(0.0) for _ in range(3000)]

        assert min(values) < 300.0, "il jitter deve poter scendere sotto base"
        assert max(values) > 300.0
        assert sum(values) / len(values) == pytest.approx(300.0, abs=0.15)

    def test_jitter_bit_identical_between_modes(self, jitter_bounds):
        """Stesso seed, stessa sequenza: la modalita' non e' osservabile
        quando il range e' implicito."""
        centered = make_param(jitter_bounds, ANCHOR_CENTER, mod_range=None, seed=42)
        anchored = make_param(jitter_bounds, ANCHOR_MIN, mod_range=None, seed=42)

        for _ in range(500):
            assert anchored.get_value(0.0) == centered.get_value(0.0)

    def test_explicit_zero_range_is_not_jitter(self, jitter_bounds):
        """range esplicito a 0 disattiva il jitter (has_explicit_range)."""
        param = make_param(jitter_bounds, ANCHOR_MIN, mod_range=0.0)

        assert all(param.get_value(0.0) == 300.0 for _ in range(50))


# =============================================================================
# 5. PITCH QUANTIZZATO
# =============================================================================

class TestQuantizedVariationFollowsAnchor:
    """QuantizedVariation campiona attorno a 0 e somma dopo
    (`base + round(sample(0, range))`): con l'ancora dentro la distribuzione
    segue la modalita' senza che VariationStrategy sappia nulla."""

    @pytest.fixture
    def quantized_bounds(self):
        return ParameterBounds(
            min_val=-36.0,
            max_val=36.0,
            min_range=0.0,
            max_range=36.0,
            variation_mode='quantized',
        )

    def test_min_mode_never_goes_below_base(self, quantized_bounds):
        param = Parameter(
            name='pitch', value=0.0, bounds=quantized_bounds,
            mod_range=12.0, range_anchor=ANCHOR_MIN,
            rng=random.Random(9),
        )
        param.set_probability_gate(AlwaysGate())

        values = [param.get_value(0.0) for _ in range(2000)]

        assert min(values) >= 0.0
        assert max(values) <= 12.0

    def test_center_mode_still_symmetric(self, quantized_bounds):
        param = Parameter(
            name='pitch', value=0.0, bounds=quantized_bounds,
            mod_range=12.0, range_anchor=ANCHOR_CENTER,
            rng=random.Random(9),
        )
        param.set_probability_gate(AlwaysGate())

        values = [param.get_value(0.0) for _ in range(2000)]

        assert min(values) < 0.0
        assert max(values) > 0.0

    def test_values_stay_integer_steps(self, quantized_bounds):
        param = Parameter(
            name='pitch', value=0.0, bounds=quantized_bounds,
            mod_range=12.0, range_anchor=ANCHOR_MIN,
            rng=random.Random(9),
        )
        param.set_probability_gate(AlwaysGate())

        assert all(v == int(v) for v in (param.get_value(0.0) for _ in range(200)))


# =============================================================================
# 6. GRANULARPARSER
# =============================================================================

class TestParserPropagatesAnchor:

    def _parser(self, anchor):
        context = StreamContext(
            stream_id='s1', onset=0.0, duration=10.0,
            sample='x.wav', sample_dur_sec=5.0,
        )
        config = StreamConfig.from_yaml({'range_anchor': anchor}, context)
        return GranularParser(config)

    def test_parser_reads_anchor(self):
        assert self._parser('min').range_anchor == ANCHOR_MIN

    def test_parser_defaults_to_center(self):
        context = StreamContext(
            stream_id='s1', onset=0.0, duration=10.0,
            sample='x.wav', sample_dur_sec=5.0,
        )
        parser = GranularParser(StreamConfig.from_yaml({}, context))

        assert parser.range_anchor == ANCHOR_CENTER

    def test_built_parameter_carries_anchor(self):
        param = self._parser('min').parse_parameter('volume', -6.0, 4.0)

        assert param._distribution.anchor == ANCHOR_MIN
