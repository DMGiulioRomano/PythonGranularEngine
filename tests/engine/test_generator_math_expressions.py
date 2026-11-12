"""
Le espressioni che il Generator valuta al caricamento (issue #309, mappe
caotiche 7/7).

`Generator._eval_math_expressions` prometteva nella docstring che
`(max(3, 7))` valesse 7. Non era cosi': il regex che riconosce
un'espressione non ammetteva la virgola, e ogni funzione a due argomenti
restava una stringa. La seconda regola non scritta era che l'espressione
deve stare tutta dentro le parentesi esterne: `(10/2)/10` usciva valutata a
meta', come la stringa `5.0/10`.

Qui i due fatti, misurati sul metodo e sul caricamento di un file vero.
"""
import ast
import inspect
import math
import re
import textwrap

import numpy as np
import pytest
import soundfile as sf
import yaml

from pge.engine.generator import Generator
from pge.shared.exceptions import ConfigError, ExpressionError

SAMPLE = 'tono.wav'


@pytest.fixture
def valuta():
    return Generator('inutile.yml')._eval_math_expressions


@pytest.fixture
def carica(tmp_path):
    refs = tmp_path / 'refs'
    refs.mkdir()
    sf.write(str(refs / SAMPLE), np.zeros(48000, dtype='float32'), 48000)

    def _carica(*streams, **testa):
        path = tmp_path / 'brano.yml'
        documento = {'seed': 1441, **testa, 'streams': list(streams)}
        path.write_text(yaml.safe_dump(documento, sort_keys=False),
                        encoding='utf-8')
        generator = Generator(str(path), samples_dir=str(refs))
        generator.load_yaml()
        return generator
    _carica.path = str(tmp_path / 'brano.yml')
    return _carica


def _stream(**extra):
    stream = {'stream_id': 's1', 'onset': 0.0, 'duration': 2.0,
              'sample': SAMPLE}
    stream.update(extra)
    return stream


# =============================================================================
# LE FUNZIONI A PIU' ARGOMENTI
# =============================================================================

class TestLaVirgola:

    @pytest.mark.parametrize('scritto, atteso', [
        ('(max(3, 7))', 7),
        ('(max(3,7))', 7),
        ('(pow(2, 3))', 8),
        ('(min(1, 2, 3))', 1),
        ('(max(1.5, 2.5))', 2.5),
        ('(min(10, 2) * 3)', 6),
        ('(pow(2, max(1, 3)))', 8),
    ])
    def test_le_funzioni_a_piu_argomenti_si_valutano(self, valuta, scritto,
                                                     atteso):
        assert valuta(scritto) == atteso

    def test_dentro_un_breakpoint(self, valuta):
        assert valuta([[0, '(max(3, 7))'], ['(pow(2, 3))', 0]]) == [
            [0, 7], [8, 0]]

    def test_dentro_un_dizionario(self, valuta):
        assert valuta({'points': [[0, '(min(4, 2))']], 'type': 'linear'}) == {
            'points': [[0, 2]], 'type': 'linear'}

    def test_nessuna_riga_su_stdout(self, valuta, capsys):
        valuta('(max(3, 7))')
        valuta('(pow(2, 3))')
        assert capsys.readouterr().out == ''

    def test_dal_file_ai_valori(self, carica, capsys):
        generator = carica(_stream(
            volume='(max(-12, -6))', grain={'duration': '(pow(10, -2))'}))
        stream = generator.data['streams'][0]
        assert stream['volume'] == -6
        assert stream['grain']['duration'] == pytest.approx(0.01)
        assert 'impossibile valutare' not in capsys.readouterr().out


class TestITipiRestanoQuelliDiOggi:
    """Un intero resta un intero: `n_reps`, `num_voices`, `iterate` lo
    pretendono, e un `4.0` al loro posto e' un errore."""

    @pytest.mark.parametrize('scritto, atteso, tipo', [
        ('(2*2)', 4, int),
        ('(10 + 5)', 15, int),
        ('(max(3, 7))', 7, int),
        ('(7//2)', 3, int),
        ('(10/2)', 5.0, float),
        ('(pow(2, 0.5))', 2 ** 0.5, float),
        ('((10/2)/10)', 0.5, float),
    ])
    def test_tipo_e_valore(self, valuta, scritto, atteso, tipo):
        valore = valuta(scritto)
        assert type(valore) is tipo
        assert valore == pytest.approx(atteso)


