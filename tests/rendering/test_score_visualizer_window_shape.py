# tests/rendering/test_score_visualizer_window_shape.py
"""
Suite per la rappresentazione della finestratura nella forma del grano
(variante "testa/bordo sagomato", flag opt-in grain_shape).

La finestra del grano (hanning, expodec, exporise, ...) e' oggi invisibile
nella partitura: tutti i grani sono frecce identiche. Con grain_shape='window'
il bordo superiore (la "testa") del grano traccia la curva della finestra,
mentre la base resta piatta sulla traccia del pointer.

Test divisi in:
- geometria pura (silhouette normalizzata + vertici del poligono), senza
  dipendere da matplotlib;
- comportamento del disegno (default invariato, branch window, fallback
  adattivo per grani troppo piccoli).
"""

import numpy as np
import pytest
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from unittest.mock import MagicMock, patch
from matplotlib.collections import PatchCollection

# Niente stub di soundfile in sys.modules (issue #182): e' una dipendenza
# dichiarata, e uno stub globale vince solo quando questo file gira da solo.

from pge.rendering.score_visualizer import ScoreVisualizer  # noqa: E402


# =============================================================================
# FACTORY
# =============================================================================

def make_grain(onset=0.0, duration=0.5, pointer_pos=0.5,
               pitch_ratio=1.0, volume=-6.0, envelope_table=10):
    g = MagicMock()
    g.onset = onset
    g.duration = duration
    g.pointer_pos = pointer_pos
    g.pitch_ratio = pitch_ratio
    g.volume = volume
    g.envelope_table = envelope_table
    return g


def make_stream(grains, window_table_map=None):
    s = MagicMock()
    s.voices = [grains]
    s.stream_id = 's1'
    s.onset = 0.0
    s.duration = 6.0
    if window_table_map is not None:
        s.window_table_map = window_table_map
    else:
        del s.window_table_map
    return s


def make_viz(config=None):
    gen = MagicMock()
    gen.streams = []
    return ScoreVisualizer(gen, config=config)


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close('all')


# =============================================================================
# GROUP 1 - Config: opt-in, default invariato
# =============================================================================

class TestConfigDefault:

    def test_grain_shape_default_is_arrow(self):
        viz = make_viz()
        assert viz.config['grain_shape'] == 'arrow'

    def test_grain_shape_override_window(self):
        viz = make_viz(config={'grain_shape': 'window'})
        assert viz.config['grain_shape'] == 'window'


# =============================================================================
# GROUP 2 - Silhouette finestra normalizzata
# =============================================================================

class TestWindowSilhouette:

    def test_returns_arrays_of_requested_resolution(self):
        viz = make_viz()
        xs, w = viz._window_silhouette('hanning', 32)
        assert len(xs) == 32
        assert len(w) == 32

    def test_normalized_to_unit_peak_and_domain(self):
        viz = make_viz()
        xs, w = viz._window_silhouette('hanning', 64)
        assert xs[0] == pytest.approx(0.0)
        assert xs[-1] == pytest.approx(1.0)
        assert w.max() == pytest.approx(1.0)
        assert w.min() >= 0.0

    def test_hanning_is_symmetric(self):
        viz = make_viz()
        _, w = viz._window_silhouette('hanning', 64)
        assert np.allclose(w, w[::-1], atol=1e-6)

    def test_expodec_decays_left_to_right(self):
        # expodec: attacco pieno, decadimento -> w[0] > w[-1]
        viz = make_viz()
        _, w = viz._window_silhouette('expodec', 64)
        assert w[0] > w[-1]

    def test_exporise_rises_left_to_right(self):
        viz = make_viz()
        _, w = viz._window_silhouette('exporise', 64)
        assert w[0] < w[-1]

    def test_silhouette_cached_by_name_and_resolution(self):
        viz = make_viz()
        a = viz._window_silhouette('hanning', 32)
        b = viz._window_silhouette('hanning', 32)
        assert a is b


# =============================================================================
# GROUP 3 - Vertici del poligono (variante testa/bordo)
# =============================================================================

