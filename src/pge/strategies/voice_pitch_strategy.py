# src/strategies/voice_pitch_strategy.py
"""
voice_pitch_strategy.py

Strategy pattern per la distribuzione di pitch (altezza) delle voci
nella sintesi granulare multi-voice.

Responsabilità:
- Calcolare il FATTORE DI RATIO di pitch per una voce data al tempo t.
- La geometria vive nell'unità (PitchUnit): le strategy "scalate"
  (step/range/stochastic) emettono una posizione adimensionale e chiedono
  all'unità di materializzarla (`unit.materialize(position, amount)`); quelle
  "assolute" (chord/spectral) emettono un offset in semitoni e usano
  `unit.to_ratio` (valido solo con unità semitones, vedi SEMITONE_LOCKED).
- Voce 0 restituisce sempre 1.0 (riferimento immutato = ratio identità).
- NON gestisce la variazione per-grano (responsabilità di PitchController + mod_range).

Design:
- VoicePitchStrategy (ABC): interfaccia comune
- StepPitchStrategy: voce i = i × step
- RangePitchStrategy: distribuiti linearmente in [0, pitch_range]
- ChordPitchStrategy: offsets da nome accordo, extend all'ottava se num_voices > chord
- StochasticPitchStrategy: offset fisso per voce (stabile entro un run)
- VOICE_PITCH_STRATEGIES: registry globale {nome: classe}
- register_voice_pitch_strategy(): estensibilità dinamica
- VoicePitchStrategyFactory: factory con create() statico

Coerente con: voice_pan_strategy.py, variation_strategy.py
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Dict, List, Type

from pge.shared.exceptions import (
    InvalidStrategyConfigError,
    StrategyNotFoundError,
)
from pge.shared.seeding import voice_rng

from pge.parameters.parameter import resolve_param, StrategyParam


# =============================================================================
# CHORD DEFINITIONS
# =============================================================================

CHORD_INTERVALS: Dict[str, List[int]] = {
    # --- 3 voci ---
    'maj':     [0, 4, 7],
    'min':     [0, 3, 7],
    'dim':     [0, 3, 6],
    'aug':     [0, 4, 8],
    'sus2':    [0, 2, 7],
    'sus4':    [0, 5, 7],
    # --- 4 voci ---
    'dom7':    [0, 4, 7, 10],
    'maj7':    [0, 4, 7, 11],
    'min7':    [0, 3, 7, 10],
    'dim7':    [0, 3, 6,  9],
    'minmaj7': [0, 3, 7, 11],
    # --- 5 voci ---
    'dom9':    [0, 4, 7, 10, 14],
    'maj9':    [0, 4, 7, 11, 14],
    'min9':    [0, 3, 7, 10, 14],
    '9sus4':   [0, 5, 7, 10, 14],
    # --- 6 voci ---
    'dom9s11': [0, 4, 7, 10, 14, 18],
    'maj9s11': [0, 4, 7, 11, 14, 18],
    'min11':   [0, 3, 7, 10, 14, 17],
    # --- 7 voci ---
    'dom13':   [0,  4,  7, 10, 14, 17, 21],
    'min13':   [0,  3,  7, 10, 14, 17, 21],
    'maj13s11':[0,  4,  7, 11, 14, 18, 21],
    'altered': [0,  4,  7, 10, 13, 15, 20],
}


# =============================================================================
# ABSTRACT BASE CLASS
# =============================================================================

class VoicePitchStrategy(ABC):
    """
    Strategy astratta per la distribuzione di pitch delle voci.

    Il valore restituito è un FATTORE DI RATIO rispetto al pitch base
    dello stream, prodotto tramite la PitchUnit attiva. Voce 0 → sempre 1.0.
    """

    @abstractmethod
    def get_pitch_factor(
        self, voice_index: int, num_voices: int, time: float, unit: 'PitchUnit'
    ) -> float:
        """
        Calcola il fattore di ratio per la voce data al tempo dato.

        Args:
            voice_index: indice della voce (0-based). Voce 0 = riferimento.
            num_voices: numero totale di voci attive.
            time: tempo corrente in secondi (onset del grain).
            unit: PitchUnit attiva — possiede la geometria (materialize/to_ratio).

        Returns:
            Fattore di ratio (float) da moltiplicare sul ratio base.
            Voce 0 → sempre 1.0 (identità).
        """
        pass


# =============================================================================
# CONCRETE STRATEGIES
# =============================================================================

class StepPitchStrategy(VoicePitchStrategy):
    """
    Distribuzione per step fisso o dinamico.

    Posizione voce i = i, ampiezza = step(t). L'unità materializza:
    EDO → 0, step, 2·step, … semitoni; ratio → step^i (geometrico).
    Esempio (semitones): step=3, 4 voci → [0, 3, 6, 9] semitoni.
    """

    def __init__(self, step: StrategyParam):
        self.step = step

    def get_pitch_factor(self, voice_index, num_voices, time, unit):
        if voice_index == 0:
            return 1.0
        return unit.materialize(float(voice_index), resolve_param(self.step, time))


class RangePitchStrategy(VoicePitchStrategy):
    """
    Distribuzione nell'intervallo [identità, pitch_range(t)].

    Posizione voce i = i/(num_voices-1) ∈ [0,1], ampiezza = pitch_range(t).
    EDO → equidistante in semitoni [0..range]; ratio → geometrica [1..range].
    Esempio (semitones): pitch_range=12, 4 voci → [0, 4, 8, 12] semitoni.
    Con num_voices=1 → solo identità.
    """

    def __init__(self, pitch_range: StrategyParam):
        self.pitch_range = pitch_range

    def get_pitch_factor(self, voice_index, num_voices, time, unit):
        if voice_index == 0 or num_voices <= 1:
            return 1.0
        position = float(voice_index) / (num_voices - 1)
        return unit.materialize(position, resolve_param(self.pitch_range, time))


class ChordPitchStrategy(VoicePitchStrategy):
    """
    Offsets da nome accordo nominale.

    Gli intervalli sono presi da CHORD_INTERVALS. Se num_voices > len(chord),
    le voci eccedenti continuano il pattern all'ottava superiore (extend).

    Extend policy: voce i → intervals[i % n] + (i // n) * 12
    dove n = len(chord_intervals).

    Esempio: dom7=[0,4,7,10], 6 voci → [0, 4, 7, 10, 12, 16]

    Il parametro `inversion` ruota gli intervalli dell'accordo in modo che
    il grado k diventi la voce più bassa (normalizzata a 0):
      inversion=0 → root position (default)
      inversion=1 → primo rivolto (terza al basso)
      ...

    L'extend policy funziona invariata sugli intervalli invertiti.
    Il parametro `time` è accettato ma ignorato (nessun param time-varying).
    """

    def __init__(self, chord: str, inversion: int = 0):
        if chord not in CHORD_INTERVALS:
            raise InvalidStrategyConfigError(
                strategy_kind="voice_pitch",
                field="chord",
                value=chord,
                hint=f"accordi disponibili: {sorted(CHORD_INTERVALS.keys())}",
            )
        base_intervals = CHORD_INTERVALS[chord]
        n = len(base_intervals)
        if not (0 <= inversion < n):
            raise InvalidStrategyConfigError(
                strategy_kind="voice_pitch",
                field="inversion",
                value=inversion,
                hint=(
                    f"accordo '{chord}' ha {n} note: inversion deve essere "
                    f"in [0, {n - 1}]"
                ),
            )
        self.chord = chord
        self.inversion = inversion
        self._intervals = self._invert(base_intervals, inversion)

    @staticmethod
    def _invert(intervals: List[int], k: int) -> List[int]:
        rotated = intervals[k:] + [x + 12 for x in intervals[:k]]
        base = rotated[0]
        return [x - base for x in rotated]

    def get_pitch_factor(self, voice_index, num_voices, time, unit):
        if voice_index == 0:
            return 1.0
        n = len(self._intervals)
        octave = voice_index // n
        interval_idx = voice_index % n
        semitones = float(self._intervals[interval_idx] + octave * 12)
        return unit.to_ratio(semitones)


class ChordProgressionPitchStrategy(VoicePitchStrategy):
    """
    Progressione armonica: l'accordo è funzione del tempo (envelope di accordi).

    Per ogni voce si costruisce un Envelope di offset in semitoni i cui
    breakpoint sono i target del voicing a ciascun istante della progressione;
    get_pitch_factor(i, nv, t) restituisce unit.to_ratio(voice_env[i].evaluate(t)).
    Riusa integralmente l'interpolazione Envelope (linear/cubic/step).

    Modello voicing-relativo: voce 0 → sempre 0.0 (riferimento; il moto di
    radice vive nell'envelope `pitch` dello stream). La progressione codifica
    solo la qualità/voicing relativo alla voce 0.

    Transizione (`interp`):
      - linear/cubic → glissando (interpolazione continua in semitoni);
      - step → blocchi (cambio istantaneo all'onset di ogni accordo).

    Voice leading (`voice_leading`):
      - positional → voce i = i-esima nota dell'accordo (extend/inversion come
        ChordPitchStrategy);
      - nearest (default) → le voci 1..N-1 sono riabbinate per minimizzare il
        movimento totale in semitoni tra voicing consecutivi, con octave-folding
        e note comuni tenute; voce 0 resta pinned a 0. Non fa mai peggio di
        positional.

    La strategy è SEMITONE_LOCKED: gli offset (anche frazionari dopo interp)
    sono in semitoni, valida solo con unità `semitones`.

    Sintassi progression (lista [tempo, accordo]):
      - [t, "maj7"]                       — accordo nominale
      - [t, "min7", 1]                    — forma compatta [t, chord, inversion]
      - [t, {"chord": "min7", "inversion": 1}]  — forma esplicita

    Time mode: i tempi seguono il `time_mode` dello stream, come gli envelope.
    `absolute` (default) → secondi; `normalized` → 0..1 mappati sulla duration
    (richiede `duration`). Stream inietta time_mode/duration in automatico.

    Gli envelope per-voce sono costruiti lazy alla prima chiamata (num_voices
    noto a runtime) e messi in cache per num_voices.
    """

    _VALID_VOICE_LEADING = frozenset({'positional', 'nearest'})
    # Soglia oltre la quale il riabbinamento brute-force (factorial) diventa
    # costoso: si ripiega su positional (caso non realistico per voicing reali).
    _NEAREST_BRUTE_MAX = 8

    def __init__(self, progression, interp: str = 'linear',
                 voice_leading: str = 'nearest',
                 time_mode: str = 'absolute', duration: float = None):
        from pge.envelopes.envelope_builder import EnvelopeBuilder

        if not isinstance(progression, (list, tuple)) or len(progression) == 0:
            raise InvalidStrategyConfigError(
                strategy_kind="voice_pitch",
                field="progression",
                value=progression,
                hint="progression deve essere una lista non vuota di [tempo, accordo].",
            )
        if interp not in EnvelopeBuilder.VALID_INTERP_TYPES:
            raise InvalidStrategyConfigError(
                strategy_kind="voice_pitch",
                field="interp",
                value=interp,
                hint=f"interp valido: {', '.join(EnvelopeBuilder.VALID_INTERP_TYPES)}.",
            )
        if voice_leading not in self._VALID_VOICE_LEADING:
            raise InvalidStrategyConfigError(
                strategy_kind="voice_pitch",
                field="voice_leading",
                value=voice_leading,
                hint=f"voice_leading valido: {', '.join(sorted(self._VALID_VOICE_LEADING))}.",
            )

        self._times: List[float] = []
        self._chords: List[List[int]] = []  # intervalli (già invertiti) per accordo
        prev_t = None
        for entry in progression:
            t, intervals = self._parse_entry(entry)
            if prev_t is not None and t < prev_t:
                raise InvalidStrategyConfigError(
                    strategy_kind="voice_pitch",
                    field="progression",
                    value=t,
                    hint="i tempi della progressione devono essere non decrescenti.",
                )
            prev_t = t
            self._times.append(float(t))
            self._chords.append(intervals)

        # time_mode normalized: i tempi (0..1) sono mappati sulla duration dello
        # stream, coerentemente con gli envelope (create_scaled_envelope). Lo
        # scaling per duration > 0 preserva l'ordinamento già validato sopra.
        if time_mode == 'normalized':
            if duration is None:
                raise InvalidStrategyConfigError(
                    strategy_kind="voice_pitch",
                    field="time_mode",
                    value=time_mode,
                    hint="time_mode 'normalized' richiede la duration dello stream.",
                )
            self._times = [t * float(duration) for t in self._times]

        self.interp = interp
        self.voice_leading = voice_leading
        self._env_cache: Dict[int, list] = {}

    @staticmethod
    def _parse_entry(entry):
        """Parsa un elemento della progressione → (tempo, intervalli_invertiti)."""
        if not isinstance(entry, (list, tuple)) or len(entry) < 2:
            raise InvalidStrategyConfigError(
                strategy_kind="voice_pitch",
                field="progression",
                value=entry,
                hint="ogni elemento deve essere [tempo, accordo] (o [tempo, accordo, inversion]).",
            )
        t = entry[0]
        spec = entry[1]
        inversion = 0
        if isinstance(spec, dict):
            chord = spec.get('chord')
            inversion = spec.get('inversion', 0)
        else:
            chord = spec
            if len(entry) >= 3:
                inversion = entry[2]

        if chord not in CHORD_INTERVALS:
            raise InvalidStrategyConfigError(
                strategy_kind="voice_pitch",
                field="chord",
                value=chord,
                hint=f"accordi disponibili: {sorted(CHORD_INTERVALS.keys())}",
            )
        base_intervals = CHORD_INTERVALS[chord]
        n = len(base_intervals)
        if not (0 <= inversion < n):
            raise InvalidStrategyConfigError(
                strategy_kind="voice_pitch",
                field="inversion",
                value=inversion,
                hint=(
                    f"accordo '{chord}' ha {n} note: inversion deve essere "
                    f"in [0, {n - 1}]"
                ),
            )
        return t, ChordPitchStrategy._invert(base_intervals, inversion)

    @staticmethod
    def _extend_targets(intervals: List[int], num_voices: int) -> List[float]:
        """Estende il voicing all'ottava superiore (come ChordPitchStrategy)."""
        n = len(intervals)
        return [float(intervals[i % n] + (i // n) * 12) for i in range(num_voices)]

    @classmethod
    def _assign_min_motion(cls, prev_upper, target_slots):
        """
        Riabbina le voci superiori agli slot del nuovo voicing minimizzando il
        movimento totale in semitoni, con octave-folding (ogni slot può essere
        preso nell'ottava più vicina). Brute-force su permutazioni (N piccolo).

        Args:
            prev_upper: offset correnti delle voci 1..N-1 (lista di float).
            target_slots: target positional delle voci 1..N-1 del nuovo accordo.

        Returns:
            Lista di offset assegnati, allineata per indice alle voci superiori.
        """
        import itertools

        m = len(prev_upper)
        if m == 0:
            return []
        if m > cls._NEAREST_BRUTE_MAX:
            # Guardia anti-factorial: ripiega su positional.
            return [float(t) for t in target_slots]

        best_cost = None
        best = None
        for perm in itertools.permutations(range(m)):
            assigned = [0.0] * m
            cost = 0.0
            for i in range(m):
                target = target_slots[perm[i]]
                octave = round((prev_upper[i] - target) / 12.0)
                val = target + 12 * octave
                cost += abs(prev_upper[i] - val)
                assigned[i] = float(val)
            if best_cost is None or cost < best_cost:
                best_cost = cost
                best = assigned
        return best

    def _build_offsets(self, num_voices: int) -> List[List[float]]:
        """Calcola gli offset per accordo e per voce (offsets[k][i])."""
        positional = [self._extend_targets(iv, num_voices) for iv in self._chords]
        if self.voice_leading == 'positional':
            return positional

        # nearest: primo accordo positional; poi riabbinamento a minimo moto.
        offsets = [list(positional[0])]
        for k in range(1, len(positional)):
            prev = offsets[k - 1]
            target = positional[k]
            assigned_upper = self._assign_min_motion(prev[1:], target[1:])
            offsets.append([0.0] + assigned_upper)
        return offsets

    def _build_envelopes(self, num_voices: int) -> list:
        from pge.envelopes.envelope import Envelope

        offsets = self._build_offsets(num_voices)
        envs = []
        for i in range(num_voices):
            pts = [[self._times[k], offsets[k][i]] for k in range(len(self._times))]
            if len(pts) == 1:
                # Accordo singolo → costante: duplica il breakpoint per evitare
                # envelope degenere a un punto solo.
                pts = [[self._times[0], offsets[0][i]],
                       [self._times[0] + 1.0, offsets[0][i]]]
            envs.append(Envelope({'type': self.interp, 'points': pts}))
        return envs

    def get_pitch_factor(self, voice_index, num_voices, time, unit):
        if voice_index == 0:
            return 1.0
        envs = self._env_cache.get(num_voices)
        if envs is None:
            envs = self._build_envelopes(num_voices)
            self._env_cache[num_voices] = envs
        offset = envs[voice_index].evaluate(time)
        return unit.to_ratio(offset)


class StochasticPitchStrategy(VoicePitchStrategy):
    """
    Offset fisso per voce entro un singolo run; la direzione è fissa, la magnitudine
    può variare nel tempo se pitch_range è un Envelope.

    Identità RNG (issue #169): il kwarg `stream_id` è l'*identità* della
    sequenza, non necessariamente l'id dello stream. Stream inietta
    `context.rng_id`, che vale il `rng_group` quando più stream condividono
    la sequenza; il nome del kwarg resta invariato per non rompere i
    factory kwarg documentati.

    Seed (issue #81): se `seed` è None il RNG per-voce usa hash(stream_id+vi) —
    stabile ENTRO un run, NON riproducibile fra processi (hash() randomizzato
    per-processo, PYTHONHASHSEED non fissato). Se `seed` è valorizzato la
    derivazione è hashlib (vedi shared.seeding.voice_rng): l'offset diventa
    riproducibile fra processi diversi.
    _cache[voice_index] memorizza la posizione normalizzata in [-1, 1].
    Fattore = unit.materialize(position, pitch_range(t)): EDO → ± attorno a 0
    in semitoni; ratio → simmetrico geometrico (es. range=2 → [0.5, 2]).
    Voce 0 (e range 0) → sempre 1.0 (identità).
    """

    def __init__(self, pitch_range: StrategyParam, stream_id: str, seed=None):
        self.pitch_range = pitch_range
        self.stream_id = stream_id
        self.seed = seed
        self._cache: Dict[int, float] = {}

    def get_pitch_factor(self, voice_index, num_voices, time, unit):
        resolved = resolve_param(self.pitch_range, time)
        if voice_index == 0 or resolved == 0.0:
            return 1.0
        if voice_index not in self._cache:
            rng = voice_rng(self.seed, self.stream_id, voice_index)
            self._cache[voice_index] = rng.uniform(-1.0, 1.0)
        return unit.materialize(self._cache[voice_index], resolved)


class SpectralPitchStrategy(VoicePitchStrategy):
    """
    Distribuzione voci sui parziali della serie armonica naturale.

    Voce i → parziale (i+1) → round(12 * log2(i+1)) semitoni.
    Voce 0 → fondamentale → 0 semitoni (invariante ABC).

    Serie [0, 12, 19, 24, 28, 31, 34, 36, ...] per le prime 8 voci.

    Args:
        max_partial: numero di parziali pre-calcolati al __init__ (default 16).
                     Voci oltre max_partial sono calcolate on-demand.

    Il parametro `time` è accettato ma ignorato (nessun param time-varying).
    """

    def __init__(self, max_partial: int = 16):
        self.max_partial = max_partial
        self._offsets: List[float] = [
            float(round(12 * math.log2(i + 1))) for i in range(max_partial)
        ]

    def get_pitch_factor(self, voice_index, num_voices, time, unit):
        if voice_index == 0:
            return 1.0
        while voice_index >= len(self._offsets):
            i = len(self._offsets)
            self._offsets.append(float(round(12 * math.log2(i + 1))))
        return unit.to_ratio(self._offsets[voice_index])


# =============================================================================
# REGISTRY
# =============================================================================

VOICE_PITCH_STRATEGIES: Dict[str, Type[VoicePitchStrategy]] = {
    'step':              StepPitchStrategy,
    'range':             RangePitchStrategy,
    'chord':             ChordPitchStrategy,
    'chord_progression': ChordProgressionPitchStrategy,
    'stochastic':        StochasticPitchStrategy,
    'spectral':          SpectralPitchStrategy,
}

# Strategie i cui offset sono intrinsecamente in semitoni (interi da
# CHORD_INTERVALS / 12*log2): in v1 accettano solo l'unità `semitones`.
# Singola fonte di verità per la validazione in Stream._init_voice_manager.
SEMITONE_LOCKED = frozenset({'chord', 'chord_progression', 'spectral'})


def register_voice_pitch_strategy(name: str, cls: Type[VoicePitchStrategy]) -> None:
    """
    Registra dinamicamente una nuova VoicePitchStrategy.

    Args:
        name: chiave stringa per il registry
        cls: classe che implementa VoicePitchStrategy
    """
    VOICE_PITCH_STRATEGIES[name] = cls


# =============================================================================
# FACTORY
# =============================================================================

class VoicePitchStrategyFactory:
    """
    Factory per la creazione di VoicePitchStrategy da nome stringa.

    Esempio:
        s = VoicePitchStrategyFactory.create('chord', chord='dom7')
        s = VoicePitchStrategyFactory.create('step', step=3.0)
    """

    @staticmethod
    def create(name: str, **kwargs) -> VoicePitchStrategy:
        """
        Crea una VoicePitchStrategy dal nome registrato.

        Args:
            name: nome della strategy nel registry
            **kwargs: parametri passati al costruttore della strategy

        Returns:
            Istanza di VoicePitchStrategy

        Raises:
            KeyError: se il nome non è nel registry
        """
        if name not in VOICE_PITCH_STRATEGIES:
            raise StrategyNotFoundError(
                strategy_kind="voice_pitch",
                name=name,
                available=list(VOICE_PITCH_STRATEGIES.keys()),
            )
        return VOICE_PITCH_STRATEGIES[name](**kwargs)