class TestCioCheNonEUnEspressione:
    """La virgola allarga cio' che il regex riconosce: una stringa che non
    e' un'espressione deve restare com'era."""

    def test_una_coppia_fra_parentesi_resta_il_suo_testo(self, valuta):
        """`(1,2)` e' una tupla per Python: valutata e riscritta diventerebbe
        `(1, 2)`, un testo diverso da quello dello YAML."""
        assert valuta('coppia (1,2)') == 'coppia (1,2)'
        assert valuta('(1,2)') == '(1,2)'

    def test_parole_fra_parentesi_con_la_virgola(self, valuta):
        assert valuta('tre voci (alto, basso)') == 'tre voci (alto, basso)'

    def test_il_nome_di_una_funzione_resta_il_suo_testo(self, valuta):
        """Prima usciva la stringa `<built-in function abs>`."""
        assert valuta('(abs)') == '(abs)'

    def test_il_nome_di_un_file_e_trattato_come_prima(self, valuta):
        assert valuta('voce (1).wav') == 'voce 1.wav'

    def test_una_stringa_senza_parentesi(self, valuta):
        assert valuta('hanning') == 'hanning'
        assert valuta('10/2') == '10/2'


# =============================================================================
# L'ESPRESSIONE STA TUTTA DENTRO LE PARENTESI ESTERNE
# =============================================================================

class TestValutataAMeta:
    """`(10/2)/10` e' un'espressione scritta per meta' fuori dalle
    parentesi: il caricamento ne valutava il pezzo fra parentesi e lasciava
    il resto come testo (`5.0/10`), che a valle era un errore di tipo. Ora
    si ferma qui, e dice come si scrive."""

    @pytest.mark.parametrize('scritto, proposta', [
        ('(10/2)/10', '((10/2)/10)'),
        ('2*(3+4)', '(2*(3+4))'),
        ('(pi)*2', '((pi)*2)'),
        ('(1+2)*(3+4)', '((1+2)*(3+4))'),
        ('max(3, 7) + (1)', '(max(3, 7) + (1))'),
    ])
    def test_e_un_errore_che_propone_la_grafia(self, carica, scritto,
                                               proposta):
        with pytest.raises(ExpressionError) as exc:
            carica(_stream(volume=scritto))
        err = exc.value
        assert isinstance(err, ConfigError)
        assert err.field == 'volume'
        assert err.stream_id == 's1'
        assert err.expression == scritto
        assert proposta in err.hint
        assert err.config_file == carica.path

    def test_il_messaggio_dice_campo_stream_e_file(self, carica):
        with pytest.raises(ExpressionError) as exc:
            carica(_stream(grain={'duration': '(10/2)/100'}))
        messaggio = exc.value.user_message()
        assert "grain.duration" in messaggio
        assert '(10/2)/100' in messaggio
        assert '((10/2)/100)' in messaggio
        assert 'Stream:       s1' in messaggio
        assert 'brano.yml' in messaggio

    def test_dentro_un_envelope_il_path_dice_il_punto(self, carica):
        with pytest.raises(ExpressionError) as exc:
            carica(_stream(volume=[[0, -6], ['(10/2)/10', 0]]))
        assert exc.value.field == 'volume[1][0]'

    def test_dentro_maps(self, carica):
        with pytest.raises(ExpressionError) as exc:
            carica(_stream(
                maps={'m1': {'type': 'logistic', 'r': '(7/2)+0.1'}},
                grain={'duration': '(0.02 + 0.08*m1)'}))
        assert exc.value.field == 'maps.m1.r'

    def test_in_testa_al_documento_non_c_e_uno_stream(self, carica):
        with pytest.raises(ExpressionError) as exc:
            carica(_stream(), seed='(1000)+441')
        assert exc.value.field == 'seed'
        assert exc.value.stream_id is None

    def test_niente_su_stdout_prima_dell_errore(self, carica, capsys):
        with pytest.raises(ExpressionError):
            carica(_stream(volume='(10/2)/10'))
        assert capsys.readouterr().out == ''

    @pytest.mark.parametrize('scritto', [
        '((10/2)/10)',
        ' (10/2) ',
        '(max(3, 7))',
    ])
    def test_tutta_fra_parentesi_si_valuta(self, carica, scritto):
        generator = carica(_stream(volume=f'(0 - {scritto})'))
        assert isinstance(generator.data['streams'][0]['volume'],
                          (int, float))

    @pytest.mark.parametrize('scritto, resta', [
        ('voce (1).wav', 'voce 1.wav'),
        ('take (2) di (3)', 'take (2) di (3)'),
        ('(boh + 1) e basta', '(boh + 1) e basta'),
    ])
    def test_una_stringa_che_non_e_aritmetica_non_e_un_errore(
            self, carica, scritto, resta):
        """Il criterio e' che la stringa INTERA, messa fra parentesi, sia
        un numero: il nome di un file non lo e', e resta trattato come
        prima."""
        generator = carica(_stream(nota=scritto))
        assert generator.data['streams'][0]['nota'] == resta

    def test_un_espressione_per_grano_non_e_riguardata(self, carica):
        """Quelle che leggono una mappa attraversano il caricamento al
        riparo: la loro regola la dice l'interprete."""
        generator = carica(_stream(
            maps={'m1': {'type': 'logistic', 'r': 3.5}},
            grain={'duration': '(clip(0.02 + 0.08*m1, 0.01, (1/2)))'}))
        assert (generator.data['streams'][0]['grain']['duration']
                == '(clip(0.02 + 0.08*m1, 0.01, (1/2)))')


