"""
Il blocco `maps:` di uno stream (issue #308, mappe caotiche 1/7): come si
dichiara una mappa, da dove parte, e chi la muove.

In questa fetta una mappa fa un passo per grano (`clock: grain`, il default)
e `r` e' un numero. Lo stato e' **uno per voce**: con piu' voci e `scatter` le
chiamate arrivano fuori ordine, e uno stato condiviso verrebbe iterato in
ordine mescolato. La mappa avanza in un punto solo (`advance`), e chi la legge
(`value`) non la muove.
"""
from unittest.mock import patch

import pytest

from pge.maps.map_set import (
    MAP_ESCAPE_LIMIT,
    MAP_ESCAPE_LOG_INTERVAL,
    MAP_KEYS,
    MAP_TRANSIENT_DEFAULT,
    MAP_TRANSIENT_MAX,
    MapSet,
)
from pge.shared.exceptions import ConfigError, MapConfigError


def _logistica(x, r):
    return r * x * (1 - x)


def _dopo(passi, r=3.7, x0=0.3):
    x = x0
    for _ in range(passi):
        x = _logistica(x, r)
    return x


def _mappe(**chiavi):
    mappa = {'type': 'logistic', 'r': 3.7}
    mappa.update(chiavi)
    return MapSet.from_yaml({'m1': mappa})


# =============================================================================
# 1. STATO INIZIALE E TRANSITORIO
# =============================================================================

class TestStatoIniziale:

    def test_senza_transitorio_il_primo_grano_legge_il_primo_passo(self):
        mappe = _mappe(transient=0)
        mappe.advance(0, 0.0)
        assert mappe.value('m1', 0.0) == _dopo(1)

    def test_x0_si_sovrascrive(self):
        mappe = _mappe(transient=0, x0=0.11)
        mappe.advance(0, 0.0)
        assert mappe.value('m1', 0.0) == _dopo(1, x0=0.11)

    def test_il_transitorio_di_default_scarta_trecento_passi(self):
        """Come nel banco: il primo grano e' gia' sull'attrattore."""
        assert MAP_TRANSIENT_DEFAULT == 300
        mappe = _mappe()
        mappe.advance(0, 0.0)
        assert mappe.value('m1', 0.0) == _dopo(301)

    def test_il_transitorio_si_dichiara(self):
        mappe = _mappe(transient=10)
        mappe.advance(0, 0.0)
        assert mappe.value('m1', 0.0) == _dopo(11)

    def test_x0_non_dipende_da_niente_fuori_dalla_mappa(self):
        """Una mappa e' deterministica, ed e' il suo punto: due insiemi con
        la stessa dichiarazione danno la stessa sequenza."""
        a, b = _mappe(), _mappe()
        for n in range(20):
            a.advance(0, n)
            b.advance(0, n)
            assert a.value('m1', n) == b.value('m1', n)


# =============================================================================
# 2. UN PASSO PER GRANO E PER VOCE
# =============================================================================

class TestStatoPerVoce:

    def test_leggere_non_muove(self):
        mappe = _mappe(transient=0)
        mappe.advance(0, 0.0)
        assert mappe.value('m1', 0.0) == mappe.value('m1', 0.0) == _dopo(1)

    def test_ogni_voce_ha_il_suo_stato(self):
        mappe = _mappe(transient=0)
        for _ in range(3):
            mappe.advance(0, 0.0)
        mappe.advance(1, 0.0)
        assert mappe.value('m1', 0.0) == _dopo(1)   # la voce appena mossa
        mappe.select(0)
        assert mappe.value('m1', 0.0) == _dopo(3)

    def test_l_ordine_in_cui_le_voci_avanzano_non_conta(self):
        """Fuori ordine, come con `scatter`: ogni voce conta i suoi passi."""
        ordinate, mescolate = _mappe(transient=0), _mappe(transient=0)
        for voce in (0, 0, 0, 1, 1, 2):
            ordinate.advance(voce, 0.0)
        for voce in (2, 0, 1, 0, 1, 0):
            mescolate.advance(voce, 0.0)
        for voce, passi in ((0, 3), (1, 2), (2, 1)):
            ordinate.select(voce)
            mescolate.select(voce)
            assert ordinate.value('m1', 0.0) == _dopo(passi)
            assert mescolate.value('m1', 0.0) == _dopo(passi)

    def test_una_voce_mai_mossa_sta_sullo_stato_iniziale(self):
        mappe = _mappe(transient=4)
        mappe.select(5)
        assert mappe.value('m1', 0.0) == _dopo(4)

    def test_due_mappe_avanzano_insieme(self):
        mappe = MapSet.from_yaml({
            'lenta': {'type': 'logistic', 'r': 3.2, 'transient': 0},
            'svelta': {'type': 'logistic', 'r': 3.9, 'transient': 0},
        })
        mappe.advance(0, 0.0)
        assert mappe.value('lenta', 0.0) == _dopo(1, r=3.2)
        assert mappe.value('svelta', 0.0) == _dopo(1, r=3.9)


