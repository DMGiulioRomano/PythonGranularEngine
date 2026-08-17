# tests/rendering/test_grain_visuals.py
"""
TDD suite per rendering.grain_visuals.

Il modulo dice che aspetto ha un grano sulla partitura: la sua forma (i vertici
del poligono) e la sua posizione sulle scale di colore e opacita'. E' la stessa
logica che prima viveva in ScoreVisualizer, ora isolata e matplotlib-free.

Dove passa la linea: il modulo arriva fino al NUMERO — la frazione [0,1] su cui
si interroga la colormap, l'alpha, i vertici — e si ferma. Applicare la
colormap e costruire il Polygon resta dell'adapter, perche' e' li' che comincia
matplotlib.
"""

import gc
from types import SimpleNamespace

import pytest

from pge.rendering.grain_visuals import (
    WINDOW_SILHOUETTE_CACHE_SIZE,
    arrow_vertices,
    window_silhouette,
    window_vertices,
    visible_grains,
    has_pitch_variation,
    pitch_cents_range,
    pitch_position,
    volume_alpha,
    window_name_map,
)


def grain(onset=0.0, duration=1.0, pointer_pos=0.0, pitch_ratio=1.0,
          volume=-6.0, envelope_table=None):
    """Grano minimo: il modulo legge solo questi campi."""
    return SimpleNamespace(
        onset=onset, duration=duration, pointer_pos=pointer_pos,
        pitch_ratio=pitch_ratio, volume=volume,
        envelope_table=envelope_table)


@pytest.fixture
def clean_silhouette_cache():
    """Cache delle silhouette vuota all'entrata e all'uscita.

    La cache e' di modulo, quindi la sua vita e' quella del processo: un test
    che la riempie di proposito la lascerebbe piena per tutti quelli dopo. E'
    l'unico stato globale che questa suite tocca, e la pulizia va in entrambe
    le direzioni perche' i test che la riempiono contano le voci.
    """
    window_silhouette.cache_clear()
    yield
    window_silhouette.cache_clear()


class TestArrowVertices:
    """La forma storica del grano: un rettangolo con la punta triangolare che
    indica il verso di lettura del sample."""

    def test_arrow_points_up_when_forward(self):
        """pitch_ratio positivo: la lettura avanza, la punta guarda in alto.

        Cinque vertici: i due della base sul pointer, i due delle spalle, e la
        punta al centro. Con onset 0, durata 1 e pointer 0, l'altezza e' la
        durata e la punta cade a meta' larghezza.
        """
        verts = arrow_vertices(grain(onset=0.0, duration=1.0, pointer_pos=0.0,
                                     pitch_ratio=1.0))
        assert len(verts) == 5
        assert verts[3] == (0.5, 1.0)   # punta: meta' larghezza, in cima
        assert verts[0] == (0.0, 0.0)   # base sinistra, sul pointer
        assert verts[1] == (1.0, 0.0)   # base destra, sul pointer

    def test_the_head_takes_half_the_length(self):
        """Le spalle stanno a meta' altezza del grano: la testa triangolare ne
        occupa la meta', il fusto l'altra meta'.

        E' la proporzione che rende la freccia leggibile a colpo d'occhio, ed
        e' l'unico numero della forma che non discende da onset/durata: senza
        un test, cambiarlo non farebbe rumore.
        """
        verts = arrow_vertices(grain(onset=0.0, duration=2.0, pointer_pos=0.0,
                                     pitch_ratio=1.0))
        shoulders = [verts[2][1], verts[4][1]]
        assert shoulders == [pytest.approx(1.0), pytest.approx(1.0)]

    def test_the_head_takes_half_the_length_when_reverse(self):
        """Ribaltata, la proporzione e' la stessa: la testa resta meta'."""
        verts = arrow_vertices(grain(onset=0.0, duration=2.0, pointer_pos=0.0,
                                     pitch_ratio=-1.0))
        shoulders = [verts[2][1], verts[4][1]]
        assert shoulders == [pytest.approx(-1.0), pytest.approx(-1.0)]

    def test_arrow_points_down_when_reverse(self):
        """pitch_ratio negativo: la lettura torna indietro, e la freccia si
        ribalta sotto il pointer. Il segno del pitch e' l'unica cosa che
        decide il verso."""
        verts = arrow_vertices(grain(onset=0.0, duration=1.0, pointer_pos=0.0,
                                     pitch_ratio=-1.0))
        assert len(verts) == 5
        assert verts[3] == (0.5, -1.0)  # punta verso il basso
        assert verts[0] == (0.0, 0.0)   # base ancora sul pointer
        assert verts[1] == (1.0, 0.0)

    def test_arrow_sits_on_the_grain_extent(self):
        """La freccia occupa esattamente l'estensione temporale del grano e
        parte dalla posizione di lettura, ovunque siano."""
        verts = arrow_vertices(grain(onset=10.0, duration=2.0,
                                     pointer_pos=0.75, pitch_ratio=1.0))
        xs = [x for x, _ in verts]
        assert min(xs) == 10.0
        assert max(xs) == 12.0
        assert verts[0] == (10.0, 0.75)
        assert verts[3] == (11.0, 2.75)  # punta: meta' larghezza, pointer+durata


