# tests/core/test_stream_voices_yaml.py
"""
test_stream_voices_yaml.py

Suite TDD per il parsing del blocco YAML `voices:` in Stream._init_voice_manager.

Verifica che Stream costruisca correttamente VoiceManager dai parametri YAML:

  voices:
    num_voices: 4
    pitch:
      strategy: chord
      chord: "dom7"
    onset_offset:
      strategy: linear
      step: 0.05
    pointer:
      strategy: stochastic
      pointer_range: 0.1
    pan:
      strategy: linear
      spread: 60

Principi:
- voices assente → VoiceManager(max_voices=1, nessuna strategy)
- stream_id auto-iniettato nelle strategy stochastiche
- spread estratto dal blocco pan e passato a VoiceManager
- strategy names invalidi → ValueError/KeyError

Organizzazione:
  1.  Default senza voices
  2.  num_voices
  3.  pitch strategy
  4.  onset_offset strategy
  5.  pointer strategy
  6.  pan strategy + spread
  7.  strategy stochastiche — stream_id auto-iniettato
  8.  Blocco voices parziale
  9.  Strategie invalide → errore
  10. Integrazione end-to-end: VoiceManager usato in generate_grains
"""

import pytest
from unittest.mock import patch, Mock

from core.stream import Stream
from controllers.voice_manager import VoiceManager, VoiceConfig
from strategies.voice_pitch_strategy import (
    StepPitchStrategy, RangePitchStrategy,
    ChordPitchStrategy, StochasticPitchStrategy,
)
from strategies.voice_onset_strategy import (
    LinearOnsetStrategy, GeometricOnsetStrategy, StochasticOnsetStrategy,
)
from strategies.voice_pointer_strategy import (
    LinearPointerStrategy, StochasticPointerStrategy,
)
from strategies.voice_pan_strategy import LinearPanStrategy


# =============================================================================
# HELPERS
# =============================================================================

SAMPLE_DUR = 5.0

def _build_stream(voices_params=None, stream_id='s1'):
    """Costruisce uno Stream reale con params YAML minimi + voices block."""
    params = {
        'stream_id': stream_id,
        'onset': 0.0,
        'duration': 10.0,
        'sample': 'test.wav',
    }
    if voices_params is not None:
        params['voices'] = voices_params

    with patch('core.stream.get_sample_duration', return_value=SAMPLE_DUR):
        return Stream(params)


# =============================================================================
# 1. Default — voices assente
# =============================================================================

class TestVoicesDefault:

    def test_no_voices_key_max_voices_1(self):
        s = _build_stream()
        assert s._voice_manager.max_voices == 1

    def test_no_voices_key_voice_config_0_is_zero(self):
        s = _build_stream()
        vc = s._voice_manager.get_voice_config(0)
        assert vc == VoiceConfig(0.0, 0.0, 0.0, 0.0)

    def test_empty_voices_dict_max_voices_1(self):
        s = _build_stream(voices_params={})
        assert s._voice_manager.max_voices == 1


# =============================================================================
# 2. num_voices
# =============================================================================

class TestNumVoices:

    def test_num_voices_4(self):
        s = _build_stream({'num_voices': 4})
        assert s._voice_manager.max_voices == 4

    def test_num_voices_1_explicit(self):
        s = _build_stream({'num_voices': 1})
        assert s._voice_manager.max_voices == 1

    def test_num_voices_default_when_absent(self):
        s = _build_stream({'pitch': {'strategy': 'step', 'step': 3.0}})
        assert s._voice_manager.max_voices == 1


# =============================================================================
# 3. Pitch strategy
# =============================================================================

class TestVoicesPitchStrategy:

    def test_step_pitch_strategy(self):
        s = _build_stream({
            'num_voices': 3,
            'pitch': {'strategy': 'step', 'step': 4.0},
        })
        assert s._voice_manager.get_voice_config(1).pitch_offset == pytest.approx(4.0)
        assert s._voice_manager.get_voice_config(2).pitch_offset == pytest.approx(8.0)

    def test_range_pitch_strategy(self):
        s = _build_stream({
            'num_voices': 3,
            'pitch': {'strategy': 'range', 'semitone_range': 12.0},
        })
        assert s._voice_manager.get_voice_config(0).pitch_offset == 0.0
        assert s._voice_manager.get_voice_config(2).pitch_offset == pytest.approx(12.0)

    def test_chord_pitch_strategy_dom7(self):
        s = _build_stream({
            'num_voices': 4,
            'pitch': {'strategy': 'chord', 'chord': 'dom7'},
        })
        assert s._voice_manager.get_voice_config(1).pitch_offset == 4.0
        assert s._voice_manager.get_voice_config(2).pitch_offset == 7.0
        assert s._voice_manager.get_voice_config(3).pitch_offset == 10.0

    def test_chord_pitch_strategy_maj(self):
        s = _build_stream({
            'num_voices': 3,
            'pitch': {'strategy': 'chord', 'chord': 'maj'},
        })
        assert s._voice_manager.get_voice_config(1).pitch_offset == 4.0
        assert s._voice_manager.get_voice_config(2).pitch_offset == 7.0

    def test_no_pitch_block_pitch_offset_zero(self):
        s = _build_stream({'num_voices': 3})
        for i in range(3):
            assert s._voice_manager.get_voice_config(i).pitch_offset == 0.0


