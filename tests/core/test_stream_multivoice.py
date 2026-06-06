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
    voice_pointer_normalized=False,
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
    s._voice_pointer_normalized = voice_pointer_normalized

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

    # Clip strategy: passthrough per test (preserva semantiche pre-U2).
    from strategies.grain_clip_strategy import PassthroughClipStrategy
    s._clip_strategy = PassthroughClipStrategy()

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

    def test_pointer_offset_rewrapped_into_buffer(self):
        """Voce con offset che supera sample_dur → pointer_pos re-wrappato in [0, sample_dur).

        Regressione issue #79: l'offset di voce veniva sommato DOPO il wrap base,
        lasciando grain.pointer_pos oltre sample_dur. Audio ok (renderer ri-wrappa),
        ma la partitura clippava le voci.
        """
        from strategies.voice_pointer_strategy import LinearPointerStrategy
        vm = VoiceManager(max_voices=2, pointer_strategy=LinearPointerStrategy(step=3.0))
        # sample_dur_sec=5.0 (default _make_stream); base=4.5, voce 1 offset=3.0 → 7.5
        s = _make_stream(duration=0.3, inter_onset=0.1, pointer_pos=4.5, voice_manager=vm)
        s.generate_grains()
        for voice_grains in s.voices:
            for g in voice_grains:
                assert 0.0 <= g.pointer_pos < s.sample_dur_sec
        # Voce 1: 4.5 + 3.0 = 7.5 → 7.5 % 5.0 = 2.5
        voice_1_pointers = [g.pointer_pos for g in s.voices[1]]
        assert all(p == pytest.approx(2.5) for p in voice_1_pointers)

    def test_normalized_linear_offset_scaled_by_sample_dur(self):
        """normalized=True → step interpretato come frazione del buffer.

        LinearPointerStrategy(step=0.2), sample_dur_sec=5.0, base=0.3.
        Voce 1 offset normalizzato = 0.2 * 5.0 = 1.0 → pointer = 0.3 + 1.0 = 1.3.
        """
        from strategies.voice_pointer_strategy import LinearPointerStrategy
        vm = VoiceManager(max_voices=2, pointer_strategy=LinearPointerStrategy(step=0.2))
        s = _make_stream(duration=0.3, inter_onset=0.1, pointer_pos=0.3,
                         voice_manager=vm, voice_pointer_normalized=True)
        s.generate_grains()
        voice_1_pointers = [g.pointer_pos for g in s.voices[1]]
        assert all(p == pytest.approx(1.3) for p in voice_1_pointers)

    def test_normalized_offset_rewrapped_into_buffer(self):
        """normalized=True con offset oltre il buffer → re-wrap in [0, sample_dur).

        step=0.6 normalizzato, sample_dur_sec=5.0 → offset=3.0; base=4.5
        → 4.5 + 3.0 = 7.5 → 7.5 % 5.0 = 2.5. Wrap valido come in modalità secondi.
        """
        from strategies.voice_pointer_strategy import LinearPointerStrategy
        vm = VoiceManager(max_voices=2, pointer_strategy=LinearPointerStrategy(step=0.6))
        s = _make_stream(duration=0.3, inter_onset=0.1, pointer_pos=4.5,
                         voice_manager=vm, voice_pointer_normalized=True)
        s.generate_grains()
        for voice_grains in s.voices:
            for g in voice_grains:
                assert 0.0 <= g.pointer_pos < s.sample_dur_sec
        voice_1_pointers = [g.pointer_pos for g in s.voices[1]]
        assert all(p == pytest.approx(2.5) for p in voice_1_pointers)

    def test_normalized_stochastic_offset_scaled_by_sample_dur(self):
        """normalized=True con stochastic → stesso cache[-1,1]*range, scalato per sample_dur_sec.

        Stesso stream_id → stesso seed → stesso fattore di cache. L'offset
        normalizzato deve essere quello in secondi moltiplicato per sample_dur_sec
        (range piccolo + base centrata → nessun wrap a confondere il confronto).
        """
        from strategies.voice_pointer_strategy import StochasticPointerStrategy
        vm_sec = VoiceManager(
            max_voices=2,
            pointer_strategy=StochasticPointerStrategy(pointer_range=0.1, stream_id='seed_x'),
        )
        vm_norm = VoiceManager(
            max_voices=2,
            pointer_strategy=StochasticPointerStrategy(pointer_range=0.1, stream_id='seed_x'),
        )
        s_sec = _make_stream(duration=0.3, inter_onset=0.1, pointer_pos=2.5, voice_manager=vm_sec)
        s_norm = _make_stream(duration=0.3, inter_onset=0.1, pointer_pos=2.5,
                              voice_manager=vm_norm, voice_pointer_normalized=True)
        s_sec.generate_grains()
        s_norm.generate_grains()
        off_sec = s_sec.voices[1][0].pointer_pos - 2.5
        off_norm = s_norm.voices[1][0].pointer_pos - 2.5
        assert off_sec != pytest.approx(0.0)  # cache non nullo
        assert off_norm == pytest.approx(off_sec * s_norm.sample_dur_sec)

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

    def test_identity_voice_config_identical_to_default(self):
        """VoiceConfig(1,0,0,0) produce lo stesso grano di nessun config."""
        s = _make_stream(pitch_ratio=1.0, pointer_pos=0.5, pan_value=0.0, onset=1.0)
        vc = VoiceConfig(1.0, 0.0, 0.0, 0.0)
        g = s._create_grain(elapsed_time=0.0, grain_dur=0.05, voice_config=vc)
        assert g.onset == pytest.approx(1.0)
        assert g.pitch_ratio == pytest.approx(1.0)
        assert g.pointer_pos == pytest.approx(0.5)
        assert g.pan == pytest.approx(0.0)

    def test_pitch_factor_multiplies_base(self):
        """pitch_factor=2.0 → pitch_ratio base moltiplicato per 2.0."""
        s = _make_stream(pitch_ratio=1.0)
        vc = VoiceConfig(pitch_factor=2.0, pointer_offset=0.0, pan_offset=0.0, onset_offset=0.0)
        g = s._create_grain(0.0, 0.05, voice_config=vc)
        assert g.pitch_ratio == pytest.approx(2.0)

    def test_pitch_factor_compounds_base(self):
        """Se il pitch base è 2.0 e pitch_factor=2.0 → 2.0 * 2.0 = 4.0."""
        s = _make_stream(pitch_ratio=2.0)
        vc = VoiceConfig(pitch_factor=2.0, pointer_offset=0.0, pan_offset=0.0, onset_offset=0.0)
        g = s._create_grain(0.0, 0.05, voice_config=vc)
        assert g.pitch_ratio == pytest.approx(4.0)

    def test_pointer_offset_added(self):
        """pointer_offset=0.2 viene sommato al pointer base."""
        s = _make_stream(pointer_pos=0.3)
        vc = VoiceConfig(pitch_factor=1.0, pointer_offset=0.2, pan_offset=0.0, onset_offset=0.0)
        g = s._create_grain(0.0, 0.05, voice_config=vc)
        assert g.pointer_pos == pytest.approx(0.5)

    def test_pan_offset_added(self):
        """pan_offset=30.0 viene sommato al pan base."""
        s = _make_stream(pan_value=10.0)
        vc = VoiceConfig(pitch_factor=1.0, pointer_offset=0.0, pan_offset=30.0, onset_offset=0.0)
        g = s._create_grain(0.0, 0.05, voice_config=vc)
        assert g.pan == pytest.approx(40.0)

    def test_onset_offset_added(self):
        """onset_offset=0.5 viene sommato all'onset assoluto."""
        s = _make_stream(onset=2.0)
        vc = VoiceConfig(pitch_factor=1.0, pointer_offset=0.0, pan_offset=0.0, onset_offset=0.5)
        g = s._create_grain(elapsed_time=0.1, grain_dur=0.05, voice_config=vc)
        # onset = stream_onset(2.0) + elapsed(0.1) + onset_offset(0.5) = 2.6
        assert g.onset == pytest.approx(2.6)

    def test_pitch_factor_below_one_descends(self):
        """pitch_factor=0.5 → pitch_ratio / 2 (ottava inferiore)."""
        s = _make_stream(pitch_ratio=1.0)
        vc = VoiceConfig(pitch_factor=0.5, pointer_offset=0.0, pan_offset=0.0, onset_offset=0.0)
        g = s._create_grain(0.0, 0.05, voice_config=vc)
        assert g.pitch_ratio == pytest.approx(0.5)

    def test_voice_config_none_uses_identity(self):
        """voice_config=None → comportamento identico a VoiceConfig(1,0,0,0)."""
        s = _make_stream(pitch_ratio=1.0, pointer_pos=0.5, pan_value=0.0, onset=1.0)
        g_none = s._create_grain(0.0, 0.05, voice_config=None)
        g_zero = s._create_grain(0.0, 0.05, voice_config=VoiceConfig(1.0, 0.0, 0.0, 0.0))
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


