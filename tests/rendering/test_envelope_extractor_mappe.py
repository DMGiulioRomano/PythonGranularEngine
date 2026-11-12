"""
Le curve di uno stream con le mappe (issue #314, mappe caotiche 6/7).

Un parametro scritto come espressione non ha una curva nota in anticipo: i
suoi valori esistono solo nei grani generati. Chi legge le curve — la
partitura, la sessione Sonic Visualiser — li riceve come **valori
realizzati**: il valore che il parametro ha dato a ogni grano della voce 0,
tenuto fino al grano dopo. Accanto, il valore della mappa (`map__m1`) e la
densita' emersa.

Il riconoscimento dell'espressione sta in `ParameterCurve`, e in nessun
altro posto: lo dice un test sull'AST di chi le curve le legge.
"""
import ast
import inspect

import numpy as np
import pytest
import soundfile as sf

from pge.core.stream import Stream
from pge.export import sv_exporter
from pge.rendering import envelope_extractor, score_visualizer
from pge.rendering.envelope_extractor import (
    ENVELOPE_COLORS, ENVELOPE_STYLES, PLOT_ENVELOPE_KEYS, base_param_name,
    get_stream_envelopes)

_SAMPLE = 'due_secondi.wav'
MAPPA = {'m1': {'type': 'logistic', 'r': 3.5}}


@pytest.fixture(scope='module')
def samples_dir(tmp_path_factory):
    cartella = tmp_path_factory.mktemp('samples')
    sf.write(str(cartella / _SAMPLE), np.zeros(96000, dtype='float32'), 48000)
    return str(cartella)


@pytest.fixture
def stream(samples_dir):
    def costruisci(maps=MAPPA, duration=2.0, onset=0.0, **extra):
        params = {
            'stream_id': 's1', 'onset': onset, 'duration': duration,
            'sample': _SAMPLE, 'density': 25,
            'grain': {'envelope': 'hanning', 'duration': 0.02},
        }
        if maps is not None:
            params['maps'] = maps
        for chiave, valore in extra.items():
            if chiave == 'grain':
                params['grain'] = {**params['grain'], **valore}
            elif valore is None:
                params.pop(chiave, None)
            else:
                params[chiave] = valore
        s = Stream(params, seed=1441, samples_dir=samples_dir)
        s.sample_table_num = 1
        s.window_table_map = {'hanning': 2}
        return s
    return costruisci


def _punti(curva):
    return [list(bp) for bp in curva.breakpoints]


# =============================================================================
# 1. I VALORI REALIZZATI DI UN PARAMETRO A ESPRESSIONE
# =============================================================================

