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

from pge.envelopes.envelope import Envelope
from pge.parameters.parameter import Parameter
from pge.parameters.parameter_definitions import GRANULAR_PARAMETERS
from pge.rendering.envelope_extractor import (
    get_stream_envelopes,
    get_voice_offset_envelopes,
    base_param_name,
)


# =============================================================================
# FIXTURES
# =============================================================================

def _param(name, value):
    return Parameter(name, value, GRANULAR_PARAMETERS[name])


def make_stream(stream_id='s1', onset=0.0, duration=10.0, sample='test.wav'):
    """Stream MagicMock, come la fixture omonima di test_score_visualizer.

    I `del` tolgono gli attributi che il test non valorizza: su un MagicMock
    esisterebbero come Mock e sporcherebbero la lettura (num_voices in
    particolare, che la vista interroga per la finestra attiva delle voci).
    """
    s = MagicMock()
    s.stream_id = stream_id
    s.onset = onset
    s.duration = duration
    s.sample = sample
    del s.volume
    del s.pan
    del s.pointer_start
    del s.density
    del s.num_voices
    del s.scatter
    del s.pointer_speed
    return s


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
    import pge.rendering.envelope_extractor as mod
    importlib.reload(mod)
    # Il modulo non deve trascinare matplotlib: l'export SV non lo richiede.
    src = open(mod.__file__).read()
    assert 'import matplotlib' not in src


# =============================================================================
# ESTRAZIONE PER PATH — suite migrata da test_score_visualizer.py.
# Verificavano l'estrattore costruendo un ScoreVisualizer intero per chiamarne
# il metodo delegante: ora interrogano la funzione, senza matplotlib.
# =============================================================================


class TestPitchEnvelopeCollection:
    """Dopo il refactor unit-driven il pitch non è più in PITCH_PARAMETER_SCHEMA.
    _get_stream_envelopes deve comunque raccogliere la curva di pitch tramite
    stream.pitch_value, per QUALSIASI unità (regressione visualizer)."""

    def _stream_with_pitch(self, pitch_value, unit_spec):
        from pge.parameters.pitch_unit import make_pitch_unit
        s = make_stream('s1', onset=0.0, duration=10.0)
        s.pitch_value = pitch_value
        s.pitch_unit = make_pitch_unit(unit_spec)
        return s

    def test_semitones_envelope_collected(self):
        from pge.envelopes.envelope import Envelope
        s = self._stream_with_pitch(Envelope([[0, 0.0], [10, 12.0]]), 'semitones')
        assert 'pitch' in get_stream_envelopes(s)

    def test_cents_envelope_collected(self):
        from pge.envelopes.envelope import Envelope
        s = self._stream_with_pitch(Envelope([[0, 0.0], [10, 1200.0]]), 'cents')
        assert 'pitch' in get_stream_envelopes(s)

    def test_edo_envelope_collected(self):
        from pge.envelopes.envelope import Envelope
        s = self._stream_with_pitch(Envelope([[0, 0.0], [10, 31.0]]), {'edo': 31})
        assert 'pitch' in get_stream_envelopes(s)

    def test_static_pitch_collected_when_show_static(self):
        s = self._stream_with_pitch(7.0, 'semitones')
        assert 'pitch' in get_stream_envelopes(s, show_static=True)

    def test_static_pitch_skipped_without_show_static(self):
        s = self._stream_with_pitch(0.0, 'semitones')
        assert 'pitch' not in get_stream_envelopes(s)


