# tests/parameters/test_parameter_range_unit.py
"""
test_parameter_range_unit.py

`duration_range_unit: relative` (issue #267): la larghezza della banda smette
di essere una quantita' assoluta e diventa una FRAZIONE del valore base, letta
istante per istante — quindi dopo l'envelope della base.

Catena: YAML grain -> ParameterSpec.range_unit_path -> ParameterOrchestrator
-> GranularParser -> Parameter(range_relative=True).

La ragione sta nell'issue: con `grain.duration` che spazia su piu' ordini di
grandezza (1 campione -> 500 ms) una banda assoluta cambia carattere da sola
lungo lo sweep — enorme sui grani corti, trascurabile sui lunghi. Relativa,
il carattere della dispersione resta costante.
"""

import random

import pytest

from pge.envelopes.envelope import Envelope
from pge.parameters.parameter import Parameter
from pge.parameters.parameter_definitions import ParameterBounds
from pge.shared.distribution_strategy import ANCHOR_CENTER, ANCHOR_MIN
from pge.shared.probability_gate import AlwaysGate


N = 400


def _bounds(**kw):
    defaults = dict(
        min_val=0.0, max_val=1000.0,
        min_range=0.0, max_range=1.0,
        default_jitter=0.0, variation_mode='additive',
    )
    defaults.update(kw)
    return ParameterBounds(**defaults)


def _param(value, mod_range, relative, anchor=ANCHOR_CENTER, bounds=None):
    p = Parameter(
        name='grain_duration',
        value=value,
        bounds=bounds if bounds is not None else _bounds(),
        mod_range=mod_range,
        distribution_mode='uniform',
        range_anchor=anchor,
        rng=random.Random(20260910),
        range_relative=relative,
    )
    p.set_probability_gate(AlwaysGate())
    return p


class TestBandaRelativaScalare:

    def test_ancora_center_banda_e_frazione_del_valore(self):
        """base 10, frazione 0.5 -> banda larga 5, cioe' 7.5 .. 12.5."""
        p = _param(10.0, 0.5, relative=True)

        draws = [p.get_value(0.0) for _ in range(N)]

        assert min(draws) >= 7.5 - 1e-9
        assert max(draws) <= 12.5 + 1e-9
        # la banda viene davvero riempita: non e' un range collassato a zero
        assert max(draws) - min(draws) > 4.0

    def test_stessa_frazione_su_base_diversa_da_banda_diversa(self):
        """E' il punto dell'issue: la frazione segue la base."""
        piccolo = _param(1.0, 0.5, relative=True)
        grande = _param(100.0, 0.5, relative=True)

        assert min(piccolo.get_value(0.0) for _ in range(N)) >= 0.75 - 1e-9
        assert max(piccolo.get_value(0.0) for _ in range(N)) <= 1.25 + 1e-9
        assert min(grande.get_value(0.0) for _ in range(N)) >= 75.0 - 1e-9
        assert max(grande.get_value(0.0) for _ in range(N)) <= 125.0 + 1e-9

    def test_assoluto_resta_il_comportamento_storico(self):
        """Senza dichiarare nulla la banda e' larga quanto il numero scritto."""
        p = _param(10.0, 0.5, relative=False)

        draws = [p.get_value(0.0) for _ in range(N)]

        assert min(draws) >= 9.75 - 1e-9
        assert max(draws) <= 10.25 + 1e-9


