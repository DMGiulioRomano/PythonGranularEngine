"""
La mappa logistica (issue #308, mappe caotiche 1/7): il catalogo e i cicli
noti.

I numeri sono quelli del plan
(docs/plans/done/2026-11-10-001-feat-mappe-caotiche-plan.md, «Numeri di
riferimento per i test»): al crescere di `r` la mappa va
da un valore solo a cicli di 2, 4 valori, e dentro il caos ha una finestra di
periodo 3.
"""
import pytest

from pge.maps.catalog import MAP_KINDS, MAP_TYPES
from pge.maps.map_set import MapSet


def _valori(r, quanti=24, **chiavi):
    """I valori che la voce 0 legge, un passo per grano."""
    mappe = MapSet.from_yaml({'m1': {'type': 'logistic', 'r': r, **chiavi}})
    letti = []
    for n in range(quanti):
        mappe.advance(0, n * 0.1)
        letti.append(mappe.value('m1', n * 0.1))
    return letti


def _ciclo(valori, cifre=3):
    """L'insieme dei valori visitati, arrotondati."""
    return sorted({round(v, cifre) for v in valori})


class TestCatalogo:

    def test_la_logistica_e_la_prima_del_catalogo(self):
        """Nella #308 era l'unica; le altre cinque sono arrivate con la
        #313 (tests/maps/test_catalog.py)."""
        assert MAP_TYPES[0] == 'logistic'
        assert set(MAP_KINDS) == set(MAP_TYPES)

    def test_il_passo_e_r_x_uno_meno_x(self):
        logistica = MAP_KINDS['logistic']
        assert logistica.step(0.3, 3.5) == pytest.approx(3.5 * 0.3 * 0.7)

    def test_lo_stato_iniziale_e_l_intervallo_sono_dati_del_tipo(self):
        """Chi scrive un'espressione deve conoscere l'intervallo di `m1`:
        `minimo + (massimo - minimo) * m1` vale per una mappa che vive in
        0...1."""
        logistica = MAP_KINDS['logistic']
        assert logistica.x0 == 0.3
        assert logistica.value_range == (0.0, 1.0)
        assert logistica.r_range == (2.5, 4.0)


class TestCicli:

    def test_r_2_8_un_valore(self):
        assert _ciclo(_valori(2.8)) == [0.643]

    def test_r_3_2_due_valori(self):
        assert _ciclo(_valori(3.2)) == [0.513, 0.799]

    def test_r_3_5_quattro_valori(self):
        assert _ciclo(_valori(3.5)) == [0.383, 0.501, 0.827, 0.875]

    def test_r_3_5_nell_ordine_del_plan(self):
        """0.827, 0.501, 0.875, 0.383, a meno di rotazione."""
        valori = [round(v, 3) for v in _valori(3.5, quanti=8)]
        ciclo = [0.827, 0.501, 0.875, 0.383]
        rotazioni = [ciclo[k:] + ciclo[:k] for k in range(4)]
        assert valori[:4] in rotazioni
        assert valori[4:] == valori[:4]

    def test_r_3_83_tre_valori(self):
        """La finestra di periodo 3 dentro il caos."""
        assert len(_ciclo(_valori(3.83, quanti=30))) == 3

    def test_r_3_9_il_caos_resta_nell_intervallo_dichiarato(self):
        valori = _valori(3.9, quanti=500)
        basso, alto = MAP_KINDS['logistic'].value_range
        assert all(basso <= v <= alto for v in valori)
        assert len(_ciclo(valori)) > 100