class TestVoiceScatterEnvelopeCollection:
    """num_voices e scatter non sono in nessuno schema *_PARAMETER_SCHEMA
    (issue #88): vanno raccolti per nome esplicito in _get_stream_envelopes,
    altrimenti i loro envelope non vengono mai disegnati."""

    def _param(self, name, value):
        from pge.parameters.parameter import Parameter
        from pge.parameters.parameter_definitions import GRANULAR_PARAMETERS
        return Parameter(name, value, GRANULAR_PARAMETERS[name])

    def _stream(self, num_voices=None, scatter=None):
        s = make_stream('s1', onset=0.0, duration=10.0)
        # make_stream fa gia' `del s.num_voices` e `del s.scatter`: assenti di default.
        if num_voices is not None:
            s.num_voices = num_voices
        if scatter is not None:
            s.scatter = scatter
        return s

    def test_scatter_dynamic_envelope_collected(self):
        from pge.envelopes.envelope import Envelope
        s = self._stream(scatter=self._param('scatter', Envelope([[0, 0.0], [10, 1.0]])))
        assert 'scatter' in get_stream_envelopes(s)

    def test_num_voices_dynamic_envelope_collected(self):
        from pge.envelopes.envelope import Envelope
        s = self._stream(num_voices=self._param('num_voices', Envelope([[0, 1.0], [10, 8.0]])))
        assert 'num_voices' in get_stream_envelopes(s)

    def test_static_scatter_skipped_without_show_static(self):
        from pge.envelopes.envelope import Envelope
        s = self._stream(scatter=self._param('scatter', Envelope([[0, 0.3], [10, 0.3]])))
        assert 'scatter' not in get_stream_envelopes(s)

    def test_static_scatter_collected_with_show_static(self):
        from pge.envelopes.envelope import Envelope
        s = self._stream(scatter=self._param('scatter', Envelope([[0, 0.3], [10, 0.3]])))
        assert 'scatter' in get_stream_envelopes(s, show_static=True)

    def test_has_envelopes_true_when_only_scatter_modulated(self):
        """Regressione issue #88: il pannello envelope deve esistere anche se
        l'unica modulazione time-varying e' scatter/num_voices."""
        from pge.envelopes.envelope import Envelope
        s = self._stream(scatter=self._param('scatter', Envelope([[0, 0.0], [10, 1.0]])))
        assert bool(get_stream_envelopes(s)) is True


class TestPointerSpeedEnvelopeCollection:
    """pointer_speed_ratio e' nello schema col nome `pointer_speed_ratio`, ma lo
    Stream espone la property `pointer_speed`: hasattr(stream, 'pointer_speed_ratio')
    e' falso, quindi il ciclo sugli schemi lo salta sempre (issue #88, Fase 2).
    Va raccolto per nome esplicito sotto la chiave `pointer_speed`."""

    def _stream(self, pointer_speed):
        s = make_stream('s1', onset=0.0, duration=10.0)
        s.pointer_speed = pointer_speed
        return s

    def test_pointer_speed_dynamic_envelope_collected(self):
        from pge.envelopes.envelope import Envelope
        s = self._stream(Envelope([[0, -2.0], [10, 4.0]]))
        assert 'pointer_speed' in get_stream_envelopes(s)

    def test_static_pointer_speed_skipped_without_show_static(self):
        from pge.envelopes.envelope import Envelope
        s = self._stream(Envelope([[0, 1.0], [10, 1.0]]))
        assert 'pointer_speed' not in get_stream_envelopes(s)

    def test_static_pointer_speed_collected_with_show_static(self):
        from pge.envelopes.envelope import Envelope
        s = self._stream(Envelope([[0, 1.0], [10, 1.0]]))
        assert 'pointer_speed' in get_stream_envelopes(s, show_static=True)


