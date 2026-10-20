"""
test_stream.py

Suite completa di test per stream.py (Stream).

Stream e' l'orchestratore centrale della sintesi granulare:
- Coordina tutti i controller (Pointer, Pitch, Density, Voice, Window)
- Gestisce il loop di generazione grani
- Mantiene backward compatibility con Generator e ScoreVisualizer

Ogni Stream di questo file passa dal costruttore (issue #283): la factory
`stream_factory` ne costruisce uno vero con `build_stream` e poi ne sostituisce
i collaboratori. I test che verificavano soltanto l'inoltro fra metodi privati
— `_init_stream_parameters` verso `ParameterOrchestrator`, `_init_controllers`
verso i quattro controller — sono usciti con l'oggetto a meta' su cui giravano.

Coverage:
  1.  contesto - campi da YAML e sample, campi obbligatori (dal costruttore)
  2.  grain.reverse - semantica YAML (dal costruttore)
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
from types import SimpleNamespace
from unittest.mock import Mock, patch, MagicMock, PropertyMock, call
from dataclasses import dataclass
from pge.core.stream_config import StreamContext, StreamConfig
from pge.core.stream import Stream
from conftest import flat_grains


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
    ptr.speed_ratio = Mock()
    ptr.speed_ratio.value = 1.0
    ptr.loop_start = None
    ptr.loop_end = None
    ptr.loop_dur = None
    return ptr


def _make_mock_pitch():
    """Crea un mock PitchController."""
    pitch = Mock()
    pitch.calculate = Mock(return_value=1.0)
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
    """Crea un mock VoiceManager compatibile con la nuova interfaccia VoiceConfig."""
    from pge.controllers.voice_manager import VoiceConfig
    vm = Mock()
    vm.max_voices = max_voices
    # get_voice_config(voice_index, time) → VoiceConfig(0,0,0,0) per tutti
    vm.get_voice_config = Mock(return_value=VoiceConfig(0.0, 0.0, 0.0, 0.0))
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


def _write_wav(directory, name='tone.wav', seconds=1.0):
    """Un wav di silenzio in `directory`, per chi costruisce lo Stream con
    uno YAML che `build_stream` non sa scrivere (un campo che manca, nessun
    blocco grain)."""
    import numpy as np
    import soundfile as sf
    sf.write(str(directory / name),
             np.zeros(int(48000 * seconds), dtype='float32'), 48000)


# =============================================================================
# FIXTURE: Stream con tutti i controller mockati
# =============================================================================

@pytest.fixture
def stream_factory(build_stream):
    """
    Factory per creare Stream con controller mockati.

    Lo Stream e' vero: lo costruisce `build_stream` attraverso `__init__`, e
    poi i collaboratori da isolare vengono sostituiti con dei mock (issue
    #283). L'isolamento resta, l'oggetto a meta' no: ogni attributo che la
    costruzione dichiara esiste, e un test non puo' piu' appoggiarsi a uno
    stato che in produzione non c'e'.
    """
    def _create(
        stream_id='test_stream',
        onset=0.0,
        duration=1.0,
        sample_dur_sec=5.0,
        max_voices=1,
        inter_onset=0.1,
        grain_dur_value=0.05,
        volume_value=-6.0,
        pan_value=0.5,
        reverse_mode='auto',
    ):
        # Il verso del grano passa dallo YAML, come in produzione: la chiave
        # `reverse:` lasciata vuota e' l'unico modo di forzarlo.
        if reverse_mode not in ('auto', True):
            raise ValueError(f"reverse_mode: 'auto' o True, non {reverse_mode!r}")
        grain = {'duration': 0.05, 'envelope': 'hanning'}
        if reverse_mode is True:
            grain['reverse'] = None
        s = build_stream(stream_id=stream_id, onset=onset, duration=duration,
                         grain=grain)

        # La durata del sample la decide il test, non il file di prova (un
        # secondo): chi la leggerebbe, i controller, e' sostituito qui sotto.
        s.sample_dur_sec = sample_dur_sec

        # Parametri diretti (mock Parameter). `read_direction` resta il None
        # che l'orchestratore scrive per il membro non dichiarato del gruppo
        # esclusivo 'grain_direction' (issue #207).
        s.grain_duration = _make_mock_parameter(grain_dur_value, 'grain_duration')
        s.volume = _make_mock_parameter(volume_value, 'volume')
        s.pan = _make_mock_parameter(pan_value, 'pan')
        s.reverse = _make_mock_parameter(0, 'reverse')

        # Controller mock
        s._pointer = _make_mock_pointer()
        s._pitch = _make_mock_pitch()
        s._density = _make_mock_density(inter_onset)
        s._window_controller = _make_mock_window_controller()

        # num_voices: mock Parameter che restituisce max_voices per ogni t
        _nv = Mock()
        _nv.get_value = Mock(return_value=float(max_voices))

        # scatter: mock Parameter che restituisce 0.0 (comportamento cluster)
        _sc = Mock()
        _sc.get_value = Mock(return_value=0.0)

        # Il controller del blocco `voices:` (#284): la generazione ne legge
        # il VoiceManager, num_voices, scatter e l'unita' dell'offset.
        s._voices_controller = SimpleNamespace(
            voice_manager=_make_mock_voice_manager(max_voices),
            num_voices=_nv,
            scatter=_sc,
            pointer_normalized=False,
        )

        # Riferimenti alle tabelle: li assegna il Generator dopo la
        # costruzione, e la generazione li pretende.
        s.sample_table_num = 1
        s.envelope_table_num = 2
        s.window_table_map = {'hanning': 2}

        # Clip strategy: passthrough per test (preserva semantiche pre-U2).
        # Test specifici per clipping iniettano la strategy esplicitamente.
        from pge.strategies.grain_clip_strategy import PassthroughClipStrategy
        s._clip_strategy = PassthroughClipStrategy()

        return s

    return _create


# =============================================================================
# 1. TEST CONTESTO, DAL COSTRUTTORE
# =============================================================================

class TestInitStreamContext:
    """I campi di contesto, chiesti al costruttore (issue #283).

    Prima si provavano chiamando `_init_stream_context` su un oggetto creato
    con `object.__new__(Stream)`; ora il comportamento pubblico che quei test
    verificavano — cosa lo Stream legge dallo YAML e dal sample, e cosa
    rifiuta — si chiede a `Stream(...)`.

    Un caso non ha un equivalente, ed e' uscito: il messaggio plurale di
    `MissingFieldError`. Dal costruttore non si raggiunge, perche' `sample`
    si controlla prima di ogni altro campo e il costruttore si ferma li'; il
    messaggio lo prova `tests/shared/test_engine_exceptions.py`.
    """

    def test_i_campi_vengono_dallo_yaml_e_dal_sample(self, build_stream):
        s = build_stream(stream_id='nuvola', onset=2.5, duration=1.5)

        assert s.stream_id == 'nuvola'
        assert s.onset == 2.5
        assert s.duration == 1.5
        assert s.sample == 'silence.wav'
        assert s.sample_dur_sec == pytest.approx(1.0)

    def test_stream_id_mancante_lo_nomina(self, tmp_path):
        from pge.shared.exceptions import MissingFieldError
        _write_wav(tmp_path)
        params = _minimal_yaml_params(sample='tone.wav')
        del params['stream_id']

        with pytest.raises(MissingFieldError,
                           match="Campo obbligatorio mancante") as exc_info:
            Stream(params, samples_dir=str(tmp_path))

        assert exc_info.value.fields == ['stream_id']

    def test_params_vuoti_rifiutati(self):
        """Senza niente il primo a mancare e' il sample."""
        from pge.shared.exceptions import MissingFieldError

        with pytest.raises(MissingFieldError) as exc_info:
            Stream({})

        assert exc_info.value.fields == ['sample']

    def test_campi_extra_ignorati(self, build_stream):
        s = build_stream(extra_field='ignored', another=42)

        assert s.stream_id == 'test_stream'
        assert not hasattr(s, 'extra_field')

    def test_sample_dur_sec_dal_file_non_dallo_yaml(self, build_stream):
        """La durata del sample la dice l'header del file: una chiave
        `sample_dur_sec` nello YAML non entra nel contesto."""
        s = build_stream(sample_dur_sec=99.0)

        assert s.sample_dur_sec == pytest.approx(1.0)


# =============================================================================
# 2. TEST grain.reverse, DAL COSTRUTTORE
# =============================================================================

class TestInitGrainReverse:
    """Semantica YAML di `grain.reverse`, chiesta al costruttore (issue #283).

    `_init_grain_reverse` resta com'e': la parita' di PGE-ls la estrae dal
    sorgente per AST e la esegue (`tests/test_pge_parity.py`).
    """

    @staticmethod
    def _con_grain(build_stream, **chiavi):
        return build_stream(grain={'duration': 0.05, 'envelope': 'hanning',
                                   **chiavi})

    def test_reverse_absent_means_auto(self, build_stream):
        """Chiave 'reverse' assente -> mode 'auto'."""
        assert self._con_grain(build_stream).grain_reverse_mode == 'auto'

    def test_reverse_none_means_forced_true(self, build_stream):
        """Chiave 'reverse:' vuota (None in YAML) -> mode True."""
        s = self._con_grain(build_stream, reverse=None)

        assert s.grain_reverse_mode is True

    @pytest.mark.parametrize('valore', [True, False, 'auto', 1])
    def test_reverse_con_un_valore_rifiutato(self, build_stream, valore):
        """Semantica ristretta: la chiave, se c'e', e' vuota."""
        from pge.shared.exceptions import InvalidFieldValueError

        with pytest.raises(InvalidFieldValueError,
                           match="grain.reverse") as exc_info:
            self._con_grain(build_stream, reverse=valore)

        assert exc_info.value.stream_id == 'test_stream'

    def test_no_grain_key_means_auto(self, tmp_path):
        """Nessun blocco 'grain' -> auto mode."""
        _write_wav(tmp_path)

        s = Stream(_minimal_yaml_params(sample='tone.wav'),
                   samples_dir=str(tmp_path))

        assert s.grain_reverse_mode == 'auto'


# =============================================================================
# 5. TEST __init__ (PIPELINE COMPLETA)
# =============================================================================

class TestStreamInit:
    """Test pipeline completa di inizializzazione."""

    def test_la_costruzione_non_genera_e_aspetta_i_riferimenti(
            self, build_stream):
        """Contratto lazy: la costruzione NON genera i grani, e i riferimenti
        alle tabelle li assegna il Generator dopo.

        Si ispeziona il backing field grezzo, non la property voices, che
        innesca generate_grains() al primo accesso.
        """
        s = build_stream(duration=2.0)

        assert s.stream_id == 'test_stream'
        assert s.duration == 2.0
        assert s._voices == []
        # Backing field unico (#201): la vista flat .grains e' derivata.
        assert not hasattr(s, '_grains')
        assert s.generated is False
        assert s.sample_table_num is None
        assert s.window_table_map is None
        assert s.envelope_table_num is None

    def test_missing_sample_raises_value_error(self):
        """Stream senza 'sample' -> ValueError leggibile."""
        params = _minimal_yaml_params()
        del params['sample']
        with pytest.raises(ValueError, match="sample"):
            Stream(params)


# =============================================================================
# 5b. TEST GENERAZIONE LAZY DEI GRANI (issue #117)
# =============================================================================

class TestLazyGrainGeneration:
    """
    Contratto lazy: i grani si materializzano alla PRIMA lettura di
    .voices, non alla costruzione. Questo permette al Generator di
    non generare i grani per gli stream cache-clean (il renderer short-circuita
    su is_dirty prima di leggere .voices), realizzando il risparmio di #117.
    """

    def test_accessing_voices_triggers_generation(self, stream_factory):
        """Leggere .voices su uno stream non generato innesca generate_grains."""
        s = stream_factory(duration=1.0, inter_onset=0.1)
        assert s.generated is False

        voices = s.voices

        assert s.generated is True
        assert len(voices) == 1            # max_voices=1
        assert len(voices[0]) > 0

    def test_voices_memoized_single_generation(self, stream_factory):
        """Accessi multipli a .voices generano i grani una sola volta."""
        s = stream_factory(duration=0.5, inter_onset=0.1)

        calls = []
        original = s.generate_grains

        def counting():
            calls.append(1)
            return original()

        s.generate_grains = counting

        first = s.voices
        second = s.voices

        assert len(calls) == 1
        assert first is second

    def test_repr_does_not_trigger_generation(self, stream_factory):
        """__repr__ NON deve materializzare i grani.

        _create_streams passa {stream} al diagnostic logger per ogni stream
        (#188): appena un handler formatta il record, un __repr__ che leggesse
        la property .voices rigenererebbe tutti gli stream annullando il
        risparmio.
        """
        s = stream_factory(duration=0.5, inter_onset=0.1)

        r = repr(s)

        assert s.generated is False
        assert 'test_stream' in r

    def test_explicit_generate_then_access_no_regeneration(self, stream_factory):
        """Dopo generate_grains() esplicita, leggere .voices non rigenera."""
        s = stream_factory(duration=0.5, inter_onset=0.1)
        s.generate_grains()

        calls = []
        original = s.generate_grains

        def counting():
            calls.append(1)
            return original()

        s.generate_grains = counting
        _ = s.voices

        assert len(calls) == 0

    def test_null_sample_raises_value_error(self):
        """Stream con sample: null -> ValueError leggibile."""
        params = _minimal_yaml_params()
        params['sample'] = None
        with pytest.raises(ValueError, match="sample"):
            Stream(params)

    def test_error_message_contains_stream_id(self):
        """L'errore include lo stream_id come attributo per facilitare il debug."""
        params = _minimal_yaml_params()
        params['stream_id'] = 'stream_problematico'
        params['sample'] = None
        with pytest.raises(ValueError) as exc_info:
            Stream(params)
        assert exc_info.value.stream_id == 'stream_problematico'
        assert 'stream_problematico' in exc_info.value.user_message()

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
        first_count = len(flat_grains(s))

        s.generate_grains()
        second_count = len(flat_grains(s))

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
        from pge.core.grain import Grain
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
        """Mode True (chiave presente e vuota) -> sempre reverse."""
        s = stream_factory(reverse_mode=True)
        s.reverse._probability_gate.should_apply.return_value = False

        result = s._calculate_grain_reverse(0.0)

        assert result is True

    def test_forced_mode_ignora_il_valore_del_parametro(self, stream_factory):
        """Il verso base del ramo forzato non dipende da `reverse._value`.

        Non e' una scelta ma una constatazione: `_init_grain_reverse` accetta
        `grain.reverse` solo vuota, quindi in questo ramo il valore e' sempre
        None. Leggerlo — e gestirne il caso Envelope — era codice morto
        (issue #207), rimosso insieme al ramo.
        """
        s = stream_factory(reverse_mode=True)
        s.reverse._probability_gate.should_apply.return_value = False

        for valore in (None, 0.0, 1.0, Mock()):
            s.reverse._value = valore
            assert s._calculate_grain_reverse(0.0) is True

    def test_un_envelope_su_grain_reverse_e_irraggiungibile(self, build_stream):
        """La controprova alla fonte: nessuno YAML puo' portare un Envelope
        dentro `reverse._value`, perche' la chiave non accetta valori."""
        with pytest.raises(ValueError, match="grain.reverse"):
            build_stream(grain={'duration': 0.05, 'envelope': 'hanning',
                                'reverse': [[0, 0], [1, 1]]})

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
        """pointer_speed espone .value da speed_ratio del PointerController.

        Il controller espone `speed_ratio` (Parameter), non `speed`: la property
        deve leggere quello. Mock con spec per garantire che `.speed` non esista
        (regressione issue #88: prima leggeva `_pointer.speed.value` → AttributeError)."""
        s = stream_factory()
        ptr = Mock(spec=['speed_ratio'])
        ptr.speed_ratio = Mock()
        ptr.speed_ratio.value = 2.0
        s._pointer = ptr

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

    def test_pitch_range_property(self, stream_factory):
        """pitch_range dal PitchController."""
        s = stream_factory()
        s._pitch.range = 2.0

        assert s.pitch_range == 2.0

    def test_scatter_property(self, stream_factory):
        """scatter espone il Parameter del controller delle voci (simmetrico a
        num_voices)."""
        s = stream_factory()
        sentinel = _make_mock_parameter(0.0, 'scatter')
        s._voices_controller.scatter = sentinel

        assert s.scatter is sentinel



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

        assert f'grains={len(flat_grains(s))}' in r

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

        for grain in flat_grains(s):
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
        assert len(flat_grains(s)) == expected_total

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

        total_grains = len(flat_grains(s))
        assert s._pitch.calculate.call_count == total_grains

    def test_pointer_controller_called_every_grain(self, stream_factory):
        """PointerController.calculate chiamato per ogni grano creato."""
        s = stream_factory(max_voices=2, duration=0.3, inter_onset=0.1)

        s.generate_grains()

        total_grains = len(flat_grains(s))
        assert s._pointer.calculate.call_count == total_grains

    def test_window_selection_per_grain(self, stream_factory):
        """WindowController.select_window chiamato per ogni grano."""
        s = stream_factory(duration=0.3, inter_onset=0.1)

        s.generate_grains()

        assert s._window_controller.select_window.call_count == len(flat_grains(s))


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
        """voices contiene esattamente max_voices liste (una per voce)."""
        s = stream_factory(max_voices=max_voices, duration=0.3, inter_onset=0.1)

        s.generate_grains()

        assert len(s.voices) == max_voices

# =============================================================================
# 16. TEST samples_dir (Fase 2 refactor library/CLI)
# =============================================================================

class TestStreamSamplesDir:
    """Stream(params, samples_dir=...) risolve il sample dalla directory
    data invece del globale PATHSAMPLES; default None = comportamento legacy."""

    def test_samples_dir_resolves_sample_from_custom_dir(self, tmp_path):
        _write_wav(tmp_path, seconds=2.0)
        params = _minimal_yaml_params(sample='tone.wav')

        s = Stream(params, samples_dir=str(tmp_path))

        assert s.sample_dur_sec == pytest.approx(2.0)

    def test_default_none_uses_pathsamples_fallback(self, tmp_path, monkeypatch):
        """Senza samples_dir vale il globale (parita' col comportamento
        storico, monkey-patch ancora efficace)."""
        _write_wav(tmp_path, seconds=1.0)
        monkeypatch.setattr('pge.shared.utils.PATHSAMPLES', str(tmp_path) + '/')
        params = _minimal_yaml_params(sample='tone.wav')

        s = Stream(params)

        assert s.sample_dur_sec == pytest.approx(1.0)

    def test_missing_sample_reports_custom_search_path(self, tmp_path):
        from pge.shared.exceptions import SampleNotFoundError
        params = _minimal_yaml_params(sample='missing.wav')

        with pytest.raises(SampleNotFoundError) as exc_info:
            Stream(params, samples_dir=str(tmp_path))

        err = exc_info.value
        assert str(tmp_path) in err.search_path
        assert err.stream_id == 'test_stream'