class TestWindowSilhouette:
    """La forma di una finestra, normalizzata: serve a disegnare il bordo
    superiore del grano quando grain_shape='window'."""

    def test_normalized_to_unit_peak_and_domain(self):
        """Dominio [0,1] e picco 1: la forma e' pura, la scala per grano la
        applica chi disegna. Cosi' la stessa curva serve grani di qualunque
        durata."""
        xs, w = window_silhouette('hanning', 64)
        assert len(xs) == 64 and len(w) == 64
        assert xs[0] == pytest.approx(0.0)
        assert xs[-1] == pytest.approx(1.0)
        assert w.max() == pytest.approx(1.0)
        assert w.min() >= 0.0

    def test_alias_name_has_a_silhouette(self):
        """La partitura disegna la finestra col nome scritto nello YAML: se
        quello e' un alias (`triangle`), la silhouette deve esistere lo stesso.
        Secondo consumatore del catalogo dopo il renderer numpy."""
        xs_alias, w_alias = window_silhouette('triangle', 64)
        xs_canon, w_canon = window_silhouette('bartlett', 64)
        assert len(w_alias) == 64
        assert list(w_alias) == list(w_canon)

    def test_same_shape_is_computed_once(self):
        """Stesso nome e stessa risoluzione: stessa curva, senza ricalcolarla."""
        a = window_silhouette('hanning', 32)
        b = window_silhouette('hanning', 32)
        assert a[0] is b[0] and a[1] is b[1]

    def test_cached_arrays_are_read_only(self):
        """La cache e' di modulo, quindi condivisa fra visualizer e fra test:
        un chiamante che mutasse la curva la avvelenerebbe per tutti. Gli
        array sono di sola lettura, cosi' il tentativo fallisce subito invece
        di propagarsi."""
        xs, w = window_silhouette('hanning', 32)
        with pytest.raises(ValueError):
            w[0] = 5.0
        with pytest.raises(ValueError):
            xs[0] = 5.0

    def test_different_resolutions_are_different_entries(self):
        """La risoluzione fa parte della chiave: due densita' diverse sono due
        curve diverse."""
        assert len(window_silhouette('hanning', 16)[1]) == 16
        assert len(window_silhouette('hanning', 64)[1]) == 64

    def test_the_cache_has_a_ceiling(self):
        """La cache e' di modulo: la sua vita e' quella del processo, non
        quella del visualizer che l'ha riempita. Senza un tetto, chi rigenera
        le figure variando window_shape_resolution la fa crescere senza che
        niente la liberi mai."""
        info = window_silhouette.cache_info()
        assert info.maxsize == WINDOW_SILHOUETTE_CACHE_SIZE
        assert info.maxsize is not None

    def test_entries_beyond_the_ceiling_are_evicted(self, clean_silhouette_cache):
        """Il tetto e' vero, non decorativo: oltre la capienza le voci vecchie
        escono, e la cache non supera mai la sua dimensione dichiarata."""
        for resolution in range(8, 8 + WINDOW_SILHOUETTE_CACHE_SIZE + 10):
            window_silhouette('hanning', resolution)
        assert (window_silhouette.cache_info().currsize
                == WINDOW_SILHOUETTE_CACHE_SIZE)

    def test_nothing_survives_the_call_beyond_the_cache(
            self, clean_silhouette_cache):
        """Il tetto della lru e' il tetto VERO: dietro non resta un registry
        che accumula gli array senza limite.

        E' il caso che il tetto esiste per chiudere — chi rigenera le figure
        variando window_shape_resolution — e un tetto sul solo strato di sopra
        non lo chiude: la memoria si accumulerebbe un livello piu' giu', dove
        per giunta stanno gli array veri e non le chiavi.
        """
        from pge.rendering.numpy_window_registry import NumpyWindowRegistry

        def retained():
            gc.collect()
            return sum(len(obj._cache) for obj in gc.get_objects()
                       if isinstance(obj, NumpyWindowRegistry))

        # Risoluzioni che nessun altro test tocca: se si sovrapponessero, un
        # registry gia' popolato le troverebbe in cache e il conteggio non
        # crescerebbe — il test passerebbe per l'ordine, non per la regola.
        base = 1000
        before = retained()
        for resolution in range(base, base + WINDOW_SILHOUETTE_CACHE_SIZE + 40):
            window_silhouette('hanning', resolution)
        assert retained() - before <= WINDOW_SILHOUETTE_CACHE_SIZE