class TestVoiceOffsetEnvelopeCollection:
    """Fase 3 issue #90: gli offset per-voce (voice_pitch_offset,
    voice_pointer_offset, voice_pointer_range) non sono Envelope sullo Stream
    ma config delle voice strategy, calcolati da
    VoiceManager.get_voice_config(voice_index, time). Vengono raccolti come
    curve per-voce SOLO col flag show_voice_offsets; la voce 0 (riferimento)
    e' sempre esclusa."""

    def _stream_with_vm(self, voice_manager, num_voices=None):
        s = make_stream('s1', onset=0.0, duration=10.0)
        s.voice_manager = voice_manager
        if num_voices is not None:
            s.num_voices = num_voices
        return s

    def _num_voices_param(self, value):
        from pge.parameters.parameter import Parameter
        from pge.parameters.parameter_definitions import GRANULAR_PARAMETERS
        return Parameter('num_voices', value, GRANULAR_PARAMETERS['num_voices'])

    def _vm_pitch(self, max_voices=3, step=3.0):
        from pge.controllers.voice_manager import VoiceManager
        from pge.strategies.voice_pitch_strategy import StepPitchStrategy
        return VoiceManager(max_voices=max_voices,
                            pitch_strategy=StepPitchStrategy(step=step))

    def _vm_pointer_linear(self, max_voices=3, step=0.05):
        from pge.controllers.voice_manager import VoiceManager
        from pge.strategies.voice_pointer_strategy import LinearPointerStrategy
        return VoiceManager(max_voices=max_voices,
                            pointer_strategy=LinearPointerStrategy(step=step))

    # --- gating col flag ---

    def test_voice_offsets_absent_without_flag(self):
        s = self._stream_with_vm(self._vm_pitch())
        env = get_stream_envelopes(s)
        assert not any(k.startswith('voice_pitch_offset') for k in env)

    def test_voice_pitch_offset_per_voice_collected_with_flag(self):
        s = self._stream_with_vm(self._vm_pitch())
        env = get_stream_envelopes(s, show_voice_offsets=True)
        assert 'voice_pitch_offset__v1' in env
        assert 'voice_pitch_offset__v2' in env
        assert 'voice_pitch_offset__v0' not in env  # voce 0 = riferimento

    def test_voice_pitch_offset_values_in_semitones(self):
        s = self._stream_with_vm(self._vm_pitch(step=3.0))
        env = get_stream_envelopes(s, show_voice_offsets=True)
        assert env['voice_pitch_offset__v1'].evaluate(0.0) == pytest.approx(3.0, abs=1e-6)
        assert env['voice_pitch_offset__v2'].evaluate(0.0) == pytest.approx(6.0, abs=1e-6)

    def test_voice_pointer_offset_per_voice_collected_with_flag(self):
        s = self._stream_with_vm(self._vm_pointer_linear(step=0.05))
        env = get_stream_envelopes(s, show_voice_offsets=True)
        assert env['voice_pointer_offset__v1'].evaluate(0.0) == pytest.approx(0.05, abs=1e-6)
        assert env['voice_pointer_offset__v2'].evaluate(0.0) == pytest.approx(0.10, abs=1e-6)

    def test_voice_pointer_range_single_curve_from_stochastic(self):
        from pge.envelopes.envelope import Envelope
        from pge.controllers.voice_manager import VoiceManager
        from pge.strategies.voice_pointer_strategy import StochasticPointerStrategy
        rng = Envelope([[0, 0.1], [10, 0.5]])
        vm = VoiceManager(
            max_voices=3,
            pointer_strategy=StochasticPointerStrategy(pointer_range=rng, stream_id='s1'),
        )
        s = self._stream_with_vm(vm)
        env = get_stream_envelopes(s, show_voice_offsets=True)
        assert env['voice_pointer_range'] is rng

    def test_no_voice_offsets_when_single_voice(self):
        s = self._stream_with_vm(self._vm_pitch(max_voices=1))
        env = get_stream_envelopes(s, show_voice_offsets=True)
        assert not any(k.startswith('voice_pitch_offset') for k in env)

    def test_no_curve_when_no_strategy(self):
        from pge.controllers.voice_manager import VoiceManager
        s = self._stream_with_vm(VoiceManager(max_voices=3))  # nessuna strategy
        env = get_stream_envelopes(s, show_voice_offsets=True)
        assert not any(k.startswith('voice_pitch_offset') for k in env)
        assert not any(k.startswith('voice_pointer_offset') for k in env)

    def test_no_voice_manager_no_crash(self):
        s = make_stream('s1', onset=0.0, duration=10.0)
        s.voice_manager = None
        env = get_stream_envelopes(s, show_voice_offsets=True)
        assert not any(k.startswith('voice_') for k in env)

    def test_time_varying_num_voices_truncates_high_voice(self):
        from pge.envelopes.envelope import Envelope
        # num_voices sale da 1 a 4: la voce 2 e' attiva solo nella seconda meta'.
        vm = self._vm_pitch(max_voices=4)
        nv = self._num_voices_param(Envelope([[0, 1.0], [10, 4.0]]))
        s = self._stream_with_vm(vm, num_voices=nv)
        env = get_stream_envelopes(s, show_voice_offsets=True)
        assert 'voice_pitch_offset__v2' in env
        assert env['voice_pitch_offset__v2'].breakpoints[0][0] > 0.0

    def test_has_envelopes_true_when_only_voice_offsets(self):
        s = self._stream_with_vm(self._vm_pitch())
        assert bool(get_stream_envelopes(s, show_voice_offsets=True)) is True


