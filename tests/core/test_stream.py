"""
test_stream.py

Suite completa di test per stream.py (Stream).

Stream e' l'orchestratore centrale della sintesi granulare:
- Coordina tutti i controller (Pointer, Pitch, Density, Voice, Window)
- Gestisce il loop di generazione grani
- Mantiene backward compatibility con Generator e ScoreVisualizer

Coverage:
  1.  _init_stream_context - validazione parametri obbligatori
  2.  _init_grain_reverse - semantica YAML reverse
  3.  _init_stream_parameters - delega a ParameterOrchestrator
  4.  _init_controllers - creazione controller
  5.  __init__ - pipeline completa
  6.  generate_grains - loop principale (1 voce, sync)
  7.  generate_grains - multi-voice con attivazione dinamica
  8.  generate_grains - stato e reset
  9.  _create_grain - assemblaggio singolo grano
 10.  _calculate_grain_reverse - auto mode e forced mode
 11.  Properties backward compatibility
 12.  __repr__
 13.  Edge cases
 14.  Integrazione end-to-end
"""

import sys
import os
import pytest
import math
from unittest.mock import Mock, patch, MagicMock, PropertyMock, call
from dataclasses import dataclass
from core.stream_config import StreamContext, StreamConfig
from core.stream import Stream


# =============================================================================
# MOCK INFRASTRUCTURE
# =============================================================================

def _make_mock_parameter(value=0.0, name='mock_param'):
    """Crea un mock Parameter con interfaccia get_value."""
    p = Mock()
    p.name = name
    p._value = value
    p.value = value
    p.get_value = Mock(return_value=float(value))
    p._probability_gate = Mock()
    p._probability_gate.should_apply = Mock(return_value=False)
    p._mod_range = None
    return p


def _make_mock_pointer():
    """Crea un mock PointerController."""
    ptr = Mock()
    ptr.calculate = Mock(return_value=2.5)
    ptr.get_speed = Mock(return_value=1.0)
    ptr.speed = Mock()
    ptr.speed.value = 1.0
    ptr.loop_start = None
    ptr.loop_end = None
    ptr.loop_dur = None
    return ptr


def _make_mock_pitch():
    """Crea un mock PitchController."""
    pitch = Mock()
    pitch.calculate = Mock(return_value=1.0)
    pitch.base_ratio = 1.0
    pitch.base_semitones = None
    pitch.range = 0.0
    return pitch


def _make_mock_density(inter_onset=0.1):
    """Crea un mock DensityController."""
    dens = Mock()
    dens.calculate_inter_onset = Mock(return_value=inter_onset)
    dens.density = 10.0
    dens.fill_factor = 2.0
    dens.distribution = Mock()
    dens.distribution.value = 0.0
    return dens


def _make_mock_voice_manager(max_voices=1):
    """Crea un mock VoiceManager."""
    vm = Mock()
    vm.max_voices = max_voices
    vm.is_voice_active = Mock(return_value=True)
    vm.get_voice_pitch_multiplier = Mock(return_value=1.0)
    vm.get_voice_pointer_offset = Mock(return_value=0.0)
    vm.get_voice_pointer_range = Mock(return_value=0.0)
    vm.num_voices_value = max_voices
    vm.voice_pitch_offset_value = 0.0
    vm.voice_pointer_offset_value = 0.0
    vm.voice_pointer_range_value = 0.0
    return vm


def _make_mock_window_controller():
    """Crea un mock WindowController."""
    wc = Mock()
    wc.select_window = Mock(return_value='hanning')
    return wc


def _make_mock_config(stream_id='test_stream', duration=1.0,
                      sample_dur_sec=5.0, onset=0.0):
    """Crea mock StreamConfig + StreamContext."""
    context = StreamContext(
        stream_id=stream_id,
        onset=onset,
        duration=duration,
        sample='test.wav',
        sample_dur_sec=sample_dur_sec
    )
    config = StreamConfig(context=context)
    return config


def _minimal_yaml_params(stream_id='test_stream', onset=0.0,
                         duration=1.0, sample='test.wav'):
    """Parametri YAML minimi per costruire uno Stream."""
    return {
        'stream_id': stream_id,
        'onset': onset,
        'duration': duration,
        'sample': sample,
    }


# =============================================================================
# FIXTURE: Stream con tutti i controller mockati
# =============================================================================

