# tests/rendering/test_score_visualizer_poc_projection.py
"""
Suite per la proiezione dell'istante della lente sulla corsia envelope
(issue #214).

La lente ingrandisce una regione del piano tempo x posizione-di-lettura, ma non
diceva a quali valori dei parametri corrisponde quell'istante: il lettore
doveva allineare a occhio la X del cerchio-sorgente con le curve sottostanti.
Ora ogni lente proietta sulla corsia envelope del suo stream una verticale
tratteggiata e, su ogni curva che incrocia, un marker con il valore reale.

Gli artisti della proiezione sono etichettati con un gid dedicato
('poc-projection', 'poc-projection-marker', 'poc-projection-label'): i test
contano quelli, non tutte le linee del subplot, che sono gia' decine fra curve,
breakpoint e griglia.

Invariante di retrocompatibilita': a magnify spenta, o su uno stream senza
curve, non compare NESSUN artista in piu'.
"""

import numpy as np
import pytest
import matplotlib
matplotlib.use('Agg')  # backend non-interattivo obbligatorio nei test
import matplotlib.pyplot as plt
from unittest.mock import MagicMock, patch

from pge.envelopes.envelope import Envelope  # noqa: E402
from pge.rendering.score_visualizer import ScoreVisualizer  # noqa: E402


SR = 44100
DUR = 4.0
FAKE_AUDIO = np.sin(
    2 * np.pi * 440 * np.linspace(0, DUR, int(SR * DUR))
).astype(np.float32)

PAGE = 30.0
TARGET_T = 6.0


# =============================================================================
# FACTORY
# =============================================================================

def make_grain(onset=0.0, duration=0.05, pointer_pos=0.5,
               pitch_ratio=1.0, volume=-6.0):
    g = MagicMock()
    g.onset = onset
    g.duration = duration
    g.pointer_pos = pointer_pos
    g.pitch_ratio = pitch_ratio
    g.volume = volume
    return g


def make_stream(stream_id='s1', onset=0.0, duration=20.0,
                sample='piano.wav', n_grains=8):
    s = MagicMock()
    s.stream_id = stream_id
    s.onset = onset
    s.duration = duration
    s.sample = sample
    spacing = duration / max(n_grains, 1)
    s.voices = [[make_grain(onset + i * spacing) for i in range(n_grains)]]
    # Gli attributi cancellati sono quelli che envelope_extractor legge per
    # nome: senza il del, un MagicMock risponderebbe a qualsiasi getattr e
    # verrebbe scartato solo piu' avanti.
    for name in ('volume', 'pan', 'pointer_start', 'density', 'num_voices',
                 'scatter', 'pointer_speed'):
        delattr(s, name)
    return s


def make_viz(streams, config=None):
    generator = MagicMock()
    generator.streams = streams
    cfg = {'page_duration': PAGE}
    cfg.update(config or {})
    return ScoreVisualizer(generator, config=cfg)


def render(streams, config=None):
    viz = make_viz(streams, config)
    with patch('soundfile.read', return_value=(FAKE_AUDIO, SR)):
        viz.analyze()
        fig = viz.render_page(0)
    fig.canvas.draw()  # finalizza transform/posizioni
    return fig


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close('all')


# =============================================================================
# SCENARI
# =============================================================================

def envelope_scene():
    """Uno stream con due curve dinamiche (density + pointer_speed)."""
    s = make_stream('s1')
    s.density = Envelope([[0, 10.0], [20, 30.0]])
    s.pointer_speed = Envelope([[0, 1.0], [20, 2.0]])
    return [s]


def static_and_dynamic_scene():
    """Due stream: il primo ha curve, il secondo e' tutto statico (corsia
    envelope presente ma vuota, issue #113)."""
    dynamic = make_stream('dyn')
    dynamic.density = Envelope([[0, 10.0], [20, 30.0]])
    return [dynamic, make_stream('static', sample='strings.wav')]


def crowded_scene(duration=20.0):
    """Quattro curve nella stessa corsia: tutte le etichette della proiezione
    cadono sulla stessa verticale, ed e' li' che si pestano i piedi."""
    s = make_stream('s1', duration=duration)
    s.density = Envelope([[0, 10.0], [duration, 30.0]])
    s.pointer_speed = Envelope([[0, 1.0], [duration, 2.0]])
    s.volume = Envelope([[0, -12.0], [duration, -3.0]])
    s.grain_duration = Envelope([[0, 0.08], [duration, 0.02]])
    return [s]