class TestBaseParamNameWithFilter:
    """_base_param_name strippa il suffisso __vN: serve a risolvere
    colore/range/filtro sul nome base per le curve per-voce (Fase 3 #90)."""

    def test_strips_voice_suffix(self):
        assert base_param_name('voice_pitch_offset__v2') == 'voice_pitch_offset'

    def test_noop_on_plain_name(self):
        assert base_param_name('pitch') == 'pitch'

    def test_filter_by_base_keeps_per_voice_keys(self):
        from pge.controllers.voice_manager import VoiceManager
        from pge.strategies.voice_pitch_strategy import StepPitchStrategy
        vm = VoiceManager(max_voices=3, pitch_strategy=StepPitchStrategy(step=3.0))
        s = make_stream('s1', onset=0.0, duration=10.0)
        s.voice_manager = vm
        env = get_stream_envelopes(s, show_voice_offsets=True,
                                   envelope_filter={'voice_pitch_offset'})
        assert 'voice_pitch_offset__v1' in env


class TestModRangeEnvelopeCollection:
    """issue #96 - i parametri con range_path (volume_range, pan_range,
    grain.duration_range, offset_range) tengono il range stocastico in
    Parameter._mod_range, mai estratto dal visualizer. Va raccolto sotto la
    chiave `spec.name + '_range'` (issue #141: chiave distinta dal valore base).
    Qui via `volume` (stream-level, raggiungibile dal loop)."""

    def _stream_with_volume_range(self, base, mod_range):
        from pge.parameters.parameter import Parameter
        from pge.parameters.parameter_definitions import GRANULAR_PARAMETERS
        s = make_stream('s1', onset=0.0, duration=10.0)
        # base scalare statico: PARTE 1 non emette 'volume', isola PARTE 3
        s.volume = Parameter('volume', base, GRANULAR_PARAMETERS['volume'],
                             mod_range=mod_range)
        return s

    def test_dynamic_range_envelope_collected(self):
        from pge.envelopes.envelope import Envelope
        s = self._stream_with_volume_range(-6.0, Envelope([[0, 0.0], [10, 12.0]]))
        assert 'volume_range' in get_stream_envelopes(s)

    def test_dynamic_range_envelope_is_the_mod_range(self):
        from pge.envelopes.envelope import Envelope
        env = Envelope([[0, 0.0], [10, 12.0]])
        s = self._stream_with_volume_range(-6.0, env)
        assert get_stream_envelopes(s)['volume_range'] is env

    def test_static_range_skipped_without_show_static(self):
        s = self._stream_with_volume_range(-6.0, 3.0)
        assert 'volume_range' not in get_stream_envelopes(s)

    def test_static_range_collected_with_show_static(self):
        s = self._stream_with_volume_range(-6.0, 3.0)
        assert 'volume_range' in get_stream_envelopes(s, show_static=True)


class TestValueAndRangeCoexist:
    """issue #141 - uno stream con valore base reale E range (_mod_range) deve
    mostrare ENTRAMBE le curve: il valore sotto `spec.name`, il range sotto
    `spec.name + '_range'`. Prima del fix la PARTE 3 sovrascriveva la chiave del
    valore base (es. il loop di `pan` perso a favore di `pan_range`)."""

    def _stream_with_pan(self, base, mod_range):
        from pge.parameters.parameter import Parameter
        from pge.parameters.parameter_definitions import GRANULAR_PARAMETERS
        s = make_stream('s1', onset=0.0, duration=10.0)
        s.pan = Parameter('pan', base, GRANULAR_PARAMETERS['pan'],
                          mod_range=mod_range)
        return s

    def test_pan_loop_preserved_when_pan_range_present(self):
        from pge.envelopes.envelope import Envelope
        base = Envelope([[0, 0.0], [10, 360.0]])      # loop rotativo
        rng = Envelope([[0, 20.0], [10, 170.0]])      # deviazione per-grano
        s = self._stream_with_pan(base, rng)
        env = get_stream_envelopes(s)
        assert 'pan' in env
        assert env['pan'] is base

    def test_pan_range_collected_under_suffixed_key(self):
        from pge.envelopes.envelope import Envelope
        base = Envelope([[0, 0.0], [10, 360.0]])
        rng = Envelope([[0, 20.0], [10, 170.0]])
        s = self._stream_with_pan(base, rng)
        env = get_stream_envelopes(s)
        assert 'pan_range' in env
        assert env['pan_range'] is rng

    def test_pan_value_without_range_unchanged(self):
        from pge.envelopes.envelope import Envelope
        base = Envelope([[0, 0.0], [10, 360.0]])
        s = self._stream_with_pan(base, None)
        env = get_stream_envelopes(s)
        assert env.get('pan') is base
        assert 'pan_range' not in env


