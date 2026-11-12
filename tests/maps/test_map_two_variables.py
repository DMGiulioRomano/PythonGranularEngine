"""
Le mappe a due variabili (issue #313, mappe caotiche 5/7): la seconda si
legge come `m1.y`.

    maps:
      m1: {type: henon, r: 1.4}
    grain:
      duration: (0.05 + 0.02*m1)
    pan: (60*m1.y)

Hénon: `x' = 1 - r*x*x + y`, `y' = 0.3*x`. Lo stato e' una coppia, e i due
aggiornamenti usano la coppia di prima.
"""
import pytest

from pge.expressions.expression import compile_expression
from pge.maps.map_set import MapSet
from pge.shared.exceptions import ExpressionError, MapConfigError


def _henon(x, y, r):
    return 1 - r * x * x + y, 0.3 * x


def _mappe(**chiavi):
    base = {'type': 'henon', 'r': 1.4}
    base.update(chiavi)
    return MapSet.from_yaml({'m1': base, 'm2': {'type': 'logistic', 'r': 3.5}},
                            stream_id='s1')


class TestLaSecondaVariabile:

    def test_e_un_nome_che_un_espressione_puo_leggere(self):
        assert _mappe().variables == ('m1', 'm1.y', 'm2', 't')

    def test_si_legge_dall_ambiente(self):
        mappe = _mappe(transient=0)
        mappe.advance(0, 0.0)
        ambiente = mappe.environment(['m1', 'm1.y'], 0.0)
        assert ambiente == pytest.approx(
            dict(zip(['m1', 'm1.y'], _henon(0.1, 0.1, 1.4))))

    def test_in_un_espressione(self):
        mappe = _mappe(transient=0)
        mappe.advance(0, 0.0)
        compilata = compile_expression('(m1 + 10*m1.y)', mappe.variables)
        assert compilata.names == ('m1', 'm1.y')
        assert compilata(mappe.environment(compilata.names, 0.0)) == \
            pytest.approx(1.086 + 0.3)

    def test_y_e_l_x_di_un_passo_prima(self):
        mappe = _mappe(transient=0)
        precedente = 0.1
        for n in range(50):
            mappe.advance(0, n * 0.1)
            a = mappe.environment(['m1', 'm1.y'], n * 0.1)
            assert a['m1.y'] == pytest.approx(0.3 * precedente)
            precedente = a['m1']

    def test_i_due_aggiornamenti_usano_la_coppia_di_prima(self):
        mappe = _mappe(transient=0)
        x, y = 0.1, 0.1
        for n in range(20):
            x, y = _henon(x, y, 1.4)
            mappe.advance(0, n * 0.1)
            a = mappe.environment(['m1', 'm1.y'], n * 0.1)
            assert (a['m1'], a['m1.y']) == pytest.approx((x, y))

    def test_su_una_mappa_a_una_variabile_e_un_errore(self):
        mappe = _mappe()
        with pytest.raises(ExpressionError) as exc:
            compile_expression('(m2.y)', mappe.variables,
                               field='grain.duration')
        assert 'm2.y' in exc.value.reason
        assert 'm1.y' in exc.value.hint


class TestLoStatoIniziale:

    def test_y0_e_quello_del_tipo(self):
        mappe = _mappe(transient=0)
        mappe.advance(0, 0.0)
        assert mappe.value('m1', 0.0) == pytest.approx(1 - 1.4 * 0.01 + 0.1)

    def test_y0_si_sovrascrive(self):
        mappe = _mappe(transient=0, x0=0.2, y0=-0.05)
        mappe.advance(0, 0.0)
        assert mappe.environment(['m1', 'm1.y'], 0.0) == pytest.approx(
            dict(zip(['m1', 'm1.y'], _henon(0.2, -0.05, 1.4))))

    def test_y0_su_una_mappa_a_una_variabile_e_un_errore(self):
        with pytest.raises(MapConfigError) as exc:
            MapSet.from_yaml({'m1': {'type': 'logistic', 'r': 3.5, 'y0': 0.1}})
        assert exc.value.field == 'maps.m1.y0'

    def test_y0_e_un_numero_finito(self):
        with pytest.raises(MapConfigError) as exc:
            _mappe(y0='boh')
        assert exc.value.field == 'maps.m1.y0'

    def test_il_transitorio_porta_sull_attrattore(self):
        """Dopo il transitorio lo stato e' quello di 300 passi a mano."""
        x, y = 0.1, 0.1
        for _ in range(300):
            x, y = _henon(x, y, 1.4)
        mappe = _mappe()
        assert mappe.environment(['m1', 'm1.y'], 0.0) == pytest.approx(
            {'m1': x, 'm1.y': y})


class TestITreModi:

    def test_clock_grain_uno_stato_per_voce(self):
        mappe = _mappe(transient=0)
        for n in range(5):
            mappe.advance(0, n * 0.1)
        mappe.advance(1, 0.0)
        x, y = _henon(0.1, 0.1, 1.4)
        assert mappe.environment(['m1', 'm1.y'], 0.0) == pytest.approx(
            {'m1': x, 'm1.y': y})
        mappe.select(0)
        x, y = 0.1, 0.1
        for _ in range(5):
            x, y = _henon(x, y, 1.4)
        assert mappe.environment(['m1', 'm1.y'], 0.4) == pytest.approx(
            {'m1': x, 'm1.y': y})

    def test_clock_a_orologio(self):
        """Il passo k cade a k/5 s; fra due passi la coppia resta ferma."""
        mappe = _mappe(clock=5, transient=0)
        x, y = 0.1, 0.1
        attesi = []
        for _ in range(4):
            x, y = _henon(x, y, 1.4)
            attesi.append((x, y))
        for k, (x, y) in enumerate(attesi):
            for t in (k * 0.2, k * 0.2 + 0.19):
                a = mappe.environment(['m1', 'm1.y'], t)
                assert (a['m1'], a['m1.y']) == pytest.approx((x, y))

    def test_il_clock_a_orologio_si_legge_anche_all_indietro(self):
        mappe = _mappe(clock=5, transient=0)
        tardi = mappe.environment(['m1.y'], 3.0)['m1.y']
        presto = mappe.environment(['m1.y'], 0.0)['m1.y']
        assert presto == pytest.approx(0.03)
        assert mappe.environment(['m1.y'], 3.0)['m1.y'] == tardi

    def test_iterate_riparte_dalla_coppia_iniziale(self):
        mappe = MapSet.from_yaml(
            {'m1': {'type': 'henon', 'r': 1.4, 'iterate': 6}})
        x, y = 0.1, 0.1
        for _ in range(6):
            x, y = _henon(x, y, 1.4)
        for t in (0.0, 1.0, 2.5):
            assert mappe.environment(['m1', 'm1.y'], t) == pytest.approx(
                {'m1': x, 'm1.y': y})


class TestLaFuga:

    def test_fuori_dall_intervallo_di_r_riparte_dalla_coppia_iniziale(self):
        """A r = 3 Hénon diverge: la rete lo riporta a (x0, y0)."""
        mappe = _mappe(r=3.0, transient=0)
        ripartito = False
        for n in range(60):
            mappe.advance(0, n * 0.1)
            a = mappe.environment(['m1', 'm1.y'], n * 0.1)
            assert abs(a['m1']) <= 1e3 and abs(a['m1.y']) <= 1e3
            ripartito = ripartito or (a['m1'], a['m1.y']) == (0.1, 0.1)
        assert ripartito
