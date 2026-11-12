"""
`type: custom`: l'equazione della mappa scritta nello YAML (issue #313, mappe
caotiche 5/7).

    maps:
      m2:
        type: custom
        x: sin(r*x)*cos(x)
        r: 3

`x:` e' obbligatoria, `y:` opzionale; il linguaggio e' quello delle
espressioni, con le variabili `x`, `y`, `r`. Un tipo di catalogo con accanto
un `x:` e' un errore: non si capirebbe quale delle due equazioni vale.
"""
import math
from unittest.mock import patch

import pytest

from pge.maps.map_set import (
    MAP_CUSTOM_X0, MAP_CUSTOM_Y0, MAP_ESCAPE_LOG_INTERVAL, MAP_KEYS, MapSet,
)
from pge.shared.exceptions import ConfigError, ExpressionError, MapConfigError


def _mappe(**mappa):
    return MapSet.from_yaml({'m2': {'type': 'custom', **mappa}},
                            stream_id='s1')


def _letti(mappe, quanti, nome='m2'):
    valori = []
    for n in range(quanti):
        mappe.advance(0, n * 0.1)
        valori.append(mappe.value(nome, n * 0.1))
    return valori


class TestLEquazione:

    def test_lo_yaml_della_issue(self):
        mappe = _mappe(x='sin(r*x)*cos(x)', r=3, transient=0)
        x = MAP_CUSTOM_X0
        attesi = []
        for _ in range(6):
            x = math.sin(3 * x) * math.cos(x)
            attesi.append(x)
        assert _letti(mappe, 6) == pytest.approx(attesi, abs=1e-12)

    def test_la_logistica_scritta_a_mano_e_la_logistica(self):
        a_mano = _mappe(x='r*x*(1-x)', r=3.5, x0=0.3)
        catalogo = MapSet.from_yaml({'m2': {'type': 'logistic', 'r': 3.5}})
        assert _letti(a_mano, 12) == _letti(catalogo, 12)

    def test_le_parentesi_esterne_non_servono_ma_non_guastano(self):
        nuda = _mappe(x='r*x*(1-x)', r=3.5)
        vestita = _mappe(x='(r*x*(1-x))', r=3.5)
        assert _letti(nuda, 8) == _letti(vestita, 8)

    def test_le_funzioni_del_linguaggio(self):
        mappe = _mappe(x='fold(r*x, 0, 1)', r=2.7, transient=0, x0=0.5)
        # 1.35 esce da 0-1 e si riflette: 2 - 1.35
        assert _letti(mappe, 1) == pytest.approx([0.65])

    def test_un_numero_e_l_equazione_costante(self):
        mappe = _mappe(x=0.25, transient=0)
        assert _letti(mappe, 3) == [0.25, 0.25, 0.25]

    def test_lo_stato_iniziale_ha_un_default_e_si_sovrascrive(self):
        assert (MAP_CUSTOM_X0, MAP_CUSTOM_Y0) == (0.1, 0.1)
        mappe = _mappe(x='x + 1', transient=0, x0=5)
        assert _letti(mappe, 2) == [6.0, 7.0]

    def test_r_a_envelope(self):
        mappe = MapSet.from_yaml(
            {'m2': {'type': 'custom', 'x': 'r + 0*x',
                    'r': [[0, 1.0], [10, 2.0]], 'transient': 0}},
            duration=10.0)
        mappe.advance(0, 5.0)
        assert mappe.value('m2', 5.0) == pytest.approx(1.5)

    def test_le_chiavi_dell_equazione_sono_chiavi_di_una_mappa(self):
        assert {'x', 'y', 'y0'} <= set(MAP_KEYS)


class TestDueVariabili:

    def test_henon_scritta_a_mano_e_henon(self):
        a_mano = MapSet.from_yaml({'m2': {
            'type': 'custom', 'x': '1 - r*x*x + y', 'y': '0.3*x', 'r': 1.4,
            'x0': 0.1, 'y0': 0.1}})
        catalogo = MapSet.from_yaml({'m2': {'type': 'henon', 'r': 1.4}})
        for n in range(40):
            a_mano.advance(0, n * 0.1)
            catalogo.advance(0, n * 0.1)
            assert (a_mano.environment(['m2', 'm2.y'], 0.0)
                    == catalogo.environment(['m2', 'm2.y'], 0.0))

    def test_con_y_la_seconda_variabile_si_legge(self):
        assert _mappe(x='y', y='x').variables == ('m2', 'm2.y', 't')

    def test_senza_y_no(self):
        assert _mappe(x='r*x*(1-x)', r=3.5).variables == ('m2', 't')

    def test_i_due_aggiornamenti_usano_la_coppia_di_prima(self):
        """Uno scambio: se `y` leggesse l'`x` gia' aggiornato, le due
        variabili diventerebbero uguali."""
        mappe = _mappe(x='y', y='x', x0=1, y0=2, transient=0)
        mappe.advance(0, 0.0)
        assert mappe.environment(['m2', 'm2.y'], 0.0) == {'m2': 2.0,
                                                           'm2.y': 1.0}


