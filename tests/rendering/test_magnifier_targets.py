# tests/rendering/test_magnifier_targets.py
"""
TDD suite per rendering.magnifier_targets.

La lente ingrandisce una regione del piano tempo x posizione-di-lettura. Questo
modulo decide DOVE puntarla: il cluster piu' denso quando e' automatica, e i
punti chiesti dall'utente quando e' esplicita, risolti su uno stream e una
quota concreti. Proiettare il cerchio e disegnare i connettori resta di
ScoreVisualizer, perche' e' li' che comincia matplotlib.

Questa logica non aveva test unitari: era coperta solo di rimbalzo dalla rete
di caratterizzazione.
"""

from types import SimpleNamespace

import pytest

from pge.rendering.magnifier_targets import (
    densest_entry,
    auto_y_at,
    explicit_target,
    auto_target,
    resolve,
)


DEFAULTS = {'zoom': 8.0, 'out': 0.12, 'src': None, 'corner': 'top-right'}


def grain(onset=0.0, duration=0.1, pointer_pos=0.0):
    return SimpleNamespace(onset=onset, duration=duration,
                           pointer_pos=pointer_pos)


def entry(stream_id='s1', sample_duration=3.0, grains=()):
    """Una riga di stream_entries: il modulo ne legge solo `stream` e
    `sample_duration`. Il resto (l'asse matplotlib) gli e' opaco e viaggia
    intatto fino a chi disegna."""
    stream = SimpleNamespace(stream_id=stream_id, voices=[list(grains)])
    return {'stream': stream, 'sample_duration': sample_duration,
            'ax': '<opaco>'}


class TestDensestEntry:
    """Quale stream ha piu' grani in pagina: e' su quello che si punta la lente
    quando l'utente non dice su quale."""

    def test_picks_the_stream_with_most_visible_grains(self):
        sparse = entry('sparse', grains=[grain(onset=1.0)])
        dense = entry('dense', grains=[grain(onset=t) for t in (1.0, 2.0, 3.0)])
        assert densest_entry([sparse, dense], 0.0, 10.0) is dense

    def test_falls_back_to_the_first_when_nobody_has_grains(self):
        """Nessuno stream con grani in pagina: puntare la lente sul primo e'
        comunque meglio che non puntarla."""
        first, second = entry('a'), entry('b')
        assert densest_entry([first, second], 0.0, 10.0) is first

    def test_no_entries_means_no_target(self):
        assert densest_entry([], 0.0, 10.0) is None

    def test_only_grains_in_the_window_count(self):
        """Uno stream fitto ma fuori pagina non vince su uno rado ma dentro."""
        outside = entry('outside', grains=[grain(onset=t) for t in (50, 51, 52)])
        inside = entry('inside', grains=[grain(onset=1.0)])
        assert densest_entry([outside, inside], 0.0, 10.0) is inside


class TestAutoY:
    """Quando l'utente dice QUANDO ma non A CHE QUOTA, la si deduce dai grani
    vicini a quell'istante."""

    def test_uses_grains_near_the_instant(self):
        """Media dei pointer_pos nella finestra locale attorno a t (+/-5%
        della pagina). Con pagina 0-100 la finestra e' +/-5."""
        stream = SimpleNamespace(voices=[[
            grain(onset=48.0, pointer_pos=1.0),
            grain(onset=52.0, pointer_pos=2.0),
            # Fuori dalla finestra locale ma non lontanissimo: e' il grano che
            # distingue un raggio del 5% da uno piu' largo.
            grain(onset=65.0, pointer_pos=10.0),
        ]])
        assert auto_y_at(stream, 50.0, 0.0, 100.0) == pytest.approx(1.5)

    def test_falls_back_to_all_grains_when_none_are_near(self):
        """Nessun grano vicino a t: si usa la media di tutti quelli in pagina,
        invece di rinunciare. Una quota approssimata e' meglio di nessuna."""
        stream = SimpleNamespace(voices=[[
            grain(onset=10.0, pointer_pos=1.0),
            grain(onset=90.0, pointer_pos=3.0),
        ]])
        assert auto_y_at(stream, 50.0, 0.0, 100.0) == pytest.approx(2.0)

    def test_no_grains_means_no_quota(self):
        """Senza grani non c'e' niente da cui dedurre la quota: decide il
        chiamante."""
        assert auto_y_at(SimpleNamespace(voices=[[]]), 50.0, 0.0, 100.0) is None


