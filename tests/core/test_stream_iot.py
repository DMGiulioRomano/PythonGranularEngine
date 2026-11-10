"""
`grain.iot`: gli onset dalla mappa, e la densita' che emerge (issue #311,
mappe caotiche 3/7).

    maps:
      m1: {type: logistic, r: 3.5}
    grain:
      iot: (0.020 + 0.180*m1)

`onset[n+1] = onset[n] + iot`: e' il cursore per voce che c'e' gia' in
`Stream.generate_grains`, con l'attesa presa da un'espressione invece che da
`1/density`. I numeri sono quelli del plan: con `r = 3.5` le attese
percorrono 169, 110, 177, 89 ms, 7.3 grani/s in media, fra 5.6 e 11.2.

Un numero del plan e' arrotondato di troppo: «546 ms per quattro grani». Le
quattro attese sono 168.85, 110.16, 177.50 e 88.91 ms, cioe' 545.42 ms. Qui
si verifica il valore esatto, non quello scritto.
"""
from unittest.mock import patch

import numpy as np
import pytest
import soundfile as sf

from pge.core.stream import Stream
from pge.envelopes.envelope import Envelope
from pge.expressions.expression import Expression
from pge.expressions.fields import EXPRESSION_FIELDS
from pge.parameters.parameter import Parameter
from pge.shared.constants import DEFAULT_OUTPUT_SR
from pge.shared.exceptions import (
    InvalidFieldValueError,
    MissingFieldError,
    ParameterBoundError,
)

_SAMPLE = 'silenzio.wav'
MAPPA = {'m1': {'type': 'logistic', 'r': 3.5}}
ATTESE_MS = [169, 110, 177, 89]
IOT = '(0.020 + 0.180*m1)'


@pytest.fixture(scope='module')
def samples_dir(tmp_path_factory):
    cartella = tmp_path_factory.mktemp('samples')
    sf.write(str(cartella / _SAMPLE), np.zeros(48000, dtype='float32'), 48000)
    return str(cartella)


@pytest.fixture
def stream(samples_dir):
    def costruisci(grain=None, maps=MAPPA, duration=6.0, **extra):
        params = {
            'stream_id': 's1',
            'onset': 0.0,
            'duration': duration,
            'sample': _SAMPLE,
            'grain': {'envelope': 'hanning', 'duration': 0.03,
                      **({'iot': IOT} if grain is None else grain)},
        }
        if maps is not None:
            params['maps'] = maps
        params.update(extra)
        s = Stream(params, seed=1441, samples_dir=samples_dir)
        s.sample_table_num = 1
        s.window_table_map = {'hanning': 2}
        return s
    return costruisci


def _attese(grani):
    onset = [g.onset for g in grani]
    return [b - a for a, b in zip(onset, onset[1:])]


def _e_il_ciclo(valori_ms, ciclo=ATTESE_MS):
    periodo = len(ciclo)
    rotazioni = [ciclo[k:] + ciclo[:k] for k in range(periodo)]
    assert len(valori_ms) >= 2 * periodo
    assert valori_ms[:periodo] in rotazioni, valori_ms[:periodo]
    for n, valore in enumerate(valori_ms):
        assert valore == valori_ms[n % periodo]


# =============================================================================
# 1. LO YAML DELLA ISSUE
# =============================================================================

class TestGliOnsetDallaMappa:

    def test_le_attese_percorrono_il_ciclo(self, stream):
        s = stream()
        _e_il_ciclo([round(a * 1000) for a in _attese(s.voices[0])])

    def test_quattro_grani_in_545_millisecondi(self, stream):
        """La somma delle quattro attese del ciclo, calcolata dalla mappa:
        545.42 ms (il plan scrive 546)."""
        x = 0.3
        for _ in range(300):
            x = 3.5 * x * (1 - x)
        ciclo = 0.0
        for _ in range(4):
            x = 3.5 * x * (1 - x)
            ciclo += 0.020 + 0.180 * x
        assert ciclo == pytest.approx(0.54542, abs=1e-5)

        onset = [g.onset for g in stream().voices[0]]
        assert onset[4] - onset[0] == pytest.approx(ciclo, abs=1e-9)
        assert onset[8] - onset[4] == pytest.approx(ciclo, abs=1e-9)

    def test_la_densita_media_e_7_3_grani_al_secondo(self, stream):
        s = stream(duration=60.0)
        assert len(s.voices[0]) / 60.0 == pytest.approx(7.3, abs=0.05)

    def test_il_parametro_e_un_espressione(self, stream):
        s = stream()
        assert isinstance(s.iot, Parameter)
        assert isinstance(s.iot.value, Expression)
        assert s.iot.value.source == IOT
        assert 'grain.iot' in EXPRESSION_FIELDS

    def test_la_mappa_decide_l_attesa_e_l_attesa_il_passo_dopo(self, stream):
        """L'anello chiuso del plan: a densita' doppia la stessa sequenza
        scorre in meta' tempo. Con le attese dimezzate i grani sono il
        doppio, e le attese percorrono lo stesso ciclo, dimezzato."""
        intera = stream()
        meta = stream(grain={'iot': '(0.010 + 0.090*m1)'})
        assert len(meta.voices[0]) == pytest.approx(
            2 * len(intera.voices[0]), abs=2)
        for a, b in zip(_attese(intera.voices[0]), _attese(meta.voices[0])):
            assert b == pytest.approx(a / 2)


