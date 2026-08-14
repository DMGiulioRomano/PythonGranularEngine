# tests/rendering/test_page_layout.py
"""
TDD suite per rendering.page_layout.

Come si dispone una partitura sulla pagina: quali stream cadono su quale
pagina, quanti se ne sovrappongono, in che corsia verticale va ciascuno, e
dove stanno le corsie degli envelope con la loro legenda.

E' la stessa logica che prima viveva in ScoreVisualizer.analyze e nei suoi
helper. Il metodo analyze resta nel visualizer perche' scrive lo stato
dell'oggetto e stampa: qui vive solo la regola.
"""

from types import SimpleNamespace

import pytest

from pge.rendering.page_layout import (
    active_streams,
    max_concurrent,
    assign_slots,
    paginate,
    total_duration,
    envelope_lanes,
    legend_display_name,
)


def stream(stream_id='s1', onset=0.0, duration=10.0):
    """Stream minimo: il layout ne legge solo identita' ed estensione."""
    return SimpleNamespace(stream_id=stream_id, onset=onset, duration=duration)


class TestActiveStreams:
    """Quali stream hanno estensione dentro una finestra di pagina."""

    def test_stream_inside_the_window_is_active(self):
        s = stream(onset=2.0, duration=5.0)
        assert active_streams([s], 0.0, 30.0) == [s]

    def test_stream_straddling_the_boundary_is_active(self):
        """Uno stream a cavallo appartiene a entrambe le pagine: va disegnato
        su tutte e due, tagliato dalla finestra."""
        s = stream(onset=25.0, duration=12.0)
        assert active_streams([s], 0.0, 30.0) == [s]
        assert active_streams([s], 30.0, 60.0) == [s]

    def test_stream_ending_on_the_boundary_belongs_to_the_page_before(self):
        """Uno stream che finisce esattamente sul confine non ha estensione
        nella pagina successiva: appartiene solo a quella prima, altrimenti
        comparirebbe come una riga vuota."""
        s = stream(onset=20.0, duration=10.0)   # 20-30
        assert active_streams([s], 0.0, 30.0) == [s]
        assert active_streams([s], 30.0, 60.0) == []


class TestMaxConcurrent:
    """Quanti stream suonano insieme nel momento piu' affollato della pagina:
    e' l'altezza minima che la pagina deve riservare."""

    def test_disjoint_streams_never_overlap(self):
        a, b = stream('a', 0.0, 5.0), stream('b', 6.0, 5.0)
        assert max_concurrent([a, b], 0.0, 30.0) == 1

    def test_counts_the_busiest_instant(self):
        """Tre stream che si accavallano a due a due, ma tutti e tre insieme
        solo fra 8 e 10: il massimo e' 3."""
        a = stream('a', 0.0, 10.0)
        b = stream('b', 5.0, 10.0)
        c = stream('c', 8.0, 15.0)
        assert max_concurrent([a, b, c], 0.0, 30.0) == 3

    def test_touching_streams_are_not_concurrent(self):
        """Uno stream che finisce nell'istante in cui un altro comincia non e'
        simultaneo: la fine si conta prima dell'inizio, o la pagina
        riserverebbe una corsia in piu' che resta vuota."""
        a, b = stream('a', 0.0, 10.0), stream('b', 10.0, 5.0)
        assert max_concurrent([a, b], 0.0, 30.0) == 1

    def test_only_the_part_inside_the_page_counts(self):
        """Gli stream si contano tagliati sulla finestra: due che si
        sovrappongono fuori pagina non affollano questa."""
        a = stream('a', 0.0, 40.0)     # attraversa tutta la pagina
        b = stream('b', 35.0, 10.0)    # si sovrappone ad 'a' solo dopo il 35
        assert max_concurrent([a, b], 0.0, 30.0) == 1


class TestAssignSlots:
    """In che corsia verticale va ciascuno stream. Stream che non si
    sovrappongono possono condividere una corsia: la pagina resta compatta."""

    def test_overlapping_streams_get_different_slots(self):
        a, b = stream('a', 0.0, 10.0), stream('b', 5.0, 10.0)
        assert assign_slots([a, b]) == {'a': 0, 'b': 1}

    def test_disjoint_streams_share_a_slot(self):
        """Il secondo comincia dopo che il primo e' finito: stessa corsia."""
        a, b = stream('a', 0.0, 10.0), stream('b', 12.0, 5.0)
        assert assign_slots([a, b]) == {'a': 0, 'b': 0}

    def test_touching_streams_share_a_slot(self):
        """Contatto esatto: il secondo comincia nell'istante in cui il primo
        finisce, e la corsia si riusa. Con un confronto stretto si sprecherebbe
        una corsia per ogni catena di stream consecutivi."""
        a, b = stream('a', 0.0, 10.0), stream('b', 10.0, 5.0)
        assert assign_slots([a, b]) == {'a': 0, 'b': 0}

    def test_first_free_slot_wins(self):
        """Fra piu' corsie libere si prende la prima: la pagina si riempie dal
        basso invece di sparpagliarsi."""
        a = stream('a', 0.0, 10.0)
        b = stream('b', 1.0, 2.0)      # slot 1
        c = stream('c', 5.0, 2.0)      # slot 1 di nuovo (b e' finito)
        assert assign_slots([a, b, c]) == {'a': 0, 'b': 1, 'c': 1}

    def test_streams_are_ordered_by_onset(self):
        """L'ordine in ingresso non conta: si assegna per onset crescente,
        altrimenti la stessa pagina darebbe corsie diverse a seconda
        dell'ordine degli stream nel file."""
        a, b = stream('a', 0.0, 10.0), stream('b', 5.0, 10.0)
        assert assign_slots([b, a]) == assign_slots([a, b])

    def test_no_streams_no_slots(self):
        assert assign_slots([]) == {}


