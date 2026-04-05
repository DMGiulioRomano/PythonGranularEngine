# tests/controllers/test_voice_manager.py
"""
test_voice_manager.py

Suite TDD per voice_manager.py

Moduli sotto test (da scrivere):
- VoiceConfig (frozen dataclass)
- VoiceManager (orchestratore strategy)

VoiceConfig:
  pitch_offset: float    # semitoni
  pointer_offset: float  # normalizzato
  pan_offset: float      # gradi
  onset_offset: float    # secondi

VoiceManager:
  - Riceve max_voices + le quattro strategy (pitch, pointer, onset, pan)
  - Pre-computa VoiceConfig per ogni voice_index 0..max_voices-1
  - Voce 0 → VoiceConfig(0.0, 0.0, 0.0, 0.0) sempre
  - get_voice_config(voice_index) → VoiceConfig
  - pan_strategy usa pan_spread come parametro aggiuntivo

Principi:
  - VoiceConfig è frozen (immutabile dopo creazione)
  - Le strategy sono opzionali: se non fornite, offset = 0 per tutte le voci
  - VoiceManager è agnostico rispetto al tempo (la logica time-varying
    di num_voices è responsabilità di Stream.generate_grains)

Organizzazione:
  1.  VoiceConfig dataclass
  2.  VoiceManager costruzione
  3.  Voce 0 sempre zeros
  4.  Delega corretta alle strategy
  5.  Strategy opzionali (NullStrategy)
  6.  pan_spread passato correttamente alla pan strategy
  7.  Pre-computazione voice_configs
  8.  Edge cases
"""

import pytest
from unittest.mock import MagicMock


# =============================================================================
# IMPORT LAZY
# =============================================================================

def _get_module():
    from controllers.voice_manager import VoiceConfig, VoiceManager
    return VoiceConfig, VoiceManager


def _get_strategies():
    from strategies.voice_pitch_strategy import StepPitchStrategy
    from strategies.voice_onset_strategy import LinearOnsetStrategy
    from strategies.voice_pointer_strategy import LinearPointerStrategy
    from strategies.voice_pan_strategy import LinearPanStrategy, AdditivePanStrategy
    return StepPitchStrategy, LinearOnsetStrategy, LinearPointerStrategy, LinearPanStrategy, AdditivePanStrategy


# =============================================================================
# 1. VoiceConfig dataclass
# =============================================================================

class TestVoiceConfig:

    def test_can_be_instantiated(self):
        VoiceConfig, _ = _get_module()
        vc = VoiceConfig(pitch_offset=3.0, pointer_offset=0.1,
                         pan_offset=30.0, onset_offset=0.05)
        assert vc.pitch_offset == 3.0
        assert vc.pointer_offset == 0.1
        assert vc.pan_offset == 30.0
        assert vc.onset_offset == 0.05

    def test_is_frozen(self):
        """VoiceConfig non è mutabile dopo la creazione."""
        VoiceConfig, _ = _get_module()
        vc = VoiceConfig(pitch_offset=0.0, pointer_offset=0.0,
                         pan_offset=0.0, onset_offset=0.0)
        with pytest.raises((AttributeError, TypeError)):
            vc.pitch_offset = 5.0

    def test_zero_config(self):
        VoiceConfig, _ = _get_module()
        vc = VoiceConfig(0.0, 0.0, 0.0, 0.0)
        assert vc.pitch_offset == 0.0
        assert vc.pointer_offset == 0.0
        assert vc.pan_offset == 0.0
        assert vc.onset_offset == 0.0

    def test_equality(self):
        VoiceConfig, _ = _get_module()
        a = VoiceConfig(1.0, 2.0, 3.0, 4.0)
        b = VoiceConfig(1.0, 2.0, 3.0, 4.0)
        assert a == b

    def test_inequality(self):
        VoiceConfig, _ = _get_module()
        a = VoiceConfig(1.0, 0.0, 0.0, 0.0)
        b = VoiceConfig(2.0, 0.0, 0.0, 0.0)
        assert a != b


