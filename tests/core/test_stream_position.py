"""
Uno stream intero con `pointer.position` (issue #312, mappe caotiche 4/7):
le voci, il fingerprint della cache, cio' che lo Stream espone a chi lo
legge, il caricamento da un file.

Che senza `position` i grani siano quelli di prima lo dice
`test_stream_puntatore_invariato.py`, su un'istantanea.
"""
import numpy as np
import pytest
import soundfile as sf
import yaml

from pge.core.stream import Stream
from pge.engine.generator import Generator
from pge.expressions.fields import EXPRESSION_FIELDS
from pge.parameters.parameter import Parameter
from pge.parameters.parameter_definitions import (
    GRANULAR_PARAMETERS, WRAPPING_PARAMETERS, parameter_wraps)
from pge.parameters.parameter_schema import POINTER_PARAMETER_SCHEMA
from pge.rendering.stream_cache_manager import StreamCacheManager

_SAMPLE = 'due_secondi.wav'
MAPPA = {'m1': {'type': 'logistic', 'r': 3.5}}
CICLO = [0.827, 0.501, 0.875, 0.383]


@pytest.fixture(scope='module')
def samples_dir(tmp_path_factory):
    cartella = tmp_path_factory.mktemp('samples')
    sf.write(str(cartella / _SAMPLE), np.zeros(96000, dtype='float32'), 48000)
    return str(cartella)


def _params(pointer, **extra):
    params = {
        'stream_id': 's1', 'onset': 0.0, 'duration': 2.0, 'sample': _SAMPLE,
        'density': 25, 'maps': MAPPA,
        'grain': {'envelope': 'hanning', 'duration': 0.05},
        'pointer': pointer,
    }
    params.update(extra)
    return params


@pytest.fixture
def stream(samples_dir):
    def costruisci(pointer, **extra):
        s = Stream(_params(pointer, **extra), seed=1441,
                   samples_dir=samples_dir)
        s.sample_table_num = 1
        s.window_table_map = {'hanning': 2}
        return s
    return costruisci


def _fingerprint(params):
    return StreamCacheManager(
        cache_path='inutile.json', renderer_type='numpy', seed=1441,
    ).compute_fingerprint(params)


def _e_il_ciclo(frazioni):
    rotazioni = [CICLO[k:] + CICLO[:k] for k in range(4)]
    assert frazioni[:4] in rotazioni, frazioni[:4]
    for n, valore in enumerate(frazioni):
        assert valore == frazioni[n % 4]


class TestPiuVoci:

    def test_ogni_voce_percorre_il_ciclo(self, stream):
        """`clock: grain` ha uno stato per voce: tre voci, tre volte la
        stessa sequenza, ognuna dall'inizio."""
        s = stream({'position': '(m1)'},
                   voices={'num_voices': 3, 'scatter': 1.0},
                   distribution=0.6)
        assert len(s.voices) == 3
        for voce in s.voices:
            assert len(voce) > 12
            _e_il_ciclo([round(g.pointer_pos / 2.0, 3) for g in voce])

    def test_con_scatter_le_voci_divergono_nel_tempo(self, stream):
        s = stream({'position': '(m1)'},
                   voices={'num_voices': 2, 'scatter': 1.0},
                   distribution=0.8)
        onset = [[g.onset for g in voce][:10] for voce in s.voices]
        assert onset[0] != onset[1]

    def test_la_stessa_mappa_su_posizione_e_durata(self, stream):
        """Due parametri che leggono `m1` nello stesso grano vedono lo
        stesso valore."""
        s = stream({'position': '(m1)'},
                   grain={'envelope': 'hanning',
                          'duration': '(0.02 + 0.08*m1)'})
        for g in s.voices[0]:
            m1 = g.pointer_pos / 2.0
            assert g.duration == pytest.approx(0.02 + 0.08 * m1, abs=1e-12)


class TestFingerprint:

    def test_cambia_con_position(self):
        base = _params({'loop_start': 0.4, 'loop_dur': 0.2})
        con = _params({'position': '(m1)', 'loop_start': 0.4,
                       'loop_dur': 0.2})
        altra = _params({'position': '(1 - m1)', 'loop_start': 0.4,
                         'loop_dur': 0.2})
        assert len({_fingerprint(base), _fingerprint(con),
                    _fingerprint(altra)}) == 3


