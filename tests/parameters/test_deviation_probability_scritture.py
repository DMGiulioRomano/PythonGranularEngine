# =============================================================================
# tests/parameters/test_deviation_probability_scritture.py
# =============================================================================
"""
Il contratto delle scritture di `deviation_probability` (issue #209, #210).

Otto modi di scrivere la chiave e il gate che ne esce. La tabella sta qui
perche' altrimenti l'unica cosa che la sostiene e' la documentazione: le
cinque scritture "vuote" di #210 non cambiano comportamento — restano quelle
misurate nel corpo di quella issue — e cio' che non cambia non lo protegge
nessun test a meno che non lo si scriva apposta.

    deviation_probability OMESSA          -> NeverGate                (#210)
    deviation_probability:  (cioe' None)  -> jitter implicito         (#210)
    deviation_probability: {}             -> NeverGate                (#210)
    deviation_probability: false          -> NeverGate                (#210)
    {read_direction: null}                -> NeverGate                (#210)
    {read_direction: {punti: [[0, 50]]}}  -> InvalidFieldValueError   (#209)
    {read_direction: ['x']}               -> InvalidFieldValueError   (#209)
    {read_direction: []}                  -> InvalidFieldValueError   (#209)

La riga che vale la pena non spostare e' la seconda: la chiave **scritta e
lasciata vuota** e' l'unica delle cinque a non dare `NeverGate`. E' la
scrittura che piu' assomiglia a "non voglio deviazione" e fa l'opposto —
applica `DEFAULT_PROB`, l'1% di jitter implicito — ma e' una scelta di design
che precede #208, e #210 ha deciso di documentarla, non di cambiarla.

Le ultime tre sono corpi malformati che fino a #209 davano `AlwaysGate`, cioe'
il ribaltamento del 100% dei grani su un verso di lettura dichiarato: da li'
in poi sono un errore di scrittura come ogni altro.

Il gate e' letto su `read_direction` senza `_range` esplicito (la chiave non
ne ha uno), che e' la condizione in cui la tabella di #210 e' stata misurata:
con un `_range` dichiarato le righe `NeverGate` darebbero `AlwaysGate`, che e'
la semantica *range-only* e non ha niente a che vedere con queste scritture.
"""
from dataclasses import fields

import pytest

from pge.core.stream_config import StreamConfig
from pge.parameters.gate_factory import GateFactory
from pge.parameters.parameter_definitions import DEFAULT_PROB
from pge.shared.exceptions import InvalidFieldValueError
from pge.shared.probability_gate import NeverGate, RandomGate

# Il valore che StreamConfig porta quando la chiave e' assente dallo YAML: la
# chiave omessa non e' `None`, e' `False`. Letto dal default reale invece che
# ricopiato — scritto a mano, questo era un secondo `False` che non seguiva il
# primo: cambiando il default in `stream_config.py` la tabella qui sotto
# restava verde continuando a misurare la scrittura sbagliata.
OMESSA = next(
    campo.default for campo in fields(StreamConfig)
    if campo.name == 'deviation_probability'
)


def _gate(deviation_probability):
    return GateFactory.create_gate(
        deviation_probability=deviation_probability,
        param_key='read_direction',
        default_prob=DEFAULT_PROB,
        has_explicit_range=False,
        range_always_active=False,
        duration=1.0,
        time_mode='absolute',
    )


class TestScrittureVuote:
    """Le cinque scritture di #210: nessuna cambia comportamento."""

    @pytest.mark.parametrize("scrittura", [
        OMESSA,
        {},
        False,
        {'read_direction': None},
    ])
    def test_niente_deviazione(self, scrittura):
        """Quattro scritture su cinque: nessuna variazione sul parametro."""
        assert isinstance(_gate(scrittura), NeverGate)

    def test_chiave_vuota_applica_il_jitter_implicito(self):
        """`deviation_probability:` senza valore -> `DEFAULT_PROB`.

        L'unica delle cinque a non dare `NeverGate`, ed e' il motivo per cui
        #210 esiste. Il test la fissa: se un giorno la si volesse rendere
        equivalente alla chiave assente, e' una decisione da prendere, non un
        effetto collaterale da scoprire dopo.
        """
        gate = _gate(None)
        assert isinstance(gate, RandomGate)
        assert gate.get_probability_value(0.0) == pytest.approx(DEFAULT_PROB)


class TestCorpiMalformati:
    """Le tre righe di #209: da `AlwaysGate` silenzioso a errore esplicito."""

    @pytest.mark.parametrize("corpo", [
        {'punti': [[0, 50]]},   # dict senza `points`: KeyError nel builder
        ['x'],                  # lista di non-breakpoint
        [],                     # lista vuota
    ])
    def test_envelope_malformato_alza_errore(self, corpo):
        """Un envelope che non si costruisce e' un errore di scrittura.

        Prima di #209 questi tre corpi tornavano `AlwaysGate` e loggavano:
        il gate piu' lontano da quanto scritto, applicato al 100% dei grani.
        """
        with pytest.raises(InvalidFieldValueError) as exc:
            _gate({'read_direction': corpo})

        assert exc.value.field == 'deviation_probability.read_direction'
        assert exc.value.value == corpo
        assert exc.value.hint
