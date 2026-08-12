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
  4. Properties (mode, range)
  5. Integrazione Envelope
  6. range + deviation_probability (uniforme per tutte le unità, edo incluso)
  7. Edge cases e clamping ai bounds
  8. base_value della strategy
  9. __repr__
"""

import pytest
import math
from pge.controllers.pitch_controller import PitchController
from pge.envelopes.envelope import Envelope
from pge.shared.exceptions import InvalidFieldValueError


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
        assert _pc(mock_config, {'edo': 31, 'value': 4}).mode == 'edo'

    def test_default_no_key_is_semitones_unison(self, mock_config):
        # nessuna chiave-unità → semitoni con valore neutro → ratio 1.0
        pc = _pc(mock_config, {})
        assert pc.mode == 'semitones'
        assert pc.calculate(0.0) == pytest.approx(1.0)

    def test_default_only_range_is_semitones(self, mock_config):
        # solo `range` (config, non unità) → resta default semitoni con base neutra
        pc = _pc(mock_config, {'range': 5.0})
        assert pc.mode == 'semitones'
        assert pc.value == pytest.approx(0.0)
        assert pc.range == pytest.approx(5.0)

    def test_default_contract_is_semitones_neutral(self, mock_config):
        # Decisione esplicita (coerente col modello voci EdoUnit(12)): il default
        # senza blocco pitch è unità semitones con valore neutro 0.0 → ratio 1.0.
        # Contratto esposto: value=0.0 (neutro), unità semitones.
        pc = _pc(mock_config, {})
        assert pc.mode == 'semitones'
        assert pc.calculate(0.0) == pytest.approx(1.0)
        assert pc.value == pytest.approx(0.0)
        assert pc.unit.name == 'semitones'

    @pytest.mark.parametrize("params", [
        {'semitones': 12.0, 'cents': 50.0},
        {'ratio': 2.0, 'semitones': 12.0},
        {'cents': 50.0, 'quarter_tone': 1.0},
        {'edo': 31, 'value': 4, 'semitones': 12.0},
    ])
    def test_multiple_unit_keys_raises(self, mock_config, params):
        # ambiguità esplicita, niente priorità silenziosa
        with pytest.raises(InvalidFieldValueError):
            _pc(mock_config, params)

    def test_typo_unit_key_raises_not_silent_default(self, mock_config):
        # `semitone` (refuso di `semitones`) non è una chiave nota:
        # niente silent default a semitoni neutri, deve sollevare.
        with pytest.raises(InvalidFieldValueError):
            _pc(mock_config, {'semitone': 12.0})

    def test_unknown_key_beside_valid_unit_raises(self, mock_config):
        # unità valida + chiave ignota nello stesso blocco → errore,
        # la chiave extra non viene silenziosamente ignorata.
        with pytest.raises(InvalidFieldValueError):
            _pc(mock_config, {'semitones': 12.0, 'cnts': 5.0})

    def test_valid_unit_with_range_no_false_positive(self, mock_config):
        # `range` è modificatore ammesso: nessun falso positivo.
        pc = _pc(mock_config, {'ratio': 2.0, 'range': 0.1})
        assert pc.mode == 'ratio'
        assert pc.range == pytest.approx(0.1)

    def test_unknown_key_error_lists_valid_keys(self, mock_config):
        # il messaggio deve guidare: elenca le chiavi valide del blocco.
        with pytest.raises(InvalidFieldValueError) as exc:
            _pc(mock_config, {'semitone': 12.0})
        msg = exc.value.user_message()
        assert 'semitones' in msg and 'range' in msg

    @pytest.mark.parametrize("params", [
        None,                              # `pitch:` vuoto nello YAML (None)
        [[0, -1200], [1, 1200]],           # `pitch: [[...]]` lista (non-mapping)
        3.0,                               # `pitch: 3.0` scalare (non-mapping)
    ])
    def test_none_or_non_mapping_pitch_block_raises(self, mock_config, params):
        # Un blocco pitch presente ma vuoto (`pitch:` → None) o non-mapping
        # (lista/scalare) è un errore di dominio esplicito: niente silent default
        # a ratio 1.0 (No Silent Failures) e mai un TypeError grezzo. Per nessuna
        # trasposizione si omette del tutto il blocco. NB: `pitch: {}` e blocco
        # assente arrivano entrambi come `{}` (default di Stream) → restano
        # default semitoni, vedi test_default_*.
        with pytest.raises(InvalidFieldValueError):
            _pc(mock_config, params)

    def test_empty_pitch_block_error_has_hint(self, mock_config):
        # L'errore deve guidare l'utente con un hint non vuoto, coerente con le
        # altre violazioni del blocco pitch.
        with pytest.raises(InvalidFieldValueError) as exc:
            _pc(mock_config, None)
        assert exc.value.user_message()


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
# GRUPPO 5: EDO FLAT (edo: N + value: X)
# =============================================================================

class TestPitchEdoBase:

    def test_edo_octave(self, mock_config):
        pc = _pc(mock_config, {'edo': 31, 'value': 31})
        assert pc.mode == 'edo'
        assert pc.calculate(0.0) == pytest.approx(2.0)

    def test_edo_partial(self, mock_config):
        assert _pc(mock_config, {'edo': 24, 'value': 12}).calculate(0.0) == pytest.approx(2 ** 0.5)

    def test_edo_value_ratio(self, mock_config):
        # forma canonica: edo: 31 + value: 18 → 2^(18/31)
        assert _pc(mock_config, {'edo': 31, 'value': 18}).calculate(0.0) == pytest.approx(2 ** (18 / 31))

    def test_edo_invalid_divisions_raises(self, mock_config):
        with pytest.raises(InvalidFieldValueError):
            _pc(mock_config, {'edo': 0, 'value': 1})

    def test_edo_missing_value_raises(self, mock_config):
        # `edo: N` senza `value` a fianco → errore esplicito
        with pytest.raises(InvalidFieldValueError):
            _pc(mock_config, {'edo': 31})

    def test_edo_nested_form_is_hard_break(self, mock_config):
        # la vecchia forma annidata {divisions, value} non è più valida:
        # deve sollevare con hint di migrazione, non passare silenziosa.
        with pytest.raises(InvalidFieldValueError) as exc:
            _pc(mock_config, {'edo': {'divisions': 31, 'value': 4}})
        assert 'edo' in exc.value.user_message()

    def test_value_with_preset_raises(self, mock_config):
        # `value` è ammesso solo con `edo: N`; per i preset il valore sta
        # nella chiave (es. semitones: 7) → value a fianco è ambiguo.
        with pytest.raises(InvalidFieldValueError):
            _pc(mock_config, {'semitones': 7, 'value': 3})

    def test_value_without_unit_raises(self, mock_config):
        # `value` da solo (nessuna unità) → errore, non default silenzioso.
        with pytest.raises(InvalidFieldValueError):
            _pc(mock_config, {'value': 3})

    def test_edo_range_property_safe(self, mock_config):
        pc = _pc(mock_config, {'edo': 31, 'value': 4})
        assert pc.range == 0.0


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
        pc = _pc(mock_config, {'edo': 12, 'value': [[0, 0.0], [10, 12.0]]})
        assert pc.calculate(0.0) == pytest.approx(1.0)
        assert pc.calculate(10.0) == pytest.approx(2.0)


# =============================================================================
# GRUPPO 9: RANGE + DEVIATION_PROBABILITY UNIFORME (anche edo)
# =============================================================================

class TestRangeUniform:
    """Tutte le unità leggono `range` dal blocco — edo incluso (il vecchio
    ramo speciale lo ignorava)."""

    @pytest.mark.parametrize("params,expected_range", [
        ({'semitones': 0.0, 'range': 6.0}, 6.0),
        ({'cents': 0.0, 'range': 100.0}, 100.0),
        ({'ratio': 1.0, 'range': 1.5}, 1.5),
        ({'edo': 31, 'value': 4, 'range': 6.0}, 6.0),
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
        from pge.shared.exceptions import ParameterBoundError
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
        assert 'PitchController' in repr(_pc(mock_config, {'edo': 31, 'value': 4}))
