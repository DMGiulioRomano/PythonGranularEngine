"""
test_pitch_controller.py

Test suite per PitchController (modello unit-driven).

Il blocco pitch è espresso da UN'unica chiave-unità tra
{semitones, cents, quarter_tone, eighth_tone, edo, ratio}. L'unità
(PitchUnit) è la singola fonte di verità: conversione, bounds e variation_mode.

Coverage:
  1. Selezione unità (default, chiavi multiple → errore)
  2. calculate() ratio / semitoni / cents / quarti / ottavi / edo
  3. Compensazione grain_reverse
  4. Properties (mode, base_ratio, base_semitones, range)
  5. Integrazione Envelope
  6. range + dephase (uniforme per tutte le unità, edo incluso)
  7. Edge cases e clamping ai bounds
  8. base_value della strategy
  9. __repr__
"""

import pytest
import math
from controllers.pitch_controller import PitchController
from envelopes.envelope import Envelope
from shared.exceptions import InvalidFieldValueError


def _pc(mock_config, params):
    """Helper: PitchController reale dal blocco YAML pitch."""
    return PitchController(params, mock_config)


# =============================================================================
# GRUPPO 1: SELEZIONE UNITÀ
# =============================================================================

class TestUnitSelection:
    """Una sola chiave-unità per blocco; default semitoni; >1 → errore."""

    def test_ratio_mode(self, mock_config):
        assert _pc(mock_config, {'ratio': 2.0}).mode == 'ratio'

    def test_semitones_mode(self, mock_config):
        assert _pc(mock_config, {'semitones': 12.0}).mode == 'semitones'

    def test_cents_mode(self, mock_config):
        assert _pc(mock_config, {'cents': 50.0}).mode == 'cents'

    def test_quarter_tone_mode(self, mock_config):
        assert _pc(mock_config, {'quarter_tone': 1.0}).mode == 'quarter_tone'

    def test_eighth_tone_mode(self, mock_config):
        assert _pc(mock_config, {'eighth_tone': 1.0}).mode == 'eighth_tone'

    def test_edo_mode(self, mock_config):
        assert _pc(mock_config, {'edo': {'divisions': 31, 'value': 4}}).mode == 'edo'

    def test_default_no_key_is_semitones_unison(self, mock_config):
        # nessuna chiave-unità → semitoni con valore neutro → ratio 1.0
        pc = _pc(mock_config, {})
        assert pc.mode == 'semitones'
        assert pc.calculate(0.0) == pytest.approx(1.0)

    def test_default_only_range_is_semitones(self, mock_config):
        # solo `range` (config, non unità) → resta default semitoni con base neutra
        pc = _pc(mock_config, {'range': 5.0})
        assert pc.mode == 'semitones'
        assert pc.base_semitones == pytest.approx(0.0)
        assert pc.range == pytest.approx(5.0)

    @pytest.mark.parametrize("params", [
        {'semitones': 12.0, 'cents': 50.0},
        {'ratio': 2.0, 'semitones': 12.0},
        {'cents': 50.0, 'quarter_tone': 1.0},
        {'edo': {'divisions': 31, 'value': 4}, 'semitones': 12.0},
    ])
    def test_multiple_unit_keys_raises(self, mock_config, params):
        # ambiguità esplicita, niente priorità silenziosa
        with pytest.raises(InvalidFieldValueError):
            _pc(mock_config, params)


# =============================================================================
# GRUPPO 2: CALCULATE - RATIO
# =============================================================================

class TestCalculateRatio:

    @pytest.mark.parametrize("ratio,expected", [(1.0, 1.0), (2.0, 2.0), (0.5, 0.5)])
    def test_ratio_returns_value(self, mock_config, ratio, expected):
        assert _pc(mock_config, {'ratio': ratio}).calculate(0.0) == pytest.approx(expected)

    def test_ratio_constant_over_time(self, mock_config):
        pc = _pc(mock_config, {'ratio': 1.5})
        for t in [0.0, 1.0, 5.0, 9.0]:
            assert pc.calculate(t) == pytest.approx(1.5)


# =============================================================================
# GRUPPO 3: CALCULATE - SEMITONI (INTERVALLI MUSICALI)
# =============================================================================

