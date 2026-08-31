# tests/rendering/test_bw_preset.py
"""
Preset B&W della partitura (issue #248).

La MAP e' pensata per lo schermo. Stampata in bianco e nero perde
informazione in due punti, e sono i due che questa suite presidia:

1. la colormap del pitch (`pitch_div`) ha i due bracci alla STESSA chiarezza,
   quindi in grigio +300 e -300 cent diventano lo stesso grigio: il segno del
   detune sparisce;
2. le curve degli envelope si distinguono solo per tinta, quindi in grigio
   volume/pan/grain_duration diventano tre linee identiche.

Il preset risponde con due canali che il grigio ha davvero: la luminanza per
il pitch (mappa divergente acromatica, compressa lontano da bianco e nero) e
il tratteggio per gli envelope (nero per tutte le curve, un pattern per
chiave).

Un terzo problema non ha una risposta gratis: l'alpha guidata dal volume si
somma alla luminanza del grigio, ed e' lo stesso canale. Il preset la
FISSA — vedi TestFixedAlpha per il perche' e per cosa costa.
"""

import matplotlib
matplotlib.use('Agg')  # backend non-interattivo obbligatorio nei test
import matplotlib.pyplot as plt
import pytest
from unittest.mock import MagicMock

from pge.rendering.envelope_extractor import (
    ENVELOPE_COLORS, ENVELOPE_STYLES, ENVELOPE_STYLE_DEFAULT, BW_ENVELOPE_COLOR)
from pge.rendering.visualizer_config import VisualizerConfig
from pge.rendering.score_visualizer import ScoreVisualizer


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close('all')


def bw_config(**overrides):
    """La config del visualizer col preset acceso."""
    return VisualizerConfig.from_overrides({'bw': True, **overrides}).as_dict()


def plain_config(**overrides):
    return VisualizerConfig.from_overrides(overrides or None).as_dict()


# =============================================================================
# LA TAVOLA DEGLI STILI
# =============================================================================

class TestEnvelopeStylesTable:
    """`ENVELOPE_STYLES` e' la mappa parallela a `ENVELOPE_COLORS`: stessa
    chiave, l'altro canale."""

    def test_covers_exactly_the_same_keys_as_the_colors(self):
        """Parallela vuol dire totale: una chiave con un colore e senza stile
        in B&W tornerebbe una linea come tutte le altre, ed e' esattamente il
        collasso che il preset esiste per chiudere."""
        assert set(ENVELOPE_STYLES) == set(ENVELOPE_COLORS)

    def test_every_entry_is_a_linestyle_and_a_positive_width(self):
        for key, value in ENVELOPE_STYLES.items():
            linestyle, linewidth = value
            assert isinstance(linestyle, (str, tuple)), key
            assert isinstance(linewidth, (int, float)) and linewidth > 0, key

    def test_the_table_holds_no_matplotlib_object(self):
        """envelope_extractor e' il modulo matplotlib-free (issue #150): i
        pattern sono dati puri, altrimenti l'export SV si trascinerebbe dietro
        la pila di plotting per leggere una tabella."""
        for key, (linestyle, _) in ENVELOPE_STYLES.items():
            if isinstance(linestyle, tuple):
                offset, onoff = linestyle
                assert isinstance(offset, (int, float)), key
                assert isinstance(onoff, tuple) and len(onoff) % 2 == 0, key
                assert all(isinstance(x, (int, float)) for x in onoff), key

    def test_no_two_keys_share_the_same_pair(self):
        """La coppia (pattern, spessore) e' l'identita' della curva sulla
        carta: due chiavi con la stessa coppia sarebbero indistinguibili
        anche col preset acceso."""
        pairs = [tuple(v) for v in ENVELOPE_STYLES.values()]
        duplicates = {p for p in pairs if pairs.count(p) > 1}
        assert not duplicates, f"coppie ripetute: {sorted(map(str, duplicates))}"

    @pytest.mark.parametrize('base,variant', [
        ('volume', 'volume_prob'),
        ('volume', 'volume_range'),
        ('pan', 'pan_prob'),
        ('pan', 'pan_range'),
        ('grain_duration', 'grain_duration_prob'),
        ('grain_duration', 'grain_duration_range'),
        ('reverse', 'reverse_prob'),
        ('pointer_deviation', 'pointer_deviation_prob'),
    ])
    def test_variants_keep_the_pattern_of_their_base(self, base, variant):
        """Il chiaro/scuro della stessa tinta diventa sottile/spesso dello
        stesso tratteggio: la parentela fra una curva e la sua probabilita' o
        la sua deviazione resta leggibile."""
        assert ENVELOPE_STYLES[variant][0] == ENVELOPE_STYLES[base][0]
        assert ENVELOPE_STYLES[variant][1] != ENVELOPE_STYLES[base][1]

    def test_prob_variants_are_thinner_than_their_base(self):
        for key, (_, width) in ENVELOPE_STYLES.items():
            if key.endswith('_prob'):
                base = key[:-len('_prob')]
                assert width < ENVELOPE_STYLES[base][1], key

    def test_default_style_is_the_historical_one(self):
        """Chi non ha una entry disegna come si e' sempre disegnato: linea
        piena, spessore 1.1."""
        assert ENVELOPE_STYLE_DEFAULT == ('-', 1.1)


