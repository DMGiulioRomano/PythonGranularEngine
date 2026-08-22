# tests/parameters/test_parameter_curve.py
"""
Suite TDD per ParameterCurve (docs/explanation/parameter-curve.md).

ParameterCurve e' la risposta di un parametro alla domanda "come varii nel
tempo?": un value object con `kind` in varying/constant/absent piu' il payload.
La classificazione avviene una volta sola, dentro chi possiede il dato, invece
di essere ripetuta da ogni consumatore che legge i privati di Parameter.

Qui si testa il modello puro: niente Stream, niente matplotlib, niente mock.
"""
from decimal import Decimal
from fractions import Fraction

import numpy as np
import pytest

from pge.envelopes.envelope import Envelope
from pge.parameters.parameter_curve import ParameterCurve


class TestClassifyEnvelope:

    def test_envelope_with_different_values_is_varying(self):
        envelope = Envelope([[0, 0.0], [10, 1.0]])
        curve = ParameterCurve.classify(envelope)
        assert curve.kind == 'varying'

    def test_varying_keeps_the_same_envelope_object(self):
        # Identita', non copia: i consumatori attuali asseriscono `is` sulla
        # curva restituita (es. il gate envelope in test_score_visualizer).
        envelope = Envelope([[0, 0.0], [10, 1.0]])
        assert ParameterCurve.classify(envelope).envelope is envelope

    def test_flat_envelope_is_constant(self):
        # La costante travestita: un Envelope con tutti i breakpoint uguali
        # non e' una curva, e' un valore fisso scritto in forma di curva.
        curve = ParameterCurve.classify(Envelope([[0, 50.0], [10, 50.0]]))
        assert curve.kind == 'constant'

    def test_flat_envelope_carries_its_value(self):
        curve = ParameterCurve.classify(Envelope([[0, 50.0], [10, 50.0]]))
        assert curve.value == 50.0


class TestClassifyScalarAndAbsent:

    def test_float_is_constant(self):
        curve = ParameterCurve.classify(-6.0)
        assert (curve.kind, curve.value) == ('constant', -6.0)

    def test_int_is_constant(self):
        curve = ParameterCurve.classify(20)
        assert (curve.kind, curve.value) == ('constant', 20.0)

    def test_none_is_absent(self):
        # mod_range None = nessun range dichiarato: la faccia non esiste.
        assert ParameterCurve.classify(None).kind == 'absent'

    def test_absent_carries_no_payload(self):
        curve = ParameterCurve.classify(None)
        assert curve.envelope is None and curve.value is None

    @pytest.mark.parametrize('raw', ['hanning', (0.0, 1.0), [0, 1], object()])
    def test_a_value_outside_the_domain_is_rejected(self, raw):
        """Envelope, numero o None: fuori da questi tre non c'e' una curva da
        classificare. Non tutti i campi di uno Stream ne hanno una — grain
        envelope e' il nome di una finestra — e chiederla e' un errore del
        chiamante, non un dato da interpretare."""
        with pytest.raises(TypeError):
            ParameterCurve.classify(raw)

    def test_the_rejection_says_what_it_got(self):
        """Il messaggio nomina tipo e valore: un `float()` nudo direbbe solo
        'could not convert string to float', lasciando a indovinare da dove
        arrivi."""
        with pytest.raises(TypeError, match="str.*hanning"):
            ParameterCurve.classify('hanning')


class TestTheNumericDomain:
    """"Numero" e' cio' che `float()` sa leggere, non cio' che eredita da
    `float` (issue #192).

    Il filtro era `isinstance(raw, (int, float))`, e la linea che tracciava non
    era il dominio del value object: era un dettaglio di ereditarieta' di
    numpy. `np.float64` passava perche' e' sottoclasse di `float`, `np.float32`
    no — pur essendo lo stesso numero scritto con meno bit. Prima del refactor
    la riga era `float(raw)`, e li leggeva tutti.
    """

    @pytest.mark.parametrize('raw, expected', [
        (np.float32(1.5), 1.5),
        (np.float64(1.5), 1.5),
        (np.int64(3), 3.0),
        (np.int32(3), 3.0),
        (Decimal('1.5'), 1.5),
        (Fraction(3, 2), 1.5),
    ])
    def test_any_numeric_type_is_a_constant(self, raw, expected):
        curve = ParameterCurve.classify(raw)
        assert (curve.kind, curve.value) == ('constant', expected)

    def test_the_payload_is_a_python_float(self):
        """Il value object normalizza: chi legge `value` non deve sapere da
        quale libreria arrivava il numero."""
        assert type(ParameterCurve.classify(np.float32(1.5)).value) is float

    def test_float32_and_float64_are_the_same_curve(self):
        """La regressione in una riga: due scritture dello stesso numero
        davano due esiti diversi."""
        assert (ParameterCurve.classify(np.float32(2.0))
                == ParameterCurve.classify(np.float64(2.0)))

    def test_a_string_is_still_outside(self):
        """L'allargamento non e' una resa: il caso per cui il controllo esiste
        — `grain_envelope`, che e' il nome di una finestra — resta fuori,
        perche' una stringa non sa diventare un float."""
        with pytest.raises(TypeError):
            ParameterCurve.classify('hanning')

    def test_something_that_only_looks_like_a_number_is_rejected_the_same_way(self):
        """Un array a piu' elementi espone `__float__` e poi fallisce la
        conversione. Il rifiuto deve restare quello del dominio — stesso tipo,
        stesso messaggio parlante — o il chiamante tollerante si troverebbe a
        catturare la formulazione di numpy senza sapere di che parametro
        parla."""
        with pytest.raises(TypeError, match="ndarray"):
            ParameterCurve.classify(np.array([1.0, 2.0]))