@pytest.fixture
def stream_factory():
    """
    Factory per creare Stream con controller mockati.

    Bypassa __init__ e assegna mock direttamente,
    permettendo di testare i metodi in isolamento.
    """
    def _create(
        stream_id='test_stream',
        onset=0.0,
        duration=1.0,
        sample='test.wav',
        sample_dur_sec=5.0,
        max_voices=1,
        inter_onset=0.1,
        grain_dur_value=0.05,
        volume_value=-6.0,
        pan_value=0.5,
        reverse_mode='auto',
    ):
        

        # Bypass __init__ completamente
        s = object.__new__(Stream)

        # Contesto base
        s.stream_id = stream_id
        s.onset = onset
        s.duration = duration
        s.sample = sample
        s.sample_dur_sec = sample_dur_sec

        # Parametri diretti (mock Parameter)
        s.grain_duration = _make_mock_parameter(grain_dur_value, 'grain_duration')
        s.volume = _make_mock_parameter(volume_value, 'volume')
        s.pan = _make_mock_parameter(pan_value, 'pan')
        s.reverse = _make_mock_parameter(0, 'reverse')
        s.grain_envelope = 'hanning'

        # Reverse mode
        s.grain_reverse_mode = reverse_mode

        # Controller mock
        s._pointer = _make_mock_pointer()
        s._pitch = _make_mock_pitch()
        s._density = _make_mock_density(inter_onset)
        s._voice_manager = _make_mock_voice_manager(max_voices)
        s._window_controller = _make_mock_window_controller()

        # Csound references
        s.sample_table_num = 1
        s.envelope_table_num = 2
        s.window_table_map = {'hanning': 2}

        # Stato
        s.voices = []
        s.grains = []
        s.generated = False

        return s

    return _create


# =============================================================================
# 1. TEST _init_stream_context
# =============================================================================

class TestInitStreamContext:
    """Test validazione parametri obbligatori in _init_stream_context."""

    def test_all_required_fields_present(self, stream_factory):
        """Con tutti i campi presenti, non solleva errori."""
        s = stream_factory()
        

        # Simula _init_stream_context su un oggetto gia' creato
        s2 = object.__new__(Stream)
        params = _minimal_yaml_params()

        with patch('core.stream.get_sample_duration', return_value=5.0):
            s2._init_stream_context(params)

        assert s2.stream_id == 'test_stream'
        assert s2.onset == 0.0
        assert s2.duration == 1.0
        assert s2.sample == 'test.wav'
        assert s2.sample_dur_sec == 5.0

    def test_missing_single_field_raises(self):
        """Parametro singolo mancante -> ValueError con nome."""
        
        s = object.__new__(Stream)
        params = {'onset': 0.0, 'duration': 1.0, 'sample': 'test.wav'}
        # Manca stream_id

        with patch('core.stream.get_sample_duration', return_value=5.0):
            with pytest.raises(ValueError, match="Parametro obbligatorio mancante"):
                s._init_stream_context(params)

    def test_missing_multiple_fields_raises(self):
        """Piu' parametri mancanti -> ValueError con nomi."""
        
        s = object.__new__(Stream)
        params = {'sample': 'test.wav'}
        # Mancano stream_id, onset, duration

        with patch('core.stream.get_sample_duration', return_value=5.0):
            with pytest.raises(ValueError, match="Parametri obbligatori mancanti"):
                s._init_stream_context(params)

    def test_empty_params_raises(self):
        """Params completamente vuoto -> ValueError."""
        
        s = object.__new__(Stream)

        with patch('core.stream.get_sample_duration', return_value=5.0):
            with pytest.raises(ValueError):
                s._init_stream_context({})

    def test_extra_fields_ignored(self):
        """Campi extra non causano errori."""
        
        s = object.__new__(Stream)
        params = _minimal_yaml_params()
        params['extra_field'] = 'ignored'
        params['another'] = 42

        with patch('core.stream.get_sample_duration', return_value=5.0):
            s._init_stream_context(params)

        assert s.stream_id == 'test_stream'
        assert not hasattr(s, 'extra_field')

    def test_sample_dur_sec_from_util(self):
        """sample_dur_sec viene da get_sample_duration, non da params."""
        
        s = object.__new__(Stream)
        params = _minimal_yaml_params()

        with patch('core.stream.get_sample_duration', return_value=3.14):
            s._init_stream_context(params)

        assert s.sample_dur_sec == 3.14


# =============================================================================
# 2. TEST _init_grain_reverse
# =============================================================================

