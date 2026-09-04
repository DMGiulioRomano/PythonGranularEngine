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
import numpy as np
import pytest
from unittest.mock import MagicMock, patch

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


class TestAMalformedStyleNamesItself:
    """`envelope_styles` e' l'unico dizionario-dato il cui VALORE viene
    spacchettato in due, e una stringa ne e' una coppia plausibile:
    `tuple('--')` vale `('-', '-')`. Senza guardia l'errore arriva da dentro
    matplotlib — `could not convert string to float: '-'` — e non nomina ne'
    la chiave di config ne' il parametro.

    Lo schema verifica i nomi e non i tipi per scelta dichiarata (vedi il
    docstring di rendering.visualizer_config): questo e' il caso che quella
    scelta lascia scoperto, e si chiude nel lettore.
    """

    @pytest.mark.parametrize('bad', [
        '--',              # coppia plausibile: ('-', '-')
        5,                 # non spacchettabile
        ('-', 'spesso'),   # spessore non numerico
        ('-', 1.1, 0),     # tre valori
    ])
    def test_the_error_names_the_key_and_the_value(self, bad):
        viz = make_env_viz(plain_config(envelope_styles={'density': bad}))
        with pytest.raises(ValueError) as exc:
            viz._envelope_style('density')
        messaggio = str(exc.value)
        assert 'envelope_styles' in messaggio
        assert 'density' in messaggio
        assert repr(bad) in messaggio

    def test_a_well_formed_pair_passes(self):
        """Anche scritta come lista: e' la forma in cui arriva da YAML o JSON."""
        viz = make_env_viz(plain_config(envelope_styles={'density': [':', 2]}))
        assert viz._envelope_style('density') == (':', 2.0)

    def test_the_table_of_the_preset_passes_whole(self):
        """Il preset stesso non deve poter cadere in questa guardia."""
        viz = make_env_viz(bw_config())
        for key in ENVELOPE_STYLES:
            assert viz._envelope_style(key) == ENVELOPE_STYLES[key]


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


# =============================================================================
# LA CHIAVE DI LETTURA: LA COLORBAR (review #249, punto 1)
# =============================================================================

def luminance(color):
    """Luminanza relativa di un colore, come la vede una stampa in grigio."""
    r, g, b, _ = matplotlib.colors.to_rgba(color)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def composited(grey, alpha):
    """Il grigio che finisce sulla carta: fondo bianco, `a*g + (1-a)`."""
    return alpha * grey + (1.0 - alpha)