# =============================================================================
# LA COLORMAP ACROMATICA
# =============================================================================

class TestBwColormap:
    """`pitch_div_bw`: la divergente del pitch spesa tutta sulla luminanza."""

    def cmap(self):
        return plt.get_cmap('pitch_div_bw')

    def test_is_registered_under_its_name(self):
        """La config la nomina come stringa, come 'pitch_div': senza
        registrazione il preset fallirebbe dentro `plt.get_cmap`."""
        assert self.cmap() is not None

    @pytest.mark.parametrize('x', [0.0, 0.15, 0.25, 0.5, 0.75, 0.9, 1.0])
    def test_is_achromatic(self, x):
        r, g, b, _ = self.cmap()(x)
        assert r == pytest.approx(g, abs=1e-6)
        assert g == pytest.approx(b, abs=1e-6)

    def test_luminance_is_strictly_increasing(self):
        """E' l'invariante che salva il segno del detune: piu' acuto = piu'
        chiaro, senza inversioni lungo il percorso."""
        values = [self.cmap()(x / 64.0)[0] for x in range(65)]
        for lo, hi in zip(values, values[1:]):
            assert hi > lo

    def test_the_arms_stop_short_of_black_and_white(self):
        """Compressa a circa 0.15-0.85: col braccio alto sul bianco i grani
        acuti sparirebbero sulla carta, col basso sul nero si confonderebbero
        con assi e griglia."""
        assert 0.10 <= self.cmap()(0.0)[0] <= 0.20
        assert 0.80 <= self.cmap()(1.0)[0] <= 0.90

    def test_the_centre_is_mid_grey(self):
        """Zero cent = nessun detune: sta in mezzo, come il #777777 della
        mappa a colori."""
        assert self.cmap()(0.5)[0] == pytest.approx(0.5, abs=0.04)

    def test_the_colour_map_is_untouched(self):
        """Il preset aggiunge, non sostituisce: 'pitch_div' resta cromatica."""
        r, g, b, _ = plt.get_cmap('pitch_div')(0.0)
        assert not (r == g == b)


# =============================================================================
# IL PRESET NELLA CONFIG
# =============================================================================