# =============================================================================
# 2. VoiceManager costruzione
# =============================================================================

class TestVoiceManagerConstruction:

    def test_can_be_instantiated_with_max_voices(self):
        _, VoiceManager = _get_module()
        vm = VoiceManager(max_voices=4)
        assert vm is not None

    def test_stores_max_voices(self):
        _, VoiceManager = _get_module()
        vm = VoiceManager(max_voices=6)
        assert vm.max_voices == 6

    def test_accepts_all_strategies(self):
        _, VoiceManager = _get_module()
        StepPitchStrategy, LinearOnsetStrategy, LinearPointerStrategy, LinearPanStrategy, _ = _get_strategies()
        vm = VoiceManager(
            max_voices=4,
            pitch_strategy=StepPitchStrategy(step=3.0),
            onset_strategy=LinearOnsetStrategy(step=0.05),
            pointer_strategy=LinearPointerStrategy(step=0.1),
            pan_strategy=LinearPanStrategy(),
            pan_spread=60.0,
        )
        assert vm is not None

    def test_max_voices_1_valid(self):
        _, VoiceManager = _get_module()
        vm = VoiceManager(max_voices=1)
        assert vm.max_voices == 1


# =============================================================================
# 3. Voce 0 sempre zeros
# =============================================================================

class TestVoiceZeroAlwaysZero:

    def test_voice_0_all_zeros_no_strategies(self):
        VoiceConfig, VoiceManager = _get_module()
        vm = VoiceManager(max_voices=4)
        vc = vm.get_voice_config(0)
        assert vc == VoiceConfig(0.0, 0.0, 0.0, 0.0)

    def test_voice_0_all_zeros_with_strategies(self):
        VoiceConfig, VoiceManager = _get_module()
        StepPitchStrategy, LinearOnsetStrategy, LinearPointerStrategy, LinearPanStrategy, _ = _get_strategies()
        vm = VoiceManager(
            max_voices=4,
            pitch_strategy=StepPitchStrategy(step=7.0),
            onset_strategy=LinearOnsetStrategy(step=1.0),
            pointer_strategy=LinearPointerStrategy(step=0.5),
            pan_strategy=LinearPanStrategy(),
            pan_spread=90.0,
        )
        vc = vm.get_voice_config(0)
        assert vc == VoiceConfig(0.0, 0.0, 0.0, 0.0)

    def test_voice_0_zero_regardless_of_pitch_strategy(self):
        VoiceConfig, VoiceManager = _get_module()
        StepPitchStrategy, *_ = _get_strategies()
        vm = VoiceManager(max_voices=3, pitch_strategy=StepPitchStrategy(step=12.0))
        assert vm.get_voice_config(0).pitch_offset == 0.0

    def test_voice_0_zero_regardless_of_onset_strategy(self):
        VoiceConfig, VoiceManager = _get_module()
        _, LinearOnsetStrategy, *_ = _get_strategies()
        vm = VoiceManager(max_voices=3, onset_strategy=LinearOnsetStrategy(step=5.0))
        assert vm.get_voice_config(0).onset_offset == 0.0


# =============================================================================
# 4. Delega corretta alle strategy
# =============================================================================

