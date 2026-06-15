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
from parameters.pitch_unit import EdoUnit, RatioUnit


def _f(semitones: float) -> float:
    """Semitoni -> fattore di ratio (EDO 12), per le asserzioni pitch_factor."""
    return 2 ** (semitones / 12)
from shared.exceptions import InvalidStrategyConfigError


# =============================================================================
# HELPERS
# =============================================================================

SAMPLE_DUR = 5.0

def _build_stream(voices_params=None, stream_id='s1', seed=None):
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
        if seed is None:
            return Stream(params)
        return Stream(params, seed=seed)


# =============================================================================
# 1. Default — voices assente
# =============================================================================

class TestVoicesDefault:

    def test_no_voices_key_max_voices_1(self):
        s = _build_stream()
        assert s._voice_manager.max_voices == 1

    def test_no_voices_key_voice_config_0_is_identity(self):
        s = _build_stream()
        vc = s._voice_manager.get_voice_config(0, 0.0)
        assert vc == VoiceConfig(1.0, 0.0, 0.0, 0.0)

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
        assert s._voice_manager.get_voice_config(1, 0.0).pitch_factor == pytest.approx(_f(4.0))
        assert s._voice_manager.get_voice_config(2, 0.0).pitch_factor == pytest.approx(_f(8.0))

    def test_range_pitch_strategy(self):
        s = _build_stream({
            'num_voices': 3,
            'pitch': {'strategy': 'range', 'pitch_range': 12.0},
        })
        assert s._voice_manager.get_voice_config(0, 0.0).pitch_factor == 1.0
        assert s._voice_manager.get_voice_config(2, 0.0).pitch_factor == pytest.approx(_f(12.0))

    def test_chord_pitch_strategy_dom7(self):
        s = _build_stream({
            'num_voices': 4,
            'pitch': {'strategy': 'chord', 'chord': 'dom7'},
        })
        assert s._voice_manager.get_voice_config(1, 0.0).pitch_factor == pytest.approx(_f(4.0))
        assert s._voice_manager.get_voice_config(2, 0.0).pitch_factor == pytest.approx(_f(7.0))
        assert s._voice_manager.get_voice_config(3, 0.0).pitch_factor == pytest.approx(_f(10.0))

    def test_chord_pitch_strategy_maj(self):
        s = _build_stream({
            'num_voices': 3,
            'pitch': {'strategy': 'chord', 'chord': 'maj'},
        })
        assert s._voice_manager.get_voice_config(1, 0.0).pitch_factor == pytest.approx(_f(4.0))
        assert s._voice_manager.get_voice_config(2, 0.0).pitch_factor == pytest.approx(_f(7.0))

    def test_no_pitch_block_pitch_factor_identity(self):
        s = _build_stream({'num_voices': 3})
        for i in range(3):
            assert s._voice_manager.get_voice_config(i, 0.0).pitch_factor == 1.0


# =============================================================================
# 4. Onset strategy
# =============================================================================

class TestVoicesOnsetStrategy:

    def test_linear_onset_strategy(self):
        s = _build_stream({
            'num_voices': 3,
            'onset_offset': {'strategy': 'linear', 'step': 0.1},
        })
        assert s._voice_manager.get_voice_config(1, 0.0).onset_offset == pytest.approx(0.1)
        assert s._voice_manager.get_voice_config(2, 0.0).onset_offset == pytest.approx(0.2)

    def test_geometric_onset_strategy(self):
        s = _build_stream({
            'num_voices': 3,
            'onset_offset': {'strategy': 'geometric', 'step': 0.1, 'base': 2.0},
        })
        assert s._voice_manager.get_voice_config(1, 0.0).onset_offset == pytest.approx(0.1)
        assert s._voice_manager.get_voice_config(2, 0.0).onset_offset == pytest.approx(0.2)

    def test_no_onset_block_onset_offset_zero(self):
        s = _build_stream({'num_voices': 3})
        for i in range(3):
            assert s._voice_manager.get_voice_config(i, 0.0).onset_offset == 0.0


# =============================================================================
# 5. Pointer strategy
# =============================================================================