class TestColorbarMatchesTheGrains:
    """La colorbar del pitch e' la chiave di lettura della mappa acromatica:
    se il suo grigio non e' quello dei grani, chi accosta un grano alla barra
    sbaglia sistematicamente il verso.

    Coi grani a opacita' variabile la barra non poteva che essere indicativa —
    non c'e' un'alpha sola da mostrare. Col preset l'alpha e' fissata, quindi
    la corrispondenza e' esprimibile ed e' un dovere.
    """

    def _colorbar_greys(self, config):
        """I grigi effettivamente dipinti nella colonna della colorbar."""
        viz = ScoreVisualizer(MagicMock(streams=[MagicMock()]), config=config)
        fig = plt.figure(figsize=(2, 4), facecolor='white')
        gs = fig.add_gridspec(1, 1)
        viz._add_pitch_colorbar(fig, gs[0, 0], (-300.0, 300.0), True)
        fig.canvas.draw()
        cax = fig.axes[-1]
        box = cax.get_window_extent()
        buf = np.asarray(fig.canvas.buffer_rgba(), dtype=float) / 255.0
        h = buf.shape[0]
        # Colonna centrale della barra, dal basso (grave) all'alto (acuto).
        col = int((box.x0 + box.x1) / 2)
        y0, y1 = int(box.y0) + 3, int(box.y1) - 3
        strip = buf[h - y1:h - y0, col, :3]
        return strip[::-1]   # dal grave all'acuto

    def test_the_bar_carries_the_grain_alpha(self):
        """Il grigio in cima e in fondo alla barra e' quello di un grano allo
        stesso pitch, non quello della mappa a opacita' piena."""
        config = bw_config()
        alpha = config['grain_alpha_range'][0]
        cmap = plt.get_cmap(config['grain_colormap'])
        strip = self._colorbar_greys(config)
        for x, sample in ((0.0, strip[0]), (1.0, strip[-1])):
            atteso = composited(cmap(x)[0], alpha)
            assert sample[0] == pytest.approx(atteso, abs=0.02)

    def test_the_bar_is_still_achromatic(self):
        strip = self._colorbar_greys(bw_config())
        assert np.allclose(strip[:, 0], strip[:, 1], atol=0.01)
        assert np.allclose(strip[:, 1], strip[:, 2], atol=0.01)

    def test_a_variable_alpha_leaves_the_bar_opaque(self):
        """Senza preset l'alpha varia col volume: non c'e' un valore solo da
        mostrare, e la barra resta quella storica a opacita' piena."""
        config = plain_config()
        cmap = plt.get_cmap(config['grain_colormap'])
        strip = self._colorbar_greys(config)
        assert strip[0][0] == pytest.approx(cmap(0.0)[0], abs=0.02)

    def test_a_fixed_alpha_reaches_the_bar_even_without_the_preset(self):
        """La condizione e' l'alpha FISSATA, non `bw`.

        Una config a colori che fissa `grain_alpha_range` da se' ha esattamente
        lo stesso bisogno del preset, e la barra la segue. E' anche l'unico
        punto in cui l'issue #248 si vede a preset spento: legarlo a un test
        invece che a un commento e' il modo di non far passare per no-op una
        cosa che no-op non e'.
        """
        config = plain_config(grain_alpha_range=(0.6, 0.6))
        cmap = plt.get_cmap(config['grain_colormap'])
        strip = self._colorbar_greys(config)
        assert strip[0][0] == pytest.approx(composited(cmap(0.0)[0], 0.6),
                                            abs=0.02)
        # E non e' il colore nudo della mappa, che e' cio' che dipingeva prima.
        assert abs(strip[0][0] - cmap(0.0)[0]) > 0.05


class TestTheDocstringNumbersAreThePageNumbers:
    """I due estremi e il centro, come finiscono sulla carta."""

    def test_the_page_greys_stay_off_black_and_white(self):
        cmap = plt.get_cmap('pitch_div_bw')
        alpha = bw_config()['grain_alpha_range'][0]
        assert 0.20 <= composited(cmap(0.0)[0], alpha) <= 0.28
        assert 0.82 <= composited(cmap(1.0)[0], alpha) <= 0.90

    def test_the_sign_of_the_detune_survives_on_the_page(self):
        """Il numero che conta davvero: il salto fra due detune simmetrici,
        sulla pagina e non sulla mappa."""
        cmap = plt.get_cmap('pitch_div_bw')
        alpha = bw_config()['grain_alpha_range'][0]
        for span in (0.5, 0.25):   # +/-300 e +/-150 cent su un range di 300
            lo = composited(cmap(0.5 - span)[0], alpha)
            hi = composited(cmap(0.5 + span)[0], alpha)
            assert (hi - lo) > 0.25


# =============================================================================
# LA LENTE (review #249, punto 2)
# =============================================================================

FAKE_SR = 44100
FAKE_AUDIO = np.sin(
    2 * np.pi * 440 * np.linspace(0, 4.0, int(44100 * 4.0))
).astype(np.float32)


def lens_scene():
    """Uno stream con due curve e una lente puntata a meta' corsa."""
    from pge.envelopes.envelope import Envelope
    s = MagicMock()
    s.stream_id = 's1'
    s.onset = 0.0
    s.duration = 20.0
    s.sample = 'piano.wav'
    s.voices = [[_lens_grain(i * 2.5) for i in range(8)]]
    for name in ('volume', 'pan', 'pointer_start', 'num_voices',
                 'scatter', 'pointer_speed'):
        delattr(s, name)
    s.density = Envelope([[0, 10.0], [20, 30.0]])
    return [s]


