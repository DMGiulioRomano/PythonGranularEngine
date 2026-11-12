"""
Il catalogo delle mappe (issue #313, mappe caotiche 5/7): cinque tipi oltre
la logistica, ognuno col suo passo, il suo `x0` e l'intervallo in cui vive.

| type     | passo                           | r           | m1          |
|----------|---------------------------------|-------------|-------------|
| logistic | r*x*(1-x)                       | 2.5 - 4     | 0 ... 1     |
| tent     | r/2*min(x, 1-x)                 | 2.5 - 3.999 | 0 ... 1     |
| sine     | sin(r*x)                        | 0 - 4       | -1 ... 1    |
| cubic    | r*x*(1-x*x)                     | 1.5 - 3     | -1.2 ... 1.2|
| henon    | 1 - r*x*x + y,  y: 0.3*x        | 0.8 - 1.4   | -1.3 ... 1.4|
| circle   | frac(x + r - 0.3*sin(2*pi*x))   | 0 - 1       | 0 ... 1     |

I valori attesi sono calcolati qui, dalla formula scritta a mano: non dal
catalogo. `sine` e `circle` passano da `sin`, che fra macchine diverse puo'
differire all'ultimo bit: i loro confronti hanno una tolleranza, e nessuno
confronta sequenze lunghe bit per bit.
"""
import ast
import inspect
import math

import pytest

from pge.maps import catalog
from pge.maps.catalog import MAP_KINDS, MAP_TYPES
from pge.maps.map_set import MapSet

TIPI = ('logistic', 'tent', 'sine', 'cubic', 'henon', 'circle')

#: tipo -> (x0, intervallo di r, intervallo di m1)
DICHIARATO = {
    'logistic': (0.3, (2.5, 4.0), (0.0, 1.0)),
    'tent': (0.3, (2.5, 3.999), (0.0, 1.0)),
    'sine': (0.1, (0.0, 4.0), (-1.0, 1.0)),
    'cubic': (0.3, (1.5, 3.0), (-1.2, 1.2)),
    'henon': (0.1, (0.8, 1.4), (-1.3, 1.4)),
    'circle': (0.2, (0.0, 1.0), (0.0, 1.0)),
}


def _frac(v):
    return v - math.floor(v)


#: tipo -> il passo, scritto a mano: (x, y, r) -> (x', y')
A_MANO = {
    'logistic': lambda x, y, r: (r * x * (1 - x), y),
    'tent': lambda x, y, r: (r / 2 * min(x, 1 - x), y),
    'sine': lambda x, y, r: (math.sin(r * x), y),
    'cubic': lambda x, y, r: (r * x * (1 - x * x), y),
    'henon': lambda x, y, r: (1 - r * x * x + y, 0.3 * x),
    'circle': lambda x, y, r: (
        _frac(x + r - 0.3 * math.sin(2 * math.pi * x)), y),
}


def _valori(tipo, r, quanti, **chiavi):
    """I valori che la voce 0 legge, un passo per grano."""
    mappe = MapSet.from_yaml({'m1': {'type': tipo, 'r': r, **chiavi}})
    letti = []
    for n in range(quanti):
        mappe.advance(0, n * 0.1)
        letti.append(mappe.value('m1', n * 0.1))
    return letti