# =============================================================================
# 4. Onset strategy
# =============================================================================

class TestVoicesOnsetStrategy:

    def test_linear_onset_strategy(self):
        s = _build_stream({
            'num_voices': 3,
            'onset_offset': {'strategy': 'linear', 'step': 0.1},
        })
        assert s._voice_manager.get_voice_config(1).onset_offset == pytest.approx(0.1)
        assert s._voice_manager.get_voice_config(2).onset_offset == pytest.approx(0.2)

    def test_geometric_onset_strategy(self):
        s = _build_stream({
            'num_voices': 3,
            'onset_offset': {'strategy': 'geometric', 'step': 0.1, 'base': 2.0},
        })
        assert s._voice_manager.get_voice_config(1).onset_offset == pytest.approx(0.1)
        assert s._voice_manager.get_voice_config(2).onset_offset == pytest.approx(0.2)

    def test_no_onset_block_onset_offset_zero(self):
        s = _build_stream({'num_voices': 3})
        for i in range(3):
            assert s._voice_manager.get_voice_config(i).onset_offset == 0.0


# =============================================================================
# 5. Pointer strategy
# =============================================================================

class TestVoicesPointerStrategy:

    def test_linear_pointer_strategy(self):
        s = _build_stream({
            'num_voices': 3,
            'pointer': {'strategy': 'linear', 'step': 0.1},
        })
        assert s._voice_manager.get_voice_config(1).pointer_offset == pytest.approx(0.1)
        assert s._voice_manager.get_voice_config(2).pointer_offset == pytest.approx(0.2)

    def test_no_pointer_block_pointer_offset_zero(self):
        s = _build_stream({'num_voices': 3})
        for i in range(3):
            assert s._voice_manager.get_voice_config(i).pointer_offset == 0.0


# =============================================================================
# 6. Pan strategy + spread
# =============================================================================

class TestVoicesPanStrategy:

    def test_linear_pan_strategy_with_spread(self):
        """LinearPanStrategy con 2 voci e spread=60: voce 1 → +30."""
        s = _build_stream({
            'num_voices': 2,
            'pan': {'strategy': 'linear', 'spread': 60.0},
        })
        assert s._voice_manager.get_voice_config(0).pan_offset == 0.0
        assert s._voice_manager.get_voice_config(1).pan_offset == pytest.approx(30.0)

    def test_spread_zero_all_pan_zero(self):
        s = _build_stream({
            'num_voices': 3,
            'pan': {'strategy': 'linear', 'spread': 0.0},
        })
        for i in range(3):
            assert s._voice_manager.get_voice_config(i).pan_offset == 0.0

    def test_no_pan_block_pan_offset_zero(self):
        s = _build_stream({'num_voices': 3})
        for i in range(3):
            assert s._voice_manager.get_voice_config(i).pan_offset == 0.0


# =============================================================================
# 7. Stochastic strategies — stream_id auto-iniettato
# =============================================================================

