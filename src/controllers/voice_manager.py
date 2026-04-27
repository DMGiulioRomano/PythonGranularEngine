# src/controllers/voice_manager.py
"""
voice_manager.py

VoiceManager — orchestratore delle strategy di voce nella sintesi granulare
multi-voice.

Responsabilità:
- Ricevere le strategy per ogni dimensione (pitch, pointer, onset, pan)
- Calcolare VoiceConfig on-the-fly per ogni voice_index e time
- Esporre get_voice_config(voice_index, time) → VoiceConfig

NON è responsabilità di VoiceManager:
- La logica time-varying di num_voices (→ Stream.generate_grains)
- La variazione per-grano (→ PitchController + mod_range)
- Il calcolo dell'onset assoluto (→ Stream._create_grain)

Design:
- Tutte le strategy sono opzionali: se non fornite, offset = 0.0
- VoiceConfig è frozen (immutabile); ephemeral per chiamata
- Voice-0 invariant garantito dalle strategy (ogni get_*_offset(0, ...) → 0.0)
- pan_spread accetta float o Envelope; risolto con resolve_param al momento della call

Layering pointer (da design doc):
  pointer_final = base_pointer(t)        # PointerController
               + voice_pointer_offset    # VoicePointerStrategy (qui)
               + grain_jitter(t)         # mod_range per-grano
"""

from dataclasses import dataclass
from typing import Optional

from parameters.parameter import resolve_param, StrategyParam
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

    Calcola VoiceConfig on-the-fly per ogni chiamata a get_voice_config,
    delegando alle quattro strategy indipendenti e passando il time corrente.

    Args:
        max_voices:       numero massimo di voci (>= 1)
        pitch_strategy:   VoicePitchStrategy opzionale
        onset_strategy:   VoiceOnsetStrategy opzionale
        pointer_strategy: VoicePointerStrategy opzionale
        pan_strategy:     VoicePanStrategy opzionale
        pan_spread:       spread in gradi per la pan strategy (float o Envelope)

    Esempio:
        vm = VoiceManager(
            max_voices=4,
            pitch_strategy=ChordPitchStrategy(chord="dom7"),
            onset_strategy=LinearOnsetStrategy(step=0.05),
        )
        config = vm.get_voice_config(2, t=0.5)
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
        pan_spread: StrategyParam = 0.0,
    ):
        self.max_voices = max_voices
        self._pitch_strategy = pitch_strategy
        self._onset_strategy = onset_strategy
        self._pointer_strategy = pointer_strategy
        self._pan_strategy = pan_strategy
        self._pan_spread = pan_spread

    def get_voice_config(self, voice_index: int, time: float) -> VoiceConfig:
        """
        Calcola e restituisce il VoiceConfig per voice_index al tempo time.

        Voce 0 restituisce sempre VoiceConfig(0.0, 0.0, 0.0, 0.0) — garantito
        dalle strategy che ritornano 0.0 per voice_index == 0.

        Args:
            voice_index: indice della voce (0-based, < max_voices)
            time:        tempo corrente della voce in secondi

        Returns:
            VoiceConfig immutabile (ephemeral per chiamata)

        Raises:
            IndexError: se voice_index fuori range [0, max_voices-1]
        """
        if voice_index >= self.max_voices or voice_index < 0:
            raise IndexError(
                f"voice_index {voice_index} fuori range [0, {self.max_voices - 1}]"
            )

        pitch = (
            self._pitch_strategy.get_pitch_offset(voice_index, self.max_voices, time)
            if self._pitch_strategy is not None
            else 0.0
        )
        onset = (
            self._onset_strategy.get_onset_offset(voice_index, self.max_voices, time)
            if self._onset_strategy is not None
            else 0.0
        )
        pointer = (
            self._pointer_strategy.get_pointer_offset(voice_index, self.max_voices, time)
            if self._pointer_strategy is not None
            else 0.0
        )
        pan = (
            self._pan_strategy.get_pan_offset(
                voice_index=voice_index,
                num_voices=self.max_voices,
                spread=resolve_param(self._pan_spread, time),
                time=time,
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