class TestVoicesPointerStrategy:

    def test_linear_pointer_strategy(self):
        s = _build_stream({
            'num_voices': 3,
            'pointer': {'strategy': 'linear', 'step': 0.1},
        })
        assert s._voice_manager.get_voice_config(1, 0.0).pointer_offset == pytest.approx(0.1)
        assert s._voice_manager.get_voice_config(2, 0.0).pointer_offset == pytest.approx(0.2)

    def test_pointer_normalized_default_false(self):
        s = _build_stream({
            'num_voices': 3,
            'pointer': {'strategy': 'linear', 'step': 0.1},
        })
        assert s._voice_pointer_normalized is False

    def test_pointer_normalized_flag_parsed(self):
        """`normalized: true` impostato e rimosso dai kwarg della strategy."""
        s = _build_stream({
            'num_voices': 3,
            'pointer': {'strategy': 'linear', 'step': 0.1, 'normalized': True},
        })
        assert s._voice_pointer_normalized is True
        # La strategy resta pura: step ancora applicato, nessun errore kwarg.
        assert s._voice_manager.get_voice_config(1, 0.0).pointer_offset == pytest.approx(0.1)

    def test_pointer_normalized_non_bool_raises(self):
        """`normalized` non-bool → InvalidFieldValueError (no coercion silenziosa)."""
        from shared.exceptions import InvalidFieldValueError
        with pytest.raises(InvalidFieldValueError):
            _build_stream({
                'num_voices': 3,
                'pointer': {'strategy': 'linear', 'step': 0.1, 'normalized': 'flase'},
            })

    def test_no_pointer_block_pointer_offset_zero(self):
        s = _build_stream({'num_voices': 3})
        for i in range(3):
            assert s._voice_manager.get_voice_config(i, 0.0).pointer_offset == 0.0


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
        assert s._voice_manager.get_voice_config(0, 0.0).pan_offset == 0.0
        assert s._voice_manager.get_voice_config(1, 0.0).pan_offset == pytest.approx(30.0)

    def test_spread_zero_all_pan_zero(self):
        s = _build_stream({
            'num_voices': 3,
            'pan': {'strategy': 'linear', 'spread': 0.0},
        })
        for i in range(3):
            assert s._voice_manager.get_voice_config(i, 0.0).pan_offset == 0.0

    def test_no_pan_block_pan_offset_zero(self):
        s = _build_stream({'num_voices': 3})
        for i in range(3):
            assert s._voice_manager.get_voice_config(i, 0.0).pan_offset == 0.0


# =============================================================================
# 7. Stochastic strategies — stream_id auto-iniettato
# =============================================================================

class TestStochasticStreamIdInjection:

    def test_stochastic_pitch_deterministic_by_stream_id(self):
        """Due stream con id diversi → pitch offsets diversi."""
        s1 = _build_stream({
            'num_voices': 3,
            'pitch': {'strategy': 'stochastic', 'pitch_range': 3.0},
        }, stream_id='stream_A')
        s2 = _build_stream({
            'num_voices': 3,
            'pitch': {'strategy': 'stochastic', 'pitch_range': 3.0},
        }, stream_id='stream_B')
        offsets1 = [s1._voice_manager.get_voice_config(i, 0.0).pitch_factor for i in range(1, 3)]
        offsets2 = [s2._voice_manager.get_voice_config(i, 0.0).pitch_factor for i in range(1, 3)]
        assert offsets1 != offsets2

    def test_stochastic_pitch_same_stream_id_reproducible(self):
        """Due stream con stesso id → stessi pitch offsets."""
        s1 = _build_stream({
            'num_voices': 3,
            'pitch': {'strategy': 'stochastic', 'pitch_range': 3.0},
        }, stream_id='same_stream')
        s2 = _build_stream({
            'num_voices': 3,
            'pitch': {'strategy': 'stochastic', 'pitch_range': 3.0},
        }, stream_id='same_stream')
        for i in range(3):
            assert (s1._voice_manager.get_voice_config(i, 0.0).pitch_factor ==
                    s2._voice_manager.get_voice_config(i, 0.0).pitch_factor)

    def test_stochastic_onset_stream_id_injected(self):
        """StochasticOnsetStrategy riceve stream_id automaticamente."""
        s = _build_stream({
            'num_voices': 3,
            'onset_offset': {'strategy': 'stochastic', 'max_offset': 0.2},
        }, stream_id='my_stream')
        # Se stream_id fosse mancante, solleverebbe TypeError
        for i in range(3):
            offset = s._voice_manager.get_voice_config(i, 0.0).onset_offset
            assert 0.0 <= offset <= 0.2

    def test_stochastic_pointer_stream_id_injected(self):
        """StochasticPointerStrategy riceve stream_id automaticamente."""
        s = _build_stream({
            'num_voices': 3,
            'pointer': {'strategy': 'stochastic', 'pointer_range': 0.1},
        }, stream_id='my_stream')
        for i in range(3):
            offset = s._voice_manager.get_voice_config(i, 0.0).pointer_offset
            assert -0.1 <= offset <= 0.1

    def test_random_pan_stream_id_injected(self):
        """RandomPanStrategy riceve stream_id automaticamente — no TypeError."""
        s = _build_stream({
            'num_voices': 3,
            'pan': {'strategy': 'random', 'spread': 60.0},
        }, stream_id='my_stream')
        assert s._voice_manager.get_voice_config(0, 0.0).pan_offset == 0.0
        for i in range(1, 3):
            offset = s._voice_manager.get_voice_config(i, 0.0).pan_offset
            assert -30.0 <= offset <= 30.0