class TestErrori:

    def test_senza_x(self):
        with pytest.raises(MapConfigError) as exc:
            _mappe(r=3)
        assert exc.value.field == 'maps.m2.x'
        assert exc.value.stream_id == 's1'

    @pytest.mark.parametrize('chiave', ['x', 'y'])
    @pytest.mark.parametrize('tipo', ['logistic', 'henon'])
    def test_un_tipo_di_catalogo_con_un_equazione(self, tipo, chiave):
        with pytest.raises(MapConfigError) as exc:
            MapSet.from_yaml(
                {'m1': {'type': tipo, 'r': 1.2, chiave: 'r*x'}})
        assert exc.value.field == f'maps.m1.{chiave}'
        assert 'custom' in exc.value.hint

    def test_un_nome_sconosciuto_nell_equazione(self):
        with pytest.raises(ExpressionError) as exc:
            _mappe(x='r*z', r=3)
        err = exc.value
        assert isinstance(err, ConfigError)
        assert err.field == 'maps.m2.x'
        assert err.stream_id == 's1'
        assert 'z' in err.reason
        assert all(nome in err.hint for nome in ('x', 'y', 'r'))

    def test_un_equazione_non_legge_le_altre_mappe_ne_il_tempo(self):
        for testo in ('m1 + x', 't*x'):
            with pytest.raises(ExpressionError):
                MapSet.from_yaml({
                    'm1': {'type': 'logistic', 'r': 3.5},
                    'm2': {'type': 'custom', 'x': testo}})

    def test_un_errore_di_sintassi_dice_dove(self):
        with pytest.raises(ExpressionError) as exc:
            _mappe(x='1 - r*x*x + y', y='0.3*x)', r=1.4)
        assert exc.value.field == 'maps.m2.y'

    def test_x_legge_y_ma_y_non_c_e(self):
        with pytest.raises(MapConfigError) as exc:
            _mappe(x='1 - r*x*x + y', r=1.4)
        assert exc.value.field == 'maps.m2.x'
        assert 'y:' in exc.value.hint

    def test_y0_senza_y(self):
        with pytest.raises(MapConfigError) as exc:
            _mappe(x='r*x', r=1.4, y0=0.2)
        assert exc.value.field == 'maps.m2.y0'

    def test_un_equazione_che_non_e_un_testo(self):
        with pytest.raises(MapConfigError) as exc:
            _mappe(x=[1, 2])
        assert exc.value.field == 'maps.m2.x'

    def test_r_manca_e_l_equazione_lo_legge(self):
        with pytest.raises(MapConfigError) as exc:
            _mappe(x='r*x*(1-x)')
        assert exc.value.field == 'maps.m2.r'

    def test_r_manca_e_l_equazione_non_lo_legge(self):
        mappe = _mappe(x='1 - x', transient=0, x0=0.25)
        assert _letti(mappe, 2) == [0.75, 0.25]


class TestLaMappaCheScappa:
    """Un'equazione scritta a mano scappa piu' facilmente di una di
    catalogo: la rete e' la stessa."""

    def test_riparte_da_x0(self):
        mappe = _mappe(x='2*x + 1', transient=0, x0=1)
        valori = _letti(mappe, 40)
        assert all(abs(v) <= 1e3 for v in valori)
        assert valori.count(1.0) >= 2

    def test_un_valore_non_finito_e_una_fuga(self):
        mappe = _mappe(x='1/(x - x)', transient=0, x0=0.5)
        assert _letti(mappe, 3) == [0.5, 0.5, 0.5]

    def test_lo_scrive_sul_clip_log_col_limite_di_frequenza(self):
        """Scappa a ogni passo, dieci passi al secondo per dodici secondi:
        una riga subito, poi una ogni 5 s di stream."""
        with patch('pge.maps.map_set.log_map_escape_warning') as log:
            mappe = _mappe(x='1/(x - x)', transient=0)
            _letti(mappe, 120)
        assert log.call_count == 3
        assert [c.kwargs['is_first'] for c in log.call_args_list] == [
            True, False, False]
        tempi = [c.kwargs['elapsed_time'] for c in log.call_args_list]
        assert all(b - a >= MAP_ESCAPE_LOG_INTERVAL - 1e-9
                   for a, b in zip(tempi, tempi[1:]))
        assert log.call_args_list[0].kwargs['map_name'] == 'm2'

    def test_in_iterate_dopo_la_fuga_non_si_itera_oltre(self):
        """`x*4`: al quinto passo supera 1000. Con dodici passi a lettura
        il valore e' `x0`, non cio' che ne uscirebbe iterando ancora da
        `x0` per i passi che restano."""
        mappe = _mappe(x='x*4', iterate=12, x0=1)
        assert mappe.value('m2', 0.0) == 1.0
        sotto = _mappe(x='x*4', iterate=4, x0=1)
        assert sotto.value('m2', 0.0) == 256.0

    def test_la_seconda_variabile_che_scappa_riporta_tutte_e_due(self):
        mappe = _mappe(x='x', y='y*10', x0=0.5, y0=1, transient=0)
        for n in range(6):
            mappe.advance(0, n * 0.1)
            assert mappe.environment(['m2', 'm2.y'], 0.0)['m2.y'] <= 1e3
        mappe2 = _mappe(x='x + 1', y='y*100', x0=0, y0=1, transient=0)
        mappe2.advance(0, 0.0)
        mappe2.advance(0, 0.1)
        assert mappe2.environment(['m2', 'm2.y'], 0.1) == {
            'm2': 0.0, 'm2.y': 1.0}