class TestStochasticStreamIdInjection:

    def test_stochastic_pitch_deterministic_by_stream_id(self):
        """Due stream con id diversi → pitch offsets diversi."""
        s1 = _build_stream({
            'num_voices': 3,
            'pitch': {'strategy': 'stochastic', 'semitone_range': 3.0},
        }, stream_id='stream_A')
        s2 = _build_stream({
            'num_voices': 3,
            'pitch': {'strategy': 'stochastic', 'semitone_range': 3.0},
        }, stream_id='stream_B')
        offsets1 = [s1._voice_manager.get_voice_config(i).pitch_offset for i in range(1, 3)]
        offsets2 = [s2._voice_manager.get_voice_config(i).pitch_offset for i in range(1, 3)]
        assert offsets1 != offsets2

    def test_stochastic_pitch_same_stream_id_reproducible(self):
        """Due stream con stesso id → stessi pitch offsets."""
        s1 = _build_stream({
            'num_voices': 3,
            'pitch': {'strategy': 'stochastic', 'semitone_range': 3.0},
        }, stream_id='same_stream')
        s2 = _build_stream({
            'num_voices': 3,
            'pitch': {'strategy': 'stochastic', 'semitone_range': 3.0},
        }, stream_id='same_stream')
        for i in range(3):
            assert (s1._voice_manager.get_voice_config(i).pitch_offset ==
                    s2._voice_manager.get_voice_config(i).pitch_offset)

    def test_stochastic_onset_stream_id_injected(self):
        """StochasticOnsetStrategy riceve stream_id automaticamente."""
        s = _build_stream({
            'num_voices': 3,
            'onset_offset': {'strategy': 'stochastic', 'max_offset': 0.2},
        }, stream_id='my_stream')
        # Se stream_id fosse mancante, solleverebbe TypeError
        for i in range(3):
            offset = s._voice_manager.get_voice_config(i).onset_offset
            assert 0.0 <= offset <= 0.2

    def test_stochastic_pointer_stream_id_injected(self):
        """StochasticPointerStrategy riceve stream_id automaticamente."""
        s = _build_stream({
            'num_voices': 3,
            'pointer': {'strategy': 'stochastic', 'pointer_range': 0.1},
        }, stream_id='my_stream')
        for i in range(3):
            offset = s._voice_manager.get_voice_config(i).pointer_offset
            assert -0.1 <= offset <= 0.1


# =============================================================================
# 8. Blocco voices parziale
# =============================================================================

class TestPartialVoicesBlock:

    def test_only_num_voices_no_strategies(self):
        s = _build_stream({'num_voices': 4})
        assert s._voice_manager.max_voices == 4
        for i in range(4):
            assert s._voice_manager.get_voice_config(i).pitch_offset == 0.0
            assert s._voice_manager.get_voice_config(i).onset_offset == 0.0

    def test_pitch_only_onset_zero(self):
        s = _build_stream({
            'num_voices': 3,
            'pitch': {'strategy': 'step', 'step': 3.0},
        })
        assert s._voice_manager.get_voice_config(1).onset_offset == 0.0

    def test_onset_only_pitch_zero(self):
        s = _build_stream({
            'num_voices': 3,
            'onset_offset': {'strategy': 'linear', 'step': 0.1},
        })
        assert s._voice_manager.get_voice_config(1).pitch_offset == 0.0


# =============================================================================
# 9. Strategy invalide → errore
# =============================================================================

class TestInvalidStrategies:

    def test_invalid_pitch_strategy_raises(self):
        with pytest.raises((KeyError, ValueError)):
            _build_stream({
                'num_voices': 2,
                'pitch': {'strategy': 'nonexistent_xyz'},
            })

    def test_invalid_onset_strategy_raises(self):
        with pytest.raises((KeyError, ValueError)):
            _build_stream({
                'num_voices': 2,
                'onset_offset': {'strategy': 'nonexistent_xyz'},
            })

    def test_invalid_pointer_strategy_raises(self):
        with pytest.raises((KeyError, ValueError)):
            _build_stream({
                'num_voices': 2,
                'pointer': {'strategy': 'nonexistent_xyz'},
            })


# =============================================================================
# 10. Integrazione: VoiceManager effettivamente usato in generate_grains
# =============================================================================

class TestVoicesYamlIntegration:

    def _prep_for_generate(self, s):
        """Prepara uno Stream reale per generate_grains senza Generator."""
        mock_density = Mock()
        mock_density.calculate_inter_onset = Mock(return_value=0.1)
        s._density = mock_density
        s.sample_table_num = 1
        s.window_table_map = {'hanning': 2}

    def test_num_voices_2_doubles_grains(self):
        """Con num_voices=2, generate_grains produce il doppio dei grani."""
        s1 = _build_stream({'num_voices': 1})
        s2 = _build_stream({'num_voices': 2})
        self._prep_for_generate(s1)
        self._prep_for_generate(s2)

        s1.generate_grains()
        s2.generate_grains()

        assert len(s2.grains) == len(s1.grains) * 2

    def test_chord_dom7_pitch_ratios_in_grains(self):
        """Voce 1 con dom7 ha pitch_ratio base × 2^(4/12)."""
        s = _build_stream({
            'num_voices': 2,
            'pitch': {'strategy': 'chord', 'chord': 'dom7'},
        })
        self._prep_for_generate(s)

        s.generate_grains()

        voice_1 = s.voices[1]
        expected = 2 ** (4.0 / 12.0)
        assert all(g.pitch_ratio == pytest.approx(expected, rel=1e-4) for g in voice_1)