class TestBandaRelativaNelTempo:

    def test_la_frazione_si_applica_alla_base_di_quell_istante(self):
        """La base e' un envelope: la banda si allarga con lei."""
        base = Envelope([[0.0, 1.0], [10.0, 100.0]])
        p = _param(base, 0.5, relative=True)

        inizio = [p.get_value(0.0) for _ in range(N)]
        fine = [p.get_value(10.0) for _ in range(N)]

        assert max(inizio) <= 1.25 + 1e-9
        assert min(fine) >= 75.0 - 1e-9

    def test_anche_la_frazione_puo_essere_un_envelope(self):
        """Entrambi envelope: la banda e' il prodotto istante per istante."""
        base = Envelope([[0.0, 10.0], [10.0, 10.0]])
        frazione = Envelope([[0.0, 0.0], [10.0, 1.0]])
        p = _param(base, frazione, relative=True)

        assert p.get_value(0.0) == pytest.approx(10.0)
        fine = [p.get_value(10.0) for _ in range(N)]
        assert min(fine) >= 5.0 - 1e-9
        assert max(fine) <= 15.0 + 1e-9


class TestBandaRelativaEAncora:

    def test_ancora_min_sale_dalla_base(self):
        """`min`: banda [base, base * (1 + frazione)]."""
        p = _param(10.0, 1.0, relative=True, anchor=ANCHOR_MIN)

        draws = [p.get_value(0.0) for _ in range(N)]

        assert min(draws) >= 10.0 - 1e-9
        assert max(draws) <= 20.0 + 1e-9


class TestJitterImplicito:

    def test_resta_assoluto_anche_in_modalita_relativa(self):
        """Senza `_range` dichiarato non c'e' nessuna frazione da leggere.

        Stessa regola di `range_anchor`: il jitter implicito non e' una banda
        dichiarata, e' un tremolio attorno al valore.
        """
        p = _param(10.0, None, relative=True, bounds=_bounds(default_jitter=2.0))

        draws = [p.get_value(0.0) for _ in range(N)]

        assert min(draws) >= 9.0 - 1e-9
        assert max(draws) <= 11.0 + 1e-9


class TestBaseConSegno:
    """La LARGHEZZA della banda non ha segno, la base si'.

    `grain_duration` vive sopra lo zero, ma il meccanismo non e' suo: il parser
    accetta `range_unit` su qualunque parametro, e i domini con segno esistono
    gia' (`volume` in dB, da -120 a +12). Li' la frazione va letta sul MODULO
    della base, o la larghezza esce negativa.

    E una larghezza negativa non e' un errore rumoroso: `UniformDistribution`
    con `spread <= 0` restituisce il centro, quindi la variazione sparirebbe
    senza un'eccezione, senza un warning e senza niente nel file da cui
    accorgersene — lo stesso difetto muto che la modalita' relativa chiude
    altrove (`duration_unit` che convertiva la frazione).
    """

    _DB = dict(min_val=-120.0, max_val=12.0)

    def test_su_base_negativa_la_banda_e_larga_quanto_il_modulo(self):
        """-6 dB con frazione 0.5 -> banda larga 3 dB, cioe' -7.5 .. -4.5."""
        p = _param(-6.0, 0.5, relative=True, bounds=_bounds(**self._DB))

        draws = [p.get_value(0.0) for _ in range(N)]

        assert min(draws) >= -7.5 - 1e-9
        assert max(draws) <= -4.5 + 1e-9
        # Il punto: la banda esiste ed e' a cavallo della base. Col segno
        # sbagliato tutti i draw sarebbero esattamente -6.0.
        assert min(draws) < -6.0 < max(draws)

    def test_su_base_negativa_l_ancora_min_sale_comunque(self):
        """`min` parte dalla base e sale: -6 dB con frazione 0.5 -> -6 .. -3.

        Con la larghezza negativa la banda non salirebbe affatto: `min` e'
        l'ancora dove il segno della larghezza si vede meglio, perche' li' la
        banda e' tutta da una parte sola.
        """
        p = _param(-6.0, 0.5, relative=True, anchor=ANCHOR_MIN,
                   bounds=_bounds(**self._DB))

        draws = [p.get_value(0.0) for _ in range(N)]

        assert min(draws) >= -6.0 - 1e-9
        assert max(draws) <= -3.0 + 1e-9
        assert max(draws) > -6.0