class TestIValoriRealizzati:

    @pytest.mark.parametrize('chiave, extra, dal_grano', [
        ('grain_duration', {'grain': {'duration': '(0.01 + 0.02*m1)'}},
         lambda g: g.duration),
        ('volume', {'volume': '(-30 + 20*m1)'}, lambda g: g.volume),
        ('pan', {'pan': '(90*m1)'}, lambda g: g.pan),
        ('pitch', {'pitch': {'semitones': '(12*m1)'}},
         lambda g: 12 * np.log2(g.pitch_ratio)),
        ('pitch', {'pitch': {'ratio': '(1 + m1)'}}, lambda g: g.pitch_ratio),
        ('pointer_position', {'pointer': {'position': '(m1)'}},
         lambda g: g.pointer_pos / 2.0),
    ])
    def test_sono_i_valori_dei_grani_della_voce_zero(self, stream, chiave,
                                                      extra, dal_grano):
        s = stream(**extra)
        curve = get_stream_envelopes(s)
        assert chiave in curve
        grani = s.voices[0]
        punti = _punti(curve[chiave])
        assert len(punti) == len(grani) > 20
        for (t, v), g in zip(punti, grani):
            assert t == pytest.approx(g.onset)
            assert v == pytest.approx(dal_grano(g), abs=1e-9)

    def test_e_una_curva_a_gradini(self, stream):
        """Il valore di un grano resta fino al grano dopo: fra due grani non
        c'e' niente da interpolare."""
        s = stream(volume='(-30 + 20*m1)')
        curva = get_stream_envelopes(s)['volume']
        assert curva.type == 'step'
        (t0, v0), (t1, v1) = curva.breakpoints[0], curva.breakpoints[1]
        assert curva.evaluate(0.5 * (t0 + t1)) == pytest.approx(v0)
        assert curva.evaluate(t1) == pytest.approx(v1)

    def test_dice_di_essere_realizzata_e_la_sua_escursione(self, stream):
        s = stream(grain={'duration': '(0.02 + 0.08*m1)'}, density=8)
        curva = get_stream_envelopes(s)['grain_duration']
        assert curva.realized is True
        basso, alto = curva.excursion
        assert round(basso * 1000) == 51 and round(alto * 1000) == 90

    def test_una_curva_dichiarata_non_e_realizzata(self, stream):
        s = stream(volume=[[0, -12], [2, -3]])
        assert not getattr(get_stream_envelopes(s)['volume'], 'realized',
                           False)

    def test_i_tempi_sono_relativi_allo_stream(self, stream):
        """Come ogni altra curva: l'onset globale lo somma chi disegna."""
        s = stream(onset=3.0, volume='(-30 + 20*m1)')
        curva = get_stream_envelopes(s)['volume']
        assert curva.breakpoints[0][0] == 0.0
        assert s.voices[0][0].onset == 3.0

    def test_la_voce_e_la_zero(self, stream):
        """Con piu' voci la curva e' quella della voce di riferimento, come
        la densita' effettiva."""
        s = stream(volume='(-30 + 20*m1)', distribution=0.6,
                   voices={'num_voices': 3, 'scatter': 1.0})
        punti = _punti(get_stream_envelopes(s)['volume'])
        assert [v for _, v in punti] == pytest.approx(
            [g.volume for g in s.voices[0]])

    def test_con_la_banda_sopra_e_il_valore_che_il_grano_ha_avuto(
            self, stream):
        s = stream(pan='(90*m1)', pan_range=20,
                   deviation_probability={'pan': 100})
        punti = _punti(get_stream_envelopes(s)['pan'])
        assert [v for _, v in punti] == pytest.approx(
            [g.pan for g in s.voices[0]])

    def test_un_valore_tagliato_si_vede_tagliato(self, stream):
        s = stream(volume='(100*m1)')
        curve = get_stream_envelopes(s, show_static=True)
        assert {v for _, v in curve['volume'].breakpoints} == {12.0}

    def test_un_espressione_che_da_un_valore_solo_e_una_costante(
            self, stream):
        """Come un envelope coi breakpoint tutti uguali: si mostra solo con
        `show_static`."""
        s = stream(volume='(-6 + 0*m1)')
        assert 'volume' not in get_stream_envelopes(s)
        assert 'volume' in get_stream_envelopes(s, show_static=True)

    def test_i_grani_tolti_in_coda_non_lasciano_un_valore(self, stream):
        """La clip strategy toglie i grani che sforano la fine dello
        stream: la curva ha un punto per ogni grano che c'e'."""
        s = stream(grain={'duration': '(0.2 + 0.5*m1)'}, density=6)
        curva = get_stream_envelopes(s)['grain_duration']
        grani = s.voices[0]
        # 12 onset in 2 secondi, ma i grani lunghi nati in fondo sforano
        assert 0 < len(grani) < 12
        assert [v for _, v in curva.breakpoints] == pytest.approx(
            [g.duration for g in grani])
        assert len(get_stream_envelopes(s)['map__m1'].breakpoints) == \
            len(grani)

    def test_grain_iot_ha_la_sua_curva(self, stream):
        s = stream(density=None, grain={'iot': '(0.020 + 0.180*m1)'})
        curve = get_stream_envelopes(s)
        assert 'grain_iot' in curve and 'effective_density' in curve
        attese = [round(v * 1000) for _, v in curve['grain_iot'].breakpoints]
        assert set(attese) == {169, 110, 177, 89}
        onset = [g.onset for g in s.voices[0]]
        veri = [b - a for a, b in zip(onset, onset[1:])]
        assert [v for _, v in curve['grain_iot'].breakpoints][:len(veri)] \
            == pytest.approx(veri)

    def test_grain_iot_a_envelope_e_una_curva_dichiarata(self, stream):
        s = stream(maps=None, density=None,
                   grain={'iot': [[0, 0.2], [2, 0.05]]})
        curva = get_stream_envelopes(s)['grain_iot']
        assert _punti(curva) == [[0, 0.2], [2, 0.05]]

    def test_la_densita_a_espressione_e_la_sua_curva(self, stream):
        s = stream(density='(10 + 40*m1)')
        curva = get_stream_envelopes(s)['density']
        onset = [g.onset for g in s.voices[0]]
        attese = [b - a for a, b in zip(onset, onset[1:])]
        assert [1 / v for _, v in curva.breakpoints][:len(attese)] == \
            pytest.approx(attese)


