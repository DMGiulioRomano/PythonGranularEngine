# tests/core/test_stream_multivoice.py
"""
test_stream_multivoice.py

Suite TDD per il sistema multi-voice di Stream.

Copre le modifiche a:
- generate_grains(): loop multi-voice con VoiceManager
- _create_grain(): applicazione VoiceConfig (pitch, pointer, pan, onset)

Principi testati:
- Voce 0 produce grani identici al comportamento mono-voice
- N voci → ~N volte i grani (overall density = per_voice_density × N)
- Ogni voce applica gli offset di VoiceConfig ai parametri del grano
- self.grains è il flatten ordinato per onset di tutte le voci
- self.voices ha un entry per ogni voce con grani

Queste suite si appoggiano alla stessa infrastruttura di mock di test_stream.py.
"""

import math
import pytest
from unittest.mock import Mock

from core.stream import Stream
from controllers.voice_manager import VoiceConfig, VoiceManager


# =============================================================================
# MOCK INFRASTRUCTURE (duplicata da test_stream.py per isolamento)
# =============================================================================

def _make_mock_parameter(value=0.0, name='mock_param'):
    p = Mock()
    p.name = name
    p._value = value
    p.value = value
    p.get_value = Mock(return_value=float(value))
    p._probability_gate = Mock()
    p._probability_gate.should_apply = Mock(return_value=False)
    p._mod_range = None
    return p


def _make_mock_pointer(return_value=0.5):
    ptr = Mock()
    ptr.calculate = Mock(return_value=return_value)
    ptr.get_speed = Mock(return_value=1.0)
    ptr.speed = Mock()
    ptr.speed.value = 1.0
    ptr.loop_start = None
    ptr.loop_end = None
    ptr.loop_dur = None
    return ptr


def _make_mock_pitch(return_value=1.0):
    pitch = Mock()
    pitch.calculate = Mock(return_value=return_value)
    pitch.base_ratio = return_value
    pitch.base_semitones = None
    pitch.range = 0.0
    return pitch


def _make_mock_density(inter_onset=0.1):
    dens = Mock()
    dens.calculate_inter_onset = Mock(return_value=inter_onset)
    dens.density = 10.0
    dens.fill_factor = None
    dens.distribution = Mock()
    dens.distribution.value = 0.0
    return dens


def _make_mock_window_controller():
    wc = Mock()
    wc.select_window = Mock(return_value='hanning')
    return wc


def _make_stream(
    duration=1.0,
    onset=0.0,
    inter_onset=0.1,
    grain_dur=0.05,
    pitch_ratio=1.0,
    pointer_pos=0.5,
    pan_value=0.0,
    voice_manager=None,
    num_voices_fn=None,
    scatter_fn=None,
    density_side_effect=None,
):
    """Crea uno Stream con tutti i controller mockati e VoiceManager reale/mock.

    num_voices_fn: callable t → float, se None restituisce max_voices per ogni t.
    """
    s = object.__new__(Stream)
    s.stream_id = 'test_stream'
    s.onset = onset
    s.duration = duration
    s.sample = 'test.wav'
    s.sample_dur_sec = 5.0
    s.grain_reverse_mode = 'auto'

    s.grain_duration = _make_mock_parameter(grain_dur, 'grain_duration')
    s.volume = _make_mock_parameter(-6.0, 'volume')
    s.pan = _make_mock_parameter(pan_value, 'pan')
    s.reverse = _make_mock_parameter(0, 'reverse')
    s.grain_envelope = 'hanning'

    s._pointer = _make_mock_pointer(pointer_pos)
    s._pitch = _make_mock_pitch(pitch_ratio)
    s._window_controller = _make_mock_window_controller()

    s._voice_manager = voice_manager or VoiceManager(max_voices=1)

    # density: supporta side_effect per simulare distribution > 0
    if density_side_effect is not None:
        dens = Mock()
        dens.calculate_inter_onset = Mock(side_effect=density_side_effect)
        dens.density = 10.0
        dens.fill_factor = None
        dens.distribution = Mock()
        dens.distribution.value = 0.0
        s._density = dens
    else:
        s._density = _make_mock_density(inter_onset)

    # num_voices: mock Parameter che restituisce max_voices per default
    max_v = float(s._voice_manager.max_voices)
    nv = Mock()
    nv.get_value = Mock(
        side_effect=num_voices_fn if num_voices_fn is not None
        else lambda t: max_v
    )
    s._num_voices = nv

    # scatter: mock Parameter, default = 0.0 (cluster)
    sc = Mock()
    sc.get_value = Mock(
        side_effect=scatter_fn if scatter_fn is not None
        else lambda t: 0.0
    )
    s._scatter = sc

    s.sample_table_num = 1
    s.envelope_table_num = 2
    s.window_table_map = {'hanning': 2}

    s.voices = []
    s.grains = []
    s.generated = False

    return s


