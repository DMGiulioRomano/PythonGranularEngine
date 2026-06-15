# tests/parameters/test_pitch_unit.py
"""
Test suite per pitch_unit.py — astrazione unità di misura del pitch.

Modulo sotto test:
- EdoUnit(N): conversione 2^(v/N) (semitoni=12, cents=1200, quarti=24, ottavi=48)
- RatioUnit: identità (moltiplicatore diretto)
- make_pitch_unit(spec): factory da preset stringa / {edo: N} / None (default semitoni)
"""

import pytest

from parameters.pitch_unit import (
    EDO_IMPLICIT_DETUNE_CENTS, EdoUnit, RatioUnit, make_pitch_unit,
)
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
    # bounds del ratio diretto: minimo esteso a 0.001
    b = RatioUnit().value_bounds()
    assert isinstance(b, ParameterBounds)
    assert b.min_val == 0.001
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
def test_materialize_ratio_non_positive_amount_is_identity(amount):
    # amount<=0 → identità, allineato a EDO (2^(p*0/d) = 1.0)
    assert RatioUnit().materialize(0.5, amount) == pytest.approx(1.0)
    assert RatioUnit().materialize(2.0, amount) == pytest.approx(1.0)


# =============================================================================
# implicit_detune_cents — detune implicito in ratio-space (issue #95)
# =============================================================================
# Il detune NON vive in default_jitter (value-space quantizzato: sub-grado
# arrotonda a 0, un grado intero è una trasposizione enorme). È una costante
# in cents (semi-ampiezza ±N) applicata da UnitPitchStrategy in ratio-space,
# solo nel path dephase senza range esplicito.

@pytest.mark.parametrize("divisions", [12, 24, 48, 1200, 31])
def test_edo_implicit_detune_matches_constant(divisions):
    # stessa semi-ampiezza per ogni griglia EDO, indipendente dalle divisioni
    assert EdoUnit(divisions).implicit_detune_cents == EDO_IMPLICIT_DETUNE_CENTS
    assert EDO_IMPLICIT_DETUNE_CENTS > 0


def test_ratio_implicit_detune_is_zero():
    # RatioUnit ha già il jitter implicito in value-space (default_jitter=0.005):
    # detune ratio-space a 0 per evitare doppia applicazione
    assert RatioUnit().implicit_detune_cents == 0.0


@pytest.mark.parametrize("preset,expected", [
    ('semitones', EDO_IMPLICIT_DETUNE_CENTS),
    ('cents', EDO_IMPLICIT_DETUNE_CENTS),
    ('quarter_tone', EDO_IMPLICIT_DETUNE_CENTS),
    ('eighth_tone', EDO_IMPLICIT_DETUNE_CENTS),
    ('ratio', 0.0),
])
def test_preset_implicit_detune(preset, expected):
    assert make_pitch_unit(preset).implicit_detune_cents == expected


def test_edo_default_jitter_stays_zero():
    # regressione: il detune non passa dai bounds — il path esplicito
    # quantizzato resta invariato
    assert EdoUnit(12).value_bounds().default_jitter == 0.0


@pytest.mark.parametrize("unit", [EdoUnit(12), EdoUnit(31), RatioUnit()])
def test_materialize_is_deterministic_no_detune(unit):
    # regressione issue #95: il detune vive solo in UnitPitchStrategy,
    # mai nella materializzazione del path voci
    a = unit.materialize(1.0, 3.0)
    b = unit.materialize(1.0, 3.0)
    assert a == b


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