# =============================================================================
# 2. LA STESSA MAPPA SU ATTESA E DURATA
# =============================================================================

class TestStessaMappaSuIotEDurata:

    def test_ogni_grano_porta_il_valore_che_ha_deciso_la_sua_attesa(self, stream):
        s = stream(grain={'iot': IOT, 'duration': '(0.020 + 0.080*m1)'})
        grani = s.voices[0]
        for grano, attesa in zip(grani, _attese(grani)):
            mappa = (grano.duration - 0.020) / 0.080
            assert attesa == pytest.approx(0.020 + 0.180 * mappa, abs=1e-9)

    def test_le_durate_percorrono_il_loro_ciclo_in_fase_con_le_attese(self, stream):
        s = stream(grain={'iot': IOT, 'duration': '(0.020 + 0.080*m1)'})
        grani = s.voices[0]
        coppie = {(round(g.duration * 1000), round(a * 1000))
                  for g, a in zip(grani, _attese(grani))}
        assert coppie == {(86, 169), (60, 110), (90, 177), (51, 89)}


# =============================================================================
# 3. UNITA'
# =============================================================================

class TestUnita:

    def test_millisecondi_su_un_espressione(self, stream):
        s = stream(grain={'iot': '(20 + 180*m1)', 'duration': 30,
                          'duration_unit': 'milliseconds'})
        _e_il_ciclo([round(a * 1000) for a in _attese(s.voices[0])])
        assert s.iot.value.scale == pytest.approx(1e-3)

    def test_campioni_su_un_espressione(self, stream):
        s = stream(grain={'iot': '(960 + 8640*m1)', 'duration': 1440,
                          'duration_unit': 'samples'})
        _e_il_ciclo([round(a * 1000) for a in _attese(s.voices[0])])

    def test_millisecondi_su_un_numero(self, stream):
        s = stream(grain={'iot': 100, 'duration': 30,
                          'duration_unit': 'milliseconds'}, maps=None)
        assert _attese(s.voices[0])[:5] == pytest.approx([0.1] * 5)

    def test_campioni_su_un_envelope(self, stream):
        s = stream(grain={'iot': [[0, 4800], [6, 9600]], 'duration': 1440,
                          'duration_unit': 'samples'}, maps=None)
        attese = _attese(s.voices[0])
        assert attese[0] == pytest.approx(0.1)
        assert attese[-1] > 0.15

    def test_il_dizionario_dello_yaml_non_viene_toccato(self, stream, samples_dir):
        """Il fingerprint della cache legge i dati grezzi."""
        grain = {'iot': 100, 'duration': 30, 'duration_unit': 'milliseconds',
                 'envelope': 'hanning'}
        params = {'stream_id': 's1', 'sample': _SAMPLE, 'duration': 2.0,
                  'grain': grain}
        Stream(params, seed=1, samples_dir=samples_dir)
        assert grain['iot'] == 100 and grain['duration'] == 30


# =============================================================================
# 4. UN'ATTESA CHE NON AVANZA NON BLOCCA IL RENDER
# =============================================================================

