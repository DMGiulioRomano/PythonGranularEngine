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
from parameters.parameter_definitions import ParameterBounds
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


# =============================================================================
# identity_value — valore neutro (ratio 1.0) dipendente dall'unità
# =============================================================================

@pytest.mark.parametrize("divisions", [12, 24, 48, 1200, 31])
def test_edo_identity_value_is_zero(divisions):
    # famiglia esponenziale: 2^0 = 1 -> nessuna trasposizione
    assert EdoUnit(divisions).identity_value() == 0.0


def test_ratio_identity_value_is_one():
    # moltiplicatore diretto: x1 -> nessuna trasposizione (non *0 = silenzio)
    assert RatioUnit().identity_value() == 1.0


@pytest.mark.parametrize("unit", [EdoUnit(12), EdoUnit(1200), EdoUnit(31), RatioUnit()])
def test_identity_value_yields_unison(unit):
    # invariante: to_ratio(identity_value()) == 1.0 per ogni unità
    assert unit.to_ratio(unit.identity_value()) == pytest.approx(1.0)


# =============================================================================
# value_bounds — i bounds derivano dall'unità (±3 ottave per EDO)
# =============================================================================

@pytest.mark.parametrize("divisions,expected", [
    (12, 36.0), (24, 72.0), (48, 144.0), (1200, 3600.0), (31, 93.0),
])
def test_edo_value_bounds_three_octaves(divisions, expected):
    b = EdoUnit(divisions).value_bounds()
    assert isinstance(b, ParameterBounds)
    assert b.min_val == -expected
    assert b.max_val == expected
    assert b.min_range == 0.0
    assert b.max_range == expected
    assert b.variation_mode == 'quantized'


def test_ratio_value_bounds_matches_legacy():
    # deve coincidere con i vecchi bounds statici di pitch_ratio
    b = RatioUnit().value_bounds()
    assert isinstance(b, ParameterBounds)
    assert b.min_val == 0.125
    assert b.max_val == 8.0
    assert b.min_range == 0.0
    assert b.max_range == 2.0
    assert b.variation_mode == 'additive'


def test_edo_semitones_bounds_match_legacy():
    # regressione: semitones (EDO 12) = vecchi pitch_semitones [-36, 36]
    b = make_pitch_unit('semitones').value_bounds()
    assert (b.min_val, b.max_val, b.max_range) == (-36.0, 36.0, 36.0)
    assert b.variation_mode == 'quantized'


# =============================================================================
# materialize(position, amount) — geometria voce-distribuzione, unit-aware
# =============================================================================
# Strategy emettono (position, amount) puri; l'unità possiede la geometria.
# EDO: additiva nel log -> 2^(position*amount/divisions) == to_ratio(position*amount).
# Ratio: geometrica -> amount^position. In entrambe position=0 -> 1.0 (identità).

@pytest.mark.parametrize("unit", [EdoUnit(12), EdoUnit(24), EdoUnit(1200), EdoUnit(31), RatioUnit()])
def test_materialize_position_zero_is_identity(unit):
    # position 0 -> ratio 1.0 per ogni unità (identità nativa, niente guard)
    assert unit.materialize(0.0, 12.0) == pytest.approx(1.0)


@pytest.mark.parametrize("divisions", [12, 24, 48, 1200, 31])
@pytest.mark.parametrize("position,amount", [(1.0, 3.0), (2.0, 4.0), (-1.0, 7.0), (0.5, 12.0)])
def test_materialize_edo_equals_to_ratio_of_product(divisions, position, amount):
    # equivalenza EDO: materialize(p, a) == to_ratio(p*a)
    unit = EdoUnit(divisions)
    assert unit.materialize(position, amount) == pytest.approx(unit.to_ratio(position * amount))


def test_materialize_ratio_is_geometric():
    u = RatioUnit()
    assert u.materialize(1.0, 2.0) == pytest.approx(2.0)
    assert u.materialize(2.0, 2.0) == pytest.approx(4.0)
    assert u.materialize(3.0, 2.0) == pytest.approx(8.0)
    assert u.materialize(-1.0, 2.0) == pytest.approx(0.5)
    assert u.materialize(0.5, 2.0) == pytest.approx(2.0 ** 0.5)


@pytest.mark.parametrize("amount", [0.0, -1.0, -2.0])
def test_materialize_ratio_non_positive_amount_raises(amount):
    # amount<=0 con esponente frazionario è nonsense -> errore di dominio
    with pytest.raises(InvalidFieldValueError):
        RatioUnit().materialize(0.5, amount)


# =============================================================================
# name / symbol — identità dell'unità (per mode e visualizer futuro)
# =============================================================================

@pytest.mark.parametrize("preset,name,symbol", [
    ('semitones',    'semitones',    'st'),
    ('cents',        'cents',        'c'),
    ('quarter_tone', 'quarter_tone', 'qt'),
    ('eighth_tone',  'eighth_tone',  'et'),
    ('ratio',        'ratio',        'x'),
])
def test_preset_name_and_symbol(preset, name, symbol):
    u = make_pitch_unit(preset)
    assert u.name == name
    assert u.symbol == symbol


def test_edo_dict_name_and_symbol():
    u = make_pitch_unit({'edo': 31})
    assert u.name == 'edo'
    assert u.symbol == 'edo31'


def test_edo_constructed_directly_defaults_to_edo_name():
    # EdoUnit(12) senza preset -> name generico 'edo', non 'semitones'
    u = EdoUnit(12)
    assert u.name == 'edo'
    assert u.symbol == 'edo12'