# =============================================================================
# 2. LA CURVA DELLA MAPPA
# =============================================================================

class TestLaCurvaDellaMappa:

    def test_esce_come_map_doppio_trattino_nome(self, stream):
        s = stream(grain={'duration': '(0.01 + 0.02*m1)'})
        assert 'map__m1' in get_stream_envelopes(s)

    def test_clock_grain_un_gradino_per_grano(self, stream):
        s = stream(grain={'duration': '(0.01 + 0.02*m1)'})
        curva = get_stream_envelopes(s)['map__m1']
        grani = s.voices[0]
        assert curva.type == 'step'
        assert len(curva.breakpoints) == len(grani)
        for (t, m1), g in zip(curva.breakpoints, grani):
            assert t == pytest.approx(g.onset)
            assert g.duration == pytest.approx(0.01 + 0.02 * m1)
        assert {round(v, 3) for _, v in curva.breakpoints} == {
            0.383, 0.501, 0.827, 0.875}

    def test_clock_a_orologio_gradini_agli_istanti_dei_passi(self, stream):
        s = stream(maps={'m1': {'type': 'logistic', 'r': 3.5, 'clock': 5}},
                   grain={'duration': '(0.01 + 0.02*m1)'})
        curva = get_stream_envelopes(s)['map__m1']
        assert curva.type == 'step'
        tempi = [t for t, _ in curva.breakpoints]
        assert tempi == pytest.approx(s.map_set.step_times('m1', 2.0))
        assert tempi == pytest.approx([0.2 * k for k in range(10)])
        # ogni grano legge il gradino in cui cade (un soffio dopo l'onset:
        # un grano che nasce sull'istante di un passo legge gia' quel passo)
        for g in s.voices[0]:
            assert g.duration == pytest.approx(
                0.01 + 0.02 * curva.evaluate(g.onset + 1e-6))

    def test_iterate_una_curva_continua(self, stream):
        s = stream(maps={'m1': {'type': 'sine', 'r': [[0, 3.0], [2, 4.0]],
                                'iterate': 3}},
                   grain={'duration': '(0.02 + 0.005*m1)'})
        curva = get_stream_envelopes(s)['map__m1']
        assert curva.type == 'linear'
        assert len(curva.breakpoints) > 100
        assert curva.breakpoints[0][0] == 0.0
        assert curva.breakpoints[-1][0] == pytest.approx(2.0)
        # la linea passa per i valori che i grani hanno letto
        for g in s.voices[0][::5]:
            assert g.duration == pytest.approx(
                0.02 + 0.005 * curva.evaluate(g.onset), abs=2e-5)

    def test_campionare_iterate_non_scrive_sul_clip_log(self, stream):
        """Disegnare una mappa che scappa non deve raccontarlo un'altra
        volta: l'ha gia' detto chi ha generato i grani."""
        from unittest.mock import patch
        # Dodici secondi: piu' dell'intervallo del limite di frequenza
        # (5 s). Chi ha generato i grani ha scritto l'ultima riga verso la
        # fine; campionare da capo, a t = 0, ne e' lontano piu' di 5 s, e
        # senza il silenzio ne scriverebbe un'altra.
        s = stream(maps={'m1': {'type': 'logistic', 'r': 5.0, 'iterate': 9}},
                   grain={'duration': '(0.02 + 0.001*m1)'}, duration=12.0)
        with patch('pge.maps.map_set.log_map_escape_warning') as generando:
            s.voices
        assert generando.call_count >= 2
        with patch('pge.maps.map_set.log_map_escape_warning') as log:
            get_stream_envelopes(s, show_static=True)
        assert log.call_count == 0

    def test_la_seconda_variabile(self, stream):
        s = stream(maps={'m1': {'type': 'henon', 'r': 1.4}},
                   pan='(100*m1.y)')
        curve = get_stream_envelopes(s)
        assert 'map__m1' in curve and 'map__m1.y' in curve
        x = [v for _, v in curve['map__m1'].breakpoints]
        y = [v for _, v in curve['map__m1.y'].breakpoints]
        assert y[1:] == pytest.approx([0.3 * v for v in x[:-1]])
        assert [v for _, v in curve['pan'].breakpoints] == pytest.approx(
            [100 * v for v in y])

    def test_la_curva_si_costruisce_una_volta(self, stream):
        """La partitura legge le curve piu' volte per pagina: una curva con
        un punto per grano non si rifa' a ogni lettura."""
        s = stream(grain={'duration': '(0.01 + 0.02*m1)'})
        prima = get_stream_envelopes(s)
        dopo = get_stream_envelopes(s)
        assert prima['map__m1'] is dopo['map__m1']
        assert prima['grain_duration'] is dopo['grain_duration']

    def test_costruirla_non_riempie_il_log_delle_trasformazioni(self, stream):
        """Il builder scrive sul log ogni envelope che espande, punto per
        punto: serve per gli envelope scritti nello YAML, non per una curva
        con un punto per grano."""
        from unittest.mock import MagicMock, patch
        from pge.shared.logger import CLIP_LOG_CONFIG
        s = stream(grain={'duration': '(0.01 + 0.02*m1)'},
                   volume=[[0, -12], [2, -3]])
        s.voices
        registro = MagicMock()
        with patch('pge.shared.logger.get_clip_logger',
                   return_value=registro):
            curve = get_stream_envelopes(s)
        assert 'map__m1' in curve and 'grain_duration' in curve
        assert registro.info.call_count == 0
        # e l'interruttore torna com'era: un envelope scritto si logga ancora
        assert CLIP_LOG_CONFIG.get('log_transformations', True) is True

    def test_una_mappa_a_una_variabile_non_ha_la_seconda(self, stream):
        s = stream(grain={'duration': '(0.01 + 0.02*m1)'})
        assert 'map__m1.y' not in get_stream_envelopes(s, show_static=True)

    def test_ogni_mappa_dichiarata_ha_la_sua(self, stream):
        s = stream(maps={'m1': {'type': 'logistic', 'r': 3.5},
                         'm2': {'type': 'tent', 'r': 3.2, 'clock': 8}},
                   volume='(-20 + 10*m1)')
        curve = get_stream_envelopes(s)
        assert [k for k in curve if k.startswith('map__')] == [
            'map__m1', 'map__m2']

    def test_una_mappa_ferma_e_una_costante(self, stream):
        """`iterate` con `r` fermo da' un valore solo."""
        s = stream(maps={'m1': {'type': 'logistic', 'r': 3.5, 'iterate': 7}},
                   volume='(-20 + 10*m1)')
        assert 'map__m1' not in get_stream_envelopes(s)
        assert 'map__m1' in get_stream_envelopes(s, show_static=True)

    def test_uno_stream_senza_mappe_non_ne_ha(self, stream):
        s = stream(maps=None, volume=[[0, -12], [2, -3]])
        assert not [k for k in get_stream_envelopes(s, show_static=True)
                    if k.startswith('map')]