class TestWindowVertices:
    """Il grano disegnato come silhouette della sua finestra: base piatta sulla
    posizione di lettura, bordo superiore che ne traccia la curva."""

    def test_vertex_count_is_resolution_plus_two(self):
        """I due vertici della base piu' un punto per campione della curva."""
        xs, w = window_silhouette('hanning', 32)
        verts = window_vertices(grain(duration=1.0), xs, w)
        assert len(verts) == 34

    def test_base_is_flat_on_the_pointer(self):
        """Primo e ultimo vertice sono sulla posizione di lettura, agli
        estremi temporali del grano: la base non segue la curva."""
        xs, w = window_silhouette('hanning', 32)
        verts = window_vertices(
            grain(onset=2.0, duration=1.0, pointer_pos=0.5), xs, w)
        assert verts[0] == (2.0, 0.5)
        assert verts[-1] == (3.0, 0.5)

    def test_edge_rises_above_the_pointer_when_forward(self):
        """Lettura in avanti: il bordo sta sopra il pointer, e il suo massimo
        e' pointer + durata (il picco unitario della finestra scalato)."""
        xs, w = window_silhouette('hanning', 33)
        verts = window_vertices(
            grain(onset=0.0, duration=2.0, pointer_pos=1.0, pitch_ratio=1.0),
            xs, w)
        ys = [y for _, y in verts]
        assert max(ys) == pytest.approx(3.0)
        assert min(ys) == pytest.approx(1.0)

    def test_edge_falls_below_the_pointer_when_reverse(self):
        """Lettura all'indietro: la silhouette si ribalta, come la freccia."""
        xs, w = window_silhouette('hanning', 33)
        verts = window_vertices(
            grain(onset=0.0, duration=2.0, pointer_pos=1.0, pitch_ratio=-1.0),
            xs, w)
        ys = [y for _, y in verts]
        assert min(ys) == pytest.approx(-1.0)
        assert max(ys) == pytest.approx(1.0)