class TestMusicalIntervals:

    @pytest.mark.parametrize("semitones,expected,name", [
        (0, 1.0, "unisono"),
        (1, 2 ** (1/12), "seconda minore"),
        (4, 2 ** (4/12), "terza maggiore"),
        (7, 2 ** (7/12), "quinta giusta"),
        (12, 2.0, "ottava"),
        (24, 4.0, "doppia ottava"),
        (-12, 0.5, "ottava sotto"),
        (-24, 0.25, "doppia ottava sotto"),
    ])
    def test_interval(self, mock_config, semitones, expected, name):
        pc = _pc(mock_config, {'semitones': float(semitones)})
        assert pc.calculate(0.0) == pytest.approx(expected, rel=1e-6), name

    def test_symmetry_up_down(self, mock_config):
        for st in [1, 3, 5, 7, 12, 24]:
            up = _pc(mock_config, {'semitones': float(st)}).calculate(0.0)
            down = _pc(mock_config, {'semitones': float(-st)}).calculate(0.0)
            assert up * down == pytest.approx(1.0)


# =============================================================================
# GRUPPO 4: NUOVE UNITÀ EDO (cents / quarti / ottavi)
# =============================================================================

class TestEdoFamilyUnits:

    def test_cents_50(self, mock_config):
        assert _pc(mock_config, {'cents': 50.0}).calculate(0.0) == pytest.approx(2 ** (50.0/1200.0))

    def test_quarter_tone_half_octave(self, mock_config):
        assert _pc(mock_config, {'quarter_tone': 12.0}).calculate(0.0) == pytest.approx(2 ** 0.5)

    def test_eighth_tone_half_octave(self, mock_config):
        assert _pc(mock_config, {'eighth_tone': 24.0}).calculate(0.0) == pytest.approx(2 ** 0.5)

    def test_cents_full_octave(self, mock_config):
        assert _pc(mock_config, {'cents': 1200.0}).calculate(0.0) == pytest.approx(2.0)


# =============================================================================
# GRUPPO 5: EDO PARAMETRICO ({divisions, value})
# =============================================================================

class TestPitchEdoBase:

    def test_edo_octave(self, mock_config):
        pc = _pc(mock_config, {'edo': {'divisions': 31, 'value': 31}})
        assert pc.mode == 'edo'
        assert pc.calculate(0.0) == pytest.approx(2.0)

    def test_edo_partial(self, mock_config):
        assert _pc(mock_config, {'edo': {'divisions': 24, 'value': 12}}).calculate(0.0) == pytest.approx(2 ** 0.5)

    def test_edo_invalid_divisions_raises(self, mock_config):
        with pytest.raises(InvalidFieldValueError):
            _pc(mock_config, {'edo': {'divisions': 0, 'value': 1}})

    def test_edo_malformed_missing_value_raises(self, mock_config):
        with pytest.raises(InvalidFieldValueError):
            _pc(mock_config, {'edo': {'divisions': 31}})

    def test_edo_range_property_safe(self, mock_config):
        pc = _pc(mock_config, {'edo': {'divisions': 31, 'value': 4}})
        assert pc.range == 0.0
        assert pc.base_ratio is None
        assert pc.base_semitones is None


# =============================================================================
# GRUPPO 6: GRAIN_REVERSE
# =============================================================================

class TestGrainReverse:

    @pytest.mark.parametrize("ratio,expected", [(1.0, -1.0), (2.0, -2.0)])
    def test_reverse_negates_ratio(self, mock_config, ratio, expected):
        assert _pc(mock_config, {'ratio': ratio}).calculate(0.0, grain_reverse=True) == pytest.approx(expected)

    def test_reverse_with_semitones(self, mock_config):
        assert _pc(mock_config, {'semitones': 12.0}).calculate(0.0, grain_reverse=True) == pytest.approx(-2.0)

    def test_reverse_default_is_false(self, mock_config):
        assert _pc(mock_config, {'ratio': 1.0}).calculate(0.0) == pytest.approx(1.0)


# =============================================================================
# GRUPPO 7: PROPERTIES
# =============================================================================

class TestProperties:

    def test_base_ratio_when_ratio_mode(self, mock_config):
        assert _pc(mock_config, {'ratio': 2.5}).base_ratio == 2.5

    def test_base_ratio_none_when_semitones_mode(self, mock_config):
        assert _pc(mock_config, {'semitones': 7.0}).base_ratio is None

    def test_base_semitones_when_semitones_mode(self, mock_config):
        assert _pc(mock_config, {'semitones': 7.0}).base_semitones == 7.0

    def test_base_semitones_none_when_ratio_mode(self, mock_config):
        assert _pc(mock_config, {'ratio': 2.0}).base_semitones is None

    def test_base_semitones_none_when_cents_mode(self, mock_config):
        # cents non è semitones: base_semitones None
        assert _pc(mock_config, {'cents': 50.0}).base_semitones is None

    def test_range_reflects_explicit_range(self, mock_config):
        assert _pc(mock_config, {'semitones': 0.0, 'range': 12.0}).range == pytest.approx(12.0)


