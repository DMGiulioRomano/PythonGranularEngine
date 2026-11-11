"""
Il modo alla Di Scipio: `iterate` (issue #310, mappe caotiche 2/7).

    maps:
      m2: {type: logistic, r: [[0, 3.0], [12, 4.0]], iterate: 7, x0: 0.1}

`iterate: n` sta al posto di `clock`, e non e' un clock: a ogni lettura si
riparte da `x0` e si fanno n passi con l'`r` di quell'istante. Nessuno stato:
il valore e' l'n-esima iterata della stessa funzione, e a disegnare la curva
e' il movimento di `r` (A. Di Scipio, DAFx99). Con `r` fermo il valore e'
fermo.
"""
from unittest.mock import patch

import pytest

from pge.maps.map_set import MAP_ITERATE_MAX, MapSet
from pge.shared.exceptions import MapConfigError

DURATA = 12.0
R_MOBILE = [[0, 3.0], [12, 4.0]]


def _iterata(n, r, x0):
    x = x0
    for _ in range(n):
        x = r * x * (1 - x)
    return x


def _mappe(**chiavi):
    mappa = {'type': 'logistic', 'r': 3.7, 'iterate': 7, 'x0': 0.1}
    mappa.update(chiavi)
    return MapSet.from_yaml({'m2': mappa}, stream_id='s1',
                            duration=DURATA, time_mode='absolute')


class TestIterate:

    def test_con_r_fermo_il_valore_e_costante(self):
        mappe = _mappe()
        atteso = _iterata(7, 3.7, 0.1)
        for t in (0.0, 0.3, 5.0, 11.99):
            assert mappe.value('m2', t) == atteso

    def test_con_r_che_si_muove_e_una_curva_nel_tempo(self):
        mappe = _mappe(r=R_MOBILE)
        valori = []
        for t in (0.0, 2.0, 6.0, 9.5, 11.0):
            valore = mappe.value('m2', t)
            assert valore == pytest.approx(
                _iterata(7, 3.0 + t / 12.0, 0.1), abs=1e-12)
            valori.append(round(valore, 6))
        assert len(set(valori)) == len(valori)

    def test_n_e_il_numero_di_passi(self):
        for n in (1, 3, 12):
            assert _mappe(iterate=n).value('m2', 0.0) == _iterata(n, 3.7, 0.1)

    def test_x0_di_default_e_quello_del_tipo(self):
        mappe = MapSet.from_yaml(
            {'m2': {'type': 'logistic', 'r': 3.7, 'iterate': 4}})
        assert mappe.value('m2', 0.0) == _iterata(4, 3.7, 0.3)

    def test_non_ha_stato_la_stessa_lettura_due_volte_in_qualunque_ordine(self):
        mappe = _mappe(r=R_MOBILE)
        tempi = [9.0, 1.0, 9.0, 4.4, 1.0]
        prima = [mappe.value('m2', t) for t in tempi]
        dopo = [mappe.value('m2', t) for t in reversed(tempi)]
        assert prima == list(reversed(dopo))
        assert prima[0] == prima[2] and prima[1] == prima[4]

    def test_il_giro_di_una_voce_non_la_muove(self):
        mappe = _mappe(r=R_MOBILE)
        prima = mappe.value('m2', 3.0)
        for voce in (0, 1, 0, 2):
            mappe.advance(voce, 3.0)
        mappe.select(5)
        assert mappe.value('m2', 3.0) == prima

    def test_non_ha_passi_nel_tempo(self):
        assert _mappe().step_times('m2', DURATA) is None


class TestFuga:

    def test_dopo_la_fuga_non_si_itera_oltre(self):
        """Con r = 4.5 da x0 = 0.3 la logistica esce da 0...1 al secondo
        passo e diverge: il valore e' `x0`, non l'iterata di un numero
        scappato."""
        mappe = _mappe(r=4.5, x0=0.3, iterate=MAP_ITERATE_MAX)
        with patch('pge.maps.map_set.log_map_escape_warning') as log:
            assert mappe.value('m2', 0.0) == 0.3
        assert log.call_count == 1
        assert log.call_args.kwargs['map_name'] == 'm2'

    def test_il_log_ha_il_rate_limit(self):
        mappe = _mappe(r=4.5, x0=0.3, iterate=MAP_ITERATE_MAX)
        with patch('pge.maps.map_set.log_map_escape_warning') as log:
            for n in range(100):
                mappe.value('m2', n * 0.01)
        assert log.call_count == 1


class TestErrori:

    @pytest.mark.parametrize('n', [0, -1, 2.5, True, 'sette', None, [7]])
    def test_iterate_e_un_intero_positivo(self, n):
        with pytest.raises(MapConfigError) as exc:
            _mappe(iterate=n)
        assert exc.value.field == 'maps.m2.iterate'
        assert exc.value.stream_id == 's1'

    def test_fino_al_tetto_si_itera(self):
        assert (_mappe(iterate=MAP_ITERATE_MAX).value('m2', 0.0)
                == _iterata(MAP_ITERATE_MAX, 3.7, 0.1))

    @pytest.mark.parametrize('oltre', [1, 1000, 10**9])
    def test_oltre_il_tetto_e_un_errore_al_parse(self, oltre):
        """Il tetto e' quello del banco, 40, che pero' li' taglia in
        silenzio. Non e' un limite di costo soltanto: a r = 4 la logistica
        perde un bit di `x0` a ogni passo, e dopo una cinquantina di passi
        l'iterata non dipende piu' da r ma dagli arrotondamenti. Senza tetto
        `iterate: 1000000` faceva un milione di passi a ogni lettura, cioe'
        a ogni grano, e il render non finiva."""
        with pytest.raises(MapConfigError) as exc:
            _mappe(iterate=MAP_ITERATE_MAX + oltre)
        assert exc.value.field == 'maps.m2.iterate'
        assert str(MAP_ITERATE_MAX) in exc.value.reason
        assert exc.value.stream_id == 's1'

    def test_il_tetto_e_quello_del_banco(self):
        assert MAP_ITERATE_MAX == 40

    @pytest.mark.parametrize('clock', ['grain', 8, [[0, 2], [12, 20]]])
    def test_clock_e_iterate_insieme_sono_un_errore(self, clock):
        with pytest.raises(MapConfigError) as exc:
            _mappe(clock=clock)
        assert exc.value.field == 'maps.m2'
        assert 'clock' in exc.value.reason and 'iterate' in exc.value.reason

    def test_iterate_non_ha_un_transitorio(self):
        """A ogni lettura si riparte da `x0`: non c'e' un transitorio da
        scartare, e scriverlo vuol dire aspettarsi un'altra cosa."""
        with pytest.raises(MapConfigError) as exc:
            _mappe(transient=300)
        assert exc.value.field == 'maps.m2.transient'
        assert 'iterate' in exc.value.reason