# =============================================================================
# 1. generate_grains — comportamento mono-voice (backward compat)
# =============================================================================

class TestGenerateGrainsBackwardCompat:
    """Con VoiceManager(max_voices=1) il comportamento è identico a prima."""

    def test_single_voice_grain_count(self):
        """1 voce, duration=1.0, inter_onset=0.1 → ~10 grani (floating point tolerance)."""
        s = _make_stream(duration=1.0, inter_onset=0.1)
        s.generate_grains()
        assert len(s.grains) in (10, 11)

    def test_single_voice_voices_list_has_one_entry(self):
        s = _make_stream(duration=1.0, inter_onset=0.1)
        s.generate_grains()
        assert len(s.voices) == 1

    def test_single_voice_grains_equals_voices_0(self):
        s = _make_stream(duration=1.0, inter_onset=0.1)
        s.generate_grains()
        assert s.grains == s.voices[0]

    def test_single_voice_onset_is_absolute(self):
        s = _make_stream(duration=0.5, onset=2.0, inter_onset=0.1)
        s.generate_grains()
        assert s.grains[0].onset == pytest.approx(2.0)

    def test_generated_flag_set(self):
        s = _make_stream()
        s.generate_grains()
        assert s.generated is True


# =============================================================================
# 2. generate_grains — multi-voice grain count
# =============================================================================

class TestGenerateGrainsMultiVoiceCount:

    def test_two_voices_double_grain_count(self):
        """2 voci, stessa density → 2× i grani totali."""
        vm = VoiceManager(max_voices=2)
        s1 = _make_stream(duration=1.0, inter_onset=0.1, voice_manager=VoiceManager(max_voices=1))
        s2 = _make_stream(duration=1.0, inter_onset=0.1, voice_manager=vm)
        s1.generate_grains()
        s2.generate_grains()
        assert len(s2.grains) == len(s1.grains) * 2

    def test_three_voices_triple_grain_count(self):
        vm = VoiceManager(max_voices=3)
        s1 = _make_stream(duration=1.0, inter_onset=0.1, voice_manager=VoiceManager(max_voices=1))
        s3 = _make_stream(duration=1.0, inter_onset=0.1, voice_manager=vm)
        s1.generate_grains()
        s3.generate_grains()
        assert len(s3.grains) == len(s1.grains) * 3

    def test_two_voices_voices_list_has_two_entries(self):
        vm = VoiceManager(max_voices=2)
        s = _make_stream(duration=1.0, inter_onset=0.1, voice_manager=vm)
        s.generate_grains()
        assert len(s.voices) == 2

    def test_each_voice_has_same_grain_count(self):
        vm = VoiceManager(max_voices=3)
        s = _make_stream(duration=1.0, inter_onset=0.1, voice_manager=vm)
        s.generate_grains()
        counts = [len(v) for v in s.voices]
        assert counts[0] == counts[1] == counts[2]

    def test_grains_is_flatten_of_all_voices(self):
        vm = VoiceManager(max_voices=2)
        s = _make_stream(duration=1.0, inter_onset=0.1, voice_manager=vm)
        s.generate_grains()
        expected = sorted(
            [g for voice in s.voices for g in voice],
            key=lambda g: g.onset
        )
        assert s.grains == expected

    def test_grains_sorted_by_onset(self):
        vm = VoiceManager(max_voices=2)
        s = _make_stream(duration=1.0, inter_onset=0.1, voice_manager=vm)
        s.generate_grains()
        onsets = [g.onset for g in s.grains]
        assert onsets == sorted(onsets)


# =============================================================================
# 3. generate_grains — voice 0 è sempre il riferimento
# =============================================================================