class TestVoiceManagerDelegation:

    def test_pitch_delegated_to_strategy(self):
        VoiceConfig, VoiceManager = _get_module()
        StepPitchStrategy, *_ = _get_strategies()
        vm = VoiceManager(max_voices=4, pitch_strategy=StepPitchStrategy(step=3.0))
        assert vm.get_voice_config(1).pitch_offset == pytest.approx(3.0)
        assert vm.get_voice_config(2).pitch_offset == pytest.approx(6.0)
        assert vm.get_voice_config(3).pitch_offset == pytest.approx(9.0)

    def test_onset_delegated_to_strategy(self):
        _, VoiceManager = _get_module()
        _, LinearOnsetStrategy, *_ = _get_strategies()
        vm = VoiceManager(max_voices=4, onset_strategy=LinearOnsetStrategy(step=0.1))
        assert vm.get_voice_config(1).onset_offset == pytest.approx(0.1)
        assert vm.get_voice_config(2).onset_offset == pytest.approx(0.2)

    def test_pointer_delegated_to_strategy(self):
        _, VoiceManager = _get_module()
        _, _, LinearPointerStrategy, *_ = _get_strategies()
        vm = VoiceManager(max_voices=4, pointer_strategy=LinearPointerStrategy(step=0.05))
        assert vm.get_voice_config(1).pointer_offset == pytest.approx(0.05)
        assert vm.get_voice_config(2).pointer_offset == pytest.approx(0.10)

    def test_pan_delegated_to_strategy_with_spread(self):
        """LinearPanStrategy con 4 voci e spread=60: voce 0 → -30, voce 3 → +30."""
        _, VoiceManager = _get_module()
        _, _, _, LinearPanStrategy, _ = _get_strategies()
        vm = VoiceManager(
            max_voices=4,
            pan_strategy=LinearPanStrategy(),
            pan_spread=60.0,
        )
        assert vm.get_voice_config(0).pan_offset == pytest.approx(0.0)   # voce 0 sempre 0
        # voce 1 con LinearPanStrategy: -30 + 1*(60/3) = -30 + 20 = -10
        assert vm.get_voice_config(1).pan_offset == pytest.approx(-10.0)
        assert vm.get_voice_config(3).pan_offset == pytest.approx(30.0)

    def test_all_strategies_combined(self):
        VoiceConfig, VoiceManager = _get_module()
        StepPitchStrategy, LinearOnsetStrategy, LinearPointerStrategy, _, AdditivePanStrategy = _get_strategies()
        vm = VoiceManager(
            max_voices=3,
            pitch_strategy=StepPitchStrategy(step=4.0),
            onset_strategy=LinearOnsetStrategy(step=0.1),
            pointer_strategy=LinearPointerStrategy(step=0.05),
            pan_strategy=AdditivePanStrategy(),
            pan_spread=10.0,
        )
        vc2 = vm.get_voice_config(2)
        assert vc2.pitch_offset == pytest.approx(8.0)
        assert vc2.onset_offset == pytest.approx(0.2)
        assert vc2.pointer_offset == pytest.approx(0.10)


# =============================================================================
# 5. Strategy opzionali (default → 0 per tutte le voci)
# =============================================================================

class TestOptionalStrategies:

    def test_no_pitch_strategy_all_zero(self):
        _, VoiceManager = _get_module()
        vm = VoiceManager(max_voices=4)
        for i in range(4):
            assert vm.get_voice_config(i).pitch_offset == 0.0

    def test_no_onset_strategy_all_zero(self):
        _, VoiceManager = _get_module()
        vm = VoiceManager(max_voices=4)
        for i in range(4):
            assert vm.get_voice_config(i).onset_offset == 0.0

    def test_no_pointer_strategy_all_zero(self):
        _, VoiceManager = _get_module()
        vm = VoiceManager(max_voices=4)
        for i in range(4):
            assert vm.get_voice_config(i).pointer_offset == 0.0

    def test_no_pan_strategy_all_zero(self):
        _, VoiceManager = _get_module()
        vm = VoiceManager(max_voices=4)
        for i in range(4):
            assert vm.get_voice_config(i).pan_offset == 0.0

    def test_partial_strategies(self):
        """Solo pitch strategy fornita, resto zero."""
        _, VoiceManager = _get_module()
        StepPitchStrategy, *_ = _get_strategies()
        vm = VoiceManager(max_voices=3, pitch_strategy=StepPitchStrategy(step=5.0))
        vc = vm.get_voice_config(1)
        assert vc.pitch_offset == pytest.approx(5.0)
        assert vc.onset_offset == 0.0
        assert vc.pointer_offset == 0.0
        assert vc.pan_offset == 0.0


# =============================================================================
# 6. pan_spread passato correttamente
# =============================================================================