class TestWindowVertices:

    def test_vertex_count_is_resolution_plus_two(self):
        viz = make_viz()
        xs, w = viz._window_silhouette('hanning', 32)
        grain = make_grain(onset=1.0, duration=0.5, pointer_pos=0.4)
        verts = viz._grain_window_vertices(grain, xs, w)
        assert len(verts) == 34  # base sx + 32 punti bordo + base dx

    def test_base_flat_on_pointer_forward(self):
        viz = make_viz()
        xs, w = viz._window_silhouette('hanning', 32)
        grain = make_grain(onset=1.0, duration=0.5, pointer_pos=0.4,
                           pitch_ratio=1.0)
        verts = viz._grain_window_vertices(grain, xs, w)
        # primo e ultimo vertice = base piatta sul pointer
        assert verts[0][1] == pytest.approx(0.4)
        assert verts[-1][1] == pytest.approx(0.4)

    def test_edge_follows_window_above_pointer_forward(self):
        viz = make_viz()
        xs, w = viz._window_silhouette('hanning', 32)
        grain = make_grain(onset=1.0, duration=0.5, pointer_pos=0.4,
                           pitch_ratio=1.0)
        verts = viz._grain_window_vertices(grain, xs, w)
        edge_ys = [y for (_, y) in verts[1:-1]]
        # tutti sopra (o uguali) il pointer; picco = pointer + height
        assert min(edge_ys) >= 0.4 - 1e-9
        assert max(edge_ys) == pytest.approx(0.4 + 0.5)

    def test_edge_below_pointer_when_reverse(self):
        viz = make_viz()
        xs, w = viz._window_silhouette('hanning', 32)
        grain = make_grain(onset=1.0, duration=0.5, pointer_pos=0.4,
                           pitch_ratio=-1.0)
        verts = viz._grain_window_vertices(grain, xs, w)
        edge_ys = [y for (_, y) in verts[1:-1]]
        assert max(edge_ys) <= 0.4 + 1e-9
        assert min(edge_ys) == pytest.approx(0.4 - 0.5)

    def test_x_span_matches_grain_extent(self):
        viz = make_viz()
        xs, w = viz._window_silhouette('hanning', 32)
        grain = make_grain(onset=1.0, duration=0.5, pointer_pos=0.4)
        verts = viz._grain_window_vertices(grain, xs, w)
        xsv = [x for (x, _) in verts]
        assert min(xsv) == pytest.approx(1.0)
        assert max(xsv) == pytest.approx(1.5)


# =============================================================================
# GROUP 4 - Vertici freccia (comportamento legacy invariato)
# =============================================================================

class TestArrowVertices:

    def test_arrow_has_five_vertices(self):
        viz = make_viz()
        grain = make_grain(onset=1.0, duration=0.5, pointer_pos=0.4,
                           pitch_ratio=1.0)
        verts = viz._grain_arrow_vertices(grain)
        assert len(verts) == 5


# =============================================================================
# GROUP 5 - Disegno: branch su grain_shape
# =============================================================================

class TestDrawGrainsFullBranch:

    def _draw(self, config):
        viz = make_viz(config=config)
        fig, ax = plt.subplots()
        # axes con range realistico cosi' la trasformazione px e' sensata
        ax.set_xlim(0, 6)
        ax.set_ylim(0, 2)
        fig.canvas.draw()
        wtm = {'expodec': 10}
        grain = make_grain(onset=1.0, duration=0.5, pointer_pos=0.4,
                           pitch_ratio=1.0, envelope_table=10)
        stream = make_stream([grain], window_table_map=wtm)
        viz._draw_grains_full(ax, stream, sample_duration=2.0,
                              page_start=0.0, page_end=6.0)
        return ax

    def test_arrow_mode_polygon_has_five_vertices(self):
        ax = self._draw({'grain_shape': 'arrow'})
        assert len(ax.collections) == 1
        paths = ax.collections[0].get_paths()
        # 5 vertici + eventuale chiusura -> <= 6 punti nel path
        assert len(paths[0].vertices) <= 6

    def test_window_mode_polygon_has_many_vertices(self):
        ax = self._draw({'grain_shape': 'window',
                         'window_shape_resolution': 32})
        assert len(ax.collections) == 1
        paths = ax.collections[0].get_paths()
        assert len(paths[0].vertices) > 6


# =============================================================================
# GROUP 6 - Fallback adattivo per grani sotto soglia
# =============================================================================

class TestAdaptiveFallback:

    def test_tiny_grain_falls_back_to_arrow(self):
        viz = make_viz(config={'grain_shape': 'window',
                               'window_shape_resolution': 32,
                               'window_shape_min_px': 50})
        fig, ax = plt.subplots()
        ax.set_xlim(0, 600)   # 600s su pochi pollici -> grano 0.5s e' sub-pixel
        ax.set_ylim(0, 2)
        fig.canvas.draw()
        grain = make_grain(onset=1.0, duration=0.5, pointer_pos=0.4,
                           envelope_table=10)
        stream = make_stream([grain], window_table_map={'hanning': 10})
        viz._draw_grains_full(ax, stream, sample_duration=2.0,
                              page_start=0.0, page_end=600.0)
        paths = ax.collections[0].get_paths()
        assert len(paths[0].vertices) <= 6  # ripiego a freccia


# =============================================================================
# GROUP 7 - Il fallback si misura sulla figura finita (issue #280)
# =============================================================================