# =============================================================================
# 7b. Seed propagato alle strategy stocastiche (issue #81)
# =============================================================================

import hashlib
import random as _random


def _seeded_pos(seed, stream_id, vi, lo=-1.0, hi=1.0):
    h = hashlib.sha256(f"{seed}:{stream_id}:{vi}".encode()).hexdigest()
    return _random.Random(int(h, 16)).uniform(lo, hi)


class TestSeedPropagation:

    def test_seed_injected_into_stochastic_pitch(self):
        s = _build_stream({
            'num_voices': 3,
            'pitch': {'strategy': 'stochastic', 'pitch_range': 3.0},
        }, stream_id='s1', seed=42)
        assert s._voice_manager._pitch_strategy.seed == 42

    def test_seed_injected_into_stochastic_onset(self):
        s = _build_stream({
            'num_voices': 3,
            'onset_offset': {'strategy': 'stochastic', 'max_offset': 0.2},
        }, stream_id='s1', seed=42)
        assert s._voice_manager._onset_strategy.seed == 42

    def test_seed_injected_into_stochastic_pointer(self):
        s = _build_stream({
            'num_voices': 3,
            'pointer': {'strategy': 'stochastic', 'pointer_range': 0.1},
        }, stream_id='s1', seed=42)
        assert s._voice_manager._pointer_strategy.seed == 42

    def test_seed_injected_into_random_pan(self):
        s = _build_stream({
            'num_voices': 3,
            'pan': {'strategy': 'random', 'spread': 60.0},
        }, stream_id='s1', seed=42)
        assert s._voice_manager._pan_strategy.seed == 42

    def test_default_seed_is_none_backward_compatible(self):
        """Senza seed: strategy.seed è None → fallback hash() (comportamento attuale)."""
        s = _build_stream({
            'num_voices': 3,
            'pitch': {'strategy': 'stochastic', 'pitch_range': 3.0},
        }, stream_id='s1')
        assert s._voice_manager._pitch_strategy.seed is None

    def test_seed_produces_hashlib_offset(self):
        """Col seed l'offset è il valore derivato via hashlib (riproducibile)."""
        s = _build_stream({
            'num_voices': 3,
            'pitch': {'strategy': 'stochastic', 'pitch_range': 2.0},
        }, stream_id='s1', seed=42)
        expected = EdoUnit(12).materialize(_seeded_pos(42, 's1', 1), 2.0)
        got = s._voice_manager.get_voice_config(1, 0.0).pitch_factor
        assert got == pytest.approx(expected)


# =============================================================================
# 8. Blocco voices parziale
# =============================================================================

