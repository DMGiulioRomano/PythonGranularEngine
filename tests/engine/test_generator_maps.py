"""
Il caricamento di uno YAML con mappe ed espressioni (issue #308, mappe
caotiche 1/7), dall'interfaccia pubblica del Generator su file veri.

Oggi `Generator._eval_math_expressions` valuta al caricamento ogni `( ... )`
in una costante, con `eval`. Un'espressione che nomina una mappa non e' una
costante: si valuta a ogni grano. Va lasciata com'e' — e senza la riga
`impossibile valutare` su stdout, che e' un contratto e che PGE-ui legge.
"""
import numpy as np
import pytest
import soundfile as sf
import yaml

from pge.engine.generator import Generator
from pge.rendering.stream_cache_manager import StreamCacheManager

SAMPLE = 'tono.wav'
ESPRESSIONE = '(0.02 + 0.08*m1)'


def _stream(**extra):
    stream = {
        'stream_id': 's1',
        'onset': 0.0,
        'duration': 3.0,
        'sample': SAMPLE,
        'maps': {'m1': {'type': 'logistic', 'r': 3.5}},
        'grain': {'duration': ESPRESSIONE},
    }
    stream.update(extra)
    return stream


@pytest.fixture
def carica(tmp_path):
    refs = tmp_path / 'refs'
    refs.mkdir()
    sf.write(str(refs / SAMPLE), np.zeros(48000, dtype='float32'), 48000)

    def _carica(*streams, testo=None):
        path = tmp_path / 'brano.yml'
        if testo is None:
            testo = yaml.safe_dump(
                {'seed': 1441, 'streams': list(streams)}, sort_keys=False)
        path.write_text(testo, encoding='utf-8')
        generator = Generator(str(path), samples_dir=str(refs))
        generator.load_yaml()
        return generator
    return _carica


def _fingerprint(stream_dict):
    return StreamCacheManager(
        cache_path='inutile.json', renderer_type='numpy', seed=1441,
    ).compute_fingerprint(stream_dict)


class TestIlCaricamentoLasciaLEspressioneComE:

    def test_niente_impossibile_valutare_su_stdout(self, carica, capsys):
        carica(_stream())
        uscita = capsys.readouterr()
        assert 'impossibile valutare' not in uscita.out
        assert 'impossibile valutare' not in uscita.err
        assert uscita.out == ''

    def test_l_espressione_arriva_allo_stream_com_e_scritta(self, carica):
        generator = carica(_stream())
        assert generator.data['streams'][0]['grain']['duration'] == ESPRESSIONE

    def test_scritta_nello_yaml_senza_virgolette(self, carica, capsys):
        """Come nella issue: `duration: (0.02 + 0.08*m1)` e' uno scalare
        YAML, una stringa."""
        generator = carica(testo=(
            "seed: 1441\n"
            "streams:\n"
            "  - stream_id: s1\n"
            f"    sample: {SAMPLE}\n"
            "    duration: 3\n"
            "    maps:\n"
            "      m1: {type: logistic, r: 3.5}\n"
            "    grain:\n"
            "      duration: (0.02 + 0.08*m1)\n"))
        assert 'impossibile valutare' not in capsys.readouterr().out
        assert generator.data['streams'][0]['grain']['duration'] == ESPRESSIONE

    def test_le_costanti_dentro_l_espressione_restano_a_lei(self, carica, capsys):
        """`(0.02 + (8/100)*m1)`: il pezzo `(8/100)` da solo sarebbe una
        costante, ma l'espressione e' una sola e la compila l'interprete."""
        generator = carica(_stream(grain={'duration': '(0.02 + (8/100)*m1)'}))
        assert 'impossibile valutare' not in capsys.readouterr().out
        assert (generator.data['streams'][0]['grain']['duration']
                == '(0.02 + (8/100)*m1)')

    def test_un_espressione_sul_solo_tempo_non_avvisa(self, carica, capsys):
        generator = carica(_stream(grain={'duration': '(0.02 + 0.01*t)'}))
        assert 'impossibile valutare' not in capsys.readouterr().out
        assert (generator.data['streams'][0]['grain']['duration']
                == '(0.02 + 0.01*t)')

    def test_le_espressioni_di_oggi_si_valutano_come_oggi(self, carica):
        """Il resto dello stream non cambia: `(1 + 1)` e' ancora 2, anche
        dentro `maps:`."""
        generator = carica(_stream(
            onset='(1 + 1)', volume='(-3 * 2)',
            maps={'m1': {'type': 'logistic', 'r': '(7 / 2)'}}))
        stream = generator.data['streams'][0]
        assert stream['onset'] == 2
        assert stream['volume'] == -6
        assert stream['maps']['m1']['r'] == 3.5

    def test_uno_stream_senza_mappe_non_e_toccato(self, carica, capsys):
        """Una stringa fra parentesi che il math-eval di oggi non sa
        valutare resta com'e', col suo avviso: senza `maps:` niente la
        nomina, e il riparo non la riguarda."""
        stream = _stream(grain={'duration': 0.05}, nota='(boh + 1)')
        del stream['maps']
        generator = carica(stream)
        assert generator.data['streams'][0]['nota'] == '(boh + 1)'
        assert 'impossibile valutare' in capsys.readouterr().out