class TestExplicitTarget:
    """Un punto chiesto dall'utente, risolto su uno stream e una quota
    concreti. La specifica ha un solo campo obbligatorio: l'istante."""

    def test_resolves_stream_and_quota_from_the_instant_alone(self):
        """Solo `t`: lo stream e' il piu' denso della pagina, la quota si
        deduce dai grani vicini, il resto viene dai default."""
        only = entry('s1', grains=[grain(onset=5.0, pointer_pos=1.5)])
        target = explicit_target({'t': 5.0}, [only], 0.0, 10.0,
                                 defaults=DEFAULTS)
        assert target.entry is only
        assert target.t == pytest.approx(5.0)
        assert target.y == pytest.approx(1.5)
        assert target.zoom == pytest.approx(8.0)
        assert target.corner == 'top-right'

    def test_instant_outside_the_window_is_dropped(self):
        """Un target che cade in un'altra pagina non si disegna qui."""
        only = entry('s1', grains=[grain(onset=5.0)])
        assert explicit_target({'t': 50.0}, [only], 0.0, 10.0,
                               defaults=DEFAULTS) is None
        assert explicit_target({}, [only], 0.0, 10.0,
                               defaults=DEFAULTS) is None

    def test_window_end_is_exclusive(self):
        """I confini seguono la stessa regola della pagina: l'inizio dentro,
        la fine fuori, cosi' un target sul confine non finisce su due pagine."""
        only = entry('s1', grains=[grain(onset=5.0)])
        assert explicit_target({'t': 0.0}, [only], 0.0, 10.0,
                               defaults=DEFAULTS) is not None
        assert explicit_target({'t': 10.0}, [only], 0.0, 10.0,
                               defaults=DEFAULTS) is None

    def test_named_stream_wins_over_the_densest(self):
        """La chiave `stream` sceglie per stream_id, anche se quello stream ha
        meno grani."""
        dense = entry('dense', grains=[grain(onset=t) for t in (1.0, 2.0, 3.0)])
        wanted = entry('wanted', grains=[grain(onset=1.0)])
        target = explicit_target({'t': 5.0, 'stream': 'wanted'},
                                 [dense, wanted], 0.0, 10.0, defaults=DEFAULTS)
        assert target.entry is wanted

    def test_unknown_stream_falls_back_to_the_densest(self):
        """Un nome che non esiste non fa sparire la lente: si ripiega sullo
        stream piu' denso."""
        dense = entry('dense', grains=[grain(onset=t) for t in (1.0, 2.0)])
        target = explicit_target({'t': 5.0, 'stream': 'inesistente'},
                                 [dense], 0.0, 10.0, defaults=DEFAULTS)
        assert target.entry is dense

    def test_quota_falls_back_to_the_middle_of_the_sample(self):
        """Senza grani da cui dedurre la quota, si punta a meta' sample."""
        empty = entry('s1', sample_duration=4.0)
        target = explicit_target({'t': 5.0}, [empty], 0.0, 10.0,
                                 defaults=DEFAULTS)
        assert target.y == pytest.approx(2.0)

    def test_explicit_keys_override_the_defaults(self):
        only = entry('s1', grains=[grain(onset=5.0)])
        target = explicit_target(
            {'t': 5.0, 'y': 9.0, 'zoom': 2.0, 'out': 0.3, 'src': 0.05,
             'corner': 'bottom-left'},
            [only], 0.0, 10.0, defaults=DEFAULTS)
        assert (target.y, target.zoom, target.out, target.src,
                target.corner) == (9.0, 2.0, 0.3, 0.05, 'bottom-left')

    def test_no_entries_means_no_target(self):
        assert explicit_target({'t': 5.0}, [], 0.0, 10.0,
                               defaults=DEFAULTS) is None


