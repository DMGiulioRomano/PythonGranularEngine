# tests/rendering/test_magnifier_projection.py
"""
TDD suite per rendering.magnifier_projection.

La lente punta un istante `t` del piano tempo x posizione-di-lettura. Questo
modulo dice a QUALI valori delle curve dello stream corrisponde quell'istante e
a che quota vanno letti dentro la corsia envelope (issue #214). Disegnare la
verticale, i marker e le etichette resta di ScoreVisualizer: qui si arriva alle
coordinate e ci si ferma, senza importare matplotlib.

Il record `EnvelopeLaneRender` e' il canale fra chi disegna la corsia e chi ci
proietta sopra: porta le curve effettivamente disegnate, i range di display CON
CUI sono state scalate e la geometria della corsia. Senza, la proiezione
dovrebbe ricalcolare i range per conto suo e potrebbe divergere da quanto e'
gia' sulla pagina.
"""

import pytest

from pge.envelopes.envelope import Envelope
from pge.rendering.magnifier_projection import (
    EnvelopeLaneRender,
    ProjectedValue,
    project,
)


PAN_RANGE = (-180, 180)


def lane_render(curves, ranges, y_base=0.0, y_height=1.0, pitch_unit=None):
    return EnvelopeLaneRender(
        curves=curves, display_ranges=ranges,
        y_base=y_base, y_height=y_height, pitch_unit=pitch_unit)


class TestEnvelopeLaneRender:
    """Il record e' vuoto per default: una corsia senza curve non ha niente da
    proiettare, ed e' lo stato con cui il visualizer esce dai casi degeneri."""

    def test_empty_by_default(self):
        render = EnvelopeLaneRender()
        assert render.curves == {}
        assert render.display_ranges == {}
        assert render.drawn_types == set()

    def test_drawn_types_are_the_curve_names(self):
        env = Envelope([[0, 1.0], [10, 2.0]])
        render = lane_render({'density': env, 'pitch': env}, {})
        assert render.drawn_types == {'density', 'pitch'}


