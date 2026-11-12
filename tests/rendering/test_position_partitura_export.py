"""
Partitura ed export su uno stream che legge la posizione da
`pointer.position` (issue #312, mappe caotiche 4/7).

Due cose. Che la partitura disegni i grani **alle posizioni lette**: il
poligono di un grano parte dalla sua posizione nel buffer, e con `position`
quella posizione non e' piu' su una retta. E che chi legge lo stream — PDF,
sessione Sonic Visualiser, grain JSON, score Csound — non cada su una
velocita' che non c'e'.
"""
import bz2
import json
import os

import numpy as np
import pytest
import soundfile as sf
import yaml

from pge import api
from pge.rendering import grain_visuals
from pge.rendering.envelope_extractor import (
    ENVELOPE_COLORS, ENVELOPE_STYLES, PLOT_ENVELOPE_KEYS, get_stream_envelopes)
from pge.rendering.page_layout import legend_display_name
from pge.rendering.score_visualizer import ScoreVisualizer

SAMPLE = 'tono.wav'


def _brano(tmp_path, pointer):
    refs = tmp_path / 'refs'
    refs.mkdir(exist_ok=True)
    sr = 48000
    t = np.arange(2 * sr) / sr
    sf.write(str(refs / SAMPLE),
             (0.2 * np.sin(2 * np.pi * 220 * t)).astype('float32'), sr)
    documento = {'seed': 1441, 'streams': [{
        'stream_id': 's1',
        'sample': SAMPLE,
        'duration': 3.0,
        'density': 12,
        'maps': {'m1': {'type': 'logistic', 'r': 3.2}},
        'grain': {'duration': 0.05},
        'pointer': pointer,
    }]}
    path = tmp_path / 'brano.yml'
    path.write_text(yaml.safe_dump(documento, sort_keys=False),
                    encoding='utf-8')
    generator = api.load_generator(str(path), samples_dir=str(refs))
    return generator, tmp_path, str(refs)


@pytest.fixture
def brano(tmp_path):
    return _brano(tmp_path, {
        'position': '(m1)', 'loop_start': 0.2, 'loop_dur': 0.1,
        'loop_unit': 'normalized'})


@pytest.fixture
def scrub(tmp_path):
    return _brano(tmp_path, {'position': [[0, 0.1], [3, 0.9]]})


class TestIGraniAllePosizioniLette:

    def test_il_poligono_parte_dalla_posizione_letta(self, brano):
        generator, _, _ = brano
        stream, = generator.streams
        grani = stream.voices[0]
        for grano in grani:
            vertici = grain_visuals.arrow_vertices(grano)
            ys = [y for _, y in vertici]
            assert min(ys) == pytest.approx(grano.pointer_pos)

    def test_le_altezze_in_partitura_sono_due(self, brano):
        """r = 3.2: due posizioni, a 0.513 e 0.799 della finestra 0.4-0.6 s."""
        generator, _, _ = brano
        stream, = generator.streams
        basi = {round(min(y for _, y in grain_visuals.arrow_vertices(g)), 4)
                for g in stream.voices[0]}
        assert len(basi) == 2
        assert {round((b - 0.4) / 0.2, 2) for b in basi} == {0.51, 0.80}

    def test_la_pagina_si_disegna_coi_grani(self, brano):
        generator, _, refs = brano
        visualizer = ScoreVisualizer(generator, {'samples_dir': refs})
        visualizer.analyze()
        figura = visualizer.render_page(0)
        try:
            # un poligono per grano, da qualche parte nella pagina
            poligoni = sum(len(ax.collections) + len(ax.patches)
                           for ax in figura.axes)
            assert poligoni > 0
        finally:
            import matplotlib.pyplot as plt
            plt.close(figura)


