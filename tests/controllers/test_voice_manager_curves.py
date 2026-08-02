# tests/controllers/test_voice_manager_curves.py
"""
Suite TDD per VoiceManager.offset_curves (docs/explanation/parameter-curve.md).

Gli offset per-voce non sono letti da un Parameter: sono il comportamento di
una voice strategy, che esiste solo se lo si campiona. La responsabilita' del
campionamento sta a VoiceManager, che e' l'unico a conoscere la semantica
delle proprie strategy — oggi invece viene frugato dall'esterno
(vm._pitch_strategy, vm._pointer_strategy) da envelope_extractor.

Qui si testa solo l'interfaccia pubblica: nessun test tocca i privati.
"""
import pytest

from pge.controllers.voice_manager import VoiceManager
from pge.envelopes.envelope import Envelope
from pge.strategies.voice_pitch_strategy import StepPitchStrategy
from pge.strategies.voice_pointer_strategy import (
    LinearPointerStrategy,
    StochasticPointerStrategy,
)


class TestVoiceZeroIsReference:

    def test_voice_zero_produces_no_curve(self):
        # Voce 0 e' il riferimento: offset sempre nullo, niente da disegnare.
        vm = VoiceManager(max_voices=3, pitch_strategy=StepPitchStrategy(step=3.0))
        indexes = {vc.voice_index for vc in vm.offset_curves(duration=10.0)}
        assert 0 not in indexes

    def test_one_curve_per_voice_above_zero(self):
        vm = VoiceManager(max_voices=3, pitch_strategy=StepPitchStrategy(step=3.0))
        pitch = [vc for vc in vm.offset_curves(duration=10.0)
                 if vc.dimension == 'pitch_offset']
        assert {vc.voice_index for vc in pitch} == {1, 2}

    def test_voice_zero_is_skipped_by_rule_not_by_luck(self):
        """Che la voce 0 non compaia lo decide il campionamento, non il caso.

        Le due asserzioni sopra passerebbero anche partendo da zero: le
        strategy di oggi danno alla voce 0 un offset nullo, e la curva verrebbe
        scartata perche' identicamente zero. Sono due regole diverse, e questa
        le separa — una strategy che desse alla voce 0 un offset reale non deve
        far comparire una traccia '__v0', perche' quella voce e' il
        RIFERIMENTO: il suo offset rispetto a se stessa e' zero per
        definizione, qualunque cosa risponda la strategy.
        """
        class OffsetsEveryVoice:
            def get_pointer_offset(self, voice_index, num_voices, time):
                return 0.5 + voice_index

        vm = VoiceManager(max_voices=3,
                          pointer_strategy=OffsetsEveryVoice())
        indexes = {vc.voice_index for vc in vm.offset_curves(duration=10.0)
                   if vc.dimension == 'pointer_offset'}
        assert indexes == {1, 2}


class TestPointerDimension:

    def _vm(self, step=0.1, max_voices=3):
        return VoiceManager(max_voices=max_voices,
                            pointer_strategy=LinearPointerStrategy(step=step))

    def test_pointer_offsets_are_produced(self):
        curves = self._vm().offset_curves(duration=10.0)
        pointer = [vc for vc in curves if vc.dimension == 'pointer_offset']
        assert {vc.voice_index for vc in pointer} == {1, 2}

    def test_pointer_offset_is_raw_not_converted(self):
        # A differenza del pitch (fattore di ratio -> semitoni), l'offset del
        # pointer si disegna nell'unita' in cui e' espresso.
        curves = self._vm(step=0.1).offset_curves(duration=10.0)
        voice2 = next(vc for vc in curves
                      if vc.dimension == 'pointer_offset' and vc.voice_index == 2)
        assert voice2.envelope.evaluate(0.0) == pytest.approx(0.2)

    def test_no_pointer_curves_without_pointer_strategy(self):
        vm = VoiceManager(max_voices=3, pitch_strategy=StepPitchStrategy(step=3.0))
        curves = vm.offset_curves(duration=10.0)
        assert not any(vc.dimension == 'pointer_offset' for vc in curves)


class TestActiveVoicesWindow:
    """num_voices time-varying: una voce esiste solo nella finestra in cui e'
    accesa, e la sua curva va troncata li'. Il predicato e' iniettato: la
    logica di num_voices non appartiene a VoiceManager."""

    def _vm(self):
        return VoiceManager(max_voices=3,
                            pitch_strategy=StepPitchStrategy(step=3.0))

    def test_curve_truncated_to_active_window(self):
        # Voce 2 attiva solo nella prima meta': i breakpoint si fermano li'.
        curves = self._vm().offset_curves(
            duration=10.0,
            active_voices=lambda t: 3 if t < 5.0 else 2,
        )
        voice2 = next(vc for vc in curves if vc.voice_index == 2)
        assert max(t for t, _ in voice2.envelope.breakpoints) < 5.0

    def test_voice_active_throughout_is_not_truncated(self):
        curves = self._vm().offset_curves(
            duration=10.0,
            active_voices=lambda t: 3 if t < 5.0 else 2,
        )
        voice1 = next(vc for vc in curves if vc.voice_index == 1)
        assert max(t for t, _ in voice1.envelope.breakpoints) == 10.0


class TestPointerRangeSpread:
    """Lo spread della pointer strategy stocastica e' una curva singola, non
    per-voce: voice_index None."""

    def _vm(self, pointer_range):
        return VoiceManager(
            max_voices=3,
            pointer_strategy=StochasticPointerStrategy(
                pointer_range=pointer_range, stream_id='s1', seed=1),
        )

    def test_scalar_spread_is_a_single_curve(self):
        curves = self._vm(0.3).offset_curves(duration=10.0)
        spread = [vc for vc in curves if vc.dimension == 'pointer_range']
        assert len(spread) == 1
        assert spread[0].voice_index is None

    def test_envelope_spread_keeps_its_curve(self):
        envelope = Envelope([[0, 0.0], [10, 0.5]])
        curves = self._vm(envelope).offset_curves(duration=10.0)
        spread = next(vc for vc in curves if vc.dimension == 'pointer_range')
        assert spread.envelope is envelope

    def test_zero_spread_is_dropped(self):
        curves = self._vm(0.0).offset_curves(duration=10.0)
        assert not any(vc.dimension == 'pointer_range' for vc in curves)


class TestSamplingGrid:
    """Il 33 storico (issue #90) era una costante muta: qui e' un argomento."""

    def _vm(self):
        return VoiceManager(
            max_voices=2,
            pitch_strategy=StepPitchStrategy(
                step=Envelope([[0, 1.0], [10, 12.0]])),
        )

    def test_default_grid_is_the_historic_density(self):
        curve = self._vm().offset_curves(duration=10.0)[0]
        assert len(curve.envelope.breakpoints) == 33

    def test_grid_density_is_configurable(self):
        curve = self._vm().offset_curves(duration=10.0, samples=9)[0]
        assert len(curve.envelope.breakpoints) == 9


class TestZeroCurvesDiscarded:

    def test_identically_zero_curve_is_dropped(self):
        # Uno step nullo non produce nessuno scarto fra le voci: curva piatta
        # a zero, nessuna informazione da mostrare.
        vm = VoiceManager(max_voices=3,
                          pitch_strategy=StepPitchStrategy(step=0.0))
        assert vm.offset_curves(duration=10.0) == []