class TestGenerateGrainsVoiceZeroReference:

    def test_voice_0_pitch_unmodified(self):
        """Voce 0 non ha pitch offset → pitch_ratio identico al base."""
        from strategies.voice_pitch_strategy import StepPitchStrategy
        vm = VoiceManager(max_voices=2, pitch_strategy=StepPitchStrategy(step=12.0))
        s = _make_stream(duration=0.3, inter_onset=0.1, pitch_ratio=1.0, voice_manager=vm)
        s.generate_grains()
        voice_0_pitches = [g.pitch_ratio for g in s.voices[0]]
        assert all(p == pytest.approx(1.0) for p in voice_0_pitches)

    def test_voice_0_pointer_unmodified(self):
        from strategies.voice_pointer_strategy import LinearPointerStrategy
        vm = VoiceManager(max_voices=2, pointer_strategy=LinearPointerStrategy(step=0.3))
        s = _make_stream(duration=0.3, inter_onset=0.1, pointer_pos=0.5, voice_manager=vm)
        s.generate_grains()
        voice_0_pointers = [g.pointer_pos for g in s.voices[0]]
        assert all(p == pytest.approx(0.5) for p in voice_0_pointers)

    def test_voice_0_onset_unmodified(self):
        from strategies.voice_onset_strategy import LinearOnsetStrategy
        vm = VoiceManager(max_voices=2, onset_strategy=LinearOnsetStrategy(step=1.0))
        s = _make_stream(duration=0.3, onset=5.0, inter_onset=0.1, voice_manager=vm)
        s.generate_grains()
        # Voce 0: onset = stream_onset + elapsed (no offset)
        assert s.voices[0][0].onset == pytest.approx(5.0)

    def test_voice_0_pan_unmodified(self):
        from strategies.voice_pan_strategy import LinearPanStrategy
        vm = VoiceManager(max_voices=2, pan_strategy=LinearPanStrategy(), pan_spread=60.0)
        s = _make_stream(duration=0.3, inter_onset=0.1, pan_value=0.0, voice_manager=vm)
        s.generate_grains()
        voice_0_pans = [g.pan for g in s.voices[0]]
        assert all(p == pytest.approx(0.0) for p in voice_0_pans)


# =============================================================================
# 4. generate_grains — voice 1 riceve gli offset
# =============================================================================

class TestGenerateGrainsVoiceOneOffsets:

    def test_voice_1_pitch_offset_applied(self):
        """Voce 1 con StepPitchStrategy(step=12) → pitch_ratio = base * 2^(12/12) = 2.0."""
        from strategies.voice_pitch_strategy import StepPitchStrategy
        vm = VoiceManager(max_voices=2, pitch_strategy=StepPitchStrategy(step=12.0))
        s = _make_stream(duration=0.3, inter_onset=0.1, pitch_ratio=1.0, voice_manager=vm)
        s.generate_grains()
        voice_1_pitches = [g.pitch_ratio for g in s.voices[1]]
        expected = 2 ** (12.0 / 12.0)  # = 2.0
        assert all(p == pytest.approx(expected) for p in voice_1_pitches)

    def test_voice_1_pitch_offset_7_semitones(self):
        """Voce 1 con step=7 → pitch_ratio = 2^(7/12) ≈ 1.4983."""
        from strategies.voice_pitch_strategy import StepPitchStrategy
        vm = VoiceManager(max_voices=2, pitch_strategy=StepPitchStrategy(step=7.0))
        s = _make_stream(duration=0.3, inter_onset=0.1, pitch_ratio=1.0, voice_manager=vm)
        s.generate_grains()
        expected = 2 ** (7.0 / 12.0)
        voice_1_pitches = [g.pitch_ratio for g in s.voices[1]]
        assert all(p == pytest.approx(expected, rel=1e-4) for p in voice_1_pitches)

    def test_voice_1_pointer_offset_applied(self):
        """Voce 1 con LinearPointerStrategy(step=0.2) → pointer = base + 0.2."""
        from strategies.voice_pointer_strategy import LinearPointerStrategy
        vm = VoiceManager(max_voices=2, pointer_strategy=LinearPointerStrategy(step=0.2))
        s = _make_stream(duration=0.3, inter_onset=0.1, pointer_pos=0.3, voice_manager=vm)
        s.generate_grains()
        voice_1_pointers = [g.pointer_pos for g in s.voices[1]]
        assert all(p == pytest.approx(0.5) for p in voice_1_pointers)

    def test_voice_1_onset_offset_applied(self):
        """Voce 1 con LinearOnsetStrategy(step=0.5) → primo onset = onset + 0.0 + 0.5."""
        from strategies.voice_onset_strategy import LinearOnsetStrategy
        vm = VoiceManager(max_voices=2, onset_strategy=LinearOnsetStrategy(step=0.5))
        s = _make_stream(duration=0.3, onset=2.0, inter_onset=0.1, voice_manager=vm)
        s.generate_grains()
        # Voce 1, primo grano: onset = stream_onset + elapsed(0.0) + onset_offset(0.5) = 2.5
        assert s.voices[1][0].onset == pytest.approx(2.5)

    def test_voice_1_pan_offset_applied(self):
        """Voce 1 con LinearPanStrategy spread=60 → pan = base_pan + pan_offset."""
        from strategies.voice_pan_strategy import LinearPanStrategy
        # 2 voci, LinearPanStrategy: voce 0 = -30, voce 1 = +30
        vm = VoiceManager(max_voices=2, pan_strategy=LinearPanStrategy(), pan_spread=60.0)
        s = _make_stream(duration=0.3, inter_onset=0.1, pan_value=0.0, voice_manager=vm)
        s.generate_grains()
        voice_1_pans = [g.pan for g in s.voices[1]]
        assert all(p == pytest.approx(30.0) for p in voice_1_pans)