# =============================================================================
# 3. I NOMI
# =============================================================================

class TestNomi:

    def test_i_nomi_sono_quelli_dichiarati_nell_ordine_dello_yaml(self):
        mappe = MapSet.from_yaml({
            'b': {'type': 'logistic', 'r': 3.2},
            'a': {'type': 'logistic', 'r': 3.2},
        })
        assert mappe.names == ('b', 'a')

    def test_le_variabili_di_un_espressione_sono_le_mappe_e_t(self):
        assert _mappe().variables == ('m1', 't')

    def test_senza_mappe_resta_t(self):
        vuoto = MapSet()
        assert vuoto.names == ()
        assert vuoto.variables == ('t',)
        vuoto.advance(0, 1.0)      # non fa niente, e non si rompe
        vuoto.select(3)

    def test_l_ambiente_porta_il_tempo_e_le_sole_mappe_chieste(self):
        mappe = _mappe(transient=0)
        mappe.advance(0, 2.5)
        assert mappe.environment(('m1', 't'), 2.5) == {
            'm1': _dopo(1), 't': 2.5}
        assert mappe.environment(('t',), 2.5) == {'t': 2.5}


# =============================================================================
# 4. LA MAPPA CHE SCAPPA
# =============================================================================

class TestFuga:
    """Fuori dal suo intervallo di `r` una mappa diverge: la logistica con
    r > 4 esce da 0...1 e va a meno infinito. Il valore non arriva al grano:
    la mappa riparte da `x0`, e lo scrive sul clip log."""

    def test_la_mappa_riparte_da_x0(self):
        mappe = _mappe(r=4.5, transient=0)
        with patch('pge.maps.map_set.log_map_escape_warning'):
            for n in range(200):
                mappe.advance(0, n * 0.01)
                assert abs(mappe.value('m1', 0.0)) <= MAP_ESCAPE_LIMIT

    def test_la_fuga_si_scrive_sul_clip_log(self):
        mappe = MapSet.from_yaml(
            {'m1': {'type': 'logistic', 'r': 4.5, 'transient': 0}},
            stream_id='s1')
        with patch('pge.maps.map_set.log_map_escape_warning') as log:
            for n in range(200):
                mappe.advance(0, 0.0)
        assert log.call_count == 1
        chiamata = log.call_args.kwargs
        assert chiamata['stream_id'] == 's1'
        assert chiamata['map_name'] == 'm1'
        assert chiamata['is_first'] is True

    def test_il_log_ha_un_rate_limit_sul_tempo_dello_stream(self):
        mappe = _mappe(r=4.5, transient=0)
        with patch('pge.maps.map_set.log_map_escape_warning') as log:
            for n in range(3000):
                mappe.advance(0, n * 0.01)          # 30 secondi di stream
        attesi = 30 / MAP_ESCAPE_LOG_INTERVAL
        assert attesi - 1 <= log.call_count <= attesi + 1
        assert [c.kwargs['is_first'] for c in log.call_args_list][:2] == [
            True, False]

    def test_il_transitorio_non_scrive_niente(self):
        with patch('pge.maps.map_set.log_map_escape_warning') as log:
            _mappe(r=4.5).select(0)
        assert log.call_count == 0

    def test_una_mappa_sana_non_scrive_niente(self):
        mappe = _mappe(r=3.99)
        with patch('pge.maps.map_set.log_map_escape_warning') as log:
            for n in range(2000):
                mappe.advance(0, n * 0.01)
        assert log.call_count == 0


# =============================================================================
# 5. ERRORI
# =============================================================================

