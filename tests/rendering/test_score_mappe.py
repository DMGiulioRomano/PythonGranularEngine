"""
La partitura di uno stream con le mappe (issue #314, mappe caotiche 6/7).

Le fette precedenti garantivano solo che la partitura non cadesse. Qui le
mappe si vedono: i valori realizzati di ogni parametro scritto come
espressione, il valore della mappa, la densita' emersa; in legenda il nome
e l'escursione vera.

E quello che NON deve cambiare: uno stream senza mappe ha le stesse curve,
nello stesso ordine, di prima — su un'istantanea presa al commit 1a68fa9,
prima della prima riga della #314.
"""
import json
import os

import matplotlib.pyplot as plt
import numpy as np
import pytest
import soundfile as sf
import yaml

from pge import api
from pge.rendering.envelope_extractor import get_stream_envelopes
from pge.rendering.score_visualizer import ScoreVisualizer
from tests.rendering import curve_senza_mappe

SAMPLE = 'tono.wav'
_ISTANTANEA = os.path.join(os.path.dirname(__file__), 'fixtures',
                           'curve_senza_mappe.json')


def _brano(tmp_path, **stream):
    refs = tmp_path / 'refs'
    refs.mkdir(exist_ok=True)
    sr = 48000
    t = np.arange(2 * sr) / sr
    sf.write(str(refs / SAMPLE),
             (0.2 * np.sin(2 * np.pi * 220 * t)).astype('float32'), sr)
    base = {'stream_id': 's1', 'sample': SAMPLE, 'duration': 3.0,
            'density': 8,
            'maps': {'m1': {'type': 'logistic', 'r': 3.5}},
            'grain': {'duration': '(0.02 + 0.08*m1)'}}
    base.update(stream)
    path = tmp_path / 'brano.yml'
    path.write_text(yaml.safe_dump({'seed': 1441, 'streams': [base]},
                                   sort_keys=False), encoding='utf-8')
    generator = api.load_generator(str(path), samples_dir=str(refs))
    return generator, str(refs)


def _pagina(generator, refs, **config):
    visualizer = ScoreVisualizer(generator, {'samples_dir': refs, **config})
    visualizer.analyze()
    return visualizer.render_page(0)


def _testi(figura):
    return [t.get_text() for ax in figura.axes for t in ax.texts]


def _linee_della_corsia(figura, stream_id='s1'):
    corsia, = [ax for ax in figura.axes
               if ax.get_label() == f'env:{stream_id}']
    return {linea.get_label(): linea for linea in corsia.get_lines()}


