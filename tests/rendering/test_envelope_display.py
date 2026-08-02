# tests/rendering/test_envelope_display.py
"""
TDD suite per rendering.envelope_display.

Il modulo risponde a due domande sulle curve di uno stream: quanto e' ampia la
finestra verticale in cui disegnarle (il range di display data-driven, issue
#114) e dove cade un valore dentro quella finestra (la normalizzazione a [0,1]).
E' la stessa logica che prima viveva in ScoreVisualizer._compute_display_ranges
e _normalize_envelope_value, ora isolata e matplotlib-free.

Due differenze di interfaccia rispetto ai metodi da cui viene:

- prende `stream_start` (float) e non uno Stream: la logica usava solo
  `stream.onset`, e chiedere l'oggetto intero era una dipendenza piu' larga
  del necessario;
- prende i range come argomento invece di leggerli da `self`. Nel visualizer
  erano stato mutabile (`_current_display_ranges`) scritto da _draw_envelopes e
  letto da _normalize_envelope_value: un canale fra metodi, non un dato.
"""

from types import SimpleNamespace

import pytest

from pge.envelopes.envelope import Envelope
from pge.rendering.envelope_display import (
    display_ranges,
    normalize,
    segment_strategy_name,
    is_per_segment_heterogeneous,
)


PAD = 0.05
SAMPLES = 128
PAN_RANGE = (-180, 180)


class TestDisplayRanges:
    """Il range di display segue l'escursione reale dei valori nella finestra
    visibile, piu' un margine proporzionale. Nessun clamp a range fissi."""

    def test_range_follows_real_excursion(self):
        """pointer_speed che si muove 2.0 -> 6.0: span 4, pad 5% per lato."""
        envelopes = {'pointer_speed': Envelope([[0, 2.0], [10, 6.0]])}
        ranges = display_ranges(
            envelopes, stream_start=0.0, t_start=0.0, t_end=10.0,
            pad_ratio=PAD, samples=SAMPLES)
        assert ranges['pointer_speed'] == pytest.approx((1.8, 6.2))

    def test_pan_is_excluded(self):
        """pan e' ciclico: resta sul range fisso, non riceve un range di
        display. E' l'unica eccezione alla regola data-driven."""
        envelopes = {'pan': Envelope([[0, -10.0], [10, 10.0]])}
        ranges = display_ranges(
            envelopes, stream_start=0.0, t_start=0.0, t_end=10.0,
            pad_ratio=PAD, samples=SAMPLES)
        assert 'pan' not in ranges

    def test_a_per_voice_pan_is_excluded_too(self):
        """L'esclusione si decide sul nome BASE, come la normalizzazione.

        Una curva per-voce eredita la natura del parametro da cui viene: se
        qui il confronto fosse sul nome pieno, `pan__v1` riceverebbe un range
        data-driven mentre `normalize` continuerebbe a trattarlo da ciclico —
        e la curva verrebbe disegnata su una scala diversa da quella con cui
        e' stata misurata.
        """
        envelopes = {'pan__v1': Envelope([[0, -10.0], [10, 10.0]])}
        ranges = display_ranges(
            envelopes, stream_start=0.0, t_start=0.0, t_end=10.0,
            pad_ratio=PAD, samples=SAMPLES)
        assert 'pan__v1' not in ranges

    def test_the_two_sides_agree_on_a_per_voice_pan(self):
        """La controprova della stessa regola dall'altro lato: `normalize`
        tratta `pan__v1` da ciclico, cioe' non cerca il suo range fra quelli
        di display. Le due funzioni devono dire la stessa cosa, o la curva
        finirebbe fuori corsia."""
        assert normalize('pan__v1', 180.0, {}, pan_range=(-180, 180)) == \
            normalize('pan', 180.0, {}, pan_range=(-180, 180))

    def test_constant_envelope_gets_a_range_around_its_value(self):
        """Escursione nulla: il pad si calcola sul valore, non sullo span, e il
        range resta non degenere. Un range collassato renderebbe la
        normalizzazione una divisione per zero."""
        envelopes = {'density': Envelope([[0, 50.0], [10, 50.0]])}
        ranges = display_ranges(
            envelopes, stream_start=0.0, t_start=0.0, t_end=10.0,
            pad_ratio=PAD, samples=SAMPLES)
        lo, hi = ranges['density']
        assert (lo, hi) == pytest.approx((47.5, 52.5))

    def test_constant_envelope_at_zero_still_gets_a_width(self):
        """Costante a zero: il pad proporzionale sarebbe zero e il range
        collasserebbe. E' il caso che il margine minimo esiste per coprire."""
        envelopes = {'volume': Envelope([[0, 0.0], [10, 0.0]])}
        ranges = display_ranges(
            envelopes, stream_start=0.0, t_start=0.0, t_end=10.0,
            pad_ratio=PAD, samples=SAMPLES)
        lo, hi = ranges['volume']
        assert hi > lo

    def test_internal_breakpoint_peak_is_exact(self):
        """Il picco cade su un breakpoint interno che la griglia di
        campionamento non colpisce: senza includere i breakpoint il massimo
        risulterebbe leggermente sotto quello vero, e la curva toccherebbe il
        bordo della corsia."""
        envelopes = {'density': Envelope([[0, 0.0], [5, 100.0], [10, 0.0]])}
        ranges = display_ranges(
            envelopes, stream_start=0.0, t_start=0.0, t_end=10.0,
            pad_ratio=PAD, samples=SAMPLES)
        lo, hi = ranges['density']
        assert (lo, hi) == pytest.approx((-5.0, 105.0))

    def test_only_the_visible_window_counts(self):
        """La curva sale 0 -> 100 su 10s ma se ne vede solo la prima meta':
        il range segue quello che si vede, non l'intera curva."""
        envelopes = {'density': Envelope([[0, 0.0], [10, 100.0]])}
        ranges = display_ranges(
            envelopes, stream_start=0.0, t_start=0.0, t_end=5.0,
            pad_ratio=PAD, samples=SAMPLES)
        assert ranges['density'] == pytest.approx((-2.5, 52.5))

    def test_window_is_absolute_breakpoints_are_relative(self):
        """I breakpoint sono relativi allo stream, la finestra e' in tempo
        assoluto: stream_start fa da ponte. Stesso stream della prova
        precedente ma con onset 100."""
        envelopes = {'density': Envelope([[0, 0.0], [10, 100.0]])}
        ranges = display_ranges(
            envelopes, stream_start=100.0, t_start=100.0, t_end=105.0,
            pad_ratio=PAD, samples=SAMPLES)
        assert ranges['density'] == pytest.approx((-2.5, 52.5))

    def test_window_starting_before_the_stream_is_harmless(self):
        """Finestra di pagina che inizia prima dell'onset dello stream: il
        range non cambia.

        Regge per due ragioni sovrapposte: il clamp del tempo relativo a zero,
        e il fatto che Envelope.evaluate SATURA fuori dominio (restituisce il
        primo breakpoint), gia' presente nel campione. Verificato togliendo il
        clamp: la suite resta verde, quindi qui e' difensivo, non portante.
        """
        envelopes = {'density': Envelope([[0, 0.0], [10, 100.0]])}
        ranges = display_ranges(
            envelopes, stream_start=100.0, t_start=90.0, t_end=105.0,
            pad_ratio=PAD, samples=SAMPLES)
        assert ranges['density'] == pytest.approx((-2.5, 52.5))

    def test_nothing_to_measure_means_no_range(self):
        """Con una griglia vuota e nessun breakpoint dentro la finestra non
        c'e' niente da misurare. La curva esce senza range — e normalize la
        mette al centro della corsia — invece di far esplodere min() su una
        lista vuota."""
        envelopes = {'density': Envelope([[0, 0.0], [10, 100.0]])}
        ranges = display_ranges(
            envelopes, stream_start=0.0, t_start=20.0, t_end=20.0,
            pad_ratio=PAD, samples=0)
        assert 'density' not in ranges

    def test_an_empty_grid_still_uses_the_breakpoints(self):
        """La guardia non deve mangiarsi il caso in cui i breakpoint ci sono:
        senza griglia il range si misura su quelli."""
        envelopes = {'density': Envelope([[0, 0.0], [10, 100.0]])}
        ranges = display_ranges(
            envelopes, stream_start=0.0, t_start=0.0, t_end=10.0,
            pad_ratio=PAD, samples=0)
        assert ranges['density'] == pytest.approx((-5.0, 105.0))