class TestIlCatalogo:

    def test_i_tipi_sono_sei(self):
        assert MAP_TYPES == TIPI
        assert tuple(MAP_KINDS) == TIPI

    @pytest.mark.parametrize('tipo', TIPI)
    def test_x0_e_intervalli_sono_dati_del_tipo(self, tipo):
        x0, r_range, value_range = DICHIARATO[tipo]
        kind = MAP_KINDS[tipo]
        assert kind.name == tipo
        assert kind.x0 == x0
        assert kind.r_range == r_range
        assert kind.value_range == value_range

    def test_henon_ha_due_variabili(self):
        henon = MAP_KINDS['henon']
        assert henon.variables == 2
        assert henon.y0 == 0.1
        # y e' 0.3*x: il suo intervallo e' quello di x, scalato
        assert henon.y_range == pytest.approx((-0.39, 0.42))
        assert [t for t in TIPI if MAP_KINDS[t].variables == 2] == ['henon']

    def test_le_altre_ne_hanno_una(self):
        for tipo in TIPI:
            if tipo != 'henon':
                assert MAP_KINDS[tipo].variables == 1
                assert MAP_KINDS[tipo].y_range is None

    def test_il_modulo_non_importa_terze_parti(self):
        """Lo legge anche chi non costruisce uno stream: solo la libreria
        standard."""
        albero = ast.parse(inspect.getsource(catalog))
        importati = set()
        for nodo in ast.walk(albero):
            if isinstance(nodo, ast.Import):
                importati |= {a.name.split('.')[0] for a in nodo.names}
            elif isinstance(nodo, ast.ImportFrom):
                importati.add((nodo.module or '').split('.')[0])
        assert importati <= {'__future__', 'dataclasses', 'typing', 'math'}

    def test_i_tipi_si_leggono_dal_sorgente_senza_importare(self):
        """`MAP_TYPES` e' una tupla letterale: un language server la legge
        dall'AST."""
        albero = ast.parse(inspect.getsource(catalog))
        letti = [ast.literal_eval(n.value) for n in albero.body
                 if isinstance(n, ast.Assign)
                 and any(getattr(t, 'id', None) == 'MAP_TYPES'
                         for t in n.targets)]
        assert letti == [TIPI]

    def test_gli_intervalli_si_leggono_dal_sorgente_senza_importare(self):
        """L'intervallo di `m1` e' un dato leggibile da un editor, non solo
        prosa: ogni voce di `MAP_KINDS` lo dichiara con un letterale."""
        albero = ast.parse(inspect.getsource(catalog))
        letti = {}
        for nodo in ast.walk(albero):
            if not (isinstance(nodo, ast.Call)
                    and getattr(nodo.func, 'id', None) == 'MapKind'):
                continue
            chiavi = {k.arg: k.value for k in nodo.keywords}
            letti[ast.literal_eval(chiavi['name'])] = (
                ast.literal_eval(chiavi['x0']),
                ast.literal_eval(chiavi['r_range']),
                ast.literal_eval(chiavi['value_range']))
        assert letti == DICHIARATO


class TestIlPasso:

    @pytest.mark.parametrize('tipo, x, y, r', [
        ('logistic', 0.3, 0.0, 3.5),
        ('tent', 0.3, 0.0, 3.0),
        ('tent', 0.7, 0.0, 3.0),
        ('sine', 0.1, 0.0, 3.0),
        ('sine', -0.4, 0.0, 3.7),
        ('cubic', 0.3, 0.0, 2.7),
        ('cubic', -0.9, 0.0, 2.2),
        ('henon', 0.1, 0.1, 1.4),
        ('henon', -0.6, 0.25, 1.2),
        ('circle', 0.2, 0.0, 0.42),
        ('circle', 0.9, 0.0, 0.7),
    ])
    def test_e_la_formula(self, tipo, x, y, r):
        ottenuto = MAP_KINDS[tipo].advance(x, y, r)
        assert ottenuto == pytest.approx(A_MANO[tipo](x, y, r), abs=1e-12)

    def test_i_numeri_a_mano(self):
        """Gli stessi passi, in cifre: una formula sbagliata due volte allo
        stesso modo qui si vede."""
        assert MAP_KINDS['tent'].advance(0.3, 0, 3.0)[0] == pytest.approx(0.45)
        assert MAP_KINDS['tent'].advance(0.7, 0, 3.0)[0] == pytest.approx(0.45)
        assert MAP_KINDS['sine'].advance(0.1, 0, 3.0)[0] == pytest.approx(
            0.2955202, abs=1e-7)
        assert MAP_KINDS['cubic'].advance(0.3, 0, 2.7)[0] == pytest.approx(
            0.7371)
        assert MAP_KINDS['henon'].advance(0.1, 0.1, 1.4) == pytest.approx(
            (1.086, 0.03))
        assert MAP_KINDS['circle'].advance(0.2, 0, 0.42)[0] == pytest.approx(
            0.3346830, abs=1e-7)

    @pytest.mark.parametrize('tipo', [t for t in TIPI if t != 'henon'])
    def test_step_resta_la_funzione_a_una_variabile(self, tipo):
        """`step(x, r)` e' il passo delle mappe a una variabile, com'era
        per la logistica."""
        kind = MAP_KINDS[tipo]
        assert kind.step(0.3, 2.9) == pytest.approx(
            A_MANO[tipo](0.3, 0.0, 2.9)[0], abs=1e-12)

    def test_il_primo_grano_legge_il_primo_passo_da_x0(self):
        for tipo in TIPI:
            x0, (r_min, r_max), _ = DICHIARATO[tipo]
            r = 0.5 * (r_min + r_max)
            letto, = _valori(tipo, r, 1, transient=0)
            y0 = MAP_KINDS[tipo].y0
            assert letto == pytest.approx(A_MANO[tipo](x0, y0, r)[0],
                                          abs=1e-12), tipo


