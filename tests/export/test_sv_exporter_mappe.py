"""
La sessione Sonic Visualiser di uno stream con le mappe (issue #314, mappe
caotiche 6/7): porta le stesse curve della partitura, nello stesso ordine.

Partitura ed export leggono le curve dallo stesso posto
(`envelope_extractor.get_stream_envelopes`): qui si verifica che l'export
non ne perda nessuna per strada — una curva con un punto per grano, a
gradini, e una continua campionata sono forme che prima non gli arrivavano.
"""
import bz2
import xml.etree.ElementTree as ET

import numpy as np
import pytest
import soundfile as sf
import yaml

from pge import api
from pge.rendering.envelope_extractor import (
    ENVELOPE_COLORS, get_stream_envelopes)

SAMPLE = 'tono.wav'


@pytest.fixture
def sessione(tmp_path):
    refs = tmp_path / 'refs'
    refs.mkdir()
    sr = 48000
    t = np.arange(2 * sr) / sr
    sf.write(str(refs / SAMPLE),
             (0.2 * np.sin(2 * np.pi * 220 * t)).astype('float32'), sr)
    documento = {'seed': 1441, 'streams': [{
        'stream_id': 's1', 'sample': SAMPLE, 'duration': 3.0, 'onset': 0.5,
        'maps': {
            'm1': {'type': 'henon', 'r': 1.4},
            'm2': {'type': 'logistic', 'r': 3.5, 'clock': 4},
            'm3': {'type': 'sine', 'r': [[0, 3.0], [3, 4.0]], 'iterate': 5},
        },
        'volume': [[0, -12], [3, -3]],
        'pan': '(100*m1.y)',
        'pitch': {'semitones': '(12*m2)'},
        'grain': {'iot': '(0.05 + 0.1*m2)',
                  'duration': '(0.04 + 0.01*m3)'},
        'pointer': {'position': '(frac(m1))'},
    }]}
    path = tmp_path / 'brano.yml'
    path.write_text(yaml.safe_dump(documento, sort_keys=False),
                    encoding='utf-8')
    generator = api.load_generator(str(path), samples_dir=str(refs))
    audio = str(tmp_path / 'brano.wav')
    api.render(generator, audio, renderer='numpy', samples_dir=str(refs))
    file_sv = api.export_sv(generator, audio, str(tmp_path / 'brano.sv'))
    with open(file_sv, 'rb') as f:              # una sessione .sv e' bz2
        testo = bz2.decompress(f.read()).decode('utf-8')
    radice = ET.fromstring(testo.split('sonic-visualiser>', 1)[1])
    return generator.streams[0], radice


def _layer(radice):
    return [l for l in radice.findall('.//data/layer')
            if l.get('type') == 'timevalues']


def _punti(radice, layer):
    modello = next(m for m in radice.findall('.//data/model')
                   if m.get('id') == layer.get('model'))
    dataset = next(d for d in radice.findall('.//data/dataset')
                   if d.get('id') == modello.get('dataset'))
    return dataset.findall('point')


class TestLeStesseCurveDellaPartitura:

    def test_gli_stessi_nomi_nello_stesso_ordine(self, sessione):
        stream, radice = sessione
        curve = list(get_stream_envelopes(stream))
        nomi = [l.get('name') for l in _layer(radice)]
        assert nomi == curve
        for attesa in ('pan', 'pitch', 'grain_duration', 'grain_iot',
                       'effective_density', 'pointer_position',
                       'map__m1', 'map__m1.y', 'map__m2', 'map__m3',
                       'volume'):
            assert attesa in nomi

    def test_la_curva_realizzata_ha_un_punto_per_grano(self, sessione):
        stream, radice = sessione
        grani = stream.voices[0]
        layer = next(l for l in _layer(radice)
                     if l.get('name') == 'pan')
        punti = _punti(radice, layer)
        assert len(punti) == len(grani)
        assert [float(p.get('value')) for p in punti] == pytest.approx(
            [g.pan for g in grani], abs=1e-4)

    def test_i_tempi_portano_l_onset_dello_stream(self, sessione):
        stream, radice = sessione
        layer = next(l for l in _layer(radice)
                     if l.get('name') == 'pan')
        primo = _punti(radice, layer)[0]
        assert int(primo.get('frame')) == round(
            stream.voices[0][0].onset * 48000)

    @pytest.mark.parametrize('curva, stile', [
        ('pan', '8'),            # valori realizzati: a gradini
        ('map__m1', '8'),        # clock: grain
        ('map__m2', '8'),        # clock a orologio
        ('map__m3', '3'),        # iterate: continua
        ('volume', '3'),         # dichiarata, lineare
    ])
    def test_lo_stile_segue_la_forma_della_curva(self, sessione, curva,
                                                 stile):
        _, radice = sessione
        layer = next(l for l in _layer(radice)
                     if l.get('name') == curva)
        assert layer.get('plotStyle') == stile

    def test_le_mappe_hanno_il_loro_colore(self, sessione):
        _, radice = sessione
        for nome in ('map__m1', 'map__m1.y', 'map__m3'):
            layer = next(l for l in _layer(radice) if l.get('name') == nome)
            assert layer.get('colour') == ENVELOPE_COLORS['map']
        iot = next(l for l in _layer(radice) if l.get('name') == 'grain_iot')
        assert iot.get('colour') == ENVELOPE_COLORS['grain_iot']
