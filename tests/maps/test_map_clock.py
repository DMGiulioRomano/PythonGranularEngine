"""
Come avanza una mappa: `r` a envelope e clock a orologio (issue #310, mappe
caotiche 2/7).

Dopo la 1/7 la mappa fa un passo per grano e `r` e' un numero. Qui `clock`
puo' essere un numero di passi al secondo, o un envelope, e `r` puo' muoversi
nel tempo:

    maps:
      m1: {type: logistic, r: [[0, 3.0], [12, 4.0]], clock: [[0, 2], [12, 20]]}

Un clock a orologio e' una **funzione del tempo**: il valore resta fermo fino
al passo successivo, non ha uno stato per voce, e tutte le voci leggono lo
stesso valore allo stesso istante. Il passo k cade dove l'integrale del clock
vale k; il primo, k = 0, a t = 0, come nel banco.
"""
from unittest.mock import patch

import pytest

from pge.envelopes.envelope import Envelope
from pge.maps.map_set import MAP_ESCAPE_LIMIT, MAP_KEYS, MapSet
from pge.shared.exceptions import ConfigError, MapConfigError

DURATA = 12.0


def _logistica(x, r):
    return r * x * (1 - x)


def _mappe(time_mode='absolute', durata=DURATA, **chiavi):
    mappa = {'type': 'logistic', 'r': 3.7, 'transient': 0}
    mappa.update(chiavi)
    return MapSet.from_yaml({'m1': mappa}, stream_id='s1',
                            duration=durata, time_mode=time_mode)


def _sequenza(passi, r_a, tempi, x0=0.3):
    """I primi `passi` valori, col passo k fatto con r(tempi[k])."""
    x, valori = x0, []
    for k in range(passi):
        x = _logistica(x, r_a(tempi[k]))
        valori.append(x)
    return valori


# =============================================================================
# 1. CLOCK NUMERICO
# =============================================================================

class TestClockNumerico:

    def test_cinque_passi_al_secondo_uno_ogni_due_decimi(self):
        mappe = _mappe(clock=5)
        assert mappe.step_times('m1', 1.0) == pytest.approx(
            [0.0, 0.2, 0.4, 0.6, 0.8])

    def test_il_valore_resta_fermo_fino_al_passo_dopo(self):
        mappe = _mappe(clock=5)
        attesi = _sequenza(5, lambda t: 3.7, [0] * 5)
        for t, passo in ((0.0, 0), (0.1, 0), (0.199, 0), (0.2, 1),
                         (0.39, 1), (0.4, 2), (0.999, 4)):
            assert mappe.value('m1', t) == attesi[passo], t

    def test_non_ha_uno_stato_per_voce(self):
        """E' una funzione del tempo: tutte le voci leggono lo stesso valore
        allo stesso istante, e il giro di una voce non la muove."""
        mappe = _mappe(clock=5)
        primo = mappe.value('m1', 0.3)
        for voce in (0, 3, 1, 3, 3):
            mappe.advance(voce, 0.3)
            assert mappe.value('m1', 0.3) == primo
        mappe.select(7)
        assert mappe.value('m1', 0.3) == primo

    def test_le_letture_col_tempo_che_torna_indietro_restano_coerenti(self):
        """Con `scatter` le voci chiedono i grani fuori ordine nel tempo."""
        in_ordine, mescolate = _mappe(clock=5), _mappe(clock=5)
        tempi = [0.05, 0.25, 0.45, 2.0, 7.3, 11.9]
        attesi = [in_ordine.value('m1', t) for t in tempi]
        for t in (7.3, 0.05, 11.9, 0.45, 2.0, 0.25, 0.05):
            assert mescolate.value('m1', t) == attesi[tempi.index(t)]

    def test_il_transitorio_si_scarta_prima_del_primo_passo(self):
        mappe = _mappe(clock=5, transient=10)
        assert mappe.value('m1', 0.0) == _sequenza(11, lambda t: 3.7,
                                                    [0] * 11)[-1]

    def test_un_clock_frazionario(self):
        """Mezzo passo al secondo: un passo ogni due secondi."""
        assert _mappe(clock=0.5).step_times('m1', DURATA) == pytest.approx(
            [0, 2, 4, 6, 8, 10])