class TestDephaseGateEnvelopeCollection:
    """issue #96 - il dephase oggi e' un ProbabilityGate in
    Parameter._probability_gate, non piu' in _mod_prob (codice morto). Va letto
    dal gate sotto la chiave `{spec.name}_prob`. Qui via `volume` (stream-level)."""

    def _stream_with_gate(self, gate):
        from pge.parameters.parameter import Parameter
        from pge.parameters.parameter_definitions import GRANULAR_PARAMETERS
        s = make_stream('s1', onset=0.0, duration=10.0)
        p = Parameter('volume', -6.0, GRANULAR_PARAMETERS['volume'])
        if gate is not None:
            p.set_probability_gate(gate)
        s.volume = p
        return s

    def test_envelope_gate_collected(self):
        from pge.envelopes.envelope import Envelope
        from pge.shared.probability_gate import EnvelopeGate
        s = self._stream_with_gate(EnvelopeGate(Envelope([[0, 0.0], [10, 100.0]])))
        assert 'volume_prob' in get_stream_envelopes(s)

    def test_envelope_gate_curve_is_the_gate_envelope(self):
        from pge.envelopes.envelope import Envelope
        from pge.shared.probability_gate import EnvelopeGate
        env = Envelope([[0, 0.0], [10, 100.0]])
        s = self._stream_with_gate(EnvelopeGate(env))
        assert get_stream_envelopes(s)['volume_prob'] is env

    def test_random_gate_skipped_without_show_static(self):
        from pge.shared.probability_gate import RandomGate
        s = self._stream_with_gate(RandomGate(50.0))
        assert 'volume_prob' not in get_stream_envelopes(s)

    def test_random_gate_collected_with_show_static(self):
        from pge.shared.probability_gate import RandomGate
        s = self._stream_with_gate(RandomGate(50.0))
        assert 'volume_prob' in get_stream_envelopes(s, show_static=True)

    def test_never_gate_not_collected(self):
        s = self._stream_with_gate(None)  # default NeverGate
        assert 'volume_prob' not in get_stream_envelopes(s, show_static=True)


class TestPointerDeviationEnvelopeCollection:
    """issue #96 - il vero pointer_deviation NON e' esposto sullo Stream: vive in
    stream._pointer.deviation (PointerController), offset_range in _mod_range e
    dephase in _probability_gate. hasattr(stream,'pointer_deviation') e' False:
    il loop sugli schemi lo salta, serve estrazione esplicita (come pointer_speed,
    issue #88). Chiavi: `pointer_deviation` (range) e `pointer_deviation_prob`."""

    def _stream(self, mod_range=None, gate=None):
        from pge.parameters.parameter import Parameter
        from pge.parameters.parameter_definitions import GRANULAR_PARAMETERS
        s = make_stream('s1', onset=0.0, duration=10.0)
        p = Parameter('pointer_deviation', 0.0,
                      GRANULAR_PARAMETERS['pointer_deviation'],
                      mod_range=mod_range)
        if gate is not None:
            p.set_probability_gate(gate)
        s.pointer_deviation = p
        return s

    def test_offset_range_envelope_collected(self):
        from pge.envelopes.envelope import Envelope
        s = self._stream(mod_range=Envelope([[0, 0.0], [10, 1.0]]))
        assert 'pointer_deviation' in get_stream_envelopes(s)

    def test_offset_range_envelope_is_the_mod_range(self):
        from pge.envelopes.envelope import Envelope
        env = Envelope([[0, 0.0], [10, 1.0]])
        s = self._stream(mod_range=env)
        assert get_stream_envelopes(s)['pointer_deviation'] is env

    def test_offset_range_static_skipped_without_show_static(self):
        s = self._stream(mod_range=0.4)
        assert 'pointer_deviation' not in get_stream_envelopes(s)

    def test_offset_range_static_collected_with_show_static(self):
        s = self._stream(mod_range=0.4)
        assert 'pointer_deviation' in get_stream_envelopes(s, show_static=True)

    def test_dephase_envelope_gate_collected(self):
        from pge.envelopes.envelope import Envelope
        from pge.shared.probability_gate import EnvelopeGate
        s = self._stream(gate=EnvelopeGate(Envelope([[0, 0.0], [10, 100.0]])))
        assert 'pointer_deviation_prob' in get_stream_envelopes(s)

    def test_dephase_random_gate_collected_with_show_static(self):
        from pge.shared.probability_gate import RandomGate
        s = self._stream(gate=RandomGate(50.0))
        assert 'pointer_deviation_prob' in get_stream_envelopes(s, show_static=True)

    def test_dephase_never_gate_not_collected(self):
        s = self._stream()  # default NeverGate
        assert 'pointer_deviation_prob' not in get_stream_envelopes(s, show_static=True)

    def test_no_pointer_attr_does_not_crash(self):
        s = make_stream('s1', onset=0.0, duration=10.0)
        del s.pointer_deviation
        assert get_stream_envelopes(s) is not None