class TestBwPreset:
    """`bw: True` sposta i default; l'utente resta l'ultima parola."""

    def test_off_by_default(self):
        assert plain_config()['bw'] is False

    def test_off_changes_nothing(self):
        """A flag spento la partitura e' identica a prima: e' la condizione
        per cui questa issue non tocca nessuna figura gia' generata."""
        before = plain_config()
        after = plain_config(bw=False)
        after.pop('bw')
        before.pop('bw')
        assert after == before

    def test_grains_switch_to_the_achromatic_map(self):
        assert bw_config()['grain_colormap'] == 'pitch_div_bw'

    def test_every_envelope_turns_black(self):
        colors = bw_config()['envelope_colors']
        assert set(colors) == set(ENVELOPE_COLORS)
        assert set(colors.values()) == {BW_ENVELOPE_COLOR}

    def test_envelope_styles_come_in(self):
        assert bw_config()['envelope_styles'] == ENVELOPE_STYLES

    def test_styles_are_empty_without_the_preset(self):
        """Senza preset nessuno stile: le curve restano piene, distinte dalla
        tinta come sempre."""
        assert plain_config()['envelope_styles'] == {}

    def test_the_chromatic_accents_turn_grey(self):
        """Un preset monocromo lo e' anche a schermo: waveform, maschera del
        loop e lente non restano le uniche macchie di colore."""
        config = bw_config()
        for key in ('waveform_color', 'loop_mask_color', 'magnify_color'):
            r, g, b, _ = matplotlib.colors.to_rgba(config[key])
            assert r == g == b, key

    def test_an_explicit_override_beats_the_preset(self):
        """Il preset e' un default, non un lucchetto."""
        config = bw_config(grain_colormap='turbo')
        assert config['grain_colormap'] == 'turbo'

    def test_a_partial_override_merges_onto_the_preset(self):
        """Ritoccare un colore non riporta a colori tutti gli altri: il merge
        parte dal preset, non dai default cromatici."""
        config = bw_config(envelope_colors={'volume': '#ff0000'})
        assert config['envelope_colors']['volume'] == '#ff0000'
        assert config['envelope_colors']['pan'] == BW_ENVELOPE_COLOR

    def test_a_partial_style_override_merges_onto_the_preset(self):
        config = bw_config(envelope_styles={'volume': ('-', 3.0)})
        assert config['envelope_styles']['volume'] == ('-', 3.0)
        assert config['envelope_styles']['pan'] == ENVELOPE_STYLES['pan']

    def test_the_preset_does_not_leak_into_the_module_table(self):
        """La tavola di modulo non si tocca: due visualizer, uno B&W e uno no,
        convivono."""
        bw_config()['envelope_colors']['volume'] = '#123456'
        assert ENVELOPE_COLORS['volume'] != '#123456'
        assert plain_config()['envelope_colors']['volume'] == ENVELOPE_COLORS['volume']

    def test_unknown_keys_still_refused_with_the_preset_on(self):
        with pytest.raises(ValueError):
            VisualizerConfig.from_overrides({'bw': True, 'banana': 1})

    def test_direct_construction_does_not_apply_the_preset(self):
        """La porta e' `from_overrides`, ed e' quella che il visualizer usa.
        Il costruttore non sa quali campi il chiamante ha dichiarato, quindi
        non saprebbe quali sostituire senza cancellare le scelte esplicite: il
        preset li' non si applica, e questo test lo dice invece di lasciarlo
        scoprire."""
        config = VisualizerConfig(bw=True).as_dict()
        assert config['grain_colormap'] == 'pitch_div'
        assert config['envelope_styles'] == {}


# =============================================================================
# L'ALPHA
# =============================================================================