# =============================================================================
# 5. _create_grain con VoiceConfig
# =============================================================================

class TestCreateGrainWithVoiceConfig:

    def test_zero_voice_config_identical_to_default(self):
        """VoiceConfig(0,0,0,0) produce lo stesso grano di nessun config."""
        s = _make_stream(pitch_ratio=1.0, pointer_pos=0.5, pan_value=0.0, onset=1.0)
        vc = VoiceConfig(0.0, 0.0, 0.0, 0.0)
        g = s._create_grain(elapsed_time=0.0, grain_dur=0.05, voice_config=vc)
        assert g.onset == pytest.approx(1.0)
        assert g.pitch_ratio == pytest.approx(1.0)
        assert g.pointer_pos == pytest.approx(0.5)
        assert g.pan == pytest.approx(0.0)

    def test_pitch_offset_semitones_to_ratio(self):
        """pitch_offset=12 → pitch_ratio moltiplicato per 2^(12/12) = 2.0."""
        s = _make_stream(pitch_ratio=1.0)
        vc = VoiceConfig(pitch_offset=12.0, pointer_offset=0.0, pan_offset=0.0, onset_offset=0.0)
        g = s._create_grain(0.0, 0.05, voice_config=vc)
        assert g.pitch_ratio == pytest.approx(2.0)

    def test_pitch_offset_multiplies_base_ratio(self):
        """Se base_ratio=2.0 e pitch_offset=12 → 2.0 * 2.0 = 4.0."""
        s = _make_stream(pitch_ratio=2.0)
        vc = VoiceConfig(pitch_offset=12.0, pointer_offset=0.0, pan_offset=0.0, onset_offset=0.0)
        g = s._create_grain(0.0, 0.05, voice_config=vc)
        assert g.pitch_ratio == pytest.approx(4.0)

    def test_pointer_offset_added(self):
        """pointer_offset=0.2 viene sommato al pointer base."""
        s = _make_stream(pointer_pos=0.3)
        vc = VoiceConfig(pitch_offset=0.0, pointer_offset=0.2, pan_offset=0.0, onset_offset=0.0)
        g = s._create_grain(0.0, 0.05, voice_config=vc)
        assert g.pointer_pos == pytest.approx(0.5)

    def test_pan_offset_added(self):
        """pan_offset=30.0 viene sommato al pan base."""
        s = _make_stream(pan_value=10.0)
        vc = VoiceConfig(pitch_offset=0.0, pointer_offset=0.0, pan_offset=30.0, onset_offset=0.0)
        g = s._create_grain(0.0, 0.05, voice_config=vc)
        assert g.pan == pytest.approx(40.0)

    def test_onset_offset_added(self):
        """onset_offset=0.5 viene sommato all'onset assoluto."""
        s = _make_stream(onset=2.0)
        vc = VoiceConfig(pitch_offset=0.0, pointer_offset=0.0, pan_offset=0.0, onset_offset=0.5)
        g = s._create_grain(elapsed_time=0.1, grain_dur=0.05, voice_config=vc)
        # onset = stream_onset(2.0) + elapsed(0.1) + onset_offset(0.5) = 2.6
        assert g.onset == pytest.approx(2.6)

    def test_negative_pitch_offset(self):
        """pitch_offset=-12 → pitch_ratio / 2 (ottava inferiore)."""
        s = _make_stream(pitch_ratio=1.0)
        vc = VoiceConfig(pitch_offset=-12.0, pointer_offset=0.0, pan_offset=0.0, onset_offset=0.0)
        g = s._create_grain(0.0, 0.05, voice_config=vc)
        assert g.pitch_ratio == pytest.approx(0.5)

    def test_voice_config_none_uses_zeros(self):
        """voice_config=None → comportamento identico a VoiceConfig(0,0,0,0)."""
        s = _make_stream(pitch_ratio=1.0, pointer_pos=0.5, pan_value=0.0, onset=1.0)
        g_none = s._create_grain(0.0, 0.05, voice_config=None)
        g_zero = s._create_grain(0.0, 0.05, voice_config=VoiceConfig(0.0, 0.0, 0.0, 0.0))
        assert g_none.pitch_ratio == g_zero.pitch_ratio
        assert g_none.pointer_pos == g_zero.pointer_pos
        assert g_none.pan == g_zero.pan
        assert g_none.onset == g_zero.onset


