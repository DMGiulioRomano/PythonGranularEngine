# tests/rendering/test_grain_height_mode.py
"""
Suite per il modo di altezza del grano nella mappa (issue #223).

Sull'asse Y della mappa (`Read position (s)`) l'altezza di un grano e' una
porzione di buffer. Quella disegnata storicamente e' `grain.duration`: la
porzione che il grano percorrerebbe leggendo a velocita' 1. La porzione che
percorre davvero e' `duration * pitch_ratio` — le due coincidono solo a
|ratio| = 1, e a ratio 2 la freccia disegna meta' di quello che il renderer
legge.

Correggerlo cambia la geometria di ogni partitura gia' generata, quindi non e'
un fix silenzioso: e' un modo, `grain_height`, che si accende. Qui si verifica
il cablaggio dal config al poligono disegnato — la geometria pura sta in
test_grain_visuals.py.
"""

import pytest
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from unittest.mock import MagicMock

from pge.rendering.score_visualizer import ScoreVisualizer  # noqa: E402


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


def drawn_ys(config, grain):
    """Le y del poligono disegnato per un grano, con la config data."""
    viz = make_viz(config=config)
    fig, ax = plt.subplots()
    ax.set_xlim(0, 6)
    ax.set_ylim(0, 2)
    fig.canvas.draw()
    viz._draw_grains_full(ax, make_stream([grain]), sample_duration=2.0,
                          page_start=0.0, page_end=6.0)
    return [y for _, y in ax.collections[0].get_paths()[0].vertices]


# =============================================================================
# GROUP 1 - Config: opt-in, default invariato
# =============================================================================

class TestConfigDefault:

    def test_default_is_duration(self):
        """Il default e' la geometria storica: le figure gia' pubblicate non
        cambiano da sole."""
        assert make_viz().config['grain_height'] == 'duration'

    def test_override_read_span(self):
        assert make_viz(
            config={'grain_height': 'read_span'}).config['grain_height'] \
            == 'read_span'


# =============================================================================
# GROUP 2 - Il modo arriva al poligono
# =============================================================================

class TestHeightReachesThePolygon:

    def test_default_ignores_the_ratio(self):
        """A ratio 3 la freccia storica resta alta quanto la durata: e'
        proprio l'errore che il modo nuovo corregge."""
        ys = drawn_ys(None, make_grain(onset=1.0, duration=0.5,
                                       pointer_pos=0.4, pitch_ratio=3.0))
        assert max(ys) == pytest.approx(0.9)

    def test_read_span_scales_the_height(self):
        """Ratio 3: il grano attraversa 1.5 s di buffer in 0.5 s di tempo."""
        ys = drawn_ys({'grain_height': 'read_span'},
                      make_grain(onset=1.0, duration=0.5, pointer_pos=0.4,
                                 pitch_ratio=3.0))
        assert max(ys) == pytest.approx(1.9)

    def test_read_span_shrinks_a_slow_grain(self):
        """Ratio 0.001: il grano resta quasi fermo sul punto di lettura."""
        ys = drawn_ys({'grain_height': 'read_span'},
                      make_grain(onset=1.0, duration=0.5, pointer_pos=0.4,
                                 pitch_ratio=0.001))
        assert max(ys) == pytest.approx(0.4005)

    def test_read_span_keeps_the_reverse_below_the_pointer(self):
        """Il verso resta questione di segno: la porzione letta si estende
        sotto la posizione di lettura, non sopra."""
        ys = drawn_ys({'grain_height': 'read_span'},
                      make_grain(onset=1.0, duration=0.5, pointer_pos=1.9,
                                 pitch_ratio=-3.0))
        assert min(ys) == pytest.approx(0.4)
        assert max(ys) == pytest.approx(1.9)

    def test_window_shape_follows_the_same_mode(self):
        """La silhouette della finestra si scala sulla stessa altezza: le due
        forme non possono raccontare due geometrie diverse."""
        ys = drawn_ys({'grain_height': 'read_span',
                       'grain_shape': 'window',
                       'window_shape_resolution': 32},
                      make_grain(onset=1.0, duration=0.5, pointer_pos=0.4,
                                 pitch_ratio=3.0, envelope_table=10))
        assert max(ys) == pytest.approx(1.9)

    def test_unknown_mode_is_refused_at_draw_time(self):
        """Un refuso nel modo non produce una figura sbagliata in silenzio."""
        with pytest.raises(ValueError, match='readspan'):
            drawn_ys({'grain_height': 'readspan'}, make_grain())


# =============================================================================
# GROUP 3 - La figura dichiara la propria geometria
# =============================================================================

class TestAxisLabelDeclaresTheMode:
    """Due partiture con geometrie diverse non devono essere indistinguibili
    guardandole: chi legge una figura fuori contesto deve poter sapere quale
    delle due altezze sta guardando."""

    def test_read_span_is_announced_on_the_axis(self):
        assert 'read span' in make_viz(
            config={'grain_height': 'read_span'})._read_position_label()

    def test_duration_mode_says_nothing_extra(self):
        """Il modo storico non annuncia niente: le figure gia' generate
        restano confrontabili con quelle nuove."""
        assert make_viz()._read_position_label() == 'Read position (s)'