class TestInitGrainReverse:
    """Test semantica YAML per grain reverse."""

    def test_reverse_absent_means_auto(self, stream_factory):
        """Chiave 'reverse' assente -> mode 'auto'."""
        
        s = object.__new__(Stream)
        s.stream_id = 'test'
        params = {'grain': {}}  # No reverse key

        s._init_grain_reverse(params)

        assert s.grain_reverse_mode == 'auto'

    def test_reverse_none_means_forced_true(self, stream_factory):
        """Chiave 'reverse:' vuota (None in YAML) -> mode True."""
        
        s = object.__new__(Stream)
        s.stream_id = 'test'
        params = {'grain': {'reverse': None}}

        s._init_grain_reverse(params)

        assert s.grain_reverse_mode is True

    def test_reverse_true_raises(self):
        """reverse: true -> ValueError (semantica ristretta)."""
        
        s = object.__new__(Stream)
        s.stream_id = 'test'
        params = {'grain': {'reverse': True}}

        with pytest.raises(ValueError, match="deve essere lasciato vuoto"):
            s._init_grain_reverse(params)

    def test_reverse_false_raises(self):
        """reverse: false -> ValueError."""
        
        s = object.__new__(Stream)
        s.stream_id = 'test'
        params = {'grain': {'reverse': False}}

        with pytest.raises(ValueError, match="deve essere lasciato vuoto"):
            s._init_grain_reverse(params)

    def test_reverse_string_raises(self):
        """reverse: 'auto' -> ValueError."""
        
        s = object.__new__(Stream)
        s.stream_id = 'test'
        params = {'grain': {'reverse': 'auto'}}

        with pytest.raises(ValueError, match="deve essere lasciato vuoto"):
            s._init_grain_reverse(params)

    def test_reverse_number_raises(self):
        """reverse: 1 -> ValueError."""
        
        s = object.__new__(Stream)
        s.stream_id = 'test'
        params = {'grain': {'reverse': 1}}

        with pytest.raises(ValueError):
            s._init_grain_reverse(params)

    def test_no_grain_key_means_auto(self):
        """Nessuna chiave 'grain' -> auto mode."""
        
        s = object.__new__(Stream)
        s.stream_id = 'test'
        params = {}

        s._init_grain_reverse(params)

        assert s.grain_reverse_mode == 'auto'


# =============================================================================
# 3. TEST _init_stream_parameters
# =============================================================================

class TestInitStreamParameters:
    """Test delega a ParameterOrchestrator per parametri diretti."""

    def test_creates_orchestrator_and_assigns(self):
        """Crea orchestrator, chiama create_all_parameters, assegna attributi."""
        
        s = object.__new__(Stream)

        mock_vol = _make_mock_parameter(-6.0, 'volume')
        mock_pan = _make_mock_parameter(0.5, 'pan')
        mock_params = {'volume': mock_vol, 'pan': mock_pan}

        config = Mock()

        with patch('core.stream.ParameterOrchestrator') as MockOrch:
            mock_orch_inst = MockOrch.return_value
            mock_orch_inst.create_all_parameters.return_value = mock_params

            s._init_stream_parameters({'volume': -6.0, 'pan': 0.5}, config)

        assert s.volume is mock_vol
        assert s.pan is mock_pan
        MockOrch.assert_called_once_with(config=config)

    def test_uses_stream_parameter_schema(self):
        """Passa STREAM_PARAMETER_SCHEMA a create_all_parameters."""
        
        s = object.__new__(Stream)

        config = Mock()

        with patch('core.stream.ParameterOrchestrator') as MockOrch:
            mock_orch_inst = MockOrch.return_value
            mock_orch_inst.create_all_parameters.return_value = {}

            s._init_stream_parameters({}, config)

        call_args = mock_orch_inst.create_all_parameters.call_args
        from parameters.parameter_schema import STREAM_PARAMETER_SCHEMA
        assert call_args.kwargs['schema'] is STREAM_PARAMETER_SCHEMA \
            or call_args[1].get('schema') is STREAM_PARAMETER_SCHEMA \
            or call_args[0][1] is STREAM_PARAMETER_SCHEMA


# =============================================================================
# 4. TEST _init_controllers
# =============================================================================

class TestInitControllers:
    """Test creazione di tutti i controller."""

    def test_creates_all_controllers(self):
        """Crea PointerController, PitchController, DensityController,
        WindowController, VoiceManager."""
        
        s = object.__new__(Stream)

        config = Mock()
        params = {
            'pointer': {'start': 0.0},
            'pitch': {'pitch_ratio': 1.0},
            'grain': {'envelope': 'hanning'},
            'voices': {'num_voices': 2},
            'fill_factor': 2.0,
        }

        with patch('core.stream.PointerController') as MockPtr, \
             patch('core.stream.PitchController') as MockPitch, \
             patch('core.stream.DensityController') as MockDens, \
             patch('core.stream.WindowController') as MockWin:

            s._init_controllers(params, config)

        MockPtr.assert_called_once()
        MockPitch.assert_called_once()
        MockDens.assert_called_once()
        MockWin.assert_called_once()

    def test_pointer_receives_pointer_subdict(self):
        """PointerController riceve params['pointer'] o {} se assente."""
        
        s = object.__new__(Stream)

        config = Mock()
        params = {'pointer': {'start': 5.0}}

        with patch('core.stream.PointerController') as MockPtr, \
             patch('core.stream.PitchController'), \
             patch('core.stream.DensityController'), \
             patch('core.stream.WindowController'):
            s._init_controllers(params, config)

        call_kwargs = MockPtr.call_args
        assert call_kwargs.kwargs['params'] == {'start': 5.0}

    def test_missing_subkeys_default_to_empty(self):
        """Sotto-chiavi mancanti producono {} come params."""
        
        s = object.__new__(Stream)

        config = Mock()
        params = {}  # Nessuna sotto-chiave

        with patch('core.stream.PointerController') as MockPtr, \
             patch('core.stream.PitchController') as MockPitch, \
             patch('core.stream.DensityController'), \
             patch('core.stream.WindowController') as MockWin:

            s._init_controllers(params, config)

        assert MockPtr.call_args.kwargs['params'] == {}
        assert MockPitch.call_args.kwargs['params'] == {}
        assert MockWin.call_args.kwargs['params'] == {}