class TestFallbackMeasuredOnFinishedFigure:
    """La soglia window_shape_min_px parla dei pixel che il grano occupa
    nella figura che si guarda, e quei pixel dipendono dai limiti dell'asse.

    I test del GROUP 6 impostano xlim prima di chiamare _draw_grains_full, e
    per questo non vedono l'ordine dei chiamanti: se un asse disegna i grani
    prima di avere i suoi limiti, la misura avviene sul default 0-1 s. Qui si
    passa da render_page e si confronta ogni poligono con la larghezza che il
    suo grano ha a figura finita, sull'asse che lo contiene.

    La scena e' scelta perche' i due assi diano risposte opposte: grani da
    5 ms su una pagina da 5 s sono sotto soglia sulla MAP e ben sopra nella
    lente a zoom 8. Una forma decisa senza guardare l'asse finito sbaglia
    almeno uno dei due.
    """

    PAGE = 5.0
    GRAIN_DUR = 0.005
    RES = 32
    SR = 44100
    FAKE_AUDIO = np.zeros(SR * 4, dtype=np.float32)

    @classmethod
    def _stream(cls):
        n = 200
        grains = [make_grain(onset=i * cls.PAGE / n, duration=cls.GRAIN_DUR,
                             pointer_pos=1.0, envelope_table=10)
                  for i in range(n)]
        s = make_stream(grains, window_table_map={'hanning': 10})
        s.duration = cls.PAGE
        s.sample = 'piano.wav'
        s.loop_start = None
        # Letti per nome da envelope_extractor: senza il del, un MagicMock
        # risponderebbe a qualsiasi getattr come se fosse una curva.
        for name in ('volume', 'pan', 'pointer_start', 'density',
                     'num_voices', 'scatter', 'pointer_speed'):
            delattr(s, name)
        return s

    def _render(self):
        gen = MagicMock()
        gen.streams = [self._stream()]
        viz = ScoreVisualizer(gen, config={
            'page_duration': self.PAGE,
            'grain_shape': 'window',
            'window_shape_resolution': self.RES,
            'magnify_targets': [{'t': self.PAGE / 2, 'y': 1.0, 'zoom': 8.0}],
        })
        with patch('soundfile.read', return_value=(self.FAKE_AUDIO, self.SR)):
            viz.analyze()
            fig = viz.render_page(0)
        fig.canvas.draw()
        return viz, fig

    @staticmethod
    def _grain_paths(ax):
        colls = [c for c in ax.collections
                 if isinstance(c, PatchCollection) and c.get_zorder() == 2]
        assert len(colls) == 1
        return colls[0].get_paths()

    def _shape(self, path):
        # Polygon(closed=True) ripete il primo vertice in coda.
        n = len(path.vertices) - 1
        if n == self.RES + 2:
            return 'window'
        if n == 5:
            return 'arrow'
        raise AssertionError(f"poligono di {n} vertici: ne' freccia ne' "
                             f"silhouette a risoluzione {self.RES}")

    @staticmethod
    def _width_px(ax, path):
        # Freccia e silhouette coprono entrambe [onset, onset + duration].
        xs = path.vertices[:, 0]
        x0 = ax.transData.transform((xs.min(), 0.0))[0]
        x1 = ax.transData.transform((xs.max(), 0.0))[0]
        return abs(x1 - x0)

    def _assert_shapes_follow_final_width(self, ax, min_px, expected):
        paths = self._grain_paths(ax)
        assert paths, 'nessun grano disegnato: la scena non prova niente'
        for path in paths:
            width = self._width_px(ax, path)
            # Premessa della scena: su questo asse tutti i grani stanno dalla
            # stessa parte della soglia, e dalla parte attesa. Il messaggio la
            # nomina: senza, un cambio di layout e una regressione del
            # fallback fallirebbero con lo stesso numero nudo.
            assert (width >= min_px) == (expected == 'window'), (
                f"premessa della scena violata: grano largo {width:.2f} px "
                f"a figura finita, soglia {min_px} px, forma attesa "
                f"{expected!r}. Va ritarata la scena, non il codice.")
            assert self._shape(path) == expected, (
                f"grano largo {width:.2f} px a figura finita (soglia "
                f"{min_px} px) disegnato come {self._shape(path)!r}: la "
                f"forma e' stata scelta su limiti diversi da quelli finali.")

    def test_lens_draws_window_for_grains_wide_in_the_lens(self):
        viz, fig = self._render()
        lenses = [ax for ax in fig.axes if ax.get_label() == '<magnifier>']
        assert len(lenses) == 1
        self._assert_shapes_follow_final_width(
            lenses[0], viz.config['window_shape_min_px'], 'window')

    def test_map_falls_back_to_arrow_for_grains_narrow_on_the_page(self):
        viz, fig = self._render()
        maps = [ax for ax in fig.axes
                if ax.get_label() != '<magnifier>'
                and any(isinstance(c, PatchCollection) and c.get_zorder() == 2
                        for c in ax.collections)]
        assert len(maps) == 1
        assert maps[0].get_xlim() == pytest.approx((0.0, self.PAGE))
        self._assert_shapes_follow_final_width(
            maps[0], viz.config['window_shape_min_px'], 'arrow')