class TestVisibleGrains:
    """Quali grani cadono dentro una finestra temporale. Il predicato era
    scritto quattro volte in ScoreVisualizer (colore pitch, colorbar, lente,
    disegno dei grani): una regola sola, un posto solo."""

    def _stream(self, *grains):
        return SimpleNamespace(voices=[list(grains)])

    def test_grain_inside_the_window_is_visible(self):
        g = grain(onset=5.0, duration=1.0)
        assert visible_grains(self._stream(g), 0.0, 10.0) == [g]

    def test_grain_overlapping_the_edges_is_visible(self):
        """Basta un'intersezione: un grano che entra o esce dalla pagina si
        vede comunque, e va disegnato."""
        entering = grain(onset=-0.5, duration=1.0)
        leaving = grain(onset=9.5, duration=1.0)
        assert visible_grains(self._stream(entering, leaving), 0.0, 10.0) == [
            entering, leaving]

    def test_grain_touching_the_edges_is_not_visible(self):
        """I confini sono stretti da entrambi i lati: un grano che finisce
        esattamente all'inizio della finestra, o che comincia esattamente alla
        fine, non ha estensione dentro e non si disegna."""
        ends_at_start = grain(onset=-1.0, duration=1.0)   # finisce a 0.0
        starts_at_end = grain(onset=10.0, duration=1.0)   # comincia a 10.0
        assert visible_grains(
            self._stream(ends_at_start, starts_at_end), 0.0, 10.0) == []

    def test_all_voices_are_considered(self):
        """I grani stanno per voce: la finestra li guarda tutti, in ordine di
        voce."""
        a, b = grain(onset=1.0), grain(onset=2.0)
        stream = SimpleNamespace(voices=[[a], [b]])
        assert visible_grains(stream, 0.0, 10.0) == [a, b]


class TestPitchCentsRange:
    """Autozoom del colore: invece di spendere l'intera colormap sul range
    fisso, la si concentra sui pitch che in questa pagina ci sono davvero."""

    def _stream(self, *ratios):
        return SimpleNamespace(
            voices=[[grain(onset=1.0, pitch_ratio=r) for r in ratios]])

    def test_range_is_centred_on_the_pitches_present(self):
        """Due grani a un'ottava di distanza: 1200 cent di escursione, centro a
        meta'. Senza pad e con uno span sopra il minimo, il range e' proprio
        l'escursione."""
        lo, hi = pitch_cents_range(
            [self._stream(1.0, 2.0)], 0.0, 10.0,
            min_span_cents=0.0, pad_ratio=0.0)
        assert (lo, hi) == pytest.approx((0.0, 1200.0))

    def test_narrow_spread_is_widened_to_the_minimum_span(self):
        """Grani quasi identici: senza un minimo la colormap esploderebbe su
        una differenza inudibile, dipingendo di rosso e blu due pitch uguali."""
        lo, hi = pitch_cents_range(
            [self._stream(1.0, 1.001)], 0.0, 10.0,
            min_span_cents=200.0, pad_ratio=0.0)
        assert (hi - lo) == pytest.approx(200.0)

    def test_no_grains_means_no_range(self):
        """Pagina senza grani visibili: nessun range da calcolare, il
        chiamante ripiega su quello fisso."""
        assert pitch_cents_range(
            [self._stream()], 0.0, 10.0,
            min_span_cents=200.0, pad_ratio=0.0) is None

    def test_only_visible_grains_count(self):
        """Un grano fuori pagina non influenza il colore di quelli dentro."""
        stream = SimpleNamespace(voices=[[
            grain(onset=1.0, duration=1.0, pitch_ratio=1.0),
            grain(onset=50.0, duration=1.0, pitch_ratio=4.0),
        ]])
        lo, hi = pitch_cents_range(
            [stream], 0.0, 10.0, min_span_cents=0.0, pad_ratio=0.0)
        assert (lo, hi) == pytest.approx((0.0, 0.0))

    def test_reverse_grains_count_by_their_absolute_pitch(self):
        """Un grano reverse ha ratio negativo ma la sua ALTEZZA e' quella del
        forward corrispondente, ed e' l'altezza che il colore racconta: -2.0
        pesa come 2.0. Il verso lo dice gia' la forma della freccia."""
        forward = pitch_cents_range(
            [self._stream(1.0, 2.0)], 0.0, 10.0,
            min_span_cents=0.0, pad_ratio=0.0)
        reverse = pitch_cents_range(
            [self._stream(1.0, -2.0)], 0.0, 10.0,
            min_span_cents=0.0, pad_ratio=0.0)
        assert reverse == pytest.approx(forward)

    def test_zero_ratio_has_no_pitch(self):
        """Il pitch in cent e' un logaritmo: ratio zero non ne ha uno."""
        assert pitch_cents_range(
            [self._stream(0.0)], 0.0, 10.0,
            min_span_cents=0.0, pad_ratio=0.0) is None


