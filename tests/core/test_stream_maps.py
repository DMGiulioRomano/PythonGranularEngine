"""
Dallo YAML al grano: uno stream dichiara una mappa in `maps:` e
`grain.duration` la legge con un'espressione (issue #308, mappe caotiche 1/7).

    maps:
      m1: {type: logistic, r: 3.5}
    grain:
      duration: (0.02 + 0.08*m1)

Sono i criteri di accettazione della issue, uno per classe. I numeri sono
quelli del plan: con `r = 3.5` la logistica percorre quattro valori, e le
durate dei grani 86, 60, 90, 51 ms.
"""
from unittest.mock import patch

import numpy as np
import pytest
import soundfile as sf

from pge.core.stream import EXPRESSION_FIELDS, Stream
from pge.expressions.expression import Expression
from pge.maps.map_set import MapSet
from pge.shared.constants import DEFAULT_OUTPUT_SR
from pge.shared.exceptions import (
    ExpressionError,
    InvalidParameterError,
    MapConfigError,
)

_SAMPLE = 'silenzio.wav'
CICLO_MS = [86, 60, 90, 51]
MAPPA = {'m1': {'type': 'logistic', 'r': 3.5}}
#: `maps:` scritta e lasciata vuota (None e' «la chiave non c'e'»).
VUOTA = object()


@pytest.fixture(scope='module')
def samples_dir(tmp_path_factory):
    cartella = tmp_path_factory.mktemp('samples')
    sf.write(str(cartella / _SAMPLE), np.zeros(48000, dtype='float32'), 48000)
    return str(cartella)


@pytest.fixture
def stream(samples_dir):
    def costruisci(grain=None, maps=MAPPA, **extra):
        params = {
            'stream_id': 's1',
            'onset': 0.0,
            'duration': 4.0,
            'sample': _SAMPLE,
            'grain': {'duration': '(0.02 + 0.08*m1)', 'envelope': 'hanning'},
        }
        if maps is VUOTA:
            params['maps'] = None
        elif maps is not None:
            params['maps'] = maps
        if grain is not None:
            params['grain'] = {'envelope': 'hanning', **grain}
        params.update(extra)
        s = Stream(params, seed=1441, samples_dir=samples_dir)
        s.sample_table_num = 1
        s.window_table_map = {'hanning': 2}
        return s
    return costruisci


def _ms(grani):
    return [round(g.duration * 1000) for g in grani]


def _e_il_ciclo(durate_ms, ciclo=CICLO_MS):
    """Le durate percorrono il ciclo, a meno di rotazione."""
    periodo = len(ciclo)
    rotazioni = [ciclo[k:] + ciclo[:k] for k in range(periodo)]
    assert len(durate_ms) >= 2 * periodo, "troppo pochi grani per dirlo"
    assert durate_ms[:periodo] in rotazioni, durate_ms[:periodo]
    for n, durata in enumerate(durate_ms):
        assert durata == durate_ms[n % periodo]


# =============================================================================
# 1. LO YAML DELLA ISSUE RENDE
# =============================================================================

class TestLoYamlDellaIssue:

    def test_le_durate_percorrono_il_ciclo_della_logistica(self, stream):
        s = stream()
        _e_il_ciclo(_ms(s.voices[0]))

    def test_il_valore_del_parametro_e_un_espressione(self, stream):
        """Il terzo tipo di valore, accanto a numero ed envelope."""
        s = stream()
        assert isinstance(s.grain_duration.value, Expression)
        assert s.grain_duration.value.source == '(0.02 + 0.08*m1)'

    def test_lo_stream_espone_le_sue_mappe(self, stream):
        s = stream()
        assert isinstance(s.map_set, MapSet)
        assert s.map_set.names == ('m1',)

    def test_il_tempo_si_legge_anche_senza_mappe(self, stream):
        """`t` e' un nome del linguaggio: secondi dall'inizio dello stream."""
        s = stream(grain={'duration': '(0.02 + 0.01*t)'}, maps=None,
                   density=10)
        grani = s.voices[0]
        assert grani[0].duration == pytest.approx(0.02)
        assert grani[10].duration == pytest.approx(0.03)

    def test_le_espressioni_valgono_dove_e_dichiarato(self):
        assert 'grain.duration' in EXPRESSION_FIELDS


# =============================================================================
# 2. UNO STATO PER VOCE
# =============================================================================