class TestNormalize:
    """Dove cade un valore dentro la corsia, come frazione della sua altezza.
    I range arrivano come argomento: nel visualizer erano stato mutabile
    condiviso fra metodi."""

    def test_value_maps_onto_the_active_range(self):
        """Gli estremi del range vanno sui bordi della corsia, il centro al
        centro."""
        ranges = {'pointer_speed': (0.3, 0.7)}
        assert normalize('pointer_speed', 0.3, ranges,
                         pan_range=PAN_RANGE) == pytest.approx(0.0)
        assert normalize('pointer_speed', 0.5, ranges,
                         pan_range=PAN_RANGE) == pytest.approx(0.5)
        assert normalize('pointer_speed', 0.7, ranges,
                         pan_range=PAN_RANGE) == pytest.approx(1.0)

    def test_pan_wraps_and_uses_the_fixed_range(self):
        """pan e' l'unico ciclico: 270 gradi e' -90, che nel range +/-180 cade
        a un quarto della corsia; 360 e' 0, cioe' il centro. Non compare mai in
        `ranges` (display_ranges lo esclude), quindi il suo range e' quello
        fisso passato a parte."""
        assert normalize('pan', 270.0, {}, pan_range=PAN_RANGE) == pytest.approx(0.25)
        assert normalize('pan', 360.0, {}, pan_range=PAN_RANGE) == pytest.approx(0.5)

    def test_pan_is_clamped(self):
        """Dopo il wrap pan resta dentro la corsia: e' l'unico parametro
        clampato, perche' il suo range e' fisso e non insegue i dati."""
        assert 0.0 <= normalize('pan', 1234.0, {}, pan_range=PAN_RANGE) <= 1.0

    def test_missing_range_falls_back_to_mid_lane(self):
        """Parametro senza range: si va al centro corsia invece di sollevare.
        Nel visualizer era il fallback difensivo di un canale di stato che
        poteva non essere stato scritto; qui i range sono un argomento, quindi
        e' il contratto per un dizionario incompleto."""
        assert normalize('density', 42.0, {}, pan_range=PAN_RANGE) == pytest.approx(0.5)

    def test_degenerate_range_falls_back_to_mid_lane(self):
        """Range collassato: niente divisione per zero, il valore va al centro.

        display_ranges non ne produce mai (somma sempre un pad positivo), ma
        ora che i range sono un argomento un chiamante puo' passarne uno."""
        assert normalize('density', 50.0, {'density': (50.0, 50.0)},
                         pan_range=PAN_RANGE) == pytest.approx(0.5)

    def test_value_outside_the_range_is_not_clamped(self):
        """Il cuore della issue #114: due valori diversi sopra il massimo
        devono restare distinti. Col vecchio clamp collassavano entrambi su
        1.0 e la curva appariva piatta contro il bordo."""
        ranges = {'density': (0.0, 100.0)}
        a = normalize('density', 150.0, ranges, pan_range=PAN_RANGE)
        b = normalize('density', 200.0, ranges, pan_range=PAN_RANGE)
        assert a > 1.0 and b > 1.0
        assert a < b

    def test_per_voice_key_scales_on_its_own_range(self):
        """Ogni curva per-voce '__vN' (issue #90) ha un range PROPRIO: si scala
        sulla propria escursione, non su quella del parametro base.

        Conseguenza da conoscere: due voci con escursioni diverse riempiono
        entrambe la corsia, quindi le tracce non sono confrontabili fra loro a
        vista. Nella baseline di caratterizzazione voice_pitch_offset__v1/v2/v3
        di 'pitch_step' hanno range 2.85-3.15, 5.7-6.3 e 8.55-9.45.
        """
        ranges = {
            'voice_pitch_offset__v1': (2.85, 3.15),
            'voice_pitch_offset__v2': (5.7, 6.3),
        }
        assert normalize('voice_pitch_offset__v1', 3.0, ranges,
                         pan_range=PAN_RANGE) == pytest.approx(0.5)
        assert normalize('voice_pitch_offset__v2', 6.0, ranges,
                         pan_range=PAN_RANGE) == pytest.approx(0.5)

    def test_per_voice_pan_is_still_cyclic(self):
        """Il nome base serve a una cosa sola: riconoscere pan. 'pan__v1' e'
        ciclico come 'pan', anche se il suo nome pieno non e' 'pan'."""
        assert normalize('pan__v1', 270.0, {},
                         pan_range=PAN_RANGE) == pytest.approx(0.25)