def two_dynamic_streams_scene():
    """Due stream con la stessa curva su escursioni molto diverse: se la
    proiezione usasse i range dell'ultima corsia disegnata invece di quelli
    della propria, il marker cadrebbe fuori dalla curva."""
    first = make_stream('s1')
    first.density = Envelope([[0, 10.0], [20, 30.0]])
    second = make_stream('s2', sample='strings.wav')
    second.density = Envelope([[0, 100.0], [20, 180.0]])
    return [first, second]


# =============================================================================
# HELPER
# =============================================================================

def env_ax(fig, stream_id):
    """Il subplot envelope di uno stream (render_page lo etichetta 'env:<id>')."""
    for ax in fig.axes:
        if ax.get_label() == f'env:{stream_id}':
            return ax
    return None


def by_gid(artists, gid):
    return [a for a in artists if a.get_gid() == gid]


def projection_lines(ax):
    return by_gid(ax.lines, 'poc-projection')


def projection_markers(ax):
    return by_gid(ax.lines, 'poc-projection-marker')


def projection_labels(ax):
    return by_gid(ax.texts, 'poc-projection-label')


def all_projection_artists(fig):
    found = []
    for ax in fig.axes:
        found += (projection_lines(ax) + projection_markers(ax)
                  + projection_labels(ax))
    return found


def curve_y_at(ax, param_name, t):
    """Quota della curva disegnata, letta dai dati del suo artista."""
    curve = next(line for line in ax.lines if line.get_label() == param_name)
    xs, ys = curve.get_xdata(), curve.get_ydata()
    return float(np.interp(t, xs, ys))


# =============================================================================
# GROUP - back-compat: niente lente, niente proiezione
# =============================================================================

class TestBackCompat:
    """A magnify spenta la pagina resta identica: la proiezione e' un artista
    della lente, non della corsia."""

    def test_no_projection_without_magnify(self):
        fig = render(envelope_scene())
        assert all_projection_artists(fig) == []

    def test_no_projection_on_a_stream_without_curves(self):
        """Corsia vuota (stream tutto statico): la lente proietta il cerchio ma
        non tocca la corsia."""
        fig = render(static_and_dynamic_scene(),
                     {'magnify_targets': [{'t': TARGET_T, 'y': 1.0,
                                           'stream': 'static'}]})
        assert [ax for ax in fig.axes if ax.get_label() == '<magnifier>']
        assert all_projection_artists(fig) == []

    def test_no_projection_when_the_instant_is_outside_the_stream(self):
        """Lo stream finisce a 10s, la lente punta a 20s: dentro la pagina ma
        fuori dallo stream. Non c'e' nessun valore da leggere, quindi nemmeno
        la verticale."""
        s = make_stream('s1', duration=10.0)
        s.density = Envelope([[0, 10.0], [10, 30.0]])
        fig = render([s], {'magnify_targets': [{'t': 20.0, 'y': 1.0}]})
        assert all_projection_artists(fig) == []

    def test_disabled_by_config_keeps_the_lens(self):
        """magnify_projection.enabled=False: la lente resta, la proiezione no."""
        fig = render(envelope_scene(),
                     {'magnify_targets': [{'t': TARGET_T, 'y': 1.0}],
                      'magnify_projection': {'enabled': False}})
        assert [ax for ax in fig.axes if ax.get_label() == '<magnifier>']
        assert all_projection_artists(fig) == []


# =============================================================================
# GROUP - la verticale
# =============================================================================

