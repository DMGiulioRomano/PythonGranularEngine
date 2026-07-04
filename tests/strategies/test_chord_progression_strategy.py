# tests/strategies/test_chord_progression_strategy.py
"""
Suite TDD per ChordProgressionPitchStrategy (issue #86).

La strategy rende l'accordo una funzione del tempo: per ogni voce costruisce
un Envelope di offset in semitoni i cui breakpoint sono i target del voicing a
ciascun istante della progressione. get_pitch_factor(i, nv, t, unit) restituisce
unit.to_ratio(voice_env[i].evaluate(t)).

Modello voicing-relativo:
- Voce 0 → sempre 0.0 (riferimento; il moto di radice vive nell'envelope pitch).
- La progressione codifica solo la qualità/voicing.

Transizione (`interp`):
- linear/cubic → glissando (interpolazione continua in semitoni).
- step → blocchi (cambio istantaneo all'onset di ogni accordo).

Voice leading (`voice_leading`):
- positional → voce i = i-esima nota (extend/inversion come ChordPitchStrategy).
- nearest (default) → riabbinamento a minimo movimento con octave-folding e note
  comuni tenute; voce 0 pinned a 0; nearest non fa mai peggio di positional.
"""

import math

import pytest

from parameters.pitch_unit import EdoUnit
from shared.exceptions import InvalidStrategyConfigError


ST = EdoUnit(12)


def _get():
    from strategies.voice_pitch_strategy import (
        ChordProgressionPitchStrategy,
        ChordPitchStrategy,
        VOICE_PITCH_STRATEGIES,
        SEMITONE_LOCKED,
        VoicePitchStrategyFactory,
    )
    return (
        ChordProgressionPitchStrategy,
        ChordPitchStrategy,
        VOICE_PITCH_STRATEGIES,
        SEMITONE_LOCKED,
        VoicePitchStrategyFactory,
    )


def _st(s, vi, nv, t, unit=ST):
    """Fattore di ratio -> offset in semitoni (inversa EDO12). 1.0 -> 0.0."""
    f = s.get_pitch_factor(vi, nv, t, unit)
    return 0.0 if f == 1.0 else round(12.0 * math.log2(f), 9)


def _semis(s, nv, t):
    return [_st(s, i, nv, t) for i in range(nv)]


# =============================================================================
# 1. Modello voicing-relativo — voce 0 invariante
# =============================================================================

class TestVoiceZeroInvariant:

    def test_voice_0_identity_linear(self):
        ChordProg, *_ = _get()
        s = ChordProg(progression=[[0, "maj7"], [8, "min7"]], interp="linear")
        for t in [0.0, 4.0, 8.0, 12.0]:
            assert s.get_pitch_factor(0, 4, t, ST) == 1.0

    def test_voice_0_identity_step(self):
        ChordProg, *_ = _get()
        s = ChordProg(progression=[[0, "maj7"], [8, "min7"]], interp="step")
        for t in [0.0, 4.0, 8.0]:
            assert s.get_pitch_factor(0, 4, t, ST) == 1.0

    def test_voice_0_identity_nearest(self):
        ChordProg, *_ = _get()
        s = ChordProg(
            progression=[[0, "maj7"], [8, "min7"], [16, "dom7"]],
            interp="linear",
            voice_leading="nearest",
        )
        for t in [0.0, 8.0, 16.0]:
            assert s.get_pitch_factor(0, 4, t, ST) == 1.0


# =============================================================================
# 2. positional — offset agli onset + glissando lineare
# =============================================================================

class TestPositional:

    def _make(self, **kw):
        ChordProg, *_ = _get()
        return ChordProg(voice_leading="positional", **kw)

    def test_offsets_at_onsets(self):
        s = self._make(progression=[[0, "maj7"], [8, "min7"]], interp="linear")
        # maj7 = [0,4,7,11]; min7 = [0,3,7,10]
        assert _semis(s, 4, 0.0) == pytest.approx([0, 4, 7, 11])
        assert _semis(s, 4, 8.0) == pytest.approx([0, 3, 7, 10])

    def test_linear_glissando_midpoint(self):
        s = self._make(progression=[[0, "maj7"], [8, "min7"]], interp="linear")
        # a metà (t=4): v1=(4+3)/2, v2=7, v3=(11+10)/2
        assert _semis(s, 4, 4.0) == pytest.approx([0, 3.5, 7, 10.5])

    def test_hold_before_first_and_after_last(self):
        s = self._make(progression=[[4, "maj7"], [8, "min7"]], interp="linear")
        # prima del primo accordo: hold del primo
        assert _semis(s, 4, 0.0) == pytest.approx([0, 4, 7, 11])
        # dopo l'ultimo: hold dell'ultimo
        assert _semis(s, 4, 20.0) == pytest.approx([0, 3, 7, 10])


