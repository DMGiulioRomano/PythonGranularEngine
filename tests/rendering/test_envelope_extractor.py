# tests/rendering/test_envelope_extractor.py
"""
TDD suite per rendering.envelope_extractor.

Il modulo estrae gli Envelope dalla IR di uno Stream (single source of truth
condivisa da ScoreVisualizer e SVExporter). E' la stessa logica che prima viveva
in ScoreVisualizer._get_stream_envelopes, ora isolata e matplotlib-free.

Copre:
- get_stream_envelopes: chiavi raccolte, ordine schema, gating show_static,
  filtro envelope_filter.
- base_param_name: strip del suffisso per-voce __vN.
- Indipendenza da matplotlib (il modulo non deve importarlo).
"""

import sys

import pytest
from unittest.mock import MagicMock

from envelopes.envelope import Envelope
from parameters.parameter import Parameter
from parameters.parameter_definitions import GRANULAR_PARAMETERS
from rendering.envelope_extractor import get_stream_envelopes, base_param_name


# =============================================================================
# FIXTURES
# =============================================================================

def _param(name, value):
    return Parameter(name, value, GRANULAR_PARAMETERS[name])


def _stream(onset=0.0, duration=10.0, **params):
    """Stream MagicMock: gli attributi non impostati sono Mock (ignorati dalle
    isinstance del modulo); solo i Parameter reali passati vengono estratti."""
    s = MagicMock()
    s.stream_id = 's1'
    s.onset = onset
    s.duration = duration
    for k, v in params.items():
        setattr(s, k, v)
    return s


# =============================================================================
# base_param_name
# =============================================================================

class TestBaseParamName:

    def test_strips_voice_suffix(self):
        assert base_param_name('voice_pitch_offset__v2') == 'voice_pitch_offset'

    def test_identity_on_plain_key(self):
        assert base_param_name('density') == 'density'

    def test_only_trailing_suffix(self):
        assert base_param_name('voice_pointer_offset__v10') == 'voice_pointer_offset'


# =============================================================================
# get_stream_envelopes
# =============================================================================

class TestGetStreamEnvelopes:

    def _e3_stream(self, onset=0.0):
        """Scenario e3: grain_duration + density + distribution dinamici."""
        return _stream(
            onset=onset,
            duration=10.0,
            grain_duration=_param('grain_duration', Envelope([[0, 0.01], [10, 0.05]])),
            density=_param('density', Envelope([[0, 5.0], [10, 1000.0]])),
            distribution=_param('distribution', Envelope([[0, 0.0], [10, 1.0]])),
        )

    def test_collects_dynamic_envelopes(self):
        env = get_stream_envelopes(self._e3_stream())
        assert set(env) == {'grain_duration', 'density', 'distribution'}

    def test_values_are_envelopes(self):
        env = get_stream_envelopes(self._e3_stream())
        assert all(isinstance(v, Envelope) for v in env.values())

    def test_schema_order_stream_then_density(self):
        # STREAM schema (grain_duration) precede DENSITY schema (density,
        # distribution): l'ordine dei layer SV ne dipende.
        keys = list(get_stream_envelopes(self._e3_stream()))
        assert keys.index('grain_duration') < keys.index('density')
        assert keys.index('density') < keys.index('distribution')

    def test_static_skipped_by_default(self):
        s = _stream(density=_param('density', Envelope([[0, 50.0], [10, 50.0]])))
        assert 'density' not in get_stream_envelopes(s)

    def test_static_collected_with_show_static(self):
        s = _stream(density=_param('density', Envelope([[0, 50.0], [10, 50.0]])))
        env = get_stream_envelopes(s, show_static=True)
        assert 'density' in env

    def test_envelope_filter_intersects(self):
        env = get_stream_envelopes(self._e3_stream(), envelope_filter={'density'})
        assert set(env) == {'density'}

    def test_breakpoints_are_stream_relative(self):
        # I breakpoint restano relativi allo stream (0-based): l'offset onset
        # e' responsabilita' del consumatore (SVExporter), non dell'estrattore.
        env = get_stream_envelopes(self._e3_stream(onset=5.0))
        assert env['density'].breakpoints[0][0] == 0


# =============================================================================
# Indipendenza da matplotlib
# =============================================================================

def test_module_does_not_import_matplotlib():
    import importlib
    import rendering.envelope_extractor as mod
    importlib.reload(mod)
    # Il modulo non deve trascinare matplotlib: l'export SV non lo richiede.
    src = open(mod.__file__).read()
    assert 'import matplotlib' not in src