class TestValoriNoti:
    """Punti fissi calcolati a mano: dove la mappa si ferma, la sequenza
    letta e' un valore solo."""

    def test_cubic_a_r_1_8_si_ferma_a_due_terzi(self):
        """x = r*x*(1 - x*x)  =>  x*x = 1 - 1/r = 4/9."""
        valori = _valori('cubic', 1.8, 12)
        assert valori == pytest.approx([2 / 3] * 12, abs=1e-9)

    def test_sine_a_r_2_si_ferma_dove_x_e_sin_2x(self):
        valori = _valori('sine', 2.0, 12)
        x = valori[-1]
        assert x == pytest.approx(math.sin(2 * x), abs=1e-9)
        assert x == pytest.approx(0.947747, abs=1e-6)
        assert valori == pytest.approx([x] * 12, abs=1e-9)

    def test_sine_sotto_r_1_si_spegne_a_zero(self):
        assert _valori('sine', 0.5, 6) == pytest.approx([0.0] * 6, abs=1e-9)

    def test_henon_a_r_0_2_si_ferma_al_suo_punto_fisso(self):
        """x = 1 - r*x*x + 0.3*x  =>  r*x*x + 0.7*x - 1 = 0."""
        r = 0.2
        atteso = (-0.7 + math.sqrt(0.49 + 4 * r)) / (2 * r)
        valori = _valori('henon', r, 8, transient=2000)
        assert valori == pytest.approx([atteso] * 8, abs=1e-9)

    def test_la_tenda_non_ha_cicli_stabili_ma_un_punto_fisso(self):
        """Pendenza r/2 > 1: nessun ciclo attrae. Il punto fisso
        x = (r/2)/(1 + r/2), se ci si parte sopra, resta."""
        r = 3.0
        fisso = (r / 2) / (1 + r / 2)
        assert MAP_KINDS['tent'].step(fisso, r) == pytest.approx(fisso)
        assert len({round(v, 6) for v in _valori('tent', r, 200)}) > 150

    def test_il_cerchio_sta_fra_zero_e_uno_escluso(self):
        valori = _valori('circle', 0.42, 300)
        assert all(0.0 <= v < 1.0 for v in valori)
        assert len({round(v, 6) for v in valori}) > 3


class TestLIntervalloDichiaratoTiene:
    """Diecimila passi ai due capi dell'intervallo di `r`: il valore resta
    dove il catalogo dice che vive."""

    @pytest.mark.parametrize('tipo', TIPI)
    @pytest.mark.parametrize('capo', [0, 1])
    def test_ai_due_capi_di_r(self, tipo, capo):
        _, r_range, (basso, alto) = DICHIARATO[tipo]
        valori = _valori(tipo, r_range[capo], 10_000, transient=0)
        assert all(math.isfinite(v) for v in valori)
        assert min(valori) >= basso - 1e-9, min(valori)
        assert max(valori) <= alto + 1e-9, max(valori)

    @pytest.mark.parametrize('capo', [0, 1])
    def test_la_y_di_henon(self, capo):
        r = DICHIARATO['henon'][1][capo]
        mappe = MapSet.from_yaml({'m1': {'type': 'henon', 'r': r,
                                         'transient': 0}})
        basso, alto = MAP_KINDS['henon'].y_range
        for n in range(10_000):
            mappe.advance(0, n * 0.1)
            y = mappe.environment(['m1.y'], n * 0.1)['m1.y']
            assert basso - 1e-9 <= y <= alto + 1e-9

    def test_in_cima_all_intervallo_di_r_la_mappa_usa_la_fascia(self):
        """Non basta non uscire: ai valori alti di `r` la fascia dichiarata
        e' quella che la mappa percorre davvero, almeno per meta'."""
        for tipo in TIPI:
            _, r_range, (basso, alto) = DICHIARATO[tipo]
            valori = _valori(tipo, r_range[1], 5000, transient=0)
            assert max(valori) - min(valori) > 0.5 * (alto - basso), tipo


class TestLaTendaNonArrivaAQuattro:

    def test_il_tetto_di_r_sta_sotto_quattro(self):
        assert MAP_KINDS['tent'].r_range[1] < 4.0
        assert MAP_KINDS['tent'].r_range[1] == 3.999

    def test_a_quattro_esatto_collassa_a_zero(self):
        """Con pendenza 2 ogni passo raddoppia e toglie un bit: in float64
        dopo una cinquantina di passi resta zero, per sempre."""
        valori = _valori('tent', 4.0, 120, transient=0)
        primo_zero = valori.index(0.0)
        assert 40 <= primo_zero <= 60
        assert set(valori[primo_zero:]) == {0.0}

    def test_al_tetto_dichiarato_no(self):
        valori = _valori('tent', 3.999, 5000, transient=0)
        assert min(valori[100:]) > 0.0
        assert len({round(v, 9) for v in valori}) > 4000