class TestICampiAEspressione:
    """Nei campi in cui un'espressione vale (`EXPRESSION_FIELDS`) il criterio
    del plan e' «nessuna riga nuova su stdout al caricamento di
    un'espressione valida», anche quando l'espressione non nomina una mappa.

    `(0.02 + 0.08*sqrt(0.25))` e' una costante, ma `sqrt` la valutazione al
    caricamento non la conosce (ha `abs int float min max pow pi e`):
    avvisava `impossibile valutare` su stdout, e poi l'interprete la
    compilava lo stesso. Va al riparo, come un'espressione su una mappa. Una
    costante che la valutazione sa fare resta sua, e diventa un numero: e' il
    numero che la partitura disegna e che i bounds controllano al parse.
    """

    @pytest.mark.parametrize('campo, espressione', [
        ('duration', '(0.02 + 0.08*sqrt(0.25))'),
        ('duration', '(0.05 * abs(sin(1)))'),
        ('duration', '(0.02 + clip(0.3, (1/2), 1)*0.08)'),
        ('iot', '(0.1 + 0.05*frac(1.3))'),
    ])
    def test_una_costante_del_linguaggio_nuovo_non_avvisa(
            self, carica, capsys, campo, espressione):
        stream = _stream(grain={campo: espressione})
        del stream['maps']
        generator = carica(stream)
        assert 'impossibile valutare' not in capsys.readouterr().out
        assert generator.data['streams'][0]['grain'][campo] == espressione
        prodotto, = generator.create_elements()
        assert prodotto.voices[0]

    def test_un_nome_sbagliato_lo_dice_l_interprete_e_basta(self, carica,
                                                            capsys):
        """Prima: l'avviso della valutazione (`name 'pii' is not defined`)
        e poi l'errore dell'interprete. Ora l'errore solo, che dice anche
        quali nomi ci sono."""
        from pge.shared.exceptions import ExpressionError
        generator = carica(_stream(grain={'duration': '(0.02 * pii)'}))
        assert 'impossibile valutare' not in capsys.readouterr().out
        with pytest.raises(ExpressionError) as exc:
            generator.create_elements()
        assert 'pii' in exc.value.reason
        assert exc.value.field == 'grain.duration'

    @pytest.mark.parametrize('scritto, numero', [
        ('(0.05 * abs(-1))', 0.05),
        ('(int(3.7)/100)', 0.03),
        ('(max(0.01*2, 0.01)*1)', None),
    ])
    def test_una_costante_che_la_valutazione_sa_fare_resta_sua(
            self, carica, scritto, numero):
        """Il riparo non si allarga alle costanti di oggi: `abs`, `int`,
        `max` li valuta il caricamento, come prima. (`max` con la virgola il
        caricamento non lo valuta, la #309: resta testo, come prima.)"""
        generator = carica(_stream(grain={'duration': scritto}))
        valore = generator.data['streams'][0]['grain']['duration']
        if numero is None:
            assert valore == scritto
        else:
            assert valore == pytest.approx(numero)

    def test_fuori_dai_campi_a_espressione_l_avviso_resta(self, carica,
                                                          capsys):
        """Su `volume` un'espressione non vale ancora (la #313): li' l'avviso
        della valutazione e' l'unica spiegazione di `sqrt`, e resta."""
        stream = _stream(volume='(sqrt(4))')
        del stream['maps']
        generator = carica(stream)
        assert 'impossibile valutare' in capsys.readouterr().out
        assert generator.data['streams'][0]['volume'] == '(sqrt(4))'

    def test_i_nomi_della_valutazione_sono_quelli_del_generator(self):
        """Il riparo sa quali nomi la valutazione al caricamento conosce:
        sono le chiavi del `safe_dict` di `_eval_math_expressions`, lette
        qui dal sorgente. Se la #309 le cambia, questo lo dice."""
        import ast
        import inspect
        import textwrap
        from pge.engine.expression_shelter import LOAD_TIME_NAMES
        albero = ast.parse(textwrap.dedent(
            inspect.getsource(Generator._eval_math_expressions)))
        dizionari = [
            nodo.value for nodo in ast.walk(albero)
            if isinstance(nodo, ast.Assign)
            and any(isinstance(b, ast.Name) and b.id == 'safe_dict'
                    for b in nodo.targets)
            and isinstance(nodo.value, ast.Dict)]
        assert len(dizionari) == 1, "safe_dict non e' piu' un dict letterale"
        chiavi = {k.value for k in dizionari[0].keys}
        assert LOAD_TIME_NAMES == frozenset(chiavi)


