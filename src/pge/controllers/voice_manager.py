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
- Ogni strategy possiede il proprio parametro (StrategyParam) e lo risolve
  internamente: il VoiceManager passa solo voice_index/num_voices/time

Layering pointer (da design doc):
  pointer_final = base_pointer(t)        # PointerController
               + voice_pointer_offset    # VoicePointerStrategy (qui)
               + grain_jitter(t)         # mod_range per-grano
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

import numpy as np

from pge.parameters.pitch_unit import PitchUnit, EdoUnit
from pge.strategies.voice_pitch_strategy import VoicePitchStrategy
from pge.strategies.voice_onset_strategy import VoiceOnsetStrategy
from pge.strategies.voice_pointer_strategy import VoicePointerStrategy
from pge.strategies.voice_pan_strategy import VoicePanStrategy


# =============================================================================
# VOICE CONFIG
# =============================================================================

@dataclass(frozen=True)
class VoiceConfig:
    """
    Configurazione immutabile per una singola voce.

    I valori sono offset rispetto alla voce 0 (riferimento); pitch è invece un
    fattore moltiplicativo. Voce 0 ha gli offset a 0.0 e pitch_factor a 1.0.

    Attributes:
        pitch_factor:   fattore di ratio sul pitch base (1.0 = identità),
                        prodotto dalla PitchUnit via la voice pitch strategy
        pointer_offset: offset sulla posizione di lettura nel sample. Unità
                        decisa dal flag `normalized` del blocco pointer YAML:
                        default = secondi nel sample; `normalized: true` =
                        frazione di sample_dur_sec (lo scaling avviene in
                        Stream._create_grain, che conosce sample_dur_sec).
        pan_offset:     offset in gradi rispetto al pan base dello stream
        onset_offset:   offset in secondi rispetto all'onset base
    """
    pitch_factor: float
    pointer_offset: float
    pan_offset: float
    onset_offset: float


@dataclass(frozen=True)
class VoiceCurve:
    """Una curva campionata da una voice strategy.

    dimension:   'pitch_offset' | 'pointer_offset' | 'pointer_range'
    voice_index: indice della voce, None per le curve non per-voce
    envelope:    la curva campionata

    Porta un Envelope e NON una ParameterCurve, deliberatamente. Per un
    Parameter un envelope piatto e' una costante travestita e va classificato
    come tale; per una curva di voce l'estensione temporale e' informazione —
    dice in quale finestra la voce esiste, perche' num_voices puo' accenderla
    e spegnerla nel tempo. Collassarla a 'constant' butterebbe via proprio il
    dato che la rende utile.

    Il nome pubblicato (`voice_pitch_offset__v2`) lo compone il consumatore
    dalla struttura: qui non si costruiscono stringhe.
    """
    dimension: str
    voice_index: Optional[int]
    envelope: 'Envelope'