class TestFixedAlpha:
    """Sul bianco l'alpha e la luminanza del grigio sono lo STESSO canale.

    Composito su fondo bianco: `a*g + (1-a)`. Con alpha libera un grano scuro
    (detune negativo) suonato piano schiarisce fino a leggersi come acuto: il
    canale che il preset esiste per salvare verrebbe mangiato da quello che
    prova a conservare. Il preset fissa l'alpha, quindi il composito resta una
    funzione monotona del solo pitch.

    Il volume smette di dirsi nel riempimento del grano: e' il prezzo, ed e'
    reversibile passando `grain_alpha_range` nella config.
    """

    def test_alpha_range_is_degenerate(self):
        lo, hi = bw_config()['grain_alpha_range']
        assert lo == hi

    def test_alpha_leaves_room_for_overlap(self):
        """Non 1.0: a opacita' piena un cluster denso diventa una lastra e la
        densita' smette di leggersi."""
        lo, hi = bw_config()['grain_alpha_range']
        assert 0.8 <= lo < 1.0

    def test_the_default_alpha_range_is_untouched(self):
        assert plain_config()['grain_alpha_range'] == (0.3, 1.0)

    def test_composited_luminance_orders_by_pitch_not_by_volume(self):
        """Il test che vale: un grano grave e piano resta piu' scuro di uno
        acuto e forte, che e' cio' che oggi non e' vero."""
        viz = ScoreVisualizer(MagicMock(streams=[MagicMock()]), config={'bw': True})
        cents_range = (-300.0, 300.0)

        def composited(cents, volume_db):
            grey = viz._pitch_to_color(2.0 ** (cents / 1200.0), cents_range)[0]
            alpha = viz._volume_to_alpha(volume_db)
            return alpha * grey + (1.0 - alpha)

        quiet_low = composited(-300.0, -60.0)   # grave, pianissimo
        loud_high = composited(+300.0, 0.0)     # acuto, forte
        loud_low = composited(-300.0, 0.0)
        quiet_high = composited(+300.0, -60.0)
        assert quiet_low < loud_high
        assert quiet_low == pytest.approx(loud_low)
        assert quiet_high == pytest.approx(loud_high)


# =============================================================================
# LO STILE ARRIVA AL DISEGNO
# =============================================================================

def make_env_viz(config):
    """Un visualizer ridotto alla sola corsia envelope, come in
    test_score_visualizer_per_segment."""
    viz = ScoreVisualizer.__new__(ScoreVisualizer)
    viz.config = config
    viz.config['envelope_ranges'] = {'density': (0, 100)}
    viz._get_stream_envelopes = lambda s: {'density': s.density}
    viz._normalize_envelope_value = lambda name, v: v / 100.0
    viz._annotate_breakpoints = lambda *a, **k: None
    return viz


def make_env_stream(env):
    stream = MagicMock()
    stream.onset = 0.0
    stream.duration = 1.0
    stream.density = env
    return stream


