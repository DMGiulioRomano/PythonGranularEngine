# tests/export/test_sv_exporter.py
"""
TDD suite per SVExporter (issue #150).

Terzo renderer della IR: esporta sessioni Sonic Visualiser (.sv, XML bzip2) con
gli envelope della IR come layer sincronizzati alla waveform.

Sezioni:
1. TestFrameConversion   - frame = round((onset + t) * sr); offset onset
2. TestEnvelopeLayers    - un modello/dataset/layer per envelope, colori, plotStyle
3. TestAudioModel        - modello waveform (mainModel, sampleRate, end, file)
4. TestLayout            - multi vs single: numero di pane
5. TestBz2RoundTrip      - generate/export producono bz2 valido e parseable
6. TestSampleRateFromFile- sr letto da soundfile.info se non iniettato
7. TestEdgeCases         - streams vuoti
8. TestChromeParity      - GOLDEN: scheletro SV identico ai .sv reali di SV

Lo "scheletro SV" e' tutto cio' che SV richiede per aprire e impaginare la
sessione, normalizzando via le parti che divergono dal prototipo by-design
(nome layer flat vs dotted, colori da ENVELOPE_COLORS, valori/frame, path audio).
"""

import bz2
import os
import sys
import types
import xml.etree.ElementTree as ET

import pytest
from unittest.mock import MagicMock

from envelopes.envelope import Envelope
from parameters.parameter import Parameter
from parameters.parameter_definitions import GRANULAR_PARAMETERS
from export.sv_exporter import SVExporter

FIX_DIR = os.path.join(os.path.dirname(__file__), 'fixtures', 'sv_reference')
SR = 48000
DUR = 65.0


# =============================================================================
# FIXTURES
# =============================================================================

def _param(name, value):
    return Parameter(name, value, GRANULAR_PARAMETERS[name])


def _stream(stream_id='s1', onset=0.0, duration=DUR, **params):
    s = MagicMock()
    s.stream_id = stream_id
    s.onset = onset
    s.duration = duration
    for k, v in params.items():
        setattr(s, k, v)
    return s


def _density_stream(onset=0.0):
    return _stream(onset=onset,
                   density=_param('density', Envelope([[0, 5.0], [DUR, 1000.0]])))


def _e3_stream():
    """grain_duration + density + distribution dinamici (scenario e3)."""
    return _stream(
        grain_duration=_param('grain_duration', Envelope([[0, 0.01], [DUR, 0.05]])),
        density=_param('density', Envelope([[0, 5.0], [DUR, 1000.0]])),
        distribution=_param('distribution', Envelope([[0, 0.0], [DUR, 1.0]])),
    )


def _build(streams, layout='multi', audio='AUDIO/x.aif', sr=SR, dur=DUR):
    return SVExporter().build(streams, audio_path=audio,
                              sample_rate=sr, duration_sec=dur, layout=layout)


def _points(root, layer_name=None):
    """Tutti i <point> dei dataset; opzionalmente del layer con quel name."""
    if layer_name is None:
        return root.findall('.//dataset/point')
    # risolvi name -> layer.model -> dataset
    layer = next(l for l in root.findall('.//data/layer')
                 if l.get('name') == layer_name)
    model = next(m for m in root.findall('.//data/model')
                 if m.get('id') == layer.get('model'))
    ds = next(d for d in root.findall('.//data/dataset')
              if d.get('id') == model.get('dataset'))
    return ds.findall('point')


def _load_ref(name):
    txt = open(os.path.join(FIX_DIR, name)).read()
    body = txt.split('sonic-visualiser>', 1)[1]
    return ET.fromstring(body)


# =============================================================================
# 1. FRAME CONVERSION
# =============================================================================