class TestStepInterp:

    def test_step_holds_until_next_onset(self):
        ChordProg, *_ = _get()
        s = ChordProg(
            progression=[[0, "maj7"], [8, "min7"]],
            interp="step",
            voice_leading="positional",
        )
        # appena prima dell'onset 8 → ancora maj7
        assert _semis(s, 4, 7.999) == pytest.approx([0, 4, 7, 11])
        # all'onset 8 → salto netto a min7
        assert _semis(s, 4, 8.0) == pytest.approx([0, 3, 7, 10])


# =============================================================================
# 3. Equivalenza con accordo statico + extend + inversione
# =============================================================================

class TestStaticEquivalenceAndExtend:

    def test_single_chord_equals_static_chord(self):
        ChordProg, ChordPitch, *_ = _get()
        prog = ChordProg(progression=[[0, "dom7"]], voice_leading="positional")
        static = ChordPitch(chord="dom7")
        for t in [0.0, 5.0, 10.0]:
            for i in range(4):
                assert prog.get_pitch_factor(i, 4, t, ST) == pytest.approx(
                    static.get_pitch_factor(i, 4, t, ST)
                )

    def test_extend_per_chord(self):
        ChordProg, *_ = _get()
        s = ChordProg(progression=[[0, "maj"]], voice_leading="positional")
        # maj=[0,4,7], 5 voci → [0,4,7,12,16]
        assert _semis(s, 5, 0.0) == pytest.approx([0, 4, 7, 12, 16])

    def test_inversion_compact_form(self):
        ChordProg, *_ = _get()
        s = ChordProg(progression=[[0, "dom7", 1]], voice_leading="positional")
        # dom7 inversion1 = [0,3,6,8]
        assert _semis(s, 4, 0.0) == pytest.approx([0, 3, 6, 8])

    def test_inversion_dict_form(self):
        ChordProg, *_ = _get()
        s = ChordProg(
            progression=[[0, {"chord": "dom7", "inversion": 1}]],
            voice_leading="positional",
        )
        assert _semis(s, 4, 0.0) == pytest.approx([0, 3, 6, 8])


# =============================================================================
# 4. nearest voice leading
# =============================================================================

class TestNearestVoiceLeading:

    def _make(self, **kw):
        ChordProg, *_ = _get()
        return ChordProg(voice_leading="nearest", **kw)

    def test_common_tone_held(self):
        # maj7 [0,4,7,11] → min7 [0,3,7,10]: la quinta (7) resta ferma.
        s = self._make(progression=[[0, "maj7"], [8, "min7"]], interp="linear")
        assert _st(s, 2, 4, 0.0) == pytest.approx(7)
        assert _st(s, 2, 4, 8.0) == pytest.approx(7)

    def test_ascending_voicings_equal_positional(self):
        # Per voicing ascendenti, nearest coincide con positional.
        near = self._make(progression=[[0, "maj7"], [8, "min7"]], interp="linear")
        ChordProg, *_ = _get()
        pos = ChordProg(
            progression=[[0, "maj7"], [8, "min7"]],
            interp="linear",
            voice_leading="positional",
        )
        assert _semis(near, 4, 8.0) == pytest.approx(_semis(pos, 4, 8.0))

    def test_total_motion_not_worse_than_positional(self):
        prog = [[0, "maj7"], [8, "min7"], [16, "dom7"], [24, "maj7"]]
        near = self._make(progression=prog, interp="step")
        ChordProg, *_ = _get()
        pos = ChordProg(progression=prog, interp="step", voice_leading="positional")
        # motion totale alle transizioni (escludendo voce 0)
        onsets = [0.0, 8.0, 16.0, 24.0]
        def motion(strat):
            tot = 0.0
            for k in range(1, len(onsets)):
                a = _semis(strat, 4, onsets[k - 1])
                b = _semis(strat, 4, onsets[k])
                tot += sum(abs(b[i] - a[i]) for i in range(1, 4))
            return tot
        assert motion(near) <= motion(pos) + 1e-9

    def test_octave_folding_helper(self):
        # Helper interno: assegna gli slot alle voci con octave-folding,
        # minimizzando il movimento. prev spanning 2 ottave, slot vicini in
        # ottava diversa → folding azzera il movimento.
        ChordProg, *_ = _get()
        assigned = ChordProg._assign_min_motion([13, 24], [1, 12])
        assert assigned == pytest.approx([13, 24])


# =============================================================================
# 5. Validazione
# =============================================================================