class TestHasPitchVariation:
    """Se le altezze dei grani variano davvero (issue #217).

    E' la domanda che il range zoomato non puo' rispondere: `pitch_cents_range`
    applica comunque il floor di mezzo semitono, quindi da' un'escursione anche
    dove non ce n'e'. Chi disegna la scala di colore ha bisogno del dato grezzo,
    non del range gia' allargato."""

    def _stream(self, *ratios):
        return SimpleNamespace(
            voices=[[grain(onset=1.0, pitch_ratio=r) for r in ratios]])

    def test_identical_pitches_do_not_vary(self):
        assert not has_pitch_variation([self._stream(1.5, 1.5, 1.5)], 0.0, 10.0)

    def test_float_drift_does_not_count_as_variation(self):
        """La stessa ottava raggiunta per due strade diverse — dodici semitoni
        moltiplicati uno alla volta contro il rapporto 2.0 — differisce
        all'ultimo bit. E' rumore aritmetico, non una variazione d'altezza:
        con l'uguaglianza esatta la colorbar ricomparirebbe."""
        drifted = 1.0
        for _ in range(12):
            drifted *= 2.0 ** (1.0 / 12.0)
        assert drifted != 2.0                       # la deriva c'e' davvero
        assert not has_pitch_variation([self._stream(2.0, drifted)], 0.0, 10.0)

    def test_sub_cent_difference_does_not_vary(self):
        """Mezzo cent e' sotto la soglia percettiva: la scala di colore
        prometterebbe un'escursione che nessuno sente."""
        stream = self._stream(1.0, 2.0 ** (0.5 / 1200.0))
        assert not has_pitch_variation([stream], 0.0, 10.0)

    def test_audible_difference_varies(self):
        """Cinque cent si sentono: la scala di colore ha qualcosa da dire."""
        stream = self._stream(1.0, 2.0 ** (5.0 / 1200.0))
        assert has_pitch_variation([stream], 0.0, 10.0)

    def test_a_single_grain_does_not_vary(self):
        """Un grano solo non e' un'escursione: non c'e' niente da cui differire,
        e una scala di colore su un unico valore direbbe meno di niente."""
        assert not has_pitch_variation([self._stream(1.5)], 0.0, 10.0)

    def test_no_pitched_grains_do_not_vary(self):
        """Nessun grano (o solo ratio zero, che un'altezza non ce l'ha):
        niente da misurare, quindi niente variazione."""
        assert not has_pitch_variation([self._stream()], 0.0, 10.0)
        assert not has_pitch_variation([self._stream(0.0)], 0.0, 10.0)

    def test_only_visible_grains_count(self):
        """Un grano fuori pagina non fa comparire una variazione dentro."""
        stream = SimpleNamespace(voices=[[
            grain(onset=1.0, duration=1.0, pitch_ratio=1.0),
            grain(onset=50.0, duration=1.0, pitch_ratio=4.0),
        ]])
        assert not has_pitch_variation([stream], 0.0, 10.0)

    def test_reverse_grains_count_by_their_absolute_pitch(self):
        """Il colore racconta l'altezza, non il verso: 1.0 e -1.0 sono lo
        stesso pitch, quindi nessuna variazione."""
        assert not has_pitch_variation([self._stream(1.0, -1.0)], 0.0, 10.0)

    def test_variation_can_come_from_two_streams_together(self):
        """La domanda si puo' porre su piu' stream insieme: due stream uniformi
        ma di altezza diversa, guardati insieme, variano."""
        streams = [self._stream(1.0), self._stream(2.0)]
        assert has_pitch_variation(streams, 0.0, 10.0)
        assert not has_pitch_variation([streams[0]], 0.0, 10.0)


