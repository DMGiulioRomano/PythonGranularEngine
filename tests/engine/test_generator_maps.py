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