class TestCioCheLoStreamEspone:

    def test_pointer_position_e_un_parametro(self, stream):
        s = stream({'position': 0.5})
        assert isinstance(s.pointer_position, Parameter)
        assert s.pointer_position.value == 0.5

    def test_senza_position_non_c_e(self, stream):
        assert stream({}).pointer_position is None
        assert stream({'speed_ratio': 2}).pointer_position is None

    def test_con_position_non_c_e_una_velocita_da_mostrare(self, stream):
        """`speed_ratio` non e' scritta e non muove niente: pubblicarne il
        default come curva direbbe una cosa falsa."""
        assert stream({'position': 0.5}).pointer_speed is None
        assert stream({}).pointer_speed == 1.0

    def test_e_un_campo_in_cui_un_espressione_vale(self):
        assert 'pointer.position' in EXPRESSION_FIELDS

    def test_e_nello_schema_del_pointer(self):
        spec, = [s for s in POINTER_PARAMETER_SCHEMA
                 if s.name == 'pointer_position']
        assert spec.yaml_path == 'position'
        assert spec.default is None

    def test_i_bounds_sono_zero_uno(self):
        bounds = GRANULAR_PARAMETERS['pointer_position']
        assert (bounds.min_val, bounds.max_val) == (0.0, 1.0)

    def test_che_rientri_a_capo_e_un_dato(self):
        """`WRAPPING_PARAMETERS` dice quali bounds non tagliano: e' l'unico,
        ed e' un letterale che chi specchia i bounds legge dal sorgente."""
        assert WRAPPING_PARAMETERS == ('pointer_position',)
        assert parameter_wraps('pointer_position')
        assert not parameter_wraps('volume')
        assert set(WRAPPING_PARAMETERS) <= set(GRANULAR_PARAMETERS)

    def test_il_dato_si_legge_senza_importare(self):
        import ast
        import inspect
        from pge.parameters import parameter_definitions
        albero = ast.parse(inspect.getsource(parameter_definitions))
        letti = [ast.literal_eval(n.value) for n in albero.body
                 if isinstance(n, ast.Assign)
                 and any(getattr(t, 'id', None) == 'WRAPPING_PARAMETERS'
                         for t in n.targets)]
        assert letti == [('pointer_position',)]


class TestDalFile:

    @pytest.fixture
    def carica(self, tmp_path):
        refs = tmp_path / 'refs'
        refs.mkdir()
        sf.write(str(refs / _SAMPLE), np.zeros(96000, dtype='float32'), 48000)

        def _carica(pointer, **extra):
            path = tmp_path / 'brano.yml'
            path.write_text(yaml.safe_dump(
                {'seed': 1441, 'streams': [_params(pointer, **extra)]},
                sort_keys=False), encoding='utf-8')
            generator = Generator(str(path), samples_dir=str(refs))
            generator.load_yaml()
            return generator
        return _carica

    def test_il_caricamento_non_avvisa(self, carica, capsys):
        generator = carica({'position': '(m1)', 'loop_start': 0.2,
                            'loop_dur': 0.1, 'loop_unit': 'normalized'})
        assert 'impossibile valutare' not in capsys.readouterr().out
        assert generator.data['streams'][0]['pointer']['position'] == '(m1)'

    def test_una_funzione_del_linguaggio_senza_mappe(self, carica, capsys):
        """`position` e' un campo a espressione: `frac` il caricamento non
        lo conosce, e non deve avvisare."""
        generator = carica({'position': '(frac(1.3))'})
        assert 'impossibile valutare' not in capsys.readouterr().out
        prodotto, = generator.create_elements()
        assert prodotto.voices[0][0].pointer_pos == pytest.approx(0.6)

    def test_una_costante_resta_un_numero(self, carica):
        generator = carica({'position': '(1/4)'})
        assert generator.data['streams'][0]['pointer']['position'] == 0.25

    def test_il_brano_rende(self, carica):
        generator = carica({'position': '(m1)'})
        prodotto, = generator.create_elements()
        _e_il_ciclo([round(g.pointer_pos / 2.0, 3)
                     for g in prodotto.voices[0]])