class TestEnvelopeFilter:
    """issue #101 - config `envelope_filter`: se non-None, _get_stream_envelopes
    ritorna solo le chiavi elencate; default None = nessun filtro (tutte)."""

    def _stream(self):
        """Stream con due envelope dinamici: pitch e pointer_speed."""
        from pge.envelopes.envelope import Envelope
        from pge.parameters.pitch_unit import make_pitch_unit
        s = make_stream('s1', onset=0.0, duration=10.0)
        s.pitch_value = Envelope([[0, 0.0], [10, 12.0]])
        s.pitch_unit = make_pitch_unit('semitones')
        s.pointer_speed = Envelope([[0, -2.0], [10, 4.0]])
        return s

    def test_filter_keeps_only_listed_keys(self):
        s = self._stream()
        assert set(get_stream_envelopes(s, envelope_filter={'pitch'})) == {'pitch'}

    def test_no_filter_keeps_all_keys(self):
        """Default (envelope_filter assente/None) = comportamento attuale."""
        s = self._stream()
        envs = get_stream_envelopes(s)
        assert set(envs) == {'pitch', 'pointer_speed'}

    def test_filter_does_not_force_static_visibility(self):
        """Il filtro interseca: uno statico elencato resta fuori senza
        show_static_params (la distinzione STATIC e' ortogonale)."""
        from pge.envelopes.envelope import Envelope
        s = make_stream('s1', onset=0.0, duration=10.0)
        s.pointer_speed = Envelope([[0, 1.0], [10, 1.0]])  # statico
        assert 'pointer_speed' not in get_stream_envelopes(s, envelope_filter={'pointer_speed'})

    def test_filter_with_show_static_keeps_listed_static(self):
        from pge.envelopes.envelope import Envelope
        s = make_stream('s1', onset=0.0, duration=10.0)
        s.pointer_speed = Envelope([[0, 1.0], [10, 1.0]])  # statico
        assert set(get_stream_envelopes(
            s, show_static=True,
            envelope_filter={'pointer_speed'})) == {'pointer_speed'}

    def test_filter_applies_to_prob_keys(self):
        """Le chiavi derivate (`*_prob`, dal ProbabilityGate) sono filtrabili
        come le altre: il filtro agisce sul dict finale."""
        from pge.envelopes.envelope import Envelope
        from pge.parameters.parameter import Parameter
        from pge.parameters.parameter_definitions import GRANULAR_PARAMETERS
        from pge.shared.probability_gate import EnvelopeGate
        s = make_stream('s1', onset=0.0, duration=10.0)
        p = Parameter('volume', Envelope([[0, -20.0], [10, 0.0]]),
                      GRANULAR_PARAMETERS['volume'])
        p.set_probability_gate(EnvelopeGate(Envelope([[0, 0.0], [10, 100.0]])))
        s.volume = p
        assert set(get_stream_envelopes(s, envelope_filter={'volume_prob'})) == {'volume_prob'}

    def test_filter_key_absent_from_stream_is_ignored(self):
        """Chiave valida nel filtro ma senza envelope nello stream: nessun
        errore, semplicemente assente dal risultato."""
        s = self._stream()
        assert set(get_stream_envelopes(s, envelope_filter={'pitch', 'density'})) == {'pitch'}




# =============================================================================
# GROUP - Pitch color auto-zoom (colormap divergente pitch_div + range dinamico per-subplot)
# =============================================================================
