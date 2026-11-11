"""
Partitura ed export su uno stream che legge una mappa (issue #308, mappe
caotiche 1/7): non si rompono su un parametro scritto come espressione.

Tutto dall'API pubblica (`pge.api`), su file veri: il render NumPy, la
partitura PDF, la sessione Sonic Visualiser, il grain JSON, lo score Csound.
Mostrare le mappe in partitura e' un'altra fetta (6/7, #314): qui si chiede
solo che un valore che non e' ne' un numero ne' un envelope non faccia cadere
niente, e che non venga raccontato come «illeggibile».
"""
import json
import os
from unittest.mock import patch

import numpy as np
import pytest
import soundfile as sf
import yaml

from pge import api
from pge.parameters.parameter_curve import ABSENT, ParameterCurve
from pge.rendering.envelope_extractor import get_stream_envelopes

SAMPLE = 'tono.wav'
ESPRESSIONE = '(0.02 + 0.08*m1)'


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
        'duration': 2.0,
        'volume': [[0, -6], [2, -12]],
        'maps': {'m1': {'type': 'logistic', 'r': 3.5}},
        'grain': {'duration': ESPRESSIONE},
    }]}
    path = tmp_path / 'brano.yml'
    path.write_text(yaml.safe_dump(documento, sort_keys=False),
                    encoding='utf-8')
    generator = api.load_generator(str(path), samples_dir=str(refs))
    return generator, tmp_path, str(refs)


class TestLeCurve:

    def test_un_espressione_non_ha_una_curva(self, brano):
        generator, _, _ = brano
        stream, = generator.streams
        curva = stream.grain_duration.value_curve
        assert curva.kind == ABSENT
        assert ParameterCurve.classify(stream.grain_duration.value).kind == ABSENT

    def test_l_estrattore_la_salta_senza_dirla_illeggibile(self, brano):
        generator, _, _ = brano
        stream, = generator.streams
        with patch('pge.shared.logger.log_unreadable_curve_warning') as avviso:
            curve = get_stream_envelopes(stream, show_static=True,
                                         show_voice_offsets=True)
        assert 'grain_duration' not in curve
        assert 'volume' in curve, "le altre curve dello stream ci sono"
        assert avviso.call_count == 0

    def test_la_densita_effettiva_non_si_campiona_su_un_espressione(self, brano):
        """In modalita' `fill_factor` la densita' vera e'
        fill_factor / grain_duration: con la durata presa da una mappa non
        e' una funzione del tempo, e la curva non c'e' (non e' un errore)."""
        generator, _, _ = brano
        stream, = generator.streams
        assert stream.effective_density_curve is None

    def test_il_repr_del_parametro_dice_l_espressione(self, brano):
        generator, _, _ = brano
        stream, = generator.streams
        assert ESPRESSIONE in repr(stream.grain_duration)


class TestRenderEdExport:

    def test_il_render_numpy_scrive_l_audio(self, brano):
        generator, tmp_path, refs = brano
        uscita = str(tmp_path / 'brano.wav')
        risultato = api.render(generator, uscita, renderer='numpy',
                               samples_dir=refs)
        assert os.path.getsize(risultato.audio_paths[0]) > 1000
        assert risultato.grain_counts['s1'].grains > 10

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

    def test_il_grain_json_porta_le_durate_del_ciclo(self, brano):
        generator, tmp_path, _ = brano
        generator.streams[0].voices        # la generazione e' lazy
        path, = api.export_grain_json(generator, str(tmp_path), 'brano')
        with open(path, encoding='utf-8') as f:
            testo = f.read()
        json.loads(testo)
        assert len(testo) > 100

    def test_lo_score_csound_scrive_l_espressione_nel_commento(self, brano):
        generator, tmp_path, _ = brano
        sco = str(tmp_path / 'brano.sco')
        generator.generate_score_file(sco)
        with open(sco, encoding='utf-8') as f:
            testo = f.read()
        assert f'Grain duration: {ESPRESSIONE}' in testo