# =============================================================================
# 5. TEST __init__ (PIPELINE COMPLETA)
# =============================================================================

class TestStreamInit:
    """Test pipeline completa di inizializzazione."""

    def test_full_init_with_mocks(self):
            """Init completo con tutte le dipendenze mockate."""
            

            params = _minimal_yaml_params(duration=2.0)

            # _init_stream_context semplificato: la vera versione e'
            # testata in TestInitStreamContext. Qui serve solo che assegni
            # gli attributi di contesto senza chiamare fields(StreamContext),
            # perche' StreamContext e' inquinato dallo stub di test_window_controller.
            def fake_init_ctx(self_stream, p):
                self_stream.stream_id = p['stream_id']
                self_stream.onset = p['onset']
                self_stream.duration = p['duration']
                self_stream.sample = p['sample']
                self_stream.sample_dur_sec = 5.0

            with patch('core.stream.get_sample_duration', return_value=5.0), \
                patch('core.stream.StreamContext') as MockSCtx, \
                patch('core.stream.StreamConfig') as MockSC, \
                patch.object(Stream, '_init_stream_context', fake_init_ctx), \
                patch('core.stream.ParameterOrchestrator') as MockOrch, \
                patch('core.stream.PointerController'), \
                patch('core.stream.PitchController'), \
                patch('core.stream.DensityController'), \
                patch('core.stream.WindowController'):
                MockSCtx.from_yaml.return_value = Mock()
                MockSC.from_yaml.return_value = Mock()

                mock_orch_inst = MockOrch.return_value
                mock_orch_inst.create_all_parameters.return_value = {
                    'volume': _make_mock_parameter(-6.0, 'volume'),
                    'pan': _make_mock_parameter(0.5, 'pan'),
                    'grain_duration': _make_mock_parameter(0.05, 'grain_duration'),
                    'grain_envelope': 'hanning',
                    'reverse': _make_mock_parameter(0, 'reverse'),
                }

                s = Stream(params)

            assert s.stream_id == 'test_stream'
            assert s.duration == 2.0
            assert s.voices == []
            assert s.grains == []
            assert s.generated is False
            assert s.sample_table_num is None
            assert s.envelope_table_num is None
# =============================================================================
# 6. TEST generate_grains - LOOP PRINCIPALE (1 VOCE)
# =============================================================================

class TestGenerateGrainsSingleVoice:
    """Test generate_grains con una sola voce."""

    def test_generates_correct_number_of_grains(self, stream_factory):
        """Con duration=1.0 e inter_onset=0.1, genera ~10 grani."""
        s = stream_factory(duration=1.0, inter_onset=0.1)

        s.generate_grains()

        assert len(s.voices) == 1
        assert len(s.voices[0]) in (10, 11)  # floating point accumulation

    def test_grains_flattened_for_backward_compat(self, stream_factory):
        """self.grains contiene versione flattened."""
        s = stream_factory(duration=0.5, inter_onset=0.1)

        s.generate_grains()

        assert len(s.grains) == len(s.voices[0])
        assert s.grains == s.voices[0]

    def test_generated_flag_set(self, stream_factory):
        """generated diventa True dopo generate_grains."""
        s = stream_factory(duration=0.3, inter_onset=0.1)

        assert s.generated is False
        s.generate_grains()
        assert s.generated is True

    def test_returns_voices_list(self, stream_factory):
        """generate_grains ritorna la lista voices."""
        s = stream_factory(duration=0.3, inter_onset=0.1)

        result = s.generate_grains()

        assert result is s.voices

    def test_grain_onset_is_absolute(self, stream_factory):
        """Onset del grano include offset dello stream."""
        s = stream_factory(onset=5.0, duration=0.3, inter_onset=0.1)

        s.generate_grains()

        # Primo grano: onset = stream.onset + elapsed_time(0.0)
        first_grain = s.voices[0][0]
        assert first_grain.onset == pytest.approx(5.0)

        # Secondo grano: onset = 5.0 + 0.1
        second_grain = s.voices[0][1]
        assert second_grain.onset == pytest.approx(5.1)

    def test_time_accumulation(self, stream_factory):
        """Inter-onset si accumula correttamente."""
        s = stream_factory(duration=0.5, inter_onset=0.1)

        s.generate_grains()

        onsets = [g.onset for g in s.voices[0]]
        for i in range(1, len(onsets)):
            delta = onsets[i] - onsets[i - 1]
            assert delta == pytest.approx(0.1)

    def test_stops_at_duration(self, stream_factory):
        """Il loop si ferma quando current_onset >= duration."""
        s = stream_factory(duration=0.35, inter_onset=0.1)

        s.generate_grains()

        # 0.0, 0.1, 0.2, 0.3 -> 4 grani (0.4 >= 0.35, stop prima)
        # In realta' 0.3 < 0.35 ma 0.3+0.1=0.4 >= 0.35 => 4 grani
        assert len(s.voices[0]) <= 4

    def test_zero_duration_no_grains(self, stream_factory):
        """duration=0 non produce grani."""
        s = stream_factory(duration=0.0, inter_onset=0.1)

        s.generate_grains()

        assert len(s.voices[0]) == 0


    # =============================================================================
