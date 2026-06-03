# tests/parameters/test_pitch_unit.py
"""
Test suite per pitch_unit.py — astrazione unità di misura del pitch.

Modulo sotto test:
- EdoUnit(N): conversione 2^(v/N) (semitoni=12, cents=1200, quarti=24, ottavi=48)
- RatioUnit: identità (moltiplicatore diretto)
- make_pitch_unit(spec): factory da preset stringa / {edo: N} / None (default semitoni)
"""

import pytest

from parameters.pitch_unit import EdoUnit, RatioUnit, make_pitch_unit
from shared.exceptions import InvalidFieldValueError


# =============================================================================
# EdoUnit.to_ratio
# =============================================================================

def test_edo12_octave_is_double():
    # 12 semitoni = un'ottava = ratio 2.0
    assert EdoUnit(12).to_ratio(12) == pytest.approx(2.0)


@pytest.mark.parametrize("divisions", [12, 24, 48, 1200, 31])
def test_edo_full_octave_is_double(divisions):
    # value == divisions -> sempre un'ottava, per qualsiasi N
    assert EdoUnit(divisions).to_ratio(divisions) == pytest.approx(2.0)


@pytest.mark.parametrize("divisions", [12, 24, 48, 1200, 31])
def test_edo_zero_is_unison(divisions):
    # value 0 -> nessuna trasposizione = ratio 1.0 (identità esponenziale)
    assert EdoUnit(divisions).to_ratio(0) == pytest.approx(1.0)


def test_edo_negative_descends():
    # -12 semitoni = un'ottava sotto = 0.5
    assert EdoUnit(12).to_ratio(-12) == pytest.approx(0.5)


# =============================================================================
# RatioUnit.to_ratio
# =============================================================================

def test_ratio_unit_is_identity():
    assert RatioUnit().to_ratio(1.5) == pytest.approx(1.5)
    assert RatioUnit().to_ratio(1.0) == pytest.approx(1.0)


# =============================================================================
# make_pitch_unit — factory
# =============================================================================

@pytest.mark.parametrize("preset,divisions", [
    ("semitones", 12),
    ("cents", 1200),
    ("quarter_tone", 24),
    ("eighth_tone", 48),
])
def test_factory_exponential_presets(preset, divisions):
    unit = make_pitch_unit(preset)
    assert isinstance(unit, EdoUnit)
    assert unit.divisions == divisions


def test_factory_ratio_preset():
    assert isinstance(make_pitch_unit("ratio"), RatioUnit)


def test_factory_edo_dict():
    unit = make_pitch_unit({"edo": 31})
    assert isinstance(unit, EdoUnit)
    assert unit.divisions == 31


def test_factory_default_is_semitones():
    # spec None (unit assente in YAML) -> semitoni, retrocompatibile
    unit = make_pitch_unit(None)
    assert isinstance(unit, EdoUnit)
    assert unit.divisions == 12


# =============================================================================
# Errori di dominio
# =============================================================================

def test_factory_unknown_preset_raises():
    with pytest.raises(InvalidFieldValueError):
        make_pitch_unit("foobar")


@pytest.mark.parametrize("bad", [0, -1, -31])
def test_factory_edo_non_positive_raises(bad):
    with pytest.raises(InvalidFieldValueError):
        make_pitch_unit({"edo": bad})


@pytest.mark.parametrize("bad", [0, -1])
def test_edo_unit_non_positive_divisions_raises(bad):
    with pytest.raises(InvalidFieldValueError):
        EdoUnit(bad)