class TestPitchPosition:
    """Dove cade un pitch sulla colormap, come frazione [0,1]. Il modulo si
    ferma qui: applicare la colormap alla frazione e' dell'adapter."""

    def test_uses_the_zoomed_range_when_present(self):
        """Con l'autozoom attivo la frazione si misura in cent sul range
        zoomato: un'ottava sopra lo zero, su un range 0-1200, e' il fondo."""
        assert pitch_position(2.0, (0.0, 1200.0),
                              pitch_range=(0.5, 2.0)) == pytest.approx(1.0)
        assert pitch_position(1.0, (0.0, 1200.0),
                              pitch_range=(0.5, 2.0)) == pytest.approx(0.0)

    def test_falls_back_to_the_fixed_range_in_ratio(self):
        """Senza autozoom la frazione si misura sul range fisso, e in ratio —
        non in cent. Su 0.5-2.0, il ratio 1.25 e' a un terzo."""
        assert pitch_position(1.25, None,
                              pitch_range=(0.5, 2.0)) == pytest.approx(0.5)

    def test_is_clamped_to_the_colormap(self):
        """Fuori dal range non c'e' colore da scegliere: si resta agli estremi
        della colormap invece di indicizzarla fuori."""
        assert pitch_position(100.0, (0.0, 1200.0), pitch_range=(0.5, 2.0)) == 1.0
        assert pitch_position(0.001, (0.0, 1200.0), pitch_range=(0.5, 2.0)) == 0.0

    def test_non_positive_ratio_uses_the_fixed_range(self):
        """Ratio non positivo non ha un valore in cent: anche con l'autozoom
        attivo si ricade sul range fisso, invece di prendere il logaritmo di
        zero.

        Il range fisso e' scelto simmetrico apposta: su 0.5-2.0 il ramo giusto
        e quello sbagliato darebbero entrambi 0.0 dopo il clamp — uno perche'
        misura sotto il minimo, l'altro perche' log2(0) e' -inf — e il test
        passerebbe qualunque cosa faccia il codice. Su -2.0..2.0 lo zero cade
        a meta', e i due rami si distinguono.
        """
        assert pitch_position(
            0.0, (0.0, 1200.0), pitch_range=(-2.0, 2.0)) == pytest.approx(0.5)

    def test_zero_ratio_does_not_take_a_logarithm(self, recwarn):
        """Il ramo in cent non viene nemmeno sfiorato: niente log2(0), quindi
        nessun -inf e nessun RuntimeWarning di divisione invalida."""
        pitch_position(0.0, (0.0, 1200.0), pitch_range=(-2.0, 2.0))
        assert [w for w in recwarn if issubclass(w.category, RuntimeWarning)] == []


class TestVolumeAlpha:
    """L'opacita' del grano segue il suo volume: i grani piano si vedono meno."""

    def test_loudest_is_most_opaque(self):
        assert volume_alpha(0.0, volume_range=(-60, 0),
                            alpha_range=(0.3, 1.0)) == pytest.approx(1.0)

    def test_quietest_is_most_transparent(self):
        """Il minimo non e' zero: un grano piano resta visibile, altrimenti
        sparirebbe dalla partitura invece di attenuarsi."""
        assert volume_alpha(-60.0, volume_range=(-60, 0),
                            alpha_range=(0.3, 1.0)) == pytest.approx(0.3)

    def test_below_the_range_stays_at_the_floor(self):
        """Sotto la soglia si resta sul minimo: l'alpha non puo' uscire
        dall'intervallo utile."""
        assert volume_alpha(-200.0, volume_range=(-60, 0),
                            alpha_range=(0.3, 1.0)) == pytest.approx(0.3)


class TestWindowNameMap:
    """Il grano porta il numero di tabella della sua finestra; per disegnarne
    la silhouette serve il nome. Lo stream ha la mappa nel verso opposto."""

    def test_map_is_inverted(self):
        stream = SimpleNamespace(window_table_map={'hanning': 1, 'gaussian': 2})
        assert window_name_map(stream) == {1: 'hanning', 2: 'gaussian'}

    def test_missing_map_is_empty(self):
        """Senza mappa non ci sono nomi da risolvere: chi disegna ripiega
        interamente sulla freccia."""
        assert window_name_map(SimpleNamespace()) == {}
        assert window_name_map(SimpleNamespace(window_table_map=None)) == {}