# 8. TEST generate_grains - STATO E RESET
# =============================================================================

class TestGenerateGrainsState:
    """Test gestione stato in generate_grains."""

    def test_reset_on_regeneration(self, stream_factory):
        """Rigenerare resetta voices e grains."""
        s = stream_factory(duration=0.3, inter_onset=0.1)

        s.generate_grains()
        first_count = len(s.grains)

        s.generate_grains()
        second_count = len(s.grains)

        # Deve aver resettato, non accumulato
        assert first_count == second_count

    def test_calls_density_inter_onset(self, stream_factory):
        """Ogni iterazione chiama calculate_inter_onset."""
        s = stream_factory(duration=0.3, inter_onset=0.1)

        s.generate_grains()

        assert s._density.calculate_inter_onset.call_count == len(s.voices[0])

    def test_grain_duration_evaluated_per_grain(self, stream_factory):
        """grain_duration.get_value() chiamata per ogni grano."""
        s = stream_factory(duration=0.3, inter_onset=0.1)

        s.generate_grains()

        assert s.grain_duration.get_value.call_count == len(s.voices[0])


# =============================================================================
# 9. TEST _create_grain
# =============================================================================

class TestCreateGrain:
    """Test assemblaggio singolo grano."""

    def test_creates_grain_object(self, stream_factory):
        """_create_grain ritorna un oggetto Grain."""
        from core.grain import Grain
        s = stream_factory()

        grain = s._create_grain(elapsed_time=0.0, grain_dur=0.05)

        assert isinstance(grain, Grain)

    def test_grain_onset_includes_stream_onset(self, stream_factory):
        """onset = stream.onset + elapsed_time."""
        s = stream_factory(onset=10.0)

        grain = s._create_grain(elapsed_time=2.5, grain_dur=0.05)

        assert grain.onset == pytest.approx(12.5)

    def test_grain_duration_from_argument(self, stream_factory):
        """Durata del grano passata come argomento."""
        s = stream_factory()

        grain = s._create_grain(0.0, grain_dur=0.123)

        assert grain.duration == pytest.approx(0.123)

    def test_grain_pitch_from_pitch_controller(self, stream_factory):
        """pitch_ratio viene direttamente da PitchController.calculate()."""
        s = stream_factory()
        s._pitch.calculate.return_value = 2.0

        grain = s._create_grain(0.0, 0.05)

        assert grain.pitch_ratio == pytest.approx(2.0)

    def test_grain_pointer_from_controller(self, stream_factory):
        """pointer_pos viene dal PointerController."""
        s = stream_factory()
        s._pointer.calculate.return_value = 3.7

        grain = s._create_grain(0.0, 0.05)

        assert grain.pointer_pos == pytest.approx(3.7)

    def test_grain_volume_from_parameter(self, stream_factory):
        """volume da Parameter.get_value."""
        s = stream_factory()
        s.volume.get_value.return_value = -12.0

        grain = s._create_grain(0.0, 0.05)

        assert grain.volume == pytest.approx(-12.0)

    def test_grain_pan_from_parameter(self, stream_factory):
        """pan da Parameter.get_value."""
        s = stream_factory()
        s.pan.get_value.return_value = 0.75

        grain = s._create_grain(0.0, 0.05)

        assert grain.pan == pytest.approx(0.75)

    def test_grain_sample_table(self, stream_factory):
        """sample_table dallo stream."""
        s = stream_factory()
        s.sample_table_num = 42

        grain = s._create_grain(0.0, 0.05)

        assert grain.sample_table == 42

    def test_grain_envelope_table_from_window_controller(self, stream_factory):
        """envelope_table dalla window_table_map."""
        s = stream_factory()
        s._window_controller.select_window.return_value = 'hanning'
        s.window_table_map = {'hanning': 99}

        grain = s._create_grain(0.0, 0.05)

        assert grain.envelope_table == 99

    def test_pointer_called_with_elapsed_and_dur_and_reverse(self, stream_factory):
        """PointerController.calculate riceve elapsed_time, grain_dur e grain_reverse."""
        s = stream_factory()

        s._create_grain(elapsed_time=1.5, grain_dur=0.03)

        s._pointer.calculate.assert_called_once()
        args = s._pointer.calculate.call_args[0]
        assert args[0] == pytest.approx(1.5)
        assert args[1] == pytest.approx(0.03)