class TestSegmentStrategies:
    """Il nome canonico dell'interpolazione di un segmento, e se un envelope
    ne mescola piu' di uno. Serve al disegno per decidere se tracciare la
    curva in blocco o segmento per segmento (issue #68)."""

    def test_strategy_name_from_the_class(self):
        """Il nome esce dal nome della classe di interpolazione."""
        from pge.envelopes.envelope_interpolation import (
            StepInterpolation, LinearInterpolation, CubicInterpolation)

        for interpolation, expected in (
            (StepInterpolation(), 'step'),
            (LinearInterpolation(), 'linear'),
            (CubicInterpolation(), 'cubic'),
        ):
            segment = SimpleNamespace(strategy=interpolation)
            assert segment_strategy_name(segment) == expected

    def test_unknown_strategy_reads_as_linear(self):
        """Un'interpolazione non riconosciuta ricade su 'linear': il disegno
        deve poter procedere comunque, la retta e' l'ipotesi neutra."""
        class WeirdInterpolation:
            pass

        segment = SimpleNamespace(strategy=WeirdInterpolation())
        assert segment_strategy_name(segment) == 'linear'


class TestHeterogeneity:
    """Un envelope e' eterogeneo se mescola interpolazioni diverse: allora va
    disegnato segmento per segmento invece che in blocco (issue #68)."""

    def test_uniform_envelope_is_not_heterogeneous(self):
        """Interpolazione unica su tutti i segmenti: omogeneo."""
        assert is_per_segment_heterogeneous(
            Envelope([[0, 0, 'step'], [0.5, 1, 'step'], [1, 0]])) is False

    def test_mixed_envelope_is_heterogeneous(self):
        """step + linear nello stesso envelope: eterogeneo."""
        assert is_per_segment_heterogeneous(
            Envelope([[0, 0, 'step'], [0.5, 1, 'linear'], [1, 0]])) is True

    def test_single_segment_is_not_heterogeneous(self):
        """Con un solo segmento non c'e' niente da mescolare."""
        assert is_per_segment_heterogeneous(Envelope([[0, 0], [1, 1]])) is False

    def test_object_without_segments_is_not_heterogeneous(self):
        """Un oggetto che non espone segmenti non e' eterogeneo: si disegna in
        blocco, che e' il comportamento di default."""
        assert is_per_segment_heterogeneous(SimpleNamespace()) is False