# Densita' della griglia di campionamento degli offset per-voce. 33 e' il
# valore storico (issue #90): nato senza motivazione e mai rivisto, qui
# diventa un default esplicito e sovrascrivibile invece di una costante
# sepolta nel codice che campiona.
DEFAULT_OFFSET_SAMPLES = 33


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
        pan_strategy:     VoicePanStrategy opzionale (possiede il proprio parametro)

    Esempio:
        vm = VoiceManager(
            max_voices=4,
            pitch_strategy=ChordPitchStrategy(chord="dom7"),
            onset_strategy=LinearOnsetStrategy(step=0.05),
        )
        config = vm.get_voice_config(2, t=0.5)
        # config.pitch_factor == 2^(7/12) (quinta di dom7 come ratio)
        # config.onset_offset == 0.10
    """

    def __init__(
        self,
        max_voices: int,
        pitch_strategy: Optional[VoicePitchStrategy] = None,
        onset_strategy: Optional[VoiceOnsetStrategy] = None,
        pointer_strategy: Optional[VoicePointerStrategy] = None,
        pan_strategy: Optional[VoicePanStrategy] = None,
        pitch_unit: Optional[PitchUnit] = None,
    ):
        self.max_voices = max_voices
        self._pitch_strategy = pitch_strategy
        self._onset_strategy = onset_strategy
        self._pointer_strategy = pointer_strategy
        self._pan_strategy = pan_strategy
        # Unità che possiede la geometria del pitch voci: materializza il
        # fattore di ratio dentro la voice pitch strategy. Default semitoni
        # (EdoUnit(12)), retrocompat.
        self.pitch_unit: PitchUnit = pitch_unit if pitch_unit is not None else EdoUnit(12)

    def get_voice_config(self, voice_index: int, time: float) -> VoiceConfig:
        """
        Calcola e restituisce il VoiceConfig per voice_index al tempo time.

        Voce 0 restituisce sempre VoiceConfig(1.0, 0.0, 0.0, 0.0) — garantito
        dalle strategy (pitch_factor 1.0, offset 0.0 per voice_index == 0).

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
            self._pitch_strategy.get_pitch_factor(
                voice_index, self.max_voices, time, self.pitch_unit
            )
            if self._pitch_strategy is not None
            else 1.0
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
                time=time,
            )
            if self._pan_strategy is not None
            else 0.0
        )

        return VoiceConfig(
            pitch_factor=pitch,
            pointer_offset=pointer,
            pan_offset=pan,
            onset_offset=onset,
        )

    # =========================================================================
    # CURVE DEGLI OFFSET PER-VOCE
    # =========================================================================

    def offset_curves(
        self,
        duration: float,
        *,
        samples: int = DEFAULT_OFFSET_SAMPLES,
        active_voices: Optional[Callable[[float], float]] = None,
    ) -> List[VoiceCurve]:
        """Campiona le strategy e restituisce le curve degli offset per-voce.

        Args:
            duration: estensione temporale su cui campionare.
            samples: densita' della griglia (default: comportamento storico).
            active_voices: callable t -> numero di voci attive, per troncare le
                curve alla finestra in cui la voce esiste. None -> tutte
                attive. E' un predicato iniettato, non un Parameter posseduto:
                la logica time-varying di num_voices resta fuori da qui.
        """
        from pge.envelopes.envelope import Envelope

        grid = np.linspace(0.0, duration, samples)
        curves: List[VoiceCurve] = []

        has_pitch = self._pitch_strategy is not None
        has_pointer = self._pointer_strategy is not None

        def is_active(voice_index, t):
            if active_voices is None:
                return True
            return int(active_voices(t)) > voice_index

        def carries_information(points):
            """Una curva identicamente nulla non dice niente: si scarta."""
            return len(points) >= 2 and any(
                abs(value) > 1e-9 for _, value in points)

        for voice_index in range(1, self.max_voices):
            pitch_points = []
            pointer_points = []
            for t in grid:
                if not is_active(voice_index, float(t)):
                    continue
                config = self.get_voice_config(voice_index, float(t))
                if has_pitch:
                    # Il pitch e' un fattore di ratio: si disegna in semitoni.
                    factor = config.pitch_factor
                    pitch_points.append([float(t), (
                        float(12.0 * np.log2(factor)) if factor > 0 else 0.0)])
                if has_pointer:
                    # L'offset del pointer si disegna com'e'.
                    pointer_points.append(
                        [float(t), float(config.pointer_offset)])

            if has_pitch and carries_information(pitch_points):
                curves.append(VoiceCurve(
                    dimension='pitch_offset',
                    voice_index=voice_index,
                    envelope=Envelope(pitch_points),
                ))
            if has_pointer and carries_information(pointer_points):
                curves.append(VoiceCurve(
                    dimension='pointer_offset',
                    voice_index=voice_index,
                    envelope=Envelope(pointer_points),
                ))

        spread = self._pointer_range_curve(duration)
        if spread is not None:
            curves.append(spread)

        return curves

    def _pointer_range_curve(self, duration: float) -> Optional[VoiceCurve]:
        """Ampiezza dello spread, esposta dalla pointer strategy stocastica.

        Curva singola e non per-voce (voice_index None): descrive la banda
        entro cui le voci si distribuiscono, non una voce in particolare.
        """
        from pge.envelopes.envelope import Envelope

        if self._pointer_strategy is None:
            return None

        spread = getattr(self._pointer_strategy, 'pointer_range', None)

        if isinstance(spread, Envelope):
            if not any(abs(bp[1]) > 1e-9 for bp in spread.breakpoints):
                return None
            envelope = spread
        elif isinstance(spread, (int, float)) and abs(spread) > 1e-9:
            envelope = Envelope([[0, spread], [duration, spread]])
        else:
            return None

        return VoiceCurve(
            dimension='pointer_range', voice_index=None, envelope=envelope)