class TestProject:
    """Un punto per ogni curva disegnata, col valore reale e la quota nella
    corsia."""

    def test_no_curves_no_points(self):
        assert project(EnvelopeLaneRender(), t=5.0, stream_start=0.0,
                       stream_duration=10.0, pan_range=PAN_RANGE) == []

    def test_one_point_per_curve(self):
        curves = {
            'density': Envelope([[0, 10.0], [10, 20.0]]),
            'pointer_speed': Envelope([[0, 1.0], [10, 3.0]]),
        }
        ranges = {'density': (10.0, 20.0), 'pointer_speed': (1.0, 3.0)}
        points = project(lane_render(curves, ranges), t=5.0, stream_start=0.0,
                         stream_duration=10.0, pan_range=PAN_RANGE)
        assert [p.param for p in points] == ['density', 'pointer_speed']
        assert all(isinstance(p, ProjectedValue) for p in points)

    def test_value_is_the_curve_value_at_that_instant(self):
        """Il valore e' quello reale del parametro, non la quota normalizzata:
        e' cio' che finisce nell'etichetta."""
        curves = {'density': Envelope([[0, 10.0], [10, 20.0]])}
        points = project(lane_render(curves, {'density': (10.0, 20.0)}),
                         t=5.0, stream_start=0.0, stream_duration=10.0,
                         pan_range=PAN_RANGE)
        assert points[0].value == pytest.approx(15.0)

    def test_y_is_the_lane_coordinate(self):
        """La quota e' y_base + frazione * y_height: la stessa trasformazione
        con cui la curva e' stata disegnata nella corsia."""
        curves = {'density': Envelope([[0, 10.0], [10, 20.0]])}
        points = project(
            lane_render(curves, {'density': (10.0, 20.0)},
                        y_base=0.2, y_height=0.6),
            t=5.0, stream_start=0.0, stream_duration=10.0, pan_range=PAN_RANGE)
        # meta' escursione -> meta' corsia
        assert points[0].y == pytest.approx(0.2 + 0.5 * 0.6)

    def test_uses_the_given_ranges(self):
        """La normalizzazione usa i range del record, non un ricalcolo: con un
        range doppio lo stesso valore cade a meta' altezza."""
        curves = {'density': Envelope([[0, 10.0], [10, 20.0]])}
        points = project(lane_render(curves, {'density': (10.0, 30.0)}),
                         t=10.0, stream_start=0.0, stream_duration=10.0,
                         pan_range=PAN_RANGE)
        assert points[0].value == pytest.approx(20.0)
        assert points[0].y == pytest.approx(0.5)

    def test_range_missing_falls_back_to_mid_lane(self):
        """Nessun range per quella curva: la quota e' il centro corsia, come
        per il disegno (envelope_display.normalize)."""
        curves = {'density': Envelope([[0, 10.0], [10, 20.0]])}
        points = project(lane_render(curves, {}, y_base=0.0, y_height=0.4),
                         t=5.0, stream_start=0.0, stream_duration=10.0,
                         pan_range=PAN_RANGE)
        assert points[0].y == pytest.approx(0.2)

    def test_pan_uses_the_cyclic_range(self):
        """pan non ha range di display (e' ciclico): normalizza sul range fisso."""
        curves = {'pan': Envelope([[0, 0.0], [10, 0.0]])}
        points = project(lane_render(curves, {}), t=5.0, stream_start=0.0,
                         stream_duration=10.0, pan_range=PAN_RANGE)
        assert points[0].y == pytest.approx(0.5)

    def test_breakpoints_are_relative_to_the_stream(self):
        """t e' assoluto, i breakpoint sono relativi all'onset: la conversione
        e' qui, come in display_ranges."""
        curves = {'density': Envelope([[0, 10.0], [10, 20.0]])}
        points = project(lane_render(curves, {'density': (10.0, 20.0)}),
                         t=17.0, stream_start=12.0, stream_duration=10.0,
                         pan_range=PAN_RANGE)
        assert points[0].value == pytest.approx(15.0)

    def test_instant_before_the_stream_projects_nothing(self):
        """Fuori dall'estensione dello stream non c'e' nessun valore da
        leggere: Envelope.evaluate saturerebbe sul primo breakpoint e la lente
        mostrerebbe un numero che in quel punto non esiste."""
        curves = {'density': Envelope([[0, 10.0], [10, 20.0]])}
        points = project(lane_render(curves, {'density': (10.0, 20.0)}),
                         t=3.0, stream_start=5.0, stream_duration=10.0,
                         pan_range=PAN_RANGE)
        assert points == []

    def test_instant_after_the_stream_projects_nothing(self):
        curves = {'density': Envelope([[0, 10.0], [10, 20.0]])}
        points = project(lane_render(curves, {'density': (10.0, 20.0)}),
                         t=16.0, stream_start=5.0, stream_duration=10.0,
                         pan_range=PAN_RANGE)
        assert points == []

    def test_the_two_ends_of_the_stream_are_included(self):
        """Estremi compresi: una lente sull'attacco o sull'ultimo istante ha
        comunque un valore da mostrare."""
        curves = {'density': Envelope([[0, 10.0], [10, 20.0]])}
        for t, expected in ((5.0, 10.0), (15.0, 20.0)):
            points = project(lane_render(curves, {'density': (10.0, 20.0)}),
                             t=t, stream_start=5.0, stream_duration=10.0,
                             pan_range=PAN_RANGE)
            assert points[0].value == pytest.approx(expected)

    def test_per_voice_curve_scales_on_its_own_range(self):
        """Le curve per-voce '__vN' hanno un range proprio, come nel disegno."""
        curves = {'voice_pitch_offset__v1': Envelope([[0, 0.0], [10, 4.0]])}
        points = project(
            lane_render(curves, {'voice_pitch_offset__v1': (0.0, 4.0)}),
            t=5.0, stream_start=0.0, stream_duration=10.0, pan_range=PAN_RANGE)
        assert points[0].y == pytest.approx(0.5)