class TestStyleReachesTheCurve:

    def _draw(self, config):
        from pge.envelopes.envelope import Envelope
        viz = make_env_viz(config)
        fig, ax = plt.subplots()
        viz._draw_envelopes(ax, make_env_stream(Envelope([[0, 0], [1, 100]])),
                            0.0, 1.0, 0.0, 1.0)
        return ax.lines

    def test_without_the_preset_the_curve_is_solid(self):
        """Il default e' il disegno storico, byte per byte: linea piena a
        1.1."""
        lines = self._draw(plain_config())
        assert len(lines) == 1
        assert lines[0].get_linestyle() == '-'
        assert lines[0].get_linewidth() == pytest.approx(1.1)

    def test_with_the_preset_the_curve_takes_its_pattern(self):
        lines = self._draw(bw_config())
        expected_ls, expected_lw = ENVELOPE_STYLES['density']
        assert lines[0].get_linewidth() == pytest.approx(expected_lw)
        assert lines[0].get_linestyle() != '-'

    def test_the_curve_is_black(self):
        lines = self._draw(bw_config())
        assert matplotlib.colors.to_hex(lines[0].get_color()) == BW_ENVELOPE_COLOR

    def test_step_curves_take_the_pattern_too(self):
        from pge.envelopes.envelope import Envelope
        viz = make_env_viz(bw_config())
        fig, ax = plt.subplots()
        env = Envelope({'type': 'step', 'points': [[0, 0], [0.5, 100], [1, 0]]})
        viz._draw_envelopes(ax, make_env_stream(env), 0.0, 1.0, 0.0, 1.0)
        assert ax.lines[0].get_linestyle() != '-'

    def test_per_segment_curves_take_the_pattern_too(self):
        """Il rendering per-segmento (issue #68) disegna una linea per
        segmento: se lo stile non passasse di li', un envelope eterogeneo
        resterebbe pieno mentre gli altri sono tratteggiati."""
        from pge.envelopes.envelope import Envelope
        viz = make_env_viz(bw_config())
        fig, ax = plt.subplots()
        env = Envelope([[0, 0, 'step'], [0.5, 100, 'linear'], [1, 0]])
        viz._draw_envelopes(ax, make_env_stream(env), 0.0, 1.0, 0.0, 1.0)
        assert len(ax.lines) >= 2
        for line in ax.lines:
            assert line.get_linestyle() != '-'

    def test_per_voice_curves_inherit_the_style_of_their_base(self):
        """Le curve per-voce '__vN' prendono il colore della base (issue #90):
        lo stile segue la stessa regola, o una voce sarebbe l'unica linea
        piena della corsia."""
        viz = make_env_viz(bw_config())
        assert viz._envelope_style('density__v2') == ENVELOPE_STYLES['density']

    def test_an_unknown_key_falls_back_to_the_historical_style(self):
        viz = make_env_viz(bw_config())
        assert viz._envelope_style('banana') == ENVELOPE_STYLE_DEFAULT


class TestStyleReachesTheLegend:
    """La legenda e' la chiave di lettura: se il suo tratto non mostra il
    pattern, il pattern sulla curva non e' attribuibile a niente."""

    def _legend_line(self, config, param='density'):
        viz = ScoreVisualizer.__new__(ScoreVisualizer)
        viz.config = config
        fig, ax = plt.subplots()
        viz._draw_envelope_legend(ax, [(param, 0.5, 's1')])
        return ax.lines[0]

    def test_without_the_preset_the_key_is_unchanged(self):
        line = self._legend_line(plain_config())
        assert line.get_linestyle() == '-'
        assert line.get_linewidth() == pytest.approx(2)
        assert list(line.get_xdata()) == [0.1, 0.15]

    def test_the_key_shows_the_curve_pattern(self):
        line = self._legend_line(bw_config())
        assert line.get_linestyle() != '-'

    def test_the_key_carries_the_curve_width(self):
        """Lo spessore e' meta' dell'informazione: e' li' che una probabilita'
        si distingue dalla sua base. Una chiave ingrossata per farsi vedere la
        perderebbe — e allungherebbe anche il ciclo del tratteggio, che
        matplotlib scala per lo spessore, riportando la chiave a leggersi
        piena."""
        for param in ('density', 'volume_prob', 'volume_range'):
            line = self._legend_line(bw_config(), param)
            assert line.get_linewidth() == pytest.approx(
                ENVELOPE_STYLES[param][1])

    def test_a_styled_key_gets_a_longer_stroke(self):
        """Il tratto storico e' il 5% della colonna: qualche punto, meno di un
        ciclo di tratteggio, quindi si leggerebbe pieno."""
        line = self._legend_line(bw_config())
        x0, x1 = line.get_xdata()
        assert (x1 - x0) > 0.05 * 3
        assert x1 < 0.4  # non entra sotto il testo della legenda

    def test_the_stroke_is_the_same_length_for_a_solid_entry(self):
        """Due lunghezze di chiave nella stessa colonna fanno leggere lo stub
        corto come un altro tratteggio: la misura e' una sola."""
        dashed = self._legend_line(bw_config(), 'density').get_xdata()
        solid = self._legend_line(bw_config(), 'volume').get_xdata()
        assert list(solid) == list(dashed)