# =============================================================================
# 2. CLOCK A ENVELOPE
# =============================================================================

class TestClockEnvelope:

    CLOCK = [[0, 2], [12, 20]]

    def test_da_2_a_20_passi_al_secondo_in_12_secondi_sono_132(self):
        """Il numero del plan: l'integrale del clock su 12 s vale 132."""
        assert len(_mappe(clock=self.CLOCK).step_times('m1', DURATA)) == 132

    def test_il_passo_k_cade_dove_l_integrale_vale_k(self):
        tempi = _mappe(clock=self.CLOCK).step_times('m1', DURATA)
        clock = Envelope(self.CLOCK)
        assert tempi[0] == 0.0
        for k, t in enumerate(tempi):
            assert clock.integrate(0, t) == pytest.approx(k, abs=1e-6)
        assert tempi == sorted(tempi)

    def test_i_passi_si_addensano_come_cresce_il_clock(self):
        tempi = _mappe(clock=self.CLOCK).step_times('m1', DURATA)
        assert tempi[1] - tempi[0] > 0.4          # ~2 passi/s in principio
        assert tempi[-1] - tempi[-2] < 0.06       # ~20 passi/s alla fine

    def test_il_valore_e_quello_dell_ultimo_passo_fatto(self):
        mappe = _mappe(clock=self.CLOCK)
        tempi = mappe.step_times('m1', DURATA)
        attesi = _sequenza(len(tempi), lambda t: 3.7, tempi)
        for k in (0, 1, 17, 60, 131):
            dopo = tempi[k] + 1e-4
            assert mappe.value('m1', dopo) == attesi[k]

    def test_segue_il_time_mode_dello_stream(self):
        """Con `time_mode: normalized` i tempi dell'envelope sono frazioni
        della durata dello stream, come per ogni altro envelope."""
        assoluto = _mappe(clock=self.CLOCK)
        normalizzato = _mappe(clock=[[0, 2], [1, 20]], time_mode='normalized')
        assert normalizzato.step_times('m1', DURATA) == pytest.approx(
            assoluto.step_times('m1', DURATA))

    def test_un_envelope_dichiarato_in_dict(self):
        mappe = _mappe(clock={'type': 'step', 'points': [[0, 1], [6, 4]]})
        tempi = mappe.step_times('m1', DURATA)
        assert tempi[:6] == pytest.approx([0, 1, 2, 3, 4, 5])
        assert tempi[6:10] == pytest.approx([6, 6.25, 6.5, 6.75])


# =============================================================================
# 3. `r` A ENVELOPE
# =============================================================================

class TestRAEnvelope:

    R = [[0, 3.0], [12, 4.0]]

    @staticmethod
    def _r(t):
        return 3.0 + t / 12.0

    def test_col_clock_a_orologio_si_legge_all_istante_del_passo(self):
        mappe = _mappe(r=self.R, clock=5)
        tempi = mappe.step_times('m1', DURATA)
        attesi = _sequenza(len(tempi), self._r, tempi)
        for k in (0, 1, 2, 30, 59):
            assert mappe.value('m1', tempi[k] + 1e-4) == pytest.approx(
                attesi[k], abs=1e-12)

    def test_col_clock_a_orologio_e_non_all_istante_della_lettura(self):
        """Due letture dentro lo stesso passo vedono lo stesso valore, anche
        se `r` nel frattempo si e' mosso."""
        mappe = _mappe(r=self.R, clock=0.5)
        assert mappe.value('m1', 2.1) == mappe.value('m1', 3.9)

    def test_con_clock_grain_si_legge_all_istante_del_grano(self):
        mappe = _mappe(r=self.R)
        tempi = [0.0, 0.7, 1.9, 6.0, 11.5]
        attesi = _sequenza(len(tempi), self._r, tempi)
        for t, atteso in zip(tempi, attesi):
            mappe.advance(0, t)
            assert mappe.value('m1', t) == pytest.approx(atteso, abs=1e-12)

    def test_il_transitorio_si_fa_a_r_di_zero(self):
        mappe = _mappe(r=self.R, transient=20)
        mappe.select(0)
        assert mappe.value('m1', 0.0) == pytest.approx(
            _sequenza(20, lambda t: 3.0, [0] * 20)[-1], abs=1e-12)

    def test_segue_il_time_mode_dello_stream(self):
        assoluto = _mappe(r=self.R, clock=5)
        normalizzato = _mappe(r=[[0, 3.0], [1, 4.0]], clock=5,
                              time_mode='normalized')
        for t in (0.0, 3.3, 9.9):
            assert normalizzato.value('m1', t) == pytest.approx(
                assoluto.value('m1', t), abs=1e-12)

    def test_una_mappa_che_scappa_lungo_la_strada_riparte(self):
        """`r` che sale oltre 4: da un certo punto la logistica scappa."""
        mappe = _mappe(r=[[0, 3.5], [12, 5.0]], clock=50)
        with patch('pge.maps.map_set.log_map_escape_warning') as log:
            for n in range(1200):
                assert abs(mappe.value('m1', n * 0.01)) <= MAP_ESCAPE_LIMIT
        assert log.call_count >= 1
        assert log.call_args_list[0].kwargs['is_first'] is True
        assert log.call_args_list[0].kwargs['r'] > 4.0