class TestUnAttesaImpossibile:
    """Il giro dei grani deve avanzare: un'attesa nulla, negativa o non
    finita sarebbe un render che non finisce. Viene tagliata al limite e
    scritta sul clip log."""

    @pytest.mark.parametrize('iot', [
        '(0 * m1)',              # nulla
        '(m1 - 5)',              # negativa
        '(sqrt(m1 - 5))',        # NaN
        '(0 - 1 / (0 * m1))',    # -infinito
    ])
    def test_tagliata_a_un_campione(self, stream, iot):
        # Grani da un campione: la clip strategy toglie quelli che sforano
        # la fine dello stream, e qui si contano gli onset.
        durata = 0.005
        s = stream(grain={'iot': iot, 'duration': 1.0 / DEFAULT_OUTPUT_SR},
                   duration=durata)
        with patch('pge.parameters.parameter.log_clip_warning') as clip:
            grani = s.voices[0]
        assert len(grani) == pytest.approx(durata * DEFAULT_OUTPUT_SR, abs=2)
        assert _attese(grani)[0] == pytest.approx(1.0 / DEFAULT_OUTPUT_SR)
        assert clip.call_count >= len(grani)
        assert clip.call_args.kwargs['param_name'] == 'grain_iot'
        assert clip.call_args.kwargs['source'] == 'EXP'

    def test_un_attesa_infinita_va_al_tetto(self, stream):
        s = stream(grain={'iot': '(1 / (0 * m1))'}, duration=2.0)
        with patch('pge.parameters.parameter.log_clip_warning') as clip:
            grani = s.voices[0]
        assert len(grani) == 1          # il secondo sarebbe dopo 100 secondi
        assert clip.call_count == 1

    def test_un_numero_fuori_limite_resta_un_errore_al_parse(self, stream):
        with pytest.raises(ParameterBoundError) as exc:
            stream(grain={'iot': 0}, maps=None)
        assert exc.value.stream_id == 's1'

    def test_sopra_la_soglia_density_high_continua_a_uscire(self, stream):
        """Un'attesa di 0.1 ms sono 10000 grani/s."""
        s = stream(grain={'iot': 0.0001, 'duration': 0.0001}, maps=None,
                   duration=0.05)
        with patch('pge.controllers.density_controller'
                   '.log_high_density_warning') as log:
            assert len(s.voices[0]) == pytest.approx(500, abs=2)
        assert log.call_count == 1
        assert log.call_args.kwargs['mode'] == 'iot'
        assert log.call_args.kwargs['stream_id'] == 's1'


# =============================================================================
# 5. INSIEME AD ALTRE CHIAVI DI DENSITA': UN ERRORE
# =============================================================================

class TestInsiemeEUnErrore:

    @pytest.mark.parametrize('chiave, valore', [
        ('density', 20), ('fill_factor', 2), ('distribution', 0.5)])
    def test_grain_iot_con_density_fill_factor_o_distribution(
            self, stream, chiave, valore):
        with pytest.raises(InvalidFieldValueError) as exc:
            stream(**{chiave: valore})
        assert exc.value.field == 'grain.iot'
        assert chiave in exc.value.hint
        assert exc.value.stream_id == 's1'

    def test_grain_iot_vuota(self, stream):
        with pytest.raises(MissingFieldError) as exc:
            stream(grain={'iot': None})
        assert exc.value.fields == ['grain.iot']
        assert exc.value.stream_id == 's1'

    def test_senza_grain_iot_il_default_resta_fill_factor_due(self, stream):
        s = stream(grain={'duration': 0.05}, maps=None, duration=2.0)
        assert s.iot is None
        assert s.density_mode == 'fill_factor'
        assert _attese(s.voices[0])[0] == pytest.approx(0.025)


# =============================================================================
# 6. NUMERO ED ENVELOPE
# =============================================================================

class TestNumeroEdEnvelope:

    def test_un_numero_e_un_metronomo(self, stream):
        s = stream(grain={'iot': 0.1}, maps=None)
        assert [g.onset for g in s.voices[0]][:5] == pytest.approx(
            [0.0, 0.1, 0.2, 0.3, 0.4])

    def test_un_envelope_e_un_accelerando(self, stream):
        s = stream(grain={'iot': [[0, 0.2], [6, 0.05]]}, maps=None)
        attese = _attese(s.voices[0])
        assert attese[0] == pytest.approx(0.2)
        assert attese == sorted(attese, reverse=True)

    def test_un_envelope_non_legge_il_tempo_a_caso(self, stream):
        """Nessuna distribuzione sopra: due render danno gli stessi onset."""
        a = stream(grain={'iot': [[0, 0.2], [6, 0.05]]}, maps=None)
        b = stream(grain={'iot': [[0, 0.2], [6, 0.05]]}, maps=None)
        assert [g.onset for g in a.voices[0]] == [g.onset for g in b.voices[0]]


# =============================================================================
# 7. PIU' VOCI E SCATTER
# =============================================================================