class TestPartialVoicesBlock:

    def test_only_num_voices_no_strategies(self):
        s = _build_stream({'num_voices': 4})
        assert s._voice_manager.max_voices == 4
        for i in range(4):
            assert s._voice_manager.get_voice_config(i, 0.0).pitch_factor == 1.0
            assert s._voice_manager.get_voice_config(i, 0.0).onset_offset == 0.0

    def test_pitch_only_onset_zero(self):
        s = _build_stream({
            'num_voices': 3,
            'pitch': {'strategy': 'step', 'step': 3.0},
        })
        assert s._voice_manager.get_voice_config(1, 0.0).onset_offset == 0.0

    def test_onset_only_pitch_zero(self):
        s = _build_stream({
            'num_voices': 3,
            'onset_offset': {'strategy': 'linear', 'step': 0.1},
        })
        assert s._voice_manager.get_voice_config(1, 0.0).pitch_factor == 1.0


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

    def test_legacy_semitone_range_key_range_raises(self):
        """`semitone_range` (vecchia chiave) su strategy range → hard break."""
        with pytest.raises(InvalidStrategyConfigError) as exc:
            _build_stream({
                'num_voices': 3,
                'pitch': {'strategy': 'range', 'semitone_range': 12.0},
            })
        assert 'pitch_range' in exc.value.user_message()

    def test_legacy_semitone_range_key_stochastic_raises(self):
        """`semitone_range` (vecchia chiave) su strategy stochastic → hard break."""
        with pytest.raises(InvalidStrategyConfigError) as exc:
            _build_stream({
                'num_voices': 3,
                'pitch': {'strategy': 'stochastic', 'semitone_range': 6.0},
            })
        assert 'pitch_range' in exc.value.user_message()


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


# =============================================================================
# 13. U4 — YAML strategy kwargs con Envelope (list / dict / normalized)
# =============================================================================

class TestStrategyKwargsEnvelope:
    """
    _parse_strategy_kwarg converte automaticamente list/dict envelope-like
    in oggetti Envelope prima di passarli alla strategy factory.
    Scalari e stringhe restano invariati.
    """

    # --- scalar backward compat ---

    def test_scalar_step_constant_offset(self):
        """step: 2 → offset identico a time=0 e time=1."""
        s = _build_stream({
            'num_voices': 4,
            'pitch': {'strategy': 'step', 'step': 2},
        })
        vc0 = s._voice_manager.get_voice_config(1, 0.0)
        vc1 = s._voice_manager.get_voice_config(1, 1.0)
        assert vc0.pitch_factor == pytest.approx(vc1.pitch_factor)
        assert vc0.pitch_factor == pytest.approx(_f(2.0))

    # --- list envelope ---

    def test_list_envelope_step_varies_over_time(self):
        """step: [[0,0],[10,12]] → offset più grande a time=10 che a time=0."""
        s = _build_stream({
            'num_voices': 4,
            'pitch': {'strategy': 'step', 'step': [[0, 0], [10, 12]]},
        })
        vc_early = s._voice_manager.get_voice_config(1, 0.0)
        vc_late = s._voice_manager.get_voice_config(1, 10.0)
        assert vc_late.pitch_factor > vc_early.pitch_factor

    def test_list_envelope_onset_varies_over_time(self):
        """step: [[0,0],[10,0.2]] onset → varia nel tempo."""
        s = _build_stream({
            'num_voices': 4,
            'onset_offset': {'strategy': 'linear', 'step': [[0, 0.0], [10, 0.2]]},
        })
        vc_early = s._voice_manager.get_voice_config(1, 0.0)
        vc_late = s._voice_manager.get_voice_config(1, 10.0)
        assert vc_late.onset_offset > vc_early.onset_offset

    def test_list_envelope_pointer_varies_over_time(self):
        """step: [[0,0],[10,0.5]] linear pointer → varia nel tempo."""
        s = _build_stream({
            'num_voices': 4,
            'pointer': {'strategy': 'linear', 'step': [[0, 0.0], [10, 0.5]]},
        })
        vc_early = s._voice_manager.get_voice_config(1, 0.0)
        vc_late = s._voice_manager.get_voice_config(1, 10.0)
        assert vc_late.pointer_offset > vc_early.pointer_offset

    # --- pan_spread envelope ---

    def test_pan_spread_list_envelope_stored_as_envelope(self):
        """spread: [[0,0],[10,120]] → _pan_spread è Envelope nel VoiceManager."""
        from envelopes.envelope import Envelope
        s = _build_stream({
            'num_voices': 4,
            'pan': {'strategy': 'linear', 'spread': [[0, 0], [10, 120]]},
        })
        assert isinstance(s._voice_manager._pan_spread, Envelope)

    def test_pan_spread_envelope_pan_varies_over_time(self):
        """spread Envelope → pan_offset voce 1 più grande a t=10 che t=0."""
        s = _build_stream({
            'num_voices': 4,
            'pan': {'strategy': 'linear', 'spread': [[0, 0], [10, 120]]},
        })
        vc_early = s._voice_manager.get_voice_config(1, 0.0)
        vc_late = s._voice_manager.get_voice_config(1, 10.0)
        assert abs(vc_late.pan_offset) > abs(vc_early.pan_offset)

    # --- dict envelope normalized ---

    def test_dict_envelope_normalized_step(self):
        """step: {points: [[0,0],[1,12]], time_mode: normalized} → scala a stream.duration."""
        s = _build_stream({
            'num_voices': 4,
            'pitch': {
                'strategy': 'step',
                'step': {'points': [[0, 0], [1, 12]], 'time_mode': 'normalized'},
            },
        })
        # duration=10.0: normalized 1.0 → t=10.0
        vc_end = s._voice_manager.get_voice_config(1, 10.0)
        assert vc_end.pitch_factor == pytest.approx(_f(12.0))

    # --- string kwargs pass-through (chord name) ---

    def test_string_kwarg_not_converted(self):
        """chord: 'dom7' non viene convertito a float né Envelope."""
        s = _build_stream({
            'num_voices': 2,
            'pitch': {'strategy': 'chord', 'chord': 'dom7'},
        })
        # Se la stringa venisse convertita a float/Envelope, la factory crasherebbe.
        # dom7 = [0,4,7,10] → voce 1 → 4 semitoni → 2^(4/12)
        vc = s._voice_manager.get_voice_config(1, 0.0)
        assert vc.pitch_factor == pytest.approx(_f(4.0))

    def test_int_kwarg_preserved_as_int(self):
        """max_partial: 4 (int YAML) non viene convertito a float.

        SpectralPitchStrategy usa range(max_partial) — float crasherebbe con TypeError.
        """
        s = _build_stream({
            'num_voices': 4,
            'pitch': {'strategy': 'spectral', 'max_partial': 4},
        })
        vc = s._voice_manager.get_voice_config(1, 0.0)
        assert vc.pitch_factor == pytest.approx(_f(12.0))  # voce 1 = 1° parziale = 12 st

    def test_chord_inversion_int_preserved(self):
        """inversion: 1 (int YAML) non viene convertito a float.

        ChordPitchStrategy._invert usa slicing con inversion — float crasherebbe.
        maj inversion=1 → [0,3,8] → voce 1 = 3 semitoni.
        """
        s = _build_stream({
            'num_voices': 4,
            'pitch': {'strategy': 'chord', 'chord': 'maj', 'inversion': 1},
        })
        vc = s._voice_manager.get_voice_config(1, 0.0)
        assert vc.pitch_factor == pytest.approx(_f(3.0))