class TestAutoTarget:
    """La lente automatica cerca il grumo: il bin piu' popolato dell'istogramma
    tempo x posizione, fra tutti gli stream attivi."""

    def test_centres_on_the_densest_cluster(self):
        """Cinque grani stretti attorno a (2, 1) piu' uno isolato: la lente va
        sul grumo, non a meta' strada."""
        cluster = [grain(onset=2.0 + i * 0.01, pointer_pos=1.0 + i * 0.01)
                   for i in range(5)]
        stray = [grain(onset=90.0, pointer_pos=2.5)]
        only = entry('s1', grains=cluster + stray)
        target = auto_target([only], 0.0, 100.0,
                             hist_bins=(40, 16), defaults=DEFAULTS)
        assert target.t == pytest.approx(2.02, abs=0.1)
        assert target.y == pytest.approx(1.02, abs=0.1)

    def test_centre_lands_on_real_grains(self):
        """Il centro e' il centroide dei grani del bin, non il centro
        geometrico del bin: cosi' la finestra — stretta per via dello zoom —
        contiene davvero qualcosa."""
        grains = [grain(onset=t, pointer_pos=1.0) for t in (0.1, 0.15, 0.2)]
        only = entry('s1', grains=grains)
        target = auto_target([only], 0.0, 100.0,
                             hist_bins=(4, 4), defaults=DEFAULTS)
        assert target.t == pytest.approx(0.15)

    def test_picks_the_densest_across_streams(self):
        sparse = entry('sparse', grains=[grain(onset=1.0, pointer_pos=0.5)])
        dense = entry('dense', grains=[
            grain(onset=8.0 + i * 0.01, pointer_pos=2.0) for i in range(6)])
        target = auto_target([sparse, dense], 0.0, 10.0,
                             hist_bins=(40, 16), defaults=DEFAULTS)
        assert target.entry is dense

    def test_no_grains_means_no_target(self):
        assert auto_target([entry('s1')], 0.0, 10.0,
                           hist_bins=(40, 16), defaults=DEFAULTS) is None

    def test_uses_the_defaults(self):
        only = entry('s1', grains=[grain(onset=2.0, pointer_pos=1.0)])
        target = auto_target([only], 0.0, 10.0,
                             hist_bins=(40, 16), defaults=DEFAULTS)
        assert (target.zoom, target.out, target.src, target.corner) == (
            8.0, 0.12, None, 'top-right')


class TestResolve:
    """L'insieme delle lenti di una pagina: l'automatica, se accesa, piu' le
    esplicite che ci cadono dentro."""

    def test_auto_comes_before_the_explicit_ones(self):
        """L'ordine e' contratto: chi disegna proietta in questa sequenza, e
        con piu' lenti sullo stesso angolo l'ordine decide le sovrapposizioni."""
        only = entry('s1', grains=[grain(onset=2.0, pointer_pos=1.0)])
        targets = resolve(
            [only], 0.0, 10.0, auto=True,
            specs=[{'t': 5.0, 'zoom': 2.0}, {'t': 6.0, 'zoom': 3.0}],
            hist_bins=(40, 16), defaults=DEFAULTS)
        assert [t.zoom for t in targets] == [8.0, 2.0, 3.0]

    def test_auto_off_leaves_only_the_explicit_ones(self):
        only = entry('s1', grains=[grain(onset=2.0, pointer_pos=1.0)])
        targets = resolve([only], 0.0, 10.0, auto=False,
                          specs=[{'t': 5.0, 'zoom': 2.0}],
                          hist_bins=(40, 16), defaults=DEFAULTS)
        assert [t.zoom for t in targets] == [2.0]

    def test_specs_outside_the_window_are_dropped(self):
        only = entry('s1', grains=[grain(onset=2.0, pointer_pos=1.0)])
        targets = resolve([only], 0.0, 10.0, auto=False,
                          specs=[{'t': 5.0}, {'t': 999.0}],
                          hist_bins=(40, 16), defaults=DEFAULTS)
        assert len(targets) == 1

    def test_nothing_to_magnify_is_an_empty_list(self):
        """Lente spenta e nessun target: nessuna lente. E' l'invariante di
        retrocompatibilita' — a flag spenti la pagina e' identica a prima."""
        only = entry('s1', grains=[grain(onset=2.0)])
        assert resolve([only], 0.0, 10.0, auto=False, specs=None,
                       hist_bins=(40, 16), defaults=DEFAULTS) == []
        assert resolve([], 0.0, 10.0, auto=True, specs=[{'t': 5.0}],
                       hist_bins=(40, 16), defaults=DEFAULTS) == []