class TestFrameConversion:

    def test_frame_is_seconds_times_sr(self):
        root = _build([_density_stream(onset=0.0)])
        pts = _points(root, 'density')
        assert [p.get('frame') for p in pts] == [str(round(0 * SR)), str(round(DUR * SR))]

    def test_onset_offset_applied(self):
        # onset=2s deve traslare i frame: round((2 + t) * sr) (issue #150).
        root = _build([_density_stream(onset=2.0)])
        pts = _points(root, 'density')
        assert pts[0].get('frame') == str(round(2.0 * SR))
        assert pts[1].get('frame') == str(round((2.0 + DUR) * SR))

    def test_point_count_equals_breakpoints(self):
        env = Envelope([[0, 5.0], [20, 50.0], [DUR, 1000.0]])
        root = _build([_stream(density=_param('density', env))])
        assert len(_points(root, 'density')) == 3


# =============================================================================
# 2. ENVELOPE LAYERS
# =============================================================================

class TestEnvelopeLayers:

    def test_one_model_dataset_layer_per_envelope(self):
        root = _build([_e3_stream()])
        env_layers = [l for l in root.findall('.//data/layer')
                      if l.get('type') == 'timevalues']
        assert len(env_layers) == 3
        assert len(root.findall('.//data/dataset')) == 3
        # 1 wavefile + 3 sparse
        models = root.findall('.//data/model')
        assert sum(1 for m in models if m.get('type') == 'sparse') == 3

    def test_colour_from_envelope_colors(self):
        from rendering.score_visualizer import ENVELOPE_COLORS
        root = _build([_e3_stream()])
        for name in ('density', 'grain_duration', 'distribution'):
            layer = next(l for l in root.findall('.//data/layer')
                         if l.get('name') == name)
            assert layer.get('colour') == ENVELOPE_COLORS[name]

    def test_plotstyle_lines_and_vertical_scale(self):
        root = _build([_e3_stream()])
        for l in root.findall('.//data/layer'):
            if l.get('type') == 'timevalues':
                assert l.get('plotStyle') == '3'      # Lines
                assert l.get('verticalScale') == '0'

    def test_layer_names_are_engine_keys(self):
        root = _build([_e3_stream()])
        names = {l.get('name') for l in root.findall('.//data/layer')
                 if l.get('type') == 'timevalues'}
        assert names == {'grain_duration', 'density', 'distribution'}

    def test_multi_stream_names_prefixed_by_stream_id(self):
        s1 = _stream('a', density=_param('density', Envelope([[0, 5.0], [DUR, 1000.0]])))
        s2 = _stream('b', density=_param('density', Envelope([[0, 1.0], [DUR, 9.0]])))
        root = _build([s1, s2])
        names = {l.get('name') for l in root.findall('.//data/layer')
                 if l.get('type') == 'timevalues'}
        assert names == {'a/density', 'b/density'}


# =============================================================================
# 3. AUDIO MODEL
# =============================================================================

class TestAudioModel:

    def test_main_model_wavefile(self):
        m = _build([_density_stream()]).find('.//data/model[@id="0"]')
        assert m.get('type') == 'wavefile'
        assert m.get('mainModel') == 'true'
        assert m.get('sampleRate') == str(SR)
        assert m.get('start') == '0'
        assert m.get('end') == str(round(DUR * SR))

    def test_file_is_absolute(self):
        root = _build([_density_stream()], audio='refs/song.aif')
        m = root.find('.//data/model[@id="0"]')
        assert os.path.isabs(m.get('file'))

    def test_playparameters_present(self):
        pp = _build([_density_stream()]).find('.//data/playparameters')
        assert pp is not None and pp.get('model') == '0'


# =============================================================================
# 4. LAYOUT
# =============================================================================

class TestLayout:

    def test_multi_one_pane_per_envelope_plus_waveform(self):
        root = _build([_e3_stream()], layout='multi')
        assert len(root.findall('.//display/view')) == 4  # waveform + 3 env

    def test_single_one_env_pane(self):
        root = _build([_e3_stream()], layout='single')
        views = root.findall('.//display/view')
        assert len(views) == 2  # waveform + 1 env pane con tutti i layer
        env_pane = views[1]
        env_layers = [l for l in env_pane.findall('layer')
                      if l.get('type') == 'timevalues']
        assert len(env_layers) == 3


# =============================================================================
# 5. BZ2 ROUND-TRIP
# =============================================================================

