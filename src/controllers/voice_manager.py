# src/controllers/voice_manager.py
"""
voice_manager.py

VoiceManager — orchestratore delle strategy di voce nella sintesi granulare
multi-voice.

Responsabilità:
- Ricevere le strategy per ogni dimensione (pitch, pointer, onset, pan)
- Pre-computare VoiceConfig per ogni voice_index 0..max_voices-1
- Esporre get_voice_config(voice_index) → VoiceConfig
- Garantire che voce 0 abbia sempre VoiceConfig(0, 0, 0, 0)

NON è responsabilità di VoiceManager:
- La logica time-varying di num_voices (→ Stream.generate_grains)
- La variazione per-grano (→ PitchController + mod_range)
- Il calcolo dell'onset assoluto (→ Stream._create_grain)

Design:
- Tutte le strategy sono opzionali: se non fornite, offset = 0.0
- VoiceConfig è frozen (immutabile)
- Pre-computazione all'init: O(max_voices) upfront, O(1) in generate_grains

Layering pointer (da design doc):
  pointer_final = base_pointer(t)        # PointerController
               + voice_pointer_offset    # VoicePointerStrategy (qui)
               + grain_jitter(t)         # mod_range per-grano
"""

from dataclasses import dataclass
from typing import List, Optional

from strategies.voice_pitch_strategy import VoicePitchStrategy
from strategies.voice_onset_strategy import VoiceOnsetStrategy
from strategies.voice_pointer_strategy import VoicePointerStrategy
from strategies.voice_pan_strategy import VoicePanStrategy


# =============================================================================
# VOICE CONFIG
# =============================================================================

@dataclass(frozen=True)
class VoiceConfig:
    """
    Configurazione immutabile per una singola voce.

    Tutti i valori sono offset rispetto alla voce 0 (riferimento).
    Voce 0 ha sempre tutti i campi a 0.0.

    Attributes:
        pitch_offset:   offset in semitoni
        pointer_offset: offset normalizzato sulla posizione nel sample
        pan_offset:     offset in gradi rispetto al pan base dello stream
        onset_offset:   offset in secondi rispetto all'onset base
    """
    pitch_offset: float
    pointer_offset: float
    pan_offset: float
    onset_offset: float


# =============================================================================
# VOICE MANAGER
# =============================================================================

class VoiceManager:
    """
    Orchestratore delle strategy di voce.

    Pre-computa VoiceConfig per ogni voice_index 0..max_voices-1
    combinando le quattro strategy indipendenti.

    Args:
        max_voices:       numero massimo di voci (>= 1)
        pitch_strategy:   VoicePitchStrategy opzionale
        onset_strategy:   VoiceOnsetStrategy opzionale
        pointer_strategy: VoicePointerStrategy opzionale
        pan_strategy:     VoicePanStrategy opzionale
        pan_spread:       spread in gradi per la pan strategy (default 0.0)

    Esempio:
        vm = VoiceManager(
            max_voices=4,
            pitch_strategy=ChordPitchStrategy(chord="dom7"),
            onset_strategy=LinearOnsetStrategy(step=0.05),
        )
        config = vm.get_voice_config(2)
        # config.pitch_offset == 7.0 (terza nota di dom7)
        # config.onset_offset == 0.10
    """

    def __init__(
        self,
        max_voices: int,
        pitch_strategy: Optional[VoicePitchStrategy] = None,
        onset_strategy: Optional[VoiceOnsetStrategy] = None,
        pointer_strategy: Optional[VoicePointerStrategy] = None,
        pan_strategy: Optional[VoicePanStrategy] = None,
        pan_spread: float = 0.0,
    ):
        self.max_voices = max_voices
        self._pitch_strategy = pitch_strategy
        self._onset_strategy = onset_strategy
        self._pointer_strategy = pointer_strategy
        self._pan_strategy = pan_strategy
        self._pan_spread = pan_spread

        # Pre-computa tutti i VoiceConfig all'init
        self.voice_configs: List[VoiceConfig] = [
            self._compute(i) for i in range(max_voices)
        ]

    def _compute(self, voice_index: int) -> VoiceConfig:
        """Calcola VoiceConfig per un voice_index dato."""
        if voice_index == 0:
            return VoiceConfig(0.0, 0.0, 0.0, 0.0)

        pitch = (
            self._pitch_strategy.get_pitch_offset(voice_index, self.max_voices, 0.0)
            if self._pitch_strategy is not None
            else 0.0
        )
        onset = (
            self._onset_strategy.get_onset_offset(voice_index, self.max_voices, 0.0)
            if self._onset_strategy is not None
            else 0.0
        )
        pointer = (
            self._pointer_strategy.get_pointer_offset(voice_index, self.max_voices, 0.0)
            if self._pointer_strategy is not None
            else 0.0
        )
        pan = (
            self._pan_strategy.get_pan_offset(
                voice_index=voice_index,
                num_voices=self.max_voices,
                spread=self._pan_spread,
                time=0.0,
            )
            if self._pan_strategy is not None
            else 0.0
        )

        return VoiceConfig(
            pitch_offset=pitch,
            pointer_offset=pointer,
            pan_offset=pan,
            onset_offset=onset,
        )

    def get_voice_config(self, voice_index: int) -> VoiceConfig:
        """
        Restituisce il VoiceConfig pre-computato per voice_index.

        Args:
            voice_index: indice della voce (0-based, < max_voices)

        Returns:
            VoiceConfig immutabile

        Raises:
            IndexError: se voice_index >= max_voices
        """
        if voice_index >= self.max_voices or voice_index < 0:
            raise IndexError(
                f"voice_index {voice_index} fuori range [0, {self.max_voices - 1}]"
            )
        return self.voice_configs[voice_index]