class TestProjectionLine:

    def _fig(self, config=None):
        cfg = {'magnify_targets': [{'t': TARGET_T, 'y': 1.0}]}
        cfg.update(config or {})
        return render(envelope_scene(), cfg)

    def test_one_line_on_the_envelope_lane(self):
        ax = env_ax(self._fig(), 's1')
        assert len(projection_lines(ax)) == 1

    def test_line_sits_on_the_target_instant(self):
        line = projection_lines(env_ax(self._fig(), 's1'))[0]
        # axvline: verticale, quindi entrambi gli estremi sull'istante.
        assert list(line.get_xdata()) == pytest.approx([TARGET_T, TARGET_T])

    def test_line_is_dashed(self):
        """Tratteggio e non solo colore: la partitura deve restare leggibile
        anche stampata in scala di grigi."""
        line = projection_lines(env_ax(self._fig(), 's1'))[0]
        assert line.get_linestyle() not in ('-', 'None')

    def test_line_uses_the_magnify_accent(self):
        """Stesso colore dell'anello sorgente e dei connettori: la proiezione e'
        parte della lente, non un elemento a se'."""
        fig = self._fig({'magnify_color': '#0000ff'})
        line = projection_lines(env_ax(fig, 's1'))[0]
        assert matplotlib.colors.to_hex(line.get_color()) == '#0000ff'

    def test_line_style_is_configurable(self):
        fig = self._fig({'magnify_projection': {'linewidth': 2.5}})
        line = projection_lines(env_ax(fig, 's1'))[0]
        assert line.get_linewidth() == pytest.approx(2.5)

    def test_the_grain_plane_is_untouched(self):
        """La verticale vive nella corsia envelope: sul piano dei grani ci
        sono gia' i connettori della lente."""
        fig = self._fig()
        grain_axes = [ax for ax in fig.axes
                      if ax.get_label() not in ('<magnifier>',
                                                '<magnifier-overlay>',
                                                'env:s1')]
        assert all(projection_lines(ax) == [] for ax in grain_axes)


# =============================================================================
# GROUP - i marker sulle curve
# =============================================================================

class TestProjectionMarkers:

    def _fig(self, streams=None, config=None):
        cfg = {'magnify_targets': [{'t': TARGET_T, 'y': 1.0}]}
        cfg.update(config or {})
        return render(streams or envelope_scene(), cfg)

    def test_one_marker_per_curve(self):
        ax = env_ax(self._fig(), 's1')
        assert len(projection_markers(ax)) == 2  # density + pointer_speed

    def test_marker_sits_on_its_curve(self):
        """L'incrocio e' vero: la quota del marker coincide con quella della
        curva disegnata nello stesso istante."""
        ax = env_ax(self._fig(), 's1')
        markers = projection_markers(ax)
        drawn = sorted(float(m.get_ydata()[0]) for m in markers)
        expected = sorted(curve_y_at(ax, name, TARGET_T)
                          for name in ('density', 'pointer_speed'))
        assert drawn == pytest.approx(expected, abs=1e-3)

    def test_marker_x_is_the_target_instant(self):
        ax = env_ax(self._fig(), 's1')
        for marker in projection_markers(ax):
            assert float(marker.get_xdata()[0]) == pytest.approx(TARGET_T)

    def test_marker_takes_the_colour_of_its_curve(self):
        """Con piu' curve nella stessa corsia il colore dice a quale
        appartiene il valore letto."""
        ax = env_ax(self._fig(), 's1')
        colors = {matplotlib.colors.to_hex(m.get_markerfacecolor())
                  for m in projection_markers(ax)}
        viz_colors = {matplotlib.colors.to_hex(c)
                      for c in (ScoreVisualizer(MagicMock(), config=None)
                                .config['envelope_colors'][name]
                                for name in ('density', 'pointer_speed'))}
        assert colors == viz_colors

    def test_each_lane_uses_its_own_display_ranges(self):
        """Due stream con escursioni molto diverse: il marker del secondo cade
        sulla curva del secondo, non su una quota calcolata coi range del
        primo (o dell'ultima corsia disegnata)."""
        fig = self._fig(
            two_dynamic_streams_scene(),
            {'magnify_targets': [{'t': TARGET_T, 'y': 1.0, 'stream': 's1'},
                                 {'t': TARGET_T, 'y': 1.0, 'stream': 's2'}]})
        for stream_id in ('s1', 's2'):
            ax = env_ax(fig, stream_id)
            marker = projection_markers(ax)[0]
            assert float(marker.get_ydata()[0]) == pytest.approx(
                curve_y_at(ax, 'density', TARGET_T), abs=1e-3)


# =============================================================================
# GROUP - le etichette col valore reale
# =============================================================================