class TestAutoTargetTieBreak:
    """Fra due stream ugualmente affollati la lente ne sceglie uno solo, e la
    scelta non puo' dipendere dall'ordine in cui capitano."""

    def _twins(self):
        """Due entry con lo stesso identico grumo: il conteggio pareggia."""
        grains = [grain(onset=1.0 + i * 0.01, pointer_pos=0.5) for i in range(6)]
        return [entry('primo', grains=grains), entry('secondo', grains=grains)]

    def test_the_first_wins_a_tie(self):
        """A parita' vince chi arriva prima: il confronto e' stretto, quindi
        un pari non spodesta il campione in carica. Con un confronto largo
        vincerebbe l'ultimo, e l'ordine di stream_entries — che e' l'ordine
        degli stream nel file — sposterebbe la lente."""
        target = auto_target(self._twins(), 0.0, 10.0,
                             hist_bins=(40, 16), defaults=DEFAULTS)
        assert target.entry['stream'].stream_id == 'primo'

    def test_the_tie_is_broken_the_same_way_reversed(self):
        """La regola e' 'il primo della lista', non 'quello che si chiama
        primo': invertendo la lista vince l'altro, e nulla resta ambiguo."""
        target = auto_target(list(reversed(self._twins())), 0.0, 10.0,
                             hist_bins=(40, 16), defaults=DEFAULTS)
        assert target.entry['stream'].stream_id == 'secondo'


class TestAutoTargetDegenerateSample:
    """L'istogramma ha bisogno di un'altezza: la posizione di lettura si
    distribuisce su [0, durata del sample]."""

    def test_a_zero_length_sample_does_not_break_the_histogram(self):
        """Un sample di durata nulla darebbe un range verticale degenere, e
        np.histogram2d su un range vuoto non produce il bin che serve. Il
        floor tiene in piedi il conto invece di far sparire la lente."""
        only = entry('s1', sample_duration=0.0,
                     grains=[grain(onset=2.0, pointer_pos=0.0)])
        target = auto_target([only], 0.0, 10.0,
                             hist_bins=(40, 16), defaults=DEFAULTS)
        assert target is not None
        assert target.t == pytest.approx(2.0)

    def test_a_negative_sample_duration_is_survived_too(self):
        """Stessa guardia, dal lato assurdo: una durata negativa non deve
        propagarsi dentro numpy come un range invertito."""
        only = entry('s1', sample_duration=-1.0,
                     grains=[grain(onset=2.0, pointer_pos=0.0)])
        assert auto_target([only], 0.0, 10.0,
                           hist_bins=(40, 16), defaults=DEFAULTS) is not None


class TestAutoTargetCountsNothing:
    """Il centro della lente e' il centroide dei grani del bin piu' popolato,
    non il centro geometrico del bin: la finestra e' stretta per via dello
    zoom, e centrata sui grani veri contiene davvero qualcosa.

    Quando invece NESSUN grano finisce dentro l'istogramma, non c'e' un bin
    su cui centrare e lo stream va saltato: `argmax` su una matrice di zeri
    restituisce comunque un indice, e senza la guardia sul conteggio la lente
    si punterebbe sul primo bin in alto a sinistra, cioe' sul vuoto.
    """

    def test_a_stream_whose_grains_fall_outside_the_range_is_skipped(self):
        """I grani sopra l'altezza del sample cadono fuori dal range
        dell'istogramma: nessun bin li conta."""
        fuori = entry('fuori', sample_duration=1.0,
                      grains=[grain(onset=2.0, pointer_pos=50.0)])
        assert auto_target([fuori], 0.0, 10.0,
                           hist_bins=(40, 16), defaults=DEFAULTS) is None

    def test_a_stream_with_grains_in_range_still_wins(self):
        """Controprova: con i grani dentro il range la lente si punta."""
        dentro = entry('dentro', sample_duration=1.0,
                       grains=[grain(onset=2.0, pointer_pos=0.5)])
        target = auto_target([dentro], 0.0, 10.0,
                             hist_bins=(40, 16), defaults=DEFAULTS)
        assert target is not None
        assert target.y == pytest.approx(0.5)