class TestLaCurva:

    def test_un_espressione_non_e_una_curva_dichiarata(self, brano):
        """Mostrarne i valori realizzati e' la 6/7 (#314): qui non cade e
        non pubblica una curva che non c'e'."""
        generator, _, _ = brano
        stream, = generator.streams
        curve = get_stream_envelopes(stream, show_static=True)
        assert 'pointer_speed' not in curve

    def test_un_envelope_e_una_curva_pubblicata(self, scrub):
        generator, _, _ = scrub
        stream, = generator.streams
        curve = get_stream_envelopes(stream)
        assert 'pointer_position' in curve
        assert [y for _, y in curve['pointer_position'].breakpoints] == [
            0.1, 0.9]

    def test_la_velocita_non_si_pubblica_nemmeno_come_statica(self, scrub):
        generator, _, _ = scrub
        stream, = generator.streams
        assert 'pointer_speed' not in get_stream_envelopes(
            stream, show_static=True)

    def test_senza_position_la_velocita_resta(self, tmp_path):
        generator, _, _ = _brano(tmp_path, {'speed_ratio': 0.5})
        stream, = generator.streams
        curve = get_stream_envelopes(stream, show_static=True)
        assert 'pointer_speed' in curve
        assert 'pointer_position' not in curve

    def test_il_nome_ha_colore_stile_e_legenda(self):
        assert 'pointer_position' in ENVELOPE_COLORS
        assert 'pointer_position' in ENVELOPE_STYLES
        assert 'pointer_position' in PLOT_ENVELOPE_KEYS
        assert legend_display_name('pointer_position') == 'ptr pos'

    def test_la_coppia_bw_e_solo_sua(self):
        coppia = ENVELOPE_STYLES['pointer_position']
        assert [k for k, v in ENVELOPE_STYLES.items() if v == coppia] == [
            'pointer_position']

    def test_il_filtro_la_seleziona_per_nome(self, scrub):
        generator, _, _ = scrub
        stream, = generator.streams
        curve = get_stream_envelopes(
            stream, envelope_filter={'pointer_position'})
        assert set(curve) == {'pointer_position'}


class TestRenderEdExport:

    def test_il_render_numpy(self, brano):
        generator, tmp_path, refs = brano
        risultato = api.render(generator, str(tmp_path / 'brano.wav'),
                               renderer='numpy', samples_dir=refs)
        assert os.path.getsize(risultato.audio_paths[0]) > 1000
        assert risultato.grain_counts['s1'].grains > 20

    def test_la_partitura_pdf(self, brano):
        generator, tmp_path, refs = brano
        pdf = api.export_score_pdf(
            generator, str(tmp_path / 'brano.pdf'),
            config={'show_static_params': True}, samples_dir=refs)
        assert os.path.getsize(pdf) > 1000

    def test_la_partitura_pdf_con_lo_scrub(self, scrub):
        generator, tmp_path, refs = scrub
        pdf = api.export_score_pdf(
            generator, str(tmp_path / 'scrub.pdf'), samples_dir=refs)
        assert os.path.getsize(pdf) > 1000

    def test_la_sessione_sonic_visualiser(self, scrub):
        generator, tmp_path, refs = scrub
        audio = str(tmp_path / 'brano.wav')
        api.render(generator, audio, renderer='numpy', samples_dir=refs)
        sessione = api.export_sv(generator, audio, str(tmp_path / 'brano.sv'))
        with open(sessione, 'rb') as f:      # una sessione .sv e' bz2
            xml = bz2.decompress(f.read()).decode('utf-8')
        assert 'pointer_position' in xml
        assert 'pointer_speed' not in xml

    def test_il_grain_json_porta_le_posizioni_lette(self, brano):
        generator, tmp_path, _ = brano
        stream, = generator.streams
        attese = [g.pointer_pos for g in stream.voices[0]]
        path, = api.export_grain_json(generator, str(tmp_path), 'brano')
        with open(path, encoding='utf-8') as f:
            testo = f.read()
        json.loads(testo)
        assert f'{attese[0]:.4f}'[:5] in testo

    def test_lo_score_csound(self, brano):
        generator, tmp_path, _ = brano
        sco = str(tmp_path / 'brano.sco')
        generator.generate_score_file(sco)
        with open(sco, encoding='utf-8') as f:
            testo = f.read()
        assert testo.count('\ni') > 20