def _lens_grain(onset):
    g = MagicMock()
    g.onset = onset
    g.duration = 0.05
    g.pointer_pos = 0.5
    g.pitch_ratio = 1.0
    g.volume = -6.0
    return g


def render_with_lens(config):
    cfg = {'page_duration': 30.0, 'magnify_targets': [{'t': 6.0, 'y': 1.0}]}
    cfg.update(config)
    viz = ScoreVisualizer(MagicMock(streams=lens_scene()), config=cfg)
    with patch('soundfile.read', return_value=(FAKE_AUDIO, FAKE_SR)):
        viz.analyze()
        fig = viz.render_page(0)
    fig.canvas.draw()
    return fig


def projection_markers(fig):
    return [a for ax in fig.axes for a in ax.lines
            if a.get_gid() == 'poc-projection-marker']


class TestLensMarkerStaysCircled:
    """Il marker della proiezione e' un pallino CERCHIATO: la faccia dice a
    quale curva appartiene, l'anello che viene dalla lente.

    Col preset la faccia e' nera come ogni envelope e l'accento della lente e'
    quasi nero: l'anello sparirebbe, e il marker diventerebbe indistinguibile
    da un breakpoint qualunque — cioe' il preset toglierebbe una lettura
    mentre dichiara di darne.
    """

    def test_the_ring_contrasts_with_the_face(self):
        markers = projection_markers(render_with_lens({'bw': True}))
        assert markers
        for m in markers:
            gap = abs(luminance(m.get_markerfacecolor())
                      - luminance(m.get_markeredgecolor()))
            assert gap > 0.5, gap

    def test_the_ring_is_wide_enough_to_read(self):
        markers = projection_markers(render_with_lens({'bw': True}))
        for m in markers:
            assert m.get_markeredgewidth() >= 1.2

    def test_without_the_preset_the_marker_is_unchanged(self):
        """A flag spento l'anello resta l'accento della lente, spesso 0.8."""
        markers = projection_markers(render_with_lens({}))
        assert markers
        accento = plain_config()['magnify_color']
        for m in markers:
            assert matplotlib.colors.to_hex(m.get_markeredgecolor()) == accento
            assert m.get_markeredgewidth() == pytest.approx(0.8)

    def test_the_edge_defaults_to_the_lens_accent(self):
        viz = ScoreVisualizer.__new__(ScoreVisualizer)
        viz.config = plain_config()
        edge, width = viz._projection_marker_edge()
        assert edge == plain_config()['magnify_color']
        assert width == pytest.approx(0.8)

    def test_the_preset_overrides_only_the_marker_edge(self):
        """L'accento della lente NON cambia: e' scelto bene contro i grani
        (piu' scuro del grano piu' scuro). Quello che cambia e' l'anello, che
        e' dove incontra il nero delle curve."""
        config = bw_config()
        assert config['magnify_color'] == '#1a1a1a'
        edge, _ = _viz_with(config)._projection_marker_edge()
        assert luminance(edge) > 0.9


def _viz_with(config):
    viz = ScoreVisualizer.__new__(ScoreVisualizer)
    viz.config = config
    return viz


# =============================================================================
# IL PRESET NON DEVE POTER DIVENTARE INERTE (review #249, punti 3 e 4)
# =============================================================================

class TestThePresetCannotBeShadowed:

    def test_bw_is_not_read_by_the_drawing_code(self):
        """`bw` seleziona default e basta. Finche' il disegno lo rilegge,
        costruire `VisualizerConfig(bw=True)` a mano non e' inerte ma
        INCOERENTE: partitura a colori con un elemento grigio scuro."""
        import inspect
        from pge.rendering import score_visualizer
        sorgente = inspect.getsource(score_visualizer)
        assert "config.get('bw')" not in sorgente
        assert "config['bw']" not in sorgente

    def test_the_stream_label_colour_is_a_config_key(self):
        assert plain_config()['stream_label_color'] == 'darkblue'
        assert luminance(bw_config()['stream_label_color']) < 0.2
