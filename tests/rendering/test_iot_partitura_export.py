"""
Partitura ed export su uno stream che prende gli onset da `grain.iot` (issue
#311, mappe caotiche 3/7).

Con `grain.iot` la densita' non e' dichiarata: `density`, `fill_factor` e
`distribution` sono None, e la densita' che emerge e' una curva pubblicata
come `effective_density`, come in modalita' `fill_factor`. Qui si chiede che
chi legge quelle tre — la partitura, la sessione Sonic Visualiser, i commenti
dello score, la riga di fine render — non cada su un None, e che la curva
arrivi fin li'.
"""
import bz2
import os

import numpy as np
import pytest
import soundfile as sf
import yaml

from pge import api
from pge.cli import _stream_timing
from pge.rendering.envelope_extractor import get_stream_envelopes

SAMPLE = 'tono.wav'
IOT = '(0.020 + 0.180*m1)'


@pytest.fixture
def brano(tmp_path):
    refs = tmp_path / 'refs'
    refs.mkdir()
    sr = 48000
    t = np.arange(sr) / sr
    sf.write(str(refs / SAMPLE),
             (0.2 * np.sin(2 * np.pi * 220 * t)).astype('float32'), sr)
    documento = {'seed': 1441, 'streams': [{
        'stream_id': 's1',
        'sample': SAMPLE,
        'duration': 3.0,
        'maps': {'m1': {'type': 'logistic', 'r': 3.5}},
        'grain': {'iot': IOT, 'duration': '(0.020 + 0.080*m1)'},
    }]}
    path = tmp_path / 'brano.yml'
    path.write_text(yaml.safe_dump(documento, sort_keys=False),
                    encoding='utf-8')
    generator = api.load_generator(str(path), samples_dir=str(refs))
    return generator, tmp_path, str(refs)


class TestLaCurvaArrivaAChiLaLegge:

    def test_l_estrattore_pubblica_la_densita_emersa(self, brano):
        generator, _, _ = brano
        stream, = generator.streams
        curve = get_stream_envelopes(stream)
        assert 'effective_density' in curve
        valori = {round(y, 1) for _, y in curve['effective_density'].breakpoints}
        assert valori == {5.6, 5.9, 9.1, 11.2}

    def test_non_pubblica_curve_che_non_ci_sono(self, brano):
        generator, _, _ = brano
        stream, = generator.streams
        curve = get_stream_envelopes(stream, show_static=True)
        for nome in ('density', 'fill_factor', 'distribution'):
            assert nome not in curve

    def test_l_attesa_e_la_durata_hanno_la_loro_curva(self, brano):
        """Nella #311 dell'attesa si pubblicava solo la densita' emersa.
        Dalla #314 `grain_iot` e `grain_duration` sono curve anche loro: i
        valori che hanno avuto, grano per grano."""
        generator, _, _ = brano
        stream, = generator.streams
        curve = get_stream_envelopes(stream)
        assert {round(v * 1000) for _, v in
                curve['grain_iot'].breakpoints} == {169, 110, 177, 89}
        assert {round(v * 1000) for _, v in
                curve['grain_duration'].breakpoints} == {86, 60, 90, 51}

    def test_il_filtro_la_seleziona_per_nome(self, brano):
        generator, _, _ = brano
        stream, = generator.streams
        curve = get_stream_envelopes(
            stream, envelope_filter={'effective_density'})
        assert set(curve) == {'effective_density'}


class TestRenderEdExport:

    def test_il_render_numpy(self, brano):
        generator, tmp_path, refs = brano
        risultato = api.render(generator, str(tmp_path / 'brano.wav'),
                               renderer='numpy', samples_dir=refs)
        assert os.path.getsize(risultato.audio_paths[0]) > 1000
        # 3 secondi a 7.3 grani/s in media
        assert 18 <= risultato.grain_counts['s1'].grains <= 24

    def test_la_partitura_pdf_con_la_curva(self, brano):
        generator, tmp_path, refs = brano
        pdf = api.export_score_pdf(
            generator, str(tmp_path / 'brano.pdf'),
            config={'show_static_params': True}, samples_dir=refs)
        assert os.path.getsize(pdf) > 1000

    def test_la_sessione_sonic_visualiser_ha_il_layer_della_densita(self, brano):
        generator, tmp_path, refs = brano
        audio = str(tmp_path / 'brano.wav')
        api.render(generator, audio, renderer='numpy', samples_dir=refs)
        sessione = api.export_sv(generator, audio, str(tmp_path / 'brano.sv'))
        with open(sessione, 'rb') as f:      # una sessione .sv e' bz2
            xml = bz2.decompress(f.read()).decode('utf-8')
        assert 'effective_density' in xml

    def test_lo_score_csound_dice_l_attesa_al_posto_della_densita(self, brano):
        generator, tmp_path, _ = brano
        sco = str(tmp_path / 'brano.sco')
        generator.generate_score_file(sco)
        with open(sco, encoding='utf-8') as f:
            testo = f.read()
        assert f'; Inter-onset: {IOT}' in testo
        assert '; Density:' not in testo
        assert '; Distribution:' not in testo

    def test_la_riga_di_fine_render_dice_iot(self, brano):
        generator, _, _ = brano
        stream, = generator.streams
        assert _stream_timing(stream) == 'onset 0s · dur 3s · iot'
