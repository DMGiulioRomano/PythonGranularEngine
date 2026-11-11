"""
Partitura ed export su uno stream che scrive un'espressione su ogni campo
in cui vale (issue #313, mappe caotiche 5/7), con una mappa a due variabili
e una scritta a mano.

Dopo la #308 chi legge lo stream — partitura, sessione Sonic Visualiser,
commenti dello score, grain JSON — incontrava un'espressione sulla sola
durata del grano. Ora la puo' incontrare su volume, pan, pitch, densita',
verso: qui si chiede che nessuno cada. Mostrare quei valori e' la 6/7
(#314).
"""
import json
import os

import numpy as np
import pytest
import soundfile as sf
import yaml

from pge import api
from pge.rendering.envelope_extractor import get_stream_envelopes
from pge.rendering.stream_cache_manager import StreamCacheManager

SAMPLE = 'tono.wav'


def _stream(**extra):
    stream = {
        'stream_id': 's1',
        'sample': SAMPLE,
        'duration': 3.0,
        'maps': {
            'm1': {'type': 'henon', 'r': 1.4},
            'm2': {'type': 'custom', 'x': 'sin(r*x)*cos(x)', 'r': 3},
            'm3': {'type': 'circle', 'r': 0.42, 'clock': 6},
        },
        'volume': '(-18 + 4*m1)',
        'pan': '(100*m1.y)',
        'pitch': {'semitones': '(12*m2)'},
        'density': '(15 + 10*m3)',
        'distribution': '(0.5*m3)',
        'grain': {'duration': '(0.04 + 0.02*m3)',
                  'read_direction': '(sign(m1 - 0.3))'},
        'pointer': {'position': '(m3)', 'loop_start': 0.2, 'loop_dur': 0.5},
    }
    stream.update(extra)
    return stream


@pytest.fixture
def brano(tmp_path):
    refs = tmp_path / 'refs'
    refs.mkdir()
    sr = 48000
    t = np.arange(2 * sr) / sr
    sf.write(str(refs / SAMPLE),
             (0.2 * np.sin(2 * np.pi * 220 * t)).astype('float32'), sr)
    path = tmp_path / 'brano.yml'
    path.write_text(yaml.safe_dump(
        {'seed': 1441, 'streams': [_stream()]}, sort_keys=False),
        encoding='utf-8')
    generator = api.load_generator(str(path), samples_dir=str(refs))
    return generator, tmp_path, str(refs)


class TestIlBranoRende:

    def test_il_caricamento_non_scrive_su_stdout(self, tmp_path, capsys):
        refs = tmp_path / 'refs'
        refs.mkdir()
        sf.write(str(refs / SAMPLE), np.zeros(96000, dtype='float32'), 48000)
        path = tmp_path / 'brano.yml'
        path.write_text(yaml.safe_dump(
            {'seed': 1441, 'streams': [_stream()]}, sort_keys=False),
            encoding='utf-8')
        from pge.engine.generator import Generator
        generator = Generator(str(path), samples_dir=str(refs))
        generator.load_yaml()
        assert 'impossibile valutare' not in capsys.readouterr().out

    def test_i_grani_hanno_valori_finiti_e_diversi(self, brano):
        generator, _, _ = brano
        stream, = generator.streams
        grani = stream.voices[0]
        assert len(grani) > 30
        for campo in ('volume', 'pan', 'pitch_ratio', 'duration',
                      'pointer_pos', 'onset'):
            valori = [getattr(g, campo) for g in grani]
            assert all(np.isfinite(v) for v in valori), campo
            assert len({round(v, 6) for v in valori}) > 5, campo
        assert {g.pitch_ratio > 0 for g in grani} == {True, False}

    def test_il_render_numpy(self, brano):
        generator, tmp_path, refs = brano
        risultato = api.render(generator, str(tmp_path / 'brano.wav'),
                               renderer='numpy', samples_dir=refs)
        assert os.path.getsize(risultato.audio_paths[0]) > 1000

    def test_due_render_danno_gli_stessi_grani(self, tmp_path):
        """Le mappe sono deterministiche, e `distribution` pesca da un RNG
        col suo seed."""
        grani = []
        for giro in ('a', 'b'):
            cartella = tmp_path / giro
            cartella.mkdir()
            refs = cartella / 'refs'
            refs.mkdir()
            sf.write(str(refs / SAMPLE),
                     np.zeros(96000, dtype='float32'), 48000)
            path = cartella / 'brano.yml'
            path.write_text(yaml.safe_dump(
                {'seed': 1441, 'streams': [_stream()]}, sort_keys=False),
                encoding='utf-8')
            generator = api.load_generator(str(path), samples_dir=str(refs))
            grani.append([(g.onset, g.pointer_pos, g.pitch_ratio, g.volume,
                           g.pan, g.duration)
                          for g in generator.streams[0].voices[0]])
        assert grani[0] == grani[1]


class TestChiLeggeLoStreamNonCade:

    def test_l_estrattore_delle_curve(self, brano):
        generator, _, _ = brano
        stream, = generator.streams
        get_stream_envelopes(stream, show_static=True,
                             show_voice_offsets=True)

    def test_la_partitura_pdf(self, brano):
        generator, tmp_path, refs = brano
        pdf = api.export_score_pdf(
            generator, str(tmp_path / 'brano.pdf'),
            config={'show_static_params': True}, samples_dir=refs)
        assert os.path.getsize(pdf) > 1000

    def test_la_sessione_sonic_visualiser(self, brano):
        generator, tmp_path, refs = brano
        audio = str(tmp_path / 'brano.wav')
        api.render(generator, audio, renderer='numpy', samples_dir=refs)
        sessione = api.export_sv(generator, audio, str(tmp_path / 'brano.sv'))
        assert os.path.getsize(sessione) > 100

    def test_il_grain_json(self, brano):
        generator, tmp_path, _ = brano
        generator.streams[0].voices
        path, = api.export_grain_json(generator, str(tmp_path), 'brano')
        with open(path, encoding='utf-8') as f:
            json.load(f)

    def test_lo_score_csound_dice_le_espressioni(self, brano):
        generator, tmp_path, _ = brano
        sco = str(tmp_path / 'brano.sco')
        generator.generate_score_file(sco)
        with open(sco, encoding='utf-8') as f:
            testo = f.read()
        assert '(15 + 10*m3)' in testo
        assert '(0.04 + 0.02*m3)' in testo
        assert testo.count('\ni') > 30


class TestFingerprint:

    def _fingerprint(self, stream):
        return StreamCacheManager(
            cache_path='inutile.json', renderer_type='numpy', seed=1441,
        ).compute_fingerprint(stream)

    def test_cambia_con_ogni_espressione_e_con_l_equazione(self):
        base = _stream()
        varianti = [
            _stream(volume='(-18 + 5*m1)'),
            _stream(pan='(90*m1.y)'),
            _stream(pitch={'semitones': '(7*m2)'}),
            _stream(density='(15 + 11*m3)'),
        ]
        altra = _stream()
        altra['maps'] = {**altra['maps'],
                         'm2': {'type': 'custom', 'x': 'sin(r*x)', 'r': 3}}
        impronte = {self._fingerprint(s) for s in [base, altra] + varianti}
        assert len(impronte) == 6
