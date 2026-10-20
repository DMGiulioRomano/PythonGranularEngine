# tests/core/test_stream_deprecazioni.py
"""
La superficie deprecata di Stream, e la versione che annuncia (issue #285).

`Stream` non e' esportato da `pge`, ma chi usa il motore come libreria lo
riceve da `Generator.streams`: un attributo esce con un `FutureWarning` e la
rimozione alla major successiva, il precedente di #201 (`grains`). Qui stanno
le quattro cose deprecate e le promesse che ognuna fa: restare leggibile finche'
non esce, annunciare una versione di uscita che non sia gia' uscita, e non
scattare durante un uso normale del motore, che non le legge.

La seconda promessa e' quella che `grains` aveva rotto: deprecata nella 9.0.0
con «rimozione prevista in 9.0.0», alla 9.1.0 avvisava ancora di una rimozione
nel passato. La versione corrente si legge da `pyproject.toml`, non si
trascrive: il giorno che esce la 10.0.0 senza la rimozione, questi test lo
dicono.
"""
import re
import warnings
from pathlib import Path

import pytest

from pge.core.stream import Stream

_PYPROJECT = Path(__file__).resolve().parents[2] / 'pyproject.toml'

DEPRECATE = ('grains', 'sampleDurSec', 'pitch_range', 'envelope_table_num')


def _versione_corrente():
    testo = _PYPROJECT.read_text(encoding='utf-8')
    m = re.search(r'^version\s*=\s*"([^"]+)"', testo, re.M)
    assert m, "pyproject.toml non dichiara piu' `version` in questa forma"
    return m.group(1)


def _tupla(versione):
    return tuple(int(parte) for parte in versione.split('.')[:3])


@pytest.fixture
def stream(build_stream):
    s = build_stream(pitch={'semitones': 0, 'range': 2.0})
    # `grains` genera i grani, e la generazione pretende i riferimenti che
    # assegna il Generator (#283).
    s.sample_table_num = 1
    s.window_table_map = {'hanning': 2}
    return s


def _avviso(stream, nome):
    """Il messaggio dell'unico FutureWarning che leggere `nome` emette."""
    with warnings.catch_warnings(record=True) as visti:
        warnings.simplefilter('always')
        getattr(stream, nome)
    futuri = [w for w in visti if issubclass(w.category, FutureWarning)]
    assert len(futuri) == 1, (nome, [str(w.message) for w in visti])
    return str(futuri[0].message)


def _versione_annunciata(messaggio):
    m = re.search(r'PGE (\d+\.\d+\.\d+)', messaggio)
    assert m, f"l'avviso non nomina la versione in cui esce: {messaggio}"
    return m.group(1)


class TestLaVersioneAnnunciata:

    @pytest.mark.parametrize('nome', DEPRECATE)
    def test_e_una_versione_che_non_e_ancora_uscita(self, stream, nome):
        versione = _versione_annunciata(_avviso(stream, nome))
        corrente = _versione_corrente()
        assert _tupla(versione) > _tupla(corrente), (
            f"Stream.{nome} annuncia la rimozione in PGE {versione}, e siamo "
            f"a {corrente}: o esce adesso, o l'avviso nomina la prossima "
            f"major (#285)")

    @pytest.mark.parametrize('nome', DEPRECATE)
    def test_la_docstring_dice_la_stessa_versione(self, stream, nome):
        versione = _versione_annunciata(_avviso(stream, nome))
        assert versione in getattr(Stream, nome).__doc__


class TestRestanoLeggibili:

    def test_sample_dur_sec(self, stream):
        with pytest.warns(FutureWarning, match=r'Stream\.sample_dur_sec'):
            assert stream.sampleDurSec == stream.sample_dur_sec

    def test_pitch_range(self, stream):
        with pytest.warns(FutureWarning):
            assert stream.pitch_range == pytest.approx(2.0)

    def test_envelope_table_num_avvisa_in_lettura_e_in_scrittura(self, stream):
        """Nessuno lo assegna, ma era un attributo: chi lo scriveva da fuori
        deve poterlo ancora fare, e saperlo."""
        with pytest.warns(FutureWarning, match=r'10\.0\.0'):
            assert stream.envelope_table_num is None
        with pytest.warns(FutureWarning, match=r'10\.0\.0'):
            stream.envelope_table_num = 7
        with pytest.warns(FutureWarning):
            assert stream.envelope_table_num == 7


class TestIlMotoreNonLiLegge:

    def test_generare_e_leggere_le_curve_non_avvisa(self, stream):
        """Il preavviso e' per chi usa il motore come libreria: un render
        normale non deve emetterlo, o lo vedrebbe chiunque."""
        from pge.rendering.envelope_extractor import get_stream_envelopes
        with warnings.catch_warnings():
            warnings.simplefilter('error', FutureWarning)
            stream.voices
            get_stream_envelopes(stream, show_static=True,
                                 show_voice_offsets=True)