# =============================================================================
# 6. Reset e stato
# =============================================================================

class TestGenerateGrainsReset:

    def test_reset_on_regeneration(self):
        vm = VoiceManager(max_voices=2)
        s = _make_stream(duration=1.0, inter_onset=0.1, voice_manager=vm)
        s.generate_grains()
        first_count = len(s.grains)
        s.generate_grains()
        assert len(s.grains) == first_count

    def test_voices_cleared_on_regeneration(self):
        vm = VoiceManager(max_voices=2)
        s = _make_stream(duration=1.0, inter_onset=0.1, voice_manager=vm)
        s.generate_grains()
        s.generate_grains()
        assert len(s.voices) == 2


# =============================================================================
# 7. num_voices time-varying — generate_grains usa get_value(t) per tick
# =============================================================================

class TestNumVoicesTimeVarying:
    """
    generate_grains() deve chiedere num_voices.get_value(elapsed_time) ad ogni
    tick e usare il risultato come numero di voci attive in quel momento.
    """

    def test_num_voices_get_value_called_per_tick(self):
        """get_value viene chiamato una volta per voce per tick."""
        max_v = 3
        vm = VoiceManager(max_voices=max_v)
        s = _make_stream(duration=1.0, inter_onset=0.1, voice_manager=vm)
        s.generate_grains()
        ticks = len(s.voices[0])  # voice 0 ha un grano per tick
        assert s.num_voices.get_value.call_count == ticks * max_v

    def test_static_num_voices_all_voices_receive_grains(self):
        """Quando num_voices è costante == max_voices, tutte le voci ricevono grani."""
        vm = VoiceManager(max_voices=3)
        s = _make_stream(duration=1.0, inter_onset=0.1, voice_manager=vm)
        s.generate_grains()
        for voice_grains in s.voices:
            assert len(voice_grains) > 0

    def test_num_voices_1_only_voice_0_gets_grains(self):
        """Con num_voices=1 fisso (< max_voices), solo la voce 0 riceve grani."""
        vm = VoiceManager(max_voices=3)
        s = _make_stream(
            duration=1.0, inter_onset=0.1,
            voice_manager=vm,
            num_voices_fn=lambda t: 1.0,
        )
        s.generate_grains()
        assert len(s.voices[0]) > 0
        assert len(s.voices[1]) == 0
        assert len(s.voices[2]) == 0

    def test_num_voices_2_voices_0_and_1_get_grains(self):
        """Con num_voices=2, le voci 0 e 1 ricevono grani; la 2 no."""
        vm = VoiceManager(max_voices=3)
        s = _make_stream(
            duration=1.0, inter_onset=0.1,
            voice_manager=vm,
            num_voices_fn=lambda t: 2.0,
        )
        s.generate_grains()
        assert len(s.voices[0]) > 0
        assert len(s.voices[1]) > 0
        assert len(s.voices[2]) == 0

    def test_voices_list_length_always_equals_max_voices(self):
        """s.voices ha sempre max_voices entry anche quando num_voices < max."""
        vm = VoiceManager(max_voices=4)
        s = _make_stream(
            duration=1.0, inter_onset=0.1,
            voice_manager=vm,
            num_voices_fn=lambda t: 1.0,
        )
        s.generate_grains()
        assert len(s.voices) == 4

    def test_growing_voices_voice_0_has_more_grains_than_voice_3(self):
        """Voci attivate progressivamente: voce 0 accumula più grani di voce 3."""
        # num_voices cresce da 1 a 4 in 10 secondi
        vm = VoiceManager(max_voices=4)
        s = _make_stream(
            duration=10.0, inter_onset=1.0,
            voice_manager=vm,
            num_voices_fn=lambda t: min(4.0, 1.0 + t * 3.0 / 9.0),
        )
        s.generate_grains()
        assert len(s.voices[0]) > len(s.voices[3])

    def test_growing_voices_voice_3_eventually_receives_grains(self):
        """Quando num_voices raggiunge 4, anche la voce 3 deve ricevere grani."""
        vm = VoiceManager(max_voices=4)
        s = _make_stream(
            duration=10.0, inter_onset=1.0,
            voice_manager=vm,
            num_voices_fn=lambda t: min(4.0, 1.0 + t * 3.0 / 9.0),
        )
        s.generate_grains()
        assert len(s.voices[3]) > 0

    def test_voice_0_always_gets_grain_at_every_tick(self):
        """La voce 0 riceve sempre un grano (num_voices >= 1 per ogni tick)."""
        vm = VoiceManager(max_voices=4)
        total_ticks = 10
        s = _make_stream(
            duration=float(total_ticks), inter_onset=1.0,
            voice_manager=vm,
            num_voices_fn=lambda t: min(4.0, 1.0 + t),
        )
        s.generate_grains()
        assert len(s.voices[0]) == total_ticks