class TestDalFileAiGrani:

    def test_il_brano_rende_e_le_durate_percorrono_il_ciclo(self, carica):
        generator = carica(_stream())
        stream, = generator.create_elements()
        durate = [round(g.duration * 1000) for g in stream.voices[0]]
        ciclo = [86, 60, 90, 51]
        assert durate[:4] in [ciclo[k:] + ciclo[:k] for k in range(4)]
        assert durate[4:8] == durate[:4]

    def test_due_stream_hanno_ognuno_le_sue_mappe(self, carica):
        """`maps:` sta dentro lo stream: lo stesso nome in due stream sono
        due mappe."""
        generator = carica(
            _stream(),
            _stream(stream_id='s2',
                    maps={'m1': {'type': 'logistic', 'r': 3.2}}))
        primo, secondo = generator.create_elements()
        assert len({round(g.duration, 4) for g in primo.voices[0]}) == 4
        assert len({round(g.duration, 4) for g in secondo.voices[0]}) == 2

    def test_un_errore_nell_espressione_nomina_il_file(self, carica):
        from pge.shared.exceptions import ExpressionError
        generator = carica(_stream(grain={'duration': '(0.02 + 0.08*m9)'}))
        with pytest.raises(ExpressionError) as exc:
            generator.create_elements()
        assert exc.value.field == 'grain.duration'
        assert exc.value.stream_id == 's1'


class TestFingerprint:
    """La cache hasha il dict dello stream: le chiavi nuove entrano da
    sole. Qui lo si misura, perche' un'espressione valutata al caricamento
    in una costante, o un `maps:` scartato, lo smentirebbero in silenzio."""

    def _fp(self, carica, **extra):
        return _fingerprint(carica(_stream(**extra)).data['streams'][0])

    def test_cambia_al_cambiare_di_r(self, carica):
        assert self._fp(carica) != self._fp(
            carica, maps={'m1': {'type': 'logistic', 'r': 3.6}})

    def test_cambia_al_cambiare_dell_espressione(self, carica):
        assert self._fp(carica) != self._fp(
            carica, grain={'duration': '(0.02 + 0.09*m1)'})

    def test_cambia_al_cambiare_di_x0_e_del_transitorio(self, carica):
        base = self._fp(carica)
        assert base != self._fp(
            carica, maps={'m1': {'type': 'logistic', 'r': 3.5, 'x0': 0.2}})
        assert base != self._fp(carica, maps={
            'm1': {'type': 'logistic', 'r': 3.5, 'transient': 0}})

    def test_e_stabile_fra_due_caricamenti(self, carica):
        assert self._fp(carica) == self._fp(carica)