# =============================================================================
# 10. TEST _calculate_grain_reverse
# =============================================================================

class TestCalculateGrainReverse:
    """Test logica di calcolo reverse per il grano."""

    def test_auto_mode_forward_speed(self, stream_factory):
        """Auto mode con speed positivo -> False (non reverse)."""
        s = stream_factory(reverse_mode='auto')
        s._pointer.get_speed.return_value = 1.0
        s.reverse._probability_gate.should_apply.return_value = False

        result = s._calculate_grain_reverse(0.0)

        assert result is False

    def test_auto_mode_backward_speed(self, stream_factory):
        """Auto mode con speed negativo -> True (reverse)."""
        s = stream_factory(reverse_mode='auto')
        s._pointer.get_speed.return_value = -1.0
        s.reverse._probability_gate.should_apply.return_value = False

        result = s._calculate_grain_reverse(0.0)

        assert result is True

    def test_auto_mode_zero_speed(self, stream_factory):
        """Auto mode con speed=0 -> False (non negativo)."""
        s = stream_factory(reverse_mode='auto')
        s._pointer.get_speed.return_value = 0.0
        s.reverse._probability_gate.should_apply.return_value = False

        result = s._calculate_grain_reverse(0.0)

        assert result is False

    def test_forced_mode_always_reverse(self, stream_factory):
        """Mode True con valore > 0.5 -> reverse."""
        s = stream_factory(reverse_mode=True)
        s.reverse._value = 1.0
        s.reverse._probability_gate.should_apply.return_value = False

        result = s._calculate_grain_reverse(0.0)

        assert result is True

    def test_flip_with_gate_auto_mode(self, stream_factory):
        """Gate aperto in auto mode flippa il risultato."""
        s = stream_factory(reverse_mode='auto')
        s._pointer.get_speed.return_value = 1.0  # Forward
        s.reverse._probability_gate.should_apply.return_value = True

        result = s._calculate_grain_reverse(0.0)

        # Forward (False) flippato -> True
        assert result is True

    def test_flip_with_gate_backward(self, stream_factory):
        """Gate aperto con speed negativo flippa reverse -> forward."""
        s = stream_factory(reverse_mode='auto')
        s._pointer.get_speed.return_value = -1.0  # Backward
        s.reverse._probability_gate.should_apply.return_value = True

        result = s._calculate_grain_reverse(0.0)

        # Backward (True) flippato -> False
        assert result is False

    def test_forced_mode_with_envelope(self, stream_factory):
        """Mode True con Envelope come _value."""
        s = stream_factory(reverse_mode=True)

        mock_env = Mock()
        mock_env.evaluate.return_value = 0.8  # > 0.5 -> True base
        s.reverse._value = mock_env
        s.reverse._probability_gate.should_apply.return_value = False

        result = s._calculate_grain_reverse(5.0)

        mock_env.evaluate.assert_called_once_with(5.0)
        assert result is True

    def test_forced_mode_envelope_below_threshold(self, stream_factory):
        """Envelope < 0.5 in forced mode -> not reverse."""
        s = stream_factory(reverse_mode=True)

        mock_env = Mock()
        mock_env.evaluate.return_value = 0.2  # < 0.5 -> False base
        s.reverse._value = mock_env
        s.reverse._probability_gate.should_apply.return_value = False

        result = s._calculate_grain_reverse(5.0)

        assert result is False


# =============================================================================
# 11. TEST PROPERTIES BACKWARD COMPATIBILITY
# =============================================================================