class TestPaginate:
    """La partitura divisa in pagine di durata fissa."""

    def test_duration_spans_all_streams(self):
        """La durata totale arriva fino alla fine dell'ultimo stream, non
        dell'ultimo dichiarato."""
        early = stream('early', 0.0, 10.0)
        late = stream('late', 50.0, 5.0)
        assert total_duration([late, early]) == pytest.approx(55.0)

    def test_partial_page_still_counts(self):
        """75 secondi in pagine da 30: tre pagine, l'ultima parziale. Con una
        divisione intera l'ultimo pezzo di partitura sparirebbe."""
        pages = paginate([stream('s', 0.0, 75.0)], page_duration=30.0)
        assert len(pages) == 3
        assert pages[-1].t_start == pytest.approx(60.0)
        assert pages[-1].t_end == pytest.approx(90.0)

    def test_page_windows_are_contiguous(self):
        pages = paginate([stream('s', 0.0, 75.0)], page_duration=30.0)
        assert [(p.index, p.t_start, p.t_end) for p in pages] == [
            (0, 0.0, 30.0), (1, 30.0, 60.0), (2, 60.0, 90.0)]

    def test_empty_page_in_a_gap(self):
        """Un buco fra due stream produce una pagina senza niente: resta nella
        sequenza, altrimenti la numerazione non corrisponderebbe piu' al tempo."""
        pages = paginate(
            [stream('a', 0.0, 10.0), stream('b', 95.0, 5.0)],
            page_duration=30.0)
        assert len(pages) == 4
        assert pages[2].streams == ()
        assert pages[2].max_concurrent == 0
        assert pages[2].slots == {}

    def test_page_carries_its_streams_and_layout(self):
        a, b = stream('a', 0.0, 10.0), stream('b', 5.0, 10.0)
        page = paginate([a, b], page_duration=30.0)[0]
        assert page.streams == (a, b)
        assert page.max_concurrent == 2
        assert page.slots == {'a': 0, 'b': 1}

    def test_lanes_never_exceed_the_reserved_height(self):
        """L'altezza riservata dalla pagina basta sempre alle corsie che le
        servono. E' la sola cosa che il disegno chiede: se una corsia cadesse
        fuori, due stream finirebbero sovrapposti.

        Il conto tiene su una batteria di forme diverse — stream a cavallo dei
        confini, catene che si toccano, grumi, pagine parziali — perche' le
        corsie si assegnano sull'estensione intera e i simultanei si contano
        tagliati sulla finestra: sono due misure diverse, e l'invariante lega
        proprio loro due.
        """
        shapes = [
            [('a', 0.0, 10.0), ('b', 5.0, 10.0)],
            [('a', 25.0, 10.0), ('b', 28.0, 10.0)],            # a cavallo
            [('a', 0.0, 10.0), ('b', 10.0, 10.0), ('c', 20.0, 10.0)],  # catena
            [('a', 0.0, 40.0), ('b', 29.0, 3.0), ('c', 31.0, 3.0)],
            [('a', 0.0, 5.0), ('b', 0.0, 5.0), ('c', 0.0, 5.0)],       # grumo
            [('a', 55.0, 20.0), ('b', 58.0, 2.0), ('c', 59.0, 30.0)],
        ]
        for shape in shapes:
            pages = paginate([stream(*s) for s in shape], page_duration=30.0)
            for page in pages:
                assert page.max_concurrent >= len(set(page.slots.values())), shape

    def test_the_page_is_a_frozen_record(self):
        """La pagina e' un record: chi la riceve la legge, non la ritocca.

        `frozen` da solo blocca il riassegnamento del campo e non la scrittura
        dentro il campo, quindi la sequenza degli stream e' una tuple: senza,
        il record prometterebbe un'immutabilita' che non ha.
        """
        page = paginate([stream('a', 0.0, 10.0)], page_duration=30.0)[0]
        assert isinstance(page.streams, tuple)
        with pytest.raises(Exception):
            page.streams = ()
        with pytest.raises(AttributeError):
            page.streams.append(stream('b'))

    def test_no_streams_is_an_error(self):
        """Impaginare il nulla non ha senso: meglio dirlo che produrre zero
        pagine e far fallire il disegno piu' avanti."""
        with pytest.raises(ValueError):
            paginate([], page_duration=30.0)