class TestStatoPerVoce:

    def test_ogni_voce_percorre_il_ciclo_dall_inizio(self, stream):
        s = stream(density=10, voices={'num_voices': 3})
        assert len(s.voices) == 3
        for voce in s.voices:
            _e_il_ciclo(_ms(voce))
        assert _ms(s.voices[0]) == _ms(s.voices[1]) == _ms(s.voices[2])

    def test_con_scatter_i_cursori_divergono_e_la_sequenza_no(self, stream):
        """Con `scatter` le voci chiedono i grani fuori ordine nel tempo:
        ognuna conta comunque i suoi passi."""
        s = stream(density=10, distribution=1.0,
                   voices={'num_voices': 3, 'scatter': 1.0})
        onset = [[g.onset for g in voce] for voce in s.voices]
        assert onset[0][:5] != onset[1][:5], "i cursori non sono divergenti"
        for voce in s.voices:
            _e_il_ciclo(_ms(voce))

    def test_una_voce_spenta_conta_i_passi_lo_stesso(self, stream):
        """La mappa avanza a ogni giro della voce, anche quando `num_voices`
        la tiene spenta: la sua sequenza non dipende da quando si accende."""
        accesa = stream(density=10, voices={'num_voices': 2})
        tardi = stream(density=10, voices={
            'num_voices': {'type': 'step', 'points': [[0, 1], [2, 2]]}})
        seconda = tardi.voices[1]
        assert 0 < len(seconda) < len(accesa.voices[1])
        saltati = len(accesa.voices[1]) - len(seconda)
        assert _ms(seconda) == _ms(accesa.voices[1])[saltati:]


# =============================================================================
# 3. L'UNITA' SI APPLICA AL RISULTATO
# =============================================================================

class TestUnita:

    def test_millisecondi(self, stream):
        s = stream(grain={'duration': '(20 + 80*m1)',
                          'duration_unit': 'milliseconds'})
        _e_il_ciclo(_ms(s.voices[0]))

    def test_campioni(self, stream):
        s = stream(grain={'duration': '(960 + 3840*m1)',
                          'duration_unit': 'samples'})
        assert DEFAULT_OUTPUT_SR == 48000
        _e_il_ciclo(_ms(s.voices[0]))

    def test_l_espressione_resta_quella_scritta(self, stream):
        s = stream(grain={'duration': '(20 + 80*m1)',
                          'duration_unit': 'milliseconds'})
        assert s.grain_duration.value.source == '(20 + 80*m1)'
        assert s.grain_duration.value.scale == pytest.approx(1e-3)


# =============================================================================
# 4. FUORI DAI BOUNDS: TAGLIATO E SCRITTO SUL CLIP LOG
# =============================================================================

class TestFuoriBounds:
    """Un envelope fuori bounds e' un errore al parse; un'espressione no: i
    suoi valori si conoscono solo grano per grano. Vale il clamp del
    parametro, con la sua riga sul clip log."""

    def test_sopra_il_massimo(self, stream):
        """Letto sul parametro: grani da 10 s in uno stream di 4 li toglie
        poi la clip strategy, che e' un'altra regola."""
        s = stream(grain={'duration': '(20 + 80*m1)'})
        s.map_set.advance(0, 0.0)
        with patch('pge.parameters.parameter.log_clip_warning') as log:
            assert s.grain_duration.get_value(0.0) == 10.0
        assert log.call_count == 1
        assert log.call_args.kwargs['source'] == 'EXP'
        assert log.call_args.kwargs['param_name'] == 'grain_duration'
        assert log.call_args.kwargs['raw_value'] > 20

    def test_sotto_il_minimo(self, stream):
        s = stream(grain={'duration': '(0 * m1)'}, density=5)
        with patch('pge.parameters.parameter.log_clip_warning') as log:
            grani = s.voices[0]
        assert all(g.duration == 1.0 / DEFAULT_OUTPUT_SR for g in grani)
        assert log.call_count == len(grani)

    def test_un_non_finito_va_al_limite_e_il_render_finisce(self, stream):
        s = stream(grain={'duration': '(sqrt(0 - 1) + m1)'}, density=5)
        with patch('pge.parameters.parameter.log_clip_warning') as log:
            grani = s.voices[0]
        assert grani and all(np.isfinite(g.duration) for g in grani)
        assert log.call_count == len(grani)

    def test_dentro_i_bounds_non_si_scrive_niente(self, stream):
        s = stream()
        with patch('pge.parameters.parameter.log_clip_warning') as log:
            assert s.voices[0]
        assert log.call_count == 0


# =============================================================================
# 5. LA BANDA SOPRA UN'ESPRESSIONE
# =============================================================================