class TestPiuVociEScatter:
    """La formula e' quella di oggi: l'attesa di una voce oltre la prima e'
    `(1 - scatter) * attesa della voce 0 + scatter * attesa letta sulla
    propria mappa`."""

    def test_a_scatter_zero_le_voci_seguono_la_voce_zero(self, stream):
        s = stream(voices={'num_voices': 3})
        onset = [[g.onset for g in voce] for voce in s.voices]
        assert onset[0] == onset[1] == onset[2]

    def test_con_clock_grain_le_mappe_delle_voci_sono_identiche(self, stream):
        """Ogni voce ha la sua mappa, ma partono tutte da `x0` e sono
        deterministiche: danno la stessa sequenza, e `scatter` — una media
        fra due attese uguali — non sposta niente. E' un fatto misurato, non
        una promessa: differenziare le voci e' un'altra decisione."""
        s = stream(voices={'num_voices': 3, 'scatter': 1.0})
        onset = [[g.onset for g in voce] for voce in s.voices]
        assert onset[0] == pytest.approx(onset[1])
        assert onset[0] == pytest.approx(onset[2])
        for voce in s.voices:
            _e_il_ciclo([round(a * 1000) for a in _attese(voce)])

    def test_la_formula_si_vede_quando_le_attese_differiscono(self, stream):
        """Con un clock a orologio l'attesa dipende dall'istante: se le voci
        partono sfalsate (scatter su un'attesa che dipende da `t`), ognuna
        legge la sua. Qui basta `t`: la voce 0 e le altre restano allineate
        perche' leggono allo stesso istante, cioe' la formula non introduce
        divergenze da sola."""
        s = stream(grain={'iot': '(0.05 + 0.01*t)'}, maps=None,
                   voices={'num_voices': 2, 'scatter': 0.5})
        assert ([g.onset for g in s.voices[0]]
                == pytest.approx([g.onset for g in s.voices[1]]))


# =============================================================================
# 8. COSA LEGGE CHI LEGGE LA DENSITA'
# =============================================================================

class TestLetture:

    def test_density_fill_factor_e_distribution_non_ci_sono(self, stream):
        s = stream()
        assert s.density is None
        assert s.fill_factor is None
        assert s.distribution is None

    def test_il_modo_e_iot(self, stream):
        s = stream()
        assert s.density_mode == 'iot'
        assert 'mode=iot' in repr(s)

    def test_il_modo_degli_altri_stream_e_quello_di_prima(self, stream):
        assert stream(grain={'duration': 0.05}, maps=None,
                      density=10).density_mode == 'density'
        assert 'mode=fill_factor' in repr(
            stream(grain={'duration': 0.05}, maps=None))

    def test_il_repr_non_genera_i_grani(self, stream):
        s = stream()
        repr(s)
        assert s.generated is False


class TestLaDensitaCheEmerge:

    def test_e_pubblicata_come_curva(self, stream):
        s = stream()
        curva = s.effective_density_curve
        assert isinstance(curva, Envelope)

    def test_va_da_5_6_a_11_2_grani_al_secondo(self, stream):
        """Le quattro attese del ciclo, invertite."""
        curva = stream().effective_density_curve
        valori = sorted({round(y, 1) for _, y in curva.breakpoints})
        assert valori == [5.6, 5.9, 9.1, 11.2]

    def test_e_l_inverso_dell_attesa_di_ogni_grano_tenuto_fino_al_dopo(self, stream):
        s = stream()
        curva = s.effective_density_curve
        grani = s.voices[0]
        for grano, attesa in list(zip(grani, _attese(grani)))[:20]:
            assert curva.evaluate(grano.onset) == pytest.approx(1 / attesa)
            assert curva.evaluate(grano.onset + attesa / 2) == pytest.approx(
                1 / attesa)

    def test_leggerla_genera_i_grani(self, stream):
        """Non e' una funzione del tempo: si conosce solo a grani fatti."""
        s = stream()
        assert s.generated is False
        s.effective_density_curve
        assert s.generated is True

    def test_con_un_numero_e_una_costante(self, stream):
        curva = stream(grain={'iot': 0.1}, maps=None).effective_density_curve
        assert {round(y, 6) for _, y in curva.breakpoints} == {10.0}

    def test_negli_altri_modi_resta_quella_di_prima(self, stream):
        assert stream(grain={'duration': 0.05}, maps=None,
                      density=10).effective_density_curve is None
        fill = stream(grain={'duration': 0.05}, maps=None, fill_factor=2)
        assert fill.effective_density_curve.evaluate(1.0) == pytest.approx(40.0)
        assert fill.generated is False