# =============================================================================
# 11. Unità di misura del pitch (voices.pitch.unit)
# =============================================================================

class TestVoicesPitchUnit:
    """Il blocco voices.pitch accetta `unit:` che possiede la geometria con cui
    la distribuzione materializza il fattore di ratio. Default: semitoni
    (EdoUnit(12)), retrocompatibile."""

    def test_default_unit_is_semitones(self):
        s = _build_stream({'num_voices': 2, 'pitch': {'strategy': 'step', 'step': 12.0}})
        assert isinstance(s._voice_manager.pitch_unit, EdoUnit)
        assert s._voice_manager.pitch_unit.divisions == 12

    def test_unit_quarter_tone_preset(self):
        s = _build_stream({
            'num_voices': 3,
            'pitch': {'strategy': 'step', 'step': 1.0, 'unit': 'quarter_tone'},
        })
        assert s._voice_manager.pitch_unit.divisions == 24

    def test_unit_edo_dict(self):
        s = _build_stream({
            'num_voices': 3,
            'pitch': {'strategy': 'range', 'pitch_range': 12.0, 'unit': {'edo': 31}},
        })
        assert s._voice_manager.pitch_unit.divisions == 31

    def test_unit_ratio(self):
        s = _build_stream({
            'num_voices': 2,
            'pitch': {'strategy': 'step', 'step': 1.5, 'unit': 'ratio'},
        })
        assert isinstance(s._voice_manager.pitch_unit, RatioUnit)

    def test_unit_not_a_strategy_kwarg(self):
        # `unit` non deve finire nel costruttore della distribuzione: step resta
        # l'unico kwarg, voce 1 → materialize(1, 5) sull'unità cents = 2^(5/1200).
        s = _build_stream({
            'num_voices': 2,
            'pitch': {'strategy': 'step', 'step': 5.0, 'unit': 'cents'},
        })
        assert s._voice_manager.get_voice_config(1, 0.0).pitch_factor == pytest.approx(2 ** (5.0 / 1200))