class TestBz2RoundTrip:

    def test_generate_is_bzip2(self):
        blob = SVExporter().generate([_density_stream()], audio_path='x.aif',
                                     sample_rate=SR, duration_sec=DUR)
        assert blob[:3] == b'BZh'  # magic bzip2

    def test_roundtrip_parses_to_sv_root(self):
        blob = SVExporter().generate([_density_stream()], audio_path='x.aif',
                                     sample_rate=SR, duration_sec=DUR)
        xml = bz2.decompress(blob).decode('utf-8')
        assert '<!DOCTYPE sonic-visualiser>' in xml
        body = xml.split('sonic-visualiser>', 1)[1]
        assert ET.fromstring(body).tag == 'sv'

    def test_export_writes_file(self, tmp_path):
        out = str(tmp_path / 'out.sv')
        ret = SVExporter().export([_density_stream()], audio_path='x.aif',
                                  out_path=out, sample_rate=SR, duration_sec=DUR)
        assert ret == out
        assert open(out, 'rb').read()[:3] == b'BZh'


# =============================================================================
# 6. SAMPLE RATE DA FILE
# =============================================================================

class TestSampleRateFromFile:

    def test_reads_sr_and_duration_from_soundfile(self, monkeypatch):
        # build() senza sr/durata espliciti deve leggerli da soundfile.info
        # (header-only). Monkeypatch di sys.modules per isolare il test dal
        # modulo soundfile (reale o fake-da-altri-test) e fissare sr/frames.
        sr, frames = 44100, 44100 * 2  # 2 secondi
        info = types.SimpleNamespace(samplerate=sr, frames=frames)
        fake_sf = types.SimpleNamespace(info=lambda path: info)
        monkeypatch.setitem(sys.modules, 'soundfile', fake_sf)
        root = SVExporter().build([_density_stream()], audio_path='a.wav')
        m = root.find('.//data/model[@id="0"]')
        assert m.get('sampleRate') == str(sr)
        assert m.get('end') == str(round(2.0 * sr))


# =============================================================================
# 7. EDGE
# =============================================================================

class TestEdgeCases:

    def test_empty_streams_only_audio(self):
        root = _build([])
        assert root.find('.//data/model[@id="0"]') is not None
        env_layers = [l for l in root.findall('.//data/layer')
                      if l.get('type') == 'timevalues']
        assert env_layers == []

    def test_stream_without_dynamic_envelopes(self):
        # density statico -> nessun layer envelope (default show_static=False)
        s = _stream(density=_param('density', Envelope([[0, 50.0], [DUR, 50.0]])))
        root = _build([s])
        env_layers = [l for l in root.findall('.//data/layer')
                      if l.get('type') == 'timevalues']
        assert env_layers == []


# =============================================================================
# 8. CHROME PARITY (GOLDEN contro i .sv reali prodotti da Sonic Visualiser)
# =============================================================================

# Attributi che divergono dal prototipo by-design o sono audio/env-specifici:
# esclusi dallo scheletro confrontato.
_DROP = {'file', 'end', 'sampleRate', 'name', 'colour', 'colourName'}


def _skel(el):
    """Scheletro SV: (tag, attrs_filtrati, figli) senza i <point> (il loro
    conteggio e' verificato altrove) e senza gli attributi che divergono
    by-design. Cattura struttura, wiring degli id, geometria pane, plotStyle,
    dimensions: tutto cio' che garantisce che SV apra e impagini la sessione."""
    attrs = {k: v for k, v in el.attrib.items() if k not in _DROP}
    children = [_skel(c) for c in el if c.tag != 'point']
    return (el.tag, tuple(sorted(attrs.items())), children)


class TestChromeParity:

    def test_multi_skeleton_matches_real_sv(self):
        root = _build([_e3_stream()], layout='multi')
        assert _skel(root) == _skel(_load_ref('e3_multi.sv.xml'))

    def test_single_skeleton_matches_real_sv(self):
        root = _build([_e3_stream()], layout='single')
        assert _skel(root) == _skel(_load_ref('e3_single.sv.xml'))

    def test_single_envelope_skeleton_matches_real_sv(self):
        root = _build([_density_stream()], layout='multi')
        assert _skel(root) == _skel(_load_ref('e1__density.sv.xml'))