class TestProjectionLabels:

    def _fig(self, config=None):
        cfg = {'magnify_targets': [{'t': TARGET_T, 'y': 1.0}]}
        cfg.update(config or {})
        return render(envelope_scene(), cfg)

    def test_one_label_per_curve(self):
        ax = env_ax(self._fig(), 's1')
        assert len(projection_labels(ax)) == 2

    def test_label_shows_the_real_value_with_its_unit(self):
        """density 10 -> 30 su 20s: a 6s vale 16 g/s. Stesso formato dei
        breakpoint annotati sulle curve."""
        ax = env_ax(self._fig(), 's1')
        texts = {t.get_text() for t in projection_labels(ax)}
        assert '16.0g/s' in texts   # density
        assert '1.30x' in texts     # pointer_speed

    def test_labels_alternate_side_going_up_the_lane(self):
        """Le etichette stanno tutte sulla stessa verticale: se cadessero tutte
        dallo stesso lato, due curve vicine si sovrascriverebbero (e' quello che
        succedeva alla prima resa della pagina di prova). Alternando il lato,
        due valori consecutivi in quota non si toccano mai."""
        fig = render(crowded_scene(),
                     {'magnify_targets': [{'t': TARGET_T, 'y': 1.0}]})
        labels = sorted(projection_labels(env_ax(fig, 's1')),
                        key=lambda ann: ann.xy[1])
        assert len(labels) == 4
        sides = [ann.get_ha() for ann in labels]
        assert all(a != b for a, b in zip(sides, sides[1:])), sides

    def test_labels_stay_inside_the_plot_near_the_right_edge(self):
        """L'alternanza non batte il bordo: vicino al margine destro tutte le
        etichette vanno comunque a sinistra del punto, come i breakpoint."""
        fig = render(crowded_scene(duration=PAGE),
                     {'magnify_targets': [{'t': 28.0, 'y': 1.0}]})
        labels = projection_labels(env_ax(fig, 's1'))
        assert labels and all(ann.get_ha() == 'right' for ann in labels)

    def test_labels_can_be_turned_off(self):
        """Corsie affollate: la verticale e i marker restano, i numeri no."""
        fig = self._fig({'magnify_projection': {'labels': False}})
        ax = env_ax(fig, 's1')
        assert projection_labels(ax) == []
        assert len(projection_markers(ax)) == 2
        assert len(projection_lines(ax)) == 1


# =============================================================================
# GROUP - il record della corsia
# =============================================================================

class TestEnvelopeLaneRecord:
    """_draw_envelopes restituisce cosa e' finito nella corsia: e' l'unico modo
    per ritrovare, al momento della proiezione, i range con cui le curve sono
    state scalate (lo scratchpad d'istanza a quel punto e' quello dell'ultimo
    stream disegnato)."""

    def _render_lane(self, stream):
        viz = make_viz([stream])
        fig, ax = plt.subplots()
        with patch('soundfile.read', return_value=(FAKE_AUDIO, SR)):
            return viz._draw_envelopes(ax, stream, 0.0, 1.0, 0.0, PAGE)

    def test_record_carries_curves_and_ranges(self):
        stream = envelope_scene()[0]
        record = self._render_lane(stream)
        assert record.drawn_types == {'density', 'pointer_speed'}
        assert set(record.display_ranges) == {'density', 'pointer_speed'}
        # range data-driven sull'escursione reale + pad (issue #114)
        lo, hi = record.display_ranges['density']
        assert lo < 10.0 and hi > 30.0

    def test_record_carries_the_lane_geometry(self):
        record = self._render_lane(envelope_scene()[0])
        assert (record.y_base, record.y_height) == (0.0, 1.0)

    def test_static_stream_gives_an_empty_record(self):
        record = self._render_lane(make_stream('statico'))
        assert record.drawn_types == set()
        assert record.display_ranges == {}


# =============================================================================
# GROUP - integrazione con le due modalita' della lente
# =============================================================================

class TestBothMagnifyModes:

    def test_auto_lens_projects_too(self):
        """La lente automatica (cluster piu' denso) proietta come le esplicite."""
        fig = render(envelope_scene(), {'magnify_auto': True})
        assert len(projection_lines(env_ax(fig, 's1'))) == 1

    def test_two_lenses_two_projections(self):
        """Ogni lente ha la sua verticale: due target, due istanti letti."""
        fig = render(envelope_scene(), {'magnify_targets': [
            {'t': 4.0, 'y': 1.0, 'corner': 'top-right'},
            {'t': 12.0, 'y': 1.0, 'corner': 'bottom-left'},
        ]})
        ax = env_ax(fig, 's1')
        xs = sorted(float(line.get_xdata()[0])
                    for line in projection_lines(ax))
        assert xs == pytest.approx([4.0, 12.0])
        assert len(projection_markers(ax)) == 4  # 2 curve x 2 lenti