# =============================================================================
# generate_grains — envelope valutata per-grain
# =============================================================================

class TestGenerateGrainsEnvelopePerGrain:
    """Verifica che l'envelope della strategy venga valutata al tempo reale di
    ogni grain (voice_cursors[voice_index]), non una volta sola per stream."""

    def test_pitch_envelope_early_grains_smaller_than_late(self):
        """Voice 1 con step=Envelope([[0,0],[1,12]]): pitch cresce nel tempo."""
        from strategies.voice_pitch_strategy import StepPitchStrategy
        from envelopes.envelope import Envelope
        env = Envelope([[0.0, 0.0], [1.0, 12.0]])
        vm = VoiceManager(max_voices=2, pitch_strategy=StepPitchStrategy(step=env))
        # duration=1.0, inter_onset=0.1 → ~10 grani per voce a t=0.0,0.1,...,0.9
        s = _make_stream(duration=1.0, inter_onset=0.1, pitch_ratio=1.0, voice_manager=vm)
        s.generate_grains()
        v1 = s.voices[1]
        assert len(v1) >= 3, "servono almeno 3 grani per confrontare early/late"
        first_ratio = v1[0].pitch_ratio
        last_ratio = v1[-1].pitch_ratio
        # Al t=0: step=0 → ratio=1.0; al t=0.9: step=10.8 → ratio = 2^(10.8/12) ≈ 1.93
        assert last_ratio > first_ratio

    def test_pitch_envelope_voice_0_always_unmodified(self):
        """Anche con step envelope, voce 0 ha sempre pitch_ratio = base."""
        from strategies.voice_pitch_strategy import StepPitchStrategy
        from envelopes.envelope import Envelope
        env = Envelope([[0.0, 0.0], [1.0, 12.0]])
        vm = VoiceManager(max_voices=2, pitch_strategy=StepPitchStrategy(step=env))
        s = _make_stream(duration=1.0, inter_onset=0.1, pitch_ratio=1.0, voice_manager=vm)
        s.generate_grains()
        voice_0_ratios = [g.pitch_ratio for g in s.voices[0]]
        assert all(r == pytest.approx(1.0) for r in voice_0_ratios)

    def test_scalar_strategy_regression_constant_over_time(self):
        """Con step scalare, tutti i grani di voice 1 hanno stesso pitch_ratio."""
        from strategies.voice_pitch_strategy import StepPitchStrategy
        vm = VoiceManager(max_voices=2, pitch_strategy=StepPitchStrategy(step=12.0))
        s = _make_stream(duration=1.0, inter_onset=0.1, pitch_ratio=1.0, voice_manager=vm)
        s.generate_grains()
        v1_ratios = [g.pitch_ratio for g in s.voices[1]]
        expected = 2 ** (12.0 / 12.0)
        assert all(r == pytest.approx(expected) for r in v1_ratios)

    def test_pitch_envelope_values_match_envelope_at_voice_cursor(self):
        """Ogni grain di voice 1 ha pitch_ratio = 2^(step_at_t/12) con t=voice_cursor."""
        from strategies.voice_pitch_strategy import StepPitchStrategy
        from envelopes.envelope import Envelope
        env = Envelope([[0.0, 0.0], [1.0, 12.0]])
        vm = VoiceManager(max_voices=2, pitch_strategy=StepPitchStrategy(step=env))
        inter_onset = 0.1
        s = _make_stream(duration=1.0, inter_onset=inter_onset, pitch_ratio=1.0, voice_manager=vm)
        s.generate_grains()
        v1 = s.voices[1]
        for i, grain in enumerate(v1):
            t = i * inter_onset
            expected_step = env.evaluate(t)
            expected_ratio = 2 ** (expected_step / 12.0)
            assert grain.pitch_ratio == pytest.approx(expected_ratio, rel=1e-4), (
                f"grain {i} at t={t:.1f}: expected ratio {expected_ratio:.4f}, got {grain.pitch_ratio:.4f}"
            )


