"""
Senza `pointer.position` il puntatore e' quello di prima, bit per bit (issue
#312, mappe caotiche 4/7).

`pointer.position` e' una seconda legge di moto, accanto a
`start + integrale di speed_ratio`. La prima non deve accorgersene.

«Di prima» e' un fatto, non un ricordo: l'istantanea in
`fixtures/grani_puntatore.json` e' stata presa al commit ead6729, prima della
prima riga della #312, quando `pointer_controller.py` era ancora quello di
`main` (b227567). Non si rigenera: se un caso diventa rosso, e' il motore ad
aver cambiato i grani di uno YAML che `position` non la nomina.

E' la gemella di `test_stream_senza_mappe_invariato.py`, che copre durata e
densita'; qui i casi sono quelli del puntatore: la velocita' (scalare,
envelope, negativa), `start`, la finestra di loop (statica, a cavallo della
fine del file, mobile), `offset_range`, gli offset di pointer delle voci,
`loop_unit`.
"""
import json
import os

import numpy as np
import pytest
import soundfile as sf

from pge.core.stream import Stream
from pge.rendering.stream_cache_manager import StreamCacheManager

_QUI = os.path.dirname(__file__)
_ISTANTANEA = os.path.join(_QUI, 'fixtures', 'grani_puntatore.json')
_SAMPLE = 'due_secondi.wav'
_SEED = 1441

CASI = {
    'default': {},
    'velocita_scalare': {'pointer': {'speed_ratio': 0.5}},
    'velocita_envelope': {'pointer': {'speed_ratio': [[0, 0.2], [2, 3.0]]}},
    'velocita_negativa': {'pointer': {'speed_ratio': -1.0, 'start': 1.5}},
    'start': {'pointer': {'start': 0.7}},
    'loop_statico': {
        'pointer': {'loop_start': 0.4, 'loop_end': 0.9, 'speed_ratio': 2.0}},
    'loop_a_cavallo': {
        'pointer': {'loop_start': 1.8, 'loop_dur': 0.5, 'speed_ratio': 1.5}},
    'loop_mobile': {
        'pointer': {'loop_start': [[0, 0.1], [2, 1.2]],
                    'loop_dur': [[0, 0.3], [2, 0.1]]}},
    'loop_normalizzato': {
        'pointer': {'loop_start': 0.2, 'loop_dur': 0.1,
                    'loop_unit': 'normalized'}},
    'offset_range': {
        'pointer': {'offset_range': 0.3, 'loop_start': 0.5, 'loop_dur': 0.4},
        'deviation_probability': 100},
    'voci_con_offset': {
        'density': 20, 'distribution': 0.4,
        'voices': {'num_voices': 3, 'scatter': 0.5,
                   'pointer': {'strategy': 'linear', 'step': 0.1}}},
    'verso_dichiarato': {
        'grain': {'duration': 0.05, 'envelope': 'hanning',
                  'read_direction': -1},
        'pointer': {'loop_start': 0.4, 'loop_dur': 0.6}},
}


def _params(extra):
    params = {
        'stream_id': 's1',
        'onset': 0.0,
        'duration': 2.0,
        'sample': _SAMPLE,
        'density': 25,
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


def scrivi_sample(cartella):
    sf.write(os.path.join(cartella, _SAMPLE),
             np.zeros(96000, dtype='float32'), 48000)


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
    scrivi_sample(str(cartella))
    return str(cartella)


@pytest.fixture(scope='module')
def di_prima():
    with open(_ISTANTANEA, encoding='utf-8') as f:
        return json.load(f)


class TestSenzaPositionIlPuntatoreEQuelloDiPrima:

    def test_l_istantanea_copre_ogni_caso(self, di_prima):
        """Un caso aggiunto qui senza la sua istantanea non confronta niente."""
        assert set(di_prima) == set(CASI)

    def test_i_casi_muovono_davvero_il_puntatore(self, di_prima):
        """Un'istantanea di posizioni tutte uguali non sorveglierebbe la
        legge di moto: ogni caso ha piu' di una posizione di lettura."""
        for nome, caso in di_prima.items():
            posizioni = {g[2] for voce in caso['grani'] for g in voce}
            assert len(posizioni) > 5, nome

    @pytest.mark.parametrize('nome', sorted(CASI))
    def test_gli_stessi_grani_di_prima(self, nome, samples_dir, di_prima):
        grani = _grani(_params(CASI[nome]), samples_dir)
        attesi = di_prima[nome]['grani']
        assert len(grani) == len(attesi)
        assert sum(len(v) for v in grani) > 0, "lo stream non ha grani"
        # Uguaglianza esatta, non approssimata: gli stessi float, bit per bit.
        assert grani == attesi

    @pytest.mark.parametrize('nome', sorted(CASI))
    def test_lo_stesso_fingerprint_di_prima(self, nome, di_prima):
        assert _fingerprint(_params(CASI[nome])) == di_prima[nome]['fingerprint']