class TestVoicesPitchUnitJunction:
    """La giunzione in _create_grain converte l'offset col PitchUnit attivo.
    base pitch_ratio default = 1.0 (nessun blocco pitch nei params)."""

    def _grain_ratio_for_voice(self, voices_params, voice_index):
        s = _build_stream(voices_params)
        s._density = type('D', (), {'calculate_inter_onset': staticmethod(lambda t, d: 1.0)})()
        s.sample_table_num = 1
        s.window_table_map = {'hanning': 2}
        s.generate_grains()
        return s.voices[voice_index][0].pitch_ratio

    def test_default_semitones_octave(self):
        # step 12 semitoni -> 2^(12/12) = 2.0
        r = self._grain_ratio_for_voice(
            {'num_voices': 2, 'pitch': {'strategy': 'step', 'step': 12.0}}, 1)
        assert r == pytest.approx(2.0)

    def test_quarter_tone_half_octave(self):
        # step 12 quarti -> 2^(12/24) = sqrt(2)
        r = self._grain_ratio_for_voice(
            {'num_voices': 2, 'pitch': {'strategy': 'step', 'step': 12.0, 'unit': 'quarter_tone'}}, 1)
        assert r == pytest.approx(2 ** 0.5)

    def test_ratio_unit_geometric_step(self):
        # step 2.0 con unit ratio -> voce 1 = 2^1 = 2.0 (geometrico: amount^position)
        r = self._grain_ratio_for_voice(
            {'num_voices': 2, 'pitch': {'strategy': 'step', 'step': 2.0, 'unit': 'ratio'}}, 1)
        assert r == pytest.approx(2.0)

    def test_ratio_unit_geometric_step_voice_2(self):
        # step 2.0 ratio, voce 2 = 2^2 = 4.0 (ottave pulite, non lineare 2*step=4? sì 4)
        r = self._grain_ratio_for_voice(
            {'num_voices': 3, 'pitch': {'strategy': 'step', 'step': 2.0, 'unit': 'ratio'}}, 2)
        assert r == pytest.approx(4.0)

    def test_voice_0_unchanged_under_ratio(self):
        # voce 0 -> pitch_factor identità 1.0 -> base invariato
        r = self._grain_ratio_for_voice(
            {'num_voices': 2, 'pitch': {'strategy': 'step', 'step': 2.0, 'unit': 'ratio'}}, 0)
        assert r == pytest.approx(1.0)


class TestVoicesPitchUnitSemitoneLocked:
    """chord e spectral producono intervalli intrinsecamente in semitoni:
    in v1 accettano solo `semitones` (o unit assente). Altra unità → errore."""

    @pytest.mark.parametrize("strategy,extra", [
        ('chord', {'chord': 'dom7'}),
        ('spectral', {}),
    ])
    @pytest.mark.parametrize("unit", ['quarter_tone', 'cents', 'ratio', {'edo': 31}])
    def test_non_semitone_unit_rejected(self, strategy, extra, unit):
        with pytest.raises(InvalidStrategyConfigError):
            _build_stream({
                'num_voices': 4,
                'pitch': {'strategy': strategy, 'unit': unit, **extra},
            })

    def test_chord_without_unit_ok(self):
        s = _build_stream({'num_voices': 4, 'pitch': {'strategy': 'chord', 'chord': 'dom7'}})
        assert s._voice_manager.pitch_unit.divisions == 12

    def test_chord_explicit_semitones_ok(self):
        s = _build_stream({
            'num_voices': 4,
            'pitch': {'strategy': 'chord', 'chord': 'dom7', 'unit': 'semitones'},
        })
        assert s._voice_manager.pitch_unit.divisions == 12