# =============================================================================
# 7. GrainClipStrategy integration (Plan 001 U2)
# =============================================================================

class TestGrainClipStrategyIntegration:
    """generate_grains applica _clip_strategy in post-process.

    Default: OverflowMarginClipStrategy(margin=0.0) — esclude grain con
    onset >= stream_end o coda che sfora stream_end.
    """

    def test_default_excludes_grain_with_onset_past_stream_end(self):
        """Voce 1 con onset_offset enorme: grain spinti oltre stream_end → esclusi."""
        from strategies.voice_onset_strategy import LinearOnsetStrategy
        from strategies.grain_clip_strategy import OverflowMarginClipStrategy
        vm = VoiceManager(max_voices=2, onset_strategy=LinearOnsetStrategy(step=10.0))
        s = _make_stream(duration=1.0, onset=0.0, inter_onset=0.1,
                         grain_dur=0.05, voice_manager=vm)
        s._clip_strategy = OverflowMarginClipStrategy(margin=0.0)
        s.generate_grains()
        # voce 0: onsets in [0, 1.0), nessun offset → tutti dentro
        assert len(s.voices[0]) > 0
        for g in s.voices[0]:
            assert g.onset < 1.0
            assert g.onset + g.duration <= 1.0
        # voce 1: onset_offset=10.0 → tutti onset >= 10.0 → tutti esclusi
        assert s.voices[1] == []

    def test_default_filters_per_voice_independently(self):
        """Voice 0 dentro bounds, voice 1 fuori: solo voice 1 filtrata."""
        from strategies.voice_onset_strategy import LinearOnsetStrategy
        from strategies.grain_clip_strategy import OverflowMarginClipStrategy
        vm = VoiceManager(max_voices=2, onset_strategy=LinearOnsetStrategy(step=10.0))
        s = _make_stream(duration=1.0, onset=0.0, inter_onset=0.1,
                         grain_dur=0.05, voice_manager=vm)
        s._clip_strategy = OverflowMarginClipStrategy(margin=0.0)
        s.generate_grains()
        voice_0_count = len(s.voices[0])
        assert voice_0_count >= 9  # ~10 grani in 1.0s @ 0.1s IOT
        assert len(s.voices[1]) == 0

    def test_default_grains_flat_excludes_out_of_bounds(self):
        """stream.grains (flatten) non contiene grain fuori bounds."""
        from strategies.voice_onset_strategy import LinearOnsetStrategy
        from strategies.grain_clip_strategy import OverflowMarginClipStrategy
        vm = VoiceManager(max_voices=2, onset_strategy=LinearOnsetStrategy(step=10.0))
        s = _make_stream(duration=1.0, onset=0.0, inter_onset=0.1,
                         grain_dur=0.05, voice_manager=vm)
        s._clip_strategy = OverflowMarginClipStrategy(margin=0.0)
        s.generate_grains()
        stream_end = s.onset + s.duration
        for g in s.grains:
            assert g.onset < stream_end
            assert g.onset + g.duration <= stream_end

    def test_passthrough_strategy_keeps_out_of_bounds_grains(self):
        """PassthroughClipStrategy iniettata: grain fuori bounds presenti."""
        from strategies.voice_onset_strategy import LinearOnsetStrategy
        from strategies.grain_clip_strategy import PassthroughClipStrategy
        vm = VoiceManager(max_voices=2, onset_strategy=LinearOnsetStrategy(step=10.0))
        s = _make_stream(duration=1.0, onset=0.0, inter_onset=0.1,
                         grain_dur=0.05, voice_manager=vm)
        s._clip_strategy = PassthroughClipStrategy()
        s.generate_grains()
        # voce 1 ora ha grain con onset >= 10.0
        assert len(s.voices[1]) > 0
        assert all(g.onset >= 10.0 for g in s.voices[1])

    def test_grain_with_tail_exactly_at_stream_end_included(self):
        """grain.onset + grain.duration == stream_end → incluso (limit `<=`)."""
        from strategies.grain_clip_strategy import OverflowMarginClipStrategy
        # inter_onset=0.25, grain_dur=0.25 FP-safe: onsets 0, 0.25, 0.5, 0.75
        # ultimo grain: onset=0.75, coda=1.0 == stream_end → incluso
        s = _make_stream(duration=1.0, onset=0.0, inter_onset=0.25, grain_dur=0.25)
        s._clip_strategy = OverflowMarginClipStrategy(margin=0.0)
        s.generate_grains()
        onsets = [g.onset for g in s.grains]
        assert any(o == pytest.approx(0.75) for o in onsets)
        for g in s.grains:
            assert g.onset + g.duration <= 1.0 + 1e-9

    def test_grain_with_tail_overflow_excluded(self):
        """grain con coda che sfora stream_end → escluso (margin=0.0)."""
        from strategies.grain_clip_strategy import OverflowMarginClipStrategy
        # duration=1.0, grain_dur=0.2: grain con onset=0.9 → coda=1.1 > 1.0 → escluso
        s = _make_stream(duration=1.0, onset=0.0, inter_onset=0.1, grain_dur=0.2)
        s._clip_strategy = OverflowMarginClipStrategy(margin=0.0)
        s.generate_grains()
        for g in s.grains:
            assert g.onset + g.duration <= 1.0

    def test_margin_allows_tail_overflow(self):
        """margin=0.5 ammette coda oltre stream_end → piu' grain di margin=0.0."""
        from strategies.grain_clip_strategy import OverflowMarginClipStrategy
        s_strict = _make_stream(duration=1.0, onset=0.0, inter_onset=0.1, grain_dur=0.2)
        s_strict._clip_strategy = OverflowMarginClipStrategy(margin=0.0)
        s_strict.generate_grains()
        s_loose = _make_stream(duration=1.0, onset=0.0, inter_onset=0.1, grain_dur=0.2)
        s_loose._clip_strategy = OverflowMarginClipStrategy(margin=0.5)
        s_loose.generate_grains()
        # con margin=0.0 grain con coda > 1.0 esclusi, con margin=0.5 inclusi
        assert len(s_loose.grains) > len(s_strict.grains)
        # coda max con margin=0.0
        for g in s_strict.grains:
            assert g.onset + g.duration <= 1.0 + 1e-9
        # coda max con margin=0.5
        for g in s_loose.grains:
            assert g.onset + g.duration <= 1.5 + 1e-9

    def test_stream_with_nonzero_onset(self):
        """stream.onset != 0: stream_end = onset + duration calcolato corretto."""
        from strategies.grain_clip_strategy import OverflowMarginClipStrategy
        s = _make_stream(duration=1.0, onset=5.0, inter_onset=0.1, grain_dur=0.05)
        s._clip_strategy = OverflowMarginClipStrategy(margin=0.0)
        s.generate_grains()
        for g in s.grains:
            assert g.onset >= 5.0
            assert g.onset < 6.0 + 1e-9
            assert g.onset + g.duration <= 6.0 + 1e-9