class TestPanSpread:

    def test_pan_spread_zero_all_zero(self):
        _, VoiceManager = _get_module()
        _, _, _, LinearPanStrategy, _ = _get_strategies()
        vm = VoiceManager(max_voices=4, pan_strategy=LinearPanStrategy(), pan_spread=0.0)
        for i in range(4):
            assert vm.get_voice_config(i).pan_offset == 0.0

    def test_pan_spread_passed_to_strategy(self):
        """La pan strategy riceve spread corretto per ogni voce non-zero."""
        _, VoiceManager = _get_module()
        mock_pan = MagicMock()
        mock_pan.get_pan_offset.return_value = 15.0
        vm = VoiceManager(max_voices=3, pan_strategy=mock_pan, pan_spread=45.0)
        # Pre-computa all'init: controlla che voice_index=1 sia stato chiamato
        mock_pan.get_pan_offset.assert_any_call(
            voice_index=1, num_voices=3, spread=45.0
        )

    def test_default_pan_spread_is_zero(self):
        _, VoiceManager = _get_module()
        _, _, _, LinearPanStrategy, _ = _get_strategies()
        vm = VoiceManager(max_voices=4, pan_strategy=LinearPanStrategy())
        for i in range(4):
            assert vm.get_voice_config(i).pan_offset == 0.0


# =============================================================================
# 7. Pre-computazione voice_configs
# =============================================================================

class TestPrecomputedConfigs:

    def test_all_configs_precomputed(self):
        """voice_configs contiene max_voices elementi."""
        _, VoiceManager = _get_module()
        vm = VoiceManager(max_voices=5)
        assert len(vm.voice_configs) == 5

    def test_get_voice_config_consistent_with_precomputed(self):
        _, VoiceManager = _get_module()
        StepPitchStrategy, *_ = _get_strategies()
        vm = VoiceManager(max_voices=4, pitch_strategy=StepPitchStrategy(step=2.0))
        for i in range(4):
            assert vm.get_voice_config(i) == vm.voice_configs[i]

    def test_voice_configs_are_voice_config_instances(self):
        VoiceConfig, VoiceManager = _get_module()
        vm = VoiceManager(max_voices=3)
        for vc in vm.voice_configs:
            assert isinstance(vc, VoiceConfig)

    def test_get_voice_config_out_of_range_raises(self):
        _, VoiceManager = _get_module()
        vm = VoiceManager(max_voices=3)
        with pytest.raises((IndexError, ValueError)):
            vm.get_voice_config(5)


# =============================================================================
# 8. Edge cases
# =============================================================================

class TestEdgeCases:

    def test_max_voices_1_only_voice_0(self):
        VoiceConfig, VoiceManager = _get_module()
        vm = VoiceManager(max_voices=1)
        assert vm.get_voice_config(0) == VoiceConfig(0.0, 0.0, 0.0, 0.0)

    def test_chord_strategy_with_voice_manager(self):
        """Integrazione ChordPitchStrategy con VoiceManager."""
        _, VoiceManager = _get_module()
        from strategies.voice_pitch_strategy import ChordPitchStrategy
        vm = VoiceManager(max_voices=4, pitch_strategy=ChordPitchStrategy(chord="dom7"))
        assert vm.get_voice_config(0).pitch_offset == 0.0
        assert vm.get_voice_config(1).pitch_offset == 4.0
        assert vm.get_voice_config(2).pitch_offset == 7.0
        assert vm.get_voice_config(3).pitch_offset == 10.0

    def test_stochastic_pitch_with_voice_manager(self):
        _, VoiceManager = _get_module()
        from strategies.voice_pitch_strategy import StochasticPitchStrategy
        s = StochasticPitchStrategy(semitone_range=2.0, stream_id="test")
        vm = VoiceManager(max_voices=4, pitch_strategy=s)
        assert vm.get_voice_config(0).pitch_offset == 0.0
        for i in range(1, 4):
            assert -2.0 <= vm.get_voice_config(i).pitch_offset <= 2.0