class TestBandaSopraUnEspressione:

    def test_il_range_e_un_tremolio_attorno_al_valore_della_mappa(self, stream):
        """`duration_range` resta lecito: la mappa NON sostituisce il
        generatore casuale dentro la banda."""
        s = stream(grain={'duration': '(0.02 + 0.08*m1)',
                          'duration_range': 0.004},
                   density=10, deviation_probability=100)
        esatti = [0.02 + 0.08 * v for v in (0.827, 0.501, 0.875, 0.383)]
        durate = [g.duration for g in s.voices[0]]
        scarti = [min(abs(d - e) for e in esatti) for d in durate]
        assert max(scarti) <= 0.002 + 1e-4
        assert max(scarti) > 1e-4, "la banda non ha mosso niente"

    def test_sotto_ancora_min_il_tetto_non_si_controlla_al_parse(self, stream):
        """Il tetto della banda si calcola dai valori dichiarati, e di
        un'espressione al parse non si sa niente: resta il clamp."""
        s = stream(grain={'duration': '(0.02 + 0.08*m1)',
                          'duration_range': 0.5},
                   density=10, range_anchor='min')
        assert s.voices[0]


# =============================================================================
# 6. ERRORI: IL PATH YAML E LO STREAM
# =============================================================================

class TestErrori:

    @pytest.mark.parametrize('espressione, dice', [
        ('(0.02 + 0.08*m2)', 'nome sconosciuto «m2»'),
        ('(0.02 + 0.08*m1', 'manca una parentesi chiusa'),
        ('(0.02 + * m1)', 'non mi aspettavo «*»'),
        ('(clip(m1, 0))', 'clip vuole 3 argomenti'),
        ('(boh(m1))', 'funzione sconosciuta «boh»'),
        ('(m1.y)', 'nome sconosciuto «m1.y»'),
    ])
    def test_un_espressione_sbagliata_si_ferma_al_caricamento(
            self, stream, espressione, dice):
        with pytest.raises(ExpressionError) as exc:
            stream(grain={'duration': espressione})
        err = exc.value
        assert dice in err.reason
        assert err.field == 'grain.duration'
        assert err.stream_id == 's1'
        messaggio = err.user_message()
        assert "grain.duration" in messaggio
        assert "Stream:       s1" in messaggio
        assert espressione in messaggio

    def test_una_mappa_non_dichiarata_dice_quali_ci_sono(self, stream):
        with pytest.raises(ExpressionError) as exc:
            stream(grain={'duration': '(0.02 + 0.08*m2)'})
        assert 'm1' in exc.value.hint

    def test_senza_maps_il_nome_di_una_mappa_e_sconosciuto(self, stream):
        with pytest.raises(ExpressionError) as exc:
            stream(maps=None)
        assert 'nome sconosciuto «m1»' in exc.value.reason

    @pytest.mark.parametrize('espressione', [
        '0.02 + 0.08*m1', '(0.02) + (0.08*m1)', 'm1'])
    def test_un_espressione_si_scrive_fra_parentesi(self, stream, espressione):
        with pytest.raises(ExpressionError) as exc:
            stream(grain={'duration': espressione})
        assert 'fra parentesi' in exc.value.reason
        assert exc.value.field == 'grain.duration'
        assert f'({espressione})' in exc.value.hint

    @pytest.mark.parametrize('maps, campo', [
        ([], 'maps'),
        ({'m1': {'type': 'boh', 'r': 3.5}}, 'maps.m1.type'),
        ({'m1': {'type': 'logistic'}}, 'maps.m1.r'),
    ])
    def test_un_blocco_maps_sbagliato_nomina_lo_stream(self, stream, maps, campo):
        with pytest.raises(MapConfigError) as exc:
            stream(maps=maps)
        assert exc.value.field == campo
        assert exc.value.stream_id == 's1'

    def test_maps_scritta_e_lasciata_vuota_e_un_errore(self, stream):
        with pytest.raises(MapConfigError) as exc:
            stream(maps=VUOTA)
        assert exc.value.field == 'maps'

    @pytest.mark.parametrize('extra', [
        {'volume': '(-6 * m1)'},
        {'pan': '(m1)'},
        {'density': '(10 + 10*m1)'},
        {'grain': {'duration': 0.05, 'duration_range': '(0.01*m1)'}},
        {'pointer': {'speed_ratio': '(m1)'}},
    ])
    def test_altrove_un_espressione_resta_un_errore(self, stream, extra):
        """In questa fetta le espressioni valgono su `grain.duration`: gli
        altri parametri arrivano con la 5/7 (#313), coi loro test."""
        with pytest.raises(InvalidParameterError) as exc:
            stream(**extra)
        assert exc.value.stream_id == 's1'
        assert 'grain.duration' in exc.value.hint
