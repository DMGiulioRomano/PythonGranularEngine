"""
Dove vale un'espressione, e dove no (issue #313, mappe caotiche 5/7).

Dopo la #308 un'espressione valeva su `grain.duration` soltanto, poi su
`grain.iot` (#311) e `pointer.position` (#312). Qui vale sul **valore base**
di ogni parametro a schema: `volume`, `pan`, il `pitch` in ogni unita',
`density`, `fill_factor`, `distribution`, `grain.read_direction`. Dove non
vale il motore lo dice, col path YAML e un suggerimento.

Tutto dall'interfaccia dello Stream: un valore si misura sui grani.
"""
from unittest.mock import patch

import numpy as np
import pytest
import soundfile as sf

from pge.core.stream import Stream
from pge.expressions.expression import Expression
from pge.expressions.fields import EXPRESSION_FIELDS, EXPRESSION_REFUSALS
from pge.parameters.parameter import EXPRESSION_CLIP_LOG_INTERVAL
from pge.parameters.parameter_definitions import (
    GRANULAR_PARAMETERS, NAN_TO_MAX_PARAMETERS)
from pge.parameters.pitch_unit import PITCH_UNIT_PRESETS
from pge.shared.exceptions import ConfigError, ExpressionError

_SAMPLE = 'due_secondi.wav'
MAPPA = {'m1': {'type': 'logistic', 'r': 3.5}}
CICLO = [0.827, 0.501, 0.875, 0.383]


@pytest.fixture(scope='module')
def samples_dir(tmp_path_factory):
    cartella = tmp_path_factory.mktemp('samples')
    sf.write(str(cartella / _SAMPLE), np.zeros(96000, dtype='float32'), 48000)
    return str(cartella)


