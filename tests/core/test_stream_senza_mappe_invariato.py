"""
Uno stream che non scrive le chiavi delle mappe caotiche (issue #307) da' gli
stessi grani e lo stesso fingerprint di prima.

«Di prima» e' un fatto, non un ricordo: l'istantanea in
`fixtures/grani_senza_mappe.json` e' stata presa su `main` (b227567), prima
della prima riga della #308, con le stesse funzioni di questo file. Non si
rigenera: se un caso diventa rosso, e' il motore ad aver cambiato i grani di
uno YAML che le chiavi nuove non le nomina — cioe' il breaking change che il
plan esclude («nessun breaking change: tutte le chiavi sono nuove»).

I casi coprono i percorsi che le tre issue toccano: la durata del grano
(scalare, envelope, con banda, con unita'), i tre modi di densita' di oggi
(default `fill_factor: 2`, `fill_factor`, `density` con `distribution`), piu'
voci con `scatter`.
"""
import json
import os

import numpy as np
import pytest
import soundfile as sf

from pge.core.stream import Stream
from pge.rendering.stream_cache_manager import StreamCacheManager

_QUI = os.path.dirname(__file__)
_ISTANTANEA = os.path.join(_QUI, 'fixtures', 'grani_senza_mappe.json')
_SAMPLE = 'silenzio.wav'
_SEED = 1441

CASI = {
    'default_fill_factor': {},
    'fill_factor_esplicito': {'fill_factor': 4},
    'density_sincrona': {'density': 20},
    'density_asincrona': {'density': 30, 'distribution': 0.7},
    'durata_envelope': {
        'grain': {'duration': [[0, 0.02], [2, 0.1]], 'envelope': 'hanning'}},
    'durata_con_banda': {
        'density': 25,
        'grain': {'duration': 0.05, 'duration_range': 0.02,
                  'envelope': 'hanning'}},
    'durata_in_millisecondi': {
        'density': 25,
        'grain': {'duration': 40, 'duration_unit': 'milliseconds',
                  'envelope': 'hanning'}},
    'tre_voci_con_scatter': {
        'density': 20, 'distribution': 0.5,
        'voices': {'num_voices': 3, 'scatter': 0.6}},
}


def _params(extra):
    params = {
        'stream_id': 's1',
        'onset': 0.0,
        'duration': 2.0,
        'sample': _SAMPLE,
        'grain': {'duration': 0.05, 'envelope': 'hanning'},
    }
    params.update(extra)
    return params


def _grani(params, samples_dir):
    """I grani dello stream, voce per voce, come liste di numeri."""
    stream = Stream(params, seed=_SEED, samples_dir=samples_dir)
    stream.sample_table_num = 1
    stream.window_table_map = {'hanning': 2}
    return [
        [[g.onset, g.duration, g.pointer_pos, g.pitch_ratio, g.volume, g.pan]
         for g in voce]
        for voce in stream.voices
    ]


def _fingerprint(params):
    return StreamCacheManager(
        cache_path='inutile.json', renderer_type='numpy', seed=_SEED,
    ).compute_fingerprint(params)


def calcola(samples_dir):
    """L'istantanea, calcolata sul motore di adesso."""
    return {
        nome: {'grani': _grani(_params(extra), samples_dir),
               'fingerprint': _fingerprint(_params(extra))}
        for nome, extra in CASI.items()
    }


@pytest.fixture(scope='module')
def samples_dir(tmp_path_factory):
    cartella = tmp_path_factory.mktemp('samples')
    sf.write(str(cartella / _SAMPLE), np.zeros(48000, dtype='float32'), 48000)
    return str(cartella)


@pytest.fixture(scope='module')
def di_prima():
    with open(_ISTANTANEA, encoding='utf-8') as f:
        return json.load(f)


class TestSenzaMappeNienteCambia:

    def test_l_istantanea_copre_ogni_caso(self, di_prima):
        """Un caso aggiunto qui senza la sua istantanea non confronta niente."""
        assert set(di_prima) == set(CASI)

    @pytest.mark.parametrize('nome', sorted(CASI))
    def test_gli_stessi_grani_di_prima(self, nome, samples_dir, di_prima):
        grani = _grani(_params(CASI[nome]), samples_dir)
        attesi = di_prima[nome]['grani']
        assert len(grani) == len(attesi)
        assert sum(len(v) for v in grani) > 0, "lo stream non ha grani"
        # Uguaglianza esatta, non approssimata: gli stessi float, bit per bit.
        # json serializza un float con repr, che lo rilegge identico.
        assert grani == attesi

    @pytest.mark.parametrize('nome', sorted(CASI))
    def test_lo_stesso_fingerprint_di_prima(self, nome, di_prima):
        assert _fingerprint(_params(CASI[nome])) == di_prima[nome]['fingerprint']