# =============================================================================
# 8. scatter — cursori per voce e blend IOT
# =============================================================================

import itertools

class TestScatter:
    """
    Con scatter=0 (default) il comportamento è identico all'originale.
    Con scatter>0 e IOT variabile, le voci divergono nel tempo.
    Con IOT costante (distribution=0 analog), scatter è sempre inerte.
    """

    # ── BACKWARD COMPAT ────────────────────────────────────────────────────

    def test_scatter_zero_constant_iot_same_grain_count(self):
        """scatter=0, IOT costante → ogni voce ha lo stesso numero di grani."""
        vm = VoiceManager(max_voices=2)
        s = _make_stream(duration=1.0, inter_onset=0.1, voice_manager=vm)
        s.generate_grains()
        assert len(s.voices[0]) == len(s.voices[1])

    def test_scatter_zero_varying_iot_voices_synchronized(self):
        """scatter=0, IOT variabile → voci usano sync_iot condiviso → stesso conteggio."""
        vm = VoiceManager(max_voices=2)
        iots = itertools.cycle([0.1, 0.2])
        s = _make_stream(
            duration=1.0, voice_manager=vm,
            density_side_effect=lambda t, gd: next(iots),
        )
        s.generate_grains()
        assert len(s.voices[0]) == len(s.voices[1])

    def test_scatter_zero_voices_list_length(self):
        """scatter=0 → s.voices ha max_v entry."""
        vm = VoiceManager(max_voices=3)
        s = _make_stream(duration=1.0, inter_onset=0.1, voice_manager=vm)
        s.generate_grains()
        assert len(s.voices) == 3

    def test_scatter_zero_grains_sorted_by_onset(self):
        """scatter=0 → s.grains ordinato per onset."""
        vm = VoiceManager(max_voices=2)
        s = _make_stream(duration=1.0, inter_onset=0.1, voice_manager=vm)
        s.generate_grains()
        onsets = [g.onset for g in s.grains]
        assert onsets == sorted(onsets)

    # ── SCATTER INERTE (IOT COSTANTE) ──────────────────────────────────────

    def test_scatter_one_constant_iot_voices_still_equal(self):
        """scatter=1, IOT costante → lerp(c, c, 1) = c → voci sincronizzate."""
        vm = VoiceManager(max_voices=2)
        s = _make_stream(
            duration=1.0, voice_manager=vm,
            scatter_fn=lambda t: 1.0,
            inter_onset=0.1,
        )
        s.generate_grains()
        assert len(s.voices[0]) == len(s.voices[1])

    # ── SCATTER ATTIVO (IOT VARIABILE) ─────────────────────────────────────

    def test_scatter_one_varying_iot_voices_diverge(self):
        """scatter=1, IOT alternato [0.1, 0.2] → v0 ha più grani di v1.

        Sequenza chiamate con 2 voci e scatter=1:
          iter 1: call→0.1 (sync_iot, v0 usa questo), call→0.2 (indep v1)
          iter 2: call→0.1 (sync_iot, v0), call→0.2 (indep v1)
          ...
          v0 avanza di 0.1 ogni iter → 10 grani in duration=1.0
          v1 avanza di 0.2 ogni iter → 5 grani in duration=1.0
        """
        vm = VoiceManager(max_voices=2)
        iots = itertools.cycle([0.1, 0.2])
        s = _make_stream(
            duration=1.0, voice_manager=vm,
            scatter_fn=lambda t: 1.0,
            density_side_effect=lambda t, gd: next(iots),
        )
        s.generate_grains()
        assert len(s.voices[0]) > len(s.voices[1])

    def test_scatter_one_varying_iot_v0_more_grains_than_v1(self):
        """scatter=1, sync_iot < indep_iot → v0 accumula più grani di v1."""
        # Il mock ritorna valori alternati [0.1, 0.2].
        # v0 usa sync_iot (call 1 di ogni iterazione = 0.1 quando entrambe le voci
        # sono attive), v1 usa indep_iot (call 2 = 0.2). v0 avanza più lentamente
        # → più grani in duration=1.0.
        vm = VoiceManager(max_voices=2)
        iots = itertools.cycle([0.1, 0.2])
        s = _make_stream(
            duration=1.0, voice_manager=vm,
            scatter_fn=lambda t: 1.0,
            density_side_effect=lambda t, gd: next(iots),
        )
        s.generate_grains()
        assert len(s.voices[0]) > len(s.voices[1])
        assert len(s.voices[1]) > 0

    def test_scatter_partial_blend_v0_more_than_v1(self):
        """scatter=0.5, IOT alternato → v1 avanza più veloce di v0 → v0 > v1."""
        # sync_iot (v0) < blend(sync, indep, 0.5) (v1): v0 ha più grani.
        vm = VoiceManager(max_voices=2)
        iots = itertools.cycle([0.1, 0.2])
        s = _make_stream(
            duration=1.0, voice_manager=vm,
            scatter_fn=lambda t: 0.5,
            density_side_effect=lambda t, gd: next(iots),
        )
        s.generate_grains()
        assert len(s.voices[0]) > len(s.voices[1])
        assert len(s.voices[1]) > 0

    # ── SCATTER COME ENVELOPE ──────────────────────────────────────────────

    def test_scatter_get_value_called_per_iteration(self):
        """_scatter.get_value viene chiamato una volta per iterazione del while."""
        vm = VoiceManager(max_voices=2)
        s = _make_stream(duration=1.0, inter_onset=0.1, voice_manager=vm)
        s.generate_grains()
        ticks = len(s.voices[0])
        assert s._scatter.get_value.call_count == ticks

    def test_scatter_grains_sorted_by_onset_with_diverging_cursors(self):
        """Anche con cursori divergenti, s.grains è ordinato per onset."""
        vm = VoiceManager(max_voices=2)
        iots = itertools.cycle([0.1, 0.2])
        s = _make_stream(
            duration=1.0, voice_manager=vm,
            scatter_fn=lambda t: 1.0,
            density_side_effect=lambda t, gd: next(iots),
        )
        s.generate_grains()
        onsets = [g.onset for g in s.grains]
        assert onsets == sorted(onsets)