class TestErrori:

    def test_sta_fra_gli_errori_di_configurazione(self):
        assert issubclass(MapConfigError, ConfigError)

    @pytest.mark.parametrize('maps, campo, dice', [
        (None, 'maps', 'dizionario'),
        ([], 'maps', 'dizionario'),
        ('m1', 'maps', 'dizionario'),
        ({}, 'maps', 'nessuna mappa'),
        ({'m1': None}, 'maps.m1', 'dizionario'),
        ({'m1': 3.5}, 'maps.m1', 'dizionario'),
        ({'m1': {'r': 3.5}}, 'maps.m1.type', 'manca'),
        ({'m1': {'type': 'boh', 'r': 3.5}}, 'maps.m1.type', 'sconosciuto'),
        ({'m1': {'type': 'logistic'}}, 'maps.m1.r', 'manca'),
        ({'m1': {'type': 'logistic', 'r': None}}, 'maps.m1.r', 'manca'),
        ({'m1': {'type': 'logistic', 'r': 'tre'}}, 'maps.m1.r', 'numero'),
        ({'m1': {'type': 'logistic', 'r': True}}, 'maps.m1.r', 'numero'),
        ({'m1': {'type': 'logistic', 'r': float('nan')}},
         'maps.m1.r', 'finito'),
        ({'m1': {'type': 'logistic', 'r': float('inf')}},
         'maps.m1.r', 'finito'),
        ({'m1': {'type': 'logistic', 'r': 3.5, 'x0': 'a'}},
         'maps.m1.x0', 'numero'),
        ({'m1': {'type': 'logistic', 'r': 3.5, 'transient': -1}},
         'maps.m1.transient', 'intero'),
        ({'m1': {'type': 'logistic', 'r': 3.5, 'transient': 2.5}},
         'maps.m1.transient', 'intero'),
        ({'m1': {'type': 'logistic', 'r': 3.5, 'transient': True}},
         'maps.m1.transient', 'intero'),
        ({'m1': {'type': 'logistic', 'r': 3.5, 'rr': 1}},
         'maps.m1.rr', 'chiave sconosciuta'),
        ({'1m': {'type': 'logistic', 'r': 3.5}}, 'maps.1m', 'nome'),
        ({'m-1': {'type': 'logistic', 'r': 3.5}}, 'maps.m-1', 'nome'),
        ({1: {'type': 'logistic', 'r': 3.5}}, 'maps.1', 'nome'),
        ({'m1.y': {'type': 'logistic', 'r': 3.5}}, 'maps.m1.y', 'nome'),
    ])
    def test_un_blocco_scritto_male_dice_dove_e_cosa(self, maps, campo, dice):
        with pytest.raises(MapConfigError) as exc:
            MapSet.from_yaml(maps)
        assert exc.value.field == campo
        assert dice in exc.value.reason

    @pytest.mark.parametrize('nome', ['t', 'pi', 'e', 'sin', 'clip', 'x',
                                      'y', 'r'])
    def test_un_nome_del_linguaggio_non_e_un_nome_di_mappa(self, nome):
        """`sin`, `pi`, `t` sono gia' qualcosa in un'espressione, e `x`, `y`,
        `r` lo sono dentro l'equazione di una mappa: una mappa con quel nome
        non si potrebbe leggere, o cambierebbe il significato di un testo
        gia' scritto."""
        with pytest.raises(MapConfigError) as exc:
            MapSet.from_yaml({nome: {'type': 'logistic', 'r': 3.5}})
        assert exc.value.field == f'maps.{nome}'
        assert 'riservato' in exc.value.reason

    def test_il_type_sconosciuto_dice_quali_ci_sono(self):
        with pytest.raises(MapConfigError) as exc:
            MapSet.from_yaml({'m1': {'type': 'tent', 'r': 3.5}})
        assert 'logistic' in exc.value.hint
        assert exc.value.value == 'tent'

    def test_la_chiave_sconosciuta_dice_quali_ci_sono(self):
        with pytest.raises(MapConfigError) as exc:
            MapSet.from_yaml({'m1': {'type': 'logistic', 'r': 3.5, 'R': 3}})
        for chiave in MAP_KEYS:
            assert chiave in exc.value.hint

    def test_l_errore_nomina_lo_stream(self):
        with pytest.raises(MapConfigError) as exc:
            MapSet.from_yaml({'m1': {'type': 'logistic'}}, stream_id='s7')
        assert exc.value.stream_id == 's7'
        assert 'Stream:       s7' in exc.value.user_message()
        assert "maps.m1.r" in exc.value.user_message()

    def test_clock_grain_e_il_default_e_si_puo_scrivere(self):
        esplicito = _mappe(clock='grain', transient=0)
        esplicito.advance(0, 0.0)
        assert esplicito.value('m1', 0.0) == _dopo(1)

    def test_il_transitorio_ha_un_tetto(self):
        """Il transitorio si fa una volta per mappa, e fino al tetto costa
        pochi millisecondi: e' piu' di trecento volte il default, abbastanza
        per gli attrattori che si raggiungono piano (vicino a una
        biforcazione). Senza tetto un `transient: 1000000000` teneva fermo
        il caricamento per minuti."""
        mappe = _mappe(transient=MAP_TRANSIENT_MAX)
        assert mappe.value('m1', 0.0) == _dopo(MAP_TRANSIENT_MAX)
        with pytest.raises(MapConfigError) as exc:
            MapSet.from_yaml(
                {'m1': {'type': 'logistic', 'r': 3.7,
                        'transient': MAP_TRANSIENT_MAX + 1}},
                stream_id='s1')
        assert exc.value.field == 'maps.m1.transient'
        assert str(MAP_TRANSIENT_MAX) in exc.value.reason
        assert exc.value.stream_id == 's1'
        assert MAP_TRANSIENT_MAX >= 300 * MAP_TRANSIENT_DEFAULT

    @pytest.mark.parametrize('clock', ['tempo', None, True])
    def test_un_clock_che_non_e_un_clock(self, clock):
        with pytest.raises(MapConfigError) as exc:
            _mappe(clock=clock)
        assert exc.value.field == 'maps.m1.clock'