# =============================================================================
# 3. I NOMI PUBBLICATI
# =============================================================================

class TestINomi:

    def test_il_nome_base_di_una_mappa_e_map(self):
        assert base_param_name('map__m1') == 'map'
        assert base_param_name('map__m1.y') == 'map'
        assert base_param_name('map__v2') == 'map'
        # e le curve per voce restano com'erano
        assert base_param_name('voice_pitch_offset__v2') == \
            'voice_pitch_offset'
        assert base_param_name('volume') == 'volume'

    @pytest.mark.parametrize('nome', ['map', 'grain_iot'])
    def test_i_nomi_nuovi_hanno_colore_e_stile(self, nome):
        assert nome in ENVELOPE_COLORS
        assert nome in ENVELOPE_STYLES
        assert nome in PLOT_ENVELOPE_KEYS

    def test_le_coppie_bw_restano_uniche(self):
        coppie = list(ENVELOPE_STYLES.values())
        assert len(coppie) == len(set(coppie))
        assert set(ENVELOPE_STYLES) == set(ENVELOPE_COLORS)

    def test_il_filtro_map_prende_tutte_le_mappe(self, stream):
        s = stream(maps={'m1': {'type': 'henon', 'r': 1.4},
                         'm2': {'type': 'logistic', 'r': 3.5}},
                   volume='(-20 + 5*m1)', pan='(40*m2)')
        curve = get_stream_envelopes(s, envelope_filter={'map'})
        assert set(curve) == {'map__m1', 'map__m1.y', 'map__m2'}

    def test_il_filtro_sul_parametro_prende_i_suoi_valori_realizzati(
            self, stream):
        s = stream(volume='(-20 + 5*m1)', pan='(40*m1)')
        assert set(get_stream_envelopes(s, envelope_filter={'pan'})) == {
            'pan'}

    def test_l_ordine_le_mappe_dopo_i_parametri(self, stream):
        s = stream(volume='(-20 + 5*m1)',
                   voices={'num_voices': 2,
                           'pitch': {'strategy': 'step', 'step': 7}})
        chiavi = list(get_stream_envelopes(
            s, show_static=True, show_voice_offsets=True))
        assert chiavi.index('volume') < chiavi.index('map__m1')
        per_voce = [k for k in chiavi if '__v' in k]
        assert per_voce and chiavi.index('map__m1') < chiavi.index(
            per_voce[0])