class TestValidation:

    def test_unknown_chord_raises(self):
        ChordProg, *_ = _get()
        with pytest.raises(InvalidStrategyConfigError) as ei:
            ChordProg(progression=[[0, "bogus_chord"]])
        assert ei.value.field == "chord"

    def test_invalid_interp_raises(self):
        ChordProg, *_ = _get()
        with pytest.raises(InvalidStrategyConfigError) as ei:
            ChordProg(progression=[[0, "maj"]], interp="bogus")
        assert ei.value.field == "interp"

    def test_invalid_voice_leading_raises(self):
        ChordProg, *_ = _get()
        with pytest.raises(InvalidStrategyConfigError) as ei:
            ChordProg(progression=[[0, "maj"]], voice_leading="bogus")
        assert ei.value.field == "voice_leading"

    def test_empty_progression_raises(self):
        ChordProg, *_ = _get()
        with pytest.raises(InvalidStrategyConfigError) as ei:
            ChordProg(progression=[])
        assert ei.value.field == "progression"

    def test_decreasing_times_raises(self):
        ChordProg, *_ = _get()
        with pytest.raises(InvalidStrategyConfigError) as ei:
            ChordProg(progression=[[8, "maj"], [0, "min"]])
        assert ei.value.field == "progression"

    def test_invalid_inversion_raises(self):
        ChordProg, *_ = _get()
        with pytest.raises(InvalidStrategyConfigError) as ei:
            ChordProg(progression=[[0, "dom7", 99]])
        assert ei.value.field == "inversion"


# =============================================================================
# 6. Registry / factory / SEMITONE_LOCKED
# =============================================================================

class TestRegistry:

    def test_in_registry(self):
        _, _, VOICE_PITCH_STRATEGIES, _, _ = _get()
        assert "chord_progression" in VOICE_PITCH_STRATEGIES

    def test_in_semitone_locked(self):
        _, _, _, SEMITONE_LOCKED, _ = _get()
        assert "chord_progression" in SEMITONE_LOCKED

    def test_factory_creates(self):
        ChordProg, _, _, _, Factory = _get()
        s = Factory.create("chord_progression", progression=[[0, "maj7"], [8, "min7"]])
        assert isinstance(s, ChordProg)

    def test_default_interp_is_linear(self):
        # default linear → glissando: a metà segmento i valori sono interpolati.
        ChordProg, *_ = _get()
        s = ChordProg(progression=[[0, "maj7"], [8, "min7"]], voice_leading="positional")
        assert _st(s, 1, 4, 4.0) == pytest.approx(3.5)

    def test_default_voice_leading_is_nearest(self):
        ChordProg, *_ = _get()
        s = ChordProg(progression=[[0, "maj7"], [8, "min7"]])
        # common tone (7) tenuto → segnale che nearest è attivo di default
        assert _st(s, 2, 4, 8.0) == pytest.approx(7)


# =============================================================================
# 7. time_mode normalized — i tempi 0..1 mappati sulla duration dello stream
# =============================================================================

class TestNormalizedTime:

    def test_normalized_scales_times_by_duration(self):
        ChordProg, *_ = _get()
        # progression in 0..1, duration 8 → t=0→maj7, t=8→min7
        s = ChordProg(
            progression=[[0.0, "maj7"], [1.0, "min7"]],
            interp="linear",
            voice_leading="positional",
            time_mode="normalized",
            duration=8.0,
        )
        assert _semis(s, 4, 0.0) == pytest.approx([0, 4, 7, 11])
        assert _semis(s, 4, 8.0) == pytest.approx([0, 3, 7, 10])
        # glissando: a metà (t=4, cioè norm 0.5) i valori sono interpolati
        assert _semis(s, 4, 4.0) == pytest.approx([0, 3.5, 7, 10.5])

    def test_normalized_multi_chord(self):
        ChordProg, *_ = _get()
        # 0, 0.5, 1.0 con duration 20 → onset a 0, 10, 20
        s = ChordProg(
            progression=[[0.0, "maj7"], [0.5, "min7"], [1.0, "dom7"]],
            interp="step",
            voice_leading="positional",
            time_mode="normalized",
            duration=20.0,
        )
        assert _semis(s, 4, 0.0) == pytest.approx([0, 4, 7, 11])
        assert _semis(s, 4, 10.0) == pytest.approx([0, 3, 7, 10])
        assert _semis(s, 4, 20.0) == pytest.approx([0, 4, 7, 10])

    def test_normalized_requires_duration(self):
        ChordProg, *_ = _get()
        with pytest.raises(InvalidStrategyConfigError) as ei:
            ChordProg(
                progression=[[0.0, "maj7"], [1.0, "min7"]],
                time_mode="normalized",
            )
        assert ei.value.field == "time_mode"

    def test_absolute_is_default_and_unchanged(self):
        ChordProg, *_ = _get()
        # default (absolute): i tempi restano secondi letterali
        s = ChordProg(
            progression=[[0.0, "maj7"], [8.0, "min7"]],
            voice_leading="positional",
        )
        assert _semis(s, 4, 8.0) == pytest.approx([0, 3, 7, 10])