@pytest.fixture
def stream(samples_dir):
    def costruisci(maps=MAPPA, duration=2.0, **extra):
        params = {
            'stream_id': 's1', 'onset': 0.0, 'duration': duration,
            'sample': _SAMPLE, 'density': 25,
            'grain': {'envelope': 'hanning', 'duration': 0.05},
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


def _m1(valori, da_valore, cifre=3):
    """I valori di `m1` ricavati da quelli letti sui grani: devono essere
    il ciclo della logistica a r = 3.5, a meno di rotazione."""
    letti = [round(da_valore(v), cifre) for v in valori]
    rotazioni = [CICLO[k:] + CICLO[:k] for k in range(4)]
    assert len(letti) >= 8
    assert letti[:4] in rotazioni, letti[:4]
    for n, valore in enumerate(letti):
        assert valore == letti[n % 4]


# =============================================================================
# 1. L'ELENCO
# =============================================================================

class TestLElenco:

    def test_i_campi(self):
        assert set(EXPRESSION_FIELDS) == {
            'volume', 'pan',
            'grain.duration', 'grain.iot', 'grain.read_direction',
            'pointer.position',
            'pitch.semitones', 'pitch.cents', 'pitch.quarter_tone',
            'pitch.eighth_tone', 'pitch.ratio', 'pitch.value',
            'density', 'fill_factor', 'distribution',
        }
        assert len(EXPRESSION_FIELDS) == len(set(EXPRESSION_FIELDS))

    def test_ogni_unita_di_pitch_c_e(self):
        """Un'unita' nuova in `PITCH_UNIT_PRESETS` senza la sua voce qui
        sarebbe un campo dove l'espressione vale e l'elenco non lo dice."""
        for unita in PITCH_UNIT_PRESETS:
            assert f'pitch.{unita}' in EXPRESSION_FIELDS
        assert 'pitch.value' in EXPRESSION_FIELDS      # edo: N + value: X

    def test_i_rifiuti(self):
        assert set(EXPRESSION_REFUSALS) == {
            'pointer.speed_ratio', 'pointer.start',
            'pointer.loop_start', 'pointer.loop_end', 'pointer.loop_dur',
            'voices.num_voices',
        }
        assert not set(EXPRESSION_REFUSALS) & set(EXPRESSION_FIELDS)
        assert all(isinstance(s, str) and s for s in
                   EXPRESSION_REFUSALS.values())

    def test_i_due_elenchi_si_leggono_dal_sorgente(self):
        """Letterali in un modulo che non importa niente: un editor li
        legge dall'AST."""
        import ast
        import inspect
        from pge.expressions import fields
        albero = ast.parse(inspect.getsource(fields))
        assert not [n for n in ast.walk(albero)
                    if isinstance(n, (ast.Import, ast.ImportFrom))]
        letti = {t.id: ast.literal_eval(n.value) for n in albero.body
                 if isinstance(n, ast.Assign) for t in n.targets}
        assert letti['EXPRESSION_FIELDS'] == EXPRESSION_FIELDS
        assert letti['EXPRESSION_REFUSALS'] == EXPRESSION_REFUSALS


# =============================================================================
# 2. DOVE VALE
# =============================================================================

class TestDoveVale:

    def test_volume(self, stream):
        s = stream(volume='(-30 + 20*m1)')
        assert isinstance(s.volume.value, Expression)
        _m1([g.volume for g in s.voices[0]], lambda v: (v + 30) / 20)

    def test_pan(self, stream):
        s = stream(pan='(90*m1)')
        _m1([g.pan for g in s.voices[0]], lambda v: v / 90)

    @pytest.mark.parametrize('pitch, in_ottave', [
        ({'semitones': '(12*m1)'}, 1.0),
        ({'cents': '(1200*m1)'}, 1.0),
        ({'quarter_tone': '(24*m1)'}, 1.0),
        ({'eighth_tone': '(48*m1)'}, 1.0),
        ({'edo': 19, 'value': '(19*m1)'}, 1.0),
        ({'edo': 31, 'value': '(62*m1)'}, 2.0),
    ])
    def test_pitch_in_ogni_unita(self, stream, pitch, in_ottave):
        """Ogni unita' porta il suo valore a un ratio: qui l'espressione
        copre `in_ottave` ottave, e il ratio e' 2**(ottave * m1)."""
        s = stream(pitch=pitch)
        _m1([g.pitch_ratio for g in s.voices[0]],
            lambda v: np.log2(v) / in_ottave)

    def test_pitch_ratio(self, stream):
        s = stream(pitch={'ratio': '(1 + m1)'})
        _m1([g.pitch_ratio for g in s.voices[0]], lambda v: v - 1)

    def test_density(self, stream):
        s = stream(density='(10 + 40*m1)')
        onset = [g.onset for g in s.voices[0]]
        attese = [b - a for a, b in zip(onset, onset[1:])]
        _m1(attese, lambda v: (1 / v - 10) / 40)

    def test_fill_factor(self, stream):
        """densita' = fill_factor / durata, con la durata a 50 ms."""
        s = stream(density=None, fill_factor='(1 + 3*m1)')
        onset = [g.onset for g in s.voices[0]]
        attese = [b - a for a, b in zip(onset, onset[1:])]
        _m1(attese, lambda v: (0.05 / v - 1) / 3)

    def test_distribution(self, stream):
        """0 = metronomo, 1 = attese sparse: letta dalla mappa cambia a
        ogni grano. Qui basta che si legga e che lo stream renda."""
        s = stream(distribution='(m1)')
        assert isinstance(s._density.distribution_param.value, Expression)
        onset = [g.onset for g in s.voices[0]]
        attese = {round(b - a, 6) for a, b in zip(onset, onset[1:])}
        assert len(attese) > 10

    def test_read_direction(self, stream):
        """Il segno decide il verso: sotto zero indietro. Con il ciclo
        0.827, 0.501, 0.875, 0.383 e la soglia a 0.6 i grani si alternano."""
        s = stream(grain={'read_direction': '(m1 - 0.6)'})
        versi = [g.pitch_ratio > 0 for g in s.voices[0]]
        assert len(versi) > 8
        assert all(a != b for a, b in zip(versi, versi[1:]))

    def test_read_direction_a_zero_e_avanti(self, stream):
        s = stream(grain={'read_direction': '(0*m1)'})
        assert all(g.pitch_ratio > 0 for g in s.voices[0])

    @pytest.mark.parametrize('campo', sorted(EXPRESSION_FIELDS))
    def test_ogni_campo_dell_elenco_accetta_un_espressione(self, stream,
                                                           campo):
        """Il test che tiene insieme l'elenco e il motore: un campo
        nell'elenco che il motore rifiuta, qui e' rosso."""
        blocco, _, chiave = campo.rpartition('.')
        valore = '(0.5*m1 + 0.2)'
        extra = {}
        if campo == 'pitch.value':
            extra['pitch'] = {'edo': 12, 'value': valore}
        elif blocco == 'pitch':
            extra['pitch'] = {chiave: valore}
        elif blocco:
            extra[blocco] = {chiave: valore}
        else:
            extra[chiave] = valore
        if campo in ('grain.iot', 'fill_factor'):
            extra['density'] = None
        s = stream(**extra)
        assert len(s.voices[0]) > 0


class TestIlTempo:

    def test_un_espressione_senza_mappe(self, stream):
        s = stream(maps=None, volume='(-6 - 3*t)')
        for g in s.voices[0]:
            assert g.volume == pytest.approx(-6 - 3 * g.onset)

    def test_le_funzioni_del_linguaggio(self, stream):
        s = stream(pan='(fold(200*m1, -45, 45))')
        assert all(-45 <= g.pan <= 45 for g in s.voices[0])
        assert len({round(g.pan, 3) for g in s.voices[0]}) == 4

    def test_la_seconda_variabile(self, stream):
        s = stream(maps={'m1': {'type': 'henon', 'r': 1.4}},
                   volume='(-20 + 5*m1)', pan='(100*m1.y)')
        grani = s.voices[0]
        for a, b in zip(grani, grani[1:]):
            # y e' 0.3 volte l'x di un passo prima
            assert b.pan == pytest.approx(30 * (a.volume + 20) / 5)


# =============================================================================
# 3. I VALORI FUORI DAI LIMITI
# =============================================================================

class TestFuoriDaiLimiti:

    def test_si_taglia_e_si_scrive_sul_clip_log(self, stream):
        with patch('pge.parameters.parameter.log_clip_warning') as clip:
            s = stream(volume='(100*m1)')
            volumi = {g.volume for g in s.voices[0]}
        assert volumi == {12.0}
        assert clip.call_count >= 1
        riga = clip.call_args_list[0].kwargs
        assert riga['param_name'] == 'volume'
        assert riga['source'] == 'EXP'
        assert riga['clipped_value'] == 12.0

    def test_non_e_un_errore_al_caricamento(self, stream):
        stream(volume='(1000)', maps=None) if False else stream(
            volume='(1000 + 0*m1)')

    def test_la_banda_resta_sopra_l_espressione(self, stream):
        """`_range` sopra un'espressione e' un tremolio attorno al valore
        dato dalla mappa."""
        s = stream(pan='(90*m1)', pan_range=10,
                   deviation_probability={'pan': 100})
        centri = [90 * c for c in CICLO]
        for g in s.voices[0]:
            assert min(abs(g.pan - c) for c in centri) <= 5 + 0.5
        assert len({round(g.pan, 4) for g in s.voices[0]}) > 4


class TestUnNanVaAlPavimento:
    """Un valore non finito non ha un lato: la regola lo manda al limite
    inferiore del parametro. Sul volume e' silenzio."""

    @pytest.mark.parametrize('campo, letto, parametro', [
        ('volume', lambda g: g.volume, 'volume'),
        ('pan', lambda g: g.pan, 'pan'),
    ])
    def test_al_minimo_del_parametro(self, stream, campo, letto, parametro):
        s = stream(**{campo: '(sqrt(0 - 1) + m1)'})
        minimo = GRANULAR_PARAMETERS[parametro].min_val
        assert {letto(g) for g in s.voices[0]} == {minimo}

    def test_la_durata_va_a_un_campione(self, stream):
        s = stream(grain={'duration': '(sqrt(0 - 1))'})
        durate = {g.duration for g in s.voices[0]}
        assert len(durate) == 1
        assert durate.pop() == pytest.approx(1 / 48000)

    def test_il_pitch_va_al_minimo_dell_unita(self, stream):
        s = stream(pitch={'semitones': '(sqrt(0 - 1))'})
        ratio, = {round(g.pitch_ratio, 9) for g in s.voices[0]}
        assert ratio == pytest.approx(2 ** (-36 / 12))

    def test_gli_infiniti_vanno_dal_loro_lato(self, stream):
        su = stream(volume='(1/0 + m1)')
        giu = stream(volume='(0 - 1/0 + m1)')
        assert {g.volume for g in su.voices[0]} == {12.0}
        assert {g.volume for g in giu.voices[0]} == {-120.0}


class TestSuGrainIotUnNanVaAlTetto:
    """L'eccezione: al pavimento un'attesa e' un campione, cioe' 48000
    grani al secondo. Un `nan` su `grain.iot` va al tetto, 100 s: il render
    finisce subito, col solo primo grano."""

    def test_l_elenco_dell_eccezione(self):
        assert NAN_TO_MAX_PARAMETERS == ('grain_iot',)

    def test_un_grano_solo(self, stream):
        s = stream(density=None, grain={'iot': '(sqrt(0 - 1))'})
        assert len(s.voices[0]) == 1

    def test_lo_scrive_sul_clip_log(self, stream):
        with patch('pge.parameters.parameter.log_clip_warning') as clip:
            s = stream(density=None, grain={'iot': '(sqrt(0 - 1))'})
            s.voices
        assert clip.call_count == 1
        assert clip.call_args.kwargs['clipped_value'] == 100.0

    def test_un_attesa_negativa_resta_al_pavimento(self, stream):
        """Un numero sotto il minimo un lato ce l'ha: si taglia al minimo,
        come ogni altro valore fuori limite."""
        with patch('pge.parameters.parameter.log_clip_warning'):
            s = stream(density=None, duration=0.1,
                       grain={'iot': '(0 - 1)', 'duration': 0.001})
            onset = [g.onset for g in s.voices[0]]
        assert len(onset) > 1000
        assert onset[1] - onset[0] == pytest.approx(1 / 48000)


# =============================================================================
# 4. IL LIMITE DEL CLIP LOG
# =============================================================================

class TestIlClipLogDiUnEspressioneHaUnLimite:
    """Una riga per grano tagliato, su un'espressione sempre fuori limite,
    sono decine di migliaia di righe. Una riga subito, poi una ogni 5 s di
    stream, col conto dei tagli taciuti."""

    def test_una_riga_ogni_cinque_secondi(self, stream):
        assert EXPRESSION_CLIP_LOG_INTERVAL == 5.0
        with patch('pge.parameters.parameter.log_clip_warning') as clip:
            s = stream(duration=12.0, volume='(100 + m1)')
            grani = s.voices[0]
        assert len(grani) > 250
        assert clip.call_count == 3
        tempi = [c.kwargs['time'] for c in clip.call_args_list]
        assert tempi[0] == 0.0
        assert all(b - a >= 5.0 - 1e-9 for a, b in zip(tempi, tempi[1:]))

    def test_la_riga_dice_quanti_ne_ha_taciuti(self, stream):
        with patch('pge.parameters.parameter.log_clip_warning') as clip:
            s = stream(duration=12.0, volume='(100 + m1)')
            grani = s.voices[0]
        taciuti = [c.kwargs['suppressed'] for c in clip.call_args_list]
        assert taciuti[0] == 0
        assert taciuti[1] > 100 and taciuti[2] > 100
        # ogni taglio e' o scritto o contato
        assert sum(taciuti) + 3 <= len(grani)

    def test_ogni_parametro_ha_il_suo_conto(self, stream):
        with patch('pge.parameters.parameter.log_clip_warning') as clip:
            s = stream(duration=4.0, volume='(100 + m1)',
                       pan='(100000 + m1)')
            s.voices
        nomi = [c.kwargs['param_name'] for c in clip.call_args_list]
        assert nomi.count('volume') == 1 and nomi.count('pan') == 1

    def test_con_piu_voci_il_limite_resta_sul_tempo(self, stream):
        with patch('pge.parameters.parameter.log_clip_warning') as clip:
            s = stream(duration=4.0, volume='(100 + m1)',
                       voices={'num_voices': 3, 'scatter': 1.0},
                       distribution=0.5)
            s.voices
        assert clip.call_count == 1

    def test_un_envelope_fuori_limite_a_runtime_non_ha_il_limite(self):
        """Numeri ed envelope restano com'erano: il limite e' delle sole
        espressioni."""
        from pge.envelopes.envelope import Envelope
        from pge.parameters.parameter import Parameter
        parametro = Parameter('volume', Envelope([[0, 100], [10, 100]]),
                              GRANULAR_PARAMETERS['volume'])
        with patch('pge.parameters.parameter.log_clip_warning') as clip:
            for n in range(50):
                parametro.get_value(n * 0.1)
        assert clip.call_count == 50
        assert clip.call_args.kwargs.get('suppressed') is None


# =============================================================================
# 5. DOVE NON VALE
# =============================================================================

class TestDoveNonVale:

    @pytest.mark.parametrize('campo, extra, suggerisce', [
        ('pointer.speed_ratio', {'pointer': {'speed_ratio': '(m1)'}},
         'pointer.position'),
        ('pointer.start', {'pointer': {'start': '(m1)'}},
         'pointer.position'),
        ('pointer.loop_start', {'pointer': {'loop_start': '(m1)',
                                            'loop_dur': 0.2}},
         'pointer.position'),
        ('pointer.loop_end', {'pointer': {'loop_start': 0.1,
                                          'loop_end': '(m1)'}},
         'pointer.position'),
        ('pointer.loop_dur', {'pointer': {'loop_start': 0.1,
                                          'loop_dur': '(m1)'}},
         'pointer.position'),
        ('voices.num_voices', {'voices': {'num_voices': '(1 + 3*m1)'}},
         'envelope'),
    ])
    def test_i_sei_rifiuti_col_path_e_il_suggerimento(
            self, stream, campo, extra, suggerisce):
        with pytest.raises(ExpressionError) as exc:
            stream(**extra)
        err = exc.value
        assert isinstance(err, ConfigError)
        assert err.field == campo
        assert err.stream_id == 's1'
        assert err.hint == EXPRESSION_REFUSALS[campo]
        assert suggerisce in err.hint
        assert 'non vale' in err.reason

    def test_la_velocita_dice_perche(self, stream):
        with pytest.raises(ExpressionError) as exc:
            stream(pointer={'speed_ratio': '(m1)'})
        assert 'integra' in exc.value.hint

    @pytest.mark.parametrize('campo, extra', [
        ('volume_range', {'volume_range': '(m1)'}),
        ('pan_range', {'pan_range': '(m1)'}),
        ('grain.duration_range', {'grain': {'duration_range': '(m1)'}}),
        ('pointer.offset_range', {'pointer': {'offset_range': '(m1)'}}),
        ('pitch.range', {'pitch': {'semitones': 0, 'range': '(m1)'}}),
        ('voices.scatter', {'voices': {'num_voices': 2,
                                       'scatter': '(m1)'}}),
    ])
    def test_fuori_dal_perimetro_un_errore_col_path(self, stream, campo,
                                                    extra):
        """Bande e `scatter`: un'espressione vale sul valore base."""
        with pytest.raises(ExpressionError) as exc:
            stream(**extra)
        err = exc.value
        assert err.field == campo
        assert err.stream_id == 's1'
        assert 'non vale' in err.reason
        assert 'volume' in err.hint and 'pointer.position' in err.hint

    @pytest.mark.parametrize('extra', [
        {'deviation_probability': '(m1)'},
        {'deviation_probability': {'volume': '(m1)'}},
        {'voices': {'num_voices': 2,
                    'pointer': {'strategy': 'linear', 'step': '(m1)'}}},
        {'voices': {'num_voices': 2,
                    'pitch': {'strategy': 'step', 'step': '(m1)'}}},
    ])
    def test_la_probabilita_e_le_strategie_di_voce_restano_un_errore(
            self, stream, extra):
        with pytest.raises(ConfigError) as exc:
            stream(**extra)
        assert exc.value.stream_id == 's1'

    def test_una_stringa_che_non_e_un_espressione_resta_l_errore_di_prima(
            self, stream):
        from pge.shared.exceptions import InvalidParameterError
        with pytest.raises(InvalidParameterError):
            stream(volume_range='forte')

    def test_dove_vale_senza_parentesi_propone_le_parentesi(self, stream):
        with pytest.raises(ExpressionError) as exc:
            stream(volume='-30 + 20*m1')
        assert exc.value.field == 'volume'
        assert '(-30 + 20*m1)' in exc.value.hint


# =============================================================================
# 6. UNA STRINGA CHE NON E' UN'ESPRESSIONE
# =============================================================================

class TestUnaStringaCheNonEUnEspressione:
    """Nei campi in cui un'espressione vale, una stringa non e' per forza
    un'espressione. `density: not_a_number` su `main` era un
    `InvalidParameterError` («Formato non valido», col suggerimento su che
    cosa il campo vuole), e `grain.read_direction: reverse` un
    `InvalidFieldValueError` che spiega i due versi. Con l'elenco allargato
    dalla #313 erano diventate tutte e due «nome sconosciuto», l'errore di
    un linguaggio che chi ha scritto quella riga non stava usando — e il
    test e2e `test_e2e_invalid_parameter_format` era rosso.

    Il criterio e' quello della #309, l'esito: e' un'espressione cio' che
    sta fra parentesi, o che senza parentesi l'interprete compila (e allora
    l'errore propone le parentesi). Il resto e' una stringa nel posto
    sbagliato, e ha l'errore di prima.
    """

    @pytest.mark.parametrize('extra, nome', [
        ({'density': 'not_a_number'}, 'density'),
        ({'volume': 'forte'}, 'volume'),
        ({'pan': 'sinistra'}, 'pan'),
        ({'distribution': 'boh'}, 'distribution'),
        ({'fill_factor': 'boh', 'density': None}, 'fill_factor'),
        ({'pitch': {'semitones': 'boh'}}, 'pitch_semitones'),
        ({'pitch': {'ratio': 'boh'}}, 'pitch_ratio'),
        ({'pointer': {'position': 'boh'}}, 'pointer_position'),
        # Una mappa che non c'e', senza parentesi: non compila, e non e'
        # scritta come un'espressione.
        ({'volume': '-30 + 20*m2'}, 'volume'),
    ])
    def test_resta_il_formato_non_valido_di_prima(self, stream, extra, nome):
        from pge.shared.exceptions import InvalidParameterError
        with pytest.raises(InvalidParameterError) as exc:
            stream(**extra)
        err = exc.value
        assert err.param_name == f'{nome}.value'
        assert err.stream_id == 's1'
        assert 'Formato non valido' in err.user_message()
        # Dice che cosa il campo vuole, e che un'espressione va fra
        # parentesi.
        assert 'atteso numero' in err.hint
        assert 'fra parentesi' in err.hint

    @pytest.mark.parametrize('scritto', ['auto', 'reverse', 'forward'])
    def test_il_verso_scritto_a_parole_resta_l_errore_del_verso(
            self, stream, scritto):
        from pge.shared.exceptions import InvalidFieldValueError
        with pytest.raises(InvalidFieldValueError) as exc:
            stream(grain={'read_direction': scritto})
        assert exc.value.field == 'grain.read_direction'
        assert exc.value.stream_id == 's1'

    @pytest.mark.parametrize('scritto', ['-30 + 20*m1', 'm1', '10/2', 't'])
    def test_senza_parentesi_ma_compila_propone_le_parentesi(
            self, stream, scritto):
        """Questo non cambia: chi ha scritto un'espressione e ha dimenticato
        le parentesi lo sente dire."""
        with pytest.raises(ExpressionError) as exc:
            stream(volume=scritto)
        assert 'fra parentesi' in exc.value.reason
        assert f'({scritto})' in exc.value.hint

    @pytest.mark.parametrize('scritto, dice', [
        ('(forte)', 'nome sconosciuto «forte»'),
        ('(-30 + 20*m2)', 'nome sconosciuto «m2»'),
        ('(-30 + * m1)', 'non mi aspettavo «*»'),
    ])
    def test_fra_parentesi_e_un_espressione_e_l_errore_e_il_suo(
            self, stream, scritto, dice):
        with pytest.raises(ExpressionError) as exc:
            stream(volume=scritto)
        assert dice in exc.value.reason
        assert exc.value.field == 'volume'


# =============================================================================
# 7. DEVIATION_PROBABILITY: ESCLUSA, CON L'ERRORE DEGLI ALTRI ESCLUSI
# =============================================================================

class TestDeviationProbabilityRifiutaComeGliAltri:
    """`deviation_probability` non e' nell'elenco dei campi a espressione
    (decisione 12 della PR #316), come le bande `_range` e `voices.scatter`.
    Su quelli un'espressione e' un `ExpressionError` che dice «qui
    un'espressione non vale» e dove vale; qui era il vecchio
    `InvalidParameterError` «Formato non valido», di un altro tipo e con un
    altro testo. Ora e' lo stesso errore, col path della chiave."""

    @pytest.mark.parametrize('extra, campo', [
        ({'deviation_probability': '(m1*100)'}, 'deviation_probability'),
        ({'deviation_probability': {'volume': '(m1*100)'},
          'volume_range': 6}, 'deviation_probability.volume'),
        ({'deviation_probability': {'pan': '(50)'}, 'pan_range': 10},
         'deviation_probability.pan'),
    ])
    def test_un_espressione_e_l_errore_degli_esclusi(self, stream, extra,
                                                     campo):
        with pytest.raises(ExpressionError) as exc:
            stream(**extra)
        err = exc.value
        assert err.field == campo
        assert err.stream_id == 's1'
        assert 'non vale' in err.reason
        assert 'probabilita' in err.reason
        assert 'volume' in err.hint and 'pointer.position' in err.hint
        assert 'deviation_probability' not in err.hint

    @pytest.mark.parametrize('scritto', ['boh', 'molto'])
    def test_una_stringa_che_non_e_un_espressione_resta_com_era(
            self, stream, scritto):
        from pge.shared.exceptions import InvalidParameterError
        with pytest.raises(InvalidParameterError):
            stream(deviation_probability=scritto)
        with pytest.raises(InvalidParameterError):
            stream(deviation_probability={'volume': scritto}, volume_range=6)

    def test_numeri_ed_envelope_valgono_come_prima(self, stream):
        assert stream(deviation_probability=50, volume_range=6).voices[0]
        assert stream(deviation_probability={'volume': [[0, 0], [2, 100]]},
                      volume_range=6).voices[0]
