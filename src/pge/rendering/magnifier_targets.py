# src/pge/rendering/magnifier_targets.py
"""
Dove puntare la lente di ingrandimento.

La lente ingrandisce una regione del piano tempo x posizione-di-lettura. Questo
modulo decide dove: il cluster piu' denso quando e' automatica, e i punti
chiesti dall'utente quando e' esplicita, risolti su uno stream e una quota
concreti.

Proiettare il cerchio, disegnare marker e connettori resta di ScoreVisualizer:
qui si arriva al bersaglio e ci si ferma. Come gli altri moduli di questa
famiglia, matplotlib non si importa.

Le `entries` sono le righe di stream_entries costruite da render_page. Il
modulo ne legge solo `stream` e `sample_duration`; il resto — l'asse su cui
proiettare — gli e' opaco e viaggia intatto fino a chi disegna.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from pge.rendering.grain_visuals import visible_grains


def grain_points(stream, t_start, t_end):
    """(onset, pointer_pos) dei grani dello stream visibili nella finestra."""
    return [(g.onset, g.pointer_pos)
            for g in visible_grains(stream, t_start, t_end)]


def densest_entry(entries, t_start, t_end):
    """Entry con piu' grani visibili nella finestra.

    Fallback alla prima: se nessuno stream ha grani, puntare la lente sul
    primo e' comunque meglio che non puntarla. None solo senza entries.
    """
    best, best_count = None, 0
    for candidate in entries:
        count = len(grain_points(candidate['stream'], t_start, t_end))
        if count > best_count:
            best, best_count = candidate, count
    return best or (entries[0] if entries else None)


# Ampiezza della finestra locale attorno all'istante bersaglio, come frazione
# della pagina: i grani entro questo raggio decidono la quota automatica.
LOCAL_WINDOW_RATIO = 0.05


def auto_y_at(stream, t, t_start, t_end):
    """Quota della lente dedotta dai grani vicini all'istante t.

    Media dei pointer_pos nella finestra locale attorno a t; se nessuno cade
    li' dentro, media di tutti i grani in pagina — una quota approssimata e'
    meglio di nessuna. None se non c'e' nessun grano: decide il chiamante.
    """
    points = grain_points(stream, t_start, t_end)
    if not points:
        return None

    radius = LOCAL_WINDOW_RATIO * (t_end - t_start)
    near = [y for (onset, y) in points if abs(onset - t) <= radius]
    return float(np.mean(near or [y for _, y in points]))


@dataclass(frozen=True)
class MagnifyTarget:
    """Una lente risolta: dove punta, quanto ingrandisce, dove si proietta.

    Sostituisce il dict a sette chiavi stringa che questa logica restituiva:
    gli stessi campi, ma dichiarati. `entry` e' la riga di stream_entries,
    opaca a questo modulo e usata da chi disegna per raggiungere l'asse.
    """
    entry: dict
    t: float
    y: float
    zoom: float
    out: float
    # Optional e non `float | None`: il progetto dichiara Python >= 3.9, dove
    # l'unione con | non e' valutabile. Qui `from __future__ import
    # annotations` la salverebbe finche' nessuno risolve le annotazioni, ma
    # basta un typing.get_type_hints — un serializzatore, un generatore di
    # doc — perche' torni a essere un errore, e il resto del modulo usa gia'
    # Optional.
    src: Optional[float]
    corner: str


def explicit_target(spec, entries, t_start, t_end, *, defaults):
    """Risolve un target chiesto dall'utente su stream e quota concreti.

    `spec` ha un solo campo obbligatorio, `t`; `y`, `zoom`, `out`, `src`,
    `corner` e `stream` sono opzionali. None se l'istante cade fuori dalla
    finestra (la lente appartiene a un'altra pagina) o se non ci sono entries.

    I confini seguono la regola della pagina: inizio incluso, fine esclusa,
    cosi' un target sul confine non finisce disegnato su due pagine.
    """
    t = spec.get('t')
    if t is None or not (t_start <= t < t_end):
        return None

    chosen = None
    stream_id = spec.get('stream')
    if stream_id is not None:
        chosen = next((e for e in entries
                       if e['stream'].stream_id == stream_id), None)
    # Nome assente o inesistente: la lente non sparisce, si ripiega sul piu'
    # denso.
    if chosen is None:
        chosen = densest_entry(entries, t_start, t_end)
    if chosen is None:
        return None

    y = spec.get('y')
    if y is None:
        y = auto_y_at(chosen['stream'], t, t_start, t_end)
    if y is None:
        # Nessun grano da cui dedurre la quota: meta' sample.
        y = chosen['sample_duration'] * 0.5

    return MagnifyTarget(
        entry=chosen, t=float(t), y=float(y),
        zoom=spec.get('zoom', defaults['zoom']),
        out=spec.get('out', defaults['out']),
        src=spec.get('src', defaults['src']),
        corner=spec.get('corner', defaults.get('corner', 'top-right')),
    )


def auto_target(entries, t_start, t_end, *, hist_bins, defaults):
    """Lente automatica sul grumo: il bin piu' popolato dell'istogramma
    tempo x posizione, fra tutti gli stream attivi.

    None se nessuno stream ha grani nella finestra.
    """
    n_time, n_pos = hist_bins
    best = None  # (conteggio, entry, t, y)

    for candidate in entries:
        points = grain_points(candidate['stream'], t_start, t_end)
        if not points:
            continue
        times = np.array([p[0] for p in points])
        positions = np.array([p[1] for p in points])
        y_max = max(candidate['sample_duration'], 1e-6)
        histogram, t_edges, y_edges = np.histogram2d(
            times, positions, bins=[n_time, n_pos],
            range=[[t_start, t_end], [0.0, y_max]])
        i, j = np.unravel_index(int(np.argmax(histogram)), histogram.shape)
        count = histogram[i, j]
        # Nessun grano dentro l'istogramma: argmax su una matrice di zeri
        # restituisce comunque (0,0), e senza questa uscita la lente si
        # punterebbe sul primo bin in alto a sinistra, cioe' sul vuoto.
        # Il caso e' coperto da TestAutoTargetCountsNothing, che pero' non
        # distingue questa uscita da quella su `in_bin` piu' sotto: quando il
        # conteggio e' nullo anche il ricontrollo trova la lista vuota, quindi
        # le due guardie si coprono a vicenda e a test si osserva solo il
        # risultato comune, cioe' che lo stream viene saltato.
        if count <= 0:
            continue

        # Centroide dei grani del bin, non centro geometrico del bin: la
        # finestra della lente e' stretta per via dello zoom, e centrata sui
        # grani reali contiene davvero qualcosa.
        in_bin = [(t, y) for t, y in points
                  if t_edges[i] <= t <= t_edges[i + 1]
                  and y_edges[j] <= y <= y_edges[j + 1]]
        # Praticamente irraggiungibile: il confronto qui sopra e' inclusivo su
        # entrambi gli estremi, quindi e' piu' largo del binning di numpy, e un
        # punto che il bin ha contato lo ricade dentro per forza. Resta perche'
        # l'indice del bin viene dall'aritmetica di numpy e il ricontrollo e'
        # nostra: a separarli, nel caso peggiore, c'e' un ULP — e centrare la
        # lente su una media di lista vuota darebbe nan, che si propaga fino
        # alle coordinate del disegno senza dire da dove viene.
        if not in_bin:  # pragma: no cover
            continue
        if best is None or count > best[0]:
            best = (count, candidate,
                    float(np.mean([t for t, _ in in_bin])),
                    float(np.mean([y for _, y in in_bin])))

    if best is None:
        return None

    _, chosen, t, y = best
    return MagnifyTarget(
        entry=chosen, t=t, y=y,
        zoom=defaults['zoom'], out=defaults['out'], src=defaults['src'],
        corner=defaults.get('corner', 'top-right'),
    )


def resolve(entries, t_start, t_end, *, auto, specs, hist_bins, defaults):
    """Le lenti di una pagina: l'automatica (se accesa) piu' le esplicite che
    cadono nella finestra.

    L'ordine e' contratto: l'automatica per prima, poi le esplicite nell'ordine
    dato. Chi disegna proietta in questa sequenza, e con piu' lenti sullo
    stesso angolo l'ordine decide le sovrapposizioni.

    Lista vuota se non c'e' niente da ingrandire: e' l'invariante di
    retrocompatibilita', a flag spenti la pagina resta identica.
    """
    if not entries:
        return []

    targets = []
    if auto:
        automatic = auto_target(entries, t_start, t_end,
                                hist_bins=hist_bins, defaults=defaults)
        if automatic is not None:
            targets.append(automatic)

    for spec in (specs or []):
        target = explicit_target(spec, entries, t_start, t_end,
                                 defaults=defaults)
        if target is not None:
            targets.append(target)

    return targets