class TestFromGate:
    """Il deviation_probability e' un ProbabilityGate. Oggi l'estrattore fa isinstance sul
    tipo di gate solo per distinguere curva da costante: la stessa domanda di
    classify, posta a un tipo invece che a un valore."""

    def test_envelope_gate_is_varying(self):
        from pge.shared.probability_gate import EnvelopeGate
        envelope = Envelope([[0, 0.0], [10, 100.0]])
        curve = ParameterCurve.from_gate(EnvelopeGate(envelope))
        assert curve.kind == 'varying'
        assert curve.envelope is envelope

    def test_random_gate_is_constant_with_its_probability(self):
        from pge.shared.probability_gate import RandomGate
        curve = ParameterCurve.from_gate(RandomGate(50.0))
        assert (curve.kind, curve.value) == ('constant', 50.0)


class TestGateKindsWithoutCurve:
    """Never e Always non hanno una curva da mostrare: Never non applica mai
    la variazione, Always la applica sempre. Comportamento storico da non
    perdere — l'estrattore oggi non emette nulla per entrambi, nemmeno con
    show_static."""

    def test_never_gate_is_absent(self):
        from pge.shared.probability_gate import NeverGate
        assert ParameterCurve.from_gate(NeverGate()).kind == 'absent'

    def test_always_gate_is_absent(self):
        from pge.shared.probability_gate import AlwaysGate
        assert ParameterCurve.from_gate(AlwaysGate()).kind == 'absent'

    def test_flat_envelope_gate_is_constant(self):
        # Un deviation_probability scritto come envelope piatto e' una probabilita' fissa:
        # stessa regola del valore base, applicata una volta sola.
        from pge.shared.probability_gate import EnvelopeGate
        curve = ParameterCurve.from_gate(
            EnvelopeGate(Envelope([[0, 40.0], [10, 40.0]])))
        assert (curve.kind, curve.value) == ('constant', 40.0)


class TestCurveInvariants:

    def test_single_breakpoint_envelope_is_constant(self):
        curve = ParameterCurve.classify(Envelope([[0, 7.0]]))
        assert (curve.kind, curve.value) == ('constant', 7.0)

    def test_classification_ignores_the_time_axis(self):
        # La classificazione non dipende dalla durata: e' per questo che
        # ParameterCurve non ha bisogno di conoscere lo Stream.
        short = ParameterCurve.classify(Envelope([[0, 3.0], [1, 3.0]]))
        long = ParameterCurve.classify(Envelope([[0, 3.0], [600, 3.0]]))
        assert short == long

    def test_is_immutable(self):
        import dataclasses
        import pytest
        curve = ParameterCurve.classify(5.0)
        with pytest.raises(dataclasses.FrozenInstanceError):
            curve.kind = 'varying'


class TestParameterFaces:
    """Le tre facce di un Parameter esposte come ParameterCurve: valore base,
    deviazione per-grano, probabilita' di deviation_probability. Oggi i consumatori le
    raggiungono via _value / _mod_range / _probability_gate."""

    def _param(self, value, mod_range=None):
        from pge.parameters.parameter import Parameter
        from pge.parameters.parameter_definitions import GRANULAR_PARAMETERS
        return Parameter('volume', value, GRANULAR_PARAMETERS['volume'],
                         mod_range=mod_range)

    def test_value_curve_of_envelope(self):
        envelope = Envelope([[0, -12.0], [10, 0.0]])
        assert self._param(envelope).value_curve.envelope is envelope

    def test_value_curve_of_scalar(self):
        curve = self._param(-6.0).value_curve
        assert (curve.kind, curve.value) == ('constant', -6.0)

    def test_range_curve_absent_without_declared_range(self):
        assert self._param(-6.0).range_curve.kind == 'absent'

    def test_range_curve_of_declared_range(self):
        curve = self._param(-6.0, mod_range=3.0).range_curve
        assert (curve.kind, curve.value) == ('constant', 3.0)

    def test_probability_curve_absent_by_default(self):
        # Un Parameter nasce con NeverGate finche' l'orchestrator non inietta
        # il gate vero.
        assert self._param(-6.0).probability_curve.kind == 'absent'

    def test_probability_curve_after_gate_injection(self):
        from pge.shared.probability_gate import RandomGate
        param = self._param(-6.0)
        param.set_probability_gate(RandomGate(80.0))
        assert param.probability_curve.value == 80.0