# =============================================================================
# 11. num_voices come Envelope (time-varying)
# =============================================================================

class TestNumVoicesEnvelope:
    """
    num_voices può essere un Envelope YAML → Stream pre-computa max_voices
    e genera grains con il conteggio giusto per tick.
    """

    def test_envelope_num_voices_max_voices_precomputed_from_peak(self):
        """VoiceManager.max_voices == picco dell'envelope."""
        s = _build_stream({'num_voices': [[0, 1], [5, 4]]})
        assert s._voice_manager.max_voices == 4

    def test_envelope_num_voices_stored_as_parameter_with_get_value(self):
        """stream.num_voices espone get_value()."""
        s = _build_stream({'num_voices': [[0, 1], [5, 4]]})
        assert hasattr(s.num_voices, 'get_value')
        assert callable(s.num_voices.get_value)

    def test_envelope_num_voices_evaluates_1_at_start(self):
        s = _build_stream({'num_voices': [[0, 1], [5, 4]]})
        assert int(s.num_voices.get_value(0.0)) == 1

    def test_envelope_num_voices_evaluates_4_at_peak(self):
        s = _build_stream({'num_voices': [[0, 1], [5, 4]]})
        assert int(s.num_voices.get_value(5.0)) == 4

    def test_static_num_voices_stored_as_parameter(self):
        """Anche num_voices: 3 statico viene esposto come Parameter."""
        s = _build_stream({'num_voices': 3})
        assert hasattr(s.num_voices, 'get_value')
        assert int(s.num_voices.get_value(0.0)) == 3

    def test_envelope_num_voices_integration_voice_0_gets_all_ticks(self):
        """Con Envelope 1→4, la voce 0 riceve un grano per ogni tick."""
        s = _build_stream({'num_voices': [[0, 1], [5, 4]]})
        prep = lambda st: setattr(
            st, '_density',
            type('D', (), {'calculate_inter_onset': staticmethod(lambda t, d: 1.0)})()
        )
        prep(s)
        s.sample_table_num = 1
        s.window_table_map = {'hanning': 2}
        s.generate_grains()
        # voice 0 è sempre attiva → ha un grano per ogni tick
        assert len(s.voices[0]) == int(s.duration)

    def test_envelope_num_voices_integration_voice_3_activates_late(self):
        """Con Envelope 1→4, la voce 3 riceve meno grani della voce 0."""
        s = _build_stream({'num_voices': [[0, 1], [5, 4]]})
        s._density = type('D', (), {'calculate_inter_onset': staticmethod(lambda t, d: 1.0)})()
        s.sample_table_num = 1
        s.window_table_map = {'hanning': 2}
        s.generate_grains()
        assert len(s.voices[3]) < len(s.voices[0])
        assert len(s.voices[3]) > 0  # ma diventa attiva


# =============================================================================
# 12. scatter — parsing YAML
# =============================================================================

class TestScatterParsing:
    """
    scatter nel blocco voices: viene parsato come Parameter.
    Default = 0.0 (cluster, backward compat).
    """

    def test_no_scatter_default_is_zero(self):
        """Senza scatter nel blocco voices, default = 0.0."""
        s = _build_stream({'num_voices': 2})
        assert s._scatter.get_value(0.0) == pytest.approx(0.0)

    def test_scatter_static_value(self):
        """scatter: 0.8 → Parameter che vale 0.8."""
        s = _build_stream({'num_voices': 2, 'scatter': 0.8})
        assert s._scatter.get_value(0.0) == pytest.approx(0.8)

    def test_scatter_envelope(self):
        """scatter come Envelope [[0, 0.0], [10, 1.0]]."""
        s = _build_stream({'num_voices': 2, 'scatter': [[0, 0.0], [10, 1.0]]})
        assert s._scatter.get_value(0.0) == pytest.approx(0.0)
        assert s._scatter.get_value(10.0) == pytest.approx(1.0)
        assert 0.0 < s._scatter.get_value(5.0) < 1.0

    def test_no_voices_block_scatter_exists_and_is_zero(self):
        """Senza blocco voices, _scatter esiste con valore 0.0."""
        s = _build_stream()
        assert hasattr(s, '_scatter')
        assert s._scatter.get_value(0.0) == pytest.approx(0.0)

    def test_scatter_has_get_value(self):
        """_scatter espone get_value (è un Parameter)."""
        s = _build_stream({'num_voices': 2, 'scatter': 0.5})
        assert callable(s._scatter.get_value)