class TestEnvelopeLanes:
    """Le corsie in cui si disegnano gli envelope, e le voci di legenda
    allineate alle curve. Lane e legenda vengono dalla stessa funzione: se le
    calcolasse ognuno per conto suo, la legenda apparirebbe specchiata rispetto
    alle curve."""

    def test_stream_without_envelopes_has_no_lane(self):
        """Uno stream tutto statico non ha niente da disegnare: l'asse resta,
        ma vuoto."""
        lanes, entries = envelope_lanes([(stream('s'), {})])
        assert lanes == [] and entries == []

    def test_single_stream_fills_the_axis_minus_the_gaps(self):
        lanes, _ = envelope_lanes([(stream('s'), {'density': object()})])
        assert len(lanes) == 1
        assert lanes[0].y_base == pytest.approx(0.02)
        assert lanes[0].y_height == pytest.approx(0.96)

    def test_streams_stack_upwards(self):
        """Piu' stream si impilano dal basso, ognuno con la sua fetta."""
        lanes, _ = envelope_lanes([
            (stream('a'), {'density': object()}),
            (stream('b'), {'volume': object()}),
        ])
        assert [lane.stream_id for lane in lanes] == ['a', 'b']
        assert lanes[0].y_base < lanes[1].y_base
        assert lanes[0].y_height == pytest.approx(lanes[1].y_height)

    def test_per_voice_curves_collapse_to_one_legend_entry(self):
        """N tracce '__vN' dello stesso parametro, una sola etichetta: la
        colonna della legenda e' stretta, e ripetere lo stesso nome tre volte
        non aggiunge niente."""
        envelopes = {f'voice_pitch_offset__v{i}': object() for i in (1, 2, 3)}
        lanes, entries = envelope_lanes([(stream('s'), envelopes)])
        assert lanes[0].env_types == ('voice_pitch_offset',)
        assert [name for name, _, _ in entries] == ['voice_pitch_offset']

    def test_single_entry_sits_in_the_middle(self):
        lanes, entries = envelope_lanes([(stream('s'), {'density': object()})])
        _, y, _ = entries[0]
        assert y == pytest.approx(lanes[0].y_base + lanes[0].y_height * 0.5)

    def test_entries_are_spread_from_top_to_bottom(self):
        """Piu' parametri: le voci si distribuiscono dall'alto verso il basso
        della corsia, fra l'85% e il 15% della sua altezza. Non 100% e 0%, o la
        prima e l'ultima toccherebbero il bordo."""
        envelopes = {'density': object(), 'volume': object(), 'pan': object()}
        lanes, entries = envelope_lanes([(stream('s'), envelopes)])
        lane = lanes[0]
        ys = [y for _, y, _ in entries]
        assert ys == sorted(ys, reverse=True)
        assert ys[0] == pytest.approx(lane.y_base + lane.y_height * 0.85)
        assert ys[-1] == pytest.approx(lane.y_base + lane.y_height * 0.15)

    def test_entries_know_their_stream(self):
        _, entries = envelope_lanes([
            (stream('a'), {'density': object()}),
            (stream('b'), {'volume': object()}),
        ])
        assert {sid for _, _, sid in entries} == {'a', 'b'}

    def test_parameter_names_are_sorted(self):
        """Ordine stabile: la stessa pagina disegnata due volte da' la stessa
        legenda."""
        envelopes = {'volume': object(), 'density': object()}
        lanes, _ = envelope_lanes([(stream('s'), envelopes)])
        assert lanes[0].env_types == ('density', 'volume')


class TestLegendDisplayName:
    """Il nome mostrato in legenda. La colonna e' larga circa il 6% della
    pagina: i nomi lunghi sforavano nel plot."""

    def test_long_names_have_an_explicit_short_form(self):
        assert legend_display_name('pointer_deviation') == 'ptr dev'
        assert legend_display_name('grain_duration') == 'grain dur'

    def test_other_names_just_lose_the_underscores(self):
        assert legend_display_name('density') == 'density'
        assert legend_display_name('fake_param') == 'fake param'

    def test_probability_suffix_becomes_a_percent(self):
        assert legend_display_name('volume_prob') == 'volume %'

    def test_range_suffix_becomes_rng(self):
        assert legend_display_name('volume_range') == 'volume rng'

    def test_suffix_is_applied_on_top_of_the_short_form(self):
        """Il suffisso si applica al nome gia' accorciato, non a quello lungo:
        'pointer_deviation_prob' diventa 'ptr dev %', non
        'pointer deviation %' che sforerebbe."""
        assert legend_display_name('pointer_deviation_prob') == 'ptr dev %'

    def test_explicit_override_wins_over_the_suffix_rule(self):
        """'grain_duration_range' avrebbe 'grain dur rng' (13 caratteri), che
        sfora: un override esplicito ha la precedenza sulla regola."""
        assert legend_display_name('grain_duration_range') == 'gr dur rng'

    def test_read_direction_abbreviated(self):
        """'read direction' (14) sfora la colonna; l'override vale anche per
        la curva di probabilita', che eredita il nome accorciato."""
        assert legend_display_name('read_direction') == 'read dir'
        assert legend_display_name('read_direction_prob') == 'read dir %'