# =============================================================================
# 4. ERRORI
# =============================================================================

class TestErrori:

    def test_clock_sta_fra_le_chiavi(self):
        assert 'clock' in MAP_KEYS and 'iterate' in MAP_KEYS

    @pytest.mark.parametrize('clock', [0, -1, -0.5, float('inf'),
                                       float('nan'), 'tempo', True, None])
    def test_un_clock_non_positivo_o_non_finito_e_un_errore_al_parse(self, clock):
        with pytest.raises(MapConfigError) as exc:
            _mappe(clock=clock)
        assert exc.value.field == 'maps.m1.clock'
        assert exc.value.stream_id == 's1'

    @pytest.mark.parametrize('clock', [
        [[0, 2], [12, 0]],
        [[0, -1], [12, 2]],
        {'type': 'step', 'points': [[0, 1], [6, 0]]},
    ])
    def test_un_envelope_di_clock_con_un_punto_non_positivo(self, clock):
        with pytest.raises(MapConfigError) as exc:
            _mappe(clock=clock)
        assert exc.value.field == 'maps.m1.clock'
        assert 'positivo' in exc.value.reason

    @pytest.mark.parametrize('chiave', ['clock', 'r'])
    @pytest.mark.parametrize('envelope', [[], {}, [[0, 1], [1, 'a']]])
    def test_un_envelope_malformato_nomina_il_campo_e_lo_stream(
            self, chiave, envelope):
        with pytest.raises(ConfigError) as exc:
            _mappe(**{chiave: envelope})
        assert f'maps.m1.{chiave}' in exc.value.user_message()
        assert exc.value.stream_id == 's1'

    @pytest.mark.parametrize('output_sr', [None, 44100, 96000])
    def test_il_clock_arriva_fino_a_un_passo_per_campione(self, output_sr):
        """Il tetto e' la risoluzione del motore, un passo per campione:
        lo stesso a cui arriva una mappa a `clock: grain` con l'attesa piu'
        corta (`grain.iot`, un campione). Senza tetto `clock: 1e9` faceva un
        miliardo di passi al secondo di stream, e il render non finiva."""
        from pge.shared.constants import DEFAULT_OUTPUT_SR
        sr = output_sr or DEFAULT_OUTPUT_SR
        MapSet.from_yaml({'m1': {'type': 'logistic', 'r': 3.7, 'clock': sr}},
                         output_sr=output_sr)
        for clock in (sr * 1.001, [[0, 2], [1, sr + 1]], 1e9):
            with pytest.raises(MapConfigError) as exc:
                MapSet.from_yaml(
                    {'m1': {'type': 'logistic', 'r': 3.7, 'clock': clock}},
                    stream_id='s1', output_sr=output_sr)
            assert exc.value.field == 'maps.m1.clock'
            assert str(sr) in exc.value.reason
            assert exc.value.stream_id == 's1'

    def test_i_passi_si_chiedono_solo_a_un_clock_a_orologio(self):
        """Una mappa a `clock: grain` non ha passi nel tempo: dipendono dai
        grani."""
        assert _mappe().step_times('m1', DURATA) is None