class TestStreamProperties:
    """Test properties per backward compatibility con ScoreVisualizer."""

    def test_sampleDurSec_alias(self, stream_factory):
        """sampleDurSec restituisce sample_dur_sec."""
        s = stream_factory(sample_dur_sec=7.5)

        assert s.sampleDurSec == 7.5


    def test_density_property(self, stream_factory):
        """density espone valore dal DensityController."""
        s = stream_factory()
        s._density.density = 20.0

        assert s.density == 20.0

    def test_fill_factor_property(self, stream_factory):
        """fill_factor espone valore dal DensityController."""
        s = stream_factory()
        s._density.fill_factor = 3.0

        assert s.fill_factor == 3.0

    def test_fill_factor_none(self, stream_factory):
        """fill_factor None quando in density mode."""
        s = stream_factory()
        s._density.fill_factor = None

        assert s.fill_factor is None

    def test_distribution_property_with_value(self, stream_factory):
        """distribution espone .value se ha attributo value."""
        s = stream_factory()
        mock_param = Mock()
        mock_param.value = 0.5
        s._density.distribution = mock_param

        assert s.distribution == 0.5

    def test_distribution_property_raw(self, stream_factory):
        """distribution espone direttamente se non ha .value."""
        s = stream_factory()
        s._density.distribution = 0.7

        assert s.distribution == 0.7

    def test_pointer_speed_property(self, stream_factory):
        """pointer_speed espone .value dalla speed del pointer."""
        s = stream_factory()
        s._pointer.speed.value = 2.0

        assert s.pointer_speed == 2.0

    def test_loop_start_property(self, stream_factory):
        """loop_start dal PointerController."""
        s = stream_factory()
        s._pointer.loop_start = 0.1

        assert s.loop_start == 0.1

    def test_loop_end_property(self, stream_factory):
        """loop_end dal PointerController."""
        s = stream_factory()
        s._pointer.loop_end = 0.9

        assert s.loop_end == 0.9

    def test_loop_dur_property(self, stream_factory):
        """loop_dur dal PointerController."""
        s = stream_factory()
        s._pointer.loop_dur = 0.5

        assert s.loop_dur == 0.5

    def test_pitch_ratio_property(self, stream_factory):
        """pitch_ratio dal PitchController."""
        s = stream_factory()
        s._pitch.base_ratio = 1.5

        assert s.pitch_ratio == 1.5

    def test_pitch_semitones_property(self, stream_factory):
        """pitch_semitones dal PitchController."""
        s = stream_factory()
        s._pitch.base_semitones = 7.0

        assert s.pitch_semitones == 7.0

    def test_pitch_range_property(self, stream_factory):
        """pitch_range dal PitchController."""
        s = stream_factory()
        s._pitch.range = 2.0

        assert s.pitch_range == 2.0



# =============================================================================
# 12. TEST __repr__
# =============================================================================

class TestStreamRepr:
    """Test rappresentazione stringa."""

    def test_repr_contains_stream_id(self, stream_factory):
        """repr contiene stream_id."""
        s = stream_factory(stream_id='cloud_01')

        r = repr(s)

        assert 'cloud_01' in r

    def test_repr_contains_onset(self, stream_factory):
        """repr contiene onset."""
        s = stream_factory(onset=5.0)

        r = repr(s)

        assert '5.0' in r

    def test_repr_contains_duration(self, stream_factory):
        """repr contiene duration."""
        s = stream_factory(duration=10.0)

        r = repr(s)

        assert '10.0' in r

    def test_repr_contains_grain_count(self, stream_factory):
        """repr contiene numero di grani."""
        s = stream_factory(duration=0.3, inter_onset=0.1)
        s.generate_grains()

        r = repr(s)

        assert f'grains={len(s.grains)}' in r

    def test_repr_fill_factor_mode(self, stream_factory):
        """repr mostra mode=fill_factor se fill_factor presente."""
        s = stream_factory()
        s._density.fill_factor = 2.0

        r = repr(s)

        assert 'fill_factor' in r

    def test_repr_density_mode(self, stream_factory):
        """repr mostra mode=density se fill_factor e' None."""
        s = stream_factory()
        s._density.fill_factor = None

        r = repr(s)

        assert 'density' in r


# =============================================================================
# 13. TEST EDGE CASES
# =============================================================================

class TestStreamEdgeCases:
    """Test casi limite e boundary conditions."""

    def test_very_short_duration(self, stream_factory):
        """Duration molto breve (1 grano)."""
        s = stream_factory(duration=0.05, inter_onset=0.1)

        s.generate_grains()

        assert len(s.voices[0]) == 1

    def test_very_high_density(self, stream_factory):
        """Inter-onset molto piccolo genera molti grani."""
        s = stream_factory(duration=0.1, inter_onset=0.001)

        s.generate_grains()

        assert len(s.voices[0]) == 100

    def test_variable_inter_onset(self, stream_factory):
        """Inter-onset variabile (simula distribuzione asincrona)."""
        s = stream_factory(duration=1.0)

        call_count = [0]
        def variable_iot(elapsed_time, grain_dur):
            call_count[0] += 1
            return 0.05 if call_count[0] % 2 == 0 else 0.15

        s._density.calculate_inter_onset = Mock(side_effect=variable_iot)

        s.generate_grains()

        # Deve completare senza errori
        assert len(s.voices[0]) > 0

    def test_grain_dur_varies_over_time(self, stream_factory):
        """grain_duration che cambia nel tempo."""
        s = stream_factory(duration=0.5, inter_onset=0.1)

        call_count = [0]
        def varying_dur(time):
            call_count[0] += 1
            return 0.03 + 0.01 * call_count[0]

        s.grain_duration.get_value = Mock(side_effect=varying_dur)

        s.generate_grains()

        # Ogni grano deve avere durata diversa
        durations = [g.duration for g in s.voices[0]]
        assert len(set(durations)) > 1


