# tests/parameters/test_parameter_dephase_api.py
"""
Test dell'API pubblica di Parameter usata dal detune implicito (issue #95):

- has_explicit_range: True se l'utente ha dichiarato `range` nello YAML
  (mod_range non None), False se il param usa il jitter implicito.
- variation_allowed(time): interroga il gate dephase senza applicare
  la variazione — usata da UnitPitchStrategy per il detune per-grano.
"""

import pytest

from pge.parameters.parameter import Parameter
from pge.parameters.parameter_definitions import ParameterBounds
from pge.shared.probability_gate import NeverGate, AlwaysGate

BOUNDS = ParameterBounds(
    min_val=-36.0, max_val=36.0,
    min_range=0.0, max_range=36.0,
    default_jitter=0.0,
    variation_mode='quantized',
)


# =============================================================================
# has_explicit_range
# =============================================================================

def test_has_explicit_range_false_without_mod_range():
    assert Parameter('p', 0.0, BOUNDS).has_explicit_range is False


def test_has_explicit_range_true_with_mod_range():
    assert Parameter('p', 0.0, BOUNDS, mod_range=2.0).has_explicit_range is True


def test_has_explicit_range_true_with_zero_range():
    # range dichiarato esplicitamente a 0 resta esplicito: l'utente ha chiesto
    # "nessuna variazione", il detune implicito non deve scattare
    assert Parameter('p', 0.0, BOUNDS, mod_range=0.0).has_explicit_range is True


# =============================================================================
# variation_allowed
# =============================================================================

def test_variation_allowed_default_gate_is_never():
    assert Parameter('p', 0.0, BOUNDS).variation_allowed(0.0) is False


def test_variation_allowed_with_always_gate():
    p = Parameter('p', 0.0, BOUNDS)
    p.set_probability_gate(AlwaysGate())
    assert p.variation_allowed(0.0) is True


def test_variation_allowed_with_never_gate():
    p = Parameter('p', 0.0, BOUNDS, mod_range=2.0)
    p.set_probability_gate(NeverGate())
    assert p.variation_allowed(0.5) is False