# =============================================================================
# LA DOCSTRING DICE QUELLO CHE IL METODO FA
# =============================================================================

class TestLaDocstring:

    def _esempi(self):
        """Le righe `"scritto" → valore` della docstring."""
        testo = inspect.getdoc(Generator._eval_math_expressions)
        return re.findall(r'^\s*"([^"]+)"\s*→\s*(.+?)\s*$', testo, re.M)

    def test_ha_degli_esempi(self):
        scritti = [scritto for scritto, _ in self._esempi()]
        assert '(max(3, 7))' in scritti
        assert '(10/2)/10' in scritti

    def test_ogni_esempio_e_vero(self, valuta):
        for scritto, promesso in self._esempi():
            ottenuto = valuta(scritto)
            if promesso.startswith('errore'):
                continue
            atteso = ast.literal_eval(promesso.rstrip('.').replace('...', ''))
            if isinstance(atteso, float):
                assert ottenuto == pytest.approx(atteso, abs=1e-3), scritto
            else:
                assert ottenuto == atteso, scritto
                assert type(ottenuto) is type(atteso), scritto

    def test_dice_la_regola_delle_parentesi_esterne(self):
        testo = inspect.getdoc(Generator._eval_math_expressions)
        assert 'parentesi esterne' in testo

    def test_il_regex_ammette_la_virgola(self):
        albero = ast.parse(textwrap.dedent(
            inspect.getsource(Generator._eval_math_expressions)))
        pattern = [n.value.value for n in ast.walk(albero)
                   if isinstance(n, ast.Assign)
                   and any(getattr(t, 'id', None) == 'pattern'
                           for t in n.targets)]
        assert pattern == [r'\(([a-zA-Z0-9+\-*/.(), ]+)\)']


# =============================================================================
# CIO' CHE IL CARICAMENTO VALUTAVA GIA' PER INTERO NON E' «A META'»
# =============================================================================

class TestGiaUnNumero:
    """`pan: -(90/2)` su `main` rendeva: il caricamento sostituiva `(90/2)`,
    ne usciva il testo `-45.0`, e quello e' un numero. Non e' un'espressione
    valutata a meta' — non resta niente da valutare — e la regola delle
    parentesi esterne (issue #309) e' nata per le stringhe che a valle
    erano gia' un errore, non per uno YAML che funzionava."""

    @pytest.mark.parametrize('scritto, atteso', [
        ('-(90/2)', -45.0),
        ('-(pi)', -math.pi),
        ('+(10/4)', 2.5),
        (' -(3) ', -3),
    ])
    def test_il_segno_davanti_alle_parentesi_vale_come_prima(
            self, carica, scritto, atteso):
        generator = carica(_stream(pan=scritto))
        valore = generator.data['streams'][0]['pan']
        assert isinstance(valore, (int, float))
        assert valore == pytest.approx(atteso)

    def test_dentro_un_envelope(self, carica):
        generator = carica(_stream(pan=[[0, '-(90/2)'], [1, 0]]))
        assert generator.data['streams'][0]['pan'][0][1] == -45.0

    @pytest.mark.parametrize('scritto', ['-(pi)*2', '-(10/2)/10', '2*(3+4)'])
    def test_cio_che_restava_un_testo_e_ancora_un_errore(self, carica,
                                                        scritto):
        with pytest.raises(ExpressionError) as exc:
            carica(_stream(pan=scritto))
        assert f'({scritto})' in exc.value.hint