# =============================================================================
# 14. TEST INTEGRAZIONE END-TO-END (con mock leggeri)
# =============================================================================

class TestStreamIntegration:
    """Test di integrazione che verifica il flusso completo."""

    def test_grain_fields_coherent(self, stream_factory):
        """Tutti i campi di ogni grano sono coerenti."""
        s = stream_factory(
            onset=1.0,
            duration=0.5,
            inter_onset=0.1,
            grain_dur_value=0.05,
            volume_value=-6.0,
            pan_value=0.5,
        )

        s.generate_grains()

        for grain in s.grains:
            assert grain.onset >= 1.0
            assert grain.duration == pytest.approx(0.05)
            assert grain.volume == pytest.approx(-6.0)
            assert grain.pan == pytest.approx(0.5)
            assert grain.sample_table == 1
            assert grain.envelope_table == 2

    def test_multivoice_grain_count(self, stream_factory):
        """Multi-voice: totale grani = somma grani per voce."""
        s = stream_factory(max_voices=4, duration=0.5, inter_onset=0.1)

        s.generate_grains()

        expected_total = sum(len(v) for v in s.voices)
        assert len(s.grains) == expected_total

    def test_onsets_monotonically_increasing_per_voice(self, stream_factory):
        """Dentro ogni voce, gli onset crescono."""
        s = stream_factory(max_voices=3, duration=0.5, inter_onset=0.1)

        s.generate_grains()

        for voice in s.voices:
            for i in range(1, len(voice)):
                assert voice[i].onset > voice[i - 1].onset

    def test_pitch_controller_called_every_grain(self, stream_factory):
        """PitchController.calculate chiamato per ogni grano creato."""
        s = stream_factory(max_voices=2, duration=0.3, inter_onset=0.1)

        s.generate_grains()

        total_grains = len(s.grains)
        assert s._pitch.calculate.call_count == total_grains

    def test_pointer_controller_called_every_grain(self, stream_factory):
        """PointerController.calculate chiamato per ogni grano creato."""
        s = stream_factory(max_voices=2, duration=0.3, inter_onset=0.1)

        s.generate_grains()

        total_grains = len(s.grains)
        assert s._pointer.calculate.call_count == total_grains

    def test_window_selection_per_grain(self, stream_factory):
        """WindowController.select_window chiamato per ogni grano."""
        s = stream_factory(duration=0.3, inter_onset=0.1)

        s.generate_grains()

        assert s._window_controller.select_window.call_count == len(s.grains)


# =============================================================================
# 15. TEST PARAMETRIZZATI
# =============================================================================

class TestStreamParametrized:
    """Test parametrizzati per copertura sistematica."""

    @pytest.mark.parametrize("duration,inter_onset,expected_min,expected_max", [
            (1.0, 0.1, 10, 11),      # float accumulation: 10*0.1 != 1.0 in IEEE 754
            (1.0, 0.2, 5, 6),        # stessa ragione
            (0.5, 0.1, 5, 6),        # stessa ragione
            (0.1, 0.1, 1, 1),        # nessun accumulo (1 sola iterazione)
            (0.0, 0.1, 0, 0),        # zero duration, zero grani
        ])
    def test_grain_count_parametrized(self, stream_factory,
                                       duration, inter_onset,
                                       expected_min, expected_max):
        """Verifica conteggio grani per diverse combinazioni."""
        s = stream_factory(duration=duration, inter_onset=inter_onset)

        s.generate_grains()

        count = len(s.voices[0])
        assert expected_min <= count <= expected_max

    @pytest.mark.parametrize("onset", [0.0, 1.0, 10.0, 100.0])
    def test_grain_onset_offset(self, stream_factory, onset):
        """Primo grano ha onset == stream onset."""
        s = stream_factory(onset=onset, duration=0.3, inter_onset=0.1)

        s.generate_grains()

        assert s.voices[0][0].onset == pytest.approx(onset)

    @pytest.mark.parametrize("max_voices", [1, 2, 5, 10])
    def test_voice_count(self, stream_factory, max_voices):
        """Single voice stream: voices contiene sempre esattamente 1 lista."""
        s = stream_factory(max_voices=max_voices, duration=0.3, inter_onset=0.1)

        s.generate_grains()

        assert len(s.voices) == 1