class TestLaPagina:

    def test_si_disegna_con_le_curve_realizzate(self, tmp_path):
        generator, refs = _brano(tmp_path)
        figura = _pagina(generator, refs)
        try:
            linee = _linee_della_corsia(figura)
            assert 'grain_duration' in linee
            assert 'map__m1' in linee
        finally:
            plt.close(figura)

    def test_la_curva_realizzata_e_a_gradini(self, tmp_path):
        generator, refs = _brano(tmp_path)
        figura = _pagina(generator, refs)
        try:
            linea = _linee_della_corsia(figura)['grain_duration']
            assert linea.get_drawstyle() == 'steps-post'
            # quattro altezze: il ciclo di quattro valori
            assert len({round(y, 6) for y in linea.get_ydata()}) == 4
        finally:
            plt.close(figura)

    def test_non_annota_un_valore_per_grano(self, tmp_path):
        """I breakpoint di una curva dichiarata si annotano coi loro
        valori; una curva realizzata ne ha uno per grano, e annotarli
        coprirebbe la corsia."""
        generator, refs = _brano(tmp_path, volume=[[0, -12], [3, -3]])
        figura = _pagina(generator, refs)
        try:
            corsia, = [ax for ax in figura.axes
                       if ax.get_label() == 'env:s1']
            annotazioni = [t.get_text() for t in corsia.texts]
            # i due breakpoint del volume, e nessuna durata in ms
            assert any('dB' in a for a in annotazioni)
            assert not any('ms' in a for a in annotazioni)
        finally:
            plt.close(figura)

    def test_in_legenda_il_nome_e_l_escursione_vera(self, tmp_path):
        """Scritto 20-100 ms, usato 51-90: e' il secondo il dato."""
        generator, refs = _brano(tmp_path)
        figura = _pagina(generator, refs)
        try:
            testi = _testi(figura)
            durata, = [t for t in testi if t.startswith('grain dur')]
            assert durata == 'grain dur\n50.6–90.0ms'
            mappa, = [t for t in testi if t.startswith('m1')]
            assert mappa == 'm1\n0.38–0.87'
        finally:
            plt.close(figura)

    def test_una_curva_dichiarata_in_legenda_ha_solo_il_nome(self, tmp_path):
        generator, refs = _brano(tmp_path, volume=[[0, -12], [3, -3]])
        figura = _pagina(generator, refs)
        try:
            assert 'volume' in _testi(figura)
        finally:
            plt.close(figura)

    def test_ogni_mappa_ha_la_sua_voce_di_legenda(self, tmp_path):
        generator, refs = _brano(
            tmp_path,
            maps={'m1': {'type': 'henon', 'r': 1.4},
                  'm2': {'type': 'tent', 'r': 3.2, 'clock': 6}},
            grain={'duration': '(0.05 + 0.01*m1)'}, pan='(40*m2 + m1.y)')
        figura = _pagina(generator, refs)
        try:
            nomi = [t.split('\n')[0] for t in _testi(figura)]
            for nome in ('m1', 'm1.y', 'm2'):
                assert nome in nomi
        finally:
            plt.close(figura)

    def test_il_preset_bianco_e_nero(self, tmp_path):
        generator, refs = _brano(tmp_path)
        figura = _pagina(generator, refs, bw=True)
        try:
            linee = _linee_della_corsia(figura)
            stili = {nome: (str(l.get_linestyle()), l.get_linewidth())
                     for nome, l in linee.items()}
            assert stili['map__m1'] != stili['grain_duration']
        finally:
            plt.close(figura)

    def test_il_pdf(self, tmp_path):
        generator, refs = _brano(tmp_path, pan='(90*m1)',
                                 pointer={'position': '(m1)'})
        pdf = api.export_score_pdf(generator, str(tmp_path / 'brano.pdf'),
                                   samples_dir=refs)
        assert os.path.getsize(pdf) > 1000

    def test_il_filtro_dalla_configurazione(self, tmp_path):
        generator, refs = _brano(tmp_path, pan='(90*m1)')
        figura = _pagina(generator, refs, envelope_filter={'map'})
        try:
            assert set(_linee_della_corsia(figura)) == {'map__m1'}
        finally:
            plt.close(figura)


class TestLeggereLeCurveNonCambiaIGrani:

    def _grani(self, generator):
        return [[(g.onset, g.duration, g.pointer_pos, g.pitch_ratio,
                  g.volume, g.pan) for g in voce]
                for voce in generator.streams[0].voices]

    CASO = dict(pan='(90*m1)', pan_range=30, distribution=0.7,
                deviation_probability={'pan': 100},
                voices={'num_voices': 2, 'scatter': 0.5})

    def test_prima_le_curve_poi_i_grani(self, tmp_path):
        """Leggere le curve genera i grani, una volta: nessuna estrazione
        casuale in piu'."""
        (tmp_path / 'a').mkdir()
        (tmp_path / 'b').mkdir()
        a, _ = _brano(tmp_path / 'a', **self.CASO)
        b, _ = _brano(tmp_path / 'b', **self.CASO)
        get_stream_envelopes(a.streams[0], show_static=True,
                             show_voice_offsets=True)
        assert self._grani(a) == self._grani(b)

    def test_rileggerle_non_li_sposta(self, tmp_path):
        generator, refs = _brano(tmp_path, **self.CASO)
        prima = self._grani(generator)
        for _ in range(3):
            get_stream_envelopes(generator.streams[0], show_static=True)
        figura = _pagina(generator, refs)
        plt.close(figura)
        assert self._grani(generator) == prima


@pytest.fixture(scope='module')
def samples_dir(tmp_path_factory):
    cartella = tmp_path_factory.mktemp('samples')
    curve_senza_mappe.scrivi_sample(str(cartella))
    return str(cartella)


@pytest.fixture(scope='module')
def di_prima():
    with open(_ISTANTANEA, encoding='utf-8') as f:
        return json.load(f)


class TestSenzaMappeLeCurveSonoQuelleDiPrima:

    def test_l_istantanea_copre_ogni_caso(self, di_prima):
        assert set(di_prima) == set(curve_senza_mappe.CASI)

    @pytest.mark.parametrize('nome', sorted(curve_senza_mappe.CASI))
    def test_le_stesse_curve_nello_stesso_ordine(self, nome, samples_dir,
                                                 di_prima):
        """Nomi, ordine, interpolazione e breakpoint: l'ordine e' quello
        dei layer della sessione Sonic Visualiser."""
        assert curve_senza_mappe.curve(nome, samples_dir) == di_prima[nome]