# =============================================================================
# GRUPPO 8: INTEGRAZIONE ENVELOPE
# =============================================================================

class TestEnvelopeIntegration:

    def test_ratio_envelope_varies(self, mock_config):
        pc = _pc(mock_config, {'ratio': [[0, 1.0], [10, 2.0]]})
        assert pc.calculate(0.0) == pytest.approx(1.0)
        assert pc.calculate(5.0) == pytest.approx(1.5)
        assert pc.calculate(10.0) == pytest.approx(2.0)

    def test_semitones_envelope_varies(self, mock_config):
        pc = _pc(mock_config, {'semitones': [[0, 0.0], [10, 12.0]]})
        assert pc.calculate(0.0) == pytest.approx(1.0)
        assert pc.calculate(5.0) == pytest.approx(math.sqrt(2))
        assert pc.calculate(10.0) == pytest.approx(2.0)

    def test_edo_envelope_varies(self, mock_config):
        pc = _pc(mock_config, {'edo': {'divisions': 12, 'value': [[0, 0.0], [10, 12.0]]}})
        assert pc.calculate(0.0) == pytest.approx(1.0)
        assert pc.calculate(10.0) == pytest.approx(2.0)

    def test_base_ratio_is_envelope_object(self, mock_config):
        pc = _pc(mock_config, {'ratio': [[0, 1.0], [10, 2.0]]})
        assert isinstance(pc.base_ratio, Envelope)


# =============================================================================
# GRUPPO 9: RANGE + DEPHASE UNIFORME (anche edo)
# =============================================================================

class TestRangeUniform:
    """Tutte le unità leggono `range` dal blocco — edo incluso (il vecchio
    ramo speciale lo ignorava)."""

    @pytest.mark.parametrize("params,expected_range", [
        ({'semitones': 0.0, 'range': 6.0}, 6.0),
        ({'cents': 0.0, 'range': 100.0}, 100.0),
        ({'ratio': 1.0, 'range': 1.5}, 1.5),
        ({'edo': {'divisions': 31, 'value': 4}, 'range': 6.0}, 6.0),
    ])
    def test_range_registered_for_all_units(self, mock_config, params, expected_range):
        assert _pc(mock_config, params).range == pytest.approx(expected_range)


# =============================================================================
# GRUPPO 10: EDGE CASES / CLAMPING
# =============================================================================

class TestEdgeCases:

    def test_max_semitones(self, mock_config):
        assert _pc(mock_config, {'semitones': 36.0}).calculate(0.0) == pytest.approx(8.0)

    def test_min_semitones(self, mock_config):
        assert _pc(mock_config, {'semitones': -36.0}).calculate(0.0) == pytest.approx(0.125)

    def test_fractional_semitones(self, mock_config):
        assert _pc(mock_config, {'semitones': 6.5}).calculate(0.0) == pytest.approx(2.0 ** (6.5/12.0))

    def test_high_ratio_at_bound(self, mock_config):
        assert _pc(mock_config, {'ratio': 8.0}).calculate(0.0) == pytest.approx(8.0)

    def test_low_ratio_at_bound(self, mock_config):
        assert _pc(mock_config, {'ratio': 0.125}).calculate(0.0) == pytest.approx(0.125)

    def test_cents_beyond_three_octaves_raises(self, mock_config):
        # strict validation: 5000 cents > 3600 (bound EDO 1200) → errore
        from shared.exceptions import ParameterBoundError
        with pytest.raises(ParameterBoundError):
            _pc(mock_config, {'cents': 5000.0})


# =============================================================================
# GRUPPO 11: STRATEGY base_value
# =============================================================================

class TestStrategyBaseValue:

    def test_ratio_strategy_base_value(self, mock_config):
        assert _pc(mock_config, {'ratio': 1.5})._strategy.base_value == 1.5

    def test_semitones_strategy_base_value(self, mock_config):
        assert _pc(mock_config, {'semitones': 7.0})._strategy.base_value == 7.0

    def test_envelope_base_value(self, mock_config):
        pc = _pc(mock_config, {'semitones': [[0, 0.0], [10, 12.0]]})
        assert isinstance(pc._strategy.base_value, Envelope)


# =============================================================================
# GRUPPO 12: __repr__
# =============================================================================

class TestRepr:

    def test_repr_ratio(self, mock_config):
        assert 'PitchController' in repr(_pc(mock_config, {'ratio': 1.0}))

    def test_repr_edo(self, mock_config):
        assert 'PitchController' in repr(_pc(mock_config, {'edo': {'divisions': 31, 'value': 4}}))