# =============================================================================
# 4. CHI LEGGE NON RICONOSCE PER CONTO SUO
# =============================================================================

class TestIlRiconoscimentoStaInUnPostoSolo:
    """`ParameterCurve` ha un caso per il valore a espressione. Chi legge le
    curve chiede quello, e non guarda il tipo del valore: un secondo
    `isinstance` e' il modo in cui il terzo lettore lo dimentica."""

    @pytest.mark.parametrize('modulo', [
        envelope_extractor, sv_exporter, score_visualizer])
    def test_chi_legge_le_curve_non_nomina_expression(self, modulo):
        albero = ast.parse(inspect.getsource(modulo))
        nomi = {n.id for n in ast.walk(albero) if isinstance(n, ast.Name)}
        attributi = {n.attr for n in ast.walk(albero)
                     if isinstance(n, ast.Attribute)}
        importati = {a.name for n in ast.walk(albero)
                     if isinstance(n, (ast.Import, ast.ImportFrom))
                     for a in n.names}
        for nome in ('Expression', 'ExpressionSource', 'CompiledExpression'):
            assert nome not in nomi | attributi | importati, (
                f"{modulo.__name__} nomina {nome}: il riconoscimento sta "
                "in ParameterCurve.classify")

    def test_l_estrattore_chiede_il_caso_a_parameter_curve(self):
        sorgente = inspect.getsource(envelope_extractor)
        assert 'EXPRESSION' in sorgente